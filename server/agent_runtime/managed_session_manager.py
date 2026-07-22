"""Anthropic Managed Agents session backend for restricted PaaS deployments.

Railway remains the control plane and runs ArcReel's project-bound custom tools.
Shell and workspace tools execute in Anthropic's isolated cloud environment.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
import tarfile
import time
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, cast

from anthropic import AsyncAnthropic, beta_async_tool

from lib.config.service import build_anthropic_env_dict
from lib.db import async_session_factory
from server.agent_runtime.models import SessionMeta, SessionStatus
from server.agent_runtime.sdk_tools import build_arcreel_tools
from server.agent_runtime.session_store import SessionMetaStore

logger = logging.getLogger(__name__)

_OFFICIAL_BASE_URLS = {"", "https://api.anthropic.com", "https://api.anthropic.com/"}
_PROJECT_TEXT_SUFFIXES = {".json", ".md", ".txt", ".csv", ".html"}
_PROFILE_SUFFIXES = _PROJECT_TEXT_SUFFIXES | {".py"}
_SYNC_SUFFIXES = _PROJECT_TEXT_SUFFIXES
_MAX_CONTEXT_FILE_BYTES = 2 * 1024 * 1024
_MAX_SYNC_FILE_BYTES = 2 * 1024 * 1024


@dataclass
class RemoteSession:
    session_id: str
    project_name: str
    status: SessionStatus = "running"
    assistant_model: str = ""
    message_buffer: list[dict[str, Any]] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    monitor_task: asyncio.Task | None = None
    tool_task: asyncio.Task | None = None
    last_activity: float = field(default_factory=time.monotonic)

    def add_message(self, message: dict[str, Any]) -> None:
        self.message_buffer.append(message)
        self.message_buffer = self.message_buffer[-100:]
        stale: list[asyncio.Queue] = []
        for queue in self.subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                stale.append(queue)
        for queue in stale:
            self.subscribers.discard(queue)
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait({"type": "_queue_overflow", "session_id": self.session_id})


class ManagedAgentsSessionManager:
    """SessionManager-compatible facade backed by Anthropic Managed Agents."""

    def __init__(
        self,
        *,
        project_root: Path,
        data_dir: Path,
        meta_store: SessionMetaStore,
        projects_root: Path,
    ) -> None:
        del data_dir
        self.project_root = Path(project_root)
        self.projects_root = Path(projects_root)
        self.meta_store = meta_store
        self.sessions: dict[str, RemoteSession] = {}
        self._client: AsyncAnthropic | None = None
        self._agent_id: str | None = None
        self._environment_id: str | None = None
        self._model = os.environ.get("ARCREEL_MANAGED_AGENT_MODEL", "claude-opus-4-6").strip()
        self._init_lock = asyncio.Lock()
        self.startup_error: str | None = None
        self._in_docker = False
        self._sandbox_enabled = True

    def _build_session_store(self) -> None:
        return None

    async def startup(self) -> None:
        try:
            await self._ensure_remote_resources()
            self.startup_error = None
        except Exception as exc:
            # Keep the core application deployable while credentials are being
            # switched in WebUI. Every Agent request retries initialization and
            # returns the same actionable error until official access is ready.
            self.startup_error = str(exc)
            logger.warning("Managed Agents 尚未就绪: %s", exc)

    async def _ensure_remote_resources(self) -> None:
        if self._client is not None and self._agent_id and self._environment_id:
            return
        async with self._init_lock:
            if self._client is not None and self._agent_id and self._environment_id:
                return
            async with async_session_factory() as db_session:
                env = await build_anthropic_env_dict(db_session)
            api_key = env.get("ANTHROPIC_API_KEY", "").strip()
            base_url = env.get("ANTHROPIC_BASE_URL", "").strip()
            if not api_key:
                raise RuntimeError("Managed Agents 需要 Anthropic 官方 API Key，请先在 Agent 配置中添加并启用。")
            if base_url not in _OFFICIAL_BASE_URLS:
                raise RuntimeError(
                    "Managed Agents 不支持当前第三方 Anthropic 兼容端点；"
                    "请在 Agent 配置中启用 Anthropic 官方 API Key（Base URL 留空）。"
                )
            client = AsyncAnthropic(api_key=api_key)
            agent_id = await self._find_or_create_agent(client)
            environment_id = await self._find_or_create_environment(client)
            self._client = client
            self._agent_id = agent_id
            self._environment_id = environment_id
            self.startup_error = None

    async def _find_or_create_agent(self, client: AsyncAnthropic) -> str:
        async for agent in client.beta.agents.list(limit=100):
            if getattr(agent, "metadata", {}).get("application") == "arcreel":
                return str(agent.id)
        agent = await client.beta.agents.create(
            name="ArcReel Agent",
            description="ArcReel 小说转短视频项目助手",
            model=self._model,
            metadata={"application": "arcreel"},
            system="你是 ArcReel 项目助手。严格遵守每个会话中提供的项目边界与回写规则。",
            tools=cast(Any, [self._builtin_toolset()]),
        )
        return str(agent.id)

    async def _find_or_create_environment(self, client: AsyncAnthropic) -> str:
        async for environment in client.beta.environments.list(limit=100):
            if getattr(environment, "metadata", {}).get("application") == "arcreel":
                return str(environment.id)
        environment = await client.beta.environments.create(
            name="ArcReel Cloud Sandbox",
            description="Isolated workspace for ArcReel Agent sessions",
            metadata={"application": "arcreel"},
            config={
                "type": "cloud",
                "networking": {
                    "type": "limited",
                    "allowed_hosts": [],
                    "allow_mcp_servers": False,
                    "allow_package_managers": False,
                },
            },
        )
        return str(environment.id)

    @staticmethod
    def _builtin_toolset() -> dict[str, Any]:
        return {
            "type": "agent_toolset_20260401",
            "default_config": {
                "enabled": True,
                "permission_policy": {"type": "always_allow"},
            },
            "configs": [
                {"name": "web_fetch", "enabled": False},
                {"name": "web_search", "enabled": False},
            ],
        }

    def _project_archive(self, project_name: str) -> bytes:
        project_dir = (self.projects_root / project_name).resolve()
        if project_dir.parent != self.projects_root.resolve() or not project_dir.is_dir():
            raise FileNotFoundError(f"project not found: {project_name}")
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for path in project_dir.rglob("*"):
                if not path.is_file() or path.is_symlink():
                    continue
                relative = path.relative_to(project_dir)
                is_profile = relative.parts and relative.parts[0] == ".claude"
                suffixes = _PROFILE_SUFFIXES if is_profile else _PROJECT_TEXT_SUFFIXES
                if path.suffix.lower() not in suffixes or path.stat().st_size > _MAX_CONTEXT_FILE_BYTES:
                    continue
                archive.add(path, arcname=relative.as_posix(), recursive=False)
        return output.getvalue()

    def _system_prompt(self, project_name: str, locale: str) -> str:
        language = {"zh": "中文", "en": "English", "vi": "Tiếng Việt"}.get(locale, "中文")
        return f"""你是 ArcReel 项目 `{project_name}` 的专属助手，默认使用{language}回复。

