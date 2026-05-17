# LLM Runtime Logic

This document explains the current trading runtime flow with:

- `LLM_ENABLED=false`
- `LLM_ENABLED=true`

It focuses on the actual implementation as it exists now in the repository.

Relevant entry points:

- trading cycle: [app/main.py](../app/main.py)
- worker loop: [app/scheduler/worker_runner.py](../app/scheduler/worker_runner.py)
- market data + features: [app/data/data_normalizer.py](../app/data/data_normalizer.py)
- strategy routing: [app/strategies/router.py](../app/strategies/router.py)
- pullback hybrid: [app/strategies/hybrid_pullback.py](../app/strategies/hybrid_pullback.py)
- pullback selector: [app/strategies/pullback_selector.py](../app/strategies/pullback_selector.py)
- DCA logic: [app/strategies/dca.py](../app/strategies/dca.py)
- swing logic: [app/strategies/swing_atr.py](../app/strategies/swing_atr.py)
- pullback logic: [app/strategies/pullback_trend.py](../app/strategies/pullback_trend.py)
- order review: [app/execution/order_manager.py](../app/execution/order_manager.py)
- LLM review: [app/llm/advisor.py](../app/llm/advisor.py)
- LLM action enforcement: [app/llm/validator.py](../app/llm/validator.py)
- execution + persistence: [app/execution/paper_broker.py](../app/execution/paper_broker.py)
- cycle journal: [app/monitoring/trading_journal.py](../app/monitoring/trading_journal.py)

Current overlay contract:

- the LLM now emits a top-level `decision`
- the decision contains:
  - `action`
  - `confidence`
  - `reason`
  - `reason_code`
  - `score`
- the evaluation harness can replay the overlay in three score-based modes:
  - `llm_hard`
  - `llm_soft`
  - `llm_weighted`

## 1. Runtime Boundary

The long-running runtime is the combined worker in [app/scheduler/worker_runner.py](../app/scheduler/worker_runner.py).

One worker cycle is:

```text
ingestion
-> local parquet is updated
-> trading cycle starts
-> trading cycle ends
-> worker sleeps until next aligned schedule boundary
```

The trading cycle itself starts inside `run_cycle()` in [app/main.py](../app/main.py).

The trading cycle ends after one of these outcomes:

- market data is not ready and the cycle returns early
- a stop-loss exit is triggered and the cycle records that exit, notifies, then returns early
- strategies run, signals are reviewed, orders are executed, state is persisted, notifications are sent, then the cycle returns normally

So:

- start = `run_cycle()` is entered
- end = `run_cycle()` returns

## 2. Common Flow Before LLM

These steps happen whether LLM is enabled or disabled.

### 2.1 Inputs at Cycle Start

Inputs loaded or derived at the start of each cycle:

- app config from `.env` / config cache / future sheet loader
- latest local BTC candles from parquet
- persisted broker state
- persisted trade ledger
- current cycle number from the journal

### 2.2 Market Data Readiness Check

In [app/data/data_normalizer.py](../app/data/data_normalizer.py), the runtime:

1. loads candles from the local parquet lake
2. checks minimum candle count
3. checks staleness of the latest candle

If either check fails:

- no indicators are computed
- no strategy runs
- no LLM runs
- no orders are placed
- the cycle ends early

### 2.3 Feature Calculations

If data is ready, the runtime computes the feature bundle:

- `last_price`
- `atr`
- `rsi`
- `ema_fast`
- `ema_slow`
- `macd`
- `macd_signal`
- `macd_histogram`

These are produced by `compute_features()` in [app/data/data_normalizer.py](../app/data/data_normalizer.py).

### 2.4 Regime Detection

The runtime then classifies the market regime via `detect_regime()`:

- `bullish`
- `weakening_bull`
- `bearish`
- `sideways`

This regime is used before the LLM step. The deterministic regime is still the primary gating signal.

### 2.5 Stop-Loss Evaluation

Before new entries are considered, the runtime:

1. marks the latest price in the paper broker
2. checks open swing positions for ATR stop-loss breaches

If a stop-loss sell executes:

- those sell orders are persisted
- the cycle is recorded
- notifications are sent
- no new entry signals are considered in that cycle
- the cycle ends

