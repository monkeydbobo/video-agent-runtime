"""Atlas Cloud 共享常量与工具。

供 image_backends.atlascloud 与 cost_calculator 复用。
"""

from __future__ import annotations

ATLASCLOUD_BASE_URL = "https://api.atlascloud.ai/api/v1"

ATLASCLOUD_MODEL_T2I = "openai/gpt-image-2/text-to-image"
ATLASCLOUD_MODEL_I2I = "openai/gpt-image-2/edit"

# 轮询间隔与超时（秒）
ATLASCLOUD_POLL_INTERVAL_SEC = 2.0
ATLASCLOUD_MAX_WAIT_SEC = 300.0

# Atlas Cloud 公示价：USD/张（flat，与 quality/size 无关）
ATLASCLOUD_IMAGE_FLAT_COST_USD = 0.008

ATLASCLOUD_RETRYABLE_ERRORS: tuple[type[Exception], ...] = ()

try:
    import httpx

    ATLASCLOUD_RETRYABLE_ERRORS = (
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.NetworkError,
    )
except ImportError:
    pass
