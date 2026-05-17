"""Parameter-sweep simulation engine built on the backtest runtime."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from itertools import product

from app.backtest.engine import BacktestEngine, BacktestResult
from app.config.schema import AppConfig
from app.strategies.profiles import normalize_strategy_profile


@dataclass(slots=True)
class SimulationCandidate:
    """One parameter-set evaluation result."""

    candidate_id: str
    params: dict[str, float | int]
    result: BacktestResult


@dataclass(slots=True)
class SimulationResult:
    """Container for one simulation sweep."""

    symbol: str
    strategy_profile: str
    interval: str
    decision_cadence_minutes: int
    start_at: str
    end_at: str
    candidate_count: int
    candidates: list[SimulationCandidate]
    best_candidate_id: str
    parameter_grid: dict[str, list[float | int]]


class SimulationEngine:
    """Run a bounded parameter sweep against the current strategy stack."""

    MAX_CANDIDATES = 120

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def run(
        self,
        *,
        symbol: str | None = None,
        interval: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        parameter_grid: dict[str, list[float | int]],
        strategy_profile: str | None = None,
    ) -> SimulationResult:
        symbol = symbol or self.config.trading.symbol
        interval = interval or self.config.ingestion.interval
        strategy_profile = normalize_strategy_profile(strategy_profile)
        candidates: list[SimulationCandidate] = []
        for index, params in enumerate(self._parameter_sets(parameter_grid, strategy_profile=strategy_profile), start=1):
            candidate_config = self._configured_candidate(params)
            result = BacktestEngine(candidate_config).run(
                symbol=symbol,
                interval=interval,
                start_at=start_at,
                end_at=end_at,
                strategy_profile=strategy_profile,
            )
            candidates.append(
                SimulationCandidate(
                    candidate_id=f"sim-{index:03d}",
                    params=params,
                    result=result,
                )
            )

        ranked_candidates = sorted(candidates, key=self._ranking_key, reverse=True)
        if not ranked_candidates:
            raise ValueError("simulation_requires_at_least_one_parameter_combination")
        best_candidate = ranked_candidates[0]
        return SimulationResult(
            symbol=symbol,
            strategy_profile=strategy_profile,
            interval=interval,
            decision_cadence_minutes=max(1, int(self.config.runtime.decision_cadence_minutes)),
            start_at=best_candidate.result.start_at,
            end_at=best_candidate.result.end_at,
            candidate_count=len(ranked_candidates),
            candidates=ranked_candidates,
            best_candidate_id=best_candidate.candidate_id,
            parameter_grid=parameter_grid,
        )

    def _parameter_sets(
        self,
        parameter_grid: dict[str, list[float | int]],
        *,
        strategy_profile: str,
    ) -> list[dict[str, float | int]]:
        if strategy_profile in {"buy_and_hold", "dca_only"}:
            return [{}]
        keys = list(parameter_grid.keys())
        value_sets = [parameter_grid[key] for key in keys]
        combinations = [dict(zip(keys, combo, strict=True)) for combo in product(*value_sets)]
        if len(combinations) > self.MAX_CANDIDATES:
            raise ValueError(f"simulation_candidate_limit_exceeded:{len(combinations)}>{self.MAX_CANDIDATES}")
        return combinations

    def _configured_candidate(self, params: dict[str, float | int]) -> AppConfig:
        config = copy.deepcopy(self.config)
        if not params:
            return config
        config.trading.swing_entry_rsi_max = float(params["swing_entry_rsi_max"])
        config.trading.swing_take_profit_percent = float(params["swing_take_profit_percent"])
        config.trading.swing_no_follow_through_candles = int(params["swing_no_follow_through_candles"])
        config.trading.swing_follow_through_buffer_percent = float(params["swing_follow_through_buffer_percent"])
        config.trading.atr_multiplier = float(params["atr_multiplier"])
        return config

    @staticmethod
    def _ranking_key(candidate: SimulationCandidate) -> tuple[float, float, float, float]:
        metrics = candidate.result.metrics
        return (
            float(metrics.total_return_percent),
            -float(metrics.max_drawdown_percent),
            float(metrics.profit_factor),
            float(metrics.sharpe_ratio),
        )
