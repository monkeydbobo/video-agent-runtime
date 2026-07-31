"""项目媒体的 S3 兼容对象存储。

Volume 仍是生成与 FFmpeg 的工作盘；本 module 把生成完成的媒体发布到独立对象存储，
并可在本地副本缺失时签发直连下载 URL。调用方无需了解 S3 key、MIME、签名或重试配置。
"""

from __future__ import annotations

import logging
import mimetypes
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

OBJECT_STORAGE_ENV_PREFIX = "ARCREEL_OBJECT_STORAGE_"
DEFAULT_PRESIGN_SECONDS = 300

logger = logging.getLogger(__name__)


class ObjectStorageConfigError(RuntimeError):
    """对象存储环境变量不完整或取值非法。"""


@dataclass(frozen=True)
class ObjectStorageConfig:
    endpoint: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    region: str = "auto"
    prefix: str = "media"
    presign_seconds: int = DEFAULT_PRESIGN_SECONDS

    @classmethod
    def from_env(cls) -> ObjectStorageConfig | None:
        values = {
            "endpoint": os.environ.get(f"{OBJECT_STORAGE_ENV_PREFIX}ENDPOINT", "").strip(),
            "bucket": os.environ.get(f"{OBJECT_STORAGE_ENV_PREFIX}BUCKET", "").strip(),
            "access_key_id": os.environ.get(f"{OBJECT_STORAGE_ENV_PREFIX}ACCESS_KEY_ID", "").strip(),
            "secret_access_key": os.environ.get(f"{OBJECT_STORAGE_ENV_PREFIX}SECRET_ACCESS_KEY", "").strip(),
        }
        if not any(values.values()):
            return None
        missing = [name for name, value in values.items() if not value]
        if missing:
            names = ", ".join(f"{OBJECT_STORAGE_ENV_PREFIX}{name.upper()}" for name in missing)
            raise ObjectStorageConfigError(f"对象存储配置不完整，缺少: {names}")

        raw_seconds = os.environ.get(
            f"{OBJECT_STORAGE_ENV_PREFIX}PRESIGN_SECONDS",
            str(DEFAULT_PRESIGN_SECONDS),
        )
        try:
            presign_seconds = int(raw_seconds)
        except ValueError as exc:
            raise ObjectStorageConfigError(f"{OBJECT_STORAGE_ENV_PREFIX}PRESIGN_SECONDS 必须是整数") from exc
        if not 60 <= presign_seconds <= 604800:
            raise ObjectStorageConfigError(f"{OBJECT_STORAGE_ENV_PREFIX}PRESIGN_SECONDS 必须在 60 到 604800 秒之间")

        return cls(
            **values,
            region=os.environ.get(f"{OBJECT_STORAGE_ENV_PREFIX}REGION", "auto").strip() or "auto",
            prefix=os.environ.get(f"{OBJECT_STORAGE_ENV_PREFIX}PREFIX", "media").strip().strip("/") or "media",
            presign_seconds=presign_seconds,
        )


@dataclass(frozen=True)
class PublishedProjectFile:
    key: str
    uri: str
    size: int


@dataclass(frozen=True)
class StoredProjectFile:
    relative_path: str
    size: int


