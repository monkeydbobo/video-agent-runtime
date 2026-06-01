"""共享校验函数，供多个 router 复用。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException

from lib.config.registry import PROVIDER_REGISTRY
from lib.i18n import _ as _default_translate


def validate_backend_value(value: str, field_name: str, _t: Callable[..., str] = _default_translate) -> None:
    """校验 ``provider/model`` 格式的 backend 字段值。

    营销视频 Agent 仅接受 ``PROVIDER_REGISTRY`` 的规范 provider id（ark / openai）。
    legacy provider 名与已移除的自定义供应商（``custom-`` 前缀）一律拒绝。

    Raises:
        HTTPException(400): 格式不合法、或 provider 不在注册表中。
    """
    if "/" not in value:
        if value in PROVIDER_REGISTRY:
            return  # 裸 registry id（无 model），下游按全局默认补全
        detail = _t("invalid_backend_format", field_name=field_name)
        raise HTTPException(
            status_code=400,
            detail=detail,
        )
    provider_id = value.split("/", 1)[0]
    if provider_id not in PROVIDER_REGISTRY:
        detail = _t("unknown_provider", provider_id=provider_id)
        raise HTTPException(
            status_code=400,
            detail=detail,
        )
