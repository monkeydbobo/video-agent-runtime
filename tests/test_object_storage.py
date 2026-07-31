import logging
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from lib import object_storage
from lib.object_storage import (
    ObjectStorageConfig,
    ObjectStorageConfigError,
    ProjectObjectStorage,
    get_project_object_storage,
    object_storage_config_error,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, str, dict]] = []
        self.objects: set[str] = set()

    def upload_file(self, filename: str, bucket: str, key: str, ExtraArgs: dict) -> None:
        self.uploads.append((filename, bucket, key, ExtraArgs))
        self.objects.add(key)

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        if Key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadObject",
            )
        return {}

    def generate_presigned_url(self, operation: str, *, Params: dict, ExpiresIn: int) -> str:
        return f"https://storage.example/{Params['Key']}?op={operation}&expires={ExpiresIn}"

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None) -> dict:
        del Bucket, ContinuationToken
        return {
            "IsTruncated": False,
            "Contents": [{"Key": key, "Size": 5} for key in sorted(self.objects) if key.startswith(Prefix)],
        }


@pytest.fixture
def storage() -> tuple[ProjectObjectStorage, FakeS3Client]:
    client = FakeS3Client()
    config = ObjectStorageConfig(
        endpoint="https://storage.example",
        bucket="arcreel-media",
        access_key_id="key",
        secret_access_key="secret",
    )
    return ProjectObjectStorage(config, client=client), client


def test_publish_project_file_hides_key_and_upload_details(storage, tmp_path: Path) -> None:
    store, client = storage
    video = tmp_path / "output" / "第1集 final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"video")

    result = store.publish_project_file(
        video,
        project_path=tmp_path,
        project_name="我的项目",
        user_id="alice/id",
    )

    assert result.key == "media/users/alice%2Fid/projects/%E6%88%91%E7%9A%84%E9%A1%B9%E7%9B%AE/output/第1集 final.mp4"
    assert result.uri == f"s3://arcreel-media/{result.key}"
    assert result.size == 5
    assert client.uploads[0][3]["ContentType"] == "video/mp4"
    assert client.uploads[0][3]["CacheControl"] == "private, no-store"


def test_exists_and_presign_use_same_deterministic_key(storage, tmp_path: Path) -> None:
    store, _ = storage
    video = tmp_path / "videos" / "scene_E1S01.mp4"
    video.parent.mkdir()
    video.write_bytes(b"video")
    store.publish_project_file(video, project_path=tmp_path, project_name="demo", user_id="alice")

    assert store.project_file_exists(
        project_name="demo",
        user_id="alice",
        relative_path="videos/scene_E1S01.mp4",
    )
    assert "media/users/alice/projects/demo/videos/scene_E1S01.mp4" in store.presign_project_file(
        project_name="demo",
        user_id="alice",
        relative_path="videos/scene_E1S01.mp4",
    )
    listed = store.list_project_files(project_name="demo", user_id="alice", subdir="videos")
    assert [(item.relative_path, item.size) for item in listed] == [("videos/scene_E1S01.mp4", 5)]


@pytest.mark.unit
def test_resolve_static_asset_hides_bucket_key_and_signing_details(storage) -> None:
    store, client = storage
    client.objects.add("media/assets/oioi_demo_oioi_bio.mp4")

    result = store.resolve_static_asset("oioi_demo_oioi_bio.mp4")

    assert result is not None
    assert result.relative_path == "oioi_demo_oioi_bio.mp4"
    assert result.url == ("https://storage.example/media/assets/oioi_demo_oioi_bio.mp4?op=get_object&expires=300")
    assert store.resolve_static_asset("missing.mp4") is None


@pytest.mark.unit
@pytest.mark.parametrize("relative", ["", "/etc/passwd", "../outside.mp4", "clips/../outside.mp4"])
def test_resolve_static_asset_rejects_paths_outside_assets_prefix(storage, relative: str) -> None:
    store, _ = storage

    with pytest.raises(ValueError, match="相对路径"):
        store.resolve_static_asset(relative)


@pytest.mark.parametrize("relative", ["", "/etc/passwd", "../outside.mp4", "output/../outside.mp4"])
def test_rejects_paths_outside_project(storage, relative: str) -> None:
    store, _ = storage
    with pytest.raises(ValueError, match="相对路径"):
        store.object_key(user_id="alice", project_name="demo", relative_path=relative)


@pytest.fixture
def partial_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCREEL_OBJECT_STORAGE_ENDPOINT", "https://storage.example")
    monkeypatch.delenv("ARCREEL_OBJECT_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("ARCREEL_OBJECT_STORAGE_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ARCREEL_OBJECT_STORAGE_SECRET_ACCESS_KEY", raising=False)
    object_storage._reported_config_errors.clear()


def test_partial_environment_configuration_fails_loudly(partial_env) -> None:
    with pytest.raises(ObjectStorageConfigError, match="配置不完整"):
        ObjectStorageConfig.from_env()

    assert "ARCREEL_OBJECT_STORAGE_BUCKET" in (object_storage_config_error() or "")


def test_partial_configuration_degrades_to_volume_only(partial_env, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="lib.object_storage"):
        assert get_project_object_storage() is None
        assert get_project_object_storage() is None

    # 每个请求都会取一次 store，重复的配置错误不能刷屏日志
    messages = [record.message for record in caplog.records if "Volume-only" in record.getMessage()]
    assert len(messages) == 1


def test_unconfigured_environment_returns_no_store(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ENDPOINT", "BUCKET", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY"):
        monkeypatch.delenv(f"ARCREEL_OBJECT_STORAGE_{name}", raising=False)

    assert get_project_object_storage() is None
    assert object_storage_config_error() is None
