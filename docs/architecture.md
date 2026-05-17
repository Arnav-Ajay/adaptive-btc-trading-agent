# Architecture

This document describes the current system architecture, the storage/runtime boundaries, and the main implementation decisions that shaped the project.

## 1. System Overview

The project has two long-running services:

- a combined market-execution worker
- a FastAPI dashboard/API

High-level shape:

```text
Coinbase
-> ingestion worker
-> canonical 1m parquet lake
-> derived interval parquet datasets
-> paper-trading cycle
-> persisted state/logs
-> FastAPI dashboard/API
```

The worker is the only runtime that talks to Coinbase. The dashboard is read-only against persisted state and parquet data.

## 2. Major Components

### 2.1 Ingestion

Primary modules:

- [collector.py](../app/ingestion/collector.py)
- [parquet_store.py](../app/ingestion/parquet_store.py)
- [preprocessor.py](../app/ingestion/preprocessor.py)
- [backfill.py](../app/ingestion/backfill.py)

Responsibilities:

- fetch overlapping `BTC-USD` `1m` candles from Coinbase
- deduplicate and persist canonical market data
- detect source gaps and recent lake continuity gaps
- derive `10m`, `30m`, `1hr`, `1d`, `1week`, and `1month` datasets from canonical `1m`
- persist ingestion state and audit files

### 2.2 Paper Trading

Primary modules:

- [main.py](../app/main.py)
- [parquet_market_data.py](../app/data/parquet_market_data.py)
- [order_manager.py](../app/execution/order_manager.py)
- [paper_broker.py](../app/execution/paper_broker.py)
- [router.py](../app/strategies/router.py)
- [hybrid.py](../app/strategies/hybrid.py)
- [hybrid_pullback.py](../app/strategies/hybrid_pullback.py)
- [pullback_selector.py](../app/strategies/pullback_selector.py)
- [pullback_trend.py](../app/strategies/pullback_trend.py)

Responsibilities:

- load recent candles from local parquet only
- compute indicators and regime features
- route between legacy DCA/swing behavior and selector-based pullback hybrid behavior
- optionally apply a score-based LLM review layer after deterministic signal generation
- execute paper fills through a deterministic fee/spread/slippage model
- track realized PnL, execution costs, and open swing positions
- persist broker state, trade ledger, cycle log, portfolio snapshot, and decision trace

Near-term architecture direction:

- shift the regime layer away from pure EMA/RSI threshold emphasis toward a structure-aware regime model
- use that regime model to gate:
  - DCA permission
  - swing-entry permission
  - future portfolio de-risking actions

Current implementation status:

- recent swing structure now feeds regime classification
- DCA is now blocked in bearish regimes by default
- DCA size is now reduced in `weakening_bull`
- BTC allocation cap is now enforced before new DCA signals are emitted
- DCA can now emit partial rebalance sells to move base BTC exposure back toward regime-aware targets
- new swing entries are now gated by regime inside the swing strategy itself, while swing exits remain available for already-open positions
- `pullback_hybrid` now runs a deterministic selector before allowing DCA
- default selector behavior blocks new hybrid DCA in `sideways`, `weakening_bull`, and `bearish`
- bullish hybrid DCA is capped so DCA acts as secondary support rather than the dominant engine
- the LLM overlay is optional, score-aware, and can be replayed as `llm_hard`, `llm_soft`, or `llm_weighted`

### 2.3 Backtesting

Primary modules:

- [engine.py](../app/backtest/engine.py)
- [metrics.py](../app/backtest/metrics.py)
- [history.py](../app/backtest/history.py)

Responsibilities:

- replay historical parquet candles through the live trading path
- use isolated paper-trading state in a temp directory
- compute equity, benchmark, drawdown, and trade metrics
- persist latest backtest plus append-only history

### 2.4 Simulations

Primary modules:

- [engine.py](../app/simulation/engine.py)
- [history.py](../app/simulation/history.py)

Responsibilities:

- build bounded strategy parameter grids
- run multiple backtests with cloned config variants
- rank candidates by return, drawdown, profit factor, and Sharpe
- persist latest sweep plus append-only history

