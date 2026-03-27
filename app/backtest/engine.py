"""Historical replay engine for paper-trading strategies."""

from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.backtest.metrics import (
    BacktestMetrics,
    compute_buy_and_hold_return_percent,
    compute_drawdown_series,
    compute_max_drawdown_percent,
    compute_profit_factor,
    compute_sharpe_ratio,
)
from app.config.schema import AppConfig
from app.execution.order_manager import OrderManager
from app.features.indicators import compute_indicator_bundle
from app.features.regime_features import detect_market_regime
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.strategies.router import StrategyRouter
from app.utils.models import AgentContext, Candle, PortfolioSnapshot, TradeSide


@dataclass(slots=True)
class BacktestStep:
    """One replayed decision step."""

    timestamp: str
    regime: str
    strategy_name: str
    signal_count: int
    execution_count: int
    decision: str
    equity_usd: float
    drawdown_percent: float
    trace: list[str]


@dataclass(slots=True)
class BacktestResult:
    """Container for replay output."""

    symbol: str
    interval: str
    start_at: str
    end_at: str
    candles_processed: int
    metrics: BacktestMetrics
    final_snapshot: PortfolioSnapshot
    trades: list[dict[str, object]]
    steps: list[BacktestStep]
    equity_curve: list[dict[str, object]]
    benchmark_curve: list[dict[str, object]]
    drawdowns: list[dict[str, object]]
    halted_reason: str | None = None
    halted_at: str | None = None


