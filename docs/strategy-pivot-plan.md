# Strategy Pivot Plan

This document records the current strategy diagnosis and the implementation plan for the next major iteration.

Its purpose is simple:

- preserve the reasoning behind the pivot
- define what stays as baseline
- define what gets built next
- define how we judge whether the new work is actually better

This is an implementation document, not a conceptual strategy brainstorm.

---

## 1. Current Diagnosis

The system is operationally solid, but the current strategy stack does not show convincing edge after realistic execution costs.

Current state:

- ingestion works
- parquet lake works
- paper trading works
- backtesting works
- simulation works
- dashboard works
- execution realism works
- persistence and logs work
- bounded LLM review works

But:

- edge is weak
- swing participation is sparse
- hybrid behavior often collapses into DCA-like exposure
- the system is too close to buy-and-hold plus costs

Short version:

```text
system works != system has edge
```

---

## 2. Core Thesis

The current bottleneck is no longer engineering quality.

The current bottleneck is:

```text
selective market participation
```

The system must improve at deciding:

- when to enter
- when not to enter
- when to reduce exposure
- when to exit

The goal is not to build a bot that always trades.

The goal is to build a system that trades only when expected value is favorable after fees, spread, and slippage.

---

## 3. What We Are Keeping

We are not discarding the current system.

The current stack remains important as:

- a working runtime
- a reference implementation
- a backtest baseline
- a control group for future comparison

We keep:

- current ingestion/runtime architecture
- current paper broker and cost model
- current backtest/simulation framework
- current structure-aware regime layer
- current DCA and swing strategies as comparison baselines
- current LLM review layer as a bounded overlay

Important discipline:

```text
do not replace the baseline blindly
add a stronger candidate beside it and compare
```

---

## 4. What We Are Changing

We are changing the strategy design philosophy.

### 4.1 DCA Changes Role

DCA should no longer be treated as the main source of edge.

New intended role:

- base exposure allocator
- accumulation policy
- exposure control component

That means DCA becomes more like a portfolio intent layer than a standalone trading strategy.

Questions DCA should answer:

- is base BTC exposure allowed in this regime?
- how much base exposure is allowed?
- should we pause adds?
- should we trim?

### 4.2 A New Primary Edge Candidate

We will add a new deterministic strategy:

```text
PullbackTrendStrategy
```

This will be the first serious replacement candidate for the current swing entry logic.

Why this strategy:

- it matches the current regime-aware architecture
- it should produce fewer trades than the current swing logic
- it should have clearer stop placement
- it is easier to reason about and debug than indicator stacking

### 4.3 LLM Role Stays Secondary

The LLM is not the source of edge yet.

For now the LLM remains:

- a bounded reviewer
- a risk overlay
- a trade suppressor / size reducer

We are **not** making the LLM the primary strategy selector before a deterministic edge candidate exists.

---

## 5. Target Design

The target medium-term structure is:

```text
Regime / structure layer
-> base allocation policy (DCA as portfolio allocator)
-> selective active strategy (pullback trend)
-> bounded LLM review
-> paper execution
```

This is different from the current practical behavior, which often trends toward:

```text
DCA + occasional swing attempt
```

---

## 6. New Strategy Direction

## 6.1 Pullback Trend Strategy

Working idea:

- trade only in bullish structure
- wait for pullback instead of chasing price
- require evidence of stabilization before entry
- place stop below invalidation
- take profit in a structured way

High-level intended logic:

```text
if regime is bullish:
    if price pulls back into a valid higher-low area:
        if momentum stabilizes:
            enter long
```

This is intentionally more selective than the current swing logic.

### 6.2 Expected Benefits

Compared to the current swing layer, this should:

- reduce trade count
- improve entry quality
- create more interpretable setups
- reduce churn caused by weak indicator-only entries
- make stop-loss placement more structurally meaningful

---

## 7. Explicit Non-Goals

To avoid drifting, these are not the current priority:

- adding more random indicators
- expanding to more data vendors
- moving to live trading
- turning the LLM into a free-form strategy engine
- replacing the whole strategy stack at once
- introducing too many new strategy types simultaneously

Also not a priority right now:

- mean reversion strategy redesign
- breakout strategy
- statistical arbitrage ideas
- complex institutional/SMC logic

Those may come later, but not before one stronger deterministic edge candidate is tested cleanly.

---

## 8. Implementation Order

The implementation order matters.

## Phase 1: Document and Freeze the Baseline

Purpose:

- keep a stable comparison point
- avoid losing track of what "current" means

Actions:

- preserve current profile labels
- preserve current backtest outputs as baseline
- keep `hybrid_current` available

Deliverable:

- documented baseline behavior

## Phase 2: Define the Pullback Strategy Contract

Purpose:

- specify exact deterministic rules before coding

Must define:

- entry conditions
- stop-loss placement
- take-profit behavior
- invalidation logic
- regime gate
- interaction with open positions
- max concurrent active positions

Deliverable:

- written rule set for `PullbackTrendStrategy`

## Phase 3: Implement the Strategy Beside Existing Profiles

Purpose:

- add the new strategy without destroying the baseline

Actions:

- create a new strategy module
- wire it into profile selection
- keep `hybrid_current`, `dca_only`, and other baselines intact

Deliverable:

- new profile that can be backtested independently

## Phase 4: Reframe DCA into Base Allocation Policy

Purpose:

- stop treating DCA as the main source of edge

Actions:

- define allowed DCA behavior per regime
- define exposure caps and trim behavior
- ensure DCA is compatible with the new active strategy

Deliverable:

- regime-aware base allocation layer

## Phase 5: Compare Results

Purpose:

- decide with evidence, not intuition

Compare at minimum:

- `dca_only`
- `hybrid_current`
- `pullback_trend + base_allocation`
- buy-and-hold

Metrics to compare:

- total return
- buy-and-hold relative performance
- max drawdown
- Sharpe
- trade count
- win rate
- profit factor

Deliverable:

- evidence that the new profile is better, worse, or inconclusive

## Phase 6: Upgrade the LLM Role Only After Deterministic Improvement

Purpose:

- avoid using the LLM to hide bad deterministic logic

Possible later upgrades:

- trade veto by context
- risk adjustment by setup quality
- bounded parameter band selection
- regime confidence overlay

Not yet:

- free-form autonomous trading

---

## 9. Acceptance Criteria for the New Direction

The new strategy direction is only worth keeping if it improves the actual trading profile after costs.

Success does not require perfection.

It does require at least some of the following:

- fewer but better trades
- stronger expectancy
- less collapse into passive BTC exposure
- clearer rationale for entries and exits
- improved return/drawdown tradeoff

Failure signs:

- trade count remains high with weak expectancy
- trades are still mostly noise around BTC drift
- profile still behaves like disguised buy-and-hold
- the new strategy cannot outperform baseline after realistic costs

---

## 10. Concrete Build Rules

While implementing this pivot:

- do not rip out the current swing logic first
- do not make multiple major strategy changes at once
- do not let the LLM become the first source of strategy logic
- do not evaluate a new strategy only on raw return
- do not remove the current profile baselines

Always preserve comparison.

---

## 11. Immediate Next Step

The next implementation task is:

```text
define the exact deterministic rules for PullbackTrendStrategy
```

That means turning the current high-level idea into:

- precise entry rules
- precise stop rules
- precise exit rules
- precise regime permissions
- precise interaction with DCA/base allocation

Once that rule set is written, implementation should begin immediately after.
