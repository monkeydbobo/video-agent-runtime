"""Google GIS ID-token login tests.

作者: wanghaobo
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import lib.db.models  # noqa: F401 — ensure all models registered for Base.metadata
import server.auth as auth_module
from lib import db
from lib.db.base import Base
from server.routers import auth as auth_router


@pytest.fixture()
async def google_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "async_session_factory", factory)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture()
def client():
    auth_module._cached_token_secret = None
    auth_module._cached_password_hash = None
    with patch.dict(
        os.environ,
        {
            "AUTH_USERNAME": "testuser",
            "AUTH_PASSWORD": "testpass",
            "AUTH_TOKEN_SECRET": "test-router-secret-key-at-least-32-bytes-long",
            "AUTH_ENABLED": "true",
            "AUTH_REGISTRATION_ENABLED": "true",
            "GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com",
        },
    ):
        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/v1")
        with TestClient(app) as c:
            yield c


def test_auth_status_exposes_google_client_id(client):
    resp = client.get("/api/v1/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["google_enabled"] is True
    assert data["google_client_id"] == "test-client.apps.googleusercontent.com"


async def test_google_login_creates_user(client, google_db, monkeypatch):
    monkeypatch.setattr(
        auth_router,
        "verify_google_id_token",
        lambda _token: {"sub": "google-sub-1", "email": "alice@example.com"},
    )
    notified: list[str] = []

    async def notify(username: str) -> None:
        notified.append(username)

    monkeypatch.setattr(auth_router, "notify_new_registration", notify)

    resp = client.post("/api/v1/auth/google", json={"id_token": "fake." + ("x" * 40)})
    assert resp.status_code == 200
    payload = auth_module.verify_token(resp.json()["access_token"])
    assert payload is not None
    assert payload["role"] == "user"
    assert notified  # new Google account notifies

    # Second login: same subject, no new notification
    notified.clear()
    resp2 = client.post("/api/v1/auth/google", json={"id_token": "fake." + ("y" * 40)})
    assert resp2.status_code == 200
    payload2 = auth_module.verify_token(resp2.json()["access_token"])
    assert payload2 is not None
    assert payload2["uid"] == payload["uid"]
    assert notified == []


async def test_google_login_rejects_invalid_token(client, google_db, monkeypatch):
    def _boom(_token: str) -> dict[str, str]:
        raise ValueError("google_token_invalid")

    monkeypatch.setattr(auth_router, "verify_google_id_token", _boom)
    resp = client.post("/api/v1/auth/google", json={"id_token": "fake." + ("z" * 40)})
    assert resp.status_code == 401


async def test_google_login_rejects_new_user_when_registration_disabled(client, google_db, monkeypatch):
    monkeypatch.setattr(auth_router, "is_registration_enabled", lambda: False)
    monkeypatch.setattr(
        auth_router,
        "verify_google_id_token",
        lambda _token: {"sub": "google-sub-2", "email": "bob@example.com"},
    )
    resp = client.post("/api/v1/auth/google", json={"id_token": "fake." + ("a" * 40)})
    assert resp.status_code == 403


def test_username_from_email_sanitizes():
    assert auth_module._username_from_email("Hello.World+tag@example.com") == "Hello.Worldtag"
    assert auth_module._username_from_email("ab@example.com") == "abx"
    assert auth_module._username_from_email(".leading@example.com").startswith("user")
