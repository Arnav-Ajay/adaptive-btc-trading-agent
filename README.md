# Adaptive BTC Trading Agent

Adaptive BTC Trading Agent is a parquet-backed paper-trading, backtesting, and simulation system for BTC-USD.

Core properties:
- parquet market-data lake
- deterministic paper execution with fees, spread, and slippage
- unified strategy stack across paper trading, backtesting, and simulation
- dashboard and JSON API for runtime inspection

Authoritative docs:
- [docs/01_architecture.md](docs/01_architecture.md)
- [docs/02_strategy_specification.md](docs/02_strategy_specification.md)
- [docs/03_metrics_reference.md](docs/03_metrics_reference.md)
- [docs/04_llm_architecture.md](docs/04_llm_architecture.md)
- [docs/05_future_work.md](docs/05_future_work.md)

## Demo Mode

Demo mode runs the project without:
- Coinbase
- OpenAI
- Google Sheets
- Gmail
- Telegram

It uses the bundled parquet snapshot in [demo_assets](demo_assets/README.md) and keeps production behavior unchanged when disabled.

### Demo Mode Setup

1. Copy `.env.example` to `.env`.
2. Set these values in `.env`:

```dotenv
DEMO_MODE=true
GOOGLE_SHEETS_ENABLED=false
LLM_ENABLED=false
GMAIL_ENABLED=false
TELEGRAM_ENABLED=false
```

3. Bootstrap the bundled demo lake into the runtime `data_lake/`:

```bash
python scripts/bootstrap_demo_data.py --force
```

4. Start the stack:

```bash
docker compose up -d --build
```

5. Open the dashboard:

```text
http://localhost:8000
```

### Demo Mode Behavior

- the dashboard reads bundled parquet and state artifacts
- backtesting reads bundled parquet
- simulation reads bundled parquet
- the worker skips Coinbase ingestion and runs scheduled parquet-backed trading cycles only
- the paper broker, strategies, and execution model are unchanged

## Full Mode

Full mode uses the real ingestion path and optional integrations.

### Full Mode Setup

1. Copy `.env.example` to `.env`.
2. Set:

```dotenv
DEMO_MODE=false
COINBASE_API_KEY=...
COINBASE_API_SECRET=...
```

3. Optionally enable:
- `GOOGLE_SHEETS_ENABLED=true`
- `LLM_ENABLED=true`
- `GMAIL_ENABLED=true`
- `TELEGRAM_ENABLED=true`

4. Install Python dependencies if you plan to run one-off bootstrap/backfill utilities locally:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

5. If starting from an empty lake, backfill historical data first:

```bash
python -m app.ingestion.backfill --start 2026-01-01T00:00:00Z
```

6. Start the Docker services:

```bash
docker compose up -d --build
```

## Runtime Notes

- `dashboard-api` serves the UI and JSON endpoints on port `8000`
- `market-execution-worker` runs the scheduled worker
- in production mode the worker runs `Coinbase ingestion -> parquet update -> trading cycle`
- in demo mode the worker runs `trading cycle only` against the local parquet snapshot

## Useful Commands

Preview the weekly report:

```bash
python -m app.monitoring.weekly_report_runner
```

Send the weekly report:

```bash
python -m app.monitoring.weekly_report_runner --send
```

Run a one-off paper-trading cycle locally:

```bash
python -m app.main
```
