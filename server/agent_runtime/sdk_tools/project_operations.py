"""Project-bound mutation tools that are safer than exposing host-side Bash."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from server.agent_runtime.sdk_tools._context import ToolContext, tool_error, validate_script_filename

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE_SCRIPT = _PROJECT_ROOT / "agent_runtime_profile/.claude/skills/compose-video/scripts/compose_video.py"
_MAX_ASSETS_PER_CALL = 200
_MAX_NAME_CHARS = 100
_MAX_DESCRIPTION_CHARS = 10_000
_AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}


def _normalize_assets(value: Any, *, allow_voice_style: bool) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("资产数据必须是名称到属性的对象")
    if len(value) > _MAX_ASSETS_PER_CALL:
        raise ValueError(f"单次最多添加 {_MAX_ASSETS_PER_CALL} 个资产")

    normalized: dict[str, dict[str, str]] = {}
    for raw_name, raw_attrs in value.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("资产名称必须是非空字符串")
        name = raw_name.strip()
        if len(name) > _MAX_NAME_CHARS:
            raise ValueError(f"资产名称过长: {name[:20]}…")
        if not isinstance(raw_attrs, dict):
            raise ValueError(f"资产 '{name}' 的属性必须是对象")
        description = raw_attrs.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"资产 '{name}' 缺少非空 description")
        if len(description) > _MAX_DESCRIPTION_CHARS:
            raise ValueError(f"资产 '{name}' 的 description 过长")
        entry = {"description": description.strip()}
        if allow_voice_style:
            voice_style = raw_attrs.get("voice_style", "")
            if not isinstance(voice_style, str):
                raise ValueError(f"资产 '{name}' 的 voice_style 必须是字符串")
            entry["voice_style"] = voice_style.strip()
        normalized[name] = entry
    return normalized


def update_project_assets_tool(ctx: ToolContext):
    @tool(
        "update_project_assets",
        "向当前项目批量追加角色（营销模式下为产品）、场景和道具定义。已存在的同名资产不会覆盖。",
        {
            "type": "object",
            "properties": {
                "characters": {"type": "object", "additionalProperties": {"type": "object"}},
                "scenes": {"type": "object", "additionalProperties": {"type": "object"}},
                "props": {"type": "object", "additionalProperties": {"type": "object"}},
            },
        },
    )
    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            characters = _normalize_assets(args.get("characters"), allow_voice_style=True)
            scenes = _normalize_assets(args.get("scenes"), allow_voice_style=False)
            props = _normalize_assets(args.get("props"), allow_voice_style=False)
            if not any((characters, scenes, props)):
                raise ValueError("至少提供 characters、scenes、props 之一")

            requested = {"characters": characters, "scenes": scenes, "props": props}
            added: dict[str, int] = {}
            skipped: dict[str, int] = {}

            def mutate(project: dict[str, Any]) -> None:
                for bucket, entries in requested.items():
                    current = project.setdefault(bucket, {})
                    if not isinstance(current, dict):
                        raise ValueError(f"project.json 的 {bucket} 必须是对象")
                    skipped[bucket] = sum(name in current for name in entries)
                    new_entries = {name: value for name, value in entries.items() if name not in current}
                    current.update(new_entries)
                    added[bucket] = len(new_entries)

            await asyncio.to_thread(ctx.pm.update_project, ctx.project_name, mutate)
            total = sum(added.values())
            lines = [f"项目资产更新完成，共新增 {total} 个："]
            labels = {"characters": "角色/产品", "scenes": "场景", "props": "道具"}
            for bucket in ("characters", "scenes", "props"):
                lines.append(f"- {labels[bucket]}：新增 {added[bucket]}，跳过同名 {skipped[bucket]}")
            return {"content": [{"type": "text", "text": "\n".join(lines)}]}
        except Exception as exc:  # noqa: BLE001
            return tool_error("update_project_assets", exc)

    return _handler


def _safe_output_filename(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or "/" in value or "\\" in value or Path(value).name != value or value in {".", ".."}:
        raise ValueError("output 必须是纯文件名")
    if Path(value).suffix.lower() != ".mp4":
        raise ValueError("output 必须使用 .mp4 扩展名")
    return value


def _safe_music_path(project_path: Path, value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or Path(value).is_absolute():
        raise ValueError("music 必须是当前项目内的相对路径")
    resolved = (project_path / value).resolve(strict=False)
    project = project_path.resolve(strict=True)
    if not resolved.is_relative_to(project) or not resolved.is_file():
        raise ValueError("music 必须是当前项目内已存在的文件")
    if resolved.suffix.lower() not in _AUDIO_SUFFIXES:
        raise ValueError("music 文件类型不受支持")
    return resolved.relative_to(project).as_posix()


async def _run_compose(ctx: ToolContext, args: dict[str, Any]) -> str:
    script = validate_script_filename(str(args.get("script", "")))
    output = _safe_output_filename(args.get("output"))
    music = _safe_music_path(ctx.project_path, args.get("music"))
    if not _COMPOSE_SCRIPT.is_file():
        raise RuntimeError("compose-video 内置脚本不存在")

    command = [sys.executable, str(_COMPOSE_SCRIPT), script]
    if output:
        command.extend(["--output", output])
    if music:
        command.extend(["--music", music])
    if args.get("use_transitions") is False:
        command.append("--no-transitions")

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(ctx.project_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    timeout = max(60, min(7200, int(os.environ.get("ARCREEL_COMPOSE_TIMEOUT_SECONDS", "3600"))))
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError(f"视频合成超过 {timeout} 秒，已终止") from None
    text = stdout.decode("utf-8", errors="replace")
    error_text = stderr.decode("utf-8", errors="replace")
    if process.returncode != 0:
        raise RuntimeError((text + "\n" + error_text).strip()[-20_000:])
    return (text + (f"\n[stderr]\n{error_text}" if error_text else "")).strip()[-20_000:]


def compose_video_tool(ctx: ToolContext):
    @tool(
        "compose_video",
        "在 Railway 内使用固定的 ArcReel/ffmpeg 流程合成当前项目的 drama 单集视频；不开放任意宿主机命令。",
        {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "scripts/ 下的纯文件名，如 episode_1.json"},
                "output": {"type": "string", "description": "可选的 .mp4 纯文件名，固定写入 output/"},
                "music": {"type": "string", "description": "可选的项目内相对音频路径"},
                "use_transitions": {"type": "boolean", "default": True},
            },
            "required": ["script"],
        },
    )
    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            text = await _run_compose(ctx, args)
            return {"content": [{"type": "text", "text": text or "视频合成完成"}]}
        except Exception as exc:  # noqa: BLE001
            return tool_error("compose_video", exc)

    return _handler
