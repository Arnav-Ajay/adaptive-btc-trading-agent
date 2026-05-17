# LLM as an Optional Overlay

This document defines the intended role of the LLM in the BTC strategy stack.

Core rule:

```text
the system must work correctly with LLM disabled
```

The LLM is a plus, not a dependency.

Configuration precedence:

```text
runtime_settings.json > .env / env vars > sheet config > local cache > defaults
```

## 1. Design Principle

The trading system should have a complete deterministic path that can:

- ingest data
- compute features
- detect regime
- generate signals
- apply risk controls
- simulate or execute orders
- persist state and logs

The LLM may improve decision quality, but it must not be required for the system to function.

That means:

- `LLM_ENABLED=false` must remain a first-class supported mode
- deterministic backtests must not depend on model availability
- live/paper runtime must continue if the LLM is unavailable
- all trading decisions must remain bounded by deterministic guardrails

## 1.1 Primary Hypothesis

The LLM should add value in a narrow, testable way.

Primary hypothesis:

```text
the LLM can filter out low-quality trades in noisy, choppy, or high-volatility regimes
better than the deterministic stack alone
```

Secondary hypotheses:

- the LLM can reduce overtrading
- the LLM can improve sizing in uncertain contexts
- the LLM can improve exits by identifying weakening momentum earlier than a fixed rule

The point is not agreement with the deterministic stack.

The point is selective disagreement where the deterministic system is too permissive.

Current observed behavior:

- the LLM now emits valid structured decisions when it participates
- the decision contract includes `action`, `confidence`, `reason`, `reason_code`, and `score`
- the latest experiments show the LLM acting like a high-precision, low-recall filter
- hard filtering has trimmed bad trades in recent windows, but return and Sharpe have not improved consistently yet
- the next experiment modes are score-based: `llm_hard`, `llm_soft`, and `llm_weighted`

## 2. What the LLM Is For

The LLM is best treated as a bounded reasoning layer on top of the strategy stack.

Good uses:

- trade filtering
- regime interpretation
- strategy selection support
- position sizing suggestions
- exit review
- feature summarization

Bad uses:

- raw price prediction
- free-form trade generation
- replacing the deterministic strategy layer
- bypassing risk controls
- becoming the only source of trading logic

## 3. Recommended Runtime Contract

The runtime contract should be:

```text
Market data
-> feature engine
-> deterministic strategy
-> optional LLM review
-> deterministic risk and execution layer
```

Important:

- deterministic strategy produces the baseline signal set
- the LLM may only review or narrow that set
- the LLM cannot create new trades that the deterministic system did not already allow
- the LLM cannot override portfolio-level safety checks

## 3.1 Action Semantics

The LLM action space must be explicit and backtestable.

Recommended semantics:

- `allow` = execute the deterministic signal as-is
- `reduce` = execute the deterministic signal at a smaller size
- `block` = do not execute the signal

The `reduce` action must map to a defined multiplier range, for example:

- `position_size_multiplier` in `[0.3, 0.7]`

The exact range can be configurable, but it must not be ambiguous.

The output schema should also include:

- `confidence`
- `score`
- `rationale`
- optional `reason_code`

If `confidence` is below threshold, the deterministic decision should stand.

Current runtime contract:

- `score < 0` means unfavorable
- `score = 0` means neutral
- `score > 0` means supportive

The evaluation harness now uses this score in three modes:

- `llm_hard` -> block when score is negative
- `llm_soft` -> block strongly negative scores, reduce middling scores, allow positive scores
- `llm_weighted` -> scale exposure from the score

## 4. Why This Matters

This keeps the project useful in three cases:

1. when the LLM is off
2. when the API is unavailable
3. when deterministic validation is needed for research or backtesting

That separation is important because the trading system should be evaluated on actual edge, not on the presence of model reasoning text.

## 5. Suggested First LLM Use Case

The highest-value first experiment is a trade filter.

The LLM receives structured features such as:

- regime
- trend state
- volatility state
- momentum state
- allocation state
- recent performance context

The LLM returns one of a small number of bounded actions:

- `allow`
- `reduce`
- `block`

This is the cleanest way to test whether the LLM adds measurable value without turning the system into a black box.

## 5.2 Prompt And Schema Contract

The LLM should only see structured inputs.

Suggested input schema:

