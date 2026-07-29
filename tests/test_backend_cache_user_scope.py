"""backend 实例缓存的用户维度隔离。

Alice / Bob 选同一 provider + model 但各自凭证时，缓存不得让二者共用同一 backend
实例（否则后到的用户会复用前一个用户的 API Key）。

作者: wanghaobo
"""

from __future__ import annotations

import pytest

from lib.config.resolver import ConfigResolver
from lib.db.repositories.credential_repository import CredentialRepository
from server.services import generation_context

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_cache():
    generation_context.invalidate_backend_cache()
    yield
    generation_context.invalidate_backend_cache()


async def _seed_credential(factory, user_id: str, api_key: str) -> None:
    async with factory() as session:
        async with session.begin():
            repo = CredentialRepository(session, user_id=user_id)
            cred = await repo.create(provider="gemini", name=f"{user_id}-key", api_key=api_key)
            await repo.activate(cred.id, "gemini")


class _StubBackend:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


async def test_same_provider_model_different_users_get_own_credential(project_ownership_db, monkeypatch):
    factory = project_ownership_db
    await _seed_credential(factory, "alice-id", "alice-secret")
    await _seed_credential(factory, "bob-id", "bob-secret")

    async def fake_assemble(*, provider_id, media_type, model_id, resolver, rate_limiter):
        """用 resolver 的用户维度读回 active 凭证，模拟真实 backend 拿 Key 的时点。"""
        async with factory() as session:
            cred = await CredentialRepository(session, user_id=resolver.user_id).get_active(provider_id)
        assert cred is not None
        return _StubBackend(cred.api_key)

    monkeypatch.setattr(generation_context, "assemble_backend", fake_assemble)

    alice_resolver = ConfigResolver(factory, user_id="alice-id")
    bob_resolver = ConfigResolver(factory, user_id="bob-id")

    alice_backend = await generation_context._get_or_create_backend(
        "image", "gemini", {"model": "nano-banana"}, alice_resolver, None, user_id="alice-id"
    )
    bob_backend = await generation_context._get_or_create_backend(
        "image", "gemini", {"model": "nano-banana"}, bob_resolver, None, user_id="bob-id"
    )

    assert alice_backend is not bob_backend
    assert alice_backend.api_key == "alice-secret"
    assert bob_backend.api_key == "bob-secret"


async def test_same_user_reuses_cached_backend(project_ownership_db, monkeypatch):
    """同用户同 key 仍复用实例，确认加入 user_id 没破坏缓存本身。"""
    factory = project_ownership_db
    await _seed_credential(factory, "alice-id", "alice-secret")

    calls = 0

    async def fake_assemble(*, provider_id, media_type, model_id, resolver, rate_limiter):
        nonlocal calls
        calls += 1
        return _StubBackend("alice-secret")

    monkeypatch.setattr(generation_context, "assemble_backend", fake_assemble)

    resolver = ConfigResolver(factory, user_id="alice-id")
    first = await generation_context._get_or_create_backend(
        "image", "gemini", {"model": "nano-banana"}, resolver, None, user_id="alice-id"
    )
    second = await generation_context._get_or_create_backend(
        "image", "gemini", {"model": "nano-banana"}, resolver, None, user_id="alice-id"
    )

    assert first is second
    assert calls == 1
