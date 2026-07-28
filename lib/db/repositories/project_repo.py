"""ProjectRepository: 项目归属（project name → user_id）的异步 CRUD。"""

from __future__ import annotations

from sqlalchemy import delete, select

from lib.db.base import DEFAULT_USER_ID
from lib.db.models.project import Project
from lib.db.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):
    async def get(self, name: str) -> Project | None:
        return (await self.session.execute(select(Project).where(Project.name == name))).scalar_one_or_none()

    async def get_owner(self, name: str) -> str | None:
        """返回项目归属的 user_id；无记录返回 None（存量项目视为 default 用户所有）。"""
        row = await self.get(name)
        return row.user_id if row is not None else None

    async def create(self, name: str, user_id: str = DEFAULT_USER_ID) -> Project:
        project = Project(name=name, user_id=user_id)
        self.session.add(project)
        await self.session.flush()
        return project

    async def ensure(self, name: str, user_id: str = DEFAULT_USER_ID) -> Project:
        """存在则原样返回（不改归属），不存在则以 user_id 创建。"""
        existing = await self.get(name)
        if existing is not None:
            return existing
        return await self.create(name, user_id)

    async def delete(self, name: str) -> None:
        await self.session.execute(delete(Project).where(Project.name == name))
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
