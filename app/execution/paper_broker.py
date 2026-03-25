"""Paper trading broker with persisted state and trade ledger."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config.schema import AppConfig
from app.execution.broker_interface import BrokerInterface
from app.execution.cost_model import apply_buy_costs, apply_sell_costs
from app.utils.models import OrderRequest, OrderResult, PortfolioSnapshot, SwingPosition, TradeFill, TradeSide


@dataclass(slots=True)
class PaperBrokerState:
    """Persisted paper broker state."""

    cash_usd: float
    dca_btc_units: float
    dca_avg_entry_price: float
    open_swing_positions: list[dict[str, object]]
    last_mark_price: float
    peak_equity: float
    realized_pnl_usd: float
    total_fees_usd: float
    total_spread_cost_usd: float
    total_slippage_cost_usd: float
    updated_at: str


class PaperBroker(BrokerInterface):
    """File-backed paper broker for safe development and testing."""

    def __init__(self, config: AppConfig) -> None:
        """Initialize the simulated broker state."""
        self.config = config
        self.state_path = Path(config.execution.paper_state_path)
        self.trade_log_path = Path(config.execution.paper_trade_log_path)
        self.state = self._load_state()

    def place_order(self, order: OrderRequest) -> OrderResult:
        """Execute a simulated order and persist balances and ledger."""
        self.mark_price(order.price)
        order_id = f"paper-{int(datetime.now(UTC).timestamp() * 1000)}"
        strategy_name = self._resolve_strategy_name(order)
        reference_price = order.price
        fee_pct = self.config.execution.fee_pct
        spread_pct = self.config.execution.spread_pct
        slippage_pct = self.config.execution.slippage_pct

        if order.side is TradeSide.BUY and order.size_usd <= self.state.cash_usd:
            execution = apply_buy_costs(
                market_price=reference_price,
                usd_amount=order.size_usd,
                fee_pct=fee_pct,
                spread_pct=spread_pct,
                slippage_pct=slippage_pct,
            )
            btc_units = execution.btc_units
            self.state.cash_usd -= execution.cash_flow_usd
            self.state.total_fees_usd += execution.fee_usd
            self.state.total_spread_cost_usd += execution.spread_cost_usd
            self.state.total_slippage_cost_usd += execution.slippage_cost_usd
            if strategy_name == "DCAStrategy":
                new_total_cost = (self.state.dca_avg_entry_price * self.state.dca_btc_units) + execution.cash_flow_usd
                new_total_units = self.state.dca_btc_units + btc_units
                self.state.dca_btc_units = new_total_units
                self.state.dca_avg_entry_price = new_total_cost / new_total_units if new_total_units > 0 else 0.0
            else:
                self._append_swing_position(
                    SwingPosition(
                        position_id=order_id,
                        symbol=order.symbol,
                        entry_price=execution.effective_price,
                        stop_loss=order.stop_loss or 0.0,
                        btc_units=btc_units,
                        size_usd=execution.cash_flow_usd,
                        opened_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
                        entry_fee_usd=execution.fee_usd,
                        entry_spread_cost_usd=execution.spread_cost_usd,
                        entry_slippage_cost_usd=execution.slippage_cost_usd,
                    )
                )
            self._append_fill(
                TradeFill(
                    timestamp=datetime.now(UTC),
                    side=order.side,
                    symbol=order.symbol,
                    size_usd=execution.cash_flow_usd,
                    price=execution.effective_price,
                    btc_units=btc_units,
                    order_id=order_id,
                    reason=order.reason or "filled",
                    strategy_name=strategy_name,
                    stop_loss=order.stop_loss,
                    fee_usd=execution.fee_usd,
                    spread_cost_usd=execution.spread_cost_usd,
                    slippage_cost_usd=execution.slippage_cost_usd,
                    execution_cost_usd=execution.execution_cost_usd,
                    reference_price=reference_price,
                )
            )
            self._save_state()
            return OrderResult(
                accepted=True,
                order_id=order_id,
                reason=order.reason or "filled",
                side=order.side,
                symbol=order.symbol,
                size_usd=execution.cash_flow_usd,
                price=execution.effective_price,
                strategy_name=strategy_name,
                stop_loss=order.stop_loss,
                fee_usd=execution.fee_usd,
                spread_cost_usd=execution.spread_cost_usd,
                slippage_cost_usd=execution.slippage_cost_usd,
                execution_cost_usd=execution.execution_cost_usd,
                reference_price=reference_price,
            )

        if order.side is TradeSide.SELL and self._can_sell(order):
            btc_units = order.size_usd / order.price if order.price > 0 else 0.0
            execution = apply_sell_costs(
                market_price=reference_price,
                btc_amount=btc_units,
                fee_pct=fee_pct,
                spread_pct=spread_pct,
                slippage_pct=slippage_pct,
            )
            self.state.cash_usd += execution.cash_flow_usd
            self.state.total_fees_usd += execution.fee_usd
            self.state.total_spread_cost_usd += execution.spread_cost_usd
            self.state.total_slippage_cost_usd += execution.slippage_cost_usd
            realized_pnl_usd: float | None = None
            if strategy_name == "DCAStrategy":
                realized_pnl_usd = execution.cash_flow_usd - (self.state.dca_avg_entry_price * btc_units)
                self.state.dca_btc_units -= btc_units
                if self.state.dca_btc_units <= 0:
                    self.state.dca_btc_units = 0.0
                    self.state.dca_avg_entry_price = 0.0
            else:
                position = self._remove_swing_position(order_id=order.reason.removeprefix("stop_loss_hit:") if order.reason.startswith("stop_loss_hit:") else "")
                if position:
                    entry_cost = float(position.get("size_usd", 0.0))
                    realized_pnl_usd = execution.cash_flow_usd - entry_cost
            if realized_pnl_usd is not None:
                self.state.realized_pnl_usd += realized_pnl_usd
            self._append_fill(
                TradeFill(
                    timestamp=datetime.now(UTC),
                    side=order.side,
                    symbol=order.symbol,
                    size_usd=execution.cash_flow_usd,
                    price=execution.effective_price,
                    btc_units=execution.btc_units,
                    order_id=order_id,
                    reason=order.reason or "filled",
                    strategy_name=strategy_name,
                    stop_loss=order.stop_loss,
                    fee_usd=execution.fee_usd,
                    spread_cost_usd=execution.spread_cost_usd,
                    slippage_cost_usd=execution.slippage_cost_usd,
                    execution_cost_usd=execution.execution_cost_usd,
                    reference_price=reference_price,
                    realized_pnl_usd=realized_pnl_usd,
                )
            )
            self._save_state()
            return OrderResult(
                accepted=True,
                order_id=order_id,
                reason=order.reason or "filled",
                side=order.side,
                symbol=order.symbol,
                size_usd=execution.cash_flow_usd,
                price=execution.effective_price,
                strategy_name=strategy_name,
                stop_loss=order.stop_loss,
                fee_usd=execution.fee_usd,
                spread_cost_usd=execution.spread_cost_usd,
                slippage_cost_usd=execution.slippage_cost_usd,
                execution_cost_usd=execution.execution_cost_usd,
                reference_price=reference_price,
                realized_pnl_usd=realized_pnl_usd,
            )

        return OrderResult(
            accepted=False,
            order_id="",
            reason="insufficient_balance",
            side=order.side,
            symbol=order.symbol,
            size_usd=order.size_usd,
            price=reference_price,
            strategy_name=strategy_name,
            stop_loss=order.stop_loss,
            fee_usd=0.0,
            spread_cost_usd=0.0,
            slippage_cost_usd=0.0,
            execution_cost_usd=0.0,
            reference_price=reference_price,
        )

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Return a point-in-time view of the paper portfolio."""
        swing_units = sum(float(position["btc_units"]) for position in self.state.open_swing_positions)
        total_btc_units = self.state.dca_btc_units + swing_units
        swing_cost = sum(float(position["size_usd"]) for position in self.state.open_swing_positions)
        total_cost = (self.state.dca_avg_entry_price * self.state.dca_btc_units) + swing_cost
        avg_entry_price = total_cost / total_btc_units if total_btc_units > 0 else 0.0
        equity = self.state.cash_usd + (total_btc_units * self.state.last_mark_price)
        self.state.peak_equity = max(self.state.peak_equity, equity)
        drawdown = (
            0.0 if self.state.peak_equity == 0 else ((self.state.peak_equity - equity) / self.state.peak_equity) * 100
        )
        return PortfolioSnapshot(
            cash_usd=self.state.cash_usd,
            btc_units=total_btc_units,
            equity_usd=equity,
            drawdown_percent=drawdown,
            avg_entry_price=avg_entry_price,
            last_mark_price=self.state.last_mark_price,
            dca_btc_units=self.state.dca_btc_units,
            swing_btc_units=swing_units,
            realized_pnl_usd=self.state.realized_pnl_usd,
            total_fees_usd=self.state.total_fees_usd,
            total_spread_cost_usd=self.state.total_spread_cost_usd,
            total_slippage_cost_usd=self.state.total_slippage_cost_usd,
        )

    def mark_price(self, price: float) -> None:
        """Update the last observed mark price and persist broker state."""
        if price <= 0:
            return
        self.state.last_mark_price = price
        total_btc_units = self.state.dca_btc_units + sum(
            float(position["btc_units"]) for position in self.state.open_swing_positions
        )
        equity = self.state.cash_usd + (total_btc_units * self.state.last_mark_price)
        self.state.peak_equity = max(self.state.peak_equity, equity)
        self._save_state()

    def latest_buy_price(self) -> float | None:
        """Return the most recent buy fill price from the trade ledger."""
        if not self.trade_log_path.exists():
            return None
        for line in reversed(self.trade_log_path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("side") == TradeSide.BUY.value:
                return float(payload["price"])
        return None

    def evaluate_stop_losses(self) -> list[OrderResult]:
        """Close any swing positions whose ATR stop-loss has been breached."""
        results: list[OrderResult] = []
        for position in list(self.state.open_swing_positions):
            stop_loss = float(position.get("stop_loss", 0.0))
            if stop_loss <= 0 or self.state.last_mark_price > stop_loss:
                continue
            results.append(
                self.place_order(
                    OrderRequest(
                        side=TradeSide.SELL,
                        symbol=str(position["symbol"]),
                        size_usd=float(position["btc_units"]) * self.state.last_mark_price,
                        price=self.state.last_mark_price,
                        reason=f"stop_loss_hit:{position['position_id']}",
                        strategy_name="SwingATRStrategy",
                        stop_loss=stop_loss,
                    )
                )
            )
        return results

    def active_swing_positions(self) -> list[SwingPosition]:
        """Return the current open swing positions."""
        return [SwingPosition(**position) for position in self.state.open_swing_positions]

    def _load_state(self) -> PaperBrokerState:
        """Load persisted broker state or initialize defaults."""
        if not self.state_path.exists():
            return PaperBrokerState(
                cash_usd=self.config.execution.initial_cash_usd,
                dca_btc_units=0.0,
                dca_avg_entry_price=0.0,
                open_swing_positions=[],
                last_mark_price=0.0,
                peak_equity=self.config.execution.initial_cash_usd,
                realized_pnl_usd=0.0,
                total_fees_usd=0.0,
                total_spread_cost_usd=0.0,
                total_slippage_cost_usd=0.0,
                updated_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            )

        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if "dca_btc_units" not in payload:
            payload = {
                "cash_usd": payload.get("cash_usd", self.config.execution.initial_cash_usd),
                "dca_btc_units": payload.get("btc_units", 0.0),
                "dca_avg_entry_price": payload.get("avg_entry_price", 0.0),
                "open_swing_positions": [],
                "last_mark_price": payload.get("last_mark_price", 0.0),
                "peak_equity": payload.get("peak_equity", self.config.execution.initial_cash_usd),
                "realized_pnl_usd": payload.get("realized_pnl_usd", 0.0),
                "total_fees_usd": payload.get("total_fees_usd", 0.0),
                "total_spread_cost_usd": payload.get("total_spread_cost_usd", 0.0),
                "total_slippage_cost_usd": payload.get("total_slippage_cost_usd", 0.0),
                "updated_at": payload.get("updated_at", datetime.now(UTC).replace(microsecond=0).isoformat()),
            }
        payload.setdefault("realized_pnl_usd", 0.0)
        payload.setdefault("total_fees_usd", 0.0)
        payload.setdefault("total_spread_cost_usd", 0.0)
        payload.setdefault("total_slippage_cost_usd", 0.0)
        return PaperBrokerState(**payload)

    def _save_state(self) -> None:
        """Persist paper broker state atomically."""
        self.state.updated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(asdict(self.state), handle, indent=2)
        temp_path.replace(self.state_path)

    def _append_fill(self, fill: TradeFill) -> None:
        """Append a fill to the trade ledger."""
        self.trade_log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": fill.timestamp.replace(microsecond=0).isoformat(),
            "side": fill.side.value,
            "symbol": fill.symbol,
            "size_usd": fill.size_usd,
            "price": fill.price,
            "btc_units": fill.btc_units,
            "order_id": fill.order_id,
            "reason": fill.reason,
            "strategy_name": fill.strategy_name,
            "stop_loss": fill.stop_loss,
            "fee_usd": fill.fee_usd,
            "spread_cost_usd": fill.spread_cost_usd,
            "slippage_cost_usd": fill.slippage_cost_usd,
            "execution_cost_usd": fill.execution_cost_usd,
            "reference_price": fill.reference_price,
            "realized_pnl_usd": fill.realized_pnl_usd,
        }
        with self.trade_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def _append_swing_position(self, position: SwingPosition) -> None:
        """Persist a newly opened swing position."""
        self.state.open_swing_positions.append(asdict(position))

    def _remove_swing_position(self, order_id: str) -> dict[str, object] | None:
        """Remove a swing position from persisted state."""
        if not order_id:
            return None
        removed: dict[str, object] | None = None
        remaining_positions: list[dict[str, object]] = []
        for position in self.state.open_swing_positions:
            if str(position.get("position_id", "")) == order_id and removed is None:
                removed = position
                continue
            remaining_positions.append(position)
        self.state.open_swing_positions = remaining_positions
        return removed

    def _can_sell(self, order: OrderRequest) -> bool:
        """Return whether a sell request can be satisfied."""
        btc_units = order.size_usd / order.price if order.price > 0 else 0.0
        strategy_name = self._resolve_strategy_name(order)
        if strategy_name == "DCAStrategy":
            return btc_units <= self.state.dca_btc_units
        if order.reason.startswith("stop_loss_hit:"):
            position_id = order.reason.removeprefix("stop_loss_hit:")
            return any(str(position.get("position_id", "")) == position_id for position in self.state.open_swing_positions)
        return btc_units <= sum(float(position["btc_units"]) for position in self.state.open_swing_positions)

    @staticmethod
    def _resolve_strategy_name(order: OrderRequest) -> str:
        """Infer a stable strategy name for backward-compatible broker operations."""
        if order.strategy_name:
            return order.strategy_name
        if "momentum" in order.reason.lower():
            return "SwingATRStrategy"
        return "DCAStrategy"

