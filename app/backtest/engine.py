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
from app.features.regime_features import detect_regime_score
from app.ingestion.parquet_store import ParquetMarketDataStore
from app.strategies.dca import DCAStrategy
from app.strategies.hybrid import HybridStrategy
from app.strategies.hybrid_pullback import HybridPullbackStrategy
from app.strategies.pullback_trend import PullbackTrendStrategy
from app.strategies.profiles import normalize_strategy_profile
from app.strategies.router import StrategyRouter
from app.strategies.swing_atr import SwingATRStrategy
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
    llm_review: dict[str, object] | None = None


@dataclass(slots=True)
class BacktestResult:
    """Container for replay output."""

    symbol: str
    strategy_profile: str
    interval: str
    decision_cadence_minutes: int
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

    def __init__(self, config: AppConfig, review_policy=None) -> None:
        """Initialize the backtest engine."""
        self.config = config
        self.review_policy = review_policy
        self.store = ParquetMarketDataStore(config.data.data_lake_path)

    def _decision_cadence_minutes(self) -> int:
        """Return the replay decision cadence in minutes."""
        return max(1, int(self.config.runtime.decision_cadence_minutes))

    @staticmethod
    def _is_decision_cadence_boundary(timestamp: datetime, cadence_minutes: int) -> bool:
        """Return whether a candle timestamp is aligned to the configured cadence."""
        cadence_minutes = max(1, int(cadence_minutes))
        if cadence_minutes < 60:
            return timestamp.minute % cadence_minutes == 0
        if cadence_minutes % 60 == 0:
            cadence_hours = cadence_minutes // 60
            return timestamp.minute == 0 and timestamp.hour % cadence_hours == 0
        elapsed_minutes = (timestamp.hour * 60) + timestamp.minute
        return elapsed_minutes % cadence_minutes == 0

    def run(
        self,
        symbol: str | None = None,
        interval: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        strategy_profile: str | None = None,
    ) -> BacktestResult:
        """Replay candles through the current trading stack."""
        symbol = symbol or self.config.trading.symbol
        interval = interval or self.config.ingestion.interval
        strategy_profile = normalize_strategy_profile(strategy_profile)
        decision_cadence_minutes = self._decision_cadence_minutes()
        candles = self._load_candles(symbol=symbol, interval=interval, start_at=start_at, end_at=end_at)
        if len(candles) < self.config.data.min_candles_required:
            raise ValueError(
                f"insufficient_history_for_backtest:{len(candles)}<{self.config.data.min_candles_required}"
            )

        if strategy_profile == "buy_and_hold":
            return self._run_buy_and_hold(
                symbol=symbol,
                interval=interval,
                candles=candles,
                strategy_profile=strategy_profile,
            )

        isolated_config = self._isolated_config()
        router = StrategyRouter(config=isolated_config)
        dca = DCAStrategy(config=isolated_config)
        swing = SwingATRStrategy(config=isolated_config)
        hybrid = HybridStrategy(config=isolated_config)
        pullback = PullbackTrendStrategy(config=isolated_config)
        hybrid_pullback = HybridPullbackStrategy(config=isolated_config)
        order_manager = OrderManager(config=isolated_config, review_policy=self.review_policy)
        replay_start_index = self.config.data.min_candles_required - 1
        replay_start_candle = candles[replay_start_index]
        benchmark_initial_price = replay_start_candle.close
        steps: list[BacktestStep] = []
        equity_curve: list[dict[str, object]] = []
        benchmark_curve: list[dict[str, object]] = []
        halted_reason: str | None = None
        halted_at: str | None = None
        halted_snapshot: PortfolioSnapshot | None = None

        for index in range(self.config.data.min_candles_required, len(candles) + 1):
            window = candles[:index]
            timestamp = window[-1].timestamp.replace(microsecond=0).isoformat()

            if halted_reason == "max_drawdown_reached" and halted_snapshot is not None:
                steps.append(
                    BacktestStep(
                        timestamp=timestamp,
                        regime="n/a",
                        strategy_name="PortfolioGuard",
                        signal_count=0,
                        execution_count=0,
                        decision="HALT",
                        equity_usd=halted_snapshot.equity_usd,
                        drawdown_percent=halted_snapshot.drawdown_percent,
                        trace=[
                            "hold:max_drawdown_guard_active",
                            f"halted_at={halted_at}",
                        ],
                    )
                )
                equity_curve.append(
                    {
                        "timestamp": timestamp,
                        "equity_usd": halted_snapshot.equity_usd,
                        "cash_usd": halted_snapshot.cash_usd,
                        "btc_units": halted_snapshot.btc_units,
                    }
                )
                benchmark_curve.append(
                    {
                        "timestamp": timestamp,
                        "equity_usd": self._buy_hold_equity(
                            initial_cash=isolated_config.execution.initial_cash_usd,
                            initial_price=benchmark_initial_price,
                            current_price=window[-1].close,
                        ),
                    }
                )
                continue

            features = compute_indicator_bundle(window)
            order_manager.mark_price(features.last_price)
            stop_results = order_manager.evaluate_stop_losses()
            snapshot = order_manager.broker.get_portfolio_snapshot()
            cadence_boundary_reached = self._is_decision_cadence_boundary(window[-1].timestamp, decision_cadence_minutes)

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
                        llm_review={
                            "enabled": bool(isolated_config.llm.enabled),
                            "used": False,
                            "status": "stop_loss_exit",
                            "summary": "Stop-loss exit processed before strategy review",
                            "action_count": 0,
                            "decision": None,
                        },
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
                            initial_price=benchmark_initial_price,
                            current_price=window[-1].close,
                        ),
                    }
                )
                continue

            if not cadence_boundary_reached:
                steps.append(
                    BacktestStep(
                        timestamp=timestamp,
                        regime="n/a",
                        strategy_name="CadenceGate",
                        signal_count=0,
                        execution_count=0,
                        decision="HOLD",
                        equity_usd=snapshot.equity_usd,
                        drawdown_percent=snapshot.drawdown_percent,
                        trace=[f"hold:decision_cadence_not_reached cadence={decision_cadence_minutes}"],
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
                            initial_price=benchmark_initial_price,
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
                        llm_review={
                            "enabled": bool(isolated_config.llm.enabled),
                            "used": False,
                            "status": "portfolio_guard",
                            "summary": "Trading paused due to max drawdown",
                            "action_count": 0,
                            "decision": None,
                        },
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
                            initial_price=benchmark_initial_price,
                            current_price=window[-1].close,
                        ),
                    }
                )
                halted_reason = "max_drawdown_reached"
                halted_at = timestamp
                halted_snapshot = snapshot
                continue

            regime_state = detect_regime_score(window, features)
            regime = regime_state.regime_label
            context = AgentContext(config=isolated_config)
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
            strategy = self._select_strategy(
                strategy_profile=strategy_profile,
                router=router,
                dca=dca,
                swing=swing,
                hybrid=hybrid,
                pullback=pullback,
                hybrid_pullback=hybrid_pullback,
                regime=regime,
                features=features,
                context=context,
                regime_score=regime_state.regime_score,
                regime_confidence=regime_state.confidence,
                deterioration_score=regime_state.deterioration_score,
            )
            outcome = strategy.generate(context=context, candles=window, features=features)
            signals = order_manager.review_signals(outcome.signals, features=features, regime=regime)
            llm_review = copy.deepcopy(order_manager.last_review_meta)
            execution_results = [*stop_results, *order_manager.execute(signals, decision_timestamp=window[-1].timestamp.replace(microsecond=0).isoformat())]
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
                    llm_review=llm_review,
                    trace=[
                        f"regime_score:{regime_state.regime_score:.3f} confidence:{regime_state.confidence:.3f} deterioration:{regime_state.deterioration_score:.3f}",
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
                        initial_price=benchmark_initial_price,
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
            benchmark_initial_price=benchmark_initial_price,
            benchmark_final_price=candles[-1].close,
            equity_curve=[point["equity_usd"] for point in equity_curve],
            initial_cash=isolated_config.execution.initial_cash_usd,
            trades=trades,
        )

        return BacktestResult(
            symbol=symbol,
            strategy_profile=strategy_profile,
            interval=interval,
            decision_cadence_minutes=decision_cadence_minutes,
            start_at=replay_start_candle.timestamp.replace(microsecond=0).isoformat(),
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

    def _run_buy_and_hold(
        self,
        *,
        symbol: str,
        interval: str,
        candles: list[Candle],
        strategy_profile: str,
    ) -> BacktestResult:
        """Replay a pure buy-and-hold baseline as a first-class strategy profile."""
        replay_start_index = self.config.data.min_candles_required - 1
        replay_start_candle = candles[replay_start_index]
        initial_cash = self.config.execution.initial_cash_usd
        initial_price = replay_start_candle.close
        initial_units = 0.0 if initial_cash <= 0 or initial_price <= 0 else initial_cash / initial_price
        steps: list[BacktestStep] = []
        equity_curve: list[dict[str, object]] = []

        for index in range(self.config.data.min_candles_required, len(candles) + 1):
            window = candles[:index]
            latest_candle = window[-1]
            timestamp = latest_candle.timestamp.replace(microsecond=0).isoformat()
            equity_usd = initial_units * latest_candle.close
            decision = "BUY" if index == self.config.data.min_candles_required else "HOLD"
            trace = (
                [
                    f"decision:buy_and_hold_entry price={initial_price:.2f}",
                    f"signal:buy_and_hold size_usd={initial_cash:.2f}",
                ]
                if decision == "BUY"
                else ["hold:buy_and_hold_position"]
            )
            steps.append(
                BacktestStep(
                    timestamp=timestamp,
                    regime="n/a",
                    strategy_name="BuyAndHoldStrategy",
                    signal_count=1 if decision == "BUY" else 0,
                    execution_count=1 if decision == "BUY" else 0,
                    decision=decision,
                    equity_usd=equity_usd,
                    drawdown_percent=0.0,
                    trace=trace,
                )
            )
            equity_curve.append(
                {
                    "timestamp": timestamp,
                    "equity_usd": equity_usd,
                    "cash_usd": 0.0,
                    "btc_units": initial_units,
                }
            )

        drawdown_values = compute_drawdown_series([point["equity_usd"] for point in equity_curve])
        for step, drawdown in zip(steps, drawdown_values):
            step.drawdown_percent = drawdown
        drawdowns = [
            {"timestamp": point["timestamp"], "drawdown_percent": drawdown}
            for point, drawdown in zip(equity_curve, drawdown_values)
        ]
        metrics = self._build_metrics(
            interval=interval,
            benchmark_initial_price=initial_price,
            benchmark_final_price=candles[-1].close,
            equity_curve=[point["equity_usd"] for point in equity_curve],
            initial_cash=initial_cash,
            trades=[],
        )
        final_equity = equity_curve[-1]["equity_usd"] if equity_curve else initial_cash
        final_snapshot = PortfolioSnapshot(
            cash_usd=0.0,
            btc_units=initial_units,
            equity_usd=final_equity,
            drawdown_percent=drawdown_values[-1] if drawdown_values else 0.0,
            avg_entry_price=initial_price,
            last_mark_price=candles[-1].close,
        )
        benchmark_curve = [{"timestamp": point["timestamp"], "equity_usd": point["equity_usd"]} for point in equity_curve]
        return BacktestResult(
            symbol=symbol,
            strategy_profile=strategy_profile,
            interval=interval,
            decision_cadence_minutes=self._decision_cadence_minutes(),
            start_at=replay_start_candle.timestamp.replace(microsecond=0).isoformat(),
            end_at=candles[-1].timestamp.replace(microsecond=0).isoformat(),
            candles_processed=len(candles),
            metrics=metrics,
            final_snapshot=final_snapshot,
            trades=[],
            steps=steps,
            equity_curve=equity_curve,
            benchmark_curve=benchmark_curve,
            drawdowns=drawdowns,
            halted_reason=None,
            halted_at=None,
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

    @staticmethod
    def _select_strategy(
        *,
        strategy_profile: str,
        router: StrategyRouter,
        dca: DCAStrategy,
        swing: SwingATRStrategy,
        hybrid: HybridStrategy,
        pullback: PullbackTrendStrategy,
        hybrid_pullback: HybridPullbackStrategy,
        regime,
        features,
        context: AgentContext,
        regime_score: float | None = None,
        regime_confidence: float | None = None,
        deterioration_score: float | None = None,
    ):
        """Return the strategy implementation for the selected profile."""
        if strategy_profile == "dca_only":
            return dca
        if strategy_profile == "swing_only":
            return swing
        if strategy_profile == "pullback_only":
            return pullback
        if strategy_profile == "pullback_hybrid":
            return hybrid_pullback
        if strategy_profile == "hybrid_current":
            return router.select(
                regime,
                bullish_trend=features.ema_fast > features.ema_slow,
                has_open_swing_positions=bool(context.active_swing_positions),
                regime_score=regime_score,
                regime_confidence=regime_confidence,
                deterioration_score=deterioration_score,
            )
        return hybrid

    def _build_metrics(
        self,
        interval: str,
        benchmark_initial_price: float,
        benchmark_final_price: float,
        equity_curve: list[float],
        initial_cash: float,
        trades: list[dict[str, object]],
    ) -> BacktestMetrics:
        final_equity = equity_curve[-1] if equity_curve else initial_cash
        total_return_percent = 0.0 if initial_cash == 0 else ((final_equity - initial_cash) / initial_cash) * 100
        buy_hold_return_percent = compute_buy_and_hold_return_percent(
            initial_price=benchmark_initial_price,
            final_price=benchmark_final_price,
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
            if strategy_name not in {"SwingATRStrategy", "PullbackTrendStrategy"} or side != TradeSide.SELL.value:
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