项目快照挂载在 `/workspace/project-context.tar.gz`。首次使用文件前执行：
`mkdir -p /workspace/project && tar -xzf /workspace/project-context.tar.gz -C /workspace/project`
之后只在 `/workspace/project` 内工作。快照是只读来源，沙盒内修改不会自动回到 Railway。

需要永久修改项目的 JSON/Markdown/TXT/CSV/HTML 文件时，必须调用 `sync_project_files`，
只提交确实需要修改的文件。严禁索取、查找或输出密钥，不要修改应用源码、数据库或配置凭证。
生成资产、分镜、剧本和视频时使用提供的 ArcReel 自定义工具；它们绑定到当前项目，不能访问其他项目。
"""

    @staticmethod
    def _tool_schema(tool: Any) -> dict[str, Any]:
        schema = getattr(tool, "input_schema", None)
        if isinstance(schema, dict):
            return schema
        return {"type": "object", "properties": {}}

    def _remote_tools(self, project_name: str) -> tuple[list[Any], list[dict[str, Any]]]:
        runners: list[Any] = []
        definitions: list[dict[str, Any]] = []

        for sdk_tool in build_arcreel_tools(project_name=project_name, projects_root=self.projects_root):
            name = str(sdk_tool.name)
            description = str(sdk_tool.description)
            schema = self._tool_schema(sdk_tool)

            async def run_sdk_tool(_tool: Any = sdk_tool, **kwargs: Any) -> Any:
                result = await _tool.handler(kwargs)
                if isinstance(result, dict) and result.get("is_error"):
                    raise RuntimeError(json.dumps(result.get("content"), ensure_ascii=False))
                return result

            runners.append(beta_async_tool(name=name, description=description, input_schema=schema)(run_sdk_tool))
            definitions.append({"type": "custom", "name": name, "description": description, "input_schema": schema})

        sync_schema = {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["path", "content"],
                        "additionalProperties": False,
                    },
                    "maxItems": 20,
                }
            },
            "required": ["files"],
            "additionalProperties": False,
        }

        async def sync_project_files(files: list[dict[str, str]]) -> str:
            result = await asyncio.to_thread(self._sync_project_files, project_name, files)
            return json.dumps(result, ensure_ascii=False)

        description = "将沙盒中已确认的项目文本文件安全回写到当前 ArcReel 项目。仅支持相对路径。"
        runners.append(
            beta_async_tool(name="sync_project_files", description=description, input_schema=sync_schema)(
                sync_project_files
            )
        )
        definitions.append(
            {
                "type": "custom",
                "name": "sync_project_files",
                "description": description,
                "input_schema": sync_schema,
            }
        )
        return runners, definitions

    def _sync_project_files(self, project_name: str, files: list[dict[str, str]]) -> dict[str, Any]:
        project_dir = (self.projects_root / project_name).resolve()
        updated: list[str] = []
        for item in files:
            relative = PurePosixPath(str(item.get("path", "")))
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError("文件路径必须是项目内的相对路径")
            if relative.suffix.lower() not in _SYNC_SUFFIXES or relative.parts[0].startswith("."):
                raise ValueError(f"不允许回写该文件类型: {relative}")
            content = str(item.get("content", ""))
            if len(content.encode("utf-8")) > _MAX_SYNC_FILE_BYTES:
                raise ValueError(f"文件过大: {relative}")
            if relative.suffix.lower() == ".json":
                json.loads(content)
            target = (project_dir / Path(*relative.parts)).resolve()
            if target != project_dir and project_dir not in target.parents:
                raise ValueError("文件路径越界")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".managed-agent.tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(target)
            updated.append(relative.as_posix())
        return {"updated": updated}

    async def send_new_session(
        self,
        project_name: str,
        prompt: str | AsyncIterable[dict],
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
        locale: str = "zh",
    ) -> str:
        await self._ensure_remote_resources()
        assert self._client is not None and self._agent_id and self._environment_id
        archive = await asyncio.to_thread(self._project_archive, project_name)
        uploaded = await self._client.beta.files.upload(file=("project-context.tar.gz", archive, "application/gzip"))
        runners, definitions = self._remote_tools(project_name)
        remote = await self._client.beta.sessions.create(
            agent=cast(
                Any,
                {
                    "type": "agent_with_overrides",
                    "id": self._agent_id,
                    "model": self._model,
                    "system": self._system_prompt(project_name, locale),
                    "tools": [self._builtin_toolset(), *definitions],
                },
            ),
            environment_id=self._environment_id,
            resources=[{"type": "file", "file_id": uploaded.id, "mount_path": "/workspace/project-context.tar.gz"}],
            metadata={"application": "arcreel", "project": project_name},
        )
        session_id = str(remote.id)
        managed = RemoteSession(session_id=session_id, project_name=project_name, assistant_model=self._model)
        self.sessions[session_id] = managed
        await self.meta_store.create(project_name, session_id)
        self._start_background_tasks(managed, runners)
        content = await self._prompt_content(prompt)
        managed.add_message(self._user_echo(echo_text or self._text_from_content(content), echo_content))
        await self._client.beta.sessions.events.send(
            session_id, events=cast(Any, [{"type": "user.message", "content": content}])
        )
        return session_id

    async def _prompt_content(self, prompt: str | AsyncIterable[dict]) -> list[dict[str, Any]]:
        if isinstance(prompt, str):
            return [{"type": "text", "text": prompt}]
        async for item in prompt:
            content = item.get("message", {}).get("content")
            if isinstance(content, list):
                return content
        return []

    @staticmethod
    def _text_from_content(content: list[dict[str, Any]]) -> str:
        return "\n".join(str(block.get("text", "")) for block in content if block.get("type") == "text")

    @staticmethod
    def _user_echo(text: str, echo_content: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        content = echo_content or ([{"type": "text", "text": text}] if text else [])
        return {"type": "user", "message": {"role": "user", "content": content}, "_local_echo": True}

    def _start_background_tasks(self, managed: RemoteSession, runners: list[Any]) -> None:
        managed.monitor_task = asyncio.create_task(self._monitor(managed), name=f"managed-events-{managed.session_id}")
        managed.tool_task = asyncio.create_task(
            self._run_tools(managed.session_id, runners), name=f"managed-tools-{managed.session_id}"
        )

    async def _run_tools(self, session_id: str, runners: list[Any]) -> None:
        assert self._client is not None
        try:
            async for _call in self._client.beta.sessions.events.tool_runner(session_id, tools=runners, max_idle=None):
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Managed Agents custom tool runner failed session_id=%s", session_id)

    @staticmethod
    def _event_dict(event: Any) -> dict[str, Any]:
        if isinstance(event, dict):
            return event
        if hasattr(event, "model_dump"):
            return event.model_dump(mode="json", exclude_none=True)
        return {}

    @classmethod
    def _map_event(cls, event: Any) -> tuple[dict[str, Any] | None, SessionStatus | None]:
        data = cls._event_dict(event)
        event_type = str(data.get("type", ""))
        if event_type == "user.message":
            return {"type": "user", "message": {"role": "user", "content": data.get("content", [])}}, None
        if event_type == "agent.message":
            return {"type": "assistant", "message": {"role": "assistant", "content": data.get("content", [])}}, None
        if event_type in {"agent.tool_use", "agent.custom_tool_use"}:
            block = {
                "type": "tool_use",
                "id": data.get("tool_use_id") or data.get("id"),
                "name": data.get("name"),
                "input": data.get("input", {}),
            }
            return {"type": "assistant", "message": {"role": "assistant", "content": [block]}}, None
        if event_type in {"agent.tool_result", "user.tool_result", "user.custom_tool_result"}:
            block = {
                "type": "tool_result",
                "tool_use_id": data.get("tool_use_id") or data.get("custom_tool_use_id"),
                "content": data.get("content", []),
                "is_error": data.get("is_error", False),
            }
            return {"type": "user", "message": {"role": "user", "content": [block]}}, None
        if event_type == "session.status_running":
            return {"type": "runtime_status", "status": "running"}, "running"
        if event_type == "session.status_idle":
            stop_reason = data.get("stop_reason", {})
            if isinstance(stop_reason, dict) and stop_reason.get("type") != "end_turn":
                return None, None
            result = {"type": "result", "subtype": "success", "stop_reason": "end_turn"}
            return result, "completed"
        if event_type in {"session.status_terminated", "session.deleted"}:
            return {"type": "result", "subtype": "interrupted"}, "interrupted"
        if event_type in {"session.error", "session.status_failed"}:
            return {"type": "result", "subtype": "error", "error": data.get("error")}, "error"
        return None, None

    async def _monitor(self, managed: RemoteSession) -> None:
        assert self._client is not None
        try:
            stream = await self._client.beta.sessions.events.stream(managed.session_id)
            async for event in stream:
                message, status = self._map_event(event)
                if status is not None:
                    managed.status = status
                    await self.meta_store.update_status(managed.session_id, status)
                if message is not None:
                    managed.add_message(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Managed Agents event stream failed session_id=%s", managed.session_id)
            managed.status = "error"
            await self.meta_store.update_status(managed.session_id, "error")
            managed.add_message({"type": "result", "subtype": "error"})

    async def _history(self, session_id: str) -> list[dict[str, Any]]:
        await self._ensure_remote_resources()
        assert self._client is not None
        messages: list[dict[str, Any]] = []
        async for event in self._client.beta.sessions.events.list(session_id, order="asc", limit=100):
            message, _status = self._map_event(event)
            if message is not None:
                messages.append(message)
        return messages

    async def get_history_messages(self, session_id: str) -> list[dict[str, Any]]:
        return await self._history(session_id)

    async def get_or_connect(self, session_id: str, *, meta: SessionMeta | None = None) -> RemoteSession:
        if session_id in self.sessions:
            return self.sessions[session_id]
        if meta is None:
            meta = await self.meta_store.get(session_id)
        if meta is None:
            raise FileNotFoundError(f"session not found: {session_id}")
        await self._ensure_remote_resources()
        assert self._client is not None
        remote = await self._client.beta.sessions.retrieve(session_id)
        status_value = str(getattr(remote, "status", meta.status))
        status: SessionStatus = "running" if "running" in status_value else meta.status
        managed = RemoteSession(
            session_id=session_id, project_name=meta.project_name, status=status, assistant_model=self._model
        )
        managed.message_buffer = await self._history(session_id)
        self.sessions[session_id] = managed
        runners, _definitions = self._remote_tools(meta.project_name)
        self._start_background_tasks(managed, runners)
        return managed

    async def send_message(
        self,
        session_id: str,
        prompt: str | AsyncIterable[dict],
        *,
        echo_text: str | None = None,
        echo_content: list[dict[str, Any]] | None = None,
        meta: SessionMeta | None = None,
    ) -> None:
        managed = await self.get_or_connect(session_id, meta=meta)
        if managed.status == "running":
            raise ValueError("会话正在处理中，请等待当前回复完成后再发送新消息")
        content = await self._prompt_content(prompt)
        managed.status = "running"
        managed.add_message(self._user_echo(echo_text or self._text_from_content(content), echo_content))
        await self.meta_store.update_status(session_id, "running")
        assert self._client is not None
        await self._client.beta.sessions.events.send(
            session_id, events=cast(Any, [{"type": "user.message", "content": content}])
        )

    async def interrupt_session(self, session_id: str) -> SessionStatus:
        meta = await self.meta_store.get(session_id)
        if meta is None:
            raise FileNotFoundError(f"session not found: {session_id}")
        await self._ensure_remote_resources()
        assert self._client is not None
        await self._client.beta.sessions.events.send(session_id, events=[{"type": "user.interrupt"}])
        await self.meta_store.update_status(session_id, "interrupted")
        if session_id in self.sessions:
            self.sessions[session_id].status = "interrupted"
        return "interrupted"

    async def close_session(self, session_id: str, *, reason: str = "session closed") -> None:
        del reason
        managed = self.sessions.pop(session_id, None)
        if managed:
            for task in (managed.monitor_task, managed.tool_task):
                if task and not task.done():
                    task.cancel()
        await self._ensure_remote_resources()
        assert self._client is not None
        with contextlib.suppress(Exception):
            await self._client.beta.sessions.delete(session_id)

    def get_buffered_messages(self, session_id: str) -> list[dict[str, Any]]:
        managed = self.sessions.get(session_id)
        return list(managed.message_buffer) if managed else []

    async def get_pending_questions_snapshot(self, session_id: str) -> list[dict[str, Any]]:
        del session_id
        return []

    async def answer_user_question(self, session_id: str, question_id: str, answers: dict[str, str]) -> None:
        del session_id, question_id, answers
        raise ValueError("远程 Agent 请直接发送文字回复")

    @asynccontextmanager
    async def stream_messages(
        self, session_id: str, *, replay: bool = True, idle_timeout: float = 20.0
    ) -> AsyncIterator[AsyncIterator[dict[str, Any]]]:
        managed = await self.get_or_connect(session_id)
        replay_messages = list(managed.message_buffer) if replay else []
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        managed.subscribers.add(queue)

        async def iterator() -> AsyncIterator[dict[str, Any]]:
            for message in replay_messages:
                yield message
            yield {"type": "_replay_done"}
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=idle_timeout)
                except TimeoutError:
                    yield {"type": "_idle"}

        try:
            yield iterator()
        finally:
            managed.subscribers.discard(queue)

    async def get_status(self, session_id: str) -> SessionStatus | None:
        if session_id in self.sessions:
            return self.sessions[session_id].status
        meta = await self.meta_store.get(session_id)
        return meta.status if meta else None

    def start_patrol(self) -> None:
        return

    async def refresh_config(self) -> None:
        if self._client is not None:
            await self._client.close()
        self._client = None
        self._agent_id = None
        self._environment_id = None
        await self._ensure_remote_resources()

    async def shutdown_gracefully(self, timeout: float = 30.0) -> None:
        del timeout
        tasks: list[asyncio.Task] = []
        for managed in self.sessions.values():
            for task in (managed.monitor_task, managed.tool_task):
                if task and not task.done():
                    task.cancel()
                    tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._client is not None:
            await self._client.close()
