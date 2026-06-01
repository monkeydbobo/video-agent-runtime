"""图片生成服务层公共 API。"""

from lib.image_backends.base import (
    ImageBackend,
    ImageCapability,
    ImageCapabilityError,
    ImageGenerationRequest,
    ImageGenerationResult,
    ReferenceImage,
)
from lib.image_backends.registry import create_backend, get_registered_backends, register_backend

__all__ = [
    "ImageBackend",
    "ImageCapability",
    "ImageCapabilityError",
    "ImageGenerationRequest",
    "ImageGenerationResult",
    "ReferenceImage",
    "create_backend",
    "get_registered_backends",
    "register_backend",
]

# Backend auto-registration — 营销视频 Agent 图片保留 Ark（火山方舟）+ OpenAI。
from lib.image_backends.ark import ArkImageBackend
from lib.image_backends.openai import OpenAIImageBackend
from lib.providers import PROVIDER_ARK, PROVIDER_OPENAI

register_backend(PROVIDER_ARK, ArkImageBackend)
register_backend(PROVIDER_OPENAI, OpenAIImageBackend)
