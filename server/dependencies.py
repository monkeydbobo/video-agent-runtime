"""Shared FastAPI dependency factories."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lib.config.service import ConfigService
from lib.db import get_async_session
from server.auth import CurrentUser


def get_config_service(
    _user: CurrentUser,
    session: AsyncSession = Depends(get_async_session),
) -> ConfigService:
    return ConfigService(session, user_id=_user.id)
