# Strategy Growth

This document tracks how the trading logic has evolved over time.

It is not a roadmap of ideas. It records the actual strategy progression the code has gone through, plus the next improvements we have explicitly identified from backtest results.

## Why This Exists

The system has matured in two different ways:

- the infrastructure and execution layer became realistic quickly
- the strategy layer is still being improved iteratively

That distinction matters.

At this point:

- the system is working correctly
- execution costs are modeled
- buys and sells can be simulated and persisted
- but strategy edge is still limited

## Stage 1: DCA Only

Implemented first:

- base BTC accumulation
- initial DCA buy when no prior fill exists
- next buys only after a configured percentage drop from the latest buy fill

What this gave us:

- persistent buy logic
- simple and deterministic accumulation behavior
- a clean baseline to test broker state, ledger writes, and cycle logging

Limitations:

- no explicit sell logic
- no profit-taking
- no active position management
- strategy quality depended almost entirely on dip-buy timing

## Stage 2: Hybrid Entry Model

Added next:

- regime detection from EMA + RSI
- `HybridStrategy` in bullish regimes
- swing momentum entries alongside DCA
- ATR-based stop-loss attached to swing trades

What changed:

- DCA remained the base accumulation layer
- swing trades became a separate tracked position type
- the system could open opportunistic trades instead of only waiting for DCA dips

What this solved:

- started using trend/momentum state, not just pullback state
- introduced strategy separation:
  - long-term DCA holdings
  - short-term swing positions

What was still missing:

- no strategy-driven sell decisions
- swing positions only exited when stop-loss fired
- backtests could show repeated stop-loss exits without any profit-taking path

## Stage 3: Proper Swing Sell Logic

Current state:

- swing take-profit exit exists
- swing signal-based exit exists
- swing no-follow-through exit exists
- swing stop-loss exit still exists
- stop-loss exits no longer terminate the entire backtest replay
- swing entry filter is now intentionally stricter:
  - `RSI < 35`
  - positive MACD histogram
  - `ema_fast > ema_slow`

Current swing exit logic:

- take profit when:
  - `last_price >= entry_price * (1 + swing_take_profit_percent / 100)`
- signal exit when:
  - `macd_histogram <= 0`
  - or `ema_fast <= ema_slow`
- no-follow-through exit when:
  - the trade does not show enough positive follow-through after a few candles
- stop-loss exit when mark price breaches the tracked ATR stop

Routing change added with this stage:

- if a swing position is still open, keep `HybridStrategy` active even outside bullish regimes
- this allows bearish or sideways cycles to generate swing exits

What this fixed:

- sell is now a real strategy decision for the swing layer
- the system no longer only exits when it is wrong
- stop-loss is no longer the only path out of a swing position
- trade churn should reduce because the swing entry gate is tighter than before

## What Backtests Are Telling Us Now

The execution system is realistic enough to trust.

The strategy still needs improvement.

Observed issues:

- too many trades in some replay windows
- weak entry quality
- execution costs can dominate small edges
- stop-loss and fee drag can overwhelm marginal signals

Plain reading of current results:

- the system is not failing operationally
- the current signal set does not yet produce a strong edge

## Confirmed Next Strategy Work

These are the next improvements already identified from the current backtest behavior.

### 1. Reduce trade count

Target:

- move from high-churn behavior toward roughly `30-50` trades in a comparable backtest window

Why:

- too many small trades create fee drag
- high turnover with weak signals compounds losses quickly

### 2. Improve profit-taking

We now have a configured swing take-profit, but profit-taking still needs tuning as part of strategy development.

Likely direction:

- clearer reward target
- better interaction between take-profit and signal-based exits

### 3. Reduce weak trade persistence further

We now have a no-follow-through exit, but it is still an initial rule and likely needs tuning.

Likely next refinement:

- adjust the follow-through window and threshold based on replay results

## Current Bottom Line

Where the project stands right now:

- DCA exists
- Hybrid exists
- proper swing sell logic exists
- execution costs are realistic
- backtests are useful enough to evaluate strategy quality

What remains:

- improve entry quality
- reduce trade count
- tune exits for better expectancy
- decide whether DCA should remain accumulation-only or eventually get its own sell logic
