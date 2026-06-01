# LLM Architecture

This document is the authoritative architecture reference for AI integration.

Ownership boundary:
- current LLM runtime architecture
- bounded advisory contract
- proposed dual-layer architecture
- replay and persistence implications

This document does not define:
- strategy rules in full
- feature formulas in full
- implementation roadmap details beyond AI integration

## 1. Current LLM Architecture

**Status: CURRENT IMPLEMENTATION**

Current live path:

```text
Candles
-> Feature generation
-> Regime detection
-> AgentContext assembly
-> Strategy selection
-> Strategy signal generation
-> LLM review of generated signals
-> Signal validation
-> Capital allocation
-> Broker execution
-> Persistence and journaling
```

There is currently one active LLM insertion point:
- after strategy-generated signals exist
- before execution

Primary runtime files:
- [app/main.py](../app/main.py)
- [app/execution/order_manager.py](../app/execution/order_manager.py)
- [app/llm/advisor.py](../app/llm/advisor.py)
- [app/llm/validator.py](../app/llm/validator.py)

## 2. Existing LLM Review Layer

**Status: CURRENT IMPLEMENTATION**

The current LLM layer is a:

```text
post-strategy bounded signal review layer
```

### Current input contract

Review call:
- [app/execution/order_manager.py](../app/execution/order_manager.py)
- `OrderManager.review_signals(signals, features, regime)`

Advisor input:
- `signals`
- `features`
- `regime`
- `snapshot`

Source:
- [app/llm/advisor.py](../app/llm/advisor.py)
- `LLMAdvisor.review(...)`

### Current prompt content

Prompt builder:
- [app/llm/prompts.py](../app/llm/prompts.py)

Current prompt includes:
- regime
- trend
- volatility
- RSI
- ATR percent
- recent return
- drawdown
- position size
- portfolio snapshot
- signal list

### Current output contract

Output object:
- `LLMAdvice`

Source:
- [app/utils/models.py](../app/utils/models.py)

Current bounded actions:
- `allow`
- `reduce`
- `block`

Validation boundary:
- [app/llm/validator.py](../app/llm/validator.py)

### Current persistence

The current review layer is persisted as `llm_review` in:
- cycle log
- decision trace
- latest snapshot

Source:
- [app/monitoring/trading_journal.py](../app/monitoring/trading_journal.py)
- [app/api/state_reader.py](../app/api/state_reader.py)

## 3. Optional Overlay Principle

**Status: CURRENT IMPLEMENTATION**

Core rule:

```text
the system must work correctly with LLM disabled
```

Current implementation reflects that rule:
- when disabled, the advisor returns a no-op review result
- deterministic strategy generation still runs
- execution still proceeds through the deterministic path
- request failure or missing API key does not stop paper trading

This makes the LLM:
- optional
- bounded
- non-authoritative

## 4. Proposed Dual-Layer Architecture

**Status: FUTURE ROADMAP**

Proposed architecture:

```text
Candles
-> Feature generation
-> Regime detection
-> Base AgentContext assembly
-> LLM #1 Context Analyst
-> Extended AgentContext
-> Strategy selection
-> Strategy signal generation
-> LLM #2 Signal Review Layer
-> Signal validation
-> Capital allocation
-> Broker execution
-> Persistence and journaling
```

Architectural separation:

```text
LLM #1 = context interpretation
LLM #2 = signal review
```

## 5. AgentContext Extension Model

**Status: FUTURE ROADMAP**

Current `AgentContext` already carries:
- regime
- anchor prices
- open positions
- portfolio snapshot
- scored regime diagnostics
- available cash

Source:
- [app/utils/models.py](../app/utils/models.py)

That makes `AgentContext` the natural extension point for LLM #1.

Official design direction:
- deterministic context remains primary
- LLM #1 adds structured annotations to `AgentContext`
- strategies may consume those annotations
- raw deterministic features and regime should not be replaced

## 6. LLM #1 Responsibilities

**Status: FUTURE ROADMAP**

LLM #1 is the proposed feature/context analyst.

Its responsibility is:

```text
context interpretation only
```

It should:
- consume features, regime score, portfolio state, and optionally recent candle summaries
- produce structured context for strategies and possibly router use

It should not:
- create trade signals
- execute trades
- replace broker logic
- replace LLM #2

## 7. LLM #2 Responsibilities

**Status: CURRENT IMPLEMENTATION**

LLM #2 is the current post-signal review layer.

Its responsibility is:

```text
bounded review of deterministic strategy output
```

It can:
- allow signals
- reduce signals
- block signals

It cannot:
- invent new trades
- bypass the portfolio guard
- bypass capital allocation
- directly execute orders

## 8. Determinism and Replay Considerations

### Current replay behavior

**Status: CURRENT IMPLEMENTATION**

Backtesting mirrors the live flow in:
- [app/backtest/engine.py](../app/backtest/engine.py)

Current P1 behavior:
- replay disables the live LLM review path by default for determinism

### Dual-layer implication

**Status: FUTURE ROADMAP**

If LLM #1 is added to live runtime, replay parity must be addressed explicitly.

Possible architectural modes:
1. disable LLM #1 in replay by default
2. persist LLM #1 output and replay it
3. inject a deterministic mock/policy in replay

Without one of those, live and replay paths diverge.

## 9. Persistence Requirements

### Current state

**Status: CURRENT IMPLEMENTATION**

Only one LLM layer is currently persisted:
- `llm_review`

### Dual-layer requirement

**Status: FUTURE ROADMAP**

If LLM #1 is implemented and should be auditable, a second persisted metadata block is required.

That persistence must be separate from:
- `llm_review`

Backtest artifacts would also need a second AI-layer metadata field if dual-layer replay becomes first-class.

## 10. Existing Extension Points

**Status: CURRENT IMPLEMENTATION**

Best current insertion points:
- `AgentContext`
- `run_cycle()` in [app/main.py](../app/main.py)
- mirrored replay path in [app/backtest/engine.py](../app/backtest/engine.py)

Existing bounded review injection point:
- `review_policy` in `OrderManager`

There is no current pre-strategy policy hook.

## 11. Experimental Surface

### Evaluation Matrix

**Status: EXPERIMENTAL**

The repo still contains broader LLM evaluation machinery under:
- `app/evaluation/*`

That surface is not part of the core stabilized runtime path.

## 12. Future Implementation Roadmap

**Status: FUTURE ROADMAP**

Phase 1:
- define the structured output contract for LLM #1

Phase 2:
- insert LLM #1 into live runtime before strategy selection/generation

Phase 3:
- mirror the same stage in backtesting

Phase 4:
- persist both AI layers separately

Phase 5:
- validate strategy consumption and replay parity

## 13. Ownership Boundaries Between Documents

**Status: CURRENT IMPLEMENTATION**

- [01_architecture.md](./01_architecture.md)
  - service/runtime architecture
- [02_strategy_specification.md](./02_strategy_specification.md)
  - trade logic and strategy rules
- [03_metrics_reference.md](./03_metrics_reference.md)
  - feature and metric formulas
- [04_llm_architecture.md](./04_llm_architecture.md)
  - AI integration architecture
- [05_future_work.md](./05_future_work.md)
  - roadmap and deferred work
