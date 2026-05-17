"""Application entrypoint for the trading agent."""

from __future__ import annotations

import logging

from app.backtest.metrics import summarize_portfolio
from app.config.schema import AppConfig
from app.config.settings import load_config
from app.data.data_normalizer import MarketDataService
from app.execution.order_manager import OrderManager
from app.monitoring.alerts import NotificationManager
from app.monitoring.logger import configure_logging
from app.monitoring.trading_journal import TradingJournal
from app.scheduler.job_runner import sleep_until_next_cycle
from app.strategies.router import StrategyRouter
from app.utils.models import AgentContext


def run_cycle(config: AppConfig | None = None) -> None:
    """Run one trading decision cycle against the local data lake."""
    config = config or load_config()
    configure_logging(config.logging.level, service_name="trading")
    logger = logging.getLogger(__name__)

    market_data_service = MarketDataService(config=config)
    router = StrategyRouter(config=config)
    order_manager = OrderManager(config=config)
    notifier = NotificationManager(config=config)
    journal = TradingJournal(config=config)
    cycle_number = journal.next_cycle_number()

    context = AgentContext(config=config)
    candles = market_data_service.fetch_candles()
    candles_ready, readiness_reason = market_data_service.validate_candles(candles)
    if not candles_ready:
        logger.warning("Skipping cycle due to market data readiness check: %s", readiness_reason)
        return

    features = market_data_service.compute_features(candles)
    regime_state = market_data_service.detect_regime_score(candles, features)
    regime = regime_state.regime_label
    order_manager.mark_price(features.last_price)
    stop_results = order_manager.evaluate_stop_losses()
    snapshot = order_manager.broker.get_portfolio_snapshot()
    if any(result.accepted for result in stop_results):
        summary = summarize_portfolio(snapshot)
        journal.record_cycle(
            cycle=cycle_number,
            regime="n/a",
            strategy_name="StopLossExit",
            indicator_snapshot={
                "candle_count": len(candles),
                "latest_candle_timestamp": candles[-1].timestamp.replace(microsecond=0).isoformat(),
                "last_price": features.last_price,
                "atr": features.atr,
                "rsi": features.rsi,
                "ema_fast": features.ema_fast,
                "ema_slow": features.ema_slow,
                "macd": features.macd,
                "macd_signal": features.macd_signal,
                "macd_histogram": features.macd_histogram,
                "structure_regime": regime.value,
                "structure_score": regime_state.structure_score,
                "momentum_score": regime_state.momentum_score,
                "regime_score": regime_state.regime_score,
                "regime_confidence": regime_state.confidence,
                "deterioration_score": regime_state.deterioration_score,
            },
            decision_trace=[
                "halt:stop_loss_triggered",
                *[
                    f"execution:{result.reason} accepted={result.accepted} side={(result.side.value if result.side else 'n/a')}"
                    for result in stop_results
                ],
            ],
            signal_count=0,
            execution_results=stop_results,
            snapshot=snapshot,
            summary=summary,
            llm_review={
                "enabled": bool(config.llm.enabled),
                "used": False,
                "status": "stop_loss_exit",
                "summary": "Stop-loss exit processed before strategy review",
                "action_count": 0,
            },
        )
        notifier.notify_cycle(
            cycle=cycle_number,
            regime="n/a",
            signal_count=0,
            execution_results=stop_results,
            summary=summary,
        )
        logger.warning("Skipping new entries for this cycle because a stop-loss exit was triggered")
        return
    context.available_cash_usd = snapshot.cash_usd
    context.market_regime = regime
    context.regime_score = regime_state.regime_score
    context.regime_confidence = regime_state.confidence
    context.regime_deterioration = regime_state.deterioration_score
    context.regime_diagnostics = {
        "swing_count": regime_state.diagnostics.swing_count,
        "high_count": regime_state.diagnostics.high_count,
        "low_count": regime_state.diagnostics.low_count,
        "rising_high_ratio": regime_state.diagnostics.rising_high_ratio,
        "rising_low_ratio": regime_state.diagnostics.rising_low_ratio,
        "falling_high_ratio": regime_state.diagnostics.falling_high_ratio,
        "falling_low_ratio": regime_state.diagnostics.falling_low_ratio,
        "last_price_vs_prior_low": regime_state.diagnostics.last_price_vs_prior_low,
        "ema_spread_percent": regime_state.diagnostics.ema_spread_percent,
        "rsi_centered": regime_state.diagnostics.rsi_centered,
        "macd_histogram_percent": regime_state.diagnostics.macd_histogram_percent,
        "atr_percent": regime_state.diagnostics.atr_percent,
    }
    context.latest_buy_fill_price = order_manager.broker.latest_buy_price()
    context.latest_dca_buy_price = order_manager.broker.latest_dca_buy_price()
    context.active_swing_positions = order_manager.broker.active_swing_positions()
    context.portfolio_snapshot = snapshot
    strategy = router.select(
        regime,
        bullish_trend=features.ema_fast > features.ema_slow,
        has_open_swing_positions=bool(context.active_swing_positions),
        regime_score=regime_state.regime_score,
        regime_confidence=regime_state.confidence,
        deterioration_score=regime_state.deterioration_score,
    )
    strategy_outcome = strategy.generate(context=context, candles=candles, features=features)
    logger.info(
        "Cycle indicators: candles=%s last_ts=%s last_price=%.2f atr=%.2f rsi=%.2f ema_fast=%.2f ema_slow=%.2f macd=%.4f macd_signal=%.4f macd_histogram=%.4f regime=%s strategy=%s",
        len(candles),
        candles[-1].timestamp.isoformat(),
        features.last_price,
        features.atr,
        features.rsi,
        features.ema_fast,
        features.ema_slow,
        features.macd,
        features.macd_signal,
        features.macd_histogram,
        f"{regime.value} score={regime_state.regime_score:.3f} conf={regime_state.confidence:.3f} det={regime_state.deterioration_score:.3f}",
        strategy_outcome.strategy_name,
    )
    logger.info("Strategy trace: %s", " | ".join(strategy_outcome.trace))
    validated_signals = order_manager.review_signals(
        signals=strategy_outcome.signals,
        features=features,
        regime=regime,
    )
    llm_review_meta = dict(order_manager.last_review_meta)
    decision_timestamp = candles[-1].timestamp.replace(microsecond=0).isoformat()
    execution_results = [*stop_results, *order_manager.execute(validated_signals, decision_timestamp=decision_timestamp)]
    latest_snapshot = order_manager.broker.get_portfolio_snapshot()
    summary = summarize_portfolio(latest_snapshot)
    journal.record_cycle(
        cycle=cycle_number,
        regime=regime.value,
        strategy_name=strategy_outcome.strategy_name,
        indicator_snapshot={
            "candle_count": len(candles),
            "latest_candle_timestamp": candles[-1].timestamp.replace(microsecond=0).isoformat(),
            "last_price": features.last_price,
            "atr": features.atr,
            "rsi": features.rsi,
            "ema_fast": features.ema_fast,
            "ema_slow": features.ema_slow,
            "macd": features.macd,
            "macd_signal": features.macd_signal,
            "macd_histogram": features.macd_histogram,
            "structure_regime": regime.value,
        },
        decision_trace=strategy_outcome.trace,
        signal_count=len(validated_signals),
        execution_results=execution_results,
        snapshot=latest_snapshot,
        summary=summary,
        llm_review=llm_review_meta,
    )

    notifier.notify_cycle(
        cycle=cycle_number,
        regime=regime.value,
        signal_count=len(validated_signals),
        execution_results=execution_results,
        summary=summary,
    )
    logger.info("Completed trading cycle")


def run() -> None:
    """Run the trading agent manually for the configured number of cycles."""
    config = load_config()
    configure_logging(config.logging.level, service_name="trading")
    logger = logging.getLogger(__name__)

    logger.info(
        "Starting manual trading agent with data_lake=%s candle_interval=%s max_cycles=%s",
        config.data.data_lake_path,
        config.ingestion.interval,
        config.runtime.max_cycles,
    )

    cycle = 0
    while config.runtime.max_cycles is None or cycle < config.runtime.max_cycles:
        cycle += 1
        run_cycle(config=load_config())
        if config.runtime.max_cycles is None or cycle < config.runtime.max_cycles:
            sleep_until_next_cycle(config.runtime.loop_interval_seconds)

    logger.info("Agent shutdown complete")


if __name__ == "__main__":
    run()
