"""Deterministic execution cost model for paper trading and backtests."""

from __future__ import annotations

from dataclasses import dataclass


PRESET_COSTS: dict[str, dict[str, float]] = {
    "simple": {"fee_pct": 0.001, "spread_pct": 0.0005, "slippage_pct": 0.0005},
    "advanced": {"fee_pct": 0.005, "spread_pct": 0.001, "slippage_pct": 0.001},
}


@dataclass(slots=True)
class ExecutionCostBreakdown:
    """Normalized execution-cost output."""

    reference_price: float
    effective_price: float
    fee_usd: float
    spread_cost_usd: float
    slippage_cost_usd: float
    execution_cost_usd: float
    btc_units: float
    cash_flow_usd: float


def resolve_execution_costs(
    preset: str,
    fee_pct: float,
    spread_pct: float,
    slippage_pct: float,
) -> tuple[float, float, float]:
    """Resolve a preset into concrete percentages."""
    normalized = (preset or "simple").lower()
    if normalized in PRESET_COSTS and normalized != "custom":
        values = PRESET_COSTS[normalized]
        return values["fee_pct"], values["spread_pct"], values["slippage_pct"]
    return fee_pct, spread_pct, slippage_pct


def apply_buy_costs(
    market_price: float,
    usd_amount: float,
    fee_pct: float,
    spread_pct: float,
    slippage_pct: float,
) -> ExecutionCostBreakdown:
    """Apply the deterministic cost model to a buy."""
    effective_price = market_price * (1 + spread_pct + slippage_pct)
    fee_usd = usd_amount * fee_pct
    spread_cost_usd = usd_amount * spread_pct
    slippage_cost_usd = usd_amount * slippage_pct
    btc_bought = 0.0 if effective_price <= 0 else max(usd_amount - fee_usd, 0.0) / effective_price
    return ExecutionCostBreakdown(
        reference_price=market_price,
        effective_price=effective_price,
        fee_usd=fee_usd,
        spread_cost_usd=spread_cost_usd,
        slippage_cost_usd=slippage_cost_usd,
        execution_cost_usd=fee_usd + spread_cost_usd + slippage_cost_usd,
        btc_units=btc_bought,
        cash_flow_usd=usd_amount,
    )


def apply_sell_costs(
    market_price: float,
    btc_amount: float,
    fee_pct: float,
    spread_pct: float,
    slippage_pct: float,
) -> ExecutionCostBreakdown:
    """Apply the deterministic cost model to a sell."""
    effective_price = market_price * (1 - spread_pct - slippage_pct)
    gross_usd = btc_amount * effective_price
    reference_notional = btc_amount * market_price
    fee_usd = gross_usd * fee_pct
    spread_cost_usd = reference_notional * spread_pct
    slippage_cost_usd = reference_notional * slippage_pct
    usd_received = gross_usd - fee_usd
    return ExecutionCostBreakdown(
        reference_price=market_price,
        effective_price=effective_price,
        fee_usd=fee_usd,
        spread_cost_usd=spread_cost_usd,
        slippage_cost_usd=slippage_cost_usd,
        execution_cost_usd=fee_usd + spread_cost_usd + slippage_cost_usd,
        btc_units=btc_amount,
        cash_flow_usd=usd_received,
    )
