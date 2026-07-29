"""磁盘布局迁移：扁平项目目录与 _global_assets → 用户命名空间。

幂等、可重试；先复制校验再写迁移标记。失败条目记录到 summary，不抛致命异常。

作者: wanghaobo
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from lib.db.base import DEFAULT_USER_ID
from lib.project_manager import ProjectManager
from lib.project_paths import (
    LEGACY_GLOBAL_ASSETS_DIR,
    STORAGE_MIGRATION_MARKER,
    ProjectLocation,
    ensure_user_asset_subdirs,
    legacy_flat_project_root,
    legacy_global_assets_root,
    sync_list_all_projects,
    user_asset_relpath,
    user_assets_root,
    user_project_root,
    write_migration_marker,
)

logger = logging.getLogger(__name__)


@dataclass
class StorageMigrationSummary:
    projects_migrated: list[str] = field(default_factory=list)
    projects_skipped: list[str] = field(default_factory=list)
    projects_failed: dict[str, str] = field(default_factory=dict)
    global_assets_migrated: bool = False
    global_assets_files: int = 0
    asset_paths_updated: int = 0


def _dir_fingerprint(root: Path) -> str:
    """递归目录内容指纹（路径 + 大小），用于复制后校验。"""
    h = hashlib.sha256()
    if not root.exists():
        return h.hexdigest()
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            rel = path.relative_to(root).as_posix()
            h.update(rel.encode())
            h.update(str(path.stat().st_size).encode())
    return h.hexdigest()


def _copy_tree_verified(src: Path, dst: Path) -> None:
    if dst.exists():
        if is_migrated_dir(dst):
            return
        raise FileExistsError(f"目标已存在且未标记迁移完成: {dst}")
    src_fp = _dir_fingerprint(src)
    shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=False)
    dst_fp = _dir_fingerprint(dst)
    if src_fp != dst_fp:
        shutil.rmtree(dst, ignore_errors=True)
        raise RuntimeError(f"复制校验失败: {src} -> {dst}")


def is_migrated_dir(project_dir: Path) -> bool:
    return project_dir.joinpath(STORAGE_MIGRATION_MARKER).is_file()


def _migrate_single_project(
    projects_root: Path,
    *,
    name: str,
    user_id: str,
    project_id: str,
) -> str:
    """迁移单个扁平项目。返回 'migrated' | 'skipped'。"""
    dst = user_project_root(projects_root, user_id, project_id)
    if is_migrated_dir(dst):
        return "skipped"

    src = legacy_flat_project_root(projects_root, name)
    if not src.is_dir() or not (src / ProjectManager.PROJECT_FILE).is_file():
        # 新布局已存在或源已删除
        if dst.is_dir() and (dst / ProjectManager.PROJECT_FILE).is_file():
            write_migration_marker(dst, source="already_namespaced", user_id=user_id, project_id=project_id)
            return "skipped"
        raise FileNotFoundError(f"扁平项目目录不存在: {src}")

    if dst.exists() and not is_migrated_dir(dst):
        raise FileExistsError(f"目标目录已存在但未完成迁移: {dst}")

    _copy_tree_verified(src, dst)
    write_migration_marker(dst, source="flat", user_id=user_id, project_id=project_id)
    return "migrated"


def _migrate_global_assets(projects_root: Path, *, default_user_id: str = DEFAULT_USER_ID) -> tuple[bool, int, int]:
    """迁移 _global_assets → users/{default}/assets/ 并更新 DB image_path。"""
    legacy_root = legacy_global_assets_root(projects_root)
    if not legacy_root.is_dir():
        return False, 0, 0

    marker = legacy_root / STORAGE_MIGRATION_MARKER
    if marker.is_file():
        return False, 0, 0

    dst_root = ensure_user_asset_subdirs(user_assets_root(projects_root, default_user_id))
    files_copied = 0
    path_updates: list[tuple[str, str]] = []

    for asset_type_dir in legacy_root.iterdir():
        if not asset_type_dir.is_dir() or asset_type_dir.name.startswith("."):
            continue
        asset_type = asset_type_dir.name
        target_type_dir = dst_root / asset_type
        target_type_dir.mkdir(parents=True, exist_ok=True)
        for src_file in asset_type_dir.iterdir():
            if not src_file.is_file() or src_file.name.startswith("."):
                continue
            dst_file = target_type_dir / src_file.name
            if not dst_file.exists():
                shutil.copy2(src_file, dst_file)
                files_copied += 1
            old_rel = f"{LEGACY_GLOBAL_ASSETS_DIR}/{asset_type}/{src_file.name}"
            new_rel = user_asset_relpath(default_user_id, asset_type, src_file.name)
            if old_rel != new_rel:
                path_updates.append((old_rel, new_rel))

    marker.write_text("ok\n", encoding="utf-8")

    updated = _update_asset_image_paths(path_updates)
    return True, files_copied, updated


def _update_asset_image_paths(updates: list[tuple[str, str]]) -> int:
    if not updates:
        return 0
    from lib.project_paths import _sqlite_db_path

    db_path = _sqlite_db_path()
    if db_path is None:
        return 0
    import sqlite3

    count = 0
    try:
        with sqlite3.connect(db_path, timeout=30) as conn:
            for old_path, new_path in updates:
                cur = conn.execute(
                    "UPDATE assets SET image_path = ? WHERE image_path = ?",
                    (new_path, old_path),
                )
                count += cur.rowcount or 0
            conn.commit()
    except sqlite3.Error:
        logger.exception("更新 assets.image_path 失败（非致命）")
    return count


def run_storage_migration(
    projects_root: Path,
    *,
    project_locations: list[ProjectLocation] | None = None,
) -> StorageMigrationSummary:
    """入口：迁移所有 DB 登记项目的磁盘目录 + legacy 全局素材库。"""
    summary = StorageMigrationSummary()
    projects_root = Path(projects_root)

    locations = project_locations if project_locations is not None else sync_list_all_projects()
    for loc in locations:
        try:
            result = _migrate_single_project(
                projects_root,
                name=loc.name,
                user_id=loc.user_id,
                project_id=loc.project_id,
            )
            if result == "migrated":
                summary.projects_migrated.append(loc.name)
            else:
                summary.projects_skipped.append(loc.name)
        except Exception as exc:
            logger.warning("项目磁盘迁移失败 name=%s: %s", loc.name, exc)
            summary.projects_failed[loc.name] = str(exc)

    try:
        migrated, files, updated = _migrate_global_assets(projects_root)
        summary.global_assets_migrated = migrated
        summary.global_assets_files = files
        summary.asset_paths_updated = updated
    except Exception:
        logger.exception("全局素材库迁移失败（非致命）")

    return summary
