"""按 project > legacy > custom provider default > None 解析每次生成调用的分辨率。"""

from __future__ import annotations

# 当 resolve_resolution 返回 None 时下游的保底分辨率。#387 Grok 即便 registry
# 声明 1080p 也可能被 xai_sdk 拒收，故按 provider 区分。
PROVIDER_FALLBACK_RESOLUTION: dict[str, str] = {
    "ark": "720p",
    "openai": "720p",
}


def get_provider_fallback(provider_id: str | None, default: str = "1080p") -> str:
    """对 registry ID（如 ``gemini-aistudio``）归一化到短前缀后查 fallback。"""
    if not provider_id:
        return default
    if provider_id in PROVIDER_FALLBACK_RESOLUTION:
        return PROVIDER_FALLBACK_RESOLUTION[provider_id]
    short = provider_id.split("-", 1)[0]
    return PROVIDER_FALLBACK_RESOLUTION.get(short, default)


def _from_project(project: dict, provider_id: str, model_id: str) -> str | None:
    # 内层也用 `or {}` 是因为 dict.get("k", {}) 在 value 显式为 None 时会返回 None，
    # 导致后续链调 AttributeError；project.json 手编可能出现这种脏值。
    key = f"{provider_id}/{model_id}"
    override = ((project.get("model_settings") or {}).get(key) or {}).get("resolution")
    if override:
        return override
    legacy = ((project.get("video_model_settings") or {}).get(model_id) or {}).get("resolution")
    if legacy:
        return legacy
    return None


async def resolve_resolution(project: dict, provider_id: str, model_id: str) -> str | None:
    """按 project.model_settings → legacy video_model_settings → None。

    None 代表“调用时不传 SDK resolution 参数”。
    """
    return _from_project(project, provider_id, model_id)
