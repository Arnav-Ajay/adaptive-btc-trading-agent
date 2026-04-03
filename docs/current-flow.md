# Current Flow

This document describes only the flows that are currently implemented and verified.

## 1. Combined Market-Execution Worker

Entry point: [app/scheduler/worker_runner.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/scheduler/worker_runner.py)

```text
Load config
-> configure worker logging
-> if no ingestion state and no canonical data exist, queue an immediate bootstrap worker cycle
-> compute next aligned 30-minute boundary
-> sleep until that exact boundary
-> run one worker cycle:
   -> CoinbaseIngestionService.collect_once()
   -> run_cycle()
```

The worker is time-aligned only on the ingestion boundary. Trading no longer has a separate scheduler or offset. It runs immediately after a completed ingestion cycle.

## 2. Ingestion Flow

Collection flow: [app/ingestion/collector.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/ingestion/collector.py)

```text
Fetch overlapping BTC-USD 1m candles from Coinbase
-> retry on failure
-> detect source-side gaps in fetched candles
-> normalize into Candle objects
-> merge with existing parquet partitions
-> deduplicate by timestamp
-> rewrite affected partitions
-> detect recent continuity gaps in canonical 1m parquet
-> persist gap audit/event files
-> build derived intervals from canonical 1m data
-> update ingestion state file
-> write logs
```

Storage and preprocessing:

- parquet storage: [app/ingestion/parquet_store.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/ingestion/parquet_store.py)
- derived interval builder: [app/ingestion/preprocessor.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/ingestion/preprocessor.py)

Derived intervals currently written:

- `10m`
- `30m`
- `1hr`
- `1d`
- `1week`
- `1month`

Ingestion state and health:

- ingestion state: [data_lake/state/coinbase_btc_usd_1m.json](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/coinbase_btc_usd_1m.json)
- ingestion gap audit: [data_lake/state/ingestion_gap_audit.json](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/ingestion_gap_audit.json)
- ingestion gap events: [data_lake/state/ingestion_gap_events.jsonl](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/ingestion_gap_events.jsonl)
- worker healthcheck combines ingestion freshness and trading freshness: [app/scheduler/worker_healthcheck.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/scheduler/worker_healthcheck.py)
- ingestion log: [logs/ingestion/ingestion.log](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/logs/ingestion/ingestion.log)

## 3. Sequential Paper-Trading Flow

One-shot entry point: [app/main.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/main.py)

```text
After the worker completes ingestion:
-> read recent candles from local parquet data lake
-> validate candle freshness and minimum history
-> compute ATR / RSI / EMA / MACD
-> update mark price and evaluate open swing stop-losses
-> detect market regime
-> choose strategy stack
-> generate signals
-> review and size signals
-> execute paper trades through fee/spread/slippage model
-> if a swing stop-loss exit fired, skip new entries for that cycle
-> update realized PnL and cumulative execution costs
-> persist broker state, trade ledger, cycle log, and portfolio snapshot
```

Trading data reader:

- [app/data/parquet_market_data.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/data/parquet_market_data.py)
- [app/data/data_normalizer.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/data/data_normalizer.py)

Feature and strategy path:

- indicators: [app/features/indicators.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/indicators.py)
- regime detection: [app/features/regime_features.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/features/regime_features.py)
- strategy router: [app/strategies/router.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/router.py)
- hybrid strategy: [app/strategies/hybrid.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/hybrid.py)
- DCA strategy: [app/strategies/dca.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/dca.py)
- swing strategy: [app/strategies/swing_atr.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/strategies/swing_atr.py)
- order review/execution: [app/execution/order_manager.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/execution/order_manager.py)
- paper broker: [app/execution/paper_broker.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/execution/paper_broker.py)

Persistent trading artifacts:

