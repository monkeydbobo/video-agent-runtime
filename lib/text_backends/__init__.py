"""文本生成服务层公共 API。"""

from lib.text_backends.base import (
    ImageInput,
    TextBackend,
    TextCapability,
    TextGenerationRequest,
    TextGenerationResult,
    TextTaskType,
)
from lib.text_backends.registry import create_backend, get_registered_backends, register_backend

__all__ = [
    "ImageInput",
    "TextBackend",
    "TextCapability",
    "TextGenerationRequest",
    "TextGenerationResult",
    "TextTaskType",
    "create_backend",
    "get_registered_backends",
    "register_backend",
]

# Backend auto-registration — 营销视频 Agent 仅保留 Ark（火山方舟）文本后端。
from lib.providers import PROVIDER_ARK
from lib.text_backends.ark import ArkTextBackend

register_backend(PROVIDER_ARK, ArkTextBackend)
