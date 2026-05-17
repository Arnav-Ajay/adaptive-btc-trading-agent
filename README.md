# Adaptive BTC Trading Agent

A research-grade crypto trading system designed to:

- simulate realistic execution (fees, spread, slippage)
- evaluate strategies through replayable backtests
- iterate on strategy logic using structured experimentation

This is not a signal bot.

This is a **trading system framework**.

## Philosophy

Most trading systems fail because:

- they ignore execution costs
- they overfit indicators
- they lack reproducibility

This system focuses on:

- execution realism
- deterministic replay
- structured strategy evolution

## What Makes This Different

- Canonical 1m market data lake (parquet-based)
- Deterministic execution model:
  - fees
  - spread
  - slippage
- Unified pipeline:
  - live trading
  - backtesting
  - simulation
- Strategy decomposition:
  - DCA (accumulation)
  - Swing (momentum)
- Full decision trace logging

## Strategy (Current State)

The system currently implements:

- DCA (base allocation / accumulation)
- Swing trading (legacy momentum + ATR risk control baseline)
- Pullback trend trading (structure-aware active layer)
- Deterministic selector-first `pullback_hybrid` profile
- Regime detection (EMA + RSI + recent structure context)

Important:

The system is **functionally correct but not yet optimized for edge**.

Backtests show:

- execution realism is working
- selector-based `pullback_hybrid` is currently outperforming the legacy hybrid and DCA baselines on the latest comparison window
- strategy edge is still being improved
- the optional LLM overlay is score-based and experimental, with modes for hard filtering, soft filtering, and weighted exposure

## Capabilities

- Paper trading with full state persistence
- Backtesting with replay engine
- Simulation with parameter sweeps
- Execution cost modeling
- Trade ledger + decision logs
- Deterministic per-cycle selector traces for `pullback_hybrid`
- Optional score-based LLM overlay for trade review and replay experiments

## Architecture

High-level:

Coinbase → Ingestion → Parquet Data Lake → Trading Engine → API/UI

See full details: [`docs/architecture.md`](docs/architecture.md)

## Quick Start

```bash
docker compose up --build -d
```

Make sure Docker Engine is already running

## First Startup

Prerequisite :
1. coinbase account to get the api key -> `.env`
2. docker installed

Canonical first-run flow:

1. Clone the repository.
2. Copy `.env.example` to `.env`.
3. Fill the required values in `.env`.
4. Install dependencies, primarily for backfill:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

5. Run the historical backfill:

```bash
python -m app.ingestion.backfill --start 2026-01-01T00:00:00Z
```

6. Build the Docker services:

```bash
docker compose up -d --build
```
7. Go to `http://localhost:8000`

## Current Docs

- [docs/architecture.md](docs/architecture.md)
- [docs/current-flow.md](docs/current-flow.md)
- [docs/llm-runtime-logic.md](docs/llm-runtime-logic.md)
- [docs/llm-optional-overlay.md](docs/llm-optional-overlay.md)
- [docs/metrics.md](docs/metrics.md)
- [docs/pullback-strategy-spec.md](docs/pullback-strategy-spec.md)
- [docs/strategy-selector-contract.md](docs/strategy-selector-contract.md)
- [docs/strategy-pivot-plan.md](docs/strategy-pivot-plan.md)
- [docs/strategies.md](docs/strategies.md)
- [docs/strategy-growth.md](docs/strategy-growth.md)

## Next Evolution

- regime-aware strategy gating
- improved entry quality
- structured exits (TP / trailing stops)
- reduced trade frequency
- probabilistic decision frameworks
- llm based decision framework
- score-based LLM overlay experiments
- config input from google sheets
- telegram message at every trade (Buy/Sell)
