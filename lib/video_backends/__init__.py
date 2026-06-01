"""视频生成服务层公共 API。"""

from lib.providers import PROVIDER_ARK
from lib.video_backends.base import (
    VideoBackend,
    VideoCapability,
    VideoGenerationRequest,
    VideoGenerationResult,
)
from lib.video_backends.registry import create_backend, get_registered_backends, register_backend

__all__ = [
    "PROVIDER_ARK",
    "VideoBackend",
    "VideoCapability",
    "VideoGenerationRequest",
    "VideoGenerationResult",
    "create_backend",
    "get_registered_backends",
    "register_backend",
]

# Auto-register backends — 营销视频 Agent 仅保留 Ark（火山方舟）视频后端。
from lib.video_backends.ark import ArkVideoBackend

register_backend(PROVIDER_ARK, ArkVideoBackend)