This is an important boundary:

- stop-loss processing happens before strategy generation
- the LLM does not participate in stop-loss exits

### 2.6 Strategy Selection

There are now two distinct deterministic selection patterns in the repo:

- legacy router path:
  - `DCAStrategy`
  - `HybridStrategy`
- selector-first pullback path:
  - `PullbackTrendStrategy`
  - `HybridPullbackStrategy`

`HybridStrategy` combines:

- `DCAStrategy`
- `SwingATRStrategy`

`HybridPullbackStrategy` runs in this order:

1. run `PullbackTrendStrategy`
2. pass the pullback outcome into `PullbackHybridSelector`
3. let the selector decide whether DCA is allowed that cycle
4. if allowed, run `DCAStrategy`
5. combine both outcomes into one deterministic signal set

### 2.7 Deterministic Strategy Decisions

The strategy layer generates raw candidate signals.

#### DCA logic currently uses:

- latest buy fill price
- configured DCA drop %
- BTC allocation cap
- regime gating
- regime-aware DCA size scaling
- regime-aware rebalance sells

Possible DCA outcomes:

- no signal
- DCA buy
- DCA rebalance sell

#### Swing logic currently uses:

- RSI threshold
- MACD histogram direction
- EMA fast vs EMA slow
- ATR stop-loss calculation
- take-profit threshold
- no-follow-through exit
- signal-based exit

Possible swing outcomes:

- no signal
- swing buy with ATR stop-loss
- swing sell

#### Pullback logic currently uses:

- bullish regime gate
- `ema_fast > ema_slow`
- confirmed higher-high / higher-low structure
- retracement band check
- stabilization check
- RSI band
- non-negative MACD histogram

Possible pullback outcomes:

- no signal
- pullback buy with ATR-based structural stop
- pullback sell for take-profit / no-follow-through / signal exit

#### Selector logic inside `pullback_hybrid` currently uses:

- current regime
- current BTC allocation
- whether a pullback-managed position is open
- whether a new pullback entry signal exists

Possible selector outcomes:

- allow DCA in bullish support mode
- suppress DCA because pullback has priority
- suppress DCA because regime is risk-off for the hybrid profile

At this point the runtime has a list of raw deterministic `Signal` objects.

## 3. Flow With `LLM_ENABLED=false`

This is the simpler path.

### 3.1 LLM Step

The runtime still calls the advisory layer through [app/execution/order_manager.py](../app/execution/order_manager.py), but [app/llm/advisor.py](../app/llm/advisor.py) immediately returns:

- summary: `"LLM disabled"`
- no per-signal actions
- no parameter suggestions

### 3.2 Review Decision

Because there are no LLM actions:

- no signal is blocked
- no signal size is reduced
- no signal is added
- no signal reason is rewritten

So the final signal list is just the deterministic strategy output after risk guard and capital allocator processing.

### 3.3 Execution

Signals are executed in the paper broker:

- buy orders reduce cash and add BTC exposure
- sell orders increase cash and reduce BTC exposure
- fees, spread, and slippage are applied
- realized PnL is updated when positions close

### 3.4 Outputs

Outputs written by the cycle:

- paper broker state JSON
- trade ledger JSONL
- cycle log JSONL
- decision trace JSONL
- latest portfolio snapshot JSON
- log messages
- optional cycle notification

### 3.5 What the LLM is doing in this mode

Nothing. In this mode the LLM path is bypassed logically.

## 4. Flow With `LLM_ENABLED=true`

This path includes one additional review stage between deterministic signal generation and final execution.

### 4.1 Inputs Sent to the LLM

After deterministic signals are created, the runtime sends a bounded review payload to the OpenAI API.

Current payload includes:

- current regime
- market indicators:
  - last price
  - ATR
  - RSI
  - EMA fast
  - EMA slow
  - MACD
  - MACD signal
  - MACD histogram
- current portfolio state:
  - cash
  - BTC units
  - equity
  - drawdown
  - DCA BTC units
  - swing BTC units
- candidate signals:
  - signal index
  - side
  - symbol
  - size in USD
  - reason
  - reference price
  - stop-loss
  - strategy name

The model does not receive permission to create arbitrary trades.

