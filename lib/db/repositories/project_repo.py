"""ProjectRepository: 项目归属（project id / name → user_id）的异步 CRUD。

作者: wanghaobo
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from lib.db.models.project import Project
from lib.db.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):
    async def get(self, project_id: str) -> Project | None:
        return (await self.session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()

    async def get_by_name(self, user_id: str, name: str) -> Project | None:
        return (
            await self.session.execute(select(Project).where(Project.user_id == user_id, Project.name == name))
        ).scalar_one_or_none()

    async def get_owner(self, name: str, user_id: str | None = None) -> str | None:
        """返回项目归属的 user_id；无记录返回 None。

        ``user_id`` 可选：传入时按 (user_id, name) 精确匹配；省略时按 name 查首条（兼容单租户期）。
        """
        stmt = select(Project).where(Project.name == name)
        if user_id is not None:
            stmt = stmt.where(Project.user_id == user_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return row.user_id if row is not None else None

    async def create(self, name: str, user_id: str, *, project_id: str | None = None) -> Project:
        project = Project(id=project_id or str(uuid.uuid4()), name=name, user_id=user_id)
        self.session.add(project)
        await self.session.flush()
        return project

    async def ensure(self, name: str, user_id: str) -> Project:
        """存在则原样返回（不改归属），不存在则以 user_id 创建。

        先按 (user_id, name) 精确匹配；若 name 已被其他用户登记则返回既有记录，
        保证 ``register_project_owner`` 幂等且不覆盖归属。
        """
        existing = await self.get_by_name(user_id, name)
        if existing is not None:
            return existing
        stmt = select(Project).where(Project.name == name)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row
        return await self.create(name, user_id)

    async def delete(self, name: str, user_id: str | None = None) -> None:
        stmt = delete(Project).where(Project.name == name)
        if user_id is not None:
            stmt = stmt.where(Project.user_id == user_id)
        await self.session.execute(stmt)
        await self.session.flush()

    async def list_names(self, user_id: str | None = None) -> list[str]:
        """列出项目名。user_id 为 None 时返回全部（admin 视图）。"""
        stmt = select(Project.name)
        if user_id is not None:
            stmt = stmt.where(Project.user_id == user_id)
        return list((await self.session.execute(stmt)).scalars())

    async def ownership_map(self) -> dict[str, str]:
        """返回 {项目名: user_id} 全量映射（用于列表过滤与导入冲突判定）。"""
        rows = (await self.session.execute(select(Project.name, Project.user_id))).all()
        return {name: user_id for name, user_id in rows}
