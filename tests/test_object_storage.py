from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from lib.object_storage import ObjectStorageConfig, ProjectObjectStorage


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


@pytest.mark.parametrize("relative", ["", "/etc/passwd", "../outside.mp4", "output/../outside.mp4"])
def test_rejects_paths_outside_project(storage, relative: str) -> None:
    store, _ = storage
    with pytest.raises(ValueError, match="相对路径"):
        store.object_key(user_id="alice", project_name="demo", relative_path=relative)


def test_partial_environment_configuration_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCREEL_OBJECT_STORAGE_ENDPOINT", "https://storage.example")
    monkeypatch.delenv("ARCREEL_OBJECT_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("ARCREEL_OBJECT_STORAGE_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ARCREEL_OBJECT_STORAGE_SECRET_ACCESS_KEY", raising=False)

    with pytest.raises(RuntimeError, match="配置不完整"):
        ObjectStorageConfig.from_env()
