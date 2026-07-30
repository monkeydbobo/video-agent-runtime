"""StreamLake (快手万擎) asynchronous video generation backend."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from lib.db.repositories.usage_repo import MAX_BILLED_DURATION_SECONDS
from lib.logging_utils import format_kwargs_for_log
from lib.providers import PROVIDER_STREAMLAKE
from lib.retry import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DOWNLOAD_BACKOFF_SECONDS,
    DOWNLOAD_MAX_ATTEMPTS,
    with_retry_async,
)
from lib.streamlake_shared import (
    STREAMLAKE_BASE_URL,
    extract_streamlake_task_id,
    extract_streamlake_video_url,
    streamlake_failure_reason,
    streamlake_is_done,
)
from lib.video_backends.base import (
    ProviderJobIdPersistenceMixin,
    ResumeExpiredError,
    VideoCapabilities,
    VideoCapability,
    VideoCapabilityError,
    VideoGenerationRequest,
    VideoGenerationResult,
    download_video,
    poll_with_retry,
    should_retry_download,
    should_retry_poll,
    should_retry_submit,
    submit_post,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ep-t29dbm-1784275940772279346"
_SUBMIT_PATH = "/videos/generations"
_POLL_INTERVAL_SECONDS = 5.0
_MIN_POLL_TIMEOUT_SECONDS = 900.0
_POLL_TIMEOUT_PER_SECOND = 90.0
_MIN_DURATION_SECONDS = 3
_MAX_DURATION_SECONDS = 10


class StreamLakeVideoBackend(ProviderJobIdPersistenceMixin):
    """StreamLake 视频后端，model 同时作为请求体 model 和轮询 endpointId。"""

    def __init__(
        self,
        *,
        api_key: str,
        model: str | None = None,
        base_url: str | None = None,
        http_timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("StreamLakeVideoBackend 需要 api_key")
        self._api_key = api_key
        self._model = model or DEFAULT_MODEL
        self._base_url = (base_url or STREAMLAKE_BASE_URL).rstrip("/")
        self._http_timeout = http_timeout
        self._capabilities = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
            VideoCapability.SEED_CONTROL,
        }

    @property
    def name(self) -> str:
        return PROVIDER_STREAMLAKE

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set[VideoCapability]:
        return self._capabilities

    @property
    def video_capabilities(self) -> VideoCapabilities:
        return VideoCapabilities(first_frame=True, last_frame=False, reference_images=False)

    async def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        payload = self._build_payload(request)
        logger.info("调用 %s 视频 API model=%s body=%s", self.name, self._model, format_kwargs_for_log(payload))
        async with httpx.AsyncClient(timeout=self._http_timeout) as client:
            task_id = await self._create_task(client, payload)
            await self._persist_provider_job_id(request, task_id, provider=PROVIDER_STREAMLAKE)
            return await self._poll_and_build(client, task_id, request, is_resume=False)

    async def resume_video(self, job_id: str, request: VideoGenerationRequest) -> VideoGenerationResult:
        async with httpx.AsyncClient(timeout=self._http_timeout) as client:
            return await self._poll_and_build(client, job_id, request, is_resume=True)

    def _build_payload(self, request: VideoGenerationRequest) -> dict[str, object]:
        duration = int(request.duration_seconds)
        if not (_MIN_DURATION_SECONDS <= duration <= _MAX_DURATION_SECONDS):
            raise VideoCapabilityError("video_duration_invalid", duration=duration)
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": request.prompt,
            "duration": duration,
            "resolution": (request.resolution or "768P").upper(),
        }
        if request.start_image_url:
            payload["first_frame"] = request.start_image_url
        elif request.start_image:
            path = Path(request.start_image)
            if not path.is_file():
                raise VideoCapabilityError("video_start_image_unreadable", model=self._model, name=path.name)
            try:
                payload["first_frame"] = base64.b64encode(path.read_bytes()).decode("ascii")
            except OSError as exc:
                raise VideoCapabilityError("video_start_image_unreadable", model=self._model, name=path.name) from exc
        if request.seed is not None:
            payload["seed"] = request.seed
        return payload

    @with_retry_async(
        max_attempts=DEFAULT_MAX_ATTEMPTS, backoff_seconds=DEFAULT_BACKOFF_SECONDS, retry_if=should_retry_submit
    )
    async def _create_task(self, client: httpx.AsyncClient, payload: dict[str, object]) -> str:
        resp = await submit_post(
            lambda: client.post(
                f"{self._base_url}{_SUBMIT_PATH}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "X-Ks-Wq-Async": "enable",
                    "Content-Type": "application/json",
                },
            ),
            provider=PROVIDER_STREAMLAKE,
        )
        return extract_streamlake_task_id(resp.json())

    async def _poll_once(self, client: httpx.AsyncClient, task_id: str) -> dict:
        resp = await client.get(
            f"{self._base_url}/endpoints/{self._model}/tasks/{task_id}",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        resp.raise_for_status()
        return resp.json()

    async def _poll_and_build(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        request: VideoGenerationRequest,
        *,
        is_resume: bool,
    ) -> VideoGenerationResult:
        async def _gated_poll() -> dict:
            try:
                return await self._poll_once(client, task_id)
            except httpx.HTTPStatusError as exc:
                if is_resume and exc.response.status_code == 404:
                    raise ResumeExpiredError(job_id=task_id, provider=PROVIDER_STREAMLAKE) from exc
                raise

        final = await poll_with_retry(
            poll_fn=_gated_poll,
            is_done=streamlake_is_done,
            is_failed=streamlake_failure_reason,
            poll_interval=_POLL_INTERVAL_SECONDS,
            max_wait=max(_MIN_POLL_TIMEOUT_SECONDS, request.duration_seconds * _POLL_TIMEOUT_PER_SECOND),
            retry_if=should_retry_poll,
            label="StreamLake",
        )
        video_url = extract_streamlake_video_url(final)
        await self._download_with_retry(video_url, request.output_path)
        return VideoGenerationResult(
            video_path=request.output_path,
            provider=PROVIDER_STREAMLAKE,
            model=self._model,
            duration_seconds=min(max(request.duration_seconds, 1), MAX_BILLED_DURATION_SECONDS),
            video_uri=video_url,
            seed=request.seed,
            task_id=task_id,
        )

    @staticmethod
    @with_retry_async(
        max_attempts=DOWNLOAD_MAX_ATTEMPTS, backoff_seconds=DOWNLOAD_BACKOFF_SECONDS, retry_if=should_retry_download
    )
    async def _download_with_retry(video_url: str, output_path: Path) -> None:
        await download_video(video_url, output_path)
