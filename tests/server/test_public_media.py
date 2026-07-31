"""溪流湖首帧的公开静态 URL 构造。"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from server.auth import verify_media_token
from server.public_media import (
    build_project_file_url,
    build_public_project_file_url,
    build_streamlake_first_frame_url,
)


def test_build_streamlake_first_frame_url_uses_public_domain_and_file_scoped_token(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-for-media-token-32b!")
    monkeypatch.setenv("ARCREEL_PUBLIC_MEDIA_BASE_URL", "https://media.example.com/")
    image = tmp_path / "storyboards" / "首帧 图.png"
    image.parent.mkdir()
    image.write_bytes(b"png")

    url = build_streamlake_first_frame_url(
        image,
        project_path=tmp_path,
        project_name="我的项目",
        user_id="alice-id",
    )

    parsed = urlsplit(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "media.example.com"
    assert (
        parsed.path
        == "/api/v1/files/%E6%88%91%E7%9A%84%E9%A1%B9%E7%9B%AE/storyboards/%E9%A6%96%E5%B8%A7%20%E5%9B%BE.png"
    )
    token = parse_qs(parsed.query)["media_token"][0]
    verify_media_token(
        token,
        user_id="alice-id",
        project_name="我的项目",
        asset_path="storyboards/首帧 图.png",
    )


def test_build_public_project_file_url_uses_same_file_scoped_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-for-media-token-32b!")
    monkeypatch.setenv("ARCREEL_PUBLIC_MEDIA_BASE_URL", "https://media.example.com")
    video = tmp_path / "output" / "episode_1_final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"mp4")

    url = build_public_project_file_url(
        video,
        project_path=tmp_path,
        project_name="demo",
        user_id="alice-id",
    )

    parsed = urlsplit(url)
    assert parsed.netloc == "media.example.com"
    assert parsed.path == "/api/v1/files/demo/output/episode_1_final.mp4"
    verify_media_token(
        parse_qs(parsed.query)["media_token"][0],
        user_id="alice-id",
        project_name="demo",
        asset_path="output/episode_1_final.mp4",
    )


@pytest.mark.unit
def test_build_project_file_url_falls_back_to_same_origin_path(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-for-media-token-32b!")
    monkeypatch.delenv("ARCREEL_PUBLIC_MEDIA_BASE_URL", raising=False)
    video = tmp_path / "output" / "episode_1_final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"mp4")

    url = build_project_file_url(
        video,
        project_path=tmp_path,
        project_name="demo",
        user_id="alice-id",
    )

    parsed = urlsplit(url)
    assert parsed.scheme == ""
    assert parsed.netloc == ""
    assert parsed.path == "/api/v1/files/demo/output/episode_1_final.mp4"
    verify_media_token(
        parse_qs(parsed.query)["media_token"][0],
        user_id="alice-id",
        project_name="demo",
        asset_path="output/episode_1_final.mp4",
    )


@pytest.mark.unit
def test_build_project_file_url_prefers_public_domain_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN_SECRET", "test-secret-for-media-token-32b!")
    monkeypatch.setenv("ARCREEL_PUBLIC_MEDIA_BASE_URL", "https://media.example.com")
    video = tmp_path / "output" / "episode_1_final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"mp4")

    url = build_project_file_url(
        video,
        project_path=tmp_path,
        project_name="demo",
        user_id="alice-id",
    )

    assert urlsplit(url).netloc == "media.example.com"


@pytest.mark.unit
def test_build_project_file_url_rejects_path_outside_project(tmp_path, monkeypatch):
    monkeypatch.delenv("ARCREEL_PUBLIC_MEDIA_BASE_URL", raising=False)
    outside = tmp_path.parent / "outside.mp4"
    outside.write_bytes(b"mp4")

    with pytest.raises(ValueError, match="项目目录"):
        build_project_file_url(outside, project_path=tmp_path, project_name="demo", user_id="alice-id")


@pytest.mark.unit
def test_build_project_file_url_rejects_invalid_configured_media_domain(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCREEL_PUBLIC_MEDIA_BASE_URL", "media.example.com")
    video = tmp_path / "output" / "episode_1_final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"mp4")

    with pytest.raises(ValueError, match="ARCREEL_PUBLIC_MEDIA_BASE_URL"):
        build_project_file_url(video, project_path=tmp_path, project_name="demo", user_id="alice-id")


def test_build_streamlake_first_frame_url_requires_configured_public_domain(tmp_path, monkeypatch):
    monkeypatch.delenv("ARCREEL_PUBLIC_MEDIA_BASE_URL", raising=False)
    image = tmp_path / "first.png"
    image.write_bytes(b"png")

    with pytest.raises(ValueError, match="ARCREEL_PUBLIC_MEDIA_BASE_URL"):
        build_streamlake_first_frame_url(image, project_path=tmp_path, project_name="project", user_id="alice-id")


def test_build_streamlake_first_frame_url_rejects_path_outside_project(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCREEL_PUBLIC_MEDIA_BASE_URL", "https://media.example.com")
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(b"png")

    with pytest.raises(ValueError, match="项目目录"):
        build_streamlake_first_frame_url(outside, project_path=tmp_path, project_name="project", user_id="alice-id")
