"""用户命名空间存储与媒体 token 基础测试。

作者: wanghaobo
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lib.db.base import DEFAULT_USER_ID
from lib.db.repositories.project_repo import ProjectRepository
from lib.project_manager import ProjectManager
from lib.project_paths import project_user_scope, user_asset_relpath, user_project_root
from lib.storage_migration import run_storage_migration
from server.auth import (
    create_media_token,
    get_token_secret,
    verify_media_token,
)

pytestmark = pytest.mark.integration
from server.routers import files


@pytest.fixture
def pm(tmp_path, monkeypatch):
    from lib.app_data_dir import _reset_for_tests

    root = tmp_path / "arcreel-data"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ARCREEL_DATA_DIR", str(root))
    _reset_for_tests()
    return ProjectManager(root)


class TestProjectPaths:
    def test_user_project_root_and_get_project_path_new_layout(self, pm, tmp_path):
        user_id = "alice"
        project_id = str(uuid.uuid4())
        pm.create_project("demo", user_id=user_id, project_id=project_id)
        resolved = pm.get_project_path("demo", user_id=user_id, project_id=project_id)
        assert resolved == user_project_root(pm.projects_root, user_id, project_id)

    def test_get_project_path_legacy_fallback(self, pm):
        pm.create_project("legacy")
        assert pm.get_project_path("legacy").name == "legacy"

    def test_get_user_assets_root(self, pm):
        root = pm.get_user_assets_root("bob")
        assert root == pm.projects_root / "users" / "bob" / "assets"
        assert (root / "character").is_dir()

    @pytest.mark.integration
    def test_create_metadata_in_namespaced_project(self, pm):
        """新建用户项目时，元数据必须直接写入已创建的 namespaced 目录。"""
        user_id = "alice"
        project_id = str(uuid.uuid4())
        project_root = pm.create_project("demo", user_id=user_id, project_id=project_id)

        created = pm.create_project_metadata(
            "demo",
            "Demo",
            "Anime",
            "narration",
            user_id=user_id,
            project_id=project_id,
        )

        assert created["title"] == "Demo"
        assert (project_root / "project.json").is_file()

    @pytest.mark.integration
    def test_bound_project_id_resolves_without_sqlite_lookup(self, pm, monkeypatch):
        """请求守卫已绑定 project_id 时，不依赖 SQLite，可兼容 PostgreSQL。"""
        project_id = str(uuid.uuid4())
        expected = pm.create_project("demo", user_id="alice", project_id=project_id)

        def _unexpected_lookup(*_args, **_kwargs):
            raise AssertionError("request-scoped path must not query SQLite")

        monkeypatch.setattr("lib.project_manager.sync_lookup_project", _unexpected_lookup)
        with project_user_scope("alice", project_name="demo", project_id=project_id):
            assert pm.get_project_path("demo") == expected


class TestMediaToken:
    def test_create_and_verify_project_scope(self):
        token = create_media_token(DEFAULT_USER_ID, project_name="demo")
        payload = verify_media_token(token, project_name="demo", user_id=DEFAULT_USER_ID)
        assert payload["purpose"] == "media"
        assert payload["uid"] == DEFAULT_USER_ID

    def test_expired_token_rejected(self):
        token = create_media_token(DEFAULT_USER_ID, project_name="demo", expires=1)
        time.sleep(1.1)
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_media_token(token, project_name="demo")

    def test_cross_user_project_rejected(self):
        token = create_media_token("alice", project_name="secret")
        with pytest.raises(ValueError):
            verify_media_token(token, project_name="secret", user_id="bob")

    def test_long_jwt_not_used_as_media_token(self):
        now = time.time()
        long_jwt = jwt.encode(
            {"sub": "admin", "uid": DEFAULT_USER_ID, "iat": now, "exp": now + 7 * 86400},
            get_token_secret(),
            algorithm="HS256",
        )
        with pytest.raises(ValueError):
            verify_media_token(long_jwt, project_name="demo")

    def test_asset_path_scope(self):
        rel = user_asset_relpath("alice", "character", "x.png")
        token = create_media_token("alice", asset_path=rel)
        verify_media_token(token, user_id="alice", asset_path=rel)
        with pytest.raises(ValueError):
            verify_media_token(token, user_id="alice", asset_path=rel.replace("x.png", "y.png"))


class TestStorageMigration:
    async def test_migrate_flat_project_to_user_namespace(self, pm, project_ownership_db):
        pm.create_project("flat-demo")
        async with project_ownership_db() as session:
            async with session.begin():
                row = await ProjectRepository(session).create("flat-demo", DEFAULT_USER_ID)

        summary = run_storage_migration(pm.projects_root)
        assert "flat-demo" in summary.projects_migrated or "flat-demo" in summary.projects_skipped
        new_dir = user_project_root(pm.projects_root, DEFAULT_USER_ID, row.id)
        assert new_dir.is_dir()
        assert (new_dir / "project.json").is_file()


class TestFilesRouterMediaToken:
    @pytest.mark.integration
    def test_legacy_global_asset_is_not_shared_with_other_users(self, pm, monkeypatch):
        legacy = pm.projects_root / "_global_assets" / "character"
        legacy.mkdir(parents=True)
        (legacy / "secret.png").write_bytes(b"legacy-secret")

        monkeypatch.setattr(files, "get_project_manager", lambda: pm)
        app = FastAPI()
        app.include_router(files.router, prefix="/api/v1")
        client = TestClient(app)

        alice_path = user_asset_relpath("alice", "character", "secret.png")
        token = create_media_token("alice", asset_path=alice_path)
        resp = client.get(f"/api/v1/global-assets/character/secret.png?media_token={token}")

        assert resp.status_code == 404

    def test_serve_with_media_token_without_bearer(self, tmp_path, monkeypatch, project_ownership_db, pm):
        user_id = "alice-id"
        project_id = str(uuid.uuid4())
        pm.create_project("demo", user_id=user_id, project_id=project_id)
        (pm.get_project_path("demo", user_id=user_id, project_id=project_id) / "source").mkdir(exist_ok=True)
        (pm.get_project_path("demo", user_id=user_id, project_id=project_id) / "source" / "a.txt").write_text(
            "hi", encoding="utf-8"
        )

        async def _seed():
            async with project_ownership_db() as session:
                async with session.begin():
                    await ProjectRepository(session).create("demo", user_id, project_id=project_id)

        import asyncio

        asyncio.run(_seed())

        monkeypatch.setattr(files, "get_project_manager", lambda: pm)
        monkeypatch.setattr(
            "lib.project_manager.sync_lookup_project",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not use SQLite path lookup")),
        )

        app = FastAPI()
        app.include_router(files.router, prefix="/api/v1")
        client = TestClient(app)

        token = create_media_token(user_id, project_name="demo")
        resp = client.get(f"/api/v1/files/demo/source/a.txt?media_token={token}")
        assert resp.status_code == 200
        assert resp.text == "hi"

    def test_cross_user_media_token_denied(self, tmp_path, monkeypatch, project_ownership_db, pm):
        pm.create_project("secret")
        (pm.get_project_path("secret") / "source").mkdir(exist_ok=True)
        (pm.get_project_path("secret") / "source" / "a.txt").write_text("no", encoding="utf-8")

        async def _seed():
            async with project_ownership_db() as session:
                async with session.begin():
                    await ProjectRepository(session).create("secret", "owner-id")

        import asyncio

        asyncio.run(_seed())

        monkeypatch.setattr(files, "get_project_manager", lambda: pm)
        app = FastAPI()
        app.include_router(files.router, prefix="/api/v1")
        client = TestClient(app)

        token = create_media_token("attacker-id", project_name="secret")
        resp = client.get(f"/api/v1/files/secret/source/a.txt?media_token={token}")
        assert resp.status_code == 404
