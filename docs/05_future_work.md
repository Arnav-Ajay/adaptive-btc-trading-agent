# Future Work

This document is the authoritative roadmap reference.

Ownership boundary:
- deferred work
- planned architecture directions
- frozen or experimental surfaces
- evolution notes

This document does not redefine:
- current runtime behavior
- strategy rules
- metrics formulas

## 1. Scope

**Status: FUTURE ROADMAP**

This document captures work that is:
- not part of the current authoritative implementation baseline
- deferred
- frozen
- exploratory

## 2. Near-Term Product Work

### 2.1 Deployment Hardening

**Status: FUTURE ROADMAP**

Areas still suitable for future work:
- cloud deployment polish
- secrets handling refinement
- production operations checklists
- deployment documentation

### 2.2 Reporting and Notification Refinement

**Status: FUTURE ROADMAP**

Current weekly Gmail and Telegram paths exist.

Future polish could include:
- richer rendering
- clearer error surfacing
- operator runbooks

## 3. AI Integration Roadmap

### 3.1 Dual-Layer LLM Architecture

**Status: FUTURE ROADMAP**

Reviewed target direction:

```text
Features -> LLM Context Layer -> Strategy -> LLM Review -> Execution
```

Official interpretation:
- LLM #1 = context analyst
- LLM #2 = bounded signal reviewer

Detailed architecture reference:
- [04_llm_architecture.md](./04_llm_architecture.md)

### 3.2 Replay and Determinism Support

**Status: FUTURE ROADMAP**

If dual-layer AI is implemented, replay support must explicitly define:
- disabled mode
- deterministic mock mode
- or persisted-context replay mode

## 4. Experimental and Frozen Areas

### 4.1 Pullback / Structure Research

**Status: EXPERIMENTAL**

The repository still contains pullback and structure-oriented code paths.

These are currently outside the active project scope and should be treated as frozen unless scope changes.

### 4.2 Broader LLM Evaluation Matrix

**Status: EXPERIMENTAL**

Evaluation-only surfaces under `app/evaluation/*` remain present in the repo.

They are not part of the current operational baseline.

### 4.3 Profit-Optimization Work

**Status: FUTURE ROADMAP**

The project’s current goal is engineering quality, not strategy-alpha maximization.

Any future profitability-focused experimentation should remain explicitly secondary to:
- reliability
- observability
- reproducibility

## 5. Documentation Maintenance Rules

**Status: FUTURE ROADMAP**

Future documentation updates should preserve these ownership boundaries:

- [01_architecture.md](./01_architecture.md)
  - current runtime/system architecture only
- [02_strategy_specification.md](./02_strategy_specification.md)
  - active strategy source of truth
- [03_metrics_reference.md](./03_metrics_reference.md)
  - formula and metric source of truth
- [04_llm_architecture.md](./04_llm_architecture.md)
  - AI integration architecture only
- [05_future_work.md](./05_future_work.md)
  - deferred and experimental work only

## 6. Project Evolution

### 6.1 P1 Stabilization Work Completed

**Status: CURRENT IMPLEMENTATION**

Completed stabilization work now reflected in code and docs:
- deterministic backtest/simulation defaults
- paper broker state recovery hardening
- exact-boundary combined worker scheduling
- journal and healthcheck robustness improvements
- Google Sheets config with hourly refresh and cache fallback
- weekly Gmail HTML reporting
- Telegram per-trade notifications

### 6.2 Strategy Formalization

**Status: CURRENT IMPLEMENTATION**

The active strategy surface is now formally defined in:
- [02_strategy_specification.md](./02_strategy_specification.md)

That document is the source of truth for:
- DCA entry and rebalance sell behavior
- swing entry and exit behavior
- hybrid composition behavior

### 6.3 Sell-Path Implementation

**Status: CURRENT IMPLEMENTATION**

The project now has explicit documented sell paths:
- DCA rebalance sell
- swing take-profit exit
- swing signal exit
- swing no-follow-through exit
- broker-driven swing stop-loss exit

### 6.4 LLM Review Architecture

**Status: CURRENT IMPLEMENTATION**

The current active AI runtime architecture is:
- optional post-signal LLM review
- bounded by deterministic validation and execution controls

Detailed reference:
- [04_llm_architecture.md](./04_llm_architecture.md)

### 6.5 Proposed Future Dual-Layer LLM Architecture

**Status: FUTURE ROADMAP**

The reviewed future direction is:

```text
Features -> LLM Context Layer -> Strategy -> LLM Review -> Execution
```

This is not current runtime behavior.

It remains a future architecture direction only.
