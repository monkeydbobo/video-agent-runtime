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

    async def get_owner(self, name: str, user_id: str) -> str | None:
        """按 ``(user_id, name)`` 返回项目属主；无记录返回 ``None``。"""
        stmt = select(Project).where(Project.name == name, Project.user_id == user_id)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return row.user_id if row is not None else None

    async def create(self, name: str, user_id: str, *, project_id: str | None = None) -> Project:
        project = Project(id=project_id or str(uuid.uuid4()), name=name, user_id=user_id)
        self.session.add(project)
        await self.session.flush()
        return project

    async def ensure(self, name: str, user_id: str) -> Project:
        """按 ``(user_id, name)`` 幂等创建，不复用其他用户的同名记录。"""
        existing = await self.get_by_name(user_id, name)
        if existing is not None:
            return existing
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

    async def list_projects(self, user_id: str) -> list[Project]:
        """列出指定用户的项目记录，供请求作用域绑定不可变 project_id。"""
        stmt = select(Project).where(Project.user_id == user_id).order_by(Project.name)
        return list((await self.session.execute(stmt)).scalars())

    async def list_all_projects(self) -> list[Project]:
        """列出全部项目记录，仅供启动迁移等显式系统级流程。"""
        return list((await self.session.execute(select(Project).order_by(Project.name))).scalars())

    async def ownership_map(self, user_id: str) -> dict[str, str]:
        """返回指定用户的 ``{项目名: user_id}`` 映射。"""
        rows = (
            await self.session.execute(select(Project.name, Project.user_id).where(Project.user_id == user_id))
        ).all()
        return {name: user_id for name, user_id in rows}
