"""AtlasCloudImageBackend 单元测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lib.atlascloud_shared import ATLASCLOUD_MODEL_I2I, ATLASCLOUD_MODEL_T2I
from lib.image_backends.base import ImageCapability, ImageGenerationRequest, ReferenceImage
from lib.providers import PROVIDER_ATLASCLOUD


def _generate_response(*, poll_url: str | None = None, prediction_id: str | None = "pred-1"):
    data: dict = {}
    if poll_url:
        data["urls"] = {"get": poll_url}
    if prediction_id:
        data["id"] = prediction_id
    return {"code": 200, "data": data}


def _completed_response(image_url: str = "https://cdn.example.com/out.jpg"):
    return {
        "code": 200,
        "data": {"status": "completed", "outputs": [image_url]},
    }


class TestAtlasCloudImageBackendInit:
    def test_requires_api_key(self):
        from lib.image_backends.atlascloud import AtlasCloudImageBackend

        with pytest.raises(ValueError, match="api_key"):
            AtlasCloudImageBackend(api_key=None)

    def test_name_and_capabilities(self):
        from lib.image_backends.atlascloud import AtlasCloudImageBackend

        backend = AtlasCloudImageBackend(api_key="test-key")
        assert backend.name == PROVIDER_ATLASCLOUD
        assert backend.model == "gpt-image-2"
        assert ImageCapability.TEXT_TO_IMAGE in backend.capabilities
        assert ImageCapability.IMAGE_TO_IMAGE in backend.capabilities


class TestAtlasCloudImageBackendGenerate:
    async def test_text_to_image_uses_urls_get_poll(self, tmp_path: Path):
        from lib.image_backends.atlascloud import AtlasCloudImageBackend

        backend = AtlasCloudImageBackend(api_key="test-key")
        output_path = tmp_path / "out.jpg"
        request = ImageGenerationRequest(
            prompt="sunset",
            output_path=output_path,
            aspect_ratio="9:16",
            image_size="1K",
        )

        mock_client = AsyncMock()
        post_resp = MagicMock()
        post_resp.raise_for_status = MagicMock()
        post_resp.json.return_value = _generate_response(poll_url="https://api.atlascloud.ai/poll/abc")
        get_resp = MagicMock()
        get_resp.raise_for_status = MagicMock()
        get_resp.json.return_value = _completed_response()
        mock_client.post = AsyncMock(return_value=post_resp)
        mock_client.get = AsyncMock(return_value=get_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("lib.image_backends.atlascloud.httpx.AsyncClient", return_value=mock_client),
            patch(
                "lib.image_backends.atlascloud.download_image_to_path",
                new_callable=AsyncMock,
            ) as mock_download,
            patch("lib.image_backends.atlascloud.poll_with_retry", new_callable=AsyncMock) as mock_poll,
        ):
            mock_poll.return_value = {"status": "completed", "outputs": ["https://cdn.example.com/out.jpg"]}
            result = await backend.generate(request)

        assert result.provider == PROVIDER_ATLASCLOUD
        assert result.image_path == output_path
        post_json = mock_client.post.await_args.kwargs["json"]
        assert post_json["model"] == ATLASCLOUD_MODEL_T2I
        assert post_json["prompt"] == "sunset"
        assert post_json["size"] == "1024x1792"
        assert post_json["quality"] == "medium"
        mock_poll.assert_awaited_once()
        mock_download.assert_awaited_once()

    async def test_image_to_image_uploads_refs(self, tmp_path: Path):
        from lib.image_backends.atlascloud import AtlasCloudImageBackend

        ref_path = tmp_path / "ref.png"
        ref_path.write_bytes(b"png")
        backend = AtlasCloudImageBackend(api_key="test-key")
        output_path = tmp_path / "out.jpg"
        request = ImageGenerationRequest(
            prompt="edit colors",
            output_path=output_path,
            reference_images=[ReferenceImage(path=str(ref_path))],
        )

        mock_client = AsyncMock()
        upload_resp = MagicMock()
        upload_resp.raise_for_status = MagicMock()
        upload_resp.json.return_value = {
            "code": 200,
            "data": {"download_url": "https://cdn.example.com/ref.jpg"},
        }
        gen_resp = MagicMock()
        gen_resp.raise_for_status = MagicMock()
        gen_resp.json.return_value = _generate_response(prediction_id="pred-99", poll_url=None)
        mock_client.post = AsyncMock(side_effect=[upload_resp, gen_resp])
        mock_client.get = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("lib.image_backends.atlascloud.httpx.AsyncClient", return_value=mock_client),
            patch(
                "lib.image_backends.atlascloud.download_image_to_path",
                new_callable=AsyncMock,
            ),
            patch("lib.image_backends.atlascloud.poll_with_retry", new_callable=AsyncMock) as mock_poll,
        ):
            mock_poll.return_value = {"status": "completed", "outputs": ["https://cdn.example.com/out.jpg"]}
            await backend.generate(request)

        assert mock_client.post.await_count == 2
        gen_json = mock_client.post.await_args_list[1].kwargs["json"]
        assert gen_json["model"] == ATLASCLOUD_MODEL_I2I
        assert gen_json["images"] == ["https://cdn.example.com/ref.jpg"]
        mock_poll.assert_awaited_once()

    async def test_failed_prediction_raises(self, tmp_path: Path):
        from lib.image_backends.atlascloud import AtlasCloudImageBackend

        backend = AtlasCloudImageBackend(api_key="test-key")
        request = ImageGenerationRequest(prompt="x", output_path=tmp_path / "o.jpg")

        mock_client = AsyncMock()
        post_resp = MagicMock()
        post_resp.raise_for_status = MagicMock()
        post_resp.json.return_value = _generate_response(poll_url="https://poll")
        mock_client.post = AsyncMock(return_value=post_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        async def _fake_poll(**kwargs):
            is_failed = kwargs["is_failed"]
            err = is_failed({"status": "failed", "error": "content policy"})
            if err:
                raise RuntimeError(err)
            return {}

        with (
            patch("lib.image_backends.atlascloud.httpx.AsyncClient", return_value=mock_client),
            patch("lib.image_backends.atlascloud.poll_with_retry", side_effect=_fake_poll),
        ):
            with pytest.raises(RuntimeError, match="content policy"):
                await backend.generate(request)


class TestAtlasCloudHelpers:
    def test_extract_poll_url_prefers_urls_get(self):
        from lib.image_backends.atlascloud import _extract_poll_url

        url = _extract_poll_url(
            "https://api.atlascloud.ai/api/v1",
            {"data": {"urls": {"get": "https://poll/1"}, "id": "x"}},
        )
        assert url == "https://poll/1"

    def test_extract_poll_url_falls_back_to_prediction_id(self):
        from lib.image_backends.atlascloud import _extract_poll_url

        url = _extract_poll_url(
            "https://api.atlascloud.ai/api/v1",
            {"data": {"id": "pred-42"}},
        )
        assert url.endswith("/model/prediction/pred-42")
