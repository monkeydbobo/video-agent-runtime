"""项目用户维度隔离测试。

覆盖：归属 Repository、归属守卫（admin 全通 / 属主放行 / 他人 404 /
存量 default 归属对全体用户共享）、列表过滤、启动对账、创建/删除时的登记与清理、
任务视图 scope 解析、导入覆盖归属校验。
"""

from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from lib.db.base import DEFAULT_USER_ID
from lib.db.repositories.project_repo import ProjectRepository
from server import project_access
from server.auth import CurrentUserInfo, get_current_user
from server.error_handlers import register_error_handlers
from server.routers import projects
from tests.conftest import make_translator

ADMIN = CurrentUserInfo(id=DEFAULT_USER_ID, sub="admin", role="admin")
ALICE = CurrentUserInfo(id="alice-id", sub="alice", role="user")
BOB = CurrentUserInfo(id="bob-id", sub="bob", role="user")

_t = make_translator()


async def _seed(factory, name: str, user_id: str) -> None:
    async with factory() as session:
        async with session.begin():
            await ProjectRepository(session).create(name, user_id)


async def _owner_in_db(factory, name: str) -> str | None:
    async with factory() as session:
        return await ProjectRepository(session).get_owner(name)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class TestProjectRepository:
    async def test_create_get_delete(self, project_ownership_db):
        factory = project_ownership_db
        await _seed(factory, "p1", "alice-id")
        assert await _owner_in_db(factory, "p1") == "alice-id"
        assert await _owner_in_db(factory, "missing") is None

        async with factory() as session:
            async with session.begin():
                repo = ProjectRepository(session)
                # ensure 不改已有归属
                row = await repo.ensure("p1", "bob-id")
                assert row.user_id == "alice-id"
                # ensure 创建缺失记录
                row2 = await repo.ensure("p2", "bob-id")
                assert row2.user_id == "bob-id"

        async with factory() as session:
            repo = ProjectRepository(session)
            assert sorted(await repo.list_names()) == ["p1", "p2"]
            assert await repo.list_names("alice-id") == ["p1"]
            assert await repo.ownership_map() == {"p1": "alice-id", "p2": "bob-id"}

        async with factory() as session:
            async with session.begin():
                await ProjectRepository(session).delete("p1")
        assert await _owner_in_db(factory, "p1") is None


# ---------------------------------------------------------------------------
# 守卫核心逻辑
# ---------------------------------------------------------------------------


class TestEnsureProjectAccess:
    async def test_admin_bypasses(self, project_ownership_db):
        await _seed(project_ownership_db, "alice-proj", "alice-id")
        await project_access.ensure_project_access("alice-proj", ADMIN, _t)

    async def test_owner_allowed(self, project_ownership_db):
        await _seed(project_ownership_db, "alice-proj", "alice-id")
        await project_access.ensure_project_access("alice-proj", ALICE, _t)

    async def test_other_user_gets_404(self, project_ownership_db):
        await _seed(project_ownership_db, "alice-proj", "alice-id")
        with pytest.raises(HTTPException) as exc_info:
            await project_access.ensure_project_access("alice-proj", BOB, _t)
        assert exc_info.value.status_code == 404

    async def test_legacy_and_default_projects_not_shared(self, project_ownership_db):
        """无归属记录 / default 归属不再对全体用户共享；仅属主或 admin 可访问。"""
        default_user = CurrentUserInfo(id=DEFAULT_USER_ID, sub="local", role="user")
        with pytest.raises(HTTPException) as exc_info:
            await project_access.ensure_project_access("legacy-proj", default_user, _t)
        assert exc_info.value.status_code == 404
        with pytest.raises(HTTPException):
            await project_access.ensure_project_access("legacy-proj", ALICE, _t)

        await _seed(project_ownership_db, "admin-owned", DEFAULT_USER_ID)
        await project_access.ensure_project_access("admin-owned", default_user, _t)
        with pytest.raises(HTTPException):
            await project_access.ensure_project_access("admin-owned", ALICE, _t)
        # admin 仍可运维
        await project_access.ensure_project_access("admin-owned", ADMIN, _t)

    async def test_accessible_project_names(self, project_ownership_db):
        await _seed(project_ownership_db, "alice-proj", "alice-id")
        await _seed(project_ownership_db, "bob-proj", "bob-id")
        await _seed(project_ownership_db, "admin-proj", DEFAULT_USER_ID)
        names = ["alice-proj", "bob-proj", "admin-proj", "unknown"]
        assert await project_access.accessible_project_names(names, ADMIN) == names
        assert await project_access.accessible_project_names(names, ALICE) == ["alice-proj"]
        default_user = CurrentUserInfo(id=DEFAULT_USER_ID, sub="local", role="user")
        assert await project_access.accessible_project_names(names, default_user) == ["admin-proj"]

    async def test_reconcile_registers_missing_and_is_idempotent(self, project_ownership_db):
        await _seed(project_ownership_db, "known", "alice-id")
        registered = await project_access.reconcile_project_ownership(["known", "orphan-a", "orphan-b"])
        assert registered == 2
        assert await _owner_in_db(project_ownership_db, "orphan-a") == DEFAULT_USER_ID
        # 已有归属不被改写
        assert await _owner_in_db(project_ownership_db, "known") == "alice-id"
        assert await project_access.reconcile_project_ownership(["known", "orphan-a", "orphan-b"]) == 0


