"""FastAPI dashboard and JSON API for the current trading system state."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from statistics import mean

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.backtest.engine import BacktestEngine
from app.api.state_reader import load_dashboard_state
from app.config.settings import load_config

app = FastAPI(title="Adaptive BTC Trading Agent", version="0.1.0")


def _nav(active: str) -> str:
    """Render the shared top navigation."""
    def cls(name: str) -> str:
        return "nav-link active" if name == active else "nav-link"

    return f"""
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">AB</div>
        <div>
          <div class="brand-title">Adaptive BTC Trading Agent</div>
          <div class="brand-sub">Paper trading cockpit</div>
        </div>
      </div>
      <nav class="nav">
        <a class="{cls('bitcoin')}" href="/bitcoin">Bitcoin</a>
        <a class="{cls('trades')}" href="/trades">Trades</a>
      </nav>
    </header>
    """


def _base_html(title: str, active: str, body: str, script: str = "") -> str:
    """Wrap page content in the shared application shell."""
    return f"""
    <html>
      <head>
        <title>{escape(title)}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
          body {{ margin:0; font-family:"Segoe UI",sans-serif; background:linear-gradient(180deg,#0a1018 0%,#121b28 20%,#f4f6f8 20%,#f4f6f8 100%); color:#132033; }}
          .shell {{ max-width:1280px; margin:0 auto; padding:1.4rem 1.4rem 2rem; }}
          .topbar {{ display:flex; justify-content:space-between; align-items:center; gap:1rem; margin-bottom:1rem; }}
          .brand {{ display:flex; align-items:center; gap:.85rem; color:#ecf3ff; }}
          .brand-mark {{ width:44px; height:44px; border-radius:14px; display:grid; place-items:center; font-weight:800; background:linear-gradient(135deg,#f59e0b 0%,#2563eb 100%); color:white; }}
          .brand-title {{ font-weight:700; font-size:1.05rem; }}
          .brand-sub {{ font-size:.84rem; opacity:.75; }}
          .nav {{ display:flex; gap:.65rem; }}
          .nav-link {{ text-decoration:none; color:#dbe7f6; border:1px solid rgba(255,255,255,.12); padding:.65rem 1rem; border-radius:999px; font-weight:600; }}
          .nav-link.active {{ background:white; color:#132033; border-color:white; }}
          .banner {{ display:grid; grid-template-columns:repeat(5,1fr); gap:.8rem; margin-bottom:1rem; }}
          .panel {{ background:#fff; border:1px solid #d9e1ea; border-radius:20px; padding:1.1rem; box-shadow:0 20px 45px rgba(16,24,40,.08); }}
          .label {{ color:#667085; font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; }}
          .value {{ margin-top:.25rem; font-size:1.12rem; font-weight:700; }}
          .page-grid {{ display:grid; grid-template-columns:1.4fr .6fr; gap:1rem; }}
          .stack {{ display:grid; gap:1rem; }}
          .hero {{ background:linear-gradient(135deg,#101827 0%,#17304c 100%); color:#ecf3ff; }}
          .hero-price {{ font-size:3.2rem; font-weight:800; margin-top:.35rem; }}
          .hero-row,.toolbar {{ display:flex; gap:.7rem; flex-wrap:wrap; margin-top:.8rem; }}
          .pill {{ display:inline-flex; align-items:center; gap:.35rem; padding:.35rem .7rem; border-radius:999px; font-size:.82rem; font-weight:700; }}
          .pill.up {{ background:rgba(34,197,94,.18); color:#9cf7b7; }} .pill.down {{ background:rgba(239,68,68,.18); color:#fecaca; }} .pill.neutral {{ background:rgba(255,255,255,.12); color:#dbe7f6; }} .pill.ok {{ background:#d5f5de; color:#166534; }} .pill.warn {{ background:#fff1c2; color:#8a5b00; }} .pill.danger {{ background:#fee2e2; color:#991b1b; }}
          .subgrid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:.8rem; margin-top:1rem; }}
          .metric {{ border-radius:16px; padding:.95rem; background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.09); }}
          .metric.light {{ background:#fff; border:1px solid #d9e1ea; }}
          .metric .metric-label {{ color:#667085; font-size:.8rem; }} .hero .metric .metric-label {{ color:rgba(236,243,255,.75); }}
          .metric .metric-value {{ margin-top:.25rem; font-weight:700; font-size:1.15rem; }}
          .chart-panel {{ padding:0; overflow:hidden; }} .chart-header {{ display:flex; justify-content:space-between; align-items:baseline; gap:1rem; padding:1rem 1rem .2rem; }} .chart-sub {{ color:#667085; font-size:.9rem; }} .chart-wrap {{ padding:.5rem 1rem 1rem; }}
          .field {{ display:grid; gap:.35rem; min-width:130px; }} .field label {{ color:#667085; font-size:.8rem; font-weight:600; }} .field select,.field input {{ border:1px solid #d0d8e2; border-radius:12px; padding:.7rem .8rem; background:white; font:inherit; }} .field select:disabled {{ background:#f8fafc; color:#98a2b3; }}
          canvas {{ width:100%; height:420px; background:linear-gradient(180deg,#0d1520 0%,#13233b 100%); border-radius:18px; display:block; }}
          .decision-card {{ background:#f8fafc; }} .decision-list {{ margin:.8rem 0 0; padding-left:1.1rem; }} .decision-card p {{ margin:.45rem 0 0; }}
          .mode {{ display:grid; gap:.4rem; border-radius:18px; padding:1rem; border:1px solid #d9e1ea; }} .mode.live {{ background:#fffaf0; border-color:#f5d38c; }}
          .ghost {{ border-radius:999px; border:1px solid #cbd5e1; background:#eef2f7; color:#667085; font-weight:700; padding:.65rem .95rem; width:fit-content; cursor:pointer; }}
          .ghost:disabled {{ cursor:not-allowed; opacity:.72; }}
          table {{ width:100%; border-collapse:collapse; margin-top:.9rem; }} th,td {{ text-align:left; padding:.75rem .65rem; border-bottom:1px solid #e5e7eb; font-size:.92rem; }} th {{ color:#667085; font-weight:700; }} .empty {{ color:#667085; }}
          .footer {{ margin-top:1.25rem; display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:1rem 1.1rem; border-radius:18px; background:rgba(255,255,255,.72); border:1px solid #d9e1ea; color:#475467; font-size:.9rem; }}
          .footer-meta {{ display:flex; gap:.65rem; align-items:center; flex-wrap:wrap; }}
          .footer-sep {{ color:#98a2b3; }}
          .footer a {{ color:#1d4ed8; text-decoration:none; font-weight:600; }}
          .status-strip {{ display:grid; grid-template-columns:repeat(5,1fr); gap:.8rem; margin-bottom:1rem; }}
          .status-chip {{ padding:.9rem 1rem; border-radius:18px; background:rgba(255,255,255,.72); border:1px solid rgba(217,225,234,.9); box-shadow:0 14px 28px rgba(16,24,40,.06); }}
          .status-chip .status-value {{ margin-top:.22rem; font-weight:700; font-size:1.02rem; }}
          .btc-layout {{ display:grid; grid-template-columns:minmax(0,1.45fr) 340px; gap:1rem; }}
          .btc-main {{ display:grid; gap:1rem; }}
          .market-card {{ padding:0; overflow:hidden; background:linear-gradient(145deg,#0f1724 0%,#15283e 58%,#1f4a73 100%); color:#f5f9ff; border:none; }}
          .market-card .label {{ color:rgba(226,236,249,.72); }}
          .market-top {{ display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; padding:1.2rem 1.25rem 0; }}
          .market-title {{ font-size:1.65rem; font-weight:800; letter-spacing:-.02em; }}
          .market-sub {{ color:rgba(229,236,246,.72); margin-top:.2rem; max-width:720px; font-size:.92rem; }}
          .market-price-row {{ display:flex; justify-content:space-between; align-items:flex-end; gap:1rem; padding:1rem 1.25rem .4rem; }}
          .market-price {{ font-size:3.4rem; font-weight:800; line-height:1; letter-spacing:-.04em; }}
          .market-change {{ font-size:1rem; font-weight:700; }}
          .market-stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:.7rem; padding:0 1.25rem 1.2rem; }}
          .market-stat {{ padding:.85rem .9rem; border-radius:16px; background:rgba(255,255,255,.07); border:1px solid rgba(255,255,255,.08); }}
          .market-stat .metric-label {{ color:rgba(229,236,246,.72); font-size:.76rem; text-transform:uppercase; letter-spacing:.05em; }}
          .market-stat .metric-value {{ margin-top:.28rem; font-weight:700; font-size:1.02rem; }}
          .chart-card {{ padding:.95rem; background:#ffffff; }}
          .chart-panel-head {{ display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; margin-bottom:.8rem; }}
          .chart-title {{ font-size:1.35rem; font-weight:800; letter-spacing:-.02em; }}
          .chart-note {{ color:#667085; font-size:.9rem; max-width:640px; }}
          .chart-toolbar-grid {{ display:grid; grid-template-columns:1.15fr 1fr auto; gap:.7rem; align-items:end; margin-bottom:.85rem; }}
          .toolbar-block {{ display:grid; gap:.35rem; }}
          .toolbar-label {{ color:#667085; font-size:.76rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; }}
          .segmented {{ display:flex; gap:.45rem; flex-wrap:wrap; }}
          .seg-btn {{ border-radius:999px; border:1px solid #d0d8e2; background:#eef2f7; color:#475467; font-weight:700; padding:.6rem .95rem; cursor:pointer; }}
          .filter-grid {{ display:none; grid-template-columns:1fr 1fr auto; gap:.7rem; align-items:end; margin-bottom:.7rem; }}
          .filter-actions {{ display:flex; gap:.45rem; flex-wrap:wrap; }}
          .status-line {{ color:#667085; font-size:.92rem; margin-bottom:.7rem; }}
          .chart-surface {{ width:100%; height:470px; background:linear-gradient(180deg,#0d1520 0%,#13233b 100%); border-radius:22px; overflow:hidden; }}
          .btc-side {{ display:grid; gap:1rem; }}
          .side-card {{ background:#ffffff; border:1px solid #d9e1ea; border-radius:20px; padding:1rem; box-shadow:0 16px 32px rgba(16,24,40,.06); }}
          .side-title {{ font-size:1.05rem; font-weight:800; margin-top:.1rem; }}
          .indicator-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:.7rem; margin-top:.85rem; }}
          .indicator-tile {{ border:1px solid #e4e8ef; border-radius:16px; padding:.85rem .9rem; background:#fbfcfe; }}
          .indicator-tile .metric-label {{ color:#667085; font-size:.76rem; text-transform:uppercase; letter-spacing:.05em; }}
          .indicator-tile .metric-value {{ margin-top:.28rem; font-weight:700; font-size:1.02rem; }}
          .indicator-group {{ margin-top:.95rem; }}
          .indicator-group:first-of-type {{ margin-top:.8rem; }}
          .indicator-group-title {{ color:#667085; font-size:.76rem; font-weight:800; text-transform:uppercase; letter-spacing:.06em; margin-bottom:.55rem; }}
          .market-mini {{ display:grid; gap:.7rem; margin-top:.85rem; }}
          .mini-row {{ display:flex; justify-content:space-between; gap:1rem; padding:.75rem .85rem; border-radius:14px; background:#f8fafc; border:1px solid #e5e7eb; }}
          .mini-row .mini-label {{ color:#667085; font-size:.82rem; }}
          .mini-row .mini-value {{ font-weight:700; }}
          .value-positive {{ color:#15803d; }}
          .value-negative {{ color:#b42318; }}
          @media (max-width:1050px) {{ .banner,.page-grid,.subgrid,.status-strip,.btc-layout,.market-stats,.chart-toolbar-grid,.filter-grid {{ grid-template-columns:1fr; }} .footer {{ flex-direction:column; align-items:flex-start; }} .market-price-row,.market-top {{ flex-direction:column; align-items:flex-start; }} }}
        </style>
      </head>
      <body><div class="shell">{_nav(active)}{body}<footer class="footer"><div>Built by <strong>Arnav</strong> / <strong>Kaijo</strong></div><div class="footer-meta"><span>Adaptive BTC Trading Agent</span><span class="footer-sep">|</span><a href="https://github.com/Arnav-Ajay" target="_blank" rel="noreferrer">GitHub</a></div></footer></div>{script}</body>
    </html>
    """


def _btc_window_summary(candles: list[dict[str, object]]) -> dict[str, float | str]:
    """Summarize current BTC candles for the hero panel."""
    if not candles:
        return {"price": 0.0, "change_percent": 0.0, "window_high": 0.0, "window_low": 0.0, "avg_volume": 0.0, "latest_timestamp": "n/a"}
    closes = [float(candle["close"]) for candle in candles]
    first = closes[0]
    last = closes[-1]
    return {
        "price": last,
        "change_percent": 0.0 if first == 0 else ((last - first) / first) * 100,
        "window_high": max(float(candle["high"]) for candle in candles),
        "window_low": min(float(candle["low"]) for candle in candles),
        "avg_volume": mean(float(candle["volume"]) for candle in candles),
        "latest_timestamp": str(candles[-1]["timestamp"]),
    }


def _data_freshness(latest_ingested_timestamp: str | None) -> tuple[str, str]:
    """Classify data freshness from the ingestion heartbeat."""
    if not latest_ingested_timestamp:
        return "Data Missing", "danger"
    latest = datetime.fromisoformat(latest_ingested_timestamp)
    age_minutes = (datetime.now(UTC) - latest.astimezone(UTC)).total_seconds() / 60
    if age_minutes <= 10:
        return f"Data Fresh ({age_minutes:.1f} min)", "ok"
    if age_minutes <= 30:
        return f"Data Aging ({age_minutes:.1f} min)", "warn"
    return f"Data Stale ({age_minutes:.1f} min)", "danger"


def _portfolio_metrics(snapshot: dict[str, object], initial_cash: float) -> dict[str, float]:
    """Compute simple portfolio performance stats."""
    cash = float(snapshot.get("cash_usd", 0.0))
    btc_units = float(snapshot.get("btc_units", 0.0))
    equity = float(snapshot.get("equity_usd", 0.0))
    avg_entry = float(snapshot.get("avg_entry_price", 0.0))
    last_mark = float(snapshot.get("last_mark_price", 0.0))
    total_pnl = equity - initial_cash
    unrealized = ((last_mark - avg_entry) * btc_units) if btc_units > 0 and avg_entry > 0 else 0.0
    realized = total_pnl - unrealized
    exposure = 0.0 if equity <= 0 else ((btc_units * last_mark) / equity) * 100
    return {
        "cash": cash, "btc_units": btc_units, "equity": equity, "avg_entry": avg_entry, "last_mark": last_mark,
        "total_pnl": total_pnl, "unrealized_pnl": unrealized, "realized_pnl": realized, "exposure_percent": exposure,
        "dca_btc_units": float(snapshot.get("dca_btc_units", 0.0)), "swing_btc_units": float(snapshot.get("swing_btc_units", 0.0)),
    }


def _trend_strength(indicators: dict[str, object]) -> tuple[float, str]:
    """Return EMA spread and a simple trend label."""
    ema_fast = float(indicators.get("ema_fast", 0.0))
    ema_slow = float(indicators.get("ema_slow", 0.0))
    spread = ema_fast - ema_slow
    label = "Bullish" if spread > 20 else "Weak bullish" if spread > 0 else "Bearish" if spread < -20 else "Weak bearish" if spread < 0 else "Flat"
    return spread, label


def _volatility_label(atr: float, price: float) -> str:
    """Bucket ATR into a simple qualitative label."""
    if price <= 0:
        return "Unknown"
    ratio = (atr / price) * 100
    if ratio >= 0.35:
        return "High"
    if ratio >= 0.15:
        return "Medium"
    return "Low"


def _decision_breakdown(latest_cycle: dict[str, object] | None, latest_trace: dict[str, object] | None) -> dict[str, object]:
    """Turn the raw trace into a more readable decision narrative."""
    if not latest_cycle:
        return {"headline": "No decision recorded", "decision": "No data", "reason_lines": ["The trading loop has not recorded a cycle yet."], "interpretation": "Run the trading loop to produce the first decision record."}
    trace = list(latest_trace.get("decision_trace", [])) if latest_trace else []
    executions = latest_cycle.get("execution_results", [])
    signal_count = int(latest_cycle.get("signal_count", 0))
    decision = "BUY" if any(item.get("accepted") for item in executions) else ("WATCH" if signal_count > 0 else "NO BUY")
    if any("price_above_drop_threshold" in item for item in trace):
        threshold = next((item for item in trace if item.startswith("threshold:")), "").replace("threshold:required_price_at_or_below=", "Required <= $")
        observed = next((item for item in trace if item.startswith("observed:")), "").replace("observed:last_price=", "Current price = $")
        return {"headline": f"Decision: {decision}", "decision": decision, "reason_lines": ["Price is above the configured DCA threshold.", threshold, observed], "interpretation": "Market is not favorable for accumulation yet, so the DCA layer is waiting for a deeper dip."}
    if any("momentum_conditions_not_met" in item for item in trace):
        checks = [item.replace("check:", "").replace(" actual=", " = ").replace(" fast=", " | fast=").replace(" slow=", " slow=") for item in trace if item.startswith("check:")]
        return {"headline": f"Decision: {decision}", "decision": decision, "reason_lines": checks, "interpretation": "Trend exists, but the swing entry filters are not aligned strongly enough to justify a trade."}
    if any("initial_dca_entry" in item for item in trace):
        return {"headline": f"Decision: {decision}", "decision": decision, "reason_lines": ["No prior DCA buy fill existed in the ledger.", "The DCA base layer opened the initial BTC position."], "interpretation": "This is the first accumulation buy for the paper portfolio."}
    return {"headline": f"Decision: {decision}", "decision": decision, "reason_lines": trace or ["No detailed decision trace recorded."], "interpretation": "The system evaluated the current market state and kept the portfolio unchanged."}


def _confidence_snapshot(indicators: dict[str, object], regime: str) -> tuple[float, str]:
    """Build a lightweight confidence score from active indicators."""
    rsi = float(indicators.get("rsi", 50.0))
    atr = float(indicators.get("atr", 0.0))
    price = float(indicators.get("last_price", 0.0))
    ema_fast = float(indicators.get("ema_fast", 0.0))
    ema_slow = float(indicators.get("ema_slow", 0.0))
    histogram = float(indicators.get("macd_histogram", 0.0))
    score = 0.5 + min(abs(ema_fast - ema_slow) / max(price, 1.0) * 50, 0.18) + min(abs(histogram) / max(price, 1.0) * 2000, 0.12)
    if regime == "bullish" and 55 <= rsi <= 68:
        score += 0.1
    elif regime == "bearish" and rsi <= 35:
        score += 0.1
    elif regime == "sideways" and 45 <= rsi <= 55:
        score += 0.08
    if price > 0 and atr / price > 0.006:
        score -= 0.05
    score = max(0.0, min(score, 0.99))
    return score, "High" if score >= 0.72 else "Medium" if score >= 0.55 else "Low"


def _format_trade_row(trade: dict[str, object]) -> str:
    """Render one trade table row."""
    strategy = str(trade.get("strategy_name", "") or "DCAStrategy")
    signal_type = "Dip Buy" if strategy == "DCAStrategy" else "Momentum"
    side = escape(str(trade.get("side", "")).upper())
    strategy_label = escape(strategy.replace("Strategy", ""))
    return (
        "<tr>"
        f"<td>{escape(_format_display_timestamp(str(trade.get('timestamp', ''))))}</td>"
        f"<td>{side}</td>"
        f"<td>{escape(str(trade.get('symbol', '')))}</td>"
        f"<td>${float(trade.get('size_usd', 0)):.2f} USD</td>"
        f"<td>${float(trade.get('price', 0)):.2f}</td>"
        f"<td>{float(trade.get('btc_units', 0)):.6f} BTC</td>"
        f"<td>{strategy_label}</td>"
        f"<td>{escape(signal_type)}</td>"
        "</tr>"
    )


def _format_display_timestamp(value: str | None) -> str:
    """Format an ISO timestamp for UI display."""
    if not value:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    formatted = parsed.astimezone(UTC).strftime("%b %d, %I:%M %p UTC")
    return formatted.replace(" 0", " ")


def _parse_optional_iso_datetime(value: str | None) -> datetime | None:
    """Parse an optional ISO datetime string for API/query use."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_datetime:{value}") from exc


@app.get("/health")
def health() -> dict[str, str]:
    """Return a minimal API health response."""
    return {"status": "ok"}


@app.get("/api/state")
def api_state() -> dict[str, object]:
    """Return the latest combined dashboard state."""
    return load_dashboard_state(load_config())


@app.get("/api/ingestion")
def api_ingestion() -> dict[str, object] | dict[str, str]:
    """Return the latest ingestion heartbeat."""
    state = load_dashboard_state(load_config())["ingestion_state"]
    return state or {"status": "missing"}


@app.get("/api/trading")
def api_trading() -> dict[str, object]:
    """Return the latest trading-related artifacts."""
    state = load_dashboard_state(load_config())
    return {"portfolio_snapshot": state["portfolio_snapshot"], "latest_cycle": state["latest_cycle"], "latest_trace": state["latest_trace"], "latest_trade": state["latest_trade"], "recent_trades": state["recent_trades"]}


@app.get("/api/candles")
def api_candles(limit: int = Query(default=500, ge=10, le=2000), start: str | None = None, end: str | None = None) -> dict[str, object]:
    """Return recent candle data for dashboard charts."""
    candles = load_dashboard_state(load_config())["recent_candles"][-limit:]
    if start:
        candles = [candle for candle in candles if str(candle["timestamp"]) >= start]
    if end:
        candles = [candle for candle in candles if str(candle["timestamp"]) <= end]
    return {"candles": candles}


@app.get("/api/trades")
def api_trades(limit: int = Query(default=25, ge=1, le=250)) -> dict[str, object]:
    """Return recent trade ledger rows."""
    trades = load_dashboard_state(load_config())["recent_trades"]
    return {"trades": trades[-limit:]}


@app.get("/api/backtest")
def api_backtest(
    symbol: str | None = None,
    interval: str = Query(default="1m"),
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
    """Run a historical backtest over parquet candles and return summary output."""
    config = load_config()
    engine = BacktestEngine(config)
    try:
        result = engine.run(
            symbol=symbol or config.trading.symbol,
            interval=interval,
            start_at=_parse_optional_iso_datetime(start),
            end_at=_parse_optional_iso_datetime(end),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "symbol": result.symbol,
        "interval": result.interval,
        "start_at": result.start_at,
        "end_at": result.end_at,
        "candles_processed": result.candles_processed,
        "metrics": result.metrics.__dict__,
        "final_snapshot": result.final_snapshot.__dict__,
        "trade_count": len(result.trades),
        "equity_curve_points": len(result.equity_curve),
    }


@app.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    """Redirect to the Bitcoin market page."""
    return RedirectResponse(url="/bitcoin", status_code=307)


@app.get("/bitcoin", response_class=HTMLResponse)
def bitcoin_page() -> str:
    """Render the Bitcoin market dashboard."""
    config = load_config()
    state = load_dashboard_state(config)
    ingestion = state["ingestion_state"] or {}
    latest_cycle = state["latest_cycle"] or {}
    portfolio = (state["portfolio_snapshot"] or {}).get("snapshot", {})
    portfolio_metrics = _portfolio_metrics(portfolio, config.execution.initial_cash_usd)
    btc_summary = _btc_window_summary(state["recent_candles"])
    indicators = latest_cycle.get("indicator_snapshot", {})
    freshness_label, freshness_class = _data_freshness(ingestion.get("last_ingested_timestamp"))
    confidence_score, confidence_label = _confidence_snapshot(indicators, str(latest_cycle.get("regime", "")))
    spread, trend_label = _trend_strength(indicators)
    volatility = _volatility_label(float(indicators.get("atr", 0.0)), float(indicators.get("last_price", 0.0)))
    latest_ingested_label = _format_display_timestamp(ingestion.get("last_ingested_timestamp"))
    avg_volume = float(btc_summary["avg_volume"])
    pnl_percent = 0.0 if config.execution.initial_cash_usd == 0 else (
        portfolio_metrics["total_pnl"] / config.execution.initial_cash_usd
    ) * 100
    pnl_class = "value-positive" if portfolio_metrics["total_pnl"] >= 0 else "value-negative"
    position_state = "LONG" if portfolio_metrics["btc_units"] > 0 else "FLAT"

    candles_payload = json.dumps(state["chart_candles"])
    trades_payload = json.dumps(state["recent_trades"])
    avg_entry = float(portfolio.get("avg_entry_price", 0.0))

    body = f"""
    <section class="status-strip">
      <div class="status-chip"><div class="label">System Status</div><div class="status-value">ACTIVE (Paper Trading)</div></div>
      <div class="status-chip"><div class="label">Current Regime</div><div class="status-value">{escape(str(latest_cycle.get('regime', 'n/a')).upper())}</div></div>
      <div class="status-chip"><div class="label">Confidence</div><div class="status-value">{confidence_score:.2f} ({escape(confidence_label)})</div></div>
      <div class="status-chip"><div class="label">Freshness</div><div class="status-value"><span class="pill {freshness_class}">{escape(freshness_label)}</span></div></div>
      <div class="status-chip"><div class="label">Latest Candle</div><div class="status-value">{escape(latest_ingested_label)}</div></div>
    </section>
    <section class="btc-layout">
      <div class="btc-main">
        <section class="panel market-card">
          <div class="market-top">
            <div>
              <div class="market-title">Market Context</div>
              <div class="market-sub">Deeper history from the local parquet lake, rendered for readability instead of raw debug output.</div>
            </div>
          </div>
          <div class="market-price-row">
            <div>
              <div class="market-price">${btc_summary["price"]:,.2f}</div>
              <div class="market-change" style="color:{'#9cf7b7' if float(btc_summary['change_percent']) >= 0 else '#fecaca'};">{btc_summary['change_percent']:+.2f}% vs loaded window</div>
            </div>
            <div class="hero-row">
              <span class="pill neutral">Trend {escape(str(latest_cycle.get('regime', 'n/a')).upper())}</span>
              <span class="pill neutral">Volatility {escape(volatility)}</span>
            </div>
          </div>
          <div class="market-stats">
            <div class="market-stat"><div class="metric-label">Range High</div><div class="metric-value">${btc_summary["window_high"]:,.2f}</div></div>
            <div class="market-stat"><div class="metric-label">Range Low</div><div class="metric-value">${btc_summary["window_low"]:,.2f}</div></div>
            <div class="market-stat"><div class="metric-label">Avg Volume</div><div class="metric-value">{avg_volume:,.2f} BTC</div></div>
            <div class="market-stat"><div class="metric-label">EMA Spread</div><div class="metric-value">{spread:+.0f} ({escape(trend_label)})</div></div>
          </div>
        </section>
        <section class="panel chart-card">
          <div class="chart-panel-head">
            <div>
              <div class="chart-title">Interactive Chart</div>
            </div>
            <div id="chartNote" class="chart-note">Preset buttons are fast views. Dense ranges are auto-compressed so the chart stays readable. Source interval: 30m.</div>
          </div>
          <div class="chart-toolbar-grid" style="grid-template-columns:1.15fr 1fr;">
            <div class="toolbar-block">
              <div class="toolbar-label">View</div>
              <div class="segmented">
                <button type="button" class="seg-btn" data-chart-type="line">Line</button>
                <button type="button" class="seg-btn" data-chart-type="bar">OHLC</button>
                <button type="button" class="seg-btn" data-chart-type="candle">Candle</button>
              </div>
            </div>
            <div class="toolbar-block">
              <div class="toolbar-label">Range</div>
              <div class="segmented">
                <button type="button" class="seg-btn" data-range="60">1H</button>
                <button type="button" class="seg-btn" data-range="240">4H</button>
                <button type="button" class="seg-btn" data-range="480">8H</button>
                <button type="button" class="seg-btn" data-range="1440">1D</button>
                <button type="button" class="seg-btn" data-range="all">ALL</button>
              </div>
            </div>
          </div>
          <div class="filter-grid">
            <div class="field"><label>Start</label><input id="startTime" type="datetime-local" /></div>
            <div class="field"><label>End</label><input id="endTime" type="datetime-local" /></div>
            <div class="toolbar-block"><div class="toolbar-label">Actions</div><div class="filter-actions"><button id="applyFilters" type="button" class="seg-btn">Apply</button><button id="resetFilters" type="button" class="seg-btn">Reset</button></div></div>
          </div>
          <div id="filterStatus" class="status-line"></div>
          <div id="btcChart" class="chart-surface"></div>
          <div id="btcTooltip" style="display:none;"></div>
        </section>
      </div>
      <aside class="btc-side">
        <section class="side-card">
          <div class="label">Indicators</div>
          <div class="side-title">Current Signal Context</div>
          <div class="indicator-group">
            <div class="indicator-group-title">Momentum</div>
            <div class="indicator-grid">
              <div class="indicator-tile"><div class="metric-label">RSI</div><div class="metric-value">{float(indicators.get('rsi', 0.0)):.2f}</div></div>
              <div class="indicator-tile"><div class="metric-label">MACD</div><div class="metric-value">{float(indicators.get('macd', 0.0)):.4f}</div></div>
              <div class="indicator-tile"><div class="metric-label">Histogram</div><div class="metric-value">{float(indicators.get('macd_histogram', 0.0)):.4f}</div></div>
            </div>
          </div>
          <div class="indicator-group">
            <div class="indicator-group-title">Trend</div>
            <div class="indicator-grid">
              <div class="indicator-tile"><div class="metric-label">EMA Fast</div><div class="metric-value">{float(indicators.get('ema_fast', 0.0)):.2f}</div></div>
              <div class="indicator-tile"><div class="metric-label">EMA Slow</div><div class="metric-value">{float(indicators.get('ema_slow', 0.0)):.2f}</div></div>
              <div class="indicator-tile"><div class="metric-label">EMA Spread</div><div class="metric-value">{spread:+.0f}</div></div>
            </div>
          </div>
          <div class="indicator-group">
            <div class="indicator-group-title">Volatility</div>
            <div class="indicator-grid">
              <div class="indicator-tile"><div class="metric-label">ATR</div><div class="metric-value">{float(indicators.get('atr', 0.0)):.2f}</div></div>
            </div>
          </div>
        </section>
        <section class="side-card">
          <div class="label">Market Summary</div>
          <div class="side-title">Portfolio Snapshot</div>
          <div class="market-mini">
            <div class="mini-row"><span class="mini-label">Avg Entry</span><span class="mini-value">${avg_entry:,.2f}</span></div>
            <div class="mini-row"><span class="mini-label">Status</span><span class="mini-value">{position_state}</span></div>
            <div class="mini-row"><span class="mini-label">Position Size</span><span class="mini-value">{portfolio_metrics["btc_units"]:.6f} BTC</span></div>
            <div class="mini-row"><span class="mini-label">PnL</span><span class="mini-value {pnl_class}">${portfolio_metrics["total_pnl"]:+,.2f} ({pnl_percent:+.2f}%)</span></div>
          </div>
        </section>
      </aside>
    </section>
    <script id="candles-data" type="application/json">{candles_payload}</script>
    <script id="trades-data" type="application/json">{trades_payload}</script>
    """

    script = f"""
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <script>
      const candleSets = JSON.parse(document.getElementById("candles-data").textContent);
      const chartEl = document.getElementById("btcChart");
      const chartNote = document.getElementById("chartNote");
      const startTime = document.getElementById("startTime");
      const endTime = document.getElementById("endTime");
      const applyFilters = document.getElementById("applyFilters");
      const resetFilters = document.getElementById("resetFilters");
      const filterStatus = document.getElementById("filterStatus");
      const rangeButtons = [...document.querySelectorAll("[data-range]")];
      const typeButtons = [...document.querySelectorAll("[data-chart-type]")];
      let activeRange = "1440";
      let activeType = "line";

      function sourceIntervalForRange(range) {{
        if (range === "60") return "1m";
        if (range === "240" || range === "480") return "10m";
        if (range === "1440") return "30m";
        if (range === "all") return "1d";
        return "1m";
      }}

      function currentCandles() {{
        const interval = sourceIntervalForRange(activeRange);
        return candleSets[interval] || candleSets["1m"] || [];
      }}

      function candlesToShowForRange(range) {{
        if (range === "60") return 60;      // 1H from 1m
        if (range === "240") return 24;     // 4H from 10m
        if (range === "480") return 48;     // 8H from 10m
        if (range === "1440") return 48;    // 1D from 30m
        return null;                        // ALL
      }}

      function updateIntervalUi() {{
        const interval = sourceIntervalForRange(activeRange);
        const labelMap = {{
          "1m": "1m",
          "10m": "10m",
          "30m": "30m",
          "1d": "1d",
        }};
        const intervalLabel = labelMap[interval] || interval;
        if (chartNote) {{
          chartNote.textContent = `Preset buttons are fast views. Dense ranges are auto-compressed so the chart stays readable. Source interval: ${{intervalLabel}}.`;
        }}
      }}

      function isoToLocalInput(iso) {{
        if (!iso) return "";
        const d = new Date(iso);
        const p = (n) => String(n).padStart(2, "0");
        return `${{d.getFullYear()}}-${{p(d.getMonth()+1)}}-${{p(d.getDate())}}T${{p(d.getHours())}}:${{p(d.getMinutes())}}`;
      }}

      function toLocalComparable(iso) {{
        return isoToLocalInput(iso);
      }}

      function setChartMessage(message) {{
        if (window.Plotly) {{
          Plotly.purge(chartEl);
        }}
        chartEl.innerHTML = `<div style="padding:2rem;color:#dbe7f6;">${{message}}</div>`;
      }}

      function filteredCandles() {{
        const candles = currentCandles();
        const startValue = startTime.value || "";
        const endValue = endTime.value || "";
        const hasManualWindow = Boolean(startValue || endValue);
        let subset = [...candles];
        const visibleCount = candlesToShowForRange(activeRange);
        if (!hasManualWindow && visibleCount) subset = subset.slice(-visibleCount);
        if (startValue) {{
          subset = subset.filter(c => toLocalComparable(c.timestamp) >= startValue);
        }}
        if (endValue) {{
          subset = subset.filter(c => toLocalComparable(c.timestamp) <= endValue);
        }}
        return subset;
      }}

      function formatXAxis(value) {{
        const d = new Date(value);
        return d.toLocaleString(undefined, {{ month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }});
      }}

      function formatTooltipTimestamp(value) {{
        const d = new Date(value);
        return d.toLocaleString(undefined, {{
          month: "short",
          day: "numeric",
          hour: "numeric",
          minute: "2-digit",
          hour12: true,
        }});
      }}

      function formatCurrency(value) {{
        return new Intl.NumberFormat(undefined, {{
          style: "currency",
          currency: "USD",
          maximumFractionDigits: 2,
        }}).format(Number(value));
      }}

      function renderChart(data) {{
        if (!window.Plotly) {{
          throw new Error("Plotly failed to load.");
        }}
        const closes = data.map(point => Number(point.close));
        const highs = data.map(point => Number(point.high ?? point.close));
        const lows = data.map(point => Number(point.low ?? point.close));
        const minPrice = Math.min(...lows);
        const maxPrice = Math.max(...highs);
        const spread = maxPrice - minPrice;
        const padding = spread === 0 ? Math.max(minPrice * 0.02, 1) : spread * 0.02;
        const yDomain = [minPrice - padding, maxPrice + padding];
        const x = data.map(point => point.timestamp);
        const latestClose = Number(data[data.length - 1].close);
        let traces = [];

        if (activeType === "bar") {{
          traces = [{{
            type: "ohlc",
            x,
            open: data.map(point => Number(point.open)),
            high: highs,
            low: lows,
            close: closes,
            increasing: {{ line: {{ color: "#16c784", width: 1.5 }} }},
            decreasing: {{ line: {{ color: "#ea3943", width: 1.5 }} }},
            line: {{ width: 1.2 }},
            hoverlabel: {{ namelength: 0 }},
            hovertemplate:
              "%{{x|%b %d, %-I:%M %p}}<br>" +
              "Open: %{{open:$,.2f}}<br>" +
              "High: %{{high:$,.2f}}<br>" +
              "Low: %{{low:$,.2f}}<br>" +
              "Close: %{{close:$,.2f}}<extra></extra>",
          }}];
        }} else if (activeType === "candle") {{
          traces = [{{
            type: "candlestick",
            x,
            open: data.map(point => Number(point.open)),
            high: highs,
            low: lows,
            close: closes,
            increasing: {{ line: {{ color: "#16c784", width: 1.2 }}, fillcolor: "#16c784" }},
            decreasing: {{ line: {{ color: "#ea3943", width: 1.2 }}, fillcolor: "#ea3943" }},
            whiskerwidth: 0.5,
            hoverlabel: {{ namelength: 0 }},
            hovertemplate:
              "%{{x|%b %d, %-I:%M %p}}<br>" +
              "Open: %{{open:$,.2f}}<br>" +
              "High: %{{high:$,.2f}}<br>" +
              "Low: %{{low:$,.2f}}<br>" +
              "Close: %{{close:$,.2f}}<extra></extra>",
          }}];
        }} else {{
          traces = [{{
            type: "scatter",
            mode: "lines+markers",
            x,
            y: closes,
            line: {{ color: "#f59e0b", width: 3, shape: "spline", smoothing: 0.55 }},
            marker: {{ size: 2, color: "#f59e0b", opacity: 0 }},
            fill: "tozeroy",
            fillcolor: "rgba(245,158,11,0.10)",
            hoverinfo: "skip",
            hovertemplate: "%{{x|%b %d, %-I:%M %p}}<br>%{{y:$,.2f}}<extra></extra>",
          }}];
        }}

        const layout = {{
          paper_bgcolor: "rgba(13,21,32,1)",
          plot_bgcolor: "rgba(13,21,32,1)",
          margin: {{ t: 24, r: 36, b: 44, l: 56, pad: 12 }},
          hovermode: "x",
          hoverdistance: 100,
          spikedistance: 100,
          showlegend: false,
          hoverlabel: {{
            bgcolor: "rgba(15,23,36,0.96)",
            bordercolor: "rgba(148,163,184,0.32)",
            font: {{ color: "#f8fafc", size: 12 }},
            align: "left",
          }},
          xaxis: {{
            type: "date",
            showgrid: false,
            zeroline: false,
            showline: false,
            tickfont: {{ color: "rgba(148,163,184,0.8)", size: 11 }},
            tickformat: "%b %-d\\n%Y",
            rangeslider: {{ visible: false }},
            automargin: true,
            showspikes: true,
            spikecolor: "rgba(255,255,255,0.25)",
            spikethickness: 1,
            spikedash: "dot",
            spikesnap: "cursor",
          }},
          yaxis: {{
            range: yDomain,
            showgrid: true,
            gridcolor: "rgba(255,255,255,0.06)",
            zeroline: false,
            tickfont: {{ color: "rgba(203,213,225,0.82)", size: 11 }},
            tickformat: "$,.0f",
            automargin: true,
            fixedrange: true,
          }},
          shapes: [{{
            type: "line",
            xref: "paper",
            x0: 0,
            x1: 1,
            y0: latestClose,
            y1: latestClose,
            line: {{ color: "rgba(245,158,11,0.40)", width: 1, dash: "dash" }},
          }}],
        }};

        Plotly.react(chartEl, traces, layout, {{
          responsive: true,
          displayModeBar: false,
          staticPlot: false,
          scrollZoom: false,
          doubleClick: false,
        }});
      }}

      function redraw() {{
        try {{
          updateIntervalUi();
          const subset = filteredCandles().map(candle => ({{
            timestamp: candle.timestamp,
            open: Number(candle.open),
            high: Number(candle.high),
            low: Number(candle.low),
            close: Number(candle.close),
          }}));
          if (!subset.length) {{
            filterStatus.textContent = `No candles in current selection (${{sourceIntervalForRange(activeRange)}} source)`;
            setChartMessage("No candles available for the selected filters.");
            return;
          }}

          const rangeLabelMap = {{
            "60": "Last 1H",
            "240": "Last 4H",
            "480": "Last 8H",
            "1440": "Last 1D",
            "all": "All Available",
          }};
          const startValue = startTime.value || "";
          const endValue = endTime.value || "";
          const hasManualWindow = Boolean(startValue || endValue);
          const label = hasManualWindow ? "Custom Range" : (rangeLabelMap[activeRange] || "Visible Range");
          filterStatus.textContent = `${{label}} (${{subset.length}} candles, ${{sourceIntervalForRange(activeRange)}} source)`;
          renderChart(subset);

          typeButtons.forEach(btn => {{
            btn.style.background = btn.dataset.chartType === activeType ? "#fff" : "#eef2f7";
            btn.style.color = btn.dataset.chartType === activeType ? "#132033" : "#667085";
          }});
          rangeButtons.forEach(btn => {{
            btn.style.background = btn.dataset.range === activeRange ? "#fff" : "#eef2f7";
            btn.style.color = btn.dataset.range === activeRange ? "#132033" : "#667085";
          }});
        }} catch (error) {{
          setChartMessage(`Chart unavailable: ${{error.message}}`);
          console.error(error);
        }}
      }}

      typeButtons.forEach(btn => btn.addEventListener("click", () => {{ activeType = btn.dataset.chartType; redraw(); }}));
      rangeButtons.forEach(btn => btn.addEventListener("click", () => {{
        activeRange = btn.dataset.range;
        startTime.value = "";
        endTime.value = "";
        redraw();
      }}));
      applyFilters.addEventListener("click", () => {{
        activeRange = "all";
        redraw();
      }});
      resetFilters.addEventListener("click", () => {{
        activeRange = "1440";
        startTime.value = "";
        endTime.value = "";
        redraw();
      }});
      window.addEventListener("resize", redraw);
      redraw();
    </script>
    """
    return _base_html("Bitcoin | Adaptive BTC Trading Agent", "bitcoin", body, script)


@app.get("/trades", response_class=HTMLResponse)
def trades_page(run_backtest: int = Query(default=0, ge=0, le=1)) -> str:
    """Render the trades and portfolio dashboard."""
    config = load_config()
    state = load_dashboard_state(config)
    latest_cycle = state["latest_cycle"] or {}
    latest_trace = state["latest_trace"] or {}
    snapshot = (state["portfolio_snapshot"] or {}).get("snapshot", {})
    portfolio = _portfolio_metrics(snapshot, config.execution.initial_cash_usd)
    decision = _decision_breakdown(latest_cycle, latest_trace)
    trades = list(reversed(state["recent_trades"]))
    recent_table = (
        "".join(_format_trade_row(trade) for trade in trades)
        if trades
        else "<tr><td class='empty' colspan='8'>No trades recorded yet.</td></tr>"
    )
    active_swings = list((state["broker_state"] or {}).get("open_swing_positions", []))
    swing_rows = (
        "".join(
            "<tr>"
            f"<td>{escape(_format_display_timestamp(str(position.get('opened_at', ''))))}</td>"
            f"<td>${float(position.get('entry_price', 0)):.2f}</td>"
            f"<td>${float(position.get('stop_loss', 0)):.2f}</td>"
            f"<td>{float(position.get('btc_units', 0)):.6f} BTC</td>"
            "</tr>"
            for position in active_swings
        )
        if active_swings
        else "<tr><td class='empty' colspan='4'>No active swing positions.</td></tr>"
    )
    latest_trade = state["latest_trade"]
    pnl_class = "value-positive" if portfolio["total_pnl"] >= 0 else "value-negative"
    backtest_summary = ""
    if run_backtest:
        try:
            backtest = BacktestEngine(config).run(symbol=config.trading.symbol, interval=config.ingestion.interval)
            metrics = backtest.metrics
            backtest_summary = f"""
            <section class="panel">
              <div class="label">Backtest Summary</div>
              <div class="value">Historical Replay ({escape(backtest.interval)})</div>
              <div class="subgrid" style="margin-top:.8rem;">
                <div class="metric light"><div class="metric-label">Total Return</div><div class="metric-value">{metrics.total_return_percent:+.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Buy & Hold</div><div class="metric-value">{metrics.buy_and_hold_return_percent:+.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Max Drawdown</div><div class="metric-value">{metrics.max_drawdown_percent:.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Sharpe</div><div class="metric-value">{metrics.sharpe_ratio:.2f}</div></div>
                <div class="metric light"><div class="metric-label">Trades</div><div class="metric-value">{metrics.filled_trade_count}</div></div>
                <div class="metric light"><div class="metric-label">Swing Win Rate</div><div class="metric-value">{metrics.win_rate_percent:.2f}%</div></div>
              </div>
              <p style="margin-top:.8rem;">Window: {escape(_format_display_timestamp(backtest.start_at))} to {escape(_format_display_timestamp(backtest.end_at))}</p>
            </section>
            """
        except ValueError as exc:
            backtest_summary = f"""
            <section class="panel">
              <div class="label">Backtest Summary</div>
              <div class="value">Unavailable</div>
              <p>{escape(str(exc))}</p>
            </section>
            """

    mode_cards = f"""
      <div class="mode live">
        <div class="label">Paper Trading</div>
        <div class="value">Active</div>
        <div>Uses the persisted paper broker, trade ledger, and local parquet market data.</div>
      </div>
      <div class="mode">
        <div class="label">Backtesting</div>
        <div class="value">Available</div>
        <a class="ghost" href="/trades?run_backtest=1" style="text-decoration:none;">Run Backtest</a>
      </div>
      <div class="mode">
        <div class="label">Simulation</div>
        <div class="value">Coming Soon</div>
        <button class="ghost" disabled>Run Simulation</button>
      </div>
    """
    latest_trade_summary = "No trades recorded yet."
    latest_trade_timestamp = ""
    if latest_trade:
        latest_trade_time = _format_display_timestamp(str(latest_trade.get("timestamp", "")))
        latest_trade_timestamp = latest_trade_time
        latest_trade_summary = (
            f"{str(latest_trade.get('side', '')).upper()} "
            f"${float(latest_trade.get('size_usd', 0)):.2f} @ ${float(latest_trade.get('price', 0)):.2f}"
        )

    body = f"""
    <section class="banner">
      <div class="panel"><div class="label">Portfolio Equity</div><div class="value">${portfolio["equity"]:.2f}</div></div>
      <div class="panel"><div class="label">Total PnL</div><div class="value {pnl_class}">${portfolio["total_pnl"]:+.2f}</div></div>
      <div class="panel"><div class="label">BTC Allocation</div><div class="value">{portfolio["exposure_percent"]:.2f}%</div></div>
      <div class="panel"><div class="label">Active Strategy</div><div class="value">{escape(str(latest_cycle.get('strategy_name', 'n/a')).replace('Strategy', ''))}</div></div>
      <div class="panel"><div class="label">Latest Trade</div><div class="value">{escape(latest_trade_summary)}</div><div class="label" style="margin-top:.35rem;">{escape(latest_trade_timestamp)}</div></div>
    </section>
    <section class="page-grid">
      <div class="stack">
        <section class="panel">
          <div class="label">Portfolio State</div>
          <div class="value">Current Holdings</div>
          <div class="subgrid">
            <div class="metric light"><div class="metric-label">Cash</div><div class="metric-value">${portfolio["cash"]:.2f} USD</div></div>
            <div class="metric light"><div class="metric-label">BTC Held</div><div class="metric-value">{portfolio["btc_units"]:.6f} BTC</div></div>
            <div class="metric light"><div class="metric-label">DCA BTC</div><div class="metric-value">{portfolio["dca_btc_units"]:.6f} BTC</div></div>
            <div class="metric light"><div class="metric-label">Swing BTC</div><div class="metric-value">{portfolio["swing_btc_units"]:.6f} BTC</div></div>
            <div class="metric light"><div class="metric-label">Avg Entry</div><div class="metric-value">${portfolio["avg_entry"]:.2f}</div></div>
            <div class="metric light"><div class="metric-label">Last Mark</div><div class="metric-value">${portfolio["last_mark"]:.2f}</div></div>
            <div class="metric light"><div class="metric-label">Unrealized PnL</div><div class="metric-value">${portfolio["unrealized_pnl"]:+.2f} USD</div></div>
            <div class="metric light"><div class="metric-label">Realized PnL</div><div class="metric-value">${portfolio["realized_pnl"]:+.2f} USD</div></div>
          </div>
        </section>
        <section class="panel decision-card">
          <div class="label">Decision Breakdown</div>
          <div class="value">{escape(str(decision["headline"]))}</div>
          <ul class="decision-list">
            {''.join(f"<li>{escape(str(line))}</li>" for line in decision["reason_lines"])}
          </ul>
          <p><strong>Interpretation:</strong> {escape(str(decision["interpretation"]))}</p>
        </section>
        {backtest_summary}
        <section class="panel">
          <div class="label">Executed Buys and Sells</div>
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Side</th>
                <th>Symbol</th>
                <th>USD</th>
                <th>Price</th>
                <th>BTC</th>
                <th>Strategy</th>
                <th>Signal Type</th>
              </tr>
            </thead>
            <tbody>{recent_table}</tbody>
          </table>
        </section>
      </div>
      <aside class="stack">
        <section class="panel"><div class="label">Execution Modes</div><div class="stack" style="margin-top:.8rem;">{mode_cards}</div></section>
        <section class="panel">
          <div class="label">Active Swing Positions</div>
          <table>
            <thead>
              <tr><th>Opened</th><th>Entry</th><th>Stop</th><th>BTC</th></tr>
            </thead>
            <tbody>{swing_rows}</tbody>
          </table>
        </section>
        <section class="panel">
          <div class="label">System Mode</div>
          <div class="value">Paper Trading</div>
          <p>The trade engine now separates base DCA holdings from opportunistic swing positions so ATR stop-loss exits can close swing trades without touching base accumulation.</p>
        </section>
      </aside>
    </section>
    """
    return _base_html("Trades | Adaptive BTC Trading Agent", "trades", body)
