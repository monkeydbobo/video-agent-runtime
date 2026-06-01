"""AtlasCloudImageBackend — Atlas Cloud GPT Image 2 图片生成后端。"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from lib.atlascloud_shared import (
    ATLASCLOUD_BASE_URL,
    ATLASCLOUD_MAX_WAIT_SEC,
    ATLASCLOUD_MODEL_I2I,
    ATLASCLOUD_MODEL_T2I,
    ATLASCLOUD_POLL_INTERVAL_SEC,
    ATLASCLOUD_RETRYABLE_ERRORS,
)
from lib.image_backends.base import (
    ImageCapability,
    ImageCapabilityError,
    ImageGenerationRequest,
    ImageGenerationResult,
    download_image_to_path,
)
from lib.logging_utils import format_kwargs_for_log
from lib.openai_shared import OPENAI_IMAGE_QUALITY_MAP
from lib.providers import PROVIDER_ATLASCLOUD
from lib.retry import with_retry_async
from lib.video_backends.base import poll_with_retry

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-image-2"
_HTTP_TIMEOUT_SEC = 120.0

# Atlas Cloud 的 GPT Image 2 网关仍接受固定尺寸档位，不能直接沿用 OpenAI
# 官方后端在 ADR 0011 中引入的任意 WxH 计算。
_ATLASCLOUD_IMAGE_SIZE_MAP: dict[tuple[str, str], str] = {
    ("512px", "1:1"): "512x512",
    ("512px", "9:16"): "512x896",
    ("512px", "16:9"): "896x512",
    ("1K", "1:1"): "1024x1024",
    ("1K", "9:16"): "1024x1792",
    ("1K", "16:9"): "1792x1024",
    ("1K", "3:4"): "1024x1792",
    ("1K", "4:3"): "1792x1024",
    ("2K", "1:1"): "2048x2048",
    ("2K", "9:16"): "2048x3584",
    ("2K", "16:9"): "3584x2048",
}


def _resolve_atlascloud_params(
    image_size: str | None,
    aspect_ratio: str,
) -> dict[str, str]:
    """将 ArcReel image_size + aspect_ratio 映射为 Atlas ``size`` / ``quality``。"""
    if image_size is None:
        return {}

    mapped_size = _ATLASCLOUD_IMAGE_SIZE_MAP.get((image_size, aspect_ratio))
    if mapped_size is not None:
        params: dict[str, str] = {"size": mapped_size}
        quality = OPENAI_IMAGE_QUALITY_MAP.get(image_size)
        if quality:
            params["quality"] = quality
        return params

    logger.warning(
        "AtlasCloud image: 未知 image_size=%r (aspect=%r)，原样作为 size 透传",
        image_size,
        aspect_ratio,
    )
    return {"size": image_size}


def _parse_json_body(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError(f"AtlasCloud 响应非 JSON 对象: {type(body).__name__}")
    code = body.get("code")
    if code is not None and code != 200:
        message = body.get("message") or body.get("msg") or f"code={code}"
        raise RuntimeError(f"AtlasCloud API 错误: {message}")
    return body


def _extract_poll_url(base_url: str, generate_body: dict[str, Any]) -> str:
    data = generate_body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("AtlasCloud generateImage 响应缺少 data")

    urls = data.get("urls")
    if isinstance(urls, dict):
        poll_url = urls.get("get")
        if isinstance(poll_url, str) and poll_url.strip():
            return poll_url.strip()

    prediction_id = data.get("id")
    if prediction_id is not None:
        return f"{base_url.rstrip('/')}/model/prediction/{prediction_id}"

    raise RuntimeError("AtlasCloud generateImage 响应缺少 urls.get 或 data.id")


class AtlasCloudImageBackend:
    """Atlas Cloud GPT Image 2 异步图片生成（T2I / I2I）。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        if not api_key:
            raise ValueError("AtlasCloud api_key is required")
        self._api_key = api_key
        self._model = model or DEFAULT_MODEL
        self._base_url = (base_url or ATLASCLOUD_BASE_URL).rstrip("/")
        self._capabilities: set[ImageCapability] = {
            ImageCapability.TEXT_TO_IMAGE,
            ImageCapability.IMAGE_TO_IMAGE,
        }

    @property
    def name(self) -> str:
        return PROVIDER_ATLASCLOUD

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[ImageCapability]:
        return self._capabilities

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _api_model(self, *, has_refs: bool) -> str:
        return ATLASCLOUD_MODEL_I2I if has_refs else ATLASCLOUD_MODEL_T2I

    async def _upload_reference(self, client: httpx.AsyncClient, path: Path) -> str:
        if not path.is_file():
            raise FileNotFoundError(f"参考图不存在: {path}")

        mime, _ = mimetypes.guess_type(path.name)
        mime = mime or "application/octet-stream"

        def _read_bytes() -> bytes:
            return path.read_bytes()

        content = await asyncio.to_thread(_read_bytes)
        files = {"file": (path.name, content, mime)}
        url = f"{self._base_url}/model/uploadMedia"
        response = await client.post(url, headers=self._auth_headers(), files=files)
        body = _parse_json_body(response)
        data = body.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("AtlasCloud uploadMedia 响应缺少 data")
        download_url = data.get("download_url")
        if not isinstance(download_url, str) or not download_url.strip():
            raise RuntimeError("AtlasCloud uploadMedia 响应缺少 download_url")
        return download_url.strip()

    async def _resolve_reference_urls(
        self,
        client: httpx.AsyncClient,
        request: ImageGenerationRequest,
    ) -> list[str]:
        urls: list[str] = []
        for ref in request.reference_images:
            ref_path = Path(ref.path)
            if ref_path.exists():
                urls.append(await self._upload_reference(client, ref_path))
            else:
                logger.warning("参考图不存在，跳过: %s", ref_path)
        return urls

    async def _submit_generation(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> str:
        url = f"{self._base_url}/model/generateImage"
        headers = {**self._auth_headers(), "Content-Type": "application/json"}
        logger.info("调用 %s 图片 API kwargs=%s", self.name, format_kwargs_for_log(payload))
        response = await client.post(url, headers=headers, json=payload)
        body = _parse_json_body(response)
        return _extract_poll_url(self._base_url, body)

    async def _poll_prediction(self, client: httpx.AsyncClient, poll_url: str) -> str:
        async def _poll_once() -> dict[str, Any]:
            response = await client.get(poll_url, headers=self._auth_headers())
            body = _parse_json_body(response)
            data = body.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("AtlasCloud prediction 响应缺少 data")
            return data

        def _is_done(data: dict[str, Any]) -> bool:
            return data.get("status") == "completed"

        def _is_failed(data: dict[str, Any]) -> str | None:
            status = data.get("status")
            if status == "failed":
                err = data.get("error")
                return str(err) if err else "AtlasCloud 图片生成失败"
            return None

        data = await poll_with_retry(
            poll_fn=_poll_once,
            is_done=_is_done,
            is_failed=_is_failed,
            poll_interval=ATLASCLOUD_POLL_INTERVAL_SEC,
            max_wait=ATLASCLOUD_MAX_WAIT_SEC,
            retryable_errors=ATLASCLOUD_RETRYABLE_ERRORS,
            label="AtlasCloud",
        )
        outputs = data.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            raise RuntimeError("AtlasCloud 图片生成完成但 outputs 为空")
        first = outputs[0]
        if not isinstance(first, str) or not first.strip():
            raise RuntimeError("AtlasCloud 图片生成 outputs[0] 无效")
        return first.strip()

    @with_retry_async(retryable_errors=ATLASCLOUD_RETRYABLE_ERRORS)
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        has_refs = bool(request.reference_images)
        if has_refs and ImageCapability.IMAGE_TO_IMAGE not in self._capabilities:
            raise ImageCapabilityError("image_endpoint_mismatch_no_i2i", model=self._model)
        if not has_refs and ImageCapability.TEXT_TO_IMAGE not in self._capabilities:
            raise ImageCapabilityError("image_endpoint_mismatch_no_t2i", model=self._model)

        payload: dict[str, Any] = {
            "model": self._api_model(has_refs=has_refs),
            "prompt": request.prompt,
            "enable_base64_output": False,
            "enable_sync_mode": False,
            "output_format": "jpeg",
            "moderation": "low",
        }
        payload.update(_resolve_atlascloud_params(request.image_size, request.aspect_ratio))

        timeout = httpx.Timeout(_HTTP_TIMEOUT_SEC)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if has_refs:
                image_urls = await self._resolve_reference_urls(client, request)
                if not image_urls:
                    raise ImageCapabilityError(
                        "image_endpoint_mismatch_no_i2i",
                        model=self._model,
                        detail="all reference images failed to upload",
                    )
                payload["images"] = image_urls

            poll_url = await self._submit_generation(client, payload)
            image_url = await self._poll_prediction(client, poll_url)

        await download_image_to_path(image_url, request.output_path)
        logger.info("AtlasCloud 图片生成完成: %s", request.output_path)

        quality = OPENAI_IMAGE_QUALITY_MAP.get(request.image_size) if request.image_size else None
        return ImageGenerationResult(
            image_path=request.output_path,
            provider=PROVIDER_ATLASCLOUD,
            model=self._model,
            quality=quality,
        )
