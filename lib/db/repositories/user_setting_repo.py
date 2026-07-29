"""UserSetting repository（按 user_id 隔离）。

作者: wanghaobo
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select

from lib.db.models.user_setting import UserSetting
from lib.db.repositories.base import UserScopedRepository


class UserSettingRepository(UserScopedRepository):
    async def set(self, key: str, value: str) -> None:
        stmt = self._scope_query(
            select(UserSetting).where(UserSetting.key == key),
            UserSetting,
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            row.value = value
            row.updated_at = datetime.now(UTC)
        else:
            self.session.add(UserSetting(user_id=self.user_id, key=key, value=value))
        await self.session.flush()

    async def delete(self, key: str) -> None:
        stmt = delete(UserSetting).where(
            UserSetting.user_id == self.user_id,
            UserSetting.key == key,
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get(self, key: str, default: str = "") -> str:
        stmt = self._scope_query(
            select(UserSetting.value).where(UserSetting.key == key),
            UserSetting,
        )
        result = await self.session.execute(stmt)
        val = result.scalar_one_or_none()
        return val if val is not None else default

    async def get_all(self) -> dict[str, str]:
        stmt = self._scope_query(select(UserSetting), UserSetting)
        result = await self.session.execute(stmt)
        return {row.key: row.value for row in result.scalars()}
