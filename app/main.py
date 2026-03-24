"""Application entrypoint for the trading agent."""

from __future__ import annotations

import logging

from backtest.metrics import summarize_portfolio
from config.settings import load_config
from data.data_normalizer import MarketDataService
from execution.order_manager import OrderManager
from monitoring.alerts import NotificationManager
from monitoring.logger import configure_logging
from scheduler.job_runner import sleep_until_next_cycle
from strategies.router import StrategyRouter
from utils.models import AgentContext


def run() -> None:
    """Run the main orchestration loop for the trading agent."""
    config = load_config()
    configure_logging(config.logging.level)
    logger = logging.getLogger(__name__)

    market_data_service = MarketDataService(config=config)
    router = StrategyRouter(config=config)
    order_manager = OrderManager(config=config)
    notifier = NotificationManager(config=config)

    logger.info("Starting agent with max_cycles=%s", config.runtime.max_cycles)

    cycle = 0
    while config.runtime.max_cycles is None or cycle < config.runtime.max_cycles:
        cycle += 1
        context = AgentContext(config=config)

        candles = market_data_service.fetch_candles()
        features = market_data_service.compute_features(candles)
        regime = market_data_service.detect_regime(features)
        strategy = router.select(regime)
        signals = strategy.generate(context=context, candles=candles, features=features)
        validated_signals = order_manager.review_signals(
            signals=signals,
            features=features,
            regime=regime,
        )
        execution_results = order_manager.execute(validated_signals)
        summary = summarize_portfolio(order_manager.broker.get_portfolio_snapshot())

        notifier.notify_cycle(
            cycle=cycle,
            regime=regime.value,
            signal_count=len(validated_signals),
            execution_results=execution_results,
            summary=summary,
        )
        logger.info("Completed cycle %s", cycle)
        if config.runtime.max_cycles is None or cycle < config.runtime.max_cycles:
            sleep_until_next_cycle(config.runtime.loop_interval_seconds)

    logger.info("Agent shutdown complete")


if __name__ == "__main__":
    run()