### 4.2 What Decision the LLM Can Make

The model can only review each existing signal and suggest one of:

- `allow`
- `reduce`
- `block`

It also returns:

- a text summary
- a top-level structured decision
- a signed score in `[-1.0, 1.0]`
- optional numeric parameter suggestions for logging/review

### 4.3 What the LLM Cannot Do

The current implementation does **not** allow the model to:

- create a new buy or sell signal
- change the side of a signal
- change symbol
- increase signal size above the deterministic size
- bypass the global portfolio guard
- bypass stop-loss execution
- place live trades

### 4.4 LLM Output Validation

The runtime sanitizes the LLM output before using it.

Validation rules include:

- invalid signal indexes are ignored
- duplicate actions on the same signal are ignored after the first accepted one
- invalid action names are ignored
- size multipliers are clamped
- `allow` becomes size multiplier `1.0`
- `block` becomes size multiplier `0.0`
- only specific numeric parameter suggestions are kept

### 4.5 Actual Runtime Effect of the LLM

After validation:

- `allow` keeps the signal unchanged
- `reduce` keeps the signal but shrinks `size_usd`
- `block` removes the signal from execution

The score is currently used by the evaluation harness, not as a direct live execution rule.
Live execution still uses the bounded per-signal actions plus the deterministic allocator.

Then the normal capital allocator still runs afterward.

So the LLM is currently acting as:

- a bounded risk filter
- a bounded trade-size reducer

It is **not** currently:

- a feature generator
- a regime classifier
- a strategy selector
- an execution agent

### 4.6 Execution After LLM Review

Once the LLM-reviewed signals are finalized, execution is identical to the non-LLM path:

- paper broker executes the orders
- fees / spread / slippage are applied
- fills are written
- state is updated
- cycle journal is written
- notification manager runs

### 4.7 Outputs in This Mode

Everything from the non-LLM path still happens, plus:

- LLM review summary is logged
- number of reviewed actions is logged
- parameter suggestions are logged

Current limitation:

- LLM decisions are not yet separately persisted as their own dedicated audit artifact
- they only appear in logs, not as a structured standalone history file

## 5. Side-by-Side Summary

### 5.1 Start Condition

Both modes start the same way:

```text
worker cycle starts
-> candles loaded
-> readiness checked
-> indicators computed
-> regime detected
-> stop-losses checked
-> deterministic strategy generates signals
```

### 5.2 Divergence Point

The flow diverges inside `OrderManager.review_signals()`.

#### `LLM_ENABLED=false`

```text
deterministic signals
-> LLM returns "disabled"
-> no signal changes
-> capital allocation
-> execution
```

#### `LLM_ENABLED=true`

```text
deterministic signals
-> OpenAI review request
-> sanitize advisory output
-> block / reduce / allow existing signals
-> capital allocation
-> execution
```

### 5.3 End Condition

Both modes end the same way:

```text
execution results finalized
-> state persisted
-> cycle journal written
-> notifications emitted
-> run_cycle() returns
```

## 6. Concrete Question: What Is the LLM Actually Doing?

Current answer:

- it reviews deterministic candidate trades after the strategies have already decided what to do
- it can suppress weak trades
- it can reduce the size of marginal trades
- it cannot originate trades
- it cannot override core deterministic risk boundaries
- it now emits a score that the evaluation harness uses for hard, soft, and weighted replay modes

So the current LLM role is:

- post-strategy trade review

It is not yet:

- adaptive strategy control
- autonomous feature engineering
- dynamic regime modeling

## 7. Practical Interpretation

### If `LLM_ENABLED=false`

You are running a fully deterministic strategy system.

### If `LLM_ENABLED=true`

You are running:

- deterministic strategy generation
- followed by a bounded AI review layer
- followed by the same paper-trade execution and persistence path

That means the LLM is currently a conservative overlay, not the core brain of the trading system.

## 8. Current Start/End Answer in One Line

### Without LLM

Start:
- cycle begins after ingestion and data readiness passes

End:
- after deterministic signals are executed and all state/log outputs are persisted

### With LLM

Start:
- same start as above

End:
- after deterministic signals are reviewed by the LLM, then executed, then all state/log outputs are persisted
