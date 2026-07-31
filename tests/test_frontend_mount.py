"""前端构建产物挂载行为测试（server/app.py 的 frontend_dist_dir 分支）。"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import lib
from server import app as app_module


@pytest.fixture
def reload_app_cleanup(monkeypatch: pytest.MonkeyPatch):
    """还原 lib.PROJECT_ROOT 并重新 reload server.app，恢复成真实构建产物路径。

    setup（写 index.html、monkeypatch、reload）仍留在各测试体内——顺序必须是
    先落盘构建产物再 reload，模块顶层的 `if index.html.is_file()` 才能读到预期状态。
    """
    yield
    monkeypatch.undo()
    importlib.reload(app_module)


def _write_dist_shells(dist_dir: Path) -> None:
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.html").write_text("<html>marketing-home</html>", encoding="utf-8")
    (dist_dir / "app.html").write_text("<html>app-shell</html>", encoding="utf-8")


async def test_deep_link_with_extension_falls_back_to_index_html(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """构建产物存在时，带扩展名的 SPA 深链应回退到 app shell 而非被当作静态资源返回 404。"""
    dist_dir = tmp_path / "frontend" / "dist"
    _write_dist_shells(dist_dir)
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/app/projects/demo/source/chapter1.txt")
        assert res.status_code == 200
        assert "app-shell" in res.text


async def test_write_request_to_spa_path_returns_405_not_shell(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """写请求误入 SPA 页面路径（含带扩展名深链与根路径）应返回 405，而非 SPA 外壳。"""
    dist_dir = tmp_path / "frontend" / "dist"
    _write_dist_shells(dist_dir)
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        deep_link_res = await client.put("/app/projects/demo/source/chapter1.txt")
        assert deep_link_res.status_code == 405
        assert "app-shell" not in deep_link_res.text

        root_res = await client.post("/")
        assert root_res.status_code == 405
        assert "marketing-home" not in root_res.text


async def test_real_static_file_under_app_path_is_not_shadowed_by_shell(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """dist/app/ 下若存在真实静态文件，spa_deep_link 应优先返回该文件而非无条件回退到外壳。"""
    dist_dir = tmp_path / "frontend" / "dist"
    (dist_dir / "app").mkdir(parents=True)
    _write_dist_shells(dist_dir)
    (dist_dir / "app" / "logo.png").write_bytes(b"fake-png-bytes")
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/app/logo.png")
        assert res.status_code == 200
        assert res.content == b"fake-png-bytes"


async def test_seo_route_serves_its_prerendered_html(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """公开主题页必须返回自己的静态 HTML，而不是通用 SPA 外壳。"""
    dist_dir = tmp_path / "frontend" / "dist"
    seo_dir = dist_dir / "zh" / "novel-to-video"
    seo_dir.mkdir(parents=True)
    _write_dist_shells(dist_dir)
    (seo_dir / "index.html").write_text("<html>小说转视频静态正文</html>", encoding="utf-8")
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/zh/novel-to-video")
        assert res.status_code == 200
        assert "小说转视频静态正文" in res.text
        assert "app-shell" not in res.text
        assert res.headers["cache-control"] == "public, max-age=300, must-revalidate"

        head_res = await client.head("/zh/novel-to-video")
        assert head_res.status_code == 200


async def test_new_seo_page_is_auto_discovered_without_backend_change(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """dist/{zh,en}/*/index.html 下的新落地页应被启动扫描自动注册，无需硬编码路由。"""
    dist_dir = tmp_path / "frontend" / "dist"
    seo_dir = dist_dir / "en" / "brand-new-guide"
    seo_dir.mkdir(parents=True)
    _write_dist_shells(dist_dir)
    (seo_dir / "index.html").write_text("<html>brand new guide body</html>", encoding="utf-8")
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/en/brand-new-guide")
        assert res.status_code == 200
        assert "brand new guide body" in res.text
        assert "app-shell" not in res.text


async def test_missing_seo_page_returns_404_instead_of_spa_shell(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """下线后的双语专题页不能回退到 200 SPA 外壳，否则搜索引擎仍会视为软 404。"""
    dist_dir = tmp_path / "frontend" / "dist"
    _write_dist_shells(dist_dir)
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/en/ai-video-workflow")
        assert res.status_code == 404
        assert "app-shell" not in res.text
        assert "marketing-home" not in res.text


async def test_unknown_public_url_returns_hard_404(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """普通未知公开路径必须是真实 404，不能落入营销首页或 app shell。"""
    dist_dir = tmp_path / "frontend" / "dist"
    _write_dist_shells(dist_dir)
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in (
            "/definitely-not-a-real-page",
            "/zh/novel-to-video/extra",
            "/en/ai-storyboard-generator/nested",
            "/random/nested/path",
        ):
            res = await client.get(path, headers={"accept": "text/html"})
            assert res.status_code == 404, path
            assert "marketing-home" not in res.text
            assert "app-shell" not in res.text


async def test_trailing_slash_seo_and_auth_redirect_keep_https_relative_location(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """专题页与认证页尾斜杠应 308 到无尾斜杠 canonical，且 Location 为相对路径（不降级 HTTPS）。"""
    dist_dir = tmp_path / "frontend" / "dist"
    seo_dir = dist_dir / "en" / "novel-to-video"
    seo_dir.mkdir(parents=True)
    _write_dist_shells(dist_dir)
    (seo_dir / "index.html").write_text("<html>seo</html>", encoding="utf-8")
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        headers = {"x-forwarded-proto": "https", "accept": "text/html"}
        seo_res = await client.get("/en/novel-to-video/", headers=headers)
        assert seo_res.status_code == 308
        assert seo_res.headers["location"] == "/en/novel-to-video"

        login_res = await client.get("/login/", headers=headers)
        assert login_res.status_code == 308
        assert login_res.headers["location"] == "/login"


async def test_login_register_trailing_slash_variants_are_noindex(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """`/login`、`/register` 及其尾斜杠变体都必须带私有页 noindex。"""
    dist_dir = tmp_path / "frontend" / "dist"
    _write_dist_shells(dist_dir)
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        for path in ("/login", "/register"):
            res = await client.get(path, headers={"accept": "text/html"})
            assert res.status_code == 200, path
            assert res.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
            assert "app-shell" in res.text

        for path in ("/login/", "/register/"):
            res = await client.get(path, headers={"accept": "text/html"})
            assert res.status_code == 308, path
            assert res.headers["x-robots-tag"] == "noindex, nofollow, noarchive"
            assert res.headers["location"] == path.rstrip("/")


async def test_zh_home_and_en_root_alias(reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """`/zh` 返回中文首页；`/en` 永久重定向到 `/`。"""
    dist_dir = tmp_path / "frontend" / "dist"
    (dist_dir / "zh").mkdir(parents=True)
    _write_dist_shells(dist_dir)
    (dist_dir / "zh" / "index.html").write_text("<html>zh-home</html>", encoding="utf-8")
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        zh_res = await client.get("/zh")
        assert zh_res.status_code == 200
        assert "zh-home" in zh_res.text

        en_res = await client.get("/en")
        assert en_res.status_code == 308
        assert en_res.headers["location"] == "/"


async def test_deep_link_path_traversal_falls_back_to_shell(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """_rest 携带 "../" 越界读取时不应逃出构建产物目录，应正常回退到 app shell。"""
    dist_dir = tmp_path / "frontend" / "dist"
    _write_dist_shells(dist_dir)
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret", encoding="utf-8")
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 用 %2e%2e 而非字面 "../"：httpx 会在客户端就地折叠字面 "../"，
        # 必须让 ".." 以编码形式保留到请求行，才能验证服务端（而非客户端）的越界防护。
        # 拼接顺序是 dist/app/<_rest>，需要 3 级 ".." 才能越过 app/、dist/、frontend/
        # 三层目录抵达 tmp_path/secret.txt
        res = await client.get("/app/%2e%2e/%2e%2e/%2e%2e/secret.txt")
        assert res.status_code == 200
        assert "app-shell" in res.text
        assert "top-secret" not in res.text


async def test_missing_index_html_skips_mount_without_crashing(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """构建产物目录缺 index.html 时跳过前端挂载，应用仍能正常启动且 API 不受影响。"""
    dist_dir = tmp_path / "frontend" / "dist"
    dist_dir.mkdir(parents=True)
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/app/anything")
        assert res.status_code == 404


async def test_spa_shell_responses_are_never_cached(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """应用 HTML shell 不能被浏览器缓存；公开营销 HTML 使用短 TTL。"""
    dist_dir = tmp_path / "frontend" / "dist"
    _write_dist_shells(dist_dir)
    assets = dist_dir / "assets"
    assets.mkdir()
    (assets / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        deep_link_res = await client.get("/app/projects/demo/source/chapter1.txt")
        assert deep_link_res.status_code == 200
        assert deep_link_res.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"

        login_res = await client.get("/login", headers={"accept": "text/html"})
        assert login_res.status_code == 200
        assert login_res.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
        assert "app-shell" in login_res.text

        root_res = await client.get("/", headers={"accept": "text/html"})
        assert root_res.status_code == 200
        assert root_res.headers["cache-control"] == "public, max-age=300, must-revalidate"
        assert "marketing-home" in root_res.text

        asset_res = await client.get("/assets/index-abc123.js")
        assert asset_res.status_code == 200
        assert asset_res.headers["cache-control"] == "public, max-age=31536000, immutable"


async def test_private_frontend_routes_are_noindex_and_browser_hardened(
    reload_app_cleanup: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """认证与工作台页面不应进入索引，所有 HTML 入口都应声明浏览器安全边界。"""
    dist_dir = tmp_path / "frontend" / "dist"
    _write_dist_shells(dist_dir)
    monkeypatch.setattr(lib, "PROJECT_ROOT", tmp_path)
    importlib.reload(app_module)

    transport = ASGITransport(app=app_module.app)
    forwarded_https = {"x-forwarded-proto": "https"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.get("/login", headers=forwarded_https)
        projects_res = await client.get("/app/projects", headers=forwarded_https)
        public_res = await client.get("/", headers={**forwarded_https, "accept": "text/html"})

    for response in (login_res, projects_res):
        assert response.status_code == 200
        assert response.headers["x-robots-tag"] == "noindex, nofollow, noarchive"

    assert "x-robots-tag" not in public_res.headers
    for response in (login_res, projects_res, public_res):
        assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert response.headers["permissions-policy"] == "camera=(), geolocation=(), microphone=()"
        assert "form-action 'self'" in response.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert "https://accounts.google.com/gsi/client" in response.headers["content-security-policy"]
        assert "connect-src 'self' https://accounts.google.com/gsi/" in response.headers["content-security-policy"]
        assert "frame-src https://accounts.google.com/gsi/" in response.headers["content-security-policy"]
        assert "https://accounts.google.com/gsi/style" in response.headers["content-security-policy"]
        assert "media-src 'self' data: blob: https:" in response.headers["content-security-policy"]
