"""用户命名空间磁盘布局与同步 DB 路径解析。

布局::
    users/{user_id}/projects/{project_id}/   — 项目私有目录
    users/{user_id}/assets/{type}/           — 全局资产库图片

扁平 ``projects/{name}/`` 与 ``_global_assets/`` 在迁移窗口内只读回退。

作者: wanghaobo
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

USERS_DIR = "users"
LEGACY_GLOBAL_ASSETS_DIR = "_global_assets"
STORAGE_MIGRATION_MARKER = ".arcreel-storage-migrated"
STORAGE_MIGRATION_MANIFEST = ".arcreel-storage-manifest.json"

_PROJECT_USER_SCOPE: ContextVar[str | None] = ContextVar("project_user_scope", default=None)
_PROJECT_ID_SCOPE: ContextVar[dict[str, str]] = ContextVar("project_id_scope", default={})


def bind_project_user_scope(
    user_id: str,
    *,
    project_ids: dict[str, str] | None = None,
) -> None:
    """把当前请求绑定到用户项目命名空间及已授权的项目 ID。"""
    _PROJECT_USER_SCOPE.set(user_id)
    _PROJECT_ID_SCOPE.set(dict(project_ids or {}))


def current_project_user_scope() -> str | None:
    """返回当前请求/任务绑定的用户 ID；系统级调用返回 ``None``。"""
    return _PROJECT_USER_SCOPE.get()


def current_project_id_scope(project_name: str) -> str | None:
    """返回当前请求中已授权项目的不可变 ID。"""
    return _PROJECT_ID_SCOPE.get().get(project_name)


def current_project_ids_scope() -> dict[str, str]:
    """返回当前请求已授权的全部项目名与 ID。"""
    return dict(_PROJECT_ID_SCOPE.get())


@contextmanager
def project_user_scope(
    user_id: str,
    *,
    project_name: str | None = None,
    project_id: str | None = None,
    project_ids: dict[str, str] | None = None,
) -> Iterator[None]:
    """在后台任务执行期间显式绑定项目用户，并在结束时恢复旧作用域。"""
    if project_ids is not None and (project_name is not None or project_id is not None):
        raise ValueError("project_ids 不能与 project_name/project_id 同时指定")
    if (project_name is None) != (project_id is None):
        raise ValueError("project_name 与 project_id 必须同时指定")
    scoped_ids = dict(project_ids or {})
    if project_name is not None and project_id is not None:
        scoped_ids[project_name] = project_id
    user_token: Token[str | None] = _PROJECT_USER_SCOPE.set(user_id)
    project_token: Token[dict[str, str]] = _PROJECT_ID_SCOPE.set(scoped_ids)
    try:
        yield
    finally:
        _PROJECT_ID_SCOPE.reset(project_token)
        _PROJECT_USER_SCOPE.reset(user_token)


@dataclass(frozen=True)
class ProjectLocation:
    user_id: str
    project_id: str
    name: str


def user_project_root(projects_root: Path, user_id: str, project_id: str) -> Path:
    return projects_root / USERS_DIR / user_id / "projects" / project_id


def user_assets_root(projects_root: Path, user_id: str) -> Path:
    return projects_root / USERS_DIR / user_id / "assets"


def legacy_flat_project_root(projects_root: Path, name: str) -> Path:
    return projects_root / name


def legacy_global_assets_root(projects_root: Path) -> Path:
    return projects_root / LEGACY_GLOBAL_ASSETS_DIR


def user_asset_relpath(user_id: str, asset_type: str, filename: str) -> str:
    """DB 持久化的相对路径（相对 projects_root）。"""
    return f"{USERS_DIR}/{user_id}/assets/{asset_type}/{filename}"


def resolve_asset_file(projects_root: Path, rel_path: str, *, user_id: str | None = None) -> Path | None:
    """按相对路径解析素材文件；兼容 legacy ``_global_assets/`` 与用户私有根。"""
    if not rel_path or ".." in rel_path:
        return None
    candidate = projects_root / rel_path
    if candidate.exists() and candidate.is_file():
        try:
            candidate.resolve().relative_to(projects_root.resolve())
        except ValueError:
            return None
        return candidate

    # legacy → 用户私有根（迁移后 DB 可能仍存旧前缀）
    if rel_path.startswith(f"{LEGACY_GLOBAL_ASSETS_DIR}/") and user_id:
        suffix = rel_path[len(LEGACY_GLOBAL_ASSETS_DIR) + 1 :]
        migrated = user_assets_root(projects_root, user_id) / suffix
        if migrated.exists() and migrated.is_file():
            return migrated
    return None


def _sqlite_db_path() -> Path | None:
    from lib.app_data_dir import app_data_dir

    db_path = app_data_dir() / ".arcreel.db"
    return db_path if db_path.exists() else None


def sync_lookup_project(name: str, user_id: str | None = None) -> ProjectLocation | None:
    """同步查询 projects 表，供 ProjectManager 等同步代码解析新布局路径。"""
    db_path = _sqlite_db_path()
    if db_path is None:
        return None
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            if user_id is not None:
                row = conn.execute(
                    "SELECT id, user_id, name FROM projects WHERE name = ? AND user_id = ? LIMIT 1",
                    (name, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id, user_id, name FROM projects WHERE name = ? LIMIT 1",
                    (name,),
                ).fetchone()
    except sqlite3.Error:
        logger.exception("sync_lookup_project failed for name=%s", name)
        return None
    if row is None:
        return None
    project_id, owner_id, row_name = row
    return ProjectLocation(user_id=str(owner_id), project_id=str(project_id), name=str(row_name))


def sync_list_project_names(user_id: str | None = None) -> list[str]:
    db_path = _sqlite_db_path()
    if db_path is None:
        return []
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            if user_id is not None:
                rows = conn.execute(
                    "SELECT name FROM projects WHERE user_id = ? ORDER BY name",
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT name FROM projects ORDER BY name").fetchall()
    except sqlite3.Error:
        logger.exception("sync_list_project_names failed")
        return []
    return [str(r[0]) for r in rows]


def sync_list_all_projects() -> list[ProjectLocation]:
    db_path = _sqlite_db_path()
    if db_path is None:
        return []
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            rows = conn.execute("SELECT id, user_id, name FROM projects ORDER BY name").fetchall()
    except sqlite3.Error:
        logger.exception("sync_list_all_projects failed")
        return []
    return [ProjectLocation(user_id=str(u), project_id=str(pid), name=str(n)) for pid, u, n in rows]


def write_migration_marker(project_dir: Path, *, source: str, user_id: str, project_id: str) -> None:
    manifest = {
        "version": 1,
        "source": source,
        "user_id": user_id,
        "project_id": project_id,
    }
    project_dir.joinpath(STORAGE_MIGRATION_MARKER).write_text("ok\n", encoding="utf-8")
    project_dir.joinpath(STORAGE_MIGRATION_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_migrated_project_dir(project_dir: Path) -> bool:
    return project_dir.joinpath(STORAGE_MIGRATION_MARKER).is_file()


def ensure_user_asset_subdirs(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("character", "scene", "prop"):
        (root / sub).mkdir(exist_ok=True)
    return root


def assert_inside(base: Path, target: Path) -> Path:
    real = os.path.realpath(target)
    bound = os.path.realpath(base) + os.sep
    if not real.startswith(bound):
        raise ValueError(f"路径越界: {target}")
    return Path(real)
