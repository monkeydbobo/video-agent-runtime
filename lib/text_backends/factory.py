"""文本 backend 工厂。"""

from __future__ import annotations

from lib.config.registry import PROVIDER_REGISTRY
from lib.config.resolver import ConfigResolver
from lib.db import async_session_factory
from lib.text_backends.base import TextBackend, TextTaskType
from lib.text_backends.registry import create_backend

# 营销视频 Agent 文本仅保留 Ark（火山方舟）。
PROVIDER_ID_TO_BACKEND: dict[str, str] = {
    "ark": "ark",
}


async def create_text_backend_for_task(
    task_type: TextTaskType,
    project_name: str | None = None,
) -> TextBackend:
    """从 DB 配置创建文本 backend。"""
    resolver = ConfigResolver(async_session_factory)

    async with resolver.session() as r:
        provider_id, model_id = await r.text_backend_for_task(task_type, project_name)
        provider_config = await r.provider_config(provider_id)

    backend_name = PROVIDER_ID_TO_BACKEND.get(provider_id, provider_id)
    kwargs: dict = {"model": model_id}

    kwargs["api_key"] = provider_config.get("api_key")
    # ark：用户优先，缺省回落 ProviderMeta.default_base_url
    # （与 server.services.generation_tasks._fill_simple_provider_kwargs 对称）。
    user_base_url = provider_config.get("base_url")
    meta = PROVIDER_REGISTRY.get(provider_id)
    base_url = user_base_url or (meta.default_base_url if meta else None)
    if base_url:
        kwargs["base_url"] = base_url

    return create_backend(backend_name, **kwargs)
