"""Tests for _build_options() — 营销视频 Agent 预置 ark + openai + atlascloud。

自定义供应商已移除，options 只来自 PROVIDER_REGISTRY 中 ready 的预置供应商。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from lib.config.service import ConfigService, ProviderStatus
from lib.db.base import Base
from server.routers.system_config import _build_options


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s, factory
    await engine.dispose()


def _make_mock_svc(ready_providers: list[str] | None = None) -> ConfigService:
    svc = MagicMock(spec=ConfigService)
    ready = set(ready_providers or [])

    async def _get_all_providers_status():
        from lib.config.registry import PROVIDER_REGISTRY

        return [
            ProviderStatus(
                name=name,
                display_name=meta.display_name,
                description=meta.description,
                status="ready" if name in ready else "unconfigured",
                media_types=list(meta.media_types),
                capabilities=list(meta.capabilities),
                required_keys=list(meta.required_keys),
                configured_keys=list(meta.required_keys) if name in ready else [],
                missing_keys=[] if name in ready else list(meta.required_keys),
            )
            for name, meta in PROVIDER_REGISTRY.items()
        ]

    svc.get_all_providers_status = AsyncMock(side_effect=_get_all_providers_status)
    return svc


class TestBuildOptionsPresetOnly:
    async def test_no_ready_providers_returns_empty_lists(self, session):
        db_session, _ = session
        options = await _build_options(_make_mock_svc(ready_providers=[]), db_session)
        for key in ("video_backends", "image_backends", "text_backends"):
            assert options[key] == []
        assert options["provider_names"] == {}

    async def test_ready_ark_populates_all_channels(self, session):
        db_session, _ = session
        options = await _build_options(_make_mock_svc(ready_providers=["ark"]), db_session)
        assert any(v.startswith("ark/") for v in options["video_backends"])
        assert any(v.startswith("ark/") for v in options["image_backends"])
        assert any(v.startswith("ark/") for v in options["text_backends"])

    async def test_ready_openai_only_image(self, session):
        db_session, _ = session
        options = await _build_options(_make_mock_svc(ready_providers=["openai"]), db_session)
        assert any(v.startswith("openai/") for v in options["image_backends"])
        assert not any(v.startswith("openai/") for v in options["video_backends"])
        assert not any(v.startswith("openai/") for v in options["text_backends"])

    async def test_ready_atlascloud_only_image(self, session):
        db_session, _ = session
        options = await _build_options(_make_mock_svc(ready_providers=["atlascloud"]), db_session)
        assert any(v.startswith("atlascloud/") for v in options["image_backends"])
        assert "atlascloud/gpt-image-2" in options["image_backends"]
        assert not any(v.startswith("atlascloud/") for v in options["video_backends"])

    async def test_no_custom_entries_ever(self, session):
        db_session, _ = session
        options = await _build_options(_make_mock_svc(ready_providers=["ark", "openai"]), db_session)
        for key in ("video_backends", "image_backends", "text_backends"):
            assert not any(v.startswith("custom-") for v in options[key])
