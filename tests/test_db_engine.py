"""Tests for lib.db.engine configuration."""

import os
from unittest.mock import patch

from lib.db.engine import get_database_url, is_sqlite_backend


class TestGetDatabaseUrl:
    def test_default_returns_sqlite(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            url = get_database_url()
            assert url.startswith("sqlite+aiosqlite:///")
            assert ".arcreel.db" in url

    def test_env_override(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://localhost/test"}):
            url = get_database_url()
            assert url == "postgresql+asyncpg://localhost/test"

    def test_railway_postgres_url_uses_asyncpg_driver(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pass@postgres.railway.internal:5432/railway"}):
            url = get_database_url()
            assert url == "postgresql+asyncpg://user:pass@postgres.railway.internal:5432/railway"


class TestIsSqliteBackend:
    def test_sqlite(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            assert is_sqlite_backend() is True

    def test_postgresql(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://localhost/test"}):
            assert is_sqlite_backend() is False
