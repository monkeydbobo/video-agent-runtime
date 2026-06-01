from __future__ import annotations

import pytest

from lib.cost_calculator import CostCalculator
from lib.providers import PROVIDER_ARK, PROVIDER_OPENAI


@pytest.fixture
def calc() -> CostCalculator:
    return CostCalculator()


def test_estimate_openai_reference_video_with_resolution(calc: CostCalculator):
    # sora-2-pro@1080p = 0.70 USD/s; 1 unit × 12s → 8.4
    amount, currency = calc.estimate_reference_video_cost(
        unit_durations_seconds=[12],
        provider=PROVIDER_OPENAI,
        model="sora-2-pro",
        resolution="1080p",
    )
    assert currency == "USD"
    assert amount == pytest.approx(8.4, abs=1e-6)


def test_estimate_ark_reference_video_requires_token_estimate(calc: CostCalculator):
    # Ark 走 token 计费；duration→token 估算使用 60 tokens/s 的常量近似
    amount, currency = calc.estimate_reference_video_cost(
        unit_durations_seconds=[5, 10],
        provider=PROVIDER_ARK,
        model="doubao-seedance-2-0-260128",
        generate_audio=True,
    )
    assert currency == "CNY"
    assert amount > 0


def test_estimate_empty_units_returns_zero(calc: CostCalculator):
    amount, currency = calc.estimate_reference_video_cost(
        unit_durations_seconds=[],
        provider=PROVIDER_OPENAI,
        model="sora-2",
    )
    assert amount == 0.0
    assert currency == "USD"
