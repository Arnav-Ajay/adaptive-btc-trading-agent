# adaptive-btc-trading-agent

This repository currently runs two working services:

- a Coinbase market data ingestor
- a local-data paper-trading runtime

The ingestor fetches `BTC-USD` `1m` candles from Coinbase on a fixed schedule, deduplicates overlapping windows, writes partitioned parquet files, updates a state file, and emits both console and file logs.

The trading runtime reads recent candles from the local parquet data lake, computes indicators, selects a strategy, and executes paper trades against an in-memory broker.

## What Works

- Coinbase candle ingestion with retries
- 30-minute scheduled ingestion with APScheduler
- partitioned parquet storage under `data_lake/`
- deduplication by candle timestamp
- ingestion state tracking
- Dockerized ingestor service with healthcheck
- ingestion logs to stdout and `logs/ingestion/ingestion.log`
- local parquet-backed market data reader
- indicator computation: ATR, RSI, EMA, MACD
- regime detection and strategy routing
- paper trade execution

## Data Layout

```text
data_lake/
  symbol=BTC-USD/
    interval=1m/
      year=2026/
        month=03/
          day=24/
            data.parquet
  state/
    coinbase_btc_usd_1m.json

logs/
  ingestion/
    ingestion.log
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

Run the paper-trading loop:

```bash
python -m app.main
```

## Docker

Start the scheduled ingestor:

```bash
docker compose up -d market-data-ingestor
```

Watch logs:

```bash
docker compose logs -f market-data-ingestor
```

Check container health:

```bash
docker inspect --format "{{json .State.Health}}" adaptive-btc-market-data-ingestor
```

## Flow

See [docs/current-flow.md](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/docs/current-flow.md) for the current runtime flow.
