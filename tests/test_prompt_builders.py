from lib.prompt_builders import (
    append_video_negative_tail,
    build_character_prompt,
    build_product_prompt,
    build_prop_prompt,
    build_scene_prompt,
    build_storyboard_suffix,
)
from lib.prompt_builders_script import build_marketing_prompt


class TestCharacterPrompt:
    def test_includes_name_description_and_quad_layout(self):
        prompt = build_character_prompt(
            "姜月茴",
            "黑发，冷静神态。",
            style="古风",
            style_description="Cinematic, low-key lighting",
        )
        assert "姜月茴" in prompt
        assert "黑发，冷静神态。" in prompt
        # 四视图 16:9 布局（issue #353）
        assert "16:9" in prompt
        assert "四格" in prompt
        assert "胸像特写" in prompt or "胸部以上" in prompt
        assert "正面" in prompt and "侧面" in prompt and "背面" in prompt
        # 风格前缀
        assert "古风" in prompt
        assert "Cinematic, low-key lighting" in prompt
        # 反向提示尾部
        assert "画面避免" in prompt

    def test_no_negative_prompt_field_returned(self):
        # build_character_prompt 仅返回字符串；反向提示已 inline 到末尾
        prompt = build_character_prompt("张三", "短发青年")
        assert isinstance(prompt, str)
        assert "画面避免" in prompt
        assert "水印" in prompt


class TestProductPrompt:
    def test_product_three_views(self):
        prompt = build_product_prompt("智能手表", "圆形表盘，金属表带")
        assert "智能手表" in prompt
        assert "圆形表盘" in prompt
        assert "三视图" in prompt or "多视角" in prompt
        assert "画面避免" in prompt


class TestScenePromptAndPropPrompt:
    def test_prop_three_views(self):
        prompt = build_prop_prompt("玉佩", "古朴温润")
        assert "玉佩" in prompt
        assert "古朴温润" in prompt
        assert "三视图" in prompt or "三个视图" in prompt
        assert "画面避免" in prompt

    def test_scene_main_detail_layout(self):
        prompt = build_scene_prompt("祠堂", "昏暗古朴")
        assert "祠堂" in prompt
        assert "昏暗古朴" in prompt
        assert "主画面" in prompt
        assert "画面避免" in prompt


class TestStoryboardSuffix:
    def test_by_aspect_ratio(self):
        assert build_storyboard_suffix(aspect_ratio="9:16") == "竖屏构图。"
        assert build_storyboard_suffix(aspect_ratio="16:9") == "横屏构图。"
        # 向后兼容：不传 aspect_ratio 时默认按 narration → 竖屏
        assert build_storyboard_suffix() == "竖屏构图。"
        assert build_storyboard_suffix(content_mode="marketing") == "竖屏构图。"


class TestVideoNegativeTail:
    def test_appends_when_missing(self):
        result = append_video_negative_tail("林清缓缓抬头")
        assert "林清缓缓抬头" in result
        assert "BGM" in result

    def test_idempotent(self):
        once = append_video_negative_tail("林清缓缓抬头")
        twice = append_video_negative_tail(once)
        assert once == twice

    def test_handles_empty_input(self):
        result = append_video_negative_tail("")
        assert "BGM" in result

    def test_handles_whitespace_only_input(self):
        # 纯空白等同空：避免拼出前导空行 + 尾词的怪异输出
        for blank in ("   ", "\n\n", "\t \n"):
            result = append_video_negative_tail(blank)
            assert result.startswith("禁止出现"), f"input={blank!r} → {result!r}"


class TestMarketingScriptPrompt:
    def test_includes_optional_viral_analysis(self):
        prompt = build_marketing_prompt(
            project_overview={"synopsis": "智能手表广告"},
            style="realistic",
            style_description="soft light",
            characters={"手表": {"description": "圆形表盘"}},
            scenes={},
            props={},
            ad_units_md="| 镜头 ID | hook | voiceover | 时长 | segment_break | 产品 | 场景 | 配件 |",
            supported_durations=[4, 6, 8],
            episode=1,
            viral_analysis_md="# 爆款视频内容理解\n## 结构拆解\n快节奏开头",
        )

        assert "<viral_analysis>" in prompt
        assert "快节奏开头" in prompt
        assert "禁止复制原视频人物" in prompt
