# adaptive-btc-trading-agent

Production-oriented scaffolding for a modular Bitcoin trading agent with:

- config-driven behavior
- deterministic strategy core
- optional LLM advisory layer
- paper trading first
- logging, alerting, and backtesting hooks

## Current Status

Phase 1 scaffolding is in place:

- package structure created
- runnable main loop skeleton
- config loader with local cache fallback
- strategy router and paper broker interfaces
- monitoring, backtest, and LLM advisory stubs

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

The default `.env` is configured to run a single cycle in paper-trading mode.

## Core Loop

```text
Load config -> Fetch market data -> Compute indicators -> Detect regime
-> Select strategy -> Generate signals -> LLM review -> Validate signals
-> Execute paper orders -> Log and notify
```

## Next Build Phases

1. Implement live market data ingestion with `yfinance` and exchange adapters.
2. Expand indicator coverage and strategy logic.
3. Add robust persistence, reporting, and tests.
4. Add Dockerized deployment and cloud runtime hardening.

