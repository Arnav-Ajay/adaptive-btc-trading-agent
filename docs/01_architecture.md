# Architecture

This document is the authoritative architecture reference for the current project structure.

Ownership boundary:
- system shape
- runtime flow
- storage layout
- service boundaries
- operational behavior

This document does not define:
- strategy rules in detail
- metrics formulas in detail
- future roadmap details beyond boundary notes

## 1. System Overview

**Status: CURRENT IMPLEMENTATION**

The project currently runs as two services:
- a combined market-execution worker
- a FastAPI dashboard/API

High-level shape:

```text
Coinbase
-> ingestion worker
-> canonical 1m parquet lake
-> derived interval parquet datasets
-> paper-trading cycle
-> persisted state and logs
-> FastAPI dashboard/API
```

The worker is the only service that talks to Coinbase.

The dashboard:
- reads persisted state
- reads parquet data
- can trigger research workflows such as backtests and simulations
- does not execute live exchange orders

## 2. Runtime Flow

**Status: CURRENT IMPLEMENTATION**

### 2.1 Combined Worker

Primary entry point:
- [app/scheduler/worker_runner.py](../app/scheduler/worker_runner.py)

Current worker flow:

```text
Load config
-> configure worker logging
-> bootstrap/catch-up check
-> compute next exact schedule boundary
-> sleep until target boundary
-> run one worker cycle:
   -> CoinbaseIngestionService.collect_once()
   -> run_cycle()
-> optionally send weekly report
-> repeat
```

Current scheduling behavior:
- one combined worker owns ingestion and trading
- trading runs immediately after ingestion
- the worker aligns to exact interval boundaries rather than using separate ingestion/trading schedulers

### 2.2 Ingestion Flow

Primary modules:
- [app/ingestion/collector.py](../app/ingestion/collector.py)
- [app/ingestion/parquet_store.py](../app/ingestion/parquet_store.py)
- [app/ingestion/preprocessor.py](../app/ingestion/preprocessor.py)

Current ingestion flow:

```text
Fetch overlapping BTC-USD 1m candles from Coinbase
-> retry on failure
-> normalize to Candle objects
-> merge with canonical parquet
-> deduplicate by timestamp
-> rewrite affected partitions
-> audit source and lake gaps
-> derive 10m / 30m / 1hr / 1d / 1week / 1month
-> update ingestion state
-> write logs
```

### 2.3 Paper-Trading Flow

Primary entry point:
- [app/main.py](../app/main.py)

Current paper-trading flow:

```text
Read recent candles from local parquet
-> validate minimum history and freshness
-> compute indicators
-> detect scored regime
-> update broker mark price
-> evaluate swing stop-losses before new entries
-> build AgentContext
-> select strategy
-> generate deterministic signals
-> apply drawdown guard, optional LLM review, and capital allocation
-> execute paper trades through PaperBroker
-> persist broker state and ledger
-> persist cycle log, decision trace, and snapshot
-> send notifications
```

Important current boundary:
- stop-loss exits run before new strategy generation
- stop-loss exits can end the cycle early

### 2.4 Research Flows

Backtesting:
- [app/backtest/engine.py](../app/backtest/engine.py)

Simulation:
- [app/simulation/engine.py](../app/simulation/engine.py)

Current research flow characteristics:
- read parquet only
- use isolated paper-trade state
- do not mutate live paper-trading state
- persist artifacts under `data_lake/state/backtesting` and `data_lake/state/simulations`

## 3. Major Components

**Status: CURRENT IMPLEMENTATION**

### 3.1 Ingestion

Responsibilities:
- fetch canonical `BTC-USD` `1m` candles from Coinbase
- detect continuity gaps
- persist canonical market data
- build derived intervals
- persist ingestion state and audits

### 3.2 Paper Trading

Responsibilities:
- load local candles only
- compute indicators and regime score
- route to strategy profile
- generate deterministic signals
- optionally review signals with LLM
- execute paper fills through deterministic cost modeling
- persist broker state, ledger, cycle logs, and snapshots

Primary runtime modules:
- [app/main.py](../app/main.py)
- [app/data/data_normalizer.py](../app/data/data_normalizer.py)
- [app/execution/order_manager.py](../app/execution/order_manager.py)
- [app/execution/paper_broker.py](../app/execution/paper_broker.py)
- [app/strategies/router.py](../app/strategies/router.py)

### 3.3 Dashboard / API

Responsibilities:
- render operational state
- expose JSON endpoints
- trigger backtests and simulations
- read persisted artifacts only

Primary modules:
- [app/api/main.py](../app/api/main.py)
- [app/api/state_reader.py](../app/api/state_reader.py)

### 3.4 Notifications

Responsibilities:
- Telegram trade notifications
- Gmail weekly report delivery

Primary modules:
- [app/monitoring/alerts.py](../app/monitoring/alerts.py)
- [app/monitoring/telegram.py](../app/monitoring/telegram.py)
- [app/monitoring/gmail.py](../app/monitoring/gmail.py)
- [app/monitoring/weekly_report.py](../app/monitoring/weekly_report.py)