# ---------------------------------------------------------------------------
# 路由集成：列表过滤 + 创建登记 + 删除清理 + 详情 404
# ---------------------------------------------------------------------------


class _IsolationPM:
    """最小 ProjectManager stub：扁平目录 + project.json 内存字典。"""

    def __init__(self, base: Path):
        self.base = base
        self.data: dict[str, dict] = {}

    def _add(self, name: str):
        self.data[name] = {"title": name, "style": "", "episodes": []}

    def list_projects(self):
        return list(self.data)

    def project_exists(self, name):
        return name in self.data

    def load_project(self, name):
        if name not in self.data:
            raise FileNotFoundError(name)
        return self.data[name]

    def load_script(self, name, script_file):
        raise FileNotFoundError(script_file)

    def get_project_path(self, name):
        path = self.base / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def generate_project_name(self, title):
        return f"gen-{title}"

    def create_project(self, name, content_mode="narration", **kwargs):
        if name in self.data:
            raise FileExistsError(name)
        self._add(name)
        return self.base / name

    def create_project_metadata(self, name, title, style, content_mode, **kwargs):
        self.data[name] = {"title": title, "style": style, "episodes": []}
        return self.data[name]

    def delete_project_directory(self, name, *, user_id=None):
        if name not in self.data:
            raise FileNotFoundError(name)
        del self.data[name]


class _NoopCalc:
    def calculate_project_status(self, name, project, preloaded_scripts=None):
        return {}

    def enrich_project(self, name, project):
        return dict(project)


def _make_client(monkeypatch, fake_pm, user_holder: dict):
    monkeypatch.setattr(projects, "get_project_manager", lambda: fake_pm)
    monkeypatch.setattr(projects, "get_status_calculator", lambda: _NoopCalc())
    monkeypatch.setattr("server.services.project_cover.resolve_project_cover", lambda *a, **k: None)
    monkeypatch.setattr(projects, "resolve_project_cover", lambda *a, **k: None)

    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: user_holder["user"]
    app.include_router(projects.router, prefix="/api/v1")
    register_error_handlers(app)
    return TestClient(app)


class TestProjectsRouterIsolation:
    def test_end_to_end_isolation(self, tmp_path, monkeypatch, project_ownership_db):
        fake_pm = _IsolationPM(tmp_path)
        user_holder = {"user": ALICE}
        client = _make_client(monkeypatch, fake_pm, user_holder)

        with client:
            # alice 创建项目 → 登记归属
            resp = client.post("/api/v1/projects", json={"name": "alice-proj", "content_mode": "narration"})
            assert resp.status_code == 200

            # alice 列表可见自己的项目
            names = [p["name"] for p in client.get("/api/v1/projects").json()["projects"]]
            assert names == ["alice-proj"]

            # alice 可读详情
            assert client.get("/api/v1/projects/alice-proj").status_code == 200

            # bob 列表为空、详情/修改/删除均 404
            user_holder["user"] = BOB
            assert client.get("/api/v1/projects").json()["projects"] == []
            assert client.get("/api/v1/projects/alice-proj").status_code == 404
            assert client.patch("/api/v1/projects/alice-proj", json={"title": "hack"}).status_code == 404
            assert client.delete("/api/v1/projects/alice-proj").status_code == 404
            # 磁盘数据未被动过
            assert fake_pm.project_exists("alice-proj")

            # admin 可见全部并可删除；删除后归属清理
            user_holder["user"] = ADMIN
            names = [p["name"] for p in client.get("/api/v1/projects").json()["projects"]]
            assert names == ["alice-proj"]
            assert client.delete("/api/v1/projects/alice-proj").status_code == 200

    def test_create_registers_owner(self, tmp_path, monkeypatch, project_ownership_db):
        fake_pm = _IsolationPM(tmp_path)
        client = _make_client(monkeypatch, fake_pm, {"user": ALICE})
        with client:
            resp = client.post("/api/v1/projects", json={"name": "mine", "content_mode": "narration"})
            assert resp.status_code == 200

        import asyncio

        owner = asyncio.new_event_loop().run_until_complete(_owner_in_db(project_ownership_db, "mine"))
        assert owner == "alice-id"

    def test_export_token_denied_for_non_owner(self, tmp_path, monkeypatch, project_ownership_db):
        fake_pm = _IsolationPM(tmp_path)
        fake_pm._add("alice-proj")
        user_holder = {"user": ALICE}
        client = _make_client(monkeypatch, fake_pm, user_holder)
        with client:
            # 先由 alice 建立归属
            client.post("/api/v1/projects", json={"name": "seed", "content_mode": "narration"})
            import asyncio

            loop = asyncio.new_event_loop()
            loop.run_until_complete(_seed(project_ownership_db, "alice-proj", "alice-id"))

            user_holder["user"] = BOB
            resp = client.post("/api/v1/projects/alice-proj/export/token")
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 任务视图 scope 解析
# ---------------------------------------------------------------------------


