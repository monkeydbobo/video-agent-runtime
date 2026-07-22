"""Project-bound E2B workspaces exposed to Claude as an in-process MCP server."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import posixpath
import re
from pathlib import Path, PurePosixPath
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from e2b import AsyncSandbox
from e2b.exceptions import SandboxException, SandboxNotFoundException
from e2b.sandbox.commands.command_handle import CommandExitException

logger = logging.getLogger(__name__)

REMOTE_PROJECT_ROOT = PurePosixPath("/home/user/project")
_PROJECT_SUFFIXES = {".json", ".md", ".txt", ".csv", ".html"}
_PROFILE_SUFFIXES = _PROJECT_SUFFIXES | {".py"}
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_TOOL_OUTPUT = 100_000


def _tool_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": [{"type": "text", "text": text[:_MAX_TOOL_OUTPUT]}]}
    if is_error:
        payload["is_error"] = True
    return payload


class E2BWorkspaceManager:
    """Own one persistent, network-disabled E2B sandbox per Agent session."""

    def __init__(self, *, projects_root: Path) -> None:
        self.projects_root = Path(projects_root).resolve(strict=False)
        self.template = os.environ.get("ARCREEL_E2B_TEMPLATE", "base").strip() or "base"
        self.timeout = max(60, int(os.environ.get("ARCREEL_E2B_TIMEOUT_SECONDS", "900")))
        self._sandboxes: dict[str, AsyncSandbox] = {}
        self._sandbox_ids: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _require_api_key(self) -> None:
        if not os.environ.get("E2B_API_KEY", "").strip():
            raise RuntimeError("E2B 沙盒尚未配置：请在 Railway 添加 E2B_API_KEY。")

    def sandbox_id_for(self, session_key: str) -> str | None:
        return self._sandbox_ids.get(session_key)

    async def prepare(
        self,
        session_key: str,
        project_name: str,
        *,
        sandbox_id: str | None = None,
    ) -> AsyncSandbox:
        if session_key in self._sandboxes:
            sandbox = self._sandboxes[session_key]
            if not await sandbox.is_running():
                await sandbox.connect(timeout=self.timeout)
            return sandbox
        lock = self._locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            if session_key in self._sandboxes:
                return self._sandboxes[session_key]
            self._require_api_key()
            if sandbox_id:
                try:
                    sandbox = await AsyncSandbox.connect(sandbox_id, timeout=self.timeout)
                except SandboxNotFoundException:
                    logger.info("E2B sandbox 已不存在，重建 session=%s", session_key)
                    sandbox = await self._create_sandbox(project_name)
            else:
                sandbox = await self._create_sandbox(project_name)
            self._sandboxes[session_key] = sandbox
            self._sandbox_ids[session_key] = sandbox.sandbox_id
            return sandbox

    async def _create_sandbox(self, project_name: str) -> AsyncSandbox:
        sandbox = await AsyncSandbox.create(
            self.template,
            timeout=self.timeout,
            metadata={"application": "arcreel", "project": project_name},
            secure=True,
            allow_internet_access=False,
            lifecycle={"on_timeout": "pause", "auto_resume": True},
        )
        await self._upload_project(sandbox, project_name)
        return sandbox

    async def bind_session(self, old_key: str, session_id: str) -> str | None:
        # Keep the temporary-key alias: the MCP handler closure was created
        # before Claude disclosed its real session id and continues using it.
        sandbox = self._sandboxes.get(old_key)
        sandbox_id = self._sandbox_ids.get(old_key)
        if sandbox is not None:
            self._sandboxes[session_id] = sandbox
        if sandbox_id is not None:
            self._sandbox_ids[session_id] = sandbox_id
        return sandbox_id

    def _project_dir(self, project_name: str) -> Path:
        project = (self.projects_root / project_name).resolve(strict=False)
        if project.parent != self.projects_root or not project.is_dir():
            raise FileNotFoundError(f"project not found: {project_name}")
        return project

    @staticmethod
    def _included_file(path: Path, relative: Path) -> bool:
        is_profile = bool(relative.parts and relative.parts[0] == ".claude")
        allowed = _PROFILE_SUFFIXES if is_profile else _PROJECT_SUFFIXES
        return path.suffix.lower() in allowed and path.stat().st_size <= _MAX_FILE_BYTES

    async def _upload_project(self, sandbox: AsyncSandbox, project_name: str) -> None:
        project = self._project_dir(project_name)
        await sandbox.files.make_dir(str(REMOTE_PROJECT_ROOT))
        for path in project.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(project)
            if not self._included_file(path, relative):
                continue
            remote = REMOTE_PROJECT_ROOT.joinpath(*relative.parts)
            await sandbox.files.make_dir(str(remote.parent))
            await sandbox.files.write(str(remote), path.read_bytes())

    @staticmethod
    def _remote_path(value: str) -> PurePosixPath:
        candidate = PurePosixPath(value)
        if not candidate.is_absolute():
            candidate = REMOTE_PROJECT_ROOT / candidate
        normalized = PurePosixPath(posixpath.normpath(str(candidate)))
        if normalized != REMOTE_PROJECT_ROOT and REMOTE_PROJECT_ROOT not in normalized.parents:
            raise ValueError("路径必须位于 /home/user/project 内")
        return normalized

    @staticmethod
    def _syncable(relative: PurePosixPath) -> bool:
        return (
            bool(relative.parts)
            and not relative.parts[0].startswith(".")
            and relative.suffix.lower() in _PROJECT_SUFFIXES
        )

    async def _sync_one(self, sandbox: AsyncSandbox, project_name: str, remote: PurePosixPath) -> bool:
        relative = remote.relative_to(REMOTE_PROJECT_ROOT)
        if not self._syncable(relative):
            return False
        raw = await sandbox.files.read(str(remote), format="bytes")
        data = bytes(raw)
        if len(data) > _MAX_FILE_BYTES:
            raise ValueError(f"文件过大，拒绝回写: {relative}")
        text = data.decode("utf-8")
        if relative.suffix.lower() == ".json":
            json.loads(text)
        project = self._project_dir(project_name)
        target = (project / Path(*relative.parts)).resolve(strict=False)
        if target != project and project not in target.parents:
            raise ValueError("回写路径越界")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".e2b.tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(target)
        return True

    async def sync_all(self, sandbox: AsyncSandbox, project_name: str) -> list[str]:
        entries = await sandbox.files.list(str(REMOTE_PROJECT_ROOT), depth=20)
        updated: list[str] = []
        for entry in entries:
            if getattr(getattr(entry, "type", None), "value", None) != "file":
                continue
            remote = self._remote_path(entry.path)
            if await self._sync_one(sandbox, project_name, remote):
                updated.append(str(remote.relative_to(REMOTE_PROJECT_ROOT)))
        return updated

    async def pause(self, session_key: str) -> None:
        sandbox = self._sandboxes.get(session_key)
        if sandbox is not None:
            try:
                await sandbox.pause()
            except SandboxException:
                logger.warning("暂停 E2B sandbox 失败 session=%s", session_key, exc_info=True)

    async def kill(self, session_key: str, *, sandbox_id: str | None = None) -> None:
        sandbox = self._sandboxes.pop(session_key, None)
        known_id = self._sandbox_ids.pop(session_key, None) or sandbox_id
        self._locks.pop(session_key, None)
        for alias, alias_id in list(self._sandbox_ids.items()):
            if known_id and alias_id == known_id:
                self._sandbox_ids.pop(alias, None)
                self._sandboxes.pop(alias, None)
                self._locks.pop(alias, None)
        if sandbox is not None:
            await sandbox.kill()
        elif known_id:
            await AsyncSandbox.kill(known_id)

    async def shutdown(self) -> None:
        unique = {sandbox.sandbox_id: sandbox for sandbox in self._sandboxes.values()}
        await asyncio.gather(*(sandbox.pause() for sandbox in unique.values()), return_exceptions=True)

    def build_mcp_server(self, *, session_key: str, project_name: str) -> Any:
        """Build E2B tools bound to exactly one project and sandbox."""

        async def get_sandbox() -> AsyncSandbox:
            sandbox = await self.prepare(session_key, project_name)
            # ArcReel business MCP tools run on Railway and may have changed
            # project.json/scripts since the preceding E2B call.
            await self._upload_project(sandbox, project_name)
            return sandbox

        @tool(
            "bash",
            "在隔离的 E2B Linux 沙盒中执行命令。工作目录固定为 /home/user/project；沙盒无外网。",
            {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"},
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600},
                },
                "required": ["command"],
            },
        )
        async def bash_tool(args: dict[str, Any]) -> dict[str, Any]:
            try:
                sandbox = await get_sandbox()
                timeout = min(600, max(1, int(args.get("timeout_seconds", 120))))
                command_failed = False
                try:
                    result = await sandbox.commands.run(
                        str(args["command"]), cwd=str(REMOTE_PROJECT_ROOT), timeout=timeout
                    )
                except CommandExitException as exc:
                    result = exc
                    command_failed = True
                updated = await self.sync_all(sandbox, project_name)
                text = result.stdout
                if result.stderr:
                    text += f"\n[stderr]\n{result.stderr}"
                if updated:
                    text += f"\n[已同步回 ArcReel: {', '.join(updated)}]"
                return _tool_result(text or "命令执行成功", is_error=command_failed)
            except Exception as exc:  # noqa: BLE001
                return _tool_result(f"E2B 命令执行失败: {exc}", is_error=True)

        @tool(
            "read_file",
            "读取 E2B 项目工作区内的 UTF-8 文本文件。",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )
        async def read_file_tool(args: dict[str, Any]) -> dict[str, Any]:
            try:
                sandbox = await get_sandbox()
                path = self._remote_path(str(args["path"]))
                value = await sandbox.files.read(str(path), format="text")
                return _tool_result(str(value))
            except Exception as exc:  # noqa: BLE001
                return _tool_result(f"读取失败: {exc}", is_error=True)

        @tool(
            "write_file",
            "写入 E2B 项目工作区文件，并将允许的项目文本文件原子回写到 ArcReel。",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        )
        async def write_file_tool(args: dict[str, Any]) -> dict[str, Any]:
            try:
                sandbox = await get_sandbox()
                path = self._remote_path(str(args["path"]))
                content = str(args["content"])
                if len(content.encode("utf-8")) > _MAX_FILE_BYTES:
                    raise ValueError("文件超过 2 MiB")
                await sandbox.files.make_dir(str(path.parent))
                await sandbox.files.write(str(path), content)
                synced = await self._sync_one(sandbox, project_name, path)
                suffix = "并已同步回 ArcReel" if synced else "（仅保留在沙盒）"
                return _tool_result(f"已写入 {path} {suffix}")
            except Exception as exc:  # noqa: BLE001
                return _tool_result(f"写入失败: {exc}", is_error=True)

        @tool(
            "list_files",
            "列出 E2B 项目工作区中的文件和目录。",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "depth": {"type": "integer", "minimum": 1, "maximum": 10},
                },
            },
        )
        async def list_files_tool(args: dict[str, Any]) -> dict[str, Any]:
            try:
                sandbox = await get_sandbox()
                path = self._remote_path(str(args.get("path", ".")))
                depth = min(10, max(1, int(args.get("depth", 3))))
                entries = await sandbox.files.list(str(path), depth=depth)
                lines = [f"{getattr(entry.type, 'value', 'unknown')}\t{entry.path}" for entry in entries]
                return _tool_result("\n".join(lines) or "目录为空")
            except Exception as exc:  # noqa: BLE001
                return _tool_result(f"列目录失败: {exc}", is_error=True)

        @tool(
            "grep",
            "在 E2B 项目工作区的文本文件中搜索正则表达式。",
            {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                },
                "required": ["pattern"],
            },
        )
        async def grep_tool(args: dict[str, Any]) -> dict[str, Any]:
            try:
                sandbox = await get_sandbox()
                root = self._remote_path(str(args.get("path", ".")))
                pattern = re.compile(str(args["pattern"]))
                entries = await sandbox.files.list(str(root), depth=20)
                matches: list[str] = []
                for entry in entries:
                    if getattr(getattr(entry, "type", None), "value", None) != "file":
                        continue
                    if PurePosixPath(entry.path).suffix.lower() not in _PROFILE_SUFFIXES:
                        continue
                    content = str(await sandbox.files.read(entry.path, format="text"))
                    for number, line in enumerate(content.splitlines(), start=1):
                        if pattern.search(line):
                            matches.append(f"{entry.path}:{number}:{line}")
                            if len(matches) >= 500:
                                return _tool_result("\n".join(matches) + "\n[结果已截断]")
                return _tool_result("\n".join(matches) or "未找到匹配")
            except Exception as exc:  # noqa: BLE001
                return _tool_result(f"搜索失败: {exc}", is_error=True)

        return create_sdk_mcp_server(
            name="e2b",
            version="1.0.0",
            tools=[bash_tool, read_file_tool, write_file_tool, list_files_tool, grep_tool],
        )