## 4. Storage Layout

**Status: CURRENT IMPLEMENTATION**

### 4.1 Market Data Lake

Canonical and derived parquet data live under:

```text
data_lake/
  symbol=BTC-USD/
    interval=1m/
    interval=10m/
    interval=30m/
    interval=1hr/
    interval=1d/
    interval=1week/
    interval=1month/
```

Current partitioning:
- `1m`, `10m`, `30m`, `1hr` -> `year/month/day`
- `1d` -> `year/month`
- `1week`, `1month` -> `year`

### 4.2 Runtime State

Current state folders:

```text
data_lake/state/
  ingestion/
  paper_trade/
  backtesting/
  simulations/
```

Important paper-trade artifacts:
- `paper_broker_state.json`
- `paper_trade_ledger.jsonl`
- `paper_cycle_log.jsonl`
- `paper_portfolio_snapshot.json`
- `paper_decision_trace.jsonl`

## 5. Configuration Architecture

**Status: CURRENT IMPLEMENTATION**

Current precedence:

```text
runtime_settings.json
-> env / .env
-> Google Sheets
-> config_cache.json
-> schema defaults
```

Primary modules:
- [app/config/settings.py](../app/config/settings.py)
- [app/config/schema.py](../app/config/schema.py)
- [app/config/sheet_loader.py](../app/config/sheet_loader.py)

Operational note:
- not every config field is truly hot-reloadable
- trading-cycle config reload is broader than worker-loop scheduling config reload

## 6. LLM Boundary

**Status: CURRENT IMPLEMENTATION**

There is currently one active LLM insertion point:

```text
Features
-> Strategy
-> LLM signal review
-> Execution
```

The LLM is currently:
- post-strategy
- bounded
- optional

Detailed ownership belongs to:
- [04_llm_architecture.md](./04_llm_architecture.md)

## 7. Experimental and Frozen Surface

### 7.1 Pullback / Structure Work

**Status: EXPERIMENTAL**

The codebase still contains legacy or frozen structure-oriented components, but they are not part of the active project direction:
- pullback strategies
- selector logic
- structure-regime experimentation

These are no longer part of the active documentation baseline for strategy behavior.

### 7.2 Evaluation Matrix

**Status: EXPERIMENTAL**

The repo still contains broader LLM evaluation machinery under `app/evaluation/*`, but it is not part of the core stabilized runtime architecture.

## 8. Service Boundaries

**Status: CURRENT IMPLEMENTATION**

Current boundaries:
- worker owns Coinbase access
- worker writes ingestion and paper-trading artifacts
- dashboard reads persisted artifacts and parquet
- backtests and simulations use isolated paper state
- Docker shares:
  - `data_lake/`
  - `config/`
  - `logs/`

This separation is deliberate:
- live ingestion and trading remain tightly coupled
- UI requests do not fetch Coinbase directly
- research paths do not mutate live paper state

## 9. Ownership Boundaries Between Documents

**Status: CURRENT IMPLEMENTATION**

- [01_architecture.md](./01_architecture.md)
  - runtime shape, storage, services, boundaries
- [02_strategy_specification.md](./02_strategy_specification.md)
  - strategy definitions and trade logic
- [03_metrics_reference.md](./03_metrics_reference.md)
  - metric formulas and meanings
- [04_llm_architecture.md](./04_llm_architecture.md)
  - AI integration architecture
- [05_future_work.md](./05_future_work.md)
  - roadmap and deferred work only

## 10. Project Evolution

### 10.1 P1 Stabilization

**Status: CURRENT IMPLEMENTATION**

Completed stabilization work reflected in the current architecture:
- deterministic backtest/simulation path by default
- corrupt paper-state recovery
- exact-boundary combined worker scheduling
- paper-trade journaling hardening
- weekly report delivery path
- Telegram per-trade notification path
- Google Sheets config with cache fallback

### 10.2 Strategy Formalization

**Status: CURRENT IMPLEMENTATION**

The active runtime strategy set is now formally documented in:
- [02_strategy_specification.md](./02_strategy_specification.md)

### 10.3 Sell-Path Implementation

**Status: CURRENT IMPLEMENTATION**

The stabilized runtime now has explicit documented sell paths:
- DCA rebalance sell
- swing take-profit exit
- swing signal exit
- swing no-follow-through exit
- broker-driven ATR stop-loss exit

### 10.4 Current LLM Review Architecture

**Status: CURRENT IMPLEMENTATION**

The current active AI layer is:
- optional post-signal LLM review

Detailed definition:
- [04_llm_architecture.md](./04_llm_architecture.md)

### 10.5 Dual-Layer LLM Direction

**Status: FUTURE ROADMAP**

The reviewed future direction is:

```text
Features -> LLM Context Layer -> Strategy -> LLM Review -> Execution
```

This is documented as architecture guidance only, not current runtime behavior.
