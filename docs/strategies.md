# Strategies

This document describes the strategies and trading controls currently present in the project.

It reflects what the code does today.

## Regime Detection

- Code: [app/features/regime_features.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/regime_features.py)
- Purpose: classify market conditions before choosing a strategy.

Current rules:

- Bullish:
  - `ema_fast > ema_slow`
  - `rsi >= 55`
- Bearish:
  - `ema_fast < ema_slow`
  - `rsi <= 45`
- Sideways:
  - anything else

Project perspective:

- This is a lightweight deterministic regime classifier.
- It does not use volume, on-chain metrics, or LLM input.

## DCA Strategy

- Code: [app/strategies/dca.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/dca.py)
- Purpose: accumulate BTC gradually as the base strategy layer.

Current rules:

- If no prior buy fill exists:
  - place an initial DCA buy
- Else:
  - compute the next dip threshold from the latest buy fill in the ledger:
    - `latest_buy_fill_price * (1 - dca_drop_percent / 100)`
  - if `last_price <= threshold`, place another DCA buy
  - otherwise skip

Inputs:

- latest buy fill price from the persisted trade ledger
- current last price
- `dca_drop_percent`
- `dca_order_size_usd`

Project perspective:

- It is persistent across runs because it reads the prior buy state from the ledger.
- It does not yet support time-based DCA intervals.
- It now explains its threshold basis in the Trades-page decision breakdown.

Example:

- Latest buy at `70,210.01`, DCA drop `3%`
- Next trigger price becomes `68,103.71`
- If BTC is `70,284.96`, skip
- If BTC falls to `67,900`, buy

## Swing ATR Strategy

- Code: [app/strategies/swing_atr.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/swing_atr.py)
- Purpose: take opportunistic momentum entries and manage exits on tracked swing positions.

Current entry rules:

- `last_price > 0`
- `atr > 0`
- `rsi < swing_entry_rsi_max`
- `macd_histogram > 0`
- `ema_fast > ema_slow`

If all pass:

- create a buy signal
- set signal size to `min(250, available_cash_usd)`
- attach stop loss:
  - `stop_loss = last_price - atr_multiplier * atr`

Current exit rules for open swing positions:

- take profit if:
  - `last_price >= entry_price * (1 + swing_take_profit_percent / 100)`
- no follow-through exit if:
  - at least `swing_no_follow_through_candles` candles have passed since entry
  - and price is still below:
    - `entry_price * (1 + swing_follow_through_buffer_percent / 100)`
- signal exit if:
  - `macd_histogram <= 0`
  - or `ema_fast <= ema_slow`
- defensive stop-loss exit if mark price breaches the tracked stop level

Project perspective:

- Entry and sell-exit logic now exist for the swing layer.
- Entry is now intentionally much stricter to reduce trade churn.
- ATR stop-loss values are attached to swing entries.
- Open swing positions are tracked separately from DCA holdings.
- Stop-loss checks run before new entries in each trading cycle.
- If a swing stop-loss exit fires, the live trading cycle now skips fresh entries for that same cycle.
- Backtests now continue after a swing stop-loss exit instead of terminating the whole replay.

Example:

- `last_price = 62,500`
- `atr = 1,000`
- `atr_multiplier = 1.5`
- stop loss becomes `61,000`

## Hybrid Strategy

- Code: [app/strategies/hybrid.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/hybrid.py)
- Purpose: keep DCA as the base layer while allowing swing opportunities in bullish regimes.

Current behavior:

- always run DCA
- also run swing logic
- merge both signal sets and decision traces

Project perspective:

- This is the current approximation of the project's intended hybrid behavior.
- It is used in bullish regimes for fresh entries.
- It also remains active while open swing positions exist so swing exits can still be generated outside bullish regimes.
- Trades-page decision breakdowns now surface the DCA and swing component outcomes separately when Hybrid produces no trade.

## Strategy Router

- Code: [app/strategies/router.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/router.py)
- Purpose: select which strategy stack to run based on regime.

Current routing:

- bullish -> `HybridStrategy`
- bearish -> `DCAStrategy`
- sideways -> `DCAStrategy`
- exception:
  - if an open swing position exists, keep `HybridStrategy` active so the swing layer can emit sell exits

## Portfolio Guard

- Code: [app/strategies/portfolio_guard.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/portfolio_guard.py)
- Purpose: stop new trades when drawdown becomes too large.

Current rule:

- pause trading if:
  - `drawdown_percent >= max_drawdown_percent`

Backtest behavior:

- the same guard now halts historical replay early once the drawdown limit is breached

## Capital Allocator

- Code: [app/strategies/capital_allocator.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/capital_allocator.py)
- Purpose: prevent signals from exceeding available cash.

Current behavior:

- clamp each signal size to remaining cash
- skip zero or negative sizes
- process signals sequentially
