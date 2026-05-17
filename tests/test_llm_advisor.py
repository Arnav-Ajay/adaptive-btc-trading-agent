from __future__ import annotations

from app.config.schema import (
    AppConfig,
    DataConfig,
    ExecutionConfig,
    IngestionConfig,
    LLMConfig,
    LoggingConfig,
    NotificationConfig,
    RuntimeConfig,
    TradingConfig,
)
from app.llm.advisor import LLMAdvisor
from app.utils.models import FeatureSet, MarketRegime, PortfolioSnapshot, Signal, TradeSide


def _build_config(*, enabled: bool, env: dict[str, str] | None = None) -> AppConfig:
    return AppConfig(
        trading=TradingConfig(),
        data=DataConfig(),
        ingestion=IngestionConfig(),
        runtime=RuntimeConfig(),
        logging=LoggingConfig(),
        notifications=NotificationConfig(),
        llm=LLMConfig(enabled=enabled),
        execution=ExecutionConfig(),
        env=env or {},
        cache_path="",
    )


def _signals() -> list[Signal]:
    return [
        Signal(
            side=TradeSide.BUY,
            symbol="BTC-USD",
            size_usd=250.0,
            reason="momentum_atr_setup",
            reference_price=61_000.0,
            stop_loss=59_500.0,
            strategy_name="SwingATRStrategy",
        )
    ]


def _features() -> FeatureSet:
    return FeatureSet(
        last_price=61_000.0,
        atr=1_000.0,
        rsi=31.0,
        ema_fast=61_200.0,
        ema_slow=60_800.0,
        macd=150.0,
        macd_signal=110.0,
        macd_histogram=40.0,
    )


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        cash_usd=9_500.0,
        btc_units=0.05,
        equity_usd=12_550.0,
        drawdown_percent=3.0,
        dca_btc_units=0.03,
        swing_btc_units=0.02,
    )


def test_llm_advisor_returns_disabled_summary_when_feature_is_off() -> None:
    advisor = LLMAdvisor(config=_build_config(enabled=False))

    advice = advisor.review(
        signals=_signals(),
        features=_features(),
        regime=MarketRegime.BULLISH,
        snapshot=_snapshot(),
    )

    assert advice.summary == "LLM disabled"
    assert advice.signal_actions == []


def test_llm_advisor_returns_missing_key_summary_when_enabled_without_api_key() -> None:
    advisor = LLMAdvisor(config=_build_config(enabled=True, env={}))

    advice = advisor.review(
        signals=_signals(),
        features=_features(),
        regime=MarketRegime.BULLISH,
        snapshot=_snapshot(),
    )

    assert "OPENAI_API_KEY is missing" in advice.summary
    assert advice.signal_actions == []


def test_llm_advisor_parses_and_sanitizes_structured_response(monkeypatch) -> None:
    config = _build_config(enabled=True, env={"OPENAI_API_KEY": "test-key"})
    advisor = LLMAdvisor(config=config)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"summary":"Reduce the swing size.",'
                                    '"decision":{"action":"reduce","confidence":0.73,"reason":"High volatility and weak follow-through.","reason_code":"elevated_noise","score":-0.42},'
                                    '"signal_actions":[{"signal_index":0,"action":"reduce","size_multiplier":0.2,'
                                    '"rationale":"Recent momentum is fragile."}],'
                                    '"parameter_suggestions":{"atr_multiplier":1.7,"unknown_field":99}}'
                                ),
                            }
                        ],
                    }
                ]
            }

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.llm.advisor.requests.post", fake_post)

    advice = advisor.review(
        signals=_signals(),
        features=_features(),
        regime=MarketRegime.BULLISH,
        snapshot=_snapshot(),
    )

    assert advice.summary == "Reduce the swing size."
    assert advice.decision is not None
    assert advice.decision_present is True
    assert advice.decision_valid is True
    assert advice.decision.action == "reduce"
    assert advice.decision.confidence == 0.73
    assert advice.decision.score == -0.42
    assert len(advice.signal_actions) == 1
    assert advice.signal_actions[0].action == "reduce"
    assert advice.signal_actions[0].size_multiplier == 0.5
    assert advice.parameter_suggestions == {"atr_multiplier": 1.7}


def test_llm_advisor_marks_missing_decision_invalid(monkeypatch) -> None:
    config = _build_config(enabled=True, env={"OPENAI_API_KEY": "test-key"})
    advisor = LLMAdvisor(config=config)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": (
                                    '{"summary":"No decision provided.",'
                                    '"signal_actions":[],"parameter_suggestions":{}}'
                                ),
                            }
                        ],
                    }
                ]
            }

    monkeypatch.setattr("app.llm.advisor.requests.post", lambda *args, **kwargs: FakeResponse())

    advice = advisor.review(
        signals=_signals(),
        features=_features(),
        regime=MarketRegime.BULLISH,
        snapshot=_snapshot(),
    )

    assert advice.decision is None
    assert advice.decision_present is False
    assert advice.decision_valid is False
    assert advice.status == "invalid_decision_contract"
