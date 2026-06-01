from lib.config.registry import PROVIDER_REGISTRY, ModelInfo, ProviderMeta


def test_all_providers_registered():
    # 营销视频 Agent：仅保留 ark（文本/图片/视频）+ openai（图片）。
    assert set(PROVIDER_REGISTRY.keys()) == {"ark", "openai"}


def test_provider_meta_fields():
    meta = PROVIDER_REGISTRY["ark"]
    assert isinstance(meta, ProviderMeta)
    assert meta.display_name == "火山方舟"
    assert "video" in meta.media_types
    assert "image" in meta.media_types
    assert "api_key" in meta.required_keys
    assert "api_key" in meta.secret_keys
    assert "text_to_video" in meta.capabilities


def test_ark_supports_video_and_image():
    meta = PROVIDER_REGISTRY["ark"]
    assert "video" in meta.media_types
    assert "image" in meta.media_types


def test_openai_is_image_only():
    meta = PROVIDER_REGISTRY["openai"]
    assert meta.media_types == ["image"]


def test_required_keys_are_subset_of_all_keys():
    for name, meta in PROVIDER_REGISTRY.items():
        all_keys = set(meta.required_keys) | set(meta.optional_keys)
        for rk in meta.required_keys:
            assert rk in all_keys, f"{name}: required key {rk} not in all keys"


def test_secret_keys_are_subset_of_required_or_optional():
    for name, meta in PROVIDER_REGISTRY.items():
        all_keys = set(meta.required_keys) | set(meta.optional_keys)
        for sk in meta.secret_keys:
            assert sk in all_keys, f"{name}: secret key {sk} not in all keys"


class TestModelInfoDurations:
    def test_video_models_have_supported_durations(self):
        """所有预置视频模型必须声明 supported_durations。"""
        for provider_id, meta in PROVIDER_REGISTRY.items():
            for model_id, model_info in meta.models.items():
                if model_info.media_type == "video":
                    assert len(model_info.supported_durations) > 0, (
                        f"{provider_id}/{model_id} 是视频模型但未声明 supported_durations"
                    )

    def test_non_video_models_have_empty_durations(self):
        """非视频模型的 supported_durations 应为空列表。"""
        for provider_id, meta in PROVIDER_REGISTRY.items():
            for model_id, model_info in meta.models.items():
                if model_info.media_type != "video":
                    assert model_info.supported_durations == [], (
                        f"{provider_id}/{model_id} 不是视频模型但有 supported_durations"
                    )

    def test_model_info_default_values(self):
        """ModelInfo 新字段的默认值。"""
        mi = ModelInfo(display_name="test", media_type="text", capabilities=[])
        assert mi.supported_durations == []
        assert mi.duration_resolution_constraints == {}
