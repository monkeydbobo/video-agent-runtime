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


def build_streamlake_first_frame_url(
    image_path: Path,
    *,
    project_path: Path,
    project_name: str,
    user_id: str,
) -> str:
    """返回仅允许读取一张项目内首帧的外部可访问 URL。"""
    try:
        relative_path = image_path.resolve().relative_to(project_path.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("溪流湖首帧必须位于项目目录内，无法生成公开静态 URL") from exc

    token = create_media_token(
        user_id,
        project_name=project_name,
        asset_path=relative_path,
    )
    encoded_project = quote(project_name, safe="")
    encoded_path = quote(relative_path, safe="/")
    return (
        f"{_public_media_base_url()}/api/v1/files/{encoded_project}/{encoded_path}?{urlencode({'media_token': token})}"
    )
