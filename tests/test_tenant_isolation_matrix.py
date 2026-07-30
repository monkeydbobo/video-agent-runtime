"""Alice / Bob / Admin 三身份隔离矩阵（验收用）。

作者: wanghaobo
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from lib.db.base import DEFAULT_USER_ID
from lib.db.repositories.api_key_repository import ApiKeyRepository
from lib.db.repositories.asset_repo import AssetRepository
from lib.db.repositories.credential_repository import CredentialRepository
from lib.db.repositories.project_repo import ProjectRepository
from lib.project_manager import ProjectManager
from server.auth import (
    CurrentUserInfo,
    create_media_token,
    get_current_user,
    verify_media_token,
)
from server.error_handlers import register_error_handlers

pytestmark = pytest.mark.integration

ADMIN = CurrentUserInfo(id=DEFAULT_USER_ID, sub="admin", role="admin")
ALICE = CurrentUserInfo(id="alice-id", sub="alice", role="user")
BOB = CurrentUserInfo(id="bob-id", sub="bob", role="user")


async def _seed_project(factory, name: str, user_id: str) -> None:
    async with factory() as session:
        async with session.begin():
            await ProjectRepository(session).create(name, user_id)


class TestSameNameAcrossUsers:
    async def test_same_project_name_per_user(self, project_ownership_db):
        factory = project_ownership_db
        await _seed_project(factory, "shared-name", "alice-id")
        await _seed_project(factory, "shared-name", "bob-id")

        async with factory() as session:
            alice = await ProjectRepository(session).get_by_name("alice-id", "shared-name")
            bob = await ProjectRepository(session).get_by_name("bob-id", "shared-name")
        assert alice is not None and bob is not None
        assert alice.id != bob.id
        assert alice.user_id == "alice-id"
        assert bob.user_id == "bob-id"

    @pytest.mark.integration
    async def test_same_project_name_loads_from_each_user_namespace(self, tmp_path, project_ownership_db):
        factory = project_ownership_db
        await _seed_project(factory, "shared-name", "alice-id")
        await _seed_project(factory, "shared-name", "bob-id")

        async with factory() as session:
            alice = await ProjectRepository(session).get_by_name("alice-id", "shared-name")
            bob = await ProjectRepository(session).get_by_name("bob-id", "shared-name")
        assert alice is not None and bob is not None

        pm = ProjectManager(tmp_path / "projects")
        pm.create_project("shared-name", user_id="alice-id", project_id=alice.id)
        pm.create_project_metadata(
            "shared-name",
            "Alice project",
            "",
            "narration",
            user_id="alice-id",
            project_id=alice.id,
        )
        pm.create_project("shared-name", user_id="bob-id", project_id=bob.id)
        pm.create_project_metadata(
            "shared-name",
            "Bob project",
            "",
            "narration",
            user_id="bob-id",
            project_id=bob.id,
        )

        from lib.project_paths import project_user_scope

        with project_user_scope("alice-id"):
            assert pm.load_project("shared-name")["title"] == "Alice project"
        with project_user_scope("bob-id"):
            assert pm.load_project("shared-name")["title"] == "Bob project"

    async def test_same_asset_name_per_user(self, project_ownership_db):
        factory = project_ownership_db
        async with factory() as session:
            async with session.begin():
                await AssetRepository(session, user_id="alice-id").create(
                    type="character", name="hero", description="a"
                )
                await AssetRepository(session, user_id="bob-id").create(type="character", name="hero", description="b")
        async with factory() as session:
            alice_assets = await AssetRepository(session, user_id="alice-id").list(type="character", q=None)
            bob_assets = await AssetRepository(session, user_id="bob-id").list(type="character", q=None)
        assert len(alice_assets) == 1
        assert len(bob_assets) == 1
        assert alice_assets[0].description == "a"
        assert bob_assets[0].description == "b"

    async def test_same_api_key_name_per_user(self, project_ownership_db):
        factory = project_ownership_db
        async with factory() as session:
            async with session.begin():
                await ApiKeyRepository(session).create(
                    name="ci",
                    key_hash="hash-alice",
                    key_prefix="arc-alice",
                    user_id="alice-id",
                )
                await ApiKeyRepository(session).create(
                    name="ci",
                    key_hash="hash-bob",
                    key_prefix="arc-bob",
                    user_id="bob-id",
                )
        async with factory() as session:
            alice_keys = await ApiKeyRepository(session).list_for_user("alice-id")
            bob_keys = await ApiKeyRepository(session).list_for_user("bob-id")
        assert len(alice_keys) == 1
        assert len(bob_keys) == 1
        assert alice_keys[0]["name"] == bob_keys[0]["name"] == "ci"


class TestCredentialIsolation:
    async def test_active_credential_is_per_user(self, project_ownership_db):
        factory = project_ownership_db
        async with factory() as session:
            async with session.begin():
                a = await CredentialRepository(session, user_id="alice-id").create(
                    provider="gemini", name="alice-key", api_key="alice-secret"
                )
                await CredentialRepository(session, user_id="alice-id").activate(a.id, "gemini")
                b = await CredentialRepository(session, user_id="bob-id").create(
                    provider="gemini", name="bob-key", api_key="bob-secret"
                )
                await CredentialRepository(session, user_id="bob-id").activate(b.id, "gemini")

        async with factory() as session:
            alice_active = await CredentialRepository(session, user_id="alice-id").get_active("gemini")
            bob_active = await CredentialRepository(session, user_id="bob-id").get_active("gemini")
        assert alice_active is not None and bob_active is not None
        assert alice_active.api_key == "alice-secret"
        assert bob_active.api_key == "bob-secret"


class TestMediaTokenMatrix:
    def test_token_bound_to_uid_and_project(self, monkeypatch):
        monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-for-media-token-32b!")
        monkeypatch.setenv("AUTH_USERNAME", "admin")
        monkeypatch.setenv("AUTH_PASSWORD", "x")
        token = create_media_token("alice-id", project_name="alice-proj")
        claims = verify_media_token(token, project_name="alice-proj", user_id="alice-id")
        assert claims["uid"] == "alice-id"

        with pytest.raises(ValueError):
            verify_media_token(token, project_name="alice-proj", user_id="bob-id")
        with pytest.raises(ValueError):
            verify_media_token(token, project_name="bob-proj", user_id="alice-id")

    def test_token_can_be_scoped_to_one_project_file(self, monkeypatch):
        monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-for-media-token-32b!")
        token = create_media_token(
            "alice-id",
            project_name="alice-proj",
            asset_path="storyboards/first.png",
        )
        claims = verify_media_token(
            token,
            project_name="alice-proj",
            asset_path="storyboards/first.png",
            user_id="alice-id",
        )
        assert claims["asset_path"] == "storyboards/first.png"

        with pytest.raises(ValueError):
            verify_media_token(
                token,
                project_name="alice-proj",
                asset_path="storyboards/other.png",
                user_id="alice-id",
            )

    def test_files_route_denies_cross_user(self, tmp_path, monkeypatch, project_ownership_db):
        from server.routers import files as files_router

        factory = project_ownership_db
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_seed_project(factory, "alice-proj", "alice-id"))

        async def _pid():
            async with factory() as session:
                row = await ProjectRepository(session).get_by_name("alice-id", "alice-proj")
                assert row is not None
                return row.id

        project_id = loop.run_until_complete(_pid())
        pm = ProjectManager(tmp_path)
        root = pm.create_project("alice-proj", user_id="alice-id", project_id=project_id)
        (Path(root) / "storyboards").mkdir(parents=True, exist_ok=True)
        (Path(root) / "storyboards" / "x.png").write_bytes(b"png")

        monkeypatch.setattr(files_router, "get_project_manager", lambda: pm)

        async def _bob_payload(_token: str, *_args):
            return {"sub": "bob", "uid": "bob-id", "role": "user", "via": "jwt"}

        monkeypatch.setattr(files_router, "_verify_and_get_payload_async", _bob_payload)

        app = FastAPI()
        app.include_router(files_router.router, prefix="/api/v1")
        register_error_handlers(app)

        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/files/alice-proj/storyboards/x.png",
                headers={"Authorization": "Bearer bob-token"},
            )
            assert resp.status_code == 404

    def test_files_route_allows_only_media_token_scoped_file(self, tmp_path, monkeypatch, project_ownership_db):
        from server.routers import files as files_router

        factory = project_ownership_db
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_seed_project(factory, "alice-proj", "alice-id"))

        async def _pid():
            async with factory() as session:
                row = await ProjectRepository(session).get_by_name("alice-id", "alice-proj")
                assert row is not None
                return row.id

        project_id = loop.run_until_complete(_pid())
        pm = ProjectManager(tmp_path)
        root = pm.create_project("alice-proj", user_id="alice-id", project_id=project_id)
        storyboards = Path(root) / "storyboards"
        storyboards.mkdir(parents=True, exist_ok=True)
        (storyboards / "first.png").write_bytes(b"first")
        (storyboards / "other.png").write_bytes(b"other")
        monkeypatch.setattr(files_router, "get_project_manager", lambda: pm)
        monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-for-media-token-32b!")

        token = create_media_token(
            "alice-id",
            project_name="alice-proj",
            asset_path="storyboards/first.png",
        )
        app = FastAPI()
        app.include_router(files_router.router, prefix="/api/v1")
        register_error_handlers(app)

        with TestClient(app) as client:
            first = client.get("/api/v1/files/alice-proj/storyboards/first.png", params={"media_token": token})
            other = client.get("/api/v1/files/alice-proj/storyboards/other.png", params={"media_token": token})

        assert first.status_code == 200
        assert first.content == b"first"
        assert first.headers["cache-control"] == "public, max-age=240"
        assert other.status_code == 401


class TestAssetsRouterMatrix:
    def test_bob_cannot_list_or_mutate_alice_assets(self, tmp_path, monkeypatch, project_ownership_db):
        from server.routers import assets as assets_router

        factory = project_ownership_db
        monkeypatch.setattr(assets_router, "async_session_factory", factory)
        monkeypatch.setattr(assets_router, "get_project_manager", lambda: ProjectManager(tmp_path))

        loop = asyncio.new_event_loop()

        async def _seed_asset():
            async with factory() as session:
                async with session.begin():
                    return await AssetRepository(session, user_id="alice-id").create(
                        type="character", name="hero", description="alice-only"
                    )

        asset = loop.run_until_complete(_seed_asset())

        app = FastAPI()
        app.include_router(assets_router.router, prefix="/api/v1")
        register_error_handlers(app)

        app.dependency_overrides[get_current_user] = lambda: BOB
        with TestClient(app) as client:
            listed = client.get("/api/v1/assets?type=character")
            assert listed.status_code == 200
            items = listed.json()["items"]
            assert items == []

            deleted = client.delete(f"/api/v1/assets/{asset.id}")
            assert deleted.status_code == 404

        app.dependency_overrides[get_current_user] = lambda: ALICE
        with TestClient(app) as client:
            listed = client.get("/api/v1/assets?type=character")
            assert listed.status_code == 200
            items = listed.json()["items"]
            assert any(i.get("name") == "hero" for i in items)


class TestUnauthenticatedDenied:
    def test_providers_require_auth(self):
        from server.routers import providers as providers_router

        app = FastAPI()
        app.include_router(providers_router.router, prefix="/api/v1")
        register_error_handlers(app)
        with TestClient(app) as client:
            resp = client.get("/api/v1/providers")
            assert resp.status_code in (401, 403)

    def test_files_require_auth(self, tmp_path, monkeypatch):
        from server.routers import files as files_router

        monkeypatch.setattr(files_router, "get_project_manager", lambda: ProjectManager(tmp_path))
        app = FastAPI()
        app.include_router(files_router.router, prefix="/api/v1")
        register_error_handlers(app)
        with TestClient(app) as client:
            resp = client.get("/api/v1/files/any/storyboards/x.png")
            assert resp.status_code in (401, 403)


class TestAdminBusinessScope:
    async def test_admin_cannot_implicitly_access_alice_project(self, project_ownership_db):
        from server import project_access
        from tests.conftest import make_translator

        await _seed_project(project_ownership_db, "alice-proj", "alice-id")
        with pytest.raises(HTTPException) as exc_info:
            await project_access.ensure_project_access("alice-proj", ADMIN, make_translator())
        assert exc_info.value.status_code == 404
