# adaptive-btc-trading-agent

This repository currently runs two working services:

- a combined market-execution worker that ingests market data and then runs trading sequentially
- a FastAPI dashboard/API over the stored runtime state

## What Works

- Coinbase `BTC-USD` candle ingestion
- exact 30-minute worker cadence aligned to UTC half-hour boundaries
- overlapping-window fetch with parquet deduplication
- derived interval preprocessing from canonical `1m` candles:
  - `10m`
  - `30m`
  - `1hr`
  - `1d`
  - `1week`
  - `1month`
- local parquet market-data lake under `data_lake/`
- backfill script for historical or missed ingestion windows
- ingestion gap audit and structured gap event logging
- persistent ingestion state and healthchecks
- paper-trading decisions on a 30-minute schedule
- local parquet-backed trading data reader
- indicator computation:
  - ATR
  - RSI
  - EMA
  - MACD
- regime detection and strategy routing
- hybrid strategy stack:
  - DCA base layer
  - opportunistic swing entries in bullish regimes
- persistent paper broker state
- persistent paper trade ledger
- persistent cycle log and portfolio snapshot
- deterministic execution-cost model:
  - trading fee
  - spread
  - slippage
- explicit realized PnL tracking
- historical backtesting over parquet data
- backtest metrics:
  - total return
  - buy-and-hold return
  - max drawdown
  - Sharpe ratio
  - filled trade count
  - closed swing trade win rate
- saved backtest history and replay-step decision traces
- saved simulation history and ranked parameter sweeps
- FastAPI UI/API with:
  - Bitcoin market page
  - Trades page with:
    - Paper
    - Backtest
    - Simulation subviews
  - JSON endpoints
- Dockerized worker and dashboard services with healthchecks

## Data Layout

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
  state/
    coinbase_btc_usd_1m.json
    ingestion_gap_audit.json
    ingestion_gap_events.jsonl
    backfill_btc_usd_1m.json
    paper_broker_state.json
    paper_trade_ledger.jsonl
    paper_cycle_log.jsonl
    paper_portfolio_snapshot.json
    paper_decision_trace.jsonl
    backtest_latest.json
    backtest_history.jsonl
    simulation_latest.json
    simulation_history.jsonl

logs/
  ingestion/
    ingestion.log
  trading/
    trading.log
```

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## First Startup

Canonical first-run flow:

1. Clone the repository.
2. Copy `.env.example` to `.env`.
3. Fill the required values in `.env`.
4. Build the Docker services once:

```bash
docker compose up -d --build
```

5. Bring the stack down before running a large local backfill:

```bash
docker compose down
```

6. Run the historical backfill:

```bash
python -m app.ingestion.backfill --start 2026-01-01T00:00:00Z
```

7. Bring the stack back up:

```bash
docker compose up -d
```

Notes:

- Yes, backfill-first is valid now. The backfill writes the main ingestion state file, so the worker healthcheck will see that bootstrap history.
- On Windows, run large local backfills with the Docker stack stopped. The parquet writer uses atomic file replacement, and open file handles from running containers can cause `PermissionError` during bulk backfill.
- If you skip backfill entirely, the worker now performs an immediate bootstrap ingestion/trading cycle on first startup instead of waiting for the next 30-minute boundary.

Run a one-shot trading cycle:

```bash
python -m app.main
```

Run the combined scheduled worker:

```bash
python -m app.scheduler.worker_runner
```

Run a backfill:

```bash
python -m app.ingestion.backfill --start 2026-01-01T00:00:00Z
```

Run a backtest from Python:

```python
from app.backtest.engine import BacktestEngine
from app.config.settings import load_config

result = BacktestEngine(load_config()).run(symbol="BTC-USD", interval="1m")
print(result.metrics)
```

Backtest notes:

- backtests use the same fee/spread/slippage execution model as paper trading
- backtests persist the latest run and append to history under `data_lake/state/`
- backtests can halt early on:
  - max drawdown guard
- swing stop-loss exits now close positions and replay continues afterward

Run the FastAPI dashboard/API:

```bash
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

Then open:

```text
http://127.0.0.1:8000/bitcoin
http://127.0.0.1:8000/trades
```

## Docker

Start all services:

```bash
docker compose up -d --build market-execution-worker dashboard-api
```

Watch logs:

```bash
docker compose logs -f market-execution-worker
docker compose logs -f dashboard-api
```

Check status:

```bash
docker compose ps
```

Safe Windows backfill workflow:

```bash
docker compose down
python -m app.ingestion.backfill --start 2026-01-01T00:00:00Z
docker compose up -d --build market-execution-worker dashboard-api
```

## Current Docs

- [docs/current-flow.md](docs/current-flow.md)
- [docs/metrics.md](docs/metrics.md)
- [docs/strategies.md](docs/strategies.md)
- [docs/strategy-growth.md](docs/strategy-growth.md)
