from pathlib import Path

import pytest

from lib import object_storage
from server.media_publishing import publish_project_file


@pytest.fixture
def project_video(tmp_path: Path) -> Path:
    video = tmp_path / "output" / "第1集_final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"video")
    return video


@pytest.mark.parametrize("required", [False, True])
async def test_partial_object_storage_config_keeps_generation_alive(
    project_video: Path,
    monkeypatch: pytest.MonkeyPatch,
    required: bool,
) -> None:
    monkeypatch.setenv("ARCREEL_OBJECT_STORAGE_ENDPOINT", "https://storage.example")
    for name in ("BUCKET", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY"):
        monkeypatch.delenv(f"ARCREEL_OBJECT_STORAGE_{name}", raising=False)
    object_storage._reported_config_errors.clear()

    published = await publish_project_file(
        project_video,
        project_path=project_video.parent.parent,
        project_name="demo",
        user_id="alice",
        required=required,
    )

    assert published is None


async def test_upload_failure_only_propagates_when_required(
    project_video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingStore:
        def publish_project_file(self, *_args, **_kwargs):
            raise RuntimeError("bucket 暂时不可用")

    monkeypatch.setattr("server.media_publishing.get_project_object_storage", lambda: _FailingStore())

    assert (
        await publish_project_file(
            project_video,
            project_path=project_video.parent.parent,
            project_name="demo",
            user_id="alice",
        )
        is None
    )

    with pytest.raises(RuntimeError, match="bucket"):
        await publish_project_file(
            project_video,
            project_path=project_video.parent.parent,
            project_name="demo",
            user_id="alice",
            required=True,
        )