### 2.5 Dashboard / API

Primary modules:

- [main.py](../app/api/main.py)
- [state_reader.py](../app/api/state_reader.py)

Responsibilities:

- render `/bitcoin` and `/trades`
- expose JSON endpoints for health, trading, candles, and backtests
- read only persisted state and parquet data
- never fetch Coinbase directly

### 2.6 Scheduling and Health

Primary modules:

- [worker_runner.py](../app/scheduler/worker_runner.py)
- [worker_healthcheck.py](../app/scheduler/worker_healthcheck.py)
- [trading_healthcheck.py](../app/scheduler/trading_healthcheck.py)

Responsibilities:

- align execution to exact UTC half-hour boundaries
- run ingestion and trading sequentially in one worker
- support bootstrap/catch-up cycles on startup
- evaluate both ingestion freshness and trading freshness

## 3. Storage Layout

### 3.1 Market Data Lake

Canonical and derived parquet data live under:

```text
data_lake/
  symbol=BTC-USD/
    interval=1m/
      year=YYYY/month=MM/day=DD/data.parquet
    interval=10m/
      year=YYYY/month=MM/day=DD/data.parquet
    interval=30m/
      year=YYYY/month=MM/day=DD/data.parquet
    interval=1hr/
      year=YYYY/month=MM/day=DD/data.parquet
    interval=1d/
      year=YYYY/month=MM/data.parquet
    interval=1week/
      year=YYYY/data.parquet
    interval=1month/
      year=YYYY/data.parquet
```

Partitioning decision:

- intraday intervals stay day-partitioned because they are large and recent reads usually only need the latest few partitions
- `1d` is month-partitioned because day partitions add overhead without reducing read cost
- `1week` and `1month` are year-partitioned because the datasets are small and natural read units are coarse

### 3.2 Runtime State

State files live under grouped subfolders:

```text
data_lake/state/
  ingestion/
  paper_trade/
  backtesting/
  simulations/
```

State-folder decision:

- ingestion artifacts are separate from trading artifacts
- paper-trading runtime files are grouped together because they are updated by the worker every cycle
- backtest and simulation histories are separated because they grow independently and are only needed by their own views

## 4. Runtime Boundaries

Current boundaries:

- the worker owns Coinbase access
- the worker writes canonical `1m`, derived intervals, and paper-trading runtime state
- the dashboard reads persisted artifacts only
- backtests and simulations read parquet plus their own saved history
- `data_lake/`, `config/`, and `logs/` are shared between the worker and dashboard containers

This separation is deliberate:

- live ingestion and live trading stay coupled in one worker to avoid timing drift between services
- UI requests do not trigger live trading or data fetches
- backtests and simulations do not mutate live paper-trading state

## 5. Key Design Decisions

### 5.1 Combined Worker Instead of Separate Ingestion and Trading Schedulers

Decision:

- run trading immediately after a completed ingestion cycle in the same process

Why:

- avoids separate scheduler drift and offset coordination
- guarantees trading decisions use freshly ingested local data
- simplifies Docker and healthchecks

Tradeoff:

- one worker now owns more responsibility, so failures need clear logging and health monitoring

### 5.2 Canonical `1m` Source of Truth

Decision:

- derive all larger intervals from locally persisted `1m` candles instead of fetching multiple resolutions independently

Why:

- one consistent market-data source
- simpler gap detection and replay logic
- backtests, simulations, and the live worker all agree on interval construction

Tradeoff:

- rebuilding derived intervals can be expensive over large `1m` history if done repeatedly

### 5.3 Interval-Specific Parquet Partitioning

Decision:

- partition each interval at the coarsest level that still supports efficient reads

Why:

- reduces unnecessary filesystem depth for `1d`, `1week`, and `1month`
- improves readability of the lake layout
- better matches how those intervals are queried

Tradeoff:

- store logic becomes interval-aware instead of generic `year/month/day` for everything

### 5.4 Rebuild Derived Intervals from Local `1m`

Decision:

- support `python -m app.ingestion.backfill --reuse-existing-source` to rebuild derived intervals from local source data without refetching Coinbase