- broker state: [data_lake/state/paper_broker_state.json](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/paper_broker_state.json)
- trade ledger: [data_lake/state/paper_trade_ledger.jsonl](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/paper_trade_ledger.jsonl)
- cycle log: [data_lake/state/paper_cycle_log.jsonl](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/paper_cycle_log.jsonl)
- portfolio snapshot: [data_lake/state/paper_portfolio_snapshot.json](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/paper_portfolio_snapshot.json)
- decision trace: [data_lake/state/paper_decision_trace.jsonl](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/paper_decision_trace.jsonl)
- trading log: [logs/trading/trading.log](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/logs/trading/trading.log)

Paper-trading accounting:

- execution costs are applied inside [app/execution/paper_broker.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/execution/paper_broker.py)
- the current model tracks separately:
  - fees
  - spread cost
  - slippage cost
- realized PnL is accumulated in broker state and surfaced in portfolio snapshots

Trading health:

- the worker freshness check uses the latest cycle timestamp via [app/scheduler/trading_healthcheck.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/scheduler/trading_healthcheck.py)

## 4. Backfill Flow

Entry point: [app/ingestion/backfill.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/ingestion/backfill.py)

```text
Read start/end arguments
-> fetch historical windows from Coinbase within API limits
-> write canonical 1m parquet data
-> build the same derived intervals
-> update the main ingestion state file
```

Backfill notes:

- backfill updates [data_lake/state/coinbase_btc_usd_1m.json](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/coinbase_btc_usd_1m.json), so worker healthchecks and clean bootstrap runs see the restored history
- on Windows, large local backfills should be run with the Docker stack stopped to avoid parquet file-replace conflicts while containers are reading from the lake

## 5. Dashboard/API Flow

API entry point: [app/api/main.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/api/main.py)

State loader:

- [app/api/state_reader.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/api/state_reader.py)

```text
Read ingestion state
-> read trading state and ledger files
-> read saved backtest history and latest saved backtest when needed
-> read saved simulation history and latest saved simulation when needed
-> load chart candles from local parquet when needed
-> render Bitcoin page
-> render Trades page subviews:
   - Paper
   - Backtest
   - Simulation
-> expose JSON health/state endpoints
```

Current dashboard pages:

- `/bitcoin`
- `/trades`

Current JSON endpoints:

- `/health`
- `/api/state`
- `/api/ingestion`
- `/api/trading`
- `/api/candles`
- `/api/trades`
- `/api/backtest`

## 6. Backtest Flow

Entry point: [app/backtest/engine.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/backtest/engine.py)

```text
Load historical candles from parquet
-> replay candles sequentially from minimum-history threshold onward
-> compute the same indicators used by the live trading runtime
-> evaluate open swing stop-losses
-> run the same regime and strategy path
-> stop early if the portfolio drawdown guard is breached
-> execute on an isolated paper broker state
-> record equity curve and trades
-> compute replay metrics
-> persist latest run and append to backtest history
```

Backtest metrics:

- total return
- buy-and-hold return
- max drawdown
- Sharpe ratio
- filled trade count
- closed swing trade win rate

Saved backtest artifacts:

- latest run: [data_lake/state/backtest_latest.json](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/backtest_latest.json)
- run history: [data_lake/state/backtest_history.jsonl](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/backtest_history.jsonl)

## 7. Simulation Flow

Entry point: [app/simulation/engine.py](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/app/simulation/engine.py)

```text
Load a bounded parameter grid
-> clone the current config for each candidate
-> run backtests for each parameter set
-> rank candidates by:
   - return
   - drawdown
   - profit factor
   - Sharpe
-> persist latest sweep and append to simulation history
```

Saved simulation artifacts:

- latest run: [data_lake/state/simulation_latest.json](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/simulation_latest.json)
- run history: [data_lake/state/simulation_history.jsonl](d:/Users/arnav/Documents/Github_Repos/apziva/adaptive-btc-trading-agent/data_lake/state/simulation_history.jsonl)

## 8. Runtime Boundaries

The current separation is:

- the combined worker is the only runtime that talks to Coinbase for market data
- the trading cycle runs only after a completed ingestion cycle inside that same worker
- preprocessing derives larger intervals from canonical `1m` candles
- the dashboard reads only persisted files and parquet data
- `data_lake/`, `config/`, and `logs/` are shared between the worker and dashboard containers
