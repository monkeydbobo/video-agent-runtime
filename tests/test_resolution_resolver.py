"""测试 resolve_resolution 按 project → legacy → custom default → None 顺序解析。"""

import pytest

from server.services.resolution_resolver import _from_project, resolve_resolution

# --- 纯项目字典路径（同步即可） ---


def test_from_project_returns_none_when_nothing_configured():
    assert _from_project({}, "gemini-aistudio", "veo-3.1-lite-generate-preview") is None


def test_from_project_legacy_only():
    project = {"video_model_settings": {"veo-3.1": {"resolution": "1080p"}}}
    assert _from_project(project, "gemini-aistudio", "veo-3.1") == "1080p"


def test_from_project_model_settings_overrides_legacy():
    project = {
        "model_settings": {"gemini-aistudio/veo-3.1": {"resolution": "720p"}},
        "video_model_settings": {"veo-3.1": {"resolution": "1080p"}},
    }
    assert _from_project(project, "gemini-aistudio", "veo-3.1") == "720p"


def test_from_project_empty_string_override_treated_as_unset():
    project = {"model_settings": {"p/m": {"resolution": ""}}}
    assert _from_project(project, "p", "m") is None


def test_from_project_composite_key_format_uses_slash():
    project = {"model_settings": {"a/b": {"resolution": "4K"}}}
    assert _from_project(project, "a", "b") == "4K"
    assert _from_project(project, "a-b", "") is None


def test_from_project_tolerates_null_entries():
    # project.json 可能被手编为 null 值；既不应崩也不应当作已配置。
    project = {
        "model_settings": {"a/b": None},
        "video_model_settings": {"m": None},
    }
    assert _from_project(project, "a", "b") is None
    assert _from_project(project, "x", "m") is None


# --- 包含 custom default 的 async 集成路径 ---


@pytest.mark.asyncio
async def test_resolve_returns_none_when_nothing_configured():
    assert await resolve_resolution({}, "ark", "doubao-seedance-1-5-pro-251215") is None


@pytest.mark.asyncio
async def test_resolve_project_override_wins():
    project = {"model_settings": {"ark/m": {"resolution": "2K"}}}
    assert await resolve_resolution(project, "ark", "m") == "2K"


@pytest.mark.asyncio
async def test_resolve_legacy_used_when_no_model_settings():
    project = {"video_model_settings": {"m": {"resolution": "1080p"}}}
    assert await resolve_resolution(project, "ark", "m") == "1080p"
