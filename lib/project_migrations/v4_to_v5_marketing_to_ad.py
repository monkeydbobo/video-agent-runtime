"""v4→v5 迁移：把实验期 ``marketing`` 项目归一化为正式 ``ad`` 模式。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.json_io import atomic_write_json, load_json


def _nonempty_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _legacy_note(unit: dict[str, Any]) -> str | None:
    """把 ad 新模型不再接收的营销字段保存在备注中，避免迁移丢文案。"""
    parts: list[str] = []
    existing = _nonempty_text(unit.get("note"))
    if existing:
        parts.append(existing)
    hook = _nonempty_text(unit.get("hook"))
    if hook:
        parts.append(f"旧营销钩子：{hook}")
    cta = _nonempty_text(unit.get("cta"))
    if cta:
        parts.append(f"旧营销 CTA：{cta}")
    return "\n".join(parts) or None


def _migrate_unit(unit: dict[str, Any], *, index: int, total: int) -> dict[str, Any]:
    """将一个 ``ad_units[]`` 条目转换为 ``shots[]``，保留所有可复用素材状态。"""
    voiceover = _nonempty_text(unit.get("voiceover"))
    hook = _nonempty_text(unit.get("hook"))
    cta = _nonempty_text(unit.get("cta"))
    if index == 0 and hook:
        section = "hook"
    elif index == total - 1 and cta:
        section = "cta"
    else:
        section = "selling_point"

    migrated = {
        "shot_id": unit.get("unit_id"),
        "section": section,
        "duration_seconds": unit.get("duration_seconds"),
        "voiceover_text": voiceover or hook or cta,
        "characters_in_shot": unit.get("characters_in_shot", []),
        "scenes": unit.get("scenes", []),
        "props": unit.get("props", []),
        "products_in_shot": unit.get("products_in_unit", []),
        "image_prompt": unit.get("image_prompt"),
        "video_prompt": unit.get("video_prompt"),
        "transition_to_next": unit.get("transition_to_next", "cut"),
        "note": _legacy_note(unit),
        "generated_assets": unit.get("generated_assets", {}),
    }
    return migrated


def migrate_script_dict(script: dict[str, Any]) -> dict[str, Any]:
    """把旧 marketing 剧本转换为 ad 剧本；非目标或已迁移数据原样返回。"""
    if script.get("content_mode") != "marketing" and "ad_units" not in script:
        return dict(script)

    data = dict(script)
    raw_units = data.pop("ad_units", [])
    if not isinstance(raw_units, list) or not all(isinstance(unit, dict) for unit in raw_units):
        raise ValueError("legacy marketing script field 'ad_units' must be a list of objects")
    units: list[dict[str, Any]] = raw_units
    data["content_mode"] = "ad"
    data["shots"] = [_migrate_unit(unit, index=index, total=len(units)) for index, unit in enumerate(units)]
    campaign = data.pop("campaign", None)
    if "novel" not in data and isinstance(campaign, dict):
        data["novel"] = {
            "title": campaign.get("title", ""),
            "chapter": campaign.get("chapter", ""),
        }
    data.setdefault("reference_units", None)
    return data


def migrate_project_dict(project: dict[str, Any]) -> dict[str, Any]:
    """将项目级旧模式名改为正式名称；其余字段保持不变。"""
    data = dict(project)
    if data.get("content_mode") == "marketing":
        data["content_mode"] = "ad"
    return data


def migrate_v4_to_v5(project_dir: Path) -> None:
    """迁移项目元数据及已有剧本；全部写入均为原子替换，可安全重试。"""
    pj = project_dir / "project.json"
    if not pj.exists():
        return
    project = load_json(pj)
    if int(project.get("schema_version") or 0) >= 5:
        return

    scripts_dir = project_dir / "scripts"
    if scripts_dir.is_dir():
        for script_path in sorted(scripts_dir.rglob("*.json")):
            script = load_json(script_path)
            migrated_script = migrate_script_dict(script)
            if migrated_script != script:
                atomic_write_json(script_path, migrated_script)

    migrated_project = migrate_project_dict(project)
    migrated_project["schema_version"] = 5
    atomic_write_json(pj, migrated_project)
