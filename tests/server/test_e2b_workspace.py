from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import server.agent_runtime.e2b_workspace as e2b_module
from server.agent_runtime.e2b_workspace import REMOTE_PROJECT_ROOT, E2BWorkspaceManager
from server.agent_runtime.session_manager import SessionManager
from server.agent_runtime.session_store import SessionMetaStore


class FakeFiles:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def make_dir(self, _path: str) -> bool:
        return True

    async def write(self, path: str, data, **_kwargs):  # noqa: ANN001
        self.values[path] = data.encode() if isinstance(data, str) else bytes(data)
        return SimpleNamespace(path=path)

    async def read(self, path: str, format: str = "text", **_kwargs):
        value = self.values[path]
        return value if format == "bytes" else value.decode("utf-8")

    async def list(self, path: str, depth: int = 1, **_kwargs):
        del depth
        return [
            SimpleNamespace(path=name, type=SimpleNamespace(value="file"))
            for name in self.values
            if name.startswith(path.rstrip("/") + "/")
        ]


class FakeCommands:
    async def run(self, _command: str, **_kwargs):
        return SimpleNamespace(stdout="ok", stderr="", exit_code=0)


class FakeSandbox:
    def __init__(self, sandbox_id: str = "sbx_test") -> None:
        self.sandbox_id = sandbox_id
        self.files = FakeFiles()
        self.commands = FakeCommands()
        self.paused = False
        self.killed = False

    async def is_running(self) -> bool:
        return not self.paused and not self.killed

    async def connect(self, **_kwargs):
        self.paused = False
        return self

    async def pause(self) -> bool:
        self.paused = True
        return True

    async def kill(self) -> bool:
        self.killed = True
        return True


def _project(tmp_path: Path) -> tuple[Path, Path]:
    projects = tmp_path / "projects"
    project = projects / "demo"
    project.mkdir(parents=True)
    (project / "project.json").write_text('{"name":"demo"}', encoding="utf-8")
    return projects, project


@pytest.mark.asyncio
async def test_prepare_creates_network_disabled_sandbox_and_uploads_safe_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, project = _project(tmp_path)
    (project / ".env").write_text("SECRET=leak", encoding="utf-8")
    (project / "unsafe.py").write_text("print('no')", encoding="utf-8")
    profile = project / ".claude" / "skills" / "demo"
    profile.mkdir(parents=True)
    (profile / "tool.py").write_text("print('safe profile')", encoding="utf-8")
    sandbox = FakeSandbox()
    captured: dict = {}

    class FakeAPI:
        @classmethod
        async def create(cls, template, **kwargs):  # noqa: ANN001
            captured.update({"template": template, **kwargs})
            return sandbox

    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setattr(e2b_module, "AsyncSandbox", FakeAPI)
    manager = E2BWorkspaceManager(projects_root=projects)

    result = await manager.prepare("temporary", "demo")

    assert result is sandbox
    assert captured["secure"] is True
    assert captured["allow_internet_access"] is False
    assert captured["lifecycle"] == {"on_timeout": "pause", "auto_resume": True}
    assert f"{REMOTE_PROJECT_ROOT}/project.json" in sandbox.files.values
    assert f"{REMOTE_PROJECT_ROOT}/.claude/skills/demo/tool.py" in sandbox.files.values
    assert f"{REMOTE_PROJECT_ROOT}/.env" not in sandbox.files.values
    assert f"{REMOTE_PROJECT_ROOT}/unsafe.py" not in sandbox.files.values


@pytest.mark.asyncio
async def test_sync_rejects_invalid_json_without_corrupting_project(tmp_path: Path) -> None:
    projects, project = _project(tmp_path)
    manager = E2BWorkspaceManager(projects_root=projects)
    sandbox = FakeSandbox()
    remote = f"{REMOTE_PROJECT_ROOT}/project.json"
    sandbox.files.values[remote] = b"not-json"

    with pytest.raises(ValueError):
        await manager.sync_all(sandbox, "demo")

    assert (project / "project.json").read_text(encoding="utf-8") == '{"name":"demo"}'


@pytest.mark.asyncio
async def test_bind_session_keeps_mcp_closure_alias(tmp_path: Path) -> None:
    projects, _project_dir = _project(tmp_path)
    manager = E2BWorkspaceManager(projects_root=projects)
    sandbox = FakeSandbox()
    manager._sandboxes["temporary"] = sandbox
    manager._sandbox_ids["temporary"] = sandbox.sandbox_id

    sandbox_id = await manager.bind_session("temporary", "sdk-session")

    assert sandbox_id == sandbox.sandbox_id
    assert manager._sandboxes["temporary"] is sandbox
    assert manager._sandboxes["sdk-session"] is sandbox


def test_remote_path_cannot_escape_workspace(tmp_path: Path) -> None:
    projects, _project_dir = _project(tmp_path)
    manager = E2BWorkspaceManager(projects_root=projects)
    with pytest.raises(ValueError, match="路径必须位于"):
        manager._remote_path("../../etc/passwd")


@pytest.mark.asyncio
async def test_e2b_options_keep_orchestration_and_reads_but_remove_local_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects, _project_dir = _project(tmp_path)
    monkeypatch.setenv("ARCREEL_AGENT_BACKEND", "e2b")
    manager = SessionManager(
        project_root=tmp_path,
        data_dir=tmp_path / ".agent_data",
        meta_store=SessionMetaStore(),
        projects_root=projects,
        sandbox_enabled=False,
    )
    assert manager._e2b_workspaces is not None
    manager._e2b_workspaces.prepare = AsyncMock(return_value=FakeSandbox())  # type: ignore[method-assign]
    manager._build_provider_env_overrides = AsyncMock(  # type: ignore[method-assign]
        return_value={"ANTHROPIC_API_KEY": "test", "ANTHROPIC_BASE_URL": "https://example.invalid"}
    )

    options = await manager._build_options("demo", runtime_session_key="temporary")

    assert "mcp__e2b__*" in options.allowed_tools
    for forbidden in ("Bash", "BashOutput", "KillBash", "Write", "Edit"):
        assert forbidden not in options.allowed_tools
    for allowed in ("Task", "Read", "Glob", "Grep"):
        assert allowed in options.allowed_tools
    assert options.sandbox == {"enabled": False}
    assert set(options.mcp_servers) == {"arcreel", "e2b"}

    callback = await manager._build_can_use_tool_callback("temporary")
    denied = await callback("Bash", {"command": "python .claude/skills/x.py"}, SimpleNamespace())
    assert "E2B 模式禁止本地工具" in denied.message

    denied_write = await callback("Write", {"file_path": "project.json", "content": "{}"}, SimpleNamespace())
    assert "E2B 模式禁止本地工具" in denied_write.message
