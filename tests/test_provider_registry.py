"""PROVIDER_REGISTRY 字段与注册完整性单元测试（营销视频 Agent：仅 ark + openai-image）。"""

from lib.config.registry import PROVIDER_REGISTRY


def test_only_ark_and_openai_registered() -> None:
    assert set(PROVIDER_REGISTRY) == {"ark", "openai"}


def test_ark_has_default_base_url() -> None:
    ark = PROVIDER_REGISTRY["ark"]
    assert ark.default_base_url == "https://ark.cn-beijing.volces.com/api/v3"


def test_ark_supports_text_image_video() -> None:
    ark = PROVIDER_REGISTRY["ark"]
    assert set(ark.media_types) == {"text", "image", "video"}


def test_openai_is_image_only() -> None:
    openai = PROVIDER_REGISTRY["openai"]
    assert openai.media_types == ["image"]


def test_ark_video_models_have_durations_and_resolutions() -> None:
    ark = PROVIDER_REGISTRY["ark"]
    for mid, m in ark.models.items():
        if m.media_type == "video":
            assert m.supported_durations, f"{mid} missing supported_durations"
            assert m.resolutions, f"{mid} missing resolutions"
