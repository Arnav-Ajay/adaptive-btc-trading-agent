# Demo Assets

This directory contains the tracked parquet snapshot used by `DEMO_MODE`.

- `data_lake/` mirrors the runtime lake structure expected by the app
- canonical `1m` BTC-USD data is included
- derived demo intervals are included for dashboard and replay paths
- paper-trade and ingestion state artifacts are included for UI/runtime visibility

Bootstrap it into the ignored runtime `data_lake/` directory with:

```bash
python -m scripts.bootstrap_demo_data --force
```
