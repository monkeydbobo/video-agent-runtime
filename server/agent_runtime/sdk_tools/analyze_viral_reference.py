"""MCP tool for marketing viral-reference video understanding."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from lib.text_backends.base import ImageInput, TextGenerationRequest, TextTaskType
from lib.text_generator import TextGenerator
from server.agent_runtime.sdk_tools._context import ToolContext, tool_error

_VIDEO_EXTS = {".mp4", ".mov", ".webm"}
_MAX_FRAMES = 6


def _resolve_video_path(project_path: Path, value: str | None) -> Path:
    if value:
        candidate = Path(value)
        path = candidate if candidate.is_absolute() else project_path / candidate
    else:
        ref_dir = project_path / "reference_videos"
        if not ref_dir.exists():
            raise FileNotFoundError("reference_videos/ 目录不存在，请先上传爆款参考视频")
        videos = [p for p in ref_dir.iterdir() if p.is_file() and p.suffix.lower() in _VIDEO_EXTS]
        if not videos:
            raise FileNotFoundError("reference_videos/ 下未找到 .mp4/.mov/.webm 爆款参考视频")
        path = max(videos, key=lambda p: p.stat().st_mtime)

    resolved = path.resolve()
    if not resolved.is_relative_to(project_path.resolve()):
        raise ValueError(f"参考视频路径超出项目目录: {value}")
    if not resolved.is_file():
        raise FileNotFoundError(f"参考视频不存在: {resolved}")
    if resolved.suffix.lower() not in _VIDEO_EXTS:
        raise ValueError(f"参考视频格式不支持: {resolved.suffix}")
    return resolved


def _probe_video(video_path: Path) -> dict[str, Any]:
    if shutil.which("ffprobe") is None:
        raise RuntimeError("未检测到 ffprobe，无法分析参考视频")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {result.stderr}")
    payload = json.loads(result.stdout or "{}")
    stream = next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), {})
    duration = float(payload.get("format", {}).get("duration") or stream.get("duration") or 0)
    return {
        "duration_seconds": round(duration, 2),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
    }


def _extract_keyframes(video_path: Path, frames_dir: Path, duration: float) -> list[Path]:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("未检测到 ffmpeg，无法抽取参考帧")
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("frame_*.jpg"):
        old.unlink()

    count = max(1, min(_MAX_FRAMES, int(duration // 4) or 1))
    timestamps = [max(0.0, (duration * (i + 1)) / (count + 1)) for i in range(count)]
    out: list[Path] = []
    for idx, ts in enumerate(timestamps, start=1):
        frame = frames_dir / f"frame_{idx:02d}.jpg"
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{ts:.2f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(frame),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and frame.exists():
            out.append(frame)
    if not out:
        raise RuntimeError("未能从参考视频抽取关键帧")
    return out


def _build_prompt(project: dict[str, Any], video_rel: str, meta: dict[str, Any], frame_rels: list[str]) -> str:
    return f"""你是一位营销短视频拆解专家。请基于用户上传的爆款参考视频关键帧，输出可复刻但不抄袭的结构化分析。

项目标题：{project.get("title", "")}
项目概述：{project.get("overview", {}).get("synopsis", "") if isinstance(project.get("overview"), dict) else ""}
参考视频：{video_rel}
视频信息：{meta.get("duration_seconds")} 秒，{meta.get("width")}x{meta.get("height")}
关键帧：{", ".join(frame_rels)}

输出必须使用以下 Markdown 结构：

# 爆款视频内容理解

## 基础信息
- 时长：
- 画幅：
- 平台风格：
- 目标受众：

## 结构拆解
| 段落 | 时间段 | 画面动作 | 口播/字幕 | 情绪/节奏 | 复刻要点 |
|---|---|---|---|---|---|

## 可复刻模板
- 开头 hook：
- 中段卖点展开：
- 信任背书/反差点：
- CTA：

## 禁止照搬
- 不复刻具体人物、品牌、logo、原始台词中的可识别表达。

只借鉴节奏、镜头结构、卖点展开方式和 CTA 放置方式；不要复制原视频中的品牌、人物、音乐名、logo 或完整台词。"""


def analyze_viral_reference_tool(ctx: ToolContext):
    @tool(
        "analyze_viral_reference",
        "分析 marketing 项目的爆款参考视频，抽取关键帧并生成 drafts/episode_N/step0_viral_analysis.md。",
        {
            "type": "object",
            "properties": {
                "episode": {"type": "integer", "description": "剧集编号"},
                "video_path": {
                    "type": "string",
                    "description": "参考视频路径（相对项目目录）；不传则取 reference_videos/ 最近上传的视频",
                },
                "dry_run": {"type": "boolean", "description": "仅抽帧并返回 prompt，不调用模型"},
            },
            "required": ["episode"],
        },
    )
    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            episode = int(args["episode"])
            dry_run = bool(args.get("dry_run"))
            project_path = ctx.project_path
            project = ctx.pm.load_project(ctx.project_name)
            if project.get("content_mode") != "marketing":
                raise ValueError("analyze_viral_reference 仅支持 content_mode=marketing 的项目")

            video_path = _resolve_video_path(project_path, args.get("video_path"))
            video_rel = video_path.relative_to(project_path).as_posix()
            meta = _probe_video(video_path)
            drafts_dir = project_path / "drafts" / f"episode_{episode}"
            frames_dir = drafts_dir / "viral_frames"
            frames = _extract_keyframes(video_path, frames_dir, float(meta["duration_seconds"] or 0))
            frame_rels = [p.relative_to(project_path).as_posix() for p in frames]
            prompt = _build_prompt(project, video_rel, meta, frame_rels)

            if dry_run:
                return {"content": [{"type": "text", "text": f"DRY RUN — Prompt:\n\n{prompt}"}]}

            generator = await TextGenerator.create(TextTaskType.STYLE_ANALYSIS, project_name=ctx.project_name)
            result = await generator.generate(
                TextGenerationRequest(
                    prompt=prompt,
                    images=[ImageInput(path=p) for p in frames],
                    max_output_tokens=8000,
                ),
                project_name=ctx.project_name,
            )
            analysis = result.text.strip()
            drafts_dir.mkdir(parents=True, exist_ok=True)
            analysis_path = drafts_dir / "step0_viral_analysis.md"
            analysis_path.write_text(analysis, encoding="utf-8")

            segments_count = analysis.count("|") // 6 if "|" in analysis else 0
            rel = analysis_path.relative_to(project_path).as_posix()
            text = (
                "✅ 爆款参考视频内容理解完成\n"
                f"参考视频: {video_rel}\n"
                f"时长: {meta['duration_seconds']} 秒\n"
                f"关键帧: {len(frame_rels)} 张\n"
                f"文件: {rel}"
            )
            return {
                "content": [{"type": "text", "text": text}],
                "analysis_path": rel,
                "duration_seconds": meta["duration_seconds"],
                "segments_count": segments_count,
            }
        except Exception as exc:  # noqa: BLE001
            return tool_error("analyze_viral_reference", exc)

    return _handler
