"""供外部媒体供应商读取项目文件的短时公开 URL。"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

from server.auth import create_media_token

PUBLIC_MEDIA_BASE_URL_ENV = "ARCREEL_PUBLIC_MEDIA_BASE_URL"


def _public_media_base_url() -> str:
    value = os.environ.get(PUBLIC_MEDIA_BASE_URL_ENV, "").strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        raise ValueError(f"必须配置有效的 {PUBLIC_MEDIA_BASE_URL_ENV}（例如 https://media.example.com）")
    return value


def _scoped_media_path(
    file_path: Path,
    *,
    project_path: Path,
    project_name: str,
    user_id: str,
) -> str:
    """返回文件级 media_token 的同源路径（不含域名）。"""
    try:
        relative_path = file_path.resolve().relative_to(project_path.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("文件必须位于项目目录内，无法生成公开静态 URL") from exc

    token = create_media_token(
        user_id,
        project_name=project_name,
        asset_path=relative_path,
    )
    encoded_project = quote(project_name, safe="")
    encoded_path = quote(relative_path, safe="/")
    return f"/api/v1/files/{encoded_project}/{encoded_path}?{urlencode({'media_token': token})}"


def build_public_project_file_url(
    file_path: Path,
    *,
    project_path: Path,
    project_name: str,
    user_id: str,
) -> str:
    """返回仅允许读取一个项目文件的短时 CDN URL；未配置公开媒体域名时抛错。"""
    base = _public_media_base_url()
    return base + _scoped_media_path(
        file_path,
        project_path=project_path,
        project_name=project_name,
        user_id=user_id,
    )


def build_project_file_url(
    file_path: Path,
    *,
    project_path: Path,
    project_name: str,
    user_id: str,
) -> str:
    """返回可供浏览器打开的短时链接。

    配置了公开媒体域名时走 CDN 绝对地址；未配置时回退为同源相对地址，
    避免只用同源 ``/api/v1/files/...`` 的部署无法下载。
    """
    try:
        base = _public_media_base_url()
    except ValueError:
        base = ""
    return base + _scoped_media_path(
        file_path,
        project_path=project_path,
        project_name=project_name,
        user_id=user_id,
    )


def build_streamlake_first_frame_url(
    image_path: Path,
    *,
    project_path: Path,
    project_name: str,
    user_id: str,
) -> str:
    """兼容溪流湖首帧调用的项目文件短时 URL 构造器。"""
    return build_public_project_file_url(
        image_path,
        project_path=project_path,
        project_name=project_name,
        user_id=user_id,
    )
