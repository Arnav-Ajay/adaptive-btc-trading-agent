# Strategy Selector Contract

This document defines the deterministic selector used by the `pullback_hybrid` profile when `LLM_ENABLED=false`.

## Goal

The system should not run DCA and pullback as two equal peers every cycle.

Instead, the selector answers:

- is DCA allowed this cycle?
- is pullback allowed this cycle?
- if both are technically available, which one has priority?

## Why This Exists

Without a selector, hybrid behavior collapses into:

- DCA always active
- pullback rarely active
- drawdown accumulates before pullback meaningfully contributes

That is a strategy interaction problem, not a wiring problem.

## Inputs

The selector uses only deterministic local state:

- `market_regime`
- open pullback-managed positions
- current pullback strategy outcome
- profile configuration flags

It does not require the LLM.

## Decision Rules

Current `pullback_hybrid` selector rules:

1. If a pullback-managed position is already open:
- keep pullback active for management/exits
- suppress DCA for that cycle

2. If the pullback strategy emits a new entry signal:
- prioritize pullback
- suppress DCA for that cycle

3. Otherwise, allow or block DCA by regime:
- bullish: configurable
- sideways: blocked by default
- weakening bull: blocked by default
- bearish: configurable

4. Even in bullish regime, DCA is only allowed while BTC allocation remains below the hybrid support cap.

## Outputs

The selector returns:

- `mode`
- `allow_dca`
- `allow_pullback`
- trace lines explaining the decision

## Current Modes

- `pullback_priority_signal`
- `pullback_priority_open_position`
- `hybrid_parallel`
- `pullback_only_risk_filter`

## Default Intent

The default hybrid behavior is now:

- bullish: pullback-first, with limited DCA support only while BTC allocation is still low
- sideways: no new DCA
- weakening bull: no new DCA
- bearish: no new DCA

That makes DCA a secondary allocator inside the hybrid profile instead of the dominant engine.

## Runtime Flow

Inside `pullback_hybrid`:

1. Run pullback logic first.
2. Pass the pullback outcome plus current context into the selector.
3. If selector allows DCA, run DCA.
4. If selector suppresses DCA, skip it explicitly.
5. Return a single combined outcome with selector traces plus component traces.

## LLM Interaction

When `LLM_ENABLED=true`, the selector still runs first.

That means:

- deterministic strategy selection happens first
- the LLM only reviews the resulting candidate signals afterward

So the LLM remains a bounded review layer, not the primary selector.
