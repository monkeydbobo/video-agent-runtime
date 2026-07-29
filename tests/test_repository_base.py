"""Tests for BaseRepository and UserScopedRepository.

作者: wanghaobo
"""

import pytest
from sqlalchemy import select

from lib.db.models import Task
from lib.db.repositories.base import BaseRepository, UserScopedRepository


class TestBaseRepository:
    def test_scope_query_noop(self):
        """_scope_query returns stmt unchanged by default."""
        repo = BaseRepository.__new__(BaseRepository)
        stmt = select(Task)
        result = repo._scope_query(stmt, Task)
        assert str(result) == str(stmt)

    def test_scope_query_overridable(self):
        """Subclass can override _scope_query to add filters."""

        class ScopedRepo(BaseRepository):
            def _scope_query(self, stmt, model):
                return stmt.where(model.user_id == "test-user")

        repo = ScopedRepo.__new__(ScopedRepo)
        stmt = select(Task)
        result = repo._scope_query(stmt, Task)
        assert "user_id" in str(result)


class TestUserScopedRepository:
    def test_requires_user_id(self):
        with pytest.raises(ValueError, match="user_id"):
            UserScopedRepository(session=None, user_id="")  # type: ignore[arg-type]

    def test_scopes_by_user_id(self):
        repo = UserScopedRepository.__new__(UserScopedRepository)
        repo.user_id = "alice-id"
        stmt = select(Task)
        result = repo._scope_query(stmt, Task)
        # user_id 以绑定参数出现，须内联字面量才能断言过滤值本身
        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "user_id" in compiled
        assert "alice-id" in compiled
