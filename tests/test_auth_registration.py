"""数据库用户注册与登录的回归测试。"""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import lib.db.models  # noqa: F401 — ensure all models registered for Base.metadata
import server.auth as auth_module
from lib import db
from lib.db.base import Base


async def test_registered_user_can_log_in_and_has_own_identity(monkeypatch):
    """注册账号使用独立密码哈希，并在 JWT 身份中保留自己的 user id。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "async_session_factory", factory)

    try:
        created = await auth_module.create_registered_user("alice", "correct-horse-battery")
        assert created is not None
        assert created.id != "default"
        assert created.role == "user"

        duplicate = await auth_module.create_registered_user("alice", "another-password")
        assert duplicate is None

        authenticated = await auth_module.authenticate_credentials("alice", "correct-horse-battery")
        assert authenticated == created
        assert await auth_module.authenticate_credentials("alice", "wrong-password") is None
    finally:
        await engine.dispose()
