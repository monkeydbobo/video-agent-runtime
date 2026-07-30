#!/usr/bin/env python3
"""把现有项目视频与成片幂等回填到已配置的对象存储。"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from lib.db import async_session_factory
from lib.db.repositories.project_repo import ProjectRepository
from lib.object_storage import ProjectObjectStorage, get_project_object_storage
from lib.project_manager import get_project_manager

MEDIA_SUBDIRS = ("videos", "output")
MEDIA_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}


@dataclass(frozen=True)
class MigrationItem:
    user_id: str
    project_name: str
    project_path: Path
    file_path: Path


async def _discover(project_name: str | None) -> list[MigrationItem]:
    async with async_session_factory() as session:
        projects = await ProjectRepository(session).list_all_projects()

    manager = get_project_manager()
    items: list[MigrationItem] = []
    for project in projects:
        if project_name is not None and project.name != project_name:
            continue
        project_path = manager.get_project_path(
            project.name,
            user_id=project.user_id,
            project_id=project.id,
        )
        for subdir in MEDIA_SUBDIRS:
            root = project_path / subdir
            if not root.is_dir():
                continue
            for file_path in sorted(root.rglob("*")):
                if file_path.is_file() and file_path.suffix.lower() in MEDIA_SUFFIXES:
                    items.append(
                        MigrationItem(
                            user_id=project.user_id,
                            project_name=project.name,
                            project_path=project_path,
                            file_path=file_path,
                        )
                    )
    return items


async def _upload(store: ProjectObjectStorage, item: MigrationItem, semaphore: asyncio.Semaphore) -> tuple[str, int]:
    async with semaphore:
        result = await asyncio.to_thread(
            store.publish_project_file,
            item.file_path,
            project_path=item.project_path,
            project_name=item.project_name,
            user_id=item.user_id,
        )
        return result.key, result.size


async def run(*, project_name: str | None, concurrency: int, dry_run: bool) -> int:
    store = get_project_object_storage()
    if store is None:
        raise RuntimeError("对象存储未配置，无法迁移")
    items = await _discover(project_name)
    total_bytes = sum(item.file_path.stat().st_size for item in items)
    print(f"发现 {len(items)} 个视频文件，共 {total_bytes / 1024 / 1024:.1f} MiB")
    if dry_run:
        for item in items:
            print(f"[dry-run] {item.project_name}: {item.file_path.relative_to(item.project_path)}")
        return 0

    semaphore = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(*(_upload(store, item, semaphore) for item in items))
    uploaded_bytes = sum(size for _, size in results)
    print(f"上传完成：{len(results)} 个对象，共 {uploaded_bytes / 1024 / 1024:.1f} MiB")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="回填项目视频与成片到 S3 兼容对象存储")
    parser.add_argument("--project", help="仅迁移指定逻辑项目名；默认迁移全部项目")
    parser.add_argument("--concurrency", type=int, default=3, help="并发上传数，默认 3")
    parser.add_argument("--dry-run", action="store_true", help="只列出待迁移文件")
    args = parser.parse_args()
    if args.concurrency < 1 or args.concurrency > 16:
        parser.error("--concurrency 必须在 1 到 16 之间")
    return asyncio.run(run(project_name=args.project, concurrency=args.concurrency, dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
