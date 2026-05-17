from __future__ import annotations

from app.llm.validator import validate_advice
from app.utils.models import LLMAdvice, LLMSignalAction, Signal, TradeSide


def test_validate_advice_blocks_and_reduces_signals() -> None:
    signals = [
        Signal(
            side=TradeSide.BUY,
            symbol="BTC-USD",
            size_usd=100.0,
            reason="initial_dca_entry",
            reference_price=60_000.0,
            strategy_name="DCAStrategy",
        ),
        Signal(
            side=TradeSide.BUY,
            symbol="BTC-USD",
            size_usd=250.0,
            reason="momentum_atr_setup",
            reference_price=60_500.0,
            stop_loss=59_200.0,
            strategy_name="SwingATRStrategy",
        ),
    ]
    advice = LLMAdvice(
        summary="Block the DCA buy and reduce the swing size.",
        signal_actions=[
            LLMSignalAction(
                signal_index=0,
                action="block",
                size_multiplier=0.0,
                rationale="Regime is too weak for a fresh DCA add.",
            ),
            LLMSignalAction(
                signal_index=1,
                action="reduce",
                size_multiplier=0.5,
                rationale="Momentum is present but conviction is moderate.",
            ),
        ],
        parameter_suggestions={},
    )

    validated = validate_advice(signals=signals, advice=advice)

    assert len(validated) == 1
    assert validated[0].reason == "momentum_atr_setup"
    assert validated[0].size_usd == 125.0
    assert validated[0].stop_loss == 59_200.0
