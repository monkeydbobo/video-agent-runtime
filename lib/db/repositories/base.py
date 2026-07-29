"""Repository base class with mandatory user scoping support.

作者: wanghaobo
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db.base import Base


class BaseRepository:
    """Repository base class. Provides ``_scope_query`` override point."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _scope_query(self, stmt: Select, model: type[Base]) -> Select:
        """Query scope limiter. Subclasses can override to inject additional filters."""
        return stmt


class UserScopedRepository(BaseRepository):
    """Repository that always filters by ``user_id``.

    Construction requires an explicit ``user_id``. Methods must not fall back to
    ``DEFAULT_USER_ID``. System/worker code that needs cross-user access should use
    a dedicated unscoped repository, not this base.
    """

    def __init__(self, session: AsyncSession, *, user_id: str):
        if not user_id:
            raise ValueError("user_id is required for UserScopedRepository")
        super().__init__(session)
        self.user_id = user_id

    def _scope_query(self, stmt: Select, model: type[Base]) -> Select:
        if hasattr(model, "user_id"):
            return stmt.where(model.user_id == self.user_id)  # type: ignore[attr-defined]
        return stmt


def rowcount(result: Any) -> int:
    """SQLAlchemy AsyncResult.rowcount 在当前 stub 中是 Any，统一在此 narrow。"""
    return result.rowcount or 0
