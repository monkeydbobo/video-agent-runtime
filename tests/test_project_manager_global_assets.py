"""ProjectManager global_assets helper."""

from __future__ import annotations

import pytest

from lib.project_manager import ProjectManager

pytestmark = pytest.mark.integration


def test_get_global_assets_root_creates_subdirs(tmp_path):
    pm = ProjectManager(tmp_path / "projects")
    root = pm.get_global_assets_root()
    # 无 legacy 目录时默认落到 default 用户私有根
    assert root == tmp_path / "projects" / "users" / "default" / "assets"
    for sub in ("character", "scene", "prop"):
        assert (root / sub).is_dir()


def test_get_global_assets_root_legacy_fallback(tmp_path):
    pm = ProjectManager(tmp_path / "projects")
    legacy = pm.projects_root / "_global_assets"
    legacy.mkdir(parents=True)
    assert pm.get_global_assets_root() == legacy


def test_list_projects_skips_global_assets(tmp_path):
    pm = ProjectManager(tmp_path / "projects")
    pm.get_global_assets_root()  # 生成 _global_assets
    (pm.projects_root / "my-project").mkdir()
    assert pm.list_projects() == ["my-project"]


def test_list_projects_skips_filesystem_lost_found(tmp_path):
    """卷文件系统的 lost+found 不是 ArcReel 项目，不能出现在项目列表。"""
    pm = ProjectManager(tmp_path / "projects")
    (pm.projects_root / "lost+found").mkdir()
    (pm.projects_root / "valid-project").mkdir()

    assert pm.list_projects() == ["valid-project"]
