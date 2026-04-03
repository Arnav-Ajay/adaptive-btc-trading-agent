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

- DCA (base accumulation)
- Swing trading (momentum + ATR risk control)
- Regime detection (EMA + RSI)

Important:

The system is **functionally correct but not yet optimized for edge**.

Backtests show:

- execution realism is working
- strategy edge is still being improved

## Capabilities

- Paper trading with full state persistence
- Backtesting with replay engine
- Simulation with parameter sweeps
- Execution cost modeling
- Trade ledger + decision logs

## Architecture

High-level:

Coinbase → Ingestion → Parquet Data Lake → Trading Engine → API/UI

See full details: [`docs/architecture.md`](docs/architecture.md)

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
5. Run the historical backfill:

```bash
python -m app.ingestion.backfill --start 2026-01-01T00:00:00Z
```
6. Start Docker Compose Stack:

```bash
docker compose up -d --build
```

## Current Docs

- [docs/architecture.md](docs/architecture.md)
- [docs/current-flow.md](docs/current-flow.md)
- [docs/metrics.md](docs/metrics.md)
- [docs/strategies.md](docs/strategies.md)
- [docs/strategy-growth.md](docs/strategy-growth.md)

## Next Evolution

- regime-aware strategy gating
- improved entry quality
- structured exits (TP / trailing stops)
- reduced trade frequency
- probabilistic decision frameworks
- llm based decision framework