class TestTaskScope:
    async def test_admin_unscoped(self, project_ownership_db):
        from server.routers.tasks import _resolve_task_scope

        assert await _resolve_task_scope(ADMIN, None, _t) == (None, None, None)

    async def test_project_name_guarded(self, project_ownership_db):
        from server.routers.tasks import _resolve_task_scope

        await _seed(project_ownership_db, "alice-proj", "alice-id")
        assert await _resolve_task_scope(ALICE, "alice-proj", _t) == ("alice-proj", None, "alice-id")
        with pytest.raises(HTTPException):
            await _resolve_task_scope(BOB, "alice-proj", _t)

    async def test_non_admin_scoped_to_owned(self, monkeypatch, project_ownership_db):
        import server.routers.tasks as tasks_module

        class _PM:
            def list_projects(self):
                return ["alice-proj", "bob-proj"]

        monkeypatch.setattr(tasks_module, "get_project_manager", lambda: _PM())
        await _seed(project_ownership_db, "alice-proj", "alice-id")
        await _seed(project_ownership_db, "bob-proj", "bob-id")

        name, names, user_id = await tasks_module._resolve_task_scope(ALICE, None, _t)
        assert name is None
        assert names == ["alice-proj"]
        assert user_id == "alice-id"


# ---------------------------------------------------------------------------
# 归档导入覆盖归属校验
# ---------------------------------------------------------------------------


class TestArchiveOverwriteGuard:
    def _service(self, tmp_path):
        from lib.project_manager import ProjectManager
        from server.services.project_archive import ProjectArchiveService

        pm = ProjectManager(tmp_path)
        return ProjectArchiveService(pm)

    def test_overwrite_denied_when_not_replaceable(self, tmp_path):
        from server.services.project_archive import ProjectArchiveValidationError

        svc = self._service(tmp_path)
        (tmp_path / "taken").mkdir()
        with pytest.raises(ProjectArchiveValidationError) as exc_info:
            svc._resolve_conflict(
                "taken",
                project_title="Taken",
                conflict_policy="overwrite",
                can_replace=lambda name: False,
            )
        assert exc_info.value.status_code == 409

    def test_overwrite_allowed_when_replaceable(self, tmp_path):
        svc = self._service(tmp_path)
        (tmp_path / "mine").mkdir()
        name, resolution = svc._resolve_conflict(
            "mine",
            project_title="Mine",
            conflict_policy="overwrite",
            can_replace=lambda name: True,
        )
        assert (name, resolution) == ("mine", "overwritten")

    def test_overwrite_without_guard_keeps_legacy_behavior(self, tmp_path):
        svc = self._service(tmp_path)
        (tmp_path / "old").mkdir()
        name, resolution = svc._resolve_conflict(
            "old",
            project_title="Old",
            conflict_policy="overwrite",
            can_replace=None,
        )
        assert (name, resolution) == ("old", "overwritten")


# ---------------------------------------------------------------------------
# Task / Usage / Session 跨用户隔离
# ---------------------------------------------------------------------------


