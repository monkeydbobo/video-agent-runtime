"""Async repository for API Key management.

作者: wanghaobo
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update

from lib.db.base import utc_now
from lib.db.models.api_key import ApiKey
from lib.db.repositories.base import BaseRepository, rowcount


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _row_to_dict(row: ApiKey) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "key_prefix": row.key_prefix,
        "created_at": _to_iso(row.created_at),
        "expires_at": _to_iso(row.expires_at),
        "last_used_at": _to_iso(row.last_used_at),
        "user_id": row.user_id,
    }


class ApiKeyRepository(BaseRepository):
    async def create(
        self,
        *,
        name: str,
        key_hash: str,
        key_prefix: str,
        user_id: str,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Create a new API key record bound to ``user_id``."""
        row = ApiKey(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            created_at=utc_now(),
            expires_at=expires_at,
            user_id=user_id,
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return _row_to_dict(row)

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return API keys owned by ``user_id`` (metadata only, no hashes)."""
        stmt = select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
        result = await self.session.execute(stmt)
        return [_row_to_dict(r) for r in result.scalars()]

    async def list_all(self) -> list[dict[str, Any]]:
        """Return all API keys (admin/unscoped). Prefer :meth:`list_for_user`."""
        stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
        result = await self.session.execute(stmt)
        return [_row_to_dict(r) for r in result.scalars()]

    async def get_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        """Look up a key by its SHA-256 hash. Returns full row including hash and user_id.

        Unscoped: authentication must resolve any user's key by hash.
        """
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "key_hash": row.key_hash,
            "key_prefix": row.key_prefix,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "last_used_at": row.last_used_at,
            "user_id": row.user_id,
        }

    async def get_by_id_for_user(self, key_id: int, user_id: str) -> dict[str, Any] | None:
        """Look up a key by ID scoped to owner. Includes key_hash for cache invalidation."""
        stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        d = _row_to_dict(row)
        d["key_hash"] = row.key_hash
        return d

    async def get_by_id(self, key_id: int) -> dict[str, Any] | None:
        """Look up a key by primary key (unscoped). Prefer :meth:`get_by_id_for_user`."""
        stmt = select(ApiKey).where(ApiKey.id == key_id)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        d = _row_to_dict(row)
        d["key_hash"] = row.key_hash
        return d

    async def delete_for_user(self, key_id: int, user_id: str) -> bool:
        """Delete a key by ID only if owned by ``user_id``."""
        result = await self.session.execute(sa_delete(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
        return rowcount(result) > 0

    async def delete(self, key_id: int) -> bool:
        """Delete a key by ID (unscoped). Prefer :meth:`delete_for_user`."""
        result = await self.session.execute(sa_delete(ApiKey).where(ApiKey.id == key_id))
        return rowcount(result) > 0

    async def touch_last_used(self, key_hash: str) -> None:
        """Update last_used_at for the given key hash."""
        await self.session.execute(update(ApiKey).where(ApiKey.key_hash == key_hash).values(last_used_at=utc_now()))
