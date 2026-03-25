# adaptive-btc-trading-agent

This repository currently runs three working services:

- a scheduled Coinbase market-data ingestor
- a scheduled local-data paper-trading runtime
- a FastAPI dashboard/API over the stored runtime state

## What Works

- Coinbase `BTC-USD` candle ingestion
- 30-minute APScheduler ingestion cadence
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
- paper trading fees and explicit realized PnL tracking
- historical backtesting over parquet data
- backtest metrics:
  - total return
  - buy-and-hold return
  - max drawdown
  - Sharpe ratio
  - filled trade count
  - closed swing trade win rate
- FastAPI UI/API with:
  - Bitcoin market page
  - Trades page
  - JSON endpoints
- Dockerized ingestor, trading, and dashboard services with healthchecks

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

Run the ingestor:

```bash
python -m app.scheduler.collector_runner
```

Run a one-shot trading cycle:

```bash
python -m app.main
```

Run the scheduled trading service:

```bash
python -m app.scheduler.trading_runner
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
docker compose up -d --build market-data-ingestor trading-agent dashboard-api
```

Watch logs:

```bash
docker compose logs -f market-data-ingestor
docker compose logs -f trading-agent
docker compose logs -f dashboard-api
```

Check status:

```bash
docker compose ps
```

## Current Docs

- [docs/current-flow.md](docs/current-flow.md)
- [docs/metrics.md](docs/metrics.md)
- [docs/strategies.md](docs/strategies.md)
