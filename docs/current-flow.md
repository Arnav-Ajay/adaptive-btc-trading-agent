# Current Flow

This document describes only the flow that is currently implemented and verified.

## 1. Scheduled Ingestion Flow

Entry point: [collector_runner.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/scheduler/collector_runner.py)

```text
Load config
-> configure ingestion logging
-> compute next aligned 30-minute boundary
-> start APScheduler
-> trigger CoinbaseIngestionService.collect_once()
```

Collection flow: [collector.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/ingestion/collector.py)

```text
Fetch 90-minute overlapping window of BTC-USD 1m candles from Coinbase
-> retry on failure
-> validate rows
-> merge with existing parquet partition
-> deduplicate by timestamp
-> rewrite affected partition
-> update ingestion state file
-> write logs
```

Storage flow: [parquet_store.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/ingestion/parquet_store.py)

```text
Normalized candles
-> DataFrame
-> partition by year/month/day
-> read existing partition if present
-> concat + dedupe + sort
-> atomic parquet write
```

State and health:

- state file: [data_lake/state/coinbase_btc_usd_1m.json](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/coinbase_btc_usd_1m.json)
- healthcheck entry point: [healthcheck.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/scheduler/healthcheck.py)
- ingestion log file: [logs/ingestion/ingestion.log](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/logs/ingestion/ingestion.log)

## 2. Paper-Trading Flow

Entry point: [app/main.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/main.py)

```text
Load config
-> read recent candles from local parquet data lake
-> compute ATR / RSI / EMA / MACD
-> detect market regime
-> select strategy
-> generate signals
-> review signals against portfolio constraints
-> execute paper orders
-> log cycle summary
```

Local data reader:

- [parquet_market_data.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/data/parquet_market_data.py)
- [data_normalizer.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/data/data_normalizer.py)

Strategy and execution path:

- indicators: [indicators.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/indicators.py)
- router: [router.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/router.py)
- DCA strategy: [dca.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/dca.py)
- paper broker: [paper_broker.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/execution/paper_broker.py)

## 3. Runtime Boundaries

The current separation is:

- the ingestor is the only runtime that talks to Coinbase for candles
- the trading loop reads only from the local parquet lake
- ingestion persistence survives Docker rebuilds because `data_lake/` is bind-mounted
- ingestion logs survive Docker restarts because `logs/` is bind-mounted
