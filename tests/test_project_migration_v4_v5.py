"""v4→v5 marketing→ad 存量项目兼容迁移。"""

import json
from pathlib import Path

from lib.project_migrations.v4_to_v5_marketing_to_ad import (
    migrate_project_dict,
    migrate_script_dict,
    migrate_v4_to_v5,
)


def _legacy_script() -> dict:
    return {
        "title": "旧营销短片",
        "content_mode": "marketing",
        "duration_seconds": 8,
        "campaign": {"title": "商品 A", "chapter": "第一版"},
        "ad_units": [
            {
                "unit_id": "E1A1",
                "duration_seconds": 4,
                "segment_break": False,
                "hook": "三秒抓住注意力",
                "voiceover": "现在认识商品 A",
                "cta": None,
                "products_in_unit": ["商品 A"],
                "scenes": ["桌面"],
                "props": [],
                "image_prompt": {"description": "产品特写"},
                "video_prompt": {"action": "推进镜头"},
                "generated_assets": {"storyboard": "completed"},
            },
            {
                "unit_id": "E1A2",
                "duration_seconds": 4,
                "segment_break": True,
                "hook": "",
                "voiceover": "立即体验",
                "cta": "点击购买",
                "products_in_unit": ["商品 A"],
                "scenes": [],
                "props": [],
                "image_prompt": {"description": "结尾卡"},
                "video_prompt": {"action": "定格"},
                "generated_assets": {},
            },
        ],
    }


def test_migrate_project_dict_renames_only_legacy_mode() -> None:
    assert migrate_project_dict({"content_mode": "marketing", "title": "A"}) == {
        "content_mode": "ad",
        "title": "A",
    }
    current = {"content_mode": "drama", "title": "B"}
    assert migrate_project_dict(current) == current


def test_migrate_script_dict_preserves_content_and_asset_state() -> None:
    migrated = migrate_script_dict(_legacy_script())

    assert migrated["content_mode"] == "ad"
    assert "ad_units" not in migrated
    assert "campaign" not in migrated
    assert migrated["novel"] == {"title": "商品 A", "chapter": "第一版"}
    assert migrated["reference_units"] is None
    first, last = migrated["shots"]
    assert first["shot_id"] == "E1A1"
    assert first["section"] == "hook"
    assert first["voiceover_text"] == "现在认识商品 A"
    assert first["products_in_shot"] == ["商品 A"]
    assert first["generated_assets"] == {"storyboard": "completed"}
    assert first["note"] == "旧营销钩子：三秒抓住注意力"
    assert last["section"] == "cta"
    assert last["note"] == "旧营销 CTA：点击购买"


def test_migrate_v4_to_v5_updates_project_and_scripts_idempotently(tmp_path: Path) -> None:
    project_dir = tmp_path / "legacy"
    scripts_dir = project_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    project_path = project_dir / "project.json"
    script_path = scripts_dir / "episode_1.json"
    project_path.write_text(
        json.dumps({"schema_version": 4, "content_mode": "marketing", "title": "旧项目"}),
        encoding="utf-8",
    )
    script_path.write_text(json.dumps(_legacy_script()), encoding="utf-8")

    migrate_v4_to_v5(project_dir)
    once_project = project_path.read_bytes()
    once_script = script_path.read_bytes()
    migrate_v4_to_v5(project_dir)

    project = json.loads(once_project)
    script = json.loads(once_script)
    assert project["schema_version"] == 5
    assert project["content_mode"] == "ad"
    assert script["content_mode"] == "ad"
    assert len(script["shots"]) == 2
    assert project_path.read_bytes() == once_project
    assert script_path.read_bytes() == once_script
