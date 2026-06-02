from __future__ import annotations

from dataclasses import dataclass, field

from lib.ark_shared import ARK_BASE_URL


@dataclass(frozen=True)
class ModelInfo:
    display_name: str
    media_type: str
    capabilities: list[str]
    default: bool = False
    supported_durations: list[int] = field(default_factory=list)
    duration_resolution_constraints: dict[str, list[int]] = field(default_factory=dict)
    resolutions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderMeta:
    display_name: str
    description: str
    required_keys: list[str]
    optional_keys: list[str] = field(default_factory=list)
    secret_keys: list[str] = field(default_factory=list)
    models: dict[str, ModelInfo] = field(default_factory=dict)
    default_base_url: str | None = None

    @property
    def media_types(self) -> list[str]:
        return sorted(set(m.media_type for m in self.models.values()))

    @property
    def capabilities(self) -> list[str]:
        return sorted(set(c for m in self.models.values() for c in m.capabilities))


# 营销视频 Agent 收敛后的供应商注册表：
# - 文本 / 视频：仅火山方舟 Ark（豆包 Seed / Seedream / Seedance）
# - 图片：火山方舟 Ark + OpenAI（GPT Image）+ Atlas Cloud（GPT Image 2 中转）
# 其它历史供应商（Gemini / Grok / Vidu / Ark Agent Plan）已移除。
PROVIDER_REGISTRY: dict[str, ProviderMeta] = {
    "ark": ProviderMeta(
        display_name="火山方舟",
        description="字节跳动火山方舟 AI 平台，支持 Seedance 视频生成和 Seedream 图片生成，具备音频生成和种子控制能力。",
        required_keys=["api_key"],
        optional_keys=["video_max_workers", "image_max_workers"],
        secret_keys=["api_key"],
        models={
            # --- text ---
            "doubao-seed-2-0-pro-260215": ModelInfo(
                display_name="豆包 Seed 2.0 Pro",
                media_type="text",
                capabilities=["text_generation", "vision"],
            ),
            "doubao-seed-2-0-lite-260215": ModelInfo(
                display_name="豆包 Seed 2.0 Lite",
                media_type="text",
                capabilities=["text_generation", "vision"],
                default=True,
            ),
            "doubao-seed-2-0-mini-260215": ModelInfo(
                display_name="豆包 Seed 2.0 Mini",
                media_type="text",
                capabilities=["text_generation", "vision"],
            ),
            "doubao-seed-1-8-251228": ModelInfo(
                display_name="豆包 Seed 1.8",
                media_type="text",
                capabilities=["text_generation", "structured_output", "vision"],
            ),
            # --- image ---
            "doubao-seedream-5-0-lite-260128": ModelInfo(
                display_name="Seedream 5.0 Lite",
                media_type="image",
                capabilities=["text_to_image", "image_to_image"],
                default=True,
            ),
            "doubao-seedream-5-0-260128": ModelInfo(
                display_name="Seedream 5.0",
                media_type="image",
                capabilities=["text_to_image", "image_to_image"],
            ),
            "doubao-seedream-4-5-251128": ModelInfo(
                display_name="Seedream 4.5",
                media_type="image",
                capabilities=["text_to_image", "image_to_image"],
            ),
            "doubao-seedream-4-0-250828": ModelInfo(
                display_name="Seedream 4.0",
                media_type="image",
                capabilities=["text_to_image", "image_to_image"],
            ),
            # --- video ---
            "doubao-seedance-1-5-pro-251215": ModelInfo(
                display_name="Seedance 1.5 Pro",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "generate_audio", "seed_control", "flex_tier"],
                default=True,
                supported_durations=list(range(4, 13)),
                resolutions=["480p", "720p", "1080p"],
            ),
            "doubao-seedance-2-0-260128": ModelInfo(
                display_name="Seedance 2.0",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "generate_audio", "seed_control", "video_extend"],
                supported_durations=list(range(4, 16)),
                resolutions=["480p", "720p", "1080p"],
            ),
            "doubao-seedance-2-0-fast-260128": ModelInfo(
                display_name="Seedance 2.0 Fast",
                media_type="video",
                capabilities=["text_to_video", "image_to_video", "generate_audio", "seed_control", "video_extend"],
                supported_durations=list(range(4, 16)),
                resolutions=["480p", "720p", "1080p"],
            ),
        },
        default_base_url=ARK_BASE_URL,
    ),
    "openai": ProviderMeta(
        display_name="OpenAI",
        description="OpenAI 官方平台，提供 GPT Image 系列图片生成能力（营销视频 Agent 仅启用图片）。",
        required_keys=["api_key"],
        optional_keys=["base_url", "image_max_workers"],
        secret_keys=["api_key"],
        models={
            # --- image only ---
            "gpt-image-2": ModelInfo(
                display_name="GPT Image 2",
                media_type="image",
                capabilities=["text_to_image", "image_to_image"],
                default=True,
                resolutions=["512px", "1K", "2K"],
            ),
            "gpt-image-1.5": ModelInfo(
                display_name="GPT Image 1.5",
                media_type="image",
                capabilities=["text_to_image", "image_to_image"],
                resolutions=["512px", "1K", "2K"],
            ),
            "gpt-image-1-mini": ModelInfo(
                display_name="GPT Image 1 Mini",
                media_type="image",
                capabilities=["text_to_image", "image_to_image"],
                resolutions=["512px", "1K", "2K"],
            ),
        },
    ),
    "atlascloud": ProviderMeta(
        display_name="Atlas Cloud",
        description="Atlas Cloud 统一推理平台，提供 GPT Image 2 文生图与图生图能力，按张计费。",
        required_keys=["api_key"],
        optional_keys=["base_url", "image_max_workers"],
        secret_keys=["api_key"],
        models={
            "gpt-image-2": ModelInfo(
                display_name="GPT Image 2 (Atlas Cloud)",
                media_type="image",
                capabilities=["text_to_image", "image_to_image"],
                default=True,
                resolutions=["512px", "1K", "2K"],
            ),
        },
        default_base_url="https://api.atlascloud.ai/api/v1",
    ),
}
