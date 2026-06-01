# Metrics Reference

This document is the authoritative reference for current project metrics and market features.

Ownership boundary:
- feature definitions
- formulas
- execution cost formulas
- metric interpretation at the project level

This document does not define:
- strategy rules
- service architecture
- future experimentation plans

## 1. Scope

**Status: CURRENT IMPLEMENTATION**

This reference covers currently used market and execution metrics:
- last price
- ATR
- RSI
- EMA fast / EMA slow
- MACD
- MACD signal
- MACD histogram
- execution cost components

## 2. Last Price

**Status: CURRENT IMPLEMENTATION**

Definition:
- close of the most recent candle in the trading lookback window

Source:
- [app/features/indicators.py](../app/features/indicators.py)

Project usage:
- strategy reference price
- broker mark price
- execution reference price

## 3. ATR

**Status: CURRENT IMPLEMENTATION**

Definition:
- Average True Range

Source:
- [app/features/atr.py](../app/features/atr.py)

Formula:

```text
true_range = max(
    high - low,
    abs(high - previous_close),
    abs(low - previous_close),
)

ATR = average of last 14 true ranges
```

Current project usage:
- swing strategy stop-loss distance
- regime diagnostics through `atr_percent`

## 4. RSI

**Status: CURRENT IMPLEMENTATION**

Definition:
- Relative Strength Index

Source:
- [app/features/rsi.py](../app/features/rsi.py)

Formula:

```text
delta = close_t - close_t-1
avg_gain = average(last 14 positive deltas)
avg_loss = average(last 14 absolute negative deltas)
RS = avg_gain / avg_loss
RSI = 100 - 100 / (1 + RS)
```

Current project usage:
- swing entry filter
- regime scoring

## 5. EMA Fast and EMA Slow

**Status: CURRENT IMPLEMENTATION**

Definition:
- Exponential moving averages over close prices

Source:
- [app/features/macd.py](../app/features/macd.py)

Current periods:
- fast EMA = `12`
- slow EMA = `26`

Current project usage:
- swing entry filter
- swing trend exit
- regime scoring

## 6. MACD

**Status: CURRENT IMPLEMENTATION**

Definition:
- Moving Average Convergence Divergence

Source:
- [app/features/macd.py](../app/features/macd.py)

Formula:

```text
MACD = EMA(12) - EMA(26)
```

Current project usage:
- feature bundle
- regime scoring

## 7. MACD Signal

**Status: CURRENT IMPLEMENTATION**

Definition:
- 9-period EMA of MACD

Source:
- [app/features/macd.py](../app/features/macd.py)

Current project usage:
- indirect, through MACD histogram

## 8. MACD Histogram

**Status: CURRENT IMPLEMENTATION**

Definition:

```text
MACD_histogram = MACD - MACD_signal
```

Source:
- [app/features/macd.py](../app/features/macd.py)

Current project usage:
- swing entry requires `macd_histogram > 0`
- swing trend exit triggers when `macd_histogram <= 0`
- regime scoring

## 9. Execution Costs

**Status: CURRENT IMPLEMENTATION**

Primary modules:
- [app/execution/cost_model.py](../app/execution/cost_model.py)
- [app/execution/paper_broker.py](../app/execution/paper_broker.py)

Current cost components:
- fee
- spread
- slippage

### Buy Model

```text
effective_price = market_price * (1 + spread_pct + slippage_pct)
fee_usd = usd_amount * fee_pct
spread_cost_usd = usd_amount * spread_pct
slippage_cost_usd = usd_amount * slippage_pct
btc_bought = max(usd_amount - fee_usd, 0) / effective_price
execution_cost_usd = fee_usd + spread_cost_usd + slippage_cost_usd
cash_flow_usd = usd_amount
```

### Sell Model

```text
effective_price = market_price * (1 - spread_pct - slippage_pct)
gross_usd = btc_amount * effective_price
reference_notional = btc_amount * market_price
fee_usd = gross_usd * fee_pct
spread_cost_usd = reference_notional * spread_pct
slippage_cost_usd = reference_notional * slippage_pct
usd_received = gross_usd - fee_usd
execution_cost_usd = fee_usd + spread_cost_usd + slippage_cost_usd
cash_flow_usd = usd_received
```

Current project usage:
- paper trading
- backtesting
- simulation
- weekly reporting

## 10. Portfolio Snapshot Metrics

**Status: CURRENT IMPLEMENTATION**

Source:
- [app/execution/paper_broker.py](../app/execution/paper_broker.py)
- `get_portfolio_snapshot()`

Current snapshot fields:
- `cash_usd`
- `btc_units`
- `equity_usd`
- `drawdown_percent`
- `avg_entry_price`
- `last_mark_price`
- `dca_btc_units`
- `swing_btc_units`
- `realized_pnl_usd`
- `total_fees_usd`
- `total_spread_cost_usd`
- `total_slippage_cost_usd`

Key formulas:

```text
total_btc_units = dca_btc_units + swing_btc_units
equity_usd = cash_usd + (total_btc_units * last_mark_price)
avg_entry_price = total_cost / total_btc_units
drawdown_percent = ((peak_equity - equity_usd) / peak_equity) * 100
```

## 11. Backtest Metrics

**Status: CURRENT IMPLEMENTATION**

Primary module:
- [app/backtest/metrics.py](../app/backtest/metrics.py)

Current persisted backtest metrics include:
- `initial_equity_usd`
- `final_equity_usd`
- `total_return_percent`
- `buy_and_hold_return_percent`
- `max_drawdown_percent`
- `sharpe_ratio`
- `trade_count`
- `filled_trade_count`
- `closed_trade_count`
- `win_rate_percent`
- `avg_win_usd`
- `avg_loss_usd`
- `profit_factor`

Detailed formulas should be validated directly against:
- [app/backtest/metrics.py](../app/backtest/metrics.py)

## 12. Experimental Surface

### Structure-Derived Diagnostics

**Status: EXPERIMENTAL**

The repo still computes scored regime diagnostics such as:
- `structure_score`
- `momentum_score`
- `regime_score`
- `confidence`
- `deterioration_score`

These are active in runtime, but the broader structure-research direction is not part of the active project scope.

## 13. Ownership Boundaries Between Documents

**Status: CURRENT IMPLEMENTATION**

- [01_architecture.md](./01_architecture.md)
  - system shape and boundaries
- [02_strategy_specification.md](./02_strategy_specification.md)
  - strategy rules
- [03_metrics_reference.md](./03_metrics_reference.md)
  - formulas and metric semantics
- [04_llm_architecture.md](./04_llm_architecture.md)
  - AI-layer integration
- [05_future_work.md](./05_future_work.md)
  - roadmap only
