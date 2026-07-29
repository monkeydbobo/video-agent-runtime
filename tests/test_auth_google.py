"""Google GIS ID-token login tests.

作者: wanghaobo
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import lib.db.models  # noqa: F401
import server.auth as auth_module
from lib import db
from lib.db.base import Base
from server.routers import auth as auth_router


@pytest.fixture()
def google_env(monkeypatch):
    auth_module._cached_token_secret = None
    auth_module._cached_password_hash = None
    monkeypatch.setenv("AUTH_USERNAME", "testuser")
    monkeypatch.setenv("AUTH_PASSWORD", "testpass")
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-router-secret-key-at-least-32-bytes-long")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "true")


@pytest.fixture()
async def db_factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "async_session_factory", factory)
    yield factory
    await engine.dispose()


@pytest.fixture()
def client(google_env):
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


def test_auth_status_hides_google_when_unset(monkeypatch):
    auth_module._cached_token_secret = None
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-router-secret-key-at-least-32-bytes-long")
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1")
    with TestClient(app) as c:
        data = c.get("/api/v1/auth/status").json()
    assert data["google_enabled"] is False
    assert data["google_client_id"] is None


@pytest.mark.asyncio
async def test_google_login_creates_user_and_reuses_identity(client, db_factory, monkeypatch):
    claims = {
        "sub": "google-sub-1",
        "email": "alice@example.com",
        "email_verified": True,
        "iss": "https://accounts.google.com",
    }
    monkeypatch.setattr(auth_router, "verify_google_id_token", lambda _token: claims)

    notified: list[str] = []

    async def notify(username: str) -> None:
        notified.append(username)

    monkeypatch.setattr(auth_router, "notify_new_registration", notify)

    resp = client.post("/api/v1/auth/google", json={"id_token": "fake-token-" + ("x" * 20)})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    payload = auth_module.verify_token(token)
    assert payload is not None
    assert payload["role"] == "user"
    assert len(notified) == 1

    resp2 = client.post("/api/v1/auth/google", json={"id_token": "fake-token-" + ("y" * 20)})
    assert resp2.status_code == 200
    payload2 = auth_module.verify_token(resp2.json()["access_token"])
    assert payload2 is not None
    assert payload2["uid"] == payload["uid"]
    assert payload2["sub"] == payload["sub"]
    assert len(notified) == 1  # returning user: no second Discord notify


@pytest.mark.asyncio
async def test_google_login_rejects_invalid_token(client, db_factory, monkeypatch):
    def _raise(_token: str):
        raise auth_module.GoogleIdTokenError("google_token_invalid")

    monkeypatch.setattr(auth_router, "verify_google_id_token", _raise)
    resp = client.post("/api/v1/auth/google", json={"id_token": "fake-token-" + ("z" * 20)})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_google_login_rejects_new_user_when_registration_disabled(client, db_factory, monkeypatch):
    monkeypatch.setenv("AUTH_REGISTRATION_ENABLED", "false")
    claims = {
        "sub": "google-sub-closed",
        "email": "closed@example.com",
        "email_verified": True,
        "iss": "accounts.google.com",
    }
    monkeypatch.setattr(auth_router, "verify_google_id_token", lambda _token: claims)
    resp = client.post("/api/v1/auth/google", json={"id_token": "fake-token-" + ("a" * 20)})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_google_login_existing_identity_rejects_email_owned_by_other_user(client, db_factory, monkeypatch):
    """A Google identity whose email now belongs to another account must not 500."""
    import uuid

    from lib.db.models.oauth_identity import OAuthIdentity
    from lib.db.models.user import User

    async with db_factory() as session:
        linked = User(id=str(uuid.uuid4()), username="linked", email="old@example.com", role="user")
        other = User(id=str(uuid.uuid4()), username="other", email="taken@example.com", role="user")
        session.add_all(
            [
                linked,
                other,
                OAuthIdentity(
                    id=str(uuid.uuid4()),
                    user_id=linked.id,
                    provider="google",
                    subject="google-sub-conflict",
                    email="old@example.com",
                ),
            ]
        )
        await session.commit()

    claims = {
        "sub": "google-sub-conflict",
        "email": "taken@example.com",
        "email_verified": True,
        "iss": "https://accounts.google.com",
    }
    monkeypatch.setattr(auth_router, "verify_google_id_token", lambda _token: claims)

    resp = client.post("/api/v1/auth/google", json={"id_token": "fake-token-" + ("c" * 20)})
    assert resp.status_code == 403

    async with db_factory() as session:
        from sqlalchemy import select

        refreshed = (await session.execute(select(User).where(User.username == "linked"))).scalar_one()
        assert refreshed.email == "old@example.com"


@pytest.mark.asyncio
async def test_google_login_existing_identity_updates_email_when_free(client, db_factory, monkeypatch):
    import uuid

    from sqlalchemy import select

    from lib.db.models.oauth_identity import OAuthIdentity
    from lib.db.models.user import User

    async with db_factory() as session:
        linked = User(id=str(uuid.uuid4()), username="mover", email="before@example.com", role="user")
        session.add_all(
            [
                linked,
                OAuthIdentity(
                    id=str(uuid.uuid4()),
                    user_id=linked.id,
                    provider="google",
                    subject="google-sub-move",
                    email="before@example.com",
                ),
            ]
        )
        await session.commit()

    claims = {
        "sub": "google-sub-move",
        "email": "after@example.com",
        "email_verified": True,
        "iss": "https://accounts.google.com",
    }
    monkeypatch.setattr(auth_router, "verify_google_id_token", lambda _token: claims)

    resp = client.post("/api/v1/auth/google", json={"id_token": "fake-token-" + ("d" * 20)})
    assert resp.status_code == 200

    async with db_factory() as session:
        refreshed = (await session.execute(select(User).where(User.username == "mover"))).scalar_one()
        assert refreshed.email == "after@example.com"
        identity = (
            await session.execute(select(OAuthIdentity).where(OAuthIdentity.subject == "google-sub-move"))
        ).scalar_one()
        assert identity.email == "after@example.com"


def test_username_from_google_email_sanitizes():
    assert auth_module._username_from_google_email("Foo.Bar+tag@gmail.com") == "foo.bartag"
    assert auth_module._username_from_google_email("___@x.com") == "user"


def test_verify_google_id_token_requires_verified_email(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")

    with patch("google.oauth2.id_token.verify_oauth2_token") as verify:
        verify.return_value = {
            "sub": "s1",
            "email": "u@example.com",
            "email_verified": False,
            "iss": "https://accounts.google.com",
        }
        with pytest.raises(auth_module.GoogleIdTokenError) as exc:
            auth_module.verify_google_id_token("tok")
        assert str(exc.value) == "google_email_unverified"
