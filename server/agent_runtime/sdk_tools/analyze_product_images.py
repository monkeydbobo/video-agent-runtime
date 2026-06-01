"""MCP tool for marketing product-image content understanding.

将用户上传的商品图（产品图）做多模态内容理解，产出结构化「产品简报」：
- 写 ``drafts/episode_{N}/step0_product_brief.md``
- 合并写 ``source/episode_{N}.txt``（供 generate_overview 与 split-marketing-ad-units 复用）
- 合并写 ``project.json`` 的 ``characters`` 桶：为每个产品设 ``reference_image``，
  供阶段 5 产品三视图生成以图生图渲染（只填缺失、不覆盖已有）。

作者：wanghaobo
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool
from pydantic import BaseModel, Field

from lib.text_backends.base import ImageInput, TextGenerationRequest, TextTaskType
from lib.text_generator import TextGenerator
from server.agent_runtime.sdk_tools._context import ToolContext, tool_error

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMAGES = 8


class _ProductEntry(BaseModel):
    """单个产品的结构化简报条目。"""

    name: str = Field(description="产品名称（简洁、可作为资产名复用）")
    category: str = Field(default="", description="产品品类")
    description: str = Field(default="", description="产品一句话描述")
    selling_points: list[str] = Field(default_factory=list, description="核心卖点列表")
    specs: str = Field(default="", description="关键规格/材质/参数")
    visual_features: str = Field(default="", description="商品图的视觉特征：外形、配色、材质质感")
    image: str = Field(default="", description="该产品对应的商品图路径，必须取自给定的候选图片列表")


class _ProductBrief(BaseModel):
    """商品图内容理解产出的结构化产品简报。"""

    products: list[_ProductEntry] = Field(description="从商品图识别出的产品列表，每张图至少对应一个产品")
    target_audience: str = Field(default="", description="目标受众画像")
    brand_tone: str = Field(default="", description="品牌调性/风格")
    voiceover_direction: str = Field(default="", description="建议的口播方向/卖点铺陈思路")


def _resolve_image_paths(project_path: Path, values: list[str] | None) -> list[Path]:
    """解析商品图路径；未指定时取 product_images/ 下所有图片（按修改时间）。"""
    if values:
        candidates: list[Path] = []
        for v in values:
            cand = Path(v)
            candidates.append(cand if cand.is_absolute() else project_path / cand)
    else:
        img_dir = project_path / "product_images"
        if not img_dir.exists():
            raise FileNotFoundError("product_images/ 目录不存在，请先上传商品图")
        candidates = sorted(
            (p for p in img_dir.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_EXTS),
            key=lambda p: p.stat().st_mtime,
        )

    resolved: list[Path] = []
    project_root = project_path.resolve()
    for cand in candidates:
        path = cand.resolve()
        if not path.is_relative_to(project_root):
            raise ValueError(f"商品图路径超出项目目录: {cand}")
        if not path.is_file():
            raise FileNotFoundError(f"商品图不存在: {path}")
        if path.suffix.lower() not in _IMAGE_EXTS:
            raise ValueError(f"商品图格式不支持: {path.suffix}")
        resolved.append(path)

    if not resolved:
        raise FileNotFoundError("product_images/ 下未找到 .png/.jpg/.jpeg/.webp 商品图")
    return resolved[:_MAX_IMAGES]


def _build_prompt(project: dict[str, Any], image_rels: list[str]) -> str:
    overview = project.get("overview")
    synopsis = overview.get("synopsis", "") if isinstance(overview, dict) else ""
    image_list = "\n".join(f"- {rel}" for rel in image_rels)
    return f"""你是一位资深的电商营销策划，需要基于用户上传的商品图（产品图）做内容理解，输出结构化的「产品简报」。

项目标题：{project.get("title", "")}
项目概述：{synopsis}

候选商品图（每个产品的 image 字段必须从下面这份列表中精确选取一条；多张图各对应一个产品，同一产品的多角度图选其代表图）：
{image_list}

