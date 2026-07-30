"""StreamLake 视频后端单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.providers import PROVIDER_STREAMLAKE
from lib.video_backends.base import VideoCapability, VideoCapabilityError, VideoGenerationRequest
from lib.video_backends.streamlake import StreamLakeVideoBackend


def _response(body: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = body
    response.raise_for_status = MagicMock()
    return response


async def _fake_download(_url: str, output_path: Path, *, timeout: int = 120) -> None:
    del timeout
    output_path.write_bytes(b"mp4")


def _client(post: MagicMock, get: MagicMock) -> AsyncMock:
    client = AsyncMock()
    client.post = AsyncMock(return_value=post)
    client.get = AsyncMock(return_value=get)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


async def test_streamlake_builds_configurable_model_and_polls(tmp_path: Path) -> None:
    post = _response({"data": {"task_id": "task-1", "task_status": "PENDING"}})
    get = _response({"data": {"task_status": "SUCCESS", "content": [{"url": "https://cdn/video.mp4"}]}})
    client = _client(post, get)
    output = tmp_path / "video.mp4"

    with (
        patch("httpx.AsyncClient", return_value=client),
        patch("lib.video_backends.streamlake._POLL_INTERVAL_SECONDS", 0),
        patch("lib.video_backends.streamlake.download_video", new=_fake_download),
    ):
        backend = StreamLakeVideoBackend(api_key="wq-key", model="ep-custom", base_url="https://streamlake.test/v1")
        result = await backend.generate(
            VideoGenerationRequest(
                prompt="咖啡冒热气",
                output_path=output,
                duration_seconds=6,
                resolution="768p",
            )
        )

    assert result.provider == PROVIDER_STREAMLAKE
    assert result.model == "ep-custom"
    assert result.task_id == "task-1"
    assert output.read_bytes() == b"mp4"
    assert client.post.call_args.args[0] == "https://streamlake.test/v1/videos/generations"
    assert client.post.call_args.kwargs["headers"]["X-Ks-Wq-Async"] == "enable"
    assert client.post.call_args.kwargs["json"] == {
        "model": "ep-custom",
        "prompt": "咖啡冒热气",
        "duration": 6,
        "resolution": "768P",
    }
    assert client.get.call_args.args[0] == "https://streamlake.test/v1/endpoints/ep-custom/tasks/task-1"


def test_streamlake_capabilities_and_base64_first_frame(tmp_path: Path) -> None:
    backend = StreamLakeVideoBackend(api_key="key", model="ep-custom")
    assert VideoCapability.TEXT_TO_VIDEO in backend.capabilities
    assert VideoCapability.IMAGE_TO_VIDEO in backend.capabilities
    assert backend.video_capabilities.reference_images is False

    image = tmp_path / "first.png"
    image.write_bytes(b"png-bytes")
    payload = backend._build_payload(
        VideoGenerationRequest(
            prompt="p",
            output_path=tmp_path / "o.mp4",
            duration_seconds=3,
            start_image=image,
        )
    )
    assert payload["first_frame"] == "cG5nLWJ5dGVz"


def test_streamlake_rejects_missing_first_frame(tmp_path: Path) -> None:
    backend = StreamLakeVideoBackend(api_key="key")

    with pytest.raises(VideoCapabilityError) as exc_info:
        backend._build_payload(
            VideoGenerationRequest(
                prompt="p", output_path=tmp_path / "o.mp4", start_image=tmp_path / "missing.png", duration_seconds=3
            )
        )
    assert exc_info.value.code == "video_start_image_unreadable"