```json
{
  "timestamp": "2026-04-22T12:00:00Z",
  "symbol": "BTC-USD",
  "regime": "sideways",
  "features": {
    "last_price": 67500.12,
    "atr": 1432.22,
    "rsi": 57.4,
    "ema_fast": 67210.11,
    "ema_slow": 67005.08,
    "macd_histogram": -12.81,
    "recent_return_24h": 1.83,
    "drawdown_from_peak": -4.1,
    "volume_trend": "weakening",
    "volatility_state": "high"
  },
  "portfolio": {
    "cash_usd": 4120.55,
    "btc_units": 0.0831,
    "equity_usd": 9680.40,
    "btc_allocation_percent": 58.2
  },
  "candidate_signals": [
    {
      "signal_index": 0,
      "strategy_name": "PullbackTrendStrategy",
      "side": "buy",
      "size_usd": 250.0,
      "reason": "pullback_trend_entry"
    }
  ]
}
```

Suggested output schema:

```json
{
  "summary": "trade rejected due to weak follow-through and elevated noise",
  "signal_actions": [
    {
      "signal_index": 0,
      "action": "block",
      "confidence": 0.82,
      "size_multiplier": 0.0,
      "rationale": "sideways regime with weakening volume makes entry low quality",
      "reason_code": "choppy_regime_low_conviction"
    }
  ],
  "parameter_suggestions": {
    "swing_take_profit_percent": 2.5
  },
  "decision": {
    "action": "block",
    "confidence": 0.82,
    "reason": "sideways regime with weakening volume makes entry low quality",
    "reason_code": "choppy_regime_low_conviction",
    "score": -0.74
  }
}
```

Contract rules:

- `signal_index` must reference an existing candidate signal
- the LLM may not invent new signal indices
- the LLM may not change signal side
- the LLM may only reduce size when action is `reduce`
- the model should not emit more actions than there are candidate signals
- malformed fields should be ignored by validation

This schema keeps the model useful while still making the system testable.

## 5.1 Decision Attribution Logging

To measure edge, every review must be logged at the decision level.

Minimum fields:

```json
{
  "timestamp": "2026-04-22T12:00:00Z",
  "symbol": "BTC-USD",
  "deterministic_signal": "buy",
  "llm_action": "block",
  "llm_confidence": 0.82,
  "executed": false,
  "reason_code": "choppy_regime_low_conviction"
}
```

This is the core audit record for attribution.

It lets us measure:

- which trades the LLM blocked
- which trades it reduced
- which trades it allowed
- whether those interventions helped or hurt

The current evaluation artifact also stores:

- `baseline_signal_generated`
- `overlay_signal_generated`
- `baseline_trade_taken`
- `overlay_trade_taken`
- `llm_decision_present`
- `llm_decision_valid`
- `llm_confidence`
- `llm_score`
- `behavior_label`

## 6. UI Toggle Recommendation

Yes, the UI should expose an on/off control for the LLM if the dashboard is used to operate the system.

But the control should be treated as a runtime convenience, not as the source of truth.

Recommended behavior:

- default state: `LLM disabled`
- control label: `Enable LLM review`
- persistence: update config/env-backed state, not just the page session
- runtime effect: the next cycle should read the updated config

Implementation note:

- because the repo currently has no settings write endpoint, a UI radio button alone would be cosmetic
- if we add the UI control, we should also add a backend path to persist `LLM_ENABLED`

UI shape:

- prefer a two-state toggle or segmented control
- a radio button pair is acceptable if it matches the dashboard style
- the key requirement is clarity, not the exact widget type

Operational constraint:

- the backend must remain functional if the UI is unavailable
- the runtime must remain functional if the LLM endpoint is unavailable

## 7. Evaluation Rule

The LLM is only worth keeping if it improves at least one of:

- net return after costs
- drawdown
- Sharpe ratio
- trade quality
- trade frequency efficiency

Additional evaluation metrics for LLM impact:

- disagreement rate versus deterministic signals
- block precision
- reduce precision
- allow precision
- average size reduction on reduced trades
- post-intervention PnL delta

Useful interpretation:

- if disagreement rate is near zero, the LLM is probably redundant
- if disagreement rate is too high, the LLM may be unstable or overreaching
- the best zone is selective disagreement with measurable benefit

Current sample interpretation:

- hard mode has shown the clearest short-window precision
- soft and weighted modes are now the next test, not the conclusion

Recommended backtest breakdown:

- deterministic signal was buy, LLM blocked, trade would have lost
- deterministic signal was buy, LLM blocked, trade would have won
- deterministic signal was buy, LLM reduced, trade outcome improved or drawdown shrank
- deterministic signal was buy, LLM allowed, trade outcome matched baseline

If it does not improve the strategy in walk-forward tests, it should remain optional and disabled by default.

## 8. Summary

The correct framing is:

```text
deterministic trading system
+ optional LLM overlay
```

Not:

```text
LLM-driven trading system
```

The LLM is an enhancement layer, not the core engine.

Current bottom line:

- the system is deterministic-first
- the LLM is optional
- the score contract is now in place so the overlay can be tested as hard, soft, or weighted
- the project is still in the experiment phase for proving net edge