class BacktestEngine:
    """Replay historical parquet candles through the live trading path."""

    PERIODS_PER_YEAR = {
        "1m": 60 * 24 * 365,
        "10m": 6 * 24 * 365,
        "30m": 2 * 24 * 365,
        "1hr": 24 * 365,
        "1d": 365,
        "1week": 52,
        "1month": 12,
    }

    def __init__(self, config: AppConfig) -> None:
        """Initialize the backtest engine."""
        self.config = config
        self.store = ParquetMarketDataStore(config.data.data_lake_path)

    def run(
        self,
        symbol: str | None = None,
        interval: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> BacktestResult:
        """Replay candles through the current trading stack."""
        symbol = symbol or self.config.trading.symbol
        interval = interval or self.config.ingestion.interval
        candles = self._load_candles(symbol=symbol, interval=interval, start_at=start_at, end_at=end_at)
        if len(candles) < self.config.data.min_candles_required:
            raise ValueError(
                f"insufficient_history_for_backtest:{len(candles)}<{self.config.data.min_candles_required}"
            )

        isolated_config = self._isolated_config()
        router = StrategyRouter(config=isolated_config)
        order_manager = OrderManager(config=isolated_config)

        steps: list[BacktestStep] = []
        equity_curve: list[dict[str, object]] = []
        benchmark_curve: list[dict[str, object]] = []
        halted_reason: str | None = None
        halted_at: str | None = None

        for index in range(self.config.data.min_candles_required, len(candles) + 1):
            window = candles[:index]
            features = compute_indicator_bundle(window)
            order_manager.mark_price(features.last_price)
            stop_results = order_manager.evaluate_stop_losses()
            snapshot = order_manager.broker.get_portfolio_snapshot()
            timestamp = window[-1].timestamp.replace(microsecond=0).isoformat()

            if any(result.accepted for result in stop_results):
                latest_snapshot = order_manager.broker.get_portfolio_snapshot()
                steps.append(
                    BacktestStep(
                        timestamp=timestamp,
                        regime="n/a",
                        strategy_name="StopLossExit",
                        signal_count=0,
                        execution_count=sum(1 for result in stop_results if result.accepted),
                        decision="SELL",
                        equity_usd=latest_snapshot.equity_usd,
                        drawdown_percent=latest_snapshot.drawdown_percent,
                        trace=[
                            "halt:stop_loss_triggered",
                            *[
                                f"execution:{result.reason} accepted={result.accepted} side={(result.side.value if result.side else 'n/a')}"
                                for result in stop_results
                            ],
                        ],
                    )
                )
                equity_curve.append(
                    {
                        "timestamp": timestamp,
                        "equity_usd": latest_snapshot.equity_usd,
                        "cash_usd": latest_snapshot.cash_usd,
                        "btc_units": latest_snapshot.btc_units,
                    }
                )
                benchmark_curve.append(
                    {
                        "timestamp": timestamp,
                        "equity_usd": self._buy_hold_equity(
                            initial_cash=isolated_config.execution.initial_cash_usd,
                            initial_price=candles[0].close,
                            current_price=window[-1].close,
                        ),
                    }
                )
                continue

            if order_manager.guard.trading_paused(snapshot):
                steps.append(
                    BacktestStep(
                        timestamp=timestamp,
                        regime="n/a",
                        strategy_name="PortfolioGuard",
                        signal_count=0,
                        execution_count=0,
                        decision="HALT",
                        equity_usd=snapshot.equity_usd,
                        drawdown_percent=snapshot.drawdown_percent,
                        trace=[
                            "halt:max_drawdown_reached",
                            f"drawdown_percent={snapshot.drawdown_percent:.2f}",
                            f"max_drawdown_percent={isolated_config.trading.max_drawdown_percent:.2f}",
                        ],
                    )
                )
                equity_curve.append(
                    {
                        "timestamp": timestamp,
                        "equity_usd": snapshot.equity_usd,
                        "cash_usd": snapshot.cash_usd,
                        "btc_units": snapshot.btc_units,
                    }
                )
                benchmark_curve.append(
                    {
                        "timestamp": timestamp,
                        "equity_usd": self._buy_hold_equity(
                            initial_cash=isolated_config.execution.initial_cash_usd,
                            initial_price=candles[0].close,
                            current_price=window[-1].close,
                        ),
                    }
                )
                halted_reason = "max_drawdown_reached"
                halted_at = timestamp
                break

            context = AgentContext(config=isolated_config)
            context.available_cash_usd = snapshot.cash_usd
            context.latest_buy_fill_price = order_manager.broker.latest_buy_price()
            context.active_swing_positions = order_manager.broker.active_swing_positions()

            regime = detect_market_regime(features)
            strategy = router.select(
                regime,
                bullish_trend=features.ema_fast > features.ema_slow,
                has_open_swing_positions=bool(context.active_swing_positions),
            )
            outcome = strategy.generate(context=context, candles=window, features=features)
            signals = order_manager.review_signals(outcome.signals, features=features, regime=regime)
            execution_results = [*stop_results, *order_manager.execute(signals)]
            latest_snapshot = order_manager.broker.get_portfolio_snapshot()

            steps.append(
                BacktestStep(
                    timestamp=timestamp,
                    regime=regime.value,
                    strategy_name=outcome.strategy_name,
                    signal_count=len(signals),
                    execution_count=sum(1 for result in execution_results if result.accepted),
                    decision="BUY" if any(result.accepted and result.side == TradeSide.BUY for result in execution_results) else "SELL" if any(result.accepted and result.side == TradeSide.SELL for result in execution_results) else "HOLD" if signals else "NO BUY",
                    equity_usd=latest_snapshot.equity_usd,
                    drawdown_percent=latest_snapshot.drawdown_percent,
                    trace=[
                        *outcome.trace,
                        *[
                            f"execution:{result.reason} accepted={result.accepted} side={(result.side.value if result.side else 'n/a')}"
                            for result in execution_results
                        ],
                    ],
                )
            )
            equity_curve.append(
                {
                    "timestamp": timestamp,
                    "equity_usd": latest_snapshot.equity_usd,
                    "cash_usd": latest_snapshot.cash_usd,
                    "btc_units": latest_snapshot.btc_units,
                }
            )
            benchmark_curve.append(
                {
                    "timestamp": timestamp,
                    "equity_usd": self._buy_hold_equity(
                        initial_cash=isolated_config.execution.initial_cash_usd,
                        initial_price=candles[0].close,
                        current_price=window[-1].close,
                    ),
                }
            )

        trades = self._load_trade_log(Path(isolated_config.execution.paper_trade_log_path))
        final_snapshot = order_manager.broker.get_portfolio_snapshot()
        drawdown_values = compute_drawdown_series([point["equity_usd"] for point in equity_curve])
        drawdowns = [
            {"timestamp": point["timestamp"], "drawdown_percent": drawdown}
            for point, drawdown in zip(equity_curve, drawdown_values)
        ]
        metrics = self._build_metrics(
            interval=interval,
            candles=candles,
            equity_curve=[point["equity_usd"] for point in equity_curve],
            initial_cash=isolated_config.execution.initial_cash_usd,
            trades=trades,
        )

        return BacktestResult(
            symbol=symbol,
            interval=interval,
            start_at=candles[0].timestamp.replace(microsecond=0).isoformat(),
            end_at=candles[-1].timestamp.replace(microsecond=0).isoformat(),
            candles_processed=len(candles),
            metrics=metrics,
            final_snapshot=final_snapshot,
            trades=trades,
            steps=steps,
            equity_curve=equity_curve,
            benchmark_curve=benchmark_curve,
            drawdowns=drawdowns,
            halted_reason=halted_reason,
            halted_at=halted_at,
        )

    def _load_candles(
        self,
        symbol: str,
        interval: str,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> list[Candle]:
        candles = self.store.load_candles(symbol=symbol, interval=interval, limit=None)
        if start_at is not None:
            candles = [candle for candle in candles if candle.timestamp >= start_at]
        if end_at is not None:
            candles = [candle for candle in candles if candle.timestamp <= end_at]
        return candles

    def _isolated_config(self) -> AppConfig:
        """Clone config and redirect paper-trading artifacts to a temp directory."""
        config = copy.deepcopy(self.config)
        temp_dir = Path(tempfile.mkdtemp(prefix="adaptive-btc-backtest-"))
        config.execution.paper_state_path = str(temp_dir / "paper_broker_state.json")
        config.execution.paper_trade_log_path = str(temp_dir / "paper_trade_ledger.jsonl")
        config.execution.paper_cycle_log_path = str(temp_dir / "paper_cycle_log.jsonl")
        config.execution.paper_snapshot_path = str(temp_dir / "paper_portfolio_snapshot.json")
        config.execution.paper_decision_trace_path = str(temp_dir / "paper_decision_trace.jsonl")
        return config

    def _build_metrics(
        self,
        interval: str,
        candles: list[Candle],
        equity_curve: list[float],
        initial_cash: float,
        trades: list[dict[str, object]],
    ) -> BacktestMetrics:
        final_equity = equity_curve[-1] if equity_curve else initial_cash
        total_return_percent = 0.0 if initial_cash == 0 else ((final_equity - initial_cash) / initial_cash) * 100
        buy_hold_return_percent = compute_buy_and_hold_return_percent(
            initial_price=candles[0].close,
            final_price=candles[-1].close,
        )
        max_drawdown_percent = compute_max_drawdown_percent(equity_curve)
        sharpe_ratio = compute_sharpe_ratio(
            equity_curve=equity_curve,
            periods_per_year=self.PERIODS_PER_YEAR.get(interval, 365),
        )
        filled_trade_count = len(trades)
        closed_trade_count, win_rate_percent, avg_win_usd, avg_loss_usd, profit_factor = self._closed_trade_stats(trades)
        return BacktestMetrics(
            initial_equity_usd=initial_cash,
            final_equity_usd=final_equity,
            total_return_percent=total_return_percent,
            buy_and_hold_return_percent=buy_hold_return_percent,
            max_drawdown_percent=max_drawdown_percent,
            sharpe_ratio=sharpe_ratio,
            trade_count=filled_trade_count,
            filled_trade_count=filled_trade_count,
            closed_trade_count=closed_trade_count,
            win_rate_percent=win_rate_percent,
            avg_win_usd=avg_win_usd,
            avg_loss_usd=avg_loss_usd,
            profit_factor=profit_factor,
        )

    @staticmethod
    def _load_trade_log(path: Path) -> list[dict[str, object]]:
        """Load executed trades from the isolated paper ledger."""
        if not path.exists():
            return []
        trades: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            trades.append(json.loads(line))
        return trades

    @staticmethod
    def _closed_trade_stats(trades: list[dict[str, object]]) -> tuple[int, float, float, float, float]:
        """Compute closed-trade stats from realized swing exits."""
        wins = 0
        closed = 0
        realized_pnls: list[float] = []
        for trade in trades:
            strategy_name = str(trade.get("strategy_name", ""))
            side = str(trade.get("side", ""))
            if strategy_name != "SwingATRStrategy" or side != TradeSide.SELL.value:
                continue
            closed += 1
            realized_pnl = float(trade.get("realized_pnl_usd", 0.0) or 0.0)
            realized_pnls.append(realized_pnl)
            if realized_pnl > 0:
                wins += 1
        win_rate = 0.0 if closed == 0 else (wins / closed) * 100
        wins_only = [value for value in realized_pnls if value > 0]
        losses_only = [value for value in realized_pnls if value < 0]
        avg_win = 0.0 if not wins_only else sum(wins_only) / len(wins_only)
        avg_loss = 0.0 if not losses_only else sum(losses_only) / len(losses_only)
        profit_factor = compute_profit_factor(realized_pnls)
        return closed, win_rate, avg_win, avg_loss, profit_factor

    @staticmethod
    def _buy_hold_equity(initial_cash: float, initial_price: float, current_price: float) -> float:
        """Compute the buy-and-hold benchmark equity at a given price."""
        if initial_cash <= 0 or initial_price <= 0:
            return initial_cash
        units = initial_cash / initial_price
        return units * current_price
