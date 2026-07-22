from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from server.agent_runtime.managed_session_manager import ManagedAgentsSessionManager
from server.agent_runtime.session_store import SessionMetaStore


def _manager(tmp_path: Path) -> ManagedAgentsSessionManager:
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    return ManagedAgentsSessionManager(
        project_root=tmp_path,
        data_dir=tmp_path / ".agent_data",
        meta_store=SessionMetaStore(),
        projects_root=projects_root,
    )


def test_project_archive_contains_only_safe_context_files(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    project = manager.projects_root / "demo"
    project.mkdir()
    (project / "project.json").write_text('{"name":"demo"}', encoding="utf-8")
    (project / ".env").write_text("SECRET=leak", encoding="utf-8")
    (project / "script.py").write_text("print('unsafe')", encoding="utf-8")
    profile = project / ".claude" / "skills" / "demo"
    profile.mkdir(parents=True)
    (profile / "tool.py").write_text("print('trusted profile')", encoding="utf-8")

    archive = manager._project_archive("demo")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        names = set(bundle.getnames())

    assert "project.json" in names
    assert ".claude/skills/demo/tool.py" in names
    assert ".env" not in names
    assert "script.py" not in names


def test_sync_project_files_validates_json_and_blocks_path_escape(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    project = manager.projects_root / "demo"
    project.mkdir()

    result = manager._sync_project_files("demo", [{"path": "episode.json", "content": '{"ok":true}'}])
    assert result == {"updated": ["episode.json"]}
    assert json.loads((project / "episode.json").read_text(encoding="utf-8")) == {"ok": True}

    with pytest.raises(ValueError, match="相对路径"):
        manager._sync_project_files("demo", [{"path": "../escape.json", "content": "{}"}])
    with pytest.raises(json.JSONDecodeError):
        manager._sync_project_files("demo", [{"path": "bad.json", "content": "not-json"}])


def test_requires_action_idle_does_not_finish_session() -> None:
    message, status = ManagedAgentsSessionManager._map_event(
        {"type": "session.status_idle", "stop_reason": {"type": "requires_action", "event_ids": ["evt"]}}
    )
    assert message is None
    assert status is None

    message, status = ManagedAgentsSessionManager._map_event(
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}}
    )
    assert message == {"type": "result", "subtype": "success", "stop_reason": "end_turn"}
    assert status == "completed"