要求：
1. 严格基于图片可见信息与项目概述推断，不虚构图中不存在的功能或参数。
2. 为每个产品给出：name（简洁名称）、category、description、selling_points（3-5 条卖点）、specs、visual_features（外形/配色/材质质感）、image（取自上面的候选路径）。
3. 给出 target_audience、brand_tone、voiceover_direction（建议口播方向）。
4. 仅输出符合 schema 的 JSON，不要包裹 markdown 代码块。"""


def _render_brief_markdown(brief: _ProductBrief) -> str:
    lines: list[str] = ["# 产品简报", ""]
    lines.append("## 受众与调性")
    lines.append(f"- 目标受众：{brief.target_audience or '（待补充）'}")
    lines.append(f"- 品牌调性：{brief.brand_tone or '（待补充）'}")
    lines.append(f"- 口播方向：{brief.voiceover_direction or '（待补充）'}")
    lines.append("")
    lines.append("## 产品清单")
    for idx, p in enumerate(brief.products, start=1):
        lines.append("")
        lines.append(f"### {idx}. {p.name}")
        lines.append(f"- 品类：{p.category or '（未知）'}")
        lines.append(f"- 描述：{p.description or '（未知）'}")
        lines.append(f"- 商品图：{p.image or '（未绑定）'}")
        if p.specs:
            lines.append(f"- 规格：{p.specs}")
        if p.visual_features:
            lines.append(f"- 视觉特征：{p.visual_features}")
        if p.selling_points:
            lines.append("- 核心卖点：")
            lines.extend(f"  - {sp}" for sp in p.selling_points)
    lines.append("")
    return "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        # 去掉首行 ``` 或 ```json 与末行 ```
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    return s.strip()


def _merge_products_into_project(
    pm: Any,
    project_name: str,
    brief: _ProductBrief,
    valid_rels: set[str],
) -> int:
    """把产品合并进 project.json 的 characters 桶，设 reference_image（只填缺失，不覆盖）。"""
    added_or_bound = 0

    def _mutate(project: dict) -> None:
        nonlocal added_or_bound
        characters = project.get("characters")
        if not isinstance(characters, dict):
            characters = {}
            project["characters"] = characters
        for p in brief.products:
            name = (p.name or "").strip()
            if not name:
                continue
            image = p.image if p.image in valid_rels else (next(iter(valid_rels)) if valid_rels else "")
            entry = characters.get(name)
            if not isinstance(entry, dict):
                characters[name] = {
                    "description": p.description or "",
                    "reference_image": image,
                }
                added_or_bound += 1
            elif not entry.get("reference_image") and image:
                entry["reference_image"] = image
                added_or_bound += 1

    pm.update_project(project_name, _mutate)
    return added_or_bound


def analyze_product_images_tool(ctx: ToolContext):
    @tool(
        "analyze_product_images",
        "分析 marketing 项目的商品图（产品图），生成 drafts/episode_N/step0_product_brief.md、"
        "同步写 source/episode_N.txt，并把商品图绑定为各产品的 reference_image。",
        {
            "type": "object",
            "properties": {
                "episode": {"type": "integer", "description": "剧集编号"},
                "image_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "商品图路径（相对项目目录）；不传则取 product_images/ 下全部",
                },
                "dry_run": {"type": "boolean", "description": "仅准备 prompt 与抽图，不调用模型"},
            },
            "required": ["episode"],
        },
    )
    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            episode = int(args["episode"])
            dry_run = bool(args.get("dry_run"))
            project_path = ctx.project_path
            project = ctx.pm.load_project(ctx.project_name)
            if project.get("content_mode") != "marketing":
                raise ValueError("analyze_product_images 仅支持 content_mode=marketing 的项目")

            images = _resolve_image_paths(project_path, args.get("image_paths"))
            image_rels = [p.relative_to(project_path).as_posix() for p in images]
            prompt = _build_prompt(project, image_rels)

            if dry_run:
                return {"content": [{"type": "text", "text": f"DRY RUN — Prompt:\n\n{prompt}"}]}

            generator = await TextGenerator.create(TextTaskType.STYLE_ANALYSIS, project_name=ctx.project_name)
            result = await generator.generate(
                TextGenerationRequest(
                    prompt=prompt,
                    images=[ImageInput(path=p) for p in images],
                    response_schema=_ProductBrief,
                    max_output_tokens=8000,
                ),
                project_name=ctx.project_name,
            )
            brief = _ProductBrief.model_validate_json(_strip_code_fence(result.text))

            brief_md = _render_brief_markdown(brief)

            # 1) drafts/episode_{N}/step0_product_brief.md
            drafts_dir = project_path / "drafts" / f"episode_{episode}"
            drafts_dir.mkdir(parents=True, exist_ok=True)
            brief_path = drafts_dir / "step0_product_brief.md"
            brief_path.write_text(brief_md, encoding="utf-8")

            # 2) source/episode_{N}.txt（合并：已存在则追加，避免覆盖用户手写简报）
            source_dir = project_path / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            source_path = source_dir / f"episode_{episode}.txt"
            if source_path.exists():
                existing = source_path.read_text(encoding="utf-8")
                if brief_md.strip() not in existing:
                    source_path.write_text(f"{existing.rstrip()}\n\n---\n\n{brief_md}", encoding="utf-8")
            else:
                source_path.write_text(brief_md, encoding="utf-8")

            # 3) project.json characters 桶绑定 reference_image
            bound = _merge_products_into_project(ctx.pm, ctx.project_name, brief, set(image_rels))

            brief_rel = brief_path.relative_to(project_path).as_posix()
            source_rel = source_path.relative_to(project_path).as_posix()
            text = (
                "✅ 商品图内容理解完成\n"
                f"商品图：{len(image_rels)} 张\n"
                f"识别产品：{len(brief.products)} 个（绑定参考图 {bound} 个）\n"
                f"产品简报：{brief_rel}\n"
                f"源文件：{source_rel}"
            )
            return {
                "content": [{"type": "text", "text": text}],
                "brief_path": brief_rel,
                "source_path": source_rel,
                "image_count": len(image_rels),
                "product_count": len(brief.products),
                "products": json.loads(brief.model_dump_json())["products"],
            }
        except Exception as exc:  # noqa: BLE001
            return tool_error("analyze_product_images", exc)

    return _handler