Why:

- makes structural migrations and derived-data repair safe and cheap
- avoids wasting API calls when canonical `1m` already exists

Tradeoff:

- semantics must be explicit so users understand this mode is rebuild-oriented, not a strict coverage validator

### 5.5 Mode-Specific State Loading in FastAPI

Decision:

- load only the state/log/history needed by the active page or subview

Why:

- prevents the Bitcoin page from reading large backtest/simulation histories
- prevents paper, backtest, and simulation trade views from loading unrelated artifacts
- keeps request latency bounded by the active feature only

Examples:

- `/bitcoin` loads ingestion state, paper snapshot context, and chart candles
- `mode=paper` loads only paper-trading artifacts
- `mode=backtest` loads only backtest artifacts
- `mode=simulation` loads only simulation artifacts

### 5.6 Fast Replay Bounds from Actual `1m` Data

Decision:

- determine backtest/simulation date-picker bounds from the actual canonical `1m` parquet range

Why:

- UI range reflects the real dataset instead of a hardcoded date
- supports historical expansion automatically as the lake grows

Optimization detail:

- bounds are read from the oldest and newest partition files only, not by scanning the full dataset

### 5.7 Bitcoin Page Chart Optimization

Decision:

- load only the candle sets actually required by the visible chart ranges

Current chart policy:

- `1H` -> `60 x 1m`
- `4H` -> `24 x 10m`
- `8H` -> `48 x 10m`
- `1D` -> `48 x 30m`
- `ALL` -> all available `1month`

Why:

- avoids sending large chart payloads that the UI never uses
- keeps the Bitcoin page fast even when `1m` history is large

### 5.8 Docker Bind-Mount Read Optimization

Decision:

- avoid expensive recursive partition discovery on hot paths

Why:

- Docker Desktop bind mounts make broad directory traversal much slower than exact file reads
- recent candle loads and replay-bound lookups should walk only the newest or boundary partitions they need

Tradeoff:

- store code is more specialized and less naive than a simple full-tree scan

## 6. End-to-End Data Flow

```text
Coinbase
-> canonical 1m ingestion
-> gap audit + ingestion state
-> derived interval rebuild
-> worker trading cycle
-> paper-trade state/logs
-> FastAPI page/API reads
-> optional backtest replay
-> optional simulation sweeps
```

## 7. Docker Architecture

Defined in [docker-compose.yml](../docker-compose.yml).

Services:

- `market-execution-worker`
- `dashboard-api`

Shared mounts:

- `./data_lake:/app/data_lake`
- `./config:/app/config`
- `./logs:/app/logs`

Docker decisions:

- keep the worker and dashboard separate so the UI can restart independently from scheduled execution
- share the same persisted volumes so the dashboard always reads the worker’s latest state
- use healthchecks to make container status reflect ingestion/trading freshness

## 8. FastAPI Surface

Main pages:

- `/bitcoin`
- `/trades`

JSON endpoints:

- `/health`
- `/api/state`
- `/api/ingestion`
- `/api/trading`
- `/api/candles`
- `/api/trades`
- `/api/backtest`

UI decisions:

- Bitcoin is a market context page, optimized for fast chart reads
- Trades is a workspace with three subviews:
  - Paper
  - Backtest
  - Simulation
- each subview should only load the data it actually renders

## 9. Operational Notes

- if canonical `1m` exists and only derived intervals need repair, delete the derived folders and run:

```bash
python -m app.ingestion.backfill --start 2025-01-01T00:00:00Z --reuse-existing-source
```

- if `.env` contains explicit state paths, those override code defaults; config and disk layout must match
- on Windows, large rebuilds/backfills should be run with the Docker stack stopped to avoid file replacement conflicts

## 10. Known Constraints

- Coinbase remains the only live market-data source in the current runtime
- backtests and simulations depend on canonical `1m` being present and derived intervals being rebuilt correctly
- append-only history files can become large over time; they must not be loaded into unrelated views
- Docker bind-mount filesystem behavior remains a practical performance constraint for parquet access patterns
