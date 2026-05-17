# Pullback Trend Strategy Spec

This document defines the deterministic rule set for `PullbackTrendStrategy`.

The strategy is designed to be:

- more selective than the current swing logic
- structure-aware
- easier to reason about in backtests
- compatible with the current paper broker and execution model

This strategy is intentionally not the live default yet.

It is being added beside the current profiles for controlled comparison.

## 1. Role

`PullbackTrendStrategy` is the active trade layer.

It is not responsible for long-term base BTC accumulation.

That remains with DCA / base allocation behavior.

So the intended combined profile is:

```text
DCA = base exposure allocator
PullbackTrendStrategy = selective active trade logic
```

## 2. Market Permission

New long entries are allowed only when:

- regime is `bullish`

## 3. Entry Anchor

The strategy uses recent swing points from `extract_swing_points()`.

It looks for:

- a confirmed recent swing high
- the confirmed swing low immediately before that high
- a prior swing high before the anchor high
- a prior swing low before the anchor low

Bullish structure requirement:

- `anchor_high > prior_high`
- `anchor_low > prior_low`

## 4. Pullback Condition

Retracement is computed as:

```text
(anchor_high - last_price) / (anchor_high - anchor_low)
```

Entry is allowed only when retracement stays inside:

- `pullback_min_retracement`
- `pullback_max_retracement`

## 5. Stabilization Condition

The strategy also requires:

- the latest candle closes in the upper half of its range
- the latest close is not still making a fresh short-term closing low

## 6. Entry Output

If all conditions pass:

- emit one long buy signal
- reason: `pullback_trend_entry`
- strategy name: `PullbackTrendStrategy`

Current size:

- `min(250 USD, available_cash_usd)`

## 7. Stop-Loss Logic

Stop-loss is placed below the anchor low:

```text
stop_loss = anchor_low - pullback_stop_atr_multiplier * ATR
```

## 8. Exit Logic

Open pullback positions are managed only by this strategy.

Exit types:

- `pullback_take_profit:<position_id>`
- `pullback_no_follow_through:<position_id>`
- `pullback_signal_exit:<position_id>`

The broker-level stop-loss still exists and is evaluated before strategy generation.

Signal exit is now intentionally less aggressive:

- the strategy exits on signal breakdown only when both:
  - `ema_fast <= ema_slow`
  - `macd_histogram <= 0`

## 9. Profiles

New profiles introduced for controlled testing:

- `pullback_only`
- `pullback_hybrid`

Existing baselines remain:

- `hybrid_current`
- `dca_only`
- `swing_only`
- `buy_and_hold`
