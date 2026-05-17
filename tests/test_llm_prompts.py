from __future__ import annotations

import json

from app.llm.prompts import build_llm_input, build_review_prompt
from app.utils.models import FeatureSet, MarketRegime, PortfolioSnapshot, Signal, TradeSide


def test_build_llm_input_compacts_cycle_context() -> None:
    features = FeatureSet(
        last_price=100.0,
        atr=0.5,
        rsi=72.5,
        ema_fast=101.0,
        ema_slow=99.0,
        macd=1.0,
        macd_signal=0.8,
        macd_histogram=0.2,
    )
    snapshot = PortfolioSnapshot(
        cash_usd=1_000.0,
        btc_units=0.25,
        equity_usd=2_000.0,
        drawdown_percent=7.5,
        avg_entry_price=90.0,
        last_mark_price=100.0,
    )

    llm_input = build_llm_input(features=features, regime=MarketRegime.BULLISH, snapshot=snapshot)

    assert llm_input.regime == "bullish"
    assert llm_input.trend == "bullish"
    assert llm_input.volatility == "low"
    assert llm_input.position_size == 0.25


def test_build_review_prompt_is_strict_json() -> None:
    signal = Signal(
        side=TradeSide.BUY,
        symbol="BTC-USD",
        size_usd=100.0,
        reason="setup",
        reference_price=100.0,
        strategy_name="SwingATRStrategy",
    )
    prompt = build_review_prompt(
        signals=[signal],
        features=FeatureSet(last_price=100.0, atr=3.0, rsi=72.5, ema_fast=101.0, ema_slow=99.0),
        regime=MarketRegime.BULLISH,
        snapshot=PortfolioSnapshot(cash_usd=1_000.0, btc_units=0.25, equity_usd=2_000.0, drawdown_percent=7.5),
    )

    payload = json.loads(prompt)
    assert payload["decision_contract"]["decision"]["action"] == "allow | reduce | block"
    assert payload["decision_contract"]["decision"]["confidence"] == "0.0 to 1.0"
    assert payload["decision_contract"]["decision"]["score"] == "-1.0 to 1.0, negative means reject, positive means support"
    assert "Return a top-level decision object every time." in payload["instructions"]["constraints"]
    assert "If you do not provide score, the response is invalid." in payload["instructions"]["constraints"]
    assert payload["input"]["regime"] == "bullish"
    assert payload["signals"][0]["strategy_name"] == "SwingATRStrategy"
