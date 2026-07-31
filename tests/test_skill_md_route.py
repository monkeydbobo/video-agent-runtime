"""GET /skill.md 模板渲染：BASE_URL + BRAND_NAME 占位符。

Author: wanghaobo
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

import server.app as app_module


def _make_request(*, host: str = "oioi.bio", scheme: str = "https", forwarded_proto: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = [(b"host", host.encode("ascii"))]
    if forwarded_proto is not None:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode("ascii")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": scheme,
        "path": "/skill.md",
        "raw_path": b"/skill.md",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": (host, 443 if scheme == "https" else 80),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_serve_skill_md_replaces_base_url_and_default_brand(tmp_path, monkeypatch):
    public = tmp_path / "public"
    public.mkdir()
    (public / "skill.md.template").write_text(
        "# {{BRAND_NAME}} Skill\nBASE={{BASE_URL}}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("BRAND_NAME", raising=False)

    response = await app_module.serve_skill_md(_make_request())

    assert response.status_code == 200
    body = response.body.decode("utf-8")
    assert "{{BASE_URL}}" not in body
    assert "{{BRAND_NAME}}" not in body
    assert body.startswith("# oioi.bio Skill\n")
    assert "BASE=https://oioi.bio\n" in body
    assert "ArcReel" not in body


@pytest.mark.asyncio
async def test_serve_skill_md_brand_name_env_override(tmp_path, monkeypatch):
    public = tmp_path / "public"
    public.mkdir()
    (public / "skill.md.template").write_text(
        "Hello {{BRAND_NAME}} at {{BASE_URL}}",
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("BRAND_NAME", "  MyBrand  ")

    response = await app_module.serve_skill_md(
        _make_request(host="192.168.1.100:1241", scheme="http", forwarded_proto="http")
    )

    body = response.body.decode("utf-8")
    assert body == "Hello MyBrand at http://192.168.1.100:1241"


@pytest.mark.asyncio
async def test_serve_skill_md_missing_template(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "PROJECT_ROOT", tmp_path)

    response = await app_module.serve_skill_md(_make_request())

    assert response.status_code == 404


def test_repo_skill_template_has_no_hardcoded_arcreel_brand():
    """仓库模板不得把上游仓库名硬编码为产品品牌。"""
    template = (app_module.PROJECT_ROOT / "public" / "skill.md.template").read_text(encoding="utf-8")
    assert "{{BRAND_NAME}}" in template
    assert "{{BASE_URL}}" in template
    assert "ArcReel" not in template
