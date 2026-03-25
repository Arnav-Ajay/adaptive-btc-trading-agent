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
    BEARISH = "bearish"
    SIDEWAYS = "sideways"


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
    strategy_name: str = ""


@dataclass(slots=True)
class StrategyOutcome:
    """Strategy decision bundle including trace details."""

    strategy_name: str
    signals: list[Signal]
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
    entry_fee_usd: float = 0.0


@dataclass(slots=True)
class LLMAdvice:
    """Bounded advisory payload."""

    summary: str
    parameter_suggestions: dict[str, float]


@dataclass(slots=True)
class AgentContext:
    """Runtime context passed into strategies."""

    config: AppConfig
    latest_buy_fill_price: float | None = None
    available_cash_usd: float = field(init=False)

    def __post_init__(self) -> None:
        """Populate derived context values."""
        self.available_cash_usd = self.config.execution.initial_cash_usd