class TestResourceClosure:
    async def _seed_task(self, factory, *, user_id: str, project_name: str) -> None:
        from lib.db.repositories.task_repo import TaskRepository

        async with factory() as session:
            await TaskRepository(session).enqueue(
                project_name=project_name,
                task_type="storyboard",
                media_type="image",
                resource_id="seg-1",
                user_id=user_id,
            )

    async def _seed_api_call(self, factory, *, user_id: str, project_name: str) -> None:
        from lib.db.repositories.usage_repo import UsageRepository

        async with factory() as session:
            await UsageRepository(session).start_call(
                project_name=project_name,
                call_type="text",
                model="test",
                provider="anthropic",
                user_id=user_id,
            )

    async def _seed_session(self, factory, *, user_id: str, project_name: str, session_id: str) -> None:
        from lib.db.repositories.session_repo import SessionRepository

        async with factory() as session:
            await SessionRepository(session).create(
                project_name=project_name,
                sdk_session_id=session_id,
                user_id=user_id,
            )

    async def test_bob_cannot_list_alice_tasks(self, project_ownership_db, monkeypatch):
        factory = project_ownership_db
        await _seed(factory, "alice-proj", "alice-id")
        await self._seed_task(factory, user_id="alice-id", project_name="alice-proj")

        from server.routers import tasks as tasks_module

        class _PM:
            def list_projects(self):
                return ["alice-proj"]

        monkeypatch.setattr(tasks_module, "get_project_manager", lambda: _PM())

        import lib.generation_queue as gq

        queue = gq.GenerationQueue(session_factory=factory)
        monkeypatch.setattr(gq, "_QUEUE_INSTANCE", queue)
        monkeypatch.setattr(tasks_module, "get_task_queue", lambda: queue)

        name, names, user_id = await tasks_module._resolve_task_scope(BOB, None, _t)
        assert name is None
        assert names == []
        assert user_id == "bob-id"

        queue = tasks_module.get_task_queue()
        result = await queue.list_tasks(user_id="bob-id", project_names=[])
        assert result["total"] == 0

    async def test_bob_cannot_access_alice_task_by_id(self, project_ownership_db, monkeypatch):
        factory = project_ownership_db
        await _seed(factory, "alice-proj", "alice-id")
        await self._seed_task(factory, user_id="alice-id", project_name="alice-proj")

        import lib.generation_queue as generation_queue_module
        from server.routers import tasks as tasks_module

        queue = generation_queue_module.GenerationQueue(session_factory=factory)
        monkeypatch.setattr(generation_queue_module, "_QUEUE_INSTANCE", queue)
        monkeypatch.setattr(tasks_module, "get_task_queue", lambda: queue)

        from lib.db.repositories.task_repo import TaskRepository

        async with factory() as session:
            row = await TaskRepository(session).list_tasks(user_id="alice-id")
        task_id = row["items"][0]["task_id"]

        from lib.api_errors import NotFoundError

        with pytest.raises(NotFoundError):
            await tasks_module._ensure_task_access(task_id, BOB, _t)

    async def test_bob_cannot_list_alice_usage(self, project_ownership_db, monkeypatch):
        factory = project_ownership_db
        await _seed(factory, "alice-proj", "alice-id")
        await self._seed_api_call(factory, user_id="alice-id", project_name="alice-proj")

        from lib.db import async_session_factory
        from lib.db.repositories.usage_repo import UsageRepository
        from server.routers import usage as usage_module

        class _PM:
            def list_projects(self):
                return ["alice-proj"]

        monkeypatch.setattr(usage_module, "get_project_manager", lambda: _PM())

        _, _, user_id = await usage_module._resolve_usage_scope(BOB, None, _t)
        assert user_id == "bob-id"

        async with async_session_factory() as session:
            stats = await UsageRepository(session).get_stats(user_id="bob-id", project_names=[])
        assert stats["total_count"] == 0

    async def test_bob_cannot_get_alice_session(self, project_ownership_db):
        factory = project_ownership_db
        await _seed(factory, "alice-proj", "alice-id")
        await self._seed_session(factory, user_id="alice-id", project_name="alice-proj", session_id="sess-alice")

        from lib.db.repositories.session_repo import SessionRepository

        async with factory() as session:
            row = await SessionRepository(session).get("sess-alice", user_id="bob-id")
        assert row is None

    def test_generate_denied_for_non_owner_project(self, tmp_path, monkeypatch, project_ownership_db):
        import asyncio

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from lib.project_manager import ProjectManager
        from server.auth import get_current_user
        from server.error_handlers import register_error_handlers
        from server.routers import generate as generate_router

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_seed(project_ownership_db, "alice-proj", "alice-id"))

        pm = ProjectManager(tmp_path)
        pm.create_project("alice-proj")

        monkeypatch.setattr(generate_router, "get_project_manager", lambda: pm)

        app = FastAPI()
        app.dependency_overrides[get_current_user] = lambda: BOB
        app.include_router(generate_router.router, prefix="/api/v1")
        register_error_handlers(app)

        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/projects/alice-proj/generate/character/hero",
                json={"prompt": "test"},
            )
            assert resp.status_code == 404
