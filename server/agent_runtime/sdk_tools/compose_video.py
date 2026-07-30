"""Railway-side MCP tool for composing a project video with FFmpeg."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from server.agent_runtime.sdk_tools._context import ToolContext, tool_error, validate_script_filename

_COMPOSE_SCRIPT = (
    Path(__file__).resolve().parents[3] / "agent_runtime_profile/.claude/skills/compose-video/scripts/compose_video.py"
)
_PROCESS_TIMEOUT_SECONDS = 30 * 60


def _validate_relative_file(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空相对路径")
    path = Path(value)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError(f"{field} 必须位于当前项目目录内")
    return value


def compose_video_tool(ctx: ToolContext):
    """Create a project-bound handler that runs the composer in Railway."""

    @tool(
        "compose_video",
        "在 Railway 主容器中使用 FFmpeg 合成当前项目的视频。不要在 E2B Bash 中运行合成脚本；"
        "视频和音频文件保留在 Railway 项目目录，由此工具直接读取。",
        {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "剧本文件名（如 episode_1.json），必须是纯文件名",
                },
                "output": {
                    "type": "string",
                    "description": "可选的输出文件名或项目内相对路径",
                },
                "music": {
                    "type": "string",
                    "description": "可选的项目内背景音乐相对路径",
                },
                "no_transitions": {
                    "type": "boolean",
                    "description": "禁用片段之间的转场",
                },
            },
            "required": ["script"],
        },
    )
    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            script_filename = validate_script_filename(args["script"])
            project_path = ctx.project_path
            if not _COMPOSE_SCRIPT.is_file():
                raise FileNotFoundError(f"找不到 Railway 合成脚本: {_COMPOSE_SCRIPT}")

            command = [sys.executable, str(_COMPOSE_SCRIPT), script_filename]
            output = args.get("output")
            if output is not None:
                command.extend(["--output", _validate_relative_file(output, field="output")])
            music = args.get("music")
            if music is not None:
                command.extend(["--music", _validate_relative_file(music, field="music")])
            if bool(args.get("no_transitions")):
                command.append("--no-transitions")

            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=project_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=_PROCESS_TIMEOUT_SECONDS)
            except TimeoutError:
                process.kill()
                await process.wait()
                raise TimeoutError(f"视频合成超过 {_PROCESS_TIMEOUT_SECONDS // 60} 分钟，已终止") from None

            log = stdout.decode("utf-8", errors="replace").strip()
            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg 合成失败（退出码 {process.returncode}）")
            if len(log) > 20_000:
                log = log[-20_000:]
            return {"content": [{"type": "text", "text": f"✅ 视频已在 Railway 容器中合成。\n{log}".strip()}]}
        except Exception as exc:  # noqa: BLE001
            return tool_error("compose_video", exc)

    return _handler