class ProjectObjectStorage:
    """把项目相对路径映射到私有 S3 object 的深 module。"""

    def __init__(self, config: ObjectStorageConfig, *, client: Any | None = None):
        self.config = config
        self._client = client or boto3.client(
            "s3",
            endpoint_url=config.endpoint,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            region_name=config.region,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 5, "mode": "adaptive"},
                s3={"addressing_style": "virtual"},
            ),
        )

    @staticmethod
    def _relative_path(file_path: Path, project_path: Path) -> str:
        try:
            relative = file_path.resolve().relative_to(project_path.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError("对象存储文件必须位于项目目录内") from exc
        return _validate_relative_path(relative)

    def object_key(self, *, user_id: str, project_name: str, relative_path: str) -> str:
        relative = _validate_relative_path(relative_path)
        return f"{self._project_prefix(user_id=user_id, project_name=project_name)}{relative}"

    def _project_prefix(self, *, user_id: str, project_name: str) -> str:
        encoded_user = quote(user_id, safe="")
        encoded_project = quote(project_name, safe="")
        return f"{self.config.prefix}/users/{encoded_user}/projects/{encoded_project}/"

    def publish_project_file(
        self,
        file_path: Path,
        *,
        project_path: Path,
        project_name: str,
        user_id: str,
    ) -> PublishedProjectFile:
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        relative = self._relative_path(file_path, project_path)
        key = self.object_key(user_id=user_id, project_name=project_name, relative_path=relative)
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self._client.upload_file(
            str(file_path),
            self.config.bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
                "CacheControl": "private, no-store",
            },
        )
        return PublishedProjectFile(
            key=key,
            uri=f"s3://{self.config.bucket}/{key}",
            size=file_path.stat().st_size,
        )

    def project_file_exists(self, *, project_name: str, user_id: str, relative_path: str) -> bool:
        key = self.object_key(user_id=user_id, project_name=project_name, relative_path=relative_path)
        try:
            self._client.head_object(Bucket=self.config.bucket, Key=key)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status == 404:
                return False
            raise
        return True

    def presign_project_file(
        self,
        *,
        project_name: str,
        user_id: str,
        relative_path: str,
        download: bool = False,
    ) -> str:
        relative = _validate_relative_path(relative_path)
        key = self.object_key(user_id=user_id, project_name=project_name, relative_path=relative)
        params: dict[str, str] = {"Bucket": self.config.bucket, "Key": key}
        if download:
            filename = quote(PurePosixPath(relative).name, safe="")
            params["ResponseContentDisposition"] = f"attachment; filename*=UTF-8''{filename}"
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=self.config.presign_seconds,
            )
        )

    def list_project_files(
        self,
        *,
        project_name: str,
        user_id: str,
        subdir: str,
    ) -> list[StoredProjectFile]:
        normalized_subdir = _validate_relative_path(subdir)
        if "/" in normalized_subdir:
            raise ValueError("对象存储列表 subdir 必须是一级目录")
        project_prefix = self._project_prefix(user_id=user_id, project_name=project_name)
        prefix = f"{project_prefix}{normalized_subdir}/"
        continuation_token: str | None = None
        results: list[StoredProjectFile] = []
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": self.config.bucket,
                "Prefix": prefix,
            }
            if continuation_token is not None:
                kwargs["ContinuationToken"] = continuation_token
            response = self._client.list_objects_v2(**kwargs)
            for item in response.get("Contents", []):
                key = str(item.get("Key", ""))
                if not key.startswith(project_prefix):
                    continue
                relative = key[len(project_prefix) :]
                path = PurePosixPath(relative)
                if path.parent.as_posix() != normalized_subdir:
                    continue
                results.append(
                    StoredProjectFile(
                        relative_path=relative,
                        size=int(item.get("Size", 0)),
                    )
                )
            if not response.get("IsTruncated"):
                break
            continuation_token = str(response.get("NextContinuationToken") or "")
            if not continuation_token:
                break
        return sorted(results, key=lambda item: item.relative_path)


def _validate_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("对象存储路径必须是项目内的非空相对路径")
    return path.as_posix()


@lru_cache(maxsize=4)
def _store_for_config(config: ObjectStorageConfig) -> ProjectObjectStorage:
    return ProjectObjectStorage(config)


_reported_config_errors: set[str] = set()


def object_storage_config_error() -> str | None:
    """返回对象存储配置的错误说明；配置完整或完全未配置时返回 ``None``。"""
    try:
        ObjectStorageConfig.from_env()
    except ObjectStorageConfigError as exc:
        return str(exc)
    return None


def get_project_object_storage() -> ProjectObjectStorage | None:
    """返回对象存储句柄；未配置或配置不完整时返回 ``None``。

    配置不完整只让对象存储这一路能力不可用，不应连带打断 Volume 上仍然可用的读写：
    此处降级为 Volume-only 并按错误内容去重记日志，启动期另有一次显式告警。
    """
    try:
        config = ObjectStorageConfig.from_env()
    except ObjectStorageConfigError as exc:
        message = str(exc)
        if message not in _reported_config_errors:
            _reported_config_errors.add(message)
            logger.error("对象存储配置无效，降级为 Volume-only：%s", message)
        return None
    return None if config is None else _store_for_config(config)
