"""Shared domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.config.schema import AppConfig


class TradeSide(str, Enum):
    """Supported trade sides."""

    BUY = "buy"
    SELL = "sell"


class MarketRegime(str, Enum):
    """Supported market regimes."""

    BULLISH = "bullish"
    WEAKENING_BULL = "weakening_bull"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    TRANSITION = "transition"


@dataclass(slots=True)
class Candle:
    """Normalized OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class FeatureSet:
    """Computed indicator bundle."""

    last_price: float = 0.0
    atr: float = 0.0
    rsi: float = 50.0
    ema_fast: float = 0.0
    ema_slow: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0


@dataclass(slots=True)
class Signal:
    """Strategy-generated trade signal."""

    side: TradeSide
    symbol: str
    size_usd: float
    reason: str
    reference_price: float = 0.0
    stop_loss: float | None = None
    decision_timestamp: str = ""
    strategy_name: str = ""


@dataclass(slots=True)
class StrategyOutcome:
    """Strategy decision bundle including trace details."""

    strategy_name: str
    signals: list[Signal]
    trace: list[str]


@dataclass(slots=True)
class StrategySelection:
    """Deterministic selector decision for multi-strategy profiles."""

    mode: str
    allow_dca: bool
    allow_pullback: bool
    trace: list[str]


@dataclass(slots=True)
class OrderRequest:
    """Broker order request."""

    side: TradeSide
    symbol: str
    size_usd: float
    price: float
    reason: str = ""
    stop_loss: float | None = None
    decision_timestamp: str = ""
    strategy_name: str = ""


@dataclass(slots=True)
class OrderResult:
    """Broker order result."""

    accepted: bool
    order_id: str
    reason: str
    side: TradeSide | None = None
    symbol: str = ""
    size_usd: float = 0.0
    price: float = 0.0
    strategy_name: str = ""
    stop_loss: float | None = None
    fee_usd: float = 0.0
    spread_cost_usd: float = 0.0
    slippage_cost_usd: float = 0.0
    execution_cost_usd: float = 0.0
    reference_price: float = 0.0
    realized_pnl_usd: float | None = None


@dataclass(slots=True)
class PortfolioSnapshot:
    """Current portfolio state."""

    cash_usd: float
    btc_units: float
    equity_usd: float
    drawdown_percent: float
    avg_entry_price: float = 0.0
    last_mark_price: float = 0.0
    dca_btc_units: float = 0.0
    swing_btc_units: float = 0.0
    realized_pnl_usd: float = 0.0
    total_fees_usd: float = 0.0
    total_spread_cost_usd: float = 0.0
    total_slippage_cost_usd: float = 0.0


@dataclass(slots=True)
class TradeFill:
    """Executed paper trade fill."""

    timestamp: datetime
    side: TradeSide
    symbol: str
    size_usd: float
    price: float
    btc_units: float
    order_id: str
    reason: str
    strategy_name: str = ""
    stop_loss: float | None = None
    fee_usd: float = 0.0
    spread_cost_usd: float = 0.0
    slippage_cost_usd: float = 0.0
    execution_cost_usd: float = 0.0
    reference_price: float = 0.0
    realized_pnl_usd: float | None = None


@dataclass(slots=True)
class SwingPosition:
    """Persisted opportunistic swing position with ATR stop-loss."""

    position_id: str
    symbol: str
    entry_price: float
    stop_loss: float
    btc_units: float
    size_usd: float
    opened_at: str
    origin_strategy: str = ""
    strategy_name: str = ""
    entry_fee_usd: float = 0.0
    entry_spread_cost_usd: float = 0.0
    entry_slippage_cost_usd: float = 0.0


@dataclass(slots=True)
class LLMSignalAction:
    """Bounded per-signal review action returned by the LLM."""

    signal_index: int
    action: str
    size_multiplier: float
    rationale: str


@dataclass(slots=True)
class LLMAdvice:
    """Bounded advisory payload."""

    summary: str
    parameter_suggestions: dict[str, float]
    signal_actions: list[LLMSignalAction] = field(default_factory=list)
    decision: LLMDecision | None = None
    decision_present: bool = False
    decision_valid: bool = False
    enabled: bool = False
    used: bool = False
    status: str = ""


@dataclass(slots=True)
class LLMInput:
    """Structured input passed to the LLM decision layer."""

    regime: str
    trend: str
    volatility: str
    rsi: float
    atr_percent: float
    recent_return: float
    drawdown: float
    position_size: float


@dataclass(slots=True)
class LLMDecision:
    """Structured single-action LLM decision."""

    action: str
    confidence: float
    reason: str
    reason_code: str = ""
    score: float = 0.0


@dataclass(slots=True)
class RegimeDiagnostics:
    """Structure and momentum diagnostics used to derive a regime score."""

    swing_count: int = 0
    high_count: int = 0
    low_count: int = 0
    rising_high_ratio: float = 0.0
    rising_low_ratio: float = 0.0
    falling_high_ratio: float = 0.0
    falling_low_ratio: float = 0.0
    last_price_vs_prior_low: float = 0.0
    ema_spread_percent: float = 0.0
    rsi_centered: float = 0.0
    macd_histogram_percent: float = 0.0
    atr_percent: float = 0.0


@dataclass(slots=True)
class RegimeScore:
    """Continuous regime view used for routing and logging."""

    regime_label: MarketRegime
    structure_score: float
    momentum_score: float
    regime_score: float
    confidence: float
    deterioration_score: float
    diagnostics: RegimeDiagnostics = field(default_factory=RegimeDiagnostics)


@dataclass(slots=True)
class AgentContext:
    """Runtime context passed into strategies."""

    config: AppConfig
    market_regime: MarketRegime | None = None
    latest_buy_fill_price: float | None = None
    latest_dca_buy_price: float | None = None
    active_swing_positions: list[SwingPosition] = field(default_factory=list)
    portfolio_snapshot: PortfolioSnapshot | None = None
    regime_score: float | None = None
    regime_confidence: float | None = None
    regime_deterioration: float | None = None
    regime_diagnostics: dict[str, object] = field(default_factory=dict)
    available_cash_usd: float = field(init=False)

    def __post_init__(self) -> None:
        """Populate derived context values."""
        self.available_cash_usd = self.config.execution.initial_cash_usd
