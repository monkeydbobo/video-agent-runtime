"""Per-session context shared by ArcReel SDK MCP tool handlers.

作者: wanghaobo
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.config.resolver import ConfigResolver
from lib.db import async_session_factory
from lib.project_manager import ProjectManager
from lib.project_paths import current_project_id_scope, sync_lookup_project


class ToolContext:
    """Bind a tool handler to one agent session's project + projects_root.

    The agent never names the project explicitly — every tool is closure-bound
    to ``project_name`` via ``build_arcreel_mcp_server(project_name=...)``.
    """

    def __init__(
        self,
        project_name: str,
        projects_root: Path,
        pm: ProjectManager | None = None,
        *,
        user_id: str | None = None,
        project_id: str | None = None,
    ):
        from lib.db.base import DEFAULT_USER_ID

        self.project_name = project_name
        self.projects_root = projects_root
        self.user_id = user_id or DEFAULT_USER_ID
        self.project_id = project_id or current_project_id_scope(project_name)
        # Avoid ``ProjectManager.from_cwd()`` — the server main process cwd is
        # the repo root, not ``projects/<name>/``. Tests may inject a fake pm.
        self.pm: ProjectManager = pm if pm is not None else ProjectManager(str(projects_root))

    @property
    def project_path(self) -> Path:
        self.ensure_project_owned()
        if self.project_id is not None:
            return self.pm.get_project_path(
                self.project_name,
                user_id=self.user_id,
                project_id=self.project_id,
            )
        loc = sync_lookup_project(self.project_name, user_id=self.user_id)
        if loc is not None:
            return self.pm.get_project_path(
                self.project_name,
                user_id=loc.user_id,
                project_id=loc.project_id,
            )
        return self.pm.get_project_path(self.project_name, user_id=self.user_id)

    def ensure_project_owned(self) -> None:
        """校验 closure 绑定的项目属于 ``user_id``；失败抛 PermissionError。"""
        if self.project_id is not None:
            return
        loc = sync_lookup_project(self.project_name, user_id=self.user_id)
        if loc is None or loc.user_id != self.user_id:
            raise PermissionError(f"项目 '{self.project_name}' 不属于当前用户")


def tool_error(name: str, exc: BaseException, log: list[str] | None = None) -> dict[str, Any]:
    """Build the ``{"is_error": True}`` response every SDK tool handler emits on failure."""
    msg = f"{name} 失败: {exc}"
    text = "\n".join([msg, *log]) if log else msg
    return {"content": [{"type": "text", "text": text}], "is_error": True}


async def fetch_video_caps(project: dict[str, Any], *, user_id: str) -> tuple[int | None, list[int]]:
    """Resolve ``(default_duration, supported_durations)`` for an MCP tool call.

    Single source of truth for video model capability lookup across SDK MCP
    tools (``enqueue_videos`` and ``text_generation`` both depend on this).
    Returns the raw resolved durations; callers decide whether an empty result
    is a hard error (video generation) or a soft fallback (script normalization).
    """
    resolver = ConfigResolver(async_session_factory, user_id=user_id)
    caps = await resolver.video_capabilities_for_project(project)
    durations = [int(d) for d in caps.get("supported_durations") or []]
    default = caps.get("default_duration")
    default_int = int(default) if isinstance(default, int | float) else None
    return default_int, durations


def validate_script_filename(value: str) -> str:
    """Reject any agent-provided ``script`` arg that is not a bare basename.

    Agents must reference scripts by filename only (e.g. ``episode_1.json``);
    the project root is bound by ``ToolContext`` and the ``scripts/`` subdir
    is fixed inside ``ProjectManager.load_script``. Any path separator —
    including a ``scripts/`` prefix or ``..`` segments — is rejected.
    """
    if not isinstance(value, str) or not value:
        raise ValueError("script 文件名不能为空")
    if "/" in value or "\\" in value or value in (".", ".."):
        raise ValueError(f"script 必须是纯文件名，禁止路径分隔符: {value!r}")
    return value
