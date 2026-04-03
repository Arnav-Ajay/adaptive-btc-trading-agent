"""FastAPI dashboard and JSON API for the current trading system state."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from html import escape
from statistics import mean

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.backtest.engine import BacktestEngine
from app.backtest.history import save_backtest_result
from app.api.state_reader import load_dashboard_state
from app.data.parquet_market_data import ParquetMarketDataClient
from app.config.settings import load_config
from app.simulation.engine import SimulationEngine
from app.simulation.history import save_simulation_result

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
          table {{ width:100%; border-collapse:collapse; margin-top:.9rem; }} th,td {{ text-align:left; padding:.75rem .65rem; border-bottom:1px solid #e5e7eb; font-size:.92rem; }} th {{ color:#667085; font-weight:700; }} .empty {{ color:#667085; }} .decision-row {{ cursor:pointer; }} .decision-row:hover {{ background:#f8fafc; }} .decision-row-active {{ background:#eef4ff; }} .decision-row-hidden {{ display:none; }}
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
          .seg-btn.active {{ background:#fff; color:#132033; border-color:#b9c6d8; box-shadow:0 6px 14px rgba(16,24,40,.08); }}
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
          .trade-page {{ display:grid; gap:1rem; }}
          .trade-hero {{ padding:0; overflow:hidden; background:linear-gradient(145deg,#0f1724 0%,#16263a 58%,#224766 100%); color:#f5f9ff; border:none; }}
          .trade-hero-top {{ display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; padding:1.2rem 1.25rem 0; }}
          .trade-hero-title {{ font-size:1.7rem; font-weight:800; letter-spacing:-.02em; }}
          .trade-hero-sub {{ color:rgba(229,236,246,.74); margin-top:.22rem; max-width:760px; font-size:.93rem; }}
          .trade-hero .label {{ color:rgba(226,236,249,.72); }}
          .trade-mode-pills {{ display:flex; gap:.55rem; flex-wrap:wrap; }}
          .trade-mode-pill {{ display:inline-flex; align-items:center; justify-content:center; padding:.55rem .9rem; min-width:108px; border-radius:999px; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.10); color:#f5f9ff; font-size:.8rem; font-weight:700; text-decoration:none; }}
          .trade-mode-pill.active {{ background:#fff; color:#132033; border-color:#fff; }}
          .trade-banner {{ display:grid; grid-template-columns:repeat(6,1fr); gap:.8rem; padding:1rem 1.25rem 1.2rem; }}
          .trade-banner-card {{ padding:.9rem .95rem; border-radius:16px; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.09); }}
          .trade-banner-card .metric-label {{ color:rgba(229,236,246,.72); font-size:.76rem; text-transform:uppercase; letter-spacing:.05em; }}
          .trade-banner-card .metric-value {{ margin-top:.28rem; font-weight:800; font-size:1.08rem; }}
          .trade-layout {{ display:grid; grid-template-columns:minmax(0,1.45fr) 340px; gap:1rem; }}
          .trade-main,.trade-side {{ display:grid; gap:1rem; }}
          .trade-section {{ padding:1.05rem; background:#fff; border:1px solid #d9e1ea; border-radius:20px; box-shadow:0 16px 34px rgba(16,24,40,.06); }}
          .trade-section-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:1rem; margin-bottom:.85rem; }}
          .trade-section-title {{ font-size:1.22rem; font-weight:800; letter-spacing:-.02em; }}
          .trade-section-note {{ color:#667085; font-size:.9rem; max-width:720px; }}
          .trade-split {{ display:grid; grid-template-columns:1.1fr .9fr; gap:1rem; }}
          .trade-card-soft {{ background:#f8fafc; border:1px solid #e4e8ef; border-radius:18px; padding:1rem; }}
          .trade-chart-card {{ padding:1rem; background:linear-gradient(180deg,#fff 0%,#f8fbff 100%); }}
          .trade-chart-frame {{ padding:.55rem; background:linear-gradient(180deg,#0d1520 0%,#13233b 100%); border-radius:24px; }}
          .trade-chart-frame .chart-surface {{ border-radius:18px; }}
          .trade-table-wrap {{ overflow:auto; }}
          .trade-note-strip {{ display:flex; gap:.55rem; flex-wrap:wrap; margin-top:.65rem; }}
          .trade-note-pill {{ display:inline-flex; align-items:center; padding:.38rem .7rem; border-radius:999px; background:#eef2f7; color:#475467; font-size:.8rem; font-weight:700; }}
          .trade-side .panel,.trade-side .trade-section {{ box-shadow:0 16px 34px rgba(16,24,40,.06); }}
          .simulation-card {{ min-height:260px; display:grid; align-content:start; gap:.75rem; background:linear-gradient(180deg,#fff 0%,#f8fbff 100%); }}
          .simulation-card .value {{ font-size:1.5rem; }}
          .history-stack {{ display:grid; gap:.55rem; margin-top:.8rem; }}
          .history-link {{ display:grid; gap:.18rem; padding:.75rem .85rem; border-radius:16px; border:1px solid #d9e1ea; background:#f8fafc; color:#475467; text-decoration:none; }}
          .history-link.active {{ background:#fff; border-color:#b9c6d8; box-shadow:0 10px 20px rgba(16,24,40,.08); color:#132033; }}
          .history-link-meta {{ color:#667085; font-size:.76rem; text-transform:uppercase; letter-spacing:.05em; }}
          .history-link-main {{ font-weight:800; font-size:1rem; }}
          .history-link-sub {{ color:#667085; font-size:.86rem; }}
          @media (max-width:1050px) {{ .banner,.page-grid,.subgrid,.status-strip,.btc-layout,.market-stats,.chart-toolbar-grid,.filter-grid,.trade-layout,.trade-banner,.trade-split {{ grid-template-columns:1fr; }} .footer {{ flex-direction:column; align-items:flex-start; }} .market-price-row,.market-top,.trade-hero-top {{ flex-direction:column; align-items:flex-start; }} }}
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
    realized = float(snapshot.get("realized_pnl_usd", 0.0))
    total_fees = float(snapshot.get("total_fees_usd", 0.0))
    total_spread = float(snapshot.get("total_spread_cost_usd", 0.0))
    total_slippage = float(snapshot.get("total_slippage_cost_usd", 0.0))
    unrealized = ((last_mark - avg_entry) * btc_units) if btc_units > 0 and avg_entry > 0 else 0.0
    total_pnl = realized + unrealized
    exposure = 0.0 if equity <= 0 else ((btc_units * last_mark) / equity) * 100
    return {
        "cash": cash, "btc_units": btc_units, "equity": equity, "avg_entry": avg_entry, "last_mark": last_mark,
        "total_pnl": total_pnl, "unrealized_pnl": unrealized, "realized_pnl": realized, "exposure_percent": exposure,
        "dca_btc_units": float(snapshot.get("dca_btc_units", 0.0)), "swing_btc_units": float(snapshot.get("swing_btc_units", 0.0)),
        "total_fees_usd": total_fees,
        "total_spread_cost_usd": total_spread,
        "total_slippage_cost_usd": total_slippage,
        "total_execution_cost_usd": total_fees + total_spread + total_slippage,
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
        return {
            "headline": "No decision recorded",
            "decision": "No data",
            "reason_lines": ["The trading loop has not recorded a cycle yet."],
            "interpretation": "Run the trading loop to produce the first decision record.",
            "timestamp": "",
        }
    trace = list(latest_trace.get("decision_trace", [])) if latest_trace else []
    executions = latest_cycle.get("execution_results", [])
    accepted_executions = [item for item in executions if item.get("accepted")]
    signal_count = int(latest_cycle.get("signal_count", 0))
    has_buy_execution = any(str(item.get("side", "")).lower() == "buy" for item in accepted_executions)
    has_sell_execution = any(str(item.get("side", "")).lower() == "sell" for item in accepted_executions)
    if accepted_executions and not has_buy_execution and not has_sell_execution:
        has_sell_execution = any(
            str(item.get("reason", "")).startswith(("stop_loss_hit:", "swing_take_profit:", "swing_signal_exit:"))
            for item in accepted_executions
        )
        has_buy_execution = not has_sell_execution
    decision = "SELL" if has_sell_execution else "BUY" if has_buy_execution else ("WATCH" if signal_count > 0 else "NO BUY")
    recorded_at = str(latest_cycle.get("recorded_at", ""))
    indicator_snapshot = latest_cycle.get("indicator_snapshot", {}) if latest_cycle else {}

    def _trace_value(prefix: str) -> str:
        for item in trace:
            if item.startswith(prefix):
                return item[len(prefix) :]
        return ""

    def _dca_skip_lines() -> list[str]:
        latest_buy_fill = next(
            (item for item in trace if "latest_buy_fill_price=" in item),
            "",
        )
        threshold = next((item for item in trace if item.startswith("threshold:")), "").replace("threshold:required_price_at_or_below=", "Required <= $")
        observed = next((item for item in trace if item.startswith("observed:")), "").replace("observed:last_price=", "Current price = $")
        threshold_value = next((item for item in trace if item.startswith("threshold:")), "").replace("threshold:required_price_at_or_below=", "")
        latest_buy_value = latest_buy_fill.split("latest_buy_fill_price=", 1)[1] if latest_buy_fill else ""
        reason_lines = ["Price is above the configured DCA threshold."]
        try:
            threshold_float = float(threshold_value)
            latest_buy_float = float(latest_buy_value)
            drop_percent = (1 - (threshold_float / latest_buy_float)) * 100
            reason_lines.append(
                f"Threshold is based on the last buy at ${latest_buy_float:.2f} with a {drop_percent:.2f}% drop trigger."
            )
        except (ValueError, ZeroDivisionError):
            pass
        reason_lines.extend([threshold, observed])
        return [line for line in reason_lines if line]

    def _swing_check_lines() -> list[str]:
        return [
            item.replace("check:", "").replace(" actual=", " = ").replace(" fast=", " | fast=").replace(" slow=", " slow=")
            for item in trace
            if item.startswith("check:")
        ]

    if accepted_executions:
        latest_execution = accepted_executions[-1]
        strategy_name = str(latest_execution.get("strategy_name") or latest_cycle.get("strategy_name", "")).replace("Strategy", "")
        reason = str(latest_execution.get("reason", ""))
        if reason in {"", "filled"}:
            if any("signal:initial_dca_entry" in item for item in trace):
                reason = "initial_dca_entry"
            elif any("signal:price_drop_dca_entry" in item for item in trace):
                reason = "price_drop_dca_entry"
            elif any("signal:momentum_atr_setup" in item for item in trace):
                reason = "momentum_atr_setup"
        price = float(latest_execution.get("price") or indicator_snapshot.get("last_price", 0.0))
        size_usd = float(latest_execution.get("size_usd", 0.0))
        if size_usd == 0.0:
            if reason == "momentum_atr_setup":
                signal_value = _trace_value("signal:momentum_atr_setup size_usd=")
                size_usd = float(signal_value or 0.0)
            elif reason in {"initial_dca_entry", "price_drop_dca_entry", "dca_drop_buy"}:
                prefix = "signal:initial_dca_entry size_usd=" if reason == "initial_dca_entry" else "signal:price_drop_dca_entry size_usd="
                signal_value = _trace_value(prefix)
                size_usd = float(signal_value or 0.0)
        stop_loss = latest_execution.get("stop_loss")
        if stop_loss is None and reason == "momentum_atr_setup":
            stop_loss_value = _trace_value("decision:momentum_conditions_met stop_loss=")
            stop_loss = float(stop_loss_value) if stop_loss_value else None
        if reason == "momentum_atr_setup":
            metric_checks = [
                item.replace("check:", "").replace(" actual=", " = ").replace(" fast=", " | fast=").replace(" slow=", " slow=")
                for item in trace
                if item.startswith("check:")
            ]
            reason_lines = [
                "Swing momentum conditions were met under the hybrid strategy.",
                *metric_checks,
                f"Entry executed at ${price:.2f} for ${size_usd:.2f}.",
            ]
            if stop_loss is not None:
                reason_lines.append(f"ATR stop-loss set at ${float(stop_loss):.2f}.")
            return {
                "headline": f"Decision: {decision}",
                "decision": decision,
                "reason_lines": reason_lines,
                "interpretation": "The swing layer inside the hybrid strategy found a valid momentum setup and opened a tracked swing position.",
                "timestamp": recorded_at,
            }
        if reason.startswith("stop_loss_hit:"):
            return {
                "headline": f"Decision: {decision}",
                "decision": decision,
                "reason_lines": [
                    "The tracked swing stop-loss was breached.",
                    f"Exit executed at ${price:.2f} for ${size_usd:.2f}.",
                    f"Protected stop level was ${float(stop_loss or 0.0):.2f}.",
                ],
                "interpretation": "The swing position was closed defensively because price moved through the configured ATR stop-loss.",
                "timestamp": recorded_at,
            }
        if reason.startswith("swing_take_profit:"):
            return {
                "headline": f"Decision: {decision}",
                "decision": decision,
                "reason_lines": [
                    "The swing take-profit target was reached.",
                    f"Exit executed at ${price:.2f} for ${size_usd:.2f}.",
                ],
                "interpretation": "The swing layer locked in gains after price reached the configured take-profit level.",
                "timestamp": recorded_at,
            }
        if reason.startswith("swing_signal_exit:"):
            exit_checks = _swing_check_lines()
            return {
                "headline": f"Decision: {decision}",
                "decision": decision,
                "reason_lines": [
                    "Swing exit conditions were triggered as momentum weakened.",
                    *exit_checks,
                    f"Exit executed at ${price:.2f} for ${size_usd:.2f}.",
                ],
                "interpretation": "The swing layer closed the position because the trend/momentum filters no longer supported staying in the trade.",
                "timestamp": recorded_at,
            }
        if reason.startswith("swing_no_follow_through:"):
            return {
                "headline": f"Decision: {decision}",
                "decision": decision,
                "reason_lines": [
                    "The swing entry did not get enough positive follow-through after entry.",
                    f"Exit executed at ${price:.2f} for ${size_usd:.2f}.",
                ],
                "interpretation": "The swing layer cut the trade early because momentum failed to follow through after the initial entry.",
                "timestamp": recorded_at,
            }
        if reason in {"initial_dca_entry", "price_drop_dca_entry", "dca_drop_buy"}:
            if reason == "initial_dca_entry":
                return {
                    "headline": f"Decision: {decision}",
                    "decision": decision,
                    "reason_lines": [
                        "No prior DCA buy fill existed in the ledger.",
                        f"DCA order size was ${size_usd:.2f}.",
                        f"Entry executed at ${price:.2f} for ${size_usd:.2f}.",
                    ],
                    "interpretation": "This is the first accumulation buy for the paper portfolio.",
                    "timestamp": recorded_at,
                }
            threshold_lines = _dca_skip_lines()
            return {
                "headline": f"Decision: {decision}",
                "decision": decision,
                "reason_lines": [
                    "Current price crossed below the configured DCA threshold.",
                    *threshold_lines[1:3],
                    f"Entry executed at ${price:.2f} for ${size_usd:.2f}.",
                ],
                "interpretation": "The DCA layer added to the long-term BTC position after the drop threshold was reached.",
                "timestamp": recorded_at,
            }
    if "component:DCAStrategy" in trace and "component:SwingATRStrategy" in trace and not accepted_executions:
        reason_lines = [
            "DCA component:",
            *_dca_skip_lines(),
            "Swing component:",
            *_swing_check_lines(),
        ]
        if any("momentum_conditions_not_met" in item for item in trace):
            reason_lines.append("Swing setup did not meet all momentum entry conditions.")
        return {
            "headline": f"Decision: {decision}",
            "decision": decision,
            "reason_lines": reason_lines,
            "interpretation": "The hybrid strategy evaluated both DCA and swing components, but neither produced an executable trade.",
            "timestamp": recorded_at,
        }
    if any("price_above_drop_threshold" in item for item in trace):
        return {
            "headline": f"Decision: {decision}",
            "decision": decision,
            "reason_lines": _dca_skip_lines(),
            "interpretation": "Market is not favorable for accumulation yet, so the DCA layer is waiting for a deeper dip.",
            "timestamp": recorded_at,
        }
    if any("momentum_conditions_not_met" in item for item in trace):
        checks = [item.replace("check:", "").replace(" actual=", " = ").replace(" fast=", " | fast=").replace(" slow=", " slow=") for item in trace if item.startswith("check:")]
        return {
            "headline": f"Decision: {decision}",
            "decision": decision,
            "reason_lines": checks,
            "interpretation": "Trend exists, but the swing entry filters are not aligned strongly enough to justify a trade.",
            "timestamp": recorded_at,
        }
    if any("initial_dca_entry" in item for item in trace):
        return {
            "headline": f"Decision: {decision}",
            "decision": decision,
            "reason_lines": [
                "No prior DCA buy fill existed in the ledger.",
                f"DCA order size was ${float(_trace_value('signal:initial_dca_entry size_usd=') or 0.0):.2f}.",
                "The DCA base layer opened the initial BTC position.",
            ],
            "interpretation": "This is the first accumulation buy for the paper portfolio.",
            "timestamp": recorded_at,
        }
    return {
        "headline": f"Decision: {decision}",
        "decision": decision,
        "reason_lines": trace or ["No detailed decision trace recorded."],
        "interpretation": "The system evaluated the current market state and kept the portfolio unchanged.",
        "timestamp": recorded_at,
    }


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


def _format_trade_row(trade: dict[str, object], first_dca_buy_timestamp: str | None = None) -> str:
    """Render one trade table row."""
    strategy = str(trade.get("strategy_name", "") or "DCAStrategy")
    reason = str(trade.get("reason", "") or "")
    is_first_dca_buy = (
        strategy == "DCAStrategy"
        and str(trade.get("side", "")).lower() == "buy"
        and first_dca_buy_timestamp is not None
        and str(trade.get("timestamp", "")) == first_dca_buy_timestamp
    )
    if reason == "initial_dca_entry" or is_first_dca_buy:
        signal_type = "Initial Buy"
    elif strategy == "DCAStrategy":
        signal_type = "Dip Buy"
    else:
        signal_type = "Momentum"
    side = escape(str(trade.get("side", "")).upper())
    strategy_label = escape(strategy.replace("Strategy", ""))
    execution_cost_usd = float(
        trade.get(
            "execution_cost_usd",
            float(trade.get("fee_usd", 0.0) or 0.0)
            + float(trade.get("spread_cost_usd", 0.0) or 0.0)
            + float(trade.get("slippage_cost_usd", 0.0) or 0.0),
        )
        or 0.0
    )
    return (
        "<tr>"
        f"<td>{escape(_format_display_timestamp(str(trade.get('timestamp', ''))))}</td>"
        f"<td>{side}</td>"
        f"<td>{escape(str(trade.get('symbol', '')))}</td>"
        f"<td>${float(trade.get('size_usd', 0)):.2f} USD</td>"
        f"<td>${float(trade.get('price', 0)):.2f}</td>"
        f"<td>{float(trade.get('btc_units', 0)):.6f} BTC</td>"
        f"<td>${execution_cost_usd:.2f}</td>"
        f"<td>{strategy_label}</td>"
        f"<td>{escape(signal_type)}</td>"
        "</tr>"
    )


def _format_decision_row(cycle: dict[str, object], breakdown: dict[str, object], hidden: bool = False) -> str:
    """Render one decision-log table row."""
    execution_results = cycle.get("execution_results", [])
    execution_count = sum(1 for result in execution_results if result.get("accepted"))
    strategy_name = str(cycle.get("strategy_name", "")).replace("Strategy", "")
    row_classes = ["decision-row"]
    if hidden:
        row_classes.append("decision-row-hidden")
    payload = escape(
        json.dumps(
            {
                "headline": str(breakdown["headline"]),
                "decision": str(breakdown["decision"]),
                "reason_lines": [str(line) for line in breakdown["reason_lines"]],
                "interpretation": str(breakdown["interpretation"]),
                "timestamp": _format_display_timestamp(str(breakdown.get("timestamp", ""))),
            }
        )
    )
    return (
        f"<tr class=\"{' '.join(row_classes)}\" data-breakdown=\"{payload}\">"
        f"<td>{escape(_format_display_timestamp(str(cycle.get('recorded_at', ''))))}</td>"
        f"<td>{escape(str(cycle.get('regime', '')).upper())}</td>"
        f"<td>{escape(strategy_name)}</td>"
        f"<td class=\"decision-cell\">{escape(str(breakdown['decision']))}</td>"
        f"<td>{int(cycle.get('signal_count', 0))}</td>"
        f"<td>{execution_count}</td>"
        f"<td>{escape(str(breakdown['interpretation']))}</td>"
        "</tr>"
    )


def _backtest_step_breakdown(step: dict[str, object]) -> dict[str, object]:
    """Render a saved backtest step as a readable decision breakdown."""
    decision = str(step.get("decision", "n/a")).upper()
    trace = [str(line) for line in (step.get("trace") or [])]
    interpretation_map = {
        "BUY": "The replay engine found an executable entry and recorded a fill under the historical execution model.",
        "SELL": "The replay engine closed exposure during this step, usually from a stop-loss or explicit exit condition.",
        "HOLD": "Signals were evaluated in this step, but none were converted into an execution.",
        "NO BUY": "The replay engine evaluated the market state and kept the portfolio unchanged.",
        "HALT": "The replay engine stopped early because a risk guard was breached.",
    }
    return {
        "headline": f"Decision: {decision}",
        "decision": decision,
        "reason_lines": trace or ["No replay trace recorded for this step."],
        "interpretation": interpretation_map.get(
            decision,
            "The replay engine processed this step and preserved the current portfolio state.",
        ),
        "timestamp": _format_display_timestamp(str(step.get("timestamp", ""))),
    }


def _format_backtest_decision_row(step: dict[str, object], hidden: bool = False) -> str:
    """Render one replay-step row for the backtest decision log."""
    row_classes = ["backtest-decision-row"]
    if hidden:
        row_classes.append("decision-row-hidden")
    breakdown = _backtest_step_breakdown(step)
    payload = escape(json.dumps(breakdown))
    return (
        f"<tr class=\"{' '.join(row_classes)}\" data-breakdown=\"{payload}\">"
        f"<td>{escape(_format_display_timestamp(str(step.get('timestamp', ''))))}</td>"
        f"<td>{escape(str(step.get('regime', 'n/a')).upper())}</td>"
        f"<td>{escape(str(step.get('strategy_name', 'n/a')).replace('Strategy', ''))}</td>"
        f"<td class=\"decision-cell\">{escape(str(step.get('decision', 'n/a')).upper())}</td>"
        f"<td>{int(step.get('signal_count', 0))}</td>"
        f"<td>{int(step.get('execution_count', 0))}</td>"
        f"<td>${float(step.get('equity_usd', 0.0)):.2f}</td>"
        "</tr>"
    )


def _decision_matches_filter(decision_value: str, filter_value: str) -> bool:
    """Return whether a decision value should be shown for the active filter."""
    normalized_filter = filter_value.upper()
    normalized_decision = decision_value.upper()
    if normalized_filter == "ALL":
        return True
    return normalized_decision == normalized_filter

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
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_datetime:{value}") from exc
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _default_backtest_start(interval: str, end_at: datetime | None) -> datetime | None:
    """Choose a bounded default backtest window for UI/API calls."""
    if end_at is None:
        return None
    if interval == "1m":
        return end_at - timedelta(days=7)
    if interval == "10m":
        return end_at - timedelta(days=21)
    if interval == "30m":
        return end_at - timedelta(days=60)
    if interval == "1hr":
        return end_at - timedelta(days=120)
    return end_at - timedelta(days=365)


def _available_replay_bounds(config) -> tuple[datetime, datetime | None]:
    """Return the supported replay bounds for UI controls and route clamping."""
    try:
        bounds = ParquetMarketDataClient(config).fetch_candle_bounds(interval=config.ingestion.interval)
    except OSError:
        bounds = None
    earliest = bounds.earliest if bounds and bounds.earliest is not None else datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    latest = bounds.latest if bounds else None
    return earliest, latest


def _clamp_datetime(value: datetime | None, *, lower: datetime, upper: datetime | None) -> datetime | None:
    """Clamp a datetime into the available replay window."""
    if value is None:
        return None
    if value < lower:
        return lower
    if upper is not None and value > upper:
        return upper
    return value


def _normalize_replay_window(
    *,
    interval: str,
    start_at: datetime | None,
    end_at: datetime | None,
    lower_bound: datetime,
    upper_bound: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    """Clamp and default a replay window to the available data range."""
    normalized_end = _clamp_datetime(end_at, lower=lower_bound, upper=upper_bound) or upper_bound
    normalized_start = _clamp_datetime(start_at, lower=lower_bound, upper=upper_bound)
    if normalized_start is None and normalized_end is not None:
        normalized_start = _default_backtest_start(interval=interval, end_at=normalized_end)
    normalized_start = _clamp_datetime(normalized_start, lower=lower_bound, upper=upper_bound)
    if normalized_end is not None and normalized_start is not None and normalized_start > normalized_end:
        normalized_start = lower_bound if lower_bound <= normalized_end else normalized_end
    return normalized_start, normalized_end


def _to_datetime_local_value(value: datetime | None) -> str:
    """Format a UTC datetime for datetime-local inputs."""
    if value is None:
        return ""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


def _configured_backtest_config(
    *,
    base_config,
    execution_cost_preset: str,
    fee_pct: float,
    spread_pct: float,
    slippage_pct: float,
) -> object:
    """Clone config and apply backtest-specific execution-cost overrides."""
    config = copy.deepcopy(base_config)
    config.execution.execution_cost_preset = execution_cost_preset
    config.execution.fee_pct = fee_pct
    config.execution.spread_pct = spread_pct
    config.execution.slippage_pct = slippage_pct
    return config


def _parse_float_sweep(raw: str | None, default: list[float]) -> list[float]:
    """Parse a comma-separated float list for simulation sweeps."""
    if raw is None or not raw.strip():
        return default
    values = [float(item.strip()) for item in raw.split(",") if item.strip()]
    return values or default


def _parse_int_sweep(raw: str | None, default: list[int]) -> list[int]:
    """Parse a comma-separated int list for simulation sweeps."""
    if raw is None or not raw.strip():
        return default
    values = [int(item.strip()) for item in raw.split(",") if item.strip()]
    return values or default


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
    state = load_dashboard_state(load_config())
    payload = state["ingestion_state"] or {"status": "missing"}
    if state["ingestion_gap_audit"] is not None:
        payload = {**payload, "gap_audit": state["ingestion_gap_audit"]}
    return payload


@app.get("/api/trading")
def api_trading() -> dict[str, object]:
    """Return the latest trading-related artifacts."""
    state = load_dashboard_state(load_config(), include_candles=False)
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
    trades = load_dashboard_state(load_config(), include_candles=False)["recent_trades"]
    return {"trades": trades[-limit:]}


@app.get("/api/backtest")
def api_backtest(
    symbol: str | None = None,
    interval: str = Query(default="30m"),
    start: str | None = None,
    end: str | None = None,
    execution_cost_preset: str = Query(default="simple"),
    fee_pct: float = Query(default=0.001, ge=0.0, le=0.1),
    spread_pct: float = Query(default=0.0005, ge=0.0, le=0.1),
    slippage_pct: float = Query(default=0.0005, ge=0.0, le=0.1),
) -> dict[str, object]:
    """Run a historical backtest over parquet candles and return summary output."""
    base_config = load_config()
    config = _configured_backtest_config(
        base_config=base_config,
        execution_cost_preset=execution_cost_preset,
        fee_pct=fee_pct,
        spread_pct=spread_pct,
        slippage_pct=slippage_pct,
    )
    engine = BacktestEngine(config)
    end_at = _parse_optional_iso_datetime(end)
    start_at = _parse_optional_iso_datetime(start)
    if start_at is None:
        start_at = _default_backtest_start(interval=interval, end_at=end_at or datetime.now(UTC))
    try:
        result = engine.run(
            symbol=symbol or config.trading.symbol,
            interval=interval,
            start_at=start_at,
            end_at=end_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = save_backtest_result(config.data.data_lake_path, result)
    return {
        "symbol": payload["symbol"],
        "interval": payload["interval"],
        "start_at": payload["start_at"],
        "end_at": payload["end_at"],
        "candles_processed": payload["candles_processed"],
        "metrics": payload["metrics"],
        "final_snapshot": payload["final_snapshot"],
        "execution_costs": {
            "preset": config.execution.execution_cost_preset,
            "fee_pct": config.execution.fee_pct,
            "spread_pct": config.execution.spread_pct,
            "slippage_pct": config.execution.slippage_pct,
            "total_fees_usd": float((payload["final_snapshot"] or {}).get("total_fees_usd", 0.0)),
            "total_spread_cost_usd": float((payload["final_snapshot"] or {}).get("total_spread_cost_usd", 0.0)),
            "total_slippage_cost_usd": float((payload["final_snapshot"] or {}).get("total_slippage_cost_usd", 0.0)),
            "total_execution_cost_usd": (
                float((payload["final_snapshot"] or {}).get("total_fees_usd", 0.0))
                + float((payload["final_snapshot"] or {}).get("total_spread_cost_usd", 0.0))
                + float((payload["final_snapshot"] or {}).get("total_slippage_cost_usd", 0.0))
            ),
        },
        "equity_curve": payload["equity_curve"],
        "benchmark_curve": payload["benchmark_curve"],
        "drawdowns": payload["drawdowns"],
        "halted_reason": payload["halted_reason"],
        "halted_at": payload["halted_at"],
        "trades": payload["trades"],
        "signals": [
            {
                "timestamp": step["timestamp"],
                "regime": step["regime"],
                "strategy_name": step["strategy_name"],
                "signal_count": step["signal_count"],
                "execution_count": step["execution_count"],
                "decision": step["decision"],
                "equity_usd": step["equity_usd"],
                "drawdown_percent": step["drawdown_percent"],
                "trace": step["trace"],
            }
            for step in payload["steps"]
        ],
    }


@app.get("/", response_class=HTMLResponse)
def index() -> RedirectResponse:
    """Redirect to the Bitcoin market page."""
    return RedirectResponse(url="/bitcoin", status_code=307)


@app.get("/bitcoin", response_class=HTMLResponse)
def bitcoin_page() -> str:
    """Render the Bitcoin market dashboard."""
    config = load_config()
    state = load_dashboard_state(
        config,
        candle_intervals=["1m", "10m", "30m", "1month"],
        candle_limits_by_interval={
            "1m": 60,
            "10m": 48,
            "30m": 48,
            "1month": None,
        },
        include_backtests=False,
        include_simulations=False,
    )
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
      <div class="status-chip"><div class="label">Trade Regime</div><div class="status-value">{escape(str(latest_cycle.get('regime', 'n/a')).upper())}</div></div>
      <div class="status-chip"><div class="label">Trade Confidence</div><div class="status-value">{confidence_score:.2f} ({escape(confidence_label)})</div></div>
      <div class="status-chip"><div class="label">Freshness</div><div class="status-value"><span class="pill {freshness_class}">{escape(freshness_label)}</span></div></div>
      <div class="status-chip"><div class="label">Latest Candle</div><div class="status-value">{escape(latest_ingested_label)}</div></div>
    </section>
    <section class="btc-layout">
      <div class="btc-main">
        <section class="panel market-card">
          <div class="market-top">
            <div>
              <div class="market-title">Market Context</div>
              <div class="market-sub">Metrics on this card update with the active chart selection. The signal panel uses the latest trading cycle separately.</div>
            </div>
          </div>
          <div class="market-price-row">
            <div>
              <div class="market-price" id="market-price">${btc_summary["price"]:,.2f}</div>
              <div class="market-change" id="market-change" style="color:{'#9cf7b7' if float(btc_summary['change_percent']) >= 0 else '#fecaca'};">{btc_summary['change_percent']:+.2f}% vs loaded window</div>
            </div>
            <div class="hero-row">
              <span class="pill neutral" id="market-trend-pill">Market Trend {escape(trend_label.upper())}</span>
              <span class="pill neutral" id="market-volatility-pill">Market Volatility {escape(volatility)}</span>
            </div>
          </div>
          <div class="market-stats">
            <div class="market-stat"><div class="metric-label">Range High</div><div class="metric-value" id="market-range-high">${btc_summary["window_high"]:,.2f}</div></div>
            <div class="market-stat"><div class="metric-label">Range Low</div><div class="metric-value" id="market-range-low">${btc_summary["window_low"]:,.2f}</div></div>
            <div class="market-stat"><div class="metric-label">Avg Volume</div><div class="metric-value" id="market-avg-volume">{avg_volume:,.2f} BTC</div></div>
            <div class="market-stat"><div class="metric-label">EMA Spread</div><div class="metric-value" id="market-ema-spread">{spread:+.0f} ({escape(trend_label)})</div></div>
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
          <div class="label">Trade Indicators</div>
          <div class="side-title">Current Signal Context</div>
          <div class="chart-note">Latest scheduled trading-cycle snapshot, based on the most recent 500 x 1m candles.</div>
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
      const marketPriceEl = document.getElementById("market-price");
      const marketChangeEl = document.getElementById("market-change");
      const marketTrendPillEl = document.getElementById("market-trend-pill");
      const marketVolatilityPillEl = document.getElementById("market-volatility-pill");
      const marketRangeHighEl = document.getElementById("market-range-high");
      const marketRangeLowEl = document.getElementById("market-range-low");
      const marketAvgVolumeEl = document.getElementById("market-avg-volume");
      const marketEmaSpreadEl = document.getElementById("market-ema-spread");
      const rangeButtons = [...document.querySelectorAll("[data-range]")];
      const typeButtons = [...document.querySelectorAll("[data-chart-type]")];
      let activeRange = "1440";
      let activeType = "line";

      function sourceIntervalForRange(range) {{
        if (range === "60") return "1m";
        if (range === "240" || range === "480") return "10m";
        if (range === "1440") return "30m";
        if (range === "all") return "1month";
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

      function xAxisTickFormatForRange(range) {{
        if (range === "60") return "%-I:%M %p";
        if (range === "240" || range === "480") return "%b %-d\\n%-I:%M %p";
        if (range === "1440") return "%b %-d\\n%-I:%M %p";
        return "%b %-d\\n%Y";
      }}

      function updateIntervalUi() {{
        const interval = sourceIntervalForRange(activeRange);
        const labelMap = {{
          "1m": "1m",
          "10m": "10m",
          "30m": "30m",
          "1d": "1d",
          "1month": "1mo",
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

      function calculateEma(values, period) {{
        if (!values.length) return 0;
        const multiplier = 2 / (period + 1);
        let ema = values[0];
        for (let index = 1; index < values.length; index += 1) {{
          ema = (values[index] - ema) * multiplier + ema;
        }}
        return ema;
      }}

      function calculateAtr(data, period = 14) {{
        if (data.length < 2) return 0;
        const trueRanges = [];
        for (let index = 1; index < data.length; index += 1) {{
          const current = data[index];
          const previous = data[index - 1];
          const high = Number(current.high ?? current.close);
          const low = Number(current.low ?? current.close);
          const previousClose = Number(previous.close);
          const trueRange = Math.max(
            high - low,
            Math.abs(high - previousClose),
            Math.abs(low - previousClose),
          );
          trueRanges.push(trueRange);
        }}
        const window = trueRanges.slice(-period);
        if (!window.length) return 0;
        return window.reduce((sum, value) => sum + value, 0) / window.length;
      }}

      function trendStrengthFromSpread(spread) {{
        if (spread > 20) return "Bullish";
        if (spread > 0) return "Weak bullish";
        if (spread < -20) return "Bearish";
        if (spread < 0) return "Weak bearish";
        return "Flat";
      }}

      function volatilityLabel(atr, price) {{
        if (price <= 0) return "Unknown";
        const ratio = (atr / price) * 100;
        if (ratio >= 0.35) return "High";
        if (ratio >= 0.15) return "Medium";
        return "Low";
      }}

      function updateMarketContext(data) {{
        if (!data.length) return;
        const closes = data.map(point => Number(point.close));
        const highs = data.map(point => Number(point.high ?? point.close));
        const lows = data.map(point => Number(point.low ?? point.close));
        const volumes = data.map(point => Number(point.volume ?? 0));
        const firstClose = closes[0];
        const lastClose = closes[closes.length - 1];
        const changePercent = firstClose === 0 ? 0 : ((lastClose - firstClose) / firstClose) * 100;
        const avgVolume = volumes.length ? volumes.reduce((sum, value) => sum + value, 0) / volumes.length : 0;
        const emaFast = calculateEma(closes, 12);
        const emaSlow = calculateEma(closes, 26);
        const spread = emaFast - emaSlow;
        const trendLabel = trendStrengthFromSpread(spread);
        const atr = calculateAtr(data, 14);
        const volatility = volatilityLabel(atr, lastClose);

        if (marketPriceEl) {{
          marketPriceEl.textContent = formatCurrency(lastClose);
        }}
        if (marketChangeEl) {{
          marketChangeEl.textContent = `${{changePercent >= 0 ? "+" : ""}}${{changePercent.toFixed(2)}}% vs visible range`;
          marketChangeEl.style.color = changePercent >= 0 ? "#9cf7b7" : "#fecaca";
        }}
        if (marketTrendPillEl) {{
          marketTrendPillEl.textContent = `Market Trend ${{trendLabel.toUpperCase()}}`;
        }}
        if (marketVolatilityPillEl) {{
          marketVolatilityPillEl.textContent = `Market Volatility ${{volatility}}`;
        }}
        if (marketRangeHighEl) {{
          marketRangeHighEl.textContent = formatCurrency(Math.max(...highs));
        }}
        if (marketRangeLowEl) {{
          marketRangeLowEl.textContent = formatCurrency(Math.min(...lows));
        }}
        if (marketAvgVolumeEl) {{
          marketAvgVolumeEl.textContent = `${{avgVolume.toFixed(2)}} BTC`;
        }}
        if (marketEmaSpreadEl) {{
          const roundedSpread = spread >= 0 ? `+${{spread.toFixed(0)}}` : spread.toFixed(0);
          marketEmaSpreadEl.textContent = `${{roundedSpread}} (${{trendLabel}})`;
        }}
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
            tickformat: xAxisTickFormatForRange(activeRange),
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
            volume: Number(candle.volume ?? 0),
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
          updateMarketContext(subset);
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
def trades_page(
    run_backtest: int = Query(default=0, ge=0, le=1),
    run_simulation: int = Query(default=0, ge=0, le=1),
    mode: str = Query(default="paper"),
    interval: str = Query(default="30m"),
    start: str | None = None,
    end: str | None = None,
    execution_cost_preset: str = Query(default="simple"),
    fee_pct: float = Query(default=0.001, ge=0.0, le=0.1),
    spread_pct: float = Query(default=0.0005, ge=0.0, le=0.1),
    slippage_pct: float = Query(default=0.0005, ge=0.0, le=0.1),
    backtest_recorded_at: str | None = None,
    backtest_run_idx: int | None = Query(default=None, ge=0),
    simulation_run_idx: int | None = Query(default=None, ge=0),
    sim_rsi_values: str | None = None,
    sim_take_profit_values: str | None = None,
    sim_no_follow_values: str | None = None,
    sim_follow_buffer_values: str | None = None,
    sim_atr_values: str | None = None,
) -> str:
    """Render the trades and portfolio dashboard."""
    view_mode = "simulation" if run_simulation else "backtest" if run_backtest else mode.lower()
    if view_mode not in {"paper", "backtest", "simulation"}:
        view_mode = "paper"
    config = load_config()
    replay_lower_bound, replay_upper_bound = _available_replay_bounds(config)
    include_trade_chart = view_mode == "paper"
    state = load_dashboard_state(
        config,
        include_candles=include_trade_chart,
        candle_intervals=["1m"] if include_trade_chart else None,
        candle_limit=90 if include_trade_chart else None,
        include_ingestion=False,
        include_paper=view_mode == "paper",
        include_backtests=view_mode == "backtest",
        include_simulations=view_mode == "simulation",
    )
    latest_cycle = state["latest_cycle"] or {}
    latest_trace = state["latest_trace"] or {}
    snapshot = (state["portfolio_snapshot"] or {}).get("snapshot", {})
    portfolio = _portfolio_metrics(snapshot, config.execution.initial_cash_usd)
    daily_pnl = 0.0
    if state["recent_cycles"]:
        latest_equity = float(snapshot.get("equity_usd", 0.0))
        latest_dt = datetime.fromisoformat(str((state["recent_cycles"][-1] or {}).get("recorded_at", datetime.now(UTC).isoformat())))
        cutoff = latest_dt - timedelta(days=1)
        day_ago_cycles = [
            cycle for cycle in state["recent_cycles"]
            if cycle.get("recorded_at") and datetime.fromisoformat(str(cycle["recorded_at"])) >= cutoff
        ]
        if day_ago_cycles:
            first_equity = float((day_ago_cycles[0].get("portfolio_snapshot") or {}).get("equity_usd", latest_equity))
            daily_pnl = latest_equity - first_equity
    decision = _decision_breakdown(latest_cycle, latest_trace)
    trades = list(reversed(state["recent_trades"]))
    decisions = list(reversed(state["recent_cycles"]))
    chronological_trades = list(state["recent_trades"])
    first_dca_buy_timestamp = next(
        (
            str(trade.get("timestamp", ""))
            for trade in chronological_trades
            if str(trade.get("side", "")).lower() == "buy"
            and str(trade.get("strategy_name", "") or "DCAStrategy") == "DCAStrategy"
        ),
        None,
    )
    recent_table = (
        "".join(_format_trade_row(trade, first_dca_buy_timestamp=first_dca_buy_timestamp) for trade in trades)
        if trades
        else "<tr><td class='empty' colspan='9'>No trades recorded yet.</td></tr>"
    )
    decision_rows: list[str] = []
    for index, cycle in enumerate(decisions):
        cycle_breakdown = _decision_breakdown(cycle, cycle)
        decision_rows.append(_format_decision_row(cycle, cycle_breakdown, hidden=index >= 10))
    decision_table = "".join(decision_rows) if decision_rows else "<tr><td class='empty' colspan='7'>No decisions recorded yet.</td></tr>"
    hidden_decision_count = max(len(decisions) - 10, 0)
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
    daily_pnl_class = "value-positive" if daily_pnl >= 0 else "value-negative"
    paper_chart_payload = json.dumps(state["chart_candles"].get("1m", [])[-90:] if include_trade_chart else [])
    paper_trades_payload = json.dumps(state["recent_trades"]) if include_trade_chart else "[]"
    signal_confidence_score, signal_confidence_label = _confidence_snapshot(
        latest_cycle.get("indicator_snapshot", {}),
        str(latest_cycle.get("regime", "")),
    )
    backtest_summary = ""
    backtest_portfolio_side = ""
    selected_backtest: dict[str, object] | None = None
    simulation_summary = ""
    simulation_side = ""
    selected_simulation: dict[str, object] | None = None
    selected_fee_pct = fee_pct if fee_pct is not None else config.execution.fee_pct
    selected_spread_pct = spread_pct if spread_pct is not None else config.execution.spread_pct
    selected_slippage_pct = slippage_pct if slippage_pct is not None else config.execution.slippage_pct
    selected_sim_rsi_values = sim_rsi_values or "35,40,45"
    selected_sim_take_profit_values = sim_take_profit_values or "1.5,2.0"
    selected_sim_no_follow_values = sim_no_follow_values or "2,3"
    selected_sim_follow_buffer_values = sim_follow_buffer_values or "0.1,0.2"
    selected_sim_atr_values = sim_atr_values or "1.5,2.0"
    parsed_start = _parse_optional_iso_datetime(start)
    parsed_end = _parse_optional_iso_datetime(end)
    normalized_start, normalized_end = _normalize_replay_window(
        interval=interval,
        start_at=parsed_start,
        end_at=parsed_end,
        lower_bound=replay_lower_bound,
        upper_bound=replay_upper_bound,
    )
    backtest_start_value = _to_datetime_local_value(normalized_start)
    backtest_end_value = _to_datetime_local_value(normalized_end)
    replay_min_value = _to_datetime_local_value(replay_lower_bound)
    replay_max_value = _to_datetime_local_value(replay_upper_bound)
    available_backtests = list(reversed(state.get("recent_backtests", [])))
    available_simulations = list(reversed(state.get("recent_simulations", [])))
    if backtest_run_idx is not None and backtest_run_idx < len(available_backtests):
        selected_backtest = available_backtests[backtest_run_idx]
    elif backtest_recorded_at:
        selected_backtest = next(
            (run for run in available_backtests if str(run.get("recorded_at", "")) == backtest_recorded_at),
            None,
        )
    if selected_backtest is None:
        selected_backtest = state.get("latest_backtest") or (available_backtests[0] if available_backtests else None)
    selected_backtest_idx = (
        available_backtests.index(selected_backtest)
        if selected_backtest in available_backtests
        else 0
    )
    if simulation_run_idx is not None and simulation_run_idx < len(available_simulations):
        selected_simulation = available_simulations[simulation_run_idx]
    if selected_simulation is None:
        selected_simulation = state.get("latest_simulation") or (available_simulations[0] if available_simulations else None)
    selected_simulation_idx = (
        available_simulations.index(selected_simulation)
        if selected_simulation in available_simulations
        else 0
    )

    backtest_history_nav = (
        "".join(
            f"""
            <a class="history-link {'active' if index == selected_backtest_idx else ''}"
               href="/trades?mode=backtest&backtest_run_idx={index}"
               style="text-decoration:none;">
              <div class="history-link-meta">{escape(_format_display_timestamp(str(run.get('recorded_at', ''))))}</div>
              <div class="history-link-main">{escape(str(run.get('interval', 'n/a')))}</div>
              <div class="history-link-sub">{float((run.get('metrics') or {}).get('total_return_percent', 0.0)):+.2f}% return</div>
            </a>
            """
            for index, run in enumerate(available_backtests)
        )
        if available_backtests
        else "<div class='empty'>No saved backtest runs yet.</div>"
    )
    simulation_history_nav = (
        "".join(
            f"""
            <a class="history-link {'active' if index == selected_simulation_idx else ''}"
               href="/trades?mode=simulation&simulation_run_idx={index}"
               style="text-decoration:none;">
              <div class="history-link-meta">{escape(_format_display_timestamp(str(run.get('recorded_at', ''))))}</div>
              <div class="history-link-main">{int(run.get('candidate_count', 0))} candidates</div>
              <div class="history-link-sub">Best {float((((run.get('candidates') or [{}])[0].get('summary') or {}).get('metrics') or {}).get('total_return_percent', 0.0)):+.2f}% return</div>
            </a>
            """
            for index, run in enumerate(available_simulations)
        )
        if available_simulations
        else "<div class='empty'>No saved simulation runs yet.</div>"
    )
    latest_trade_summary = "No trades recorded yet."
    latest_trade_timestamp = ""
    if latest_trade:
        latest_trade_time = _format_display_timestamp(str(latest_trade.get("timestamp", "")))
        latest_trade_timestamp = latest_trade_time
        latest_trade_summary = (
            f"{str(latest_trade.get('side', '')).upper()} "
            f"${float(latest_trade.get('size_usd', 0)):.2f} @ ${float(latest_trade.get('price', 0)):.2f}"
        )

    paper_sections = f"""
        <section class="trade-section">
          <div class="trade-section-head">
            <div>
              <div class="label">Live Trade Context</div>
              <div class="trade-section-title">Paper Trading Overview</div>
              <div class="trade-section-note">Live paper-trading context uses recent 1m candles, persisted ledger activity, and the latest scheduled decision snapshot.</div>
            </div>
          </div>
          <div class="trade-split">
            <div class="trade-card-soft trade-chart-card">
              <div class="label">Paper Trading Chart</div>
              <div class="value">Last 90 Minutes</div>
              <div class="chart-note">Recent 1m BTC-USD candles with executed paper-trade markers. ATR bands are shown when the latest trade has a tracked swing stop.</div>
              <div class="trade-chart-frame" style="margin-top:.8rem;">
                <div id="tradePaperChart" class="chart-surface" style="height:360px;"></div>
              </div>
            </div>
            <div class="trade-card-soft">
              <div class="label">Signal Panel</div>
              <div class="value">Latest Trading Snapshot</div>
              <div class="subgrid" style="grid-template-columns:repeat(2,1fr);">
                <div class="metric light"><div class="metric-label">Regime</div><div class="metric-value">{escape(str(latest_cycle.get('regime', 'n/a')).upper())}</div></div>
                <div class="metric light"><div class="metric-label">Signal</div><div class="metric-value">{escape(str(decision.get('decision', 'n/a')).upper())}</div></div>
                <div class="metric light"><div class="metric-label">Confidence</div><div class="metric-value">{signal_confidence_score:.2f} ({escape(signal_confidence_label)})</div></div>
                <div class="metric light"><div class="metric-label">Strategy</div><div class="metric-value">{escape(str(latest_cycle.get('strategy_name', 'n/a')).replace('Strategy', ''))}</div></div>
                <div class="metric light"><div class="metric-label">RSI</div><div class="metric-value">{float((latest_cycle.get('indicator_snapshot') or {}).get('rsi', 0.0)):.2f}</div></div>
                <div class="metric light"><div class="metric-label">ATR</div><div class="metric-value">{float((latest_cycle.get('indicator_snapshot') or {}).get('atr', 0.0)):.2f}</div></div>
                <div class="metric light"><div class="metric-label">Trend</div><div class="metric-value">{escape(str(latest_cycle.get('regime', 'n/a')).upper())}</div></div>
              </div>
            </div>
          </div>
        </section>
        <section class="trade-section">
          <div class="trade-section-head">
            <div>
              <div class="label">Executed Buys and Sells</div>
              <div class="trade-section-title">Ledger Activity</div>
            </div>
          </div>
          <div class="trade-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Side</th>
                <th>Symbol</th>
                <th>USD</th>
                <th>Price</th>
                <th>BTC</th>
                <th>Costs</th>
                <th>Strategy</th>
                <th>Signal Type</th>
              </tr>
            </thead>
            <tbody>{recent_table}</tbody>
          </table>
          </div>
        </section>
        <section class="trade-section decision-card">
          <div class="trade-section-head">
            <div>
              <div class="label">Decision Breakdown</div>
              <div class="trade-section-title" id="decision-headline">{escape(str(decision["headline"]))}</div>
            </div>
          </div>
          <p class="label" id="decision-timestamp" style="margin-top:.45rem;">{escape(_format_display_timestamp(str(decision.get("timestamp", ""))))}</p>
          <ul class="decision-list" id="decision-reasons">
            {''.join(f"<li>{escape(str(line))}</li>" for line in decision["reason_lines"])}
          </ul>
          <p id="decision-interpretation"><strong>Interpretation:</strong> {escape(str(decision["interpretation"]))}</p>
        </section>
        <section class="trade-section">
          <div class="trade-section-head">
            <div>
              <div class="label">Decision Log</div>
              <div class="trade-section-title">Recent Scheduled Decisions</div>
            </div>
          </div>
          <div class="segmented" style="margin-top:.8rem;">
            <button class="seg-btn active" id="decision-filter-buy" type="button">Buy</button>
            <button class="seg-btn" id="decision-filter-sell" type="button">Sell</button>
            <button class="seg-btn" id="decision-filter-all" type="button">All</button>
          </div>
          <div class="trade-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Regime</th>
                <th>Strategy</th>
                <th>Decision</th>
                <th>Signals</th>
                <th>Executions</th>
                <th>Interpretation</th>
              </tr>
            </thead>
            <tbody id="decision-log-body">{decision_table}</tbody>
          </table>
          </div>
          {"<button class='ghost' id='decision-log-expand' style='margin-top:.9rem;'>Show 10 more</button>" if hidden_decision_count else ""}
        </section>
    """
    backtest_controls = f"""
        <section class="trade-section">
          <div class="trade-section-head">
            <div>
              <div class="label">Backtest Controls</div>
              <div class="trade-section-title">Historical Replay Setup</div>
              <div class="trade-section-note">Configure the replay window and cost assumptions, then run the selected scenario explicitly.</div>
            </div>
          </div>
          <form method="get" action="/trades" style="margin-top:.9rem; display:grid; gap:.8rem;">
            <input type="hidden" name="mode" value="backtest" />
            <input type="hidden" name="run_backtest" value="1" />
            <div class="filter-grid" style="display:grid; grid-template-columns:180px 1fr 1fr auto;">
              <div class="field">
                <label for="backtestInterval">Interval</label>
                <select id="backtestInterval" name="interval">
                  <option value="1m" {'selected' if interval == '1m' else ''}>1m</option>
                  <option value="10m" {'selected' if interval == '10m' else ''}>10m</option>
                  <option value="30m" {'selected' if interval == '30m' else ''}>30m</option>
                  <option value="1hr" {'selected' if interval == '1hr' else ''}>1hr</option>
                  <option value="1d" {'selected' if interval == '1d' else ''}>1d</option>
                </select>
              </div>
              <div class="field">
                <label for="backtestStart">Start</label>
                <input id="backtestStart" type="datetime-local" name="start" min="{escape(replay_min_value)}" max="{escape(replay_max_value)}" value="{escape(backtest_start_value)}" />
              </div>
              <div class="field">
                <label for="backtestEnd">End</label>
                <input id="backtestEnd" type="datetime-local" name="end" min="{escape(replay_min_value)}" max="{escape(replay_max_value)}" value="{escape(backtest_end_value)}" />
              </div>
              <input type="hidden" name="execution_cost_preset" value="custom" />
            </div>
            <div class="filter-grid" style="display:grid; grid-template-columns:1fr 1fr 1fr auto;">
              <div class="field">
                <label for="backtestFeePct">Fee %</label>
                <input id="backtestFeePct" type="number" name="fee_pct" min="0" max="0.1" step="0.0001" value="{selected_fee_pct:.4f}" />
              </div>
              <div class="field">
                <label for="backtestSpreadPct">Spread %</label>
                <input id="backtestSpreadPct" type="number" name="spread_pct" min="0" max="0.1" step="0.0001" value="{selected_spread_pct:.4f}" />
              </div>
              <div class="field">
                <label for="backtestSlippagePct">Slippage %</label>
                <input id="backtestSlippagePct" type="number" name="slippage_pct" min="0" max="0.1" step="0.0001" value="{selected_slippage_pct:.4f}" />
              </div>
              <div class="filter-actions" style="align-items:end;">
                <button class="ghost" type="submit">Run Backtest</button>
              </div>
            </div>
          </form>
        </section>
    """
    backtest_empty = """
        <section class="trade-section simulation-card">
          <div class="label">Backtest Summary</div>
          <div class="value">Not Run Yet</div>
          <p>Choose an interval and optional date window, then run the backtest from this view.</p>
        </section>
    """
    backtest_payload = ""
    if view_mode == "backtest" and run_backtest:
        try:
            start_at, end_at = normalized_start, normalized_end
            backtest_config = _configured_backtest_config(
                base_config=config,
                execution_cost_preset="custom",
                fee_pct=selected_fee_pct,
                spread_pct=selected_spread_pct,
                slippage_pct=selected_slippage_pct,
            )
            backtest_result = BacktestEngine(backtest_config).run(
                symbol=config.trading.symbol,
                interval=interval,
                start_at=start_at,
                end_at=end_at,
            )
            saved_backtest = save_backtest_result(config.data.data_lake_path, backtest_result)
            selected_backtest = saved_backtest
            backtest_payload = json.dumps(
                {
                    "equity_curve": saved_backtest["equity_curve"],
                    "benchmark_curve": saved_backtest["benchmark_curve"],
                    "drawdowns": saved_backtest["drawdowns"],
                }
            )
            metrics = backtest_result.metrics
            latest_step = saved_backtest["steps"][-1] if saved_backtest["steps"] else None
            final_snapshot = saved_backtest["final_snapshot"] or {}
            total_fees = float(final_snapshot.get("total_fees_usd", 0.0))
            total_spread = float(final_snapshot.get("total_spread_cost_usd", 0.0))
            total_slippage = float(final_snapshot.get("total_slippage_cost_usd", 0.0))
            total_execution_cost = total_fees + total_spread + total_slippage
        except ValueError as exc:
            backtest_summary = f"""
            <section class="trade-section">
              <div class="label">Backtest Summary</div>
              <div class="value">Unavailable</div>
              <p>{escape(str(exc))}</p>
            </section>
            """
    if view_mode == "backtest" and not backtest_summary and selected_backtest:
        backtest_payload = json.dumps(
            {
                "equity_curve": selected_backtest.get("equity_curve", []),
                "benchmark_curve": selected_backtest.get("benchmark_curve", []),
                "drawdowns": selected_backtest.get("drawdowns", []),
            }
        )
        metrics = selected_backtest.get("metrics", {}) or {}
        final_snapshot = selected_backtest.get("final_snapshot", {}) or {}
        total_fees = float(final_snapshot.get("total_fees_usd", 0.0))
        total_spread = float(final_snapshot.get("total_spread_cost_usd", 0.0))
        total_slippage = float(final_snapshot.get("total_slippage_cost_usd", 0.0))
        total_execution_cost = total_fees + total_spread + total_slippage
        halted_reason = str(selected_backtest.get("halted_reason") or "")
        halted_at = str(selected_backtest.get("halted_at") or "")
        halt_label = (
            "Stopped by Stop-Loss" if halted_reason == "stop_loss_triggered"
            else "Stopped by Drawdown Guard" if halted_reason == "max_drawdown_reached"
            else "Completed Window"
        )
        selected_step = ((selected_backtest.get("steps") or [])[-1:][0]) if selected_backtest.get("steps") else None
        selected_step_breakdown = _backtest_step_breakdown(selected_step or {})
        backtest_decisions = list(reversed(selected_backtest.get("steps") or []))
        backtest_decision_rows = "".join(
            _format_backtest_decision_row(step, hidden=index >= 10)
            for index, step in enumerate(backtest_decisions)
        ) or "<tr><td class='empty' colspan='7'>No replay decisions recorded yet.</td></tr>"
        hidden_backtest_decision_count = max(len(backtest_decisions) - 10, 0)
        backtest_portfolio_side = f"""
        <section class="trade-section" style="display:{'block' if view_mode == 'backtest' else 'none'};">
          <div class="label">Portfolio Snapshot</div>
          <div class="value">Replay End State</div>
          <div class="market-mini">
            <div class="mini-row"><div class="mini-label">Final Portfolio Value</div><div class="mini-value">${float(final_snapshot.get('equity_usd', 0.0)):.2f}</div></div>
            <div class="mini-row"><div class="mini-label">Ending Cash</div><div class="mini-value">${float(final_snapshot.get('cash_usd', 0.0)):.2f}</div></div>
            <div class="mini-row"><div class="mini-label">Ending BTC</div><div class="mini-value">{float(final_snapshot.get('btc_units', 0.0)):.6f} BTC</div></div>
            <div class="mini-row"><div class="mini-label">Avg Entry</div><div class="mini-value">${float(final_snapshot.get('avg_entry_price', 0.0)):.2f}</div></div>
            <div class="mini-row"><div class="mini-label">Last Mark</div><div class="mini-value">${float(final_snapshot.get('last_mark_price', 0.0)):.2f}</div></div>
            <div class="mini-row"><div class="mini-label">Realized PnL</div><div class="mini-value">${float(final_snapshot.get('realized_pnl_usd', 0.0)):+.2f}</div></div>
            <div class="mini-row"><div class="mini-label">Final Cost</div><div class="mini-value">${total_execution_cost:.2f}</div></div>
            <div class="mini-row"><div class="mini-label">Run Status</div><div class="mini-value">{escape(halt_label)}</div></div>
          </div>
        </section>
        """
        backtest_summary = f"""
            <section class="trade-section">
              <div class="trade-section-head">
                <div>
                  <div class="label">Backtest Results</div>
                  <div class="trade-section-title">Historical Replay ({escape(str(selected_backtest.get('interval', 'n/a')))})</div>
                </div>
              </div>
              <div class="market-mini" style="margin-top:.35rem; margin-bottom:.95rem;">
                <div class="mini-row"><div class="mini-label">Replay Window</div><div class="mini-value">{escape(_format_display_timestamp(str(selected_backtest.get('start_at', ''))))} to {escape(_format_display_timestamp(str(selected_backtest.get('end_at', ''))))}</div></div>
                <div class="mini-row"><div class="mini-label">Saved Run</div><div class="mini-value">{escape(_format_display_timestamp(str(selected_backtest.get('recorded_at', ''))))}</div></div>
                <div class="mini-row"><div class="mini-label">Run End</div><div class="mini-value">{escape(_format_display_timestamp(halted_at)) if halted_at else 'Completed selected window'}</div></div>
              </div>
              <div class="subgrid" style="margin-top:.8rem;">
                <div class="metric light"><div class="metric-label">Total Return</div><div class="metric-value">{float(metrics.get('total_return_percent', 0.0)):+.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Buy & Hold</div><div class="metric-value">{float(metrics.get('buy_and_hold_return_percent', 0.0)):+.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Max Drawdown</div><div class="metric-value">{float(metrics.get('max_drawdown_percent', 0.0)):.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Sharpe</div><div class="metric-value">{float(metrics.get('sharpe_ratio', 0.0)):.2f}</div></div>
                <div class="metric light"><div class="metric-label">Win Rate</div><div class="metric-value">{float(metrics.get('win_rate_percent', 0.0)):.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Total Trades</div><div class="metric-value">{int(metrics.get('filled_trade_count', 0))}</div></div>
                <div class="metric light"><div class="metric-label">Avg Win</div><div class="metric-value">${float(metrics.get('avg_win_usd', 0.0)):.2f}</div></div>
                <div class="metric light"><div class="metric-label">Avg Loss</div><div class="metric-value">${float(metrics.get('avg_loss_usd', 0.0)):.2f}</div></div>
                <div class="metric light"><div class="metric-label">Profit Factor</div><div class="metric-value">{float(metrics.get('profit_factor', 0.0)):.2f}</div></div>
                <div class="metric light"><div class="metric-label">Fees Paid</div><div class="metric-value">${total_fees:.2f}</div></div>
                <div class="metric light"><div class="metric-label">Spread Cost</div><div class="metric-value">${total_spread:.2f}</div></div>
                <div class="metric light"><div class="metric-label">Slippage Cost</div><div class="metric-value">${total_slippage:.2f}</div></div>
              </div>
            </section>
            <section class="trade-section decision-card">
              <div class="trade-section-head">
                <div>
                  <div class="label">Decision Breakdown</div>
                  <div class="trade-section-title" id="backtest-decision-headline">{escape(str(selected_step_breakdown['headline']))}</div>
                </div>
              </div>
              <p class="label" id="backtest-decision-timestamp" style="margin-top:.45rem;">{escape(str(selected_step_breakdown.get('timestamp', '')))}</p>
              <ul class="decision-list" id="backtest-decision-reasons">
                {''.join(f"<li>{escape(str(line))}</li>" for line in selected_step_breakdown["reason_lines"])}
              </ul>
              <p id="backtest-decision-interpretation"><strong>Interpretation:</strong> {escape(str(selected_step_breakdown["interpretation"]))}</p>
            </section>
            <section class="trade-section">
              <div class="trade-section-head">
                <div>
                  <div class="label">Decision Log</div>
                  <div class="trade-section-title">Replay Decision Timeline</div>
                </div>
              </div>
              <div class="segmented" style="margin-top:.8rem;">
                <button class="seg-btn active" id="backtest-decision-filter-buy" type="button">Buy</button>
                <button class="seg-btn" id="backtest-decision-filter-sell" type="button">Sell</button>
                <button class="seg-btn" id="backtest-decision-filter-all" type="button">All</button>
              </div>
              <div class="trade-table-wrap">
              <table>
                <thead>
                  <tr><th>Timestamp</th><th>Regime</th><th>Strategy</th><th>Decision</th><th>Signals</th><th>Executions</th><th>Equity</th></tr>
                </thead>
                <tbody id="backtest-decision-log-body">{backtest_decision_rows}</tbody>
              </table>
              </div>
              {"<button class='ghost' id='backtest-decision-expand' style='margin-top:.9rem;'>Show 10 more</button>" if hidden_backtest_decision_count else ""}
            </section>
            <section class="trade-section chart-card">
              <div class="label">Equity Curve</div>
              <div class="value">Strategy vs Buy & Hold</div>
              <div class="trade-chart-frame" style="margin-top:.8rem;">
                <div id="backtestEquityChart" class="chart-surface" style="height:320px;"></div>
              </div>
            </section>
            <section class="trade-section chart-card">
              <div class="label">Drawdowns</div>
              <div class="value">Peak-to-Trough Decline</div>
              <div class="trade-chart-frame" style="margin-top:.8rem;">
                <div id="backtestDrawdownChart" class="chart-surface" style="height:280px;"></div>
              </div>
            </section>
        """
    else:
        backtest_portfolio_side = ""
    if not backtest_summary:
        backtest_empty = (
            backtest_empty
        )
    backtest_sections = backtest_controls + (backtest_summary or backtest_empty)
    simulation_payload = ""
    simulation_controls = f"""
        <section class="trade-section">
          <div class="trade-section-head">
            <div>
              <div class="label">Simulation Controls</div>
              <div class="trade-section-title">Strategy Parameter Sweep</div>
              <div class="trade-section-note">Run a bounded parameter sweep over the current swing strategy to compare which settings improve return, drawdown, and trade count.</div>
            </div>
          </div>
          <form method="get" action="/trades" style="margin-top:.9rem; display:grid; gap:.8rem;">
            <input type="hidden" name="mode" value="simulation" />
            <input type="hidden" name="run_simulation" value="1" />
            <div class="filter-grid" style="display:grid; grid-template-columns:180px 1fr 1fr auto;">
              <div class="field">
                <label for="simulationInterval">Interval</label>
                <select id="simulationInterval" name="interval">
                  <option value="1m" {'selected' if interval == '1m' else ''}>1m</option>
                  <option value="10m" {'selected' if interval == '10m' else ''}>10m</option>
                  <option value="30m" {'selected' if interval == '30m' else ''}>30m</option>
                  <option value="1hr" {'selected' if interval == '1hr' else ''}>1hr</option>
                  <option value="1d" {'selected' if interval == '1d' else ''}>1d</option>
                </select>
              </div>
              <div class="field">
                <label for="simulationStart">Start</label>
                <input id="simulationStart" type="datetime-local" name="start" min="{escape(replay_min_value)}" max="{escape(replay_max_value)}" value="{escape(backtest_start_value)}" />
              </div>
              <div class="field">
                <label for="simulationEnd">End</label>
                <input id="simulationEnd" type="datetime-local" name="end" min="{escape(replay_min_value)}" max="{escape(replay_max_value)}" value="{escape(backtest_end_value)}" />
              </div>
              <div class="filter-actions" style="align-items:end;">
                <button class="ghost" type="submit">Run Simulation</button>
              </div>
            </div>
            <div class="filter-grid" style="display:grid; grid-template-columns:repeat(3, 1fr);">
              <div class="field">
                <label for="simRsiValues">RSI Max Values</label>
                <input id="simRsiValues" type="text" name="sim_rsi_values" value="{escape(selected_sim_rsi_values)}" />
              </div>
              <div class="field">
                <label for="simTakeProfitValues">Take Profit % Values</label>
                <input id="simTakeProfitValues" type="text" name="sim_take_profit_values" value="{escape(selected_sim_take_profit_values)}" />
              </div>
              <div class="field">
                <label for="simAtrValues">ATR Multiplier Values</label>
                <input id="simAtrValues" type="text" name="sim_atr_values" value="{escape(selected_sim_atr_values)}" />
              </div>
            </div>
            <div class="filter-grid" style="display:grid; grid-template-columns:repeat(2, 1fr);">
              <div class="field">
                <label for="simNoFollowValues">No Follow-Through Candle Values</label>
                <input id="simNoFollowValues" type="text" name="sim_no_follow_values" value="{escape(selected_sim_no_follow_values)}" />
              </div>
              <div class="field">
                <label for="simFollowBufferValues">Follow-Through Buffer % Values</label>
                <input id="simFollowBufferValues" type="text" name="sim_follow_buffer_values" value="{escape(selected_sim_follow_buffer_values)}" />
              </div>
            </div>
          </form>
        </section>
    """
    simulation_empty = """
        <section class="trade-section simulation-card">
          <div class="label">Simulation Results</div>
          <div class="value">Not Run Yet</div>
          <p>Run a parameter sweep from this view to compare multiple strategy configurations against the same historical window.</p>
        </section>
    """
    if view_mode == "simulation" and run_simulation:
        try:
            start_at, end_at = normalized_start, normalized_end
            parameter_grid = {
                "swing_entry_rsi_max": _parse_float_sweep(sim_rsi_values, [35.0, 40.0, 45.0]),
                "swing_take_profit_percent": _parse_float_sweep(sim_take_profit_values, [1.5, 2.0]),
                "swing_no_follow_through_candles": _parse_int_sweep(sim_no_follow_values, [2, 3]),
                "swing_follow_through_buffer_percent": _parse_float_sweep(sim_follow_buffer_values, [0.1, 0.2]),
                "atr_multiplier": _parse_float_sweep(sim_atr_values, [1.5, 2.0]),
            }
            simulation_result = SimulationEngine(config).run(
                symbol=config.trading.symbol,
                interval=interval,
                start_at=start_at,
                end_at=end_at,
                parameter_grid=parameter_grid,
            )
            selected_simulation = save_simulation_result(config.data.data_lake_path, simulation_result)
        except ValueError as exc:
            simulation_summary = f"""
            <section class="trade-section">
              <div class="label">Simulation Results</div>
              <div class="value">Unavailable</div>
              <p>{escape(str(exc))}</p>
            </section>
            """
    if view_mode == "simulation" and not simulation_summary and selected_simulation:
        candidates = list(selected_simulation.get("candidates", []))
        best_candidate = candidates[0] if candidates else None
        if best_candidate is not None:
            best_backtest = best_candidate.get("backtest", {}) or {}
            best_metrics = ((best_candidate.get("summary") or {}).get("metrics") or {})
            simulation_payload = json.dumps(
                {
                    "equity_curve": best_backtest.get("equity_curve", []),
                    "benchmark_curve": best_backtest.get("benchmark_curve", []),
                    "drawdowns": best_backtest.get("drawdowns", []),
                }
            )
            candidate_rows_list: list[str] = []
            for candidate in candidates[:12]:
                params = candidate.get("params") or {}
                metrics = ((candidate.get("summary") or {}).get("metrics") or {})
                candidate_rows_list.append(
                    "<tr>"
                    f"<td>{escape(str(candidate.get('candidate_id', 'n/a')))}</td>"
                    f"<td>RSI &lt; {float(params.get('swing_entry_rsi_max', 0.0)):.0f}</td>"
                    f"<td>{float(params.get('swing_take_profit_percent', 0.0)):.2f}%</td>"
                    f"<td>{int(params.get('swing_no_follow_through_candles', 0))}</td>"
                    f"<td>{float(params.get('swing_follow_through_buffer_percent', 0.0)):.2f}%</td>"
                    f"<td>{float(params.get('atr_multiplier', 0.0)):.2f}</td>"
                    f"<td>{float(metrics.get('total_return_percent', 0.0)):+.2f}%</td>"
                    f"<td>{float(metrics.get('max_drawdown_percent', 0.0)):.2f}%</td>"
                    f"<td>{int(metrics.get('filled_trade_count', 0))}</td>"
                    "</tr>"
                )
            candidate_rows = "".join(candidate_rows_list) or "<tr><td class='empty' colspan='9'>No simulation candidates recorded.</td></tr>"
            simulation_side = f"""
            <section class="trade-section" style="display:{'block' if view_mode == 'simulation' else 'none'};">
              <div class="label">Best Candidate</div>
              <div class="value">{escape(str(best_candidate.get('candidate_id', 'n/a')))}</div>
              <div class="market-mini">
                <div class="mini-row"><div class="mini-label">RSI Max</div><div class="mini-value">{float((best_candidate.get('params') or {}).get('swing_entry_rsi_max', 0.0)):.0f}</div></div>
                <div class="mini-row"><div class="mini-label">Take Profit</div><div class="mini-value">{float((best_candidate.get('params') or {}).get('swing_take_profit_percent', 0.0)):.2f}%</div></div>
                <div class="mini-row"><div class="mini-label">No Follow Candles</div><div class="mini-value">{int((best_candidate.get('params') or {}).get('swing_no_follow_through_candles', 0))}</div></div>
                <div class="mini-row"><div class="mini-label">Follow Buffer</div><div class="mini-value">{float((best_candidate.get('params') or {}).get('swing_follow_through_buffer_percent', 0.0)):.2f}%</div></div>
                <div class="mini-row"><div class="mini-label">ATR Multiplier</div><div class="mini-value">{float((best_candidate.get('params') or {}).get('atr_multiplier', 0.0)):.2f}</div></div>
              </div>
            </section>
            <section class="trade-section" style="display:{'block' if view_mode == 'simulation' else 'none'};">
              <div class="label">Simulation History</div>
              <div class="history-stack">{simulation_history_nav}</div>
            </section>
            """
            simulation_summary = f"""
            <section class="trade-section">
              <div class="trade-section-head">
                <div>
                  <div class="label">Simulation Results</div>
                  <div class="trade-section-title">Parameter Sweep ({escape(str(selected_simulation.get('interval', 'n/a')))})</div>
                </div>
              </div>
              <div class="market-mini" style="margin-top:.35rem; margin-bottom:.95rem;">
                <div class="mini-row"><div class="mini-label">Replay Window</div><div class="mini-value">{escape(_format_display_timestamp(str(selected_simulation.get('start_at', ''))))} to {escape(_format_display_timestamp(str(selected_simulation.get('end_at', ''))))}</div></div>
                <div class="mini-row"><div class="mini-label">Saved Run</div><div class="mini-value">{escape(_format_display_timestamp(str(selected_simulation.get('recorded_at', ''))))}</div></div>
                <div class="mini-row"><div class="mini-label">Candidates Tested</div><div class="mini-value">{int(selected_simulation.get('candidate_count', 0))}</div></div>
              </div>
              <div class="subgrid" style="margin-top:.8rem;">
                <div class="metric light"><div class="metric-label">Best Return</div><div class="metric-value">{float(best_metrics.get('total_return_percent', 0.0)):+.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Buy & Hold</div><div class="metric-value">{float(best_metrics.get('buy_and_hold_return_percent', 0.0)):+.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Max Drawdown</div><div class="metric-value">{float(best_metrics.get('max_drawdown_percent', 0.0)):.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Sharpe</div><div class="metric-value">{float(best_metrics.get('sharpe_ratio', 0.0)):.2f}</div></div>
                <div class="metric light"><div class="metric-label">Win Rate</div><div class="metric-value">{float(best_metrics.get('win_rate_percent', 0.0)):.2f}%</div></div>
                <div class="metric light"><div class="metric-label">Trades</div><div class="metric-value">{int(best_metrics.get('filled_trade_count', 0))}</div></div>
              </div>
            </section>
            <section class="trade-section">
              <div class="trade-section-head">
                <div>
                  <div class="label">Ranked Candidates</div>
                  <div class="trade-section-title">Top Parameter Sets</div>
                  <div class="trade-section-note">Candidates are ranked by return first, then drawdown, profit factor, and Sharpe.</div>
                </div>
              </div>
              <div class="trade-table-wrap">
                <table>
                  <thead>
                    <tr><th>ID</th><th>Entry</th><th>TP</th><th>No Follow</th><th>Buffer</th><th>ATR</th><th>Return</th><th>Drawdown</th><th>Trades</th></tr>
                  </thead>
                  <tbody>{candidate_rows}</tbody>
                </table>
              </div>
            </section>
            <section class="trade-section chart-card">
              <div class="label">Best Candidate Curve</div>
              <div class="value">Strategy vs Buy & Hold</div>
              <div class="trade-chart-frame" style="margin-top:.8rem;">
                <div id="simulationEquityChart" class="chart-surface" style="height:320px;"></div>
              </div>
            </section>
            <section class="trade-section chart-card">
              <div class="label">Best Candidate Drawdowns</div>
              <div class="value">Peak-to-Trough Decline</div>
              <div class="trade-chart-frame" style="margin-top:.8rem;">
                <div id="simulationDrawdownChart" class="chart-surface" style="height:280px;"></div>
              </div>
            </section>
            """
    if not simulation_summary:
        simulation_summary = simulation_empty
    if not simulation_side:
        simulation_side = f"""
        <section class="trade-section" style="display:{'block' if view_mode == 'simulation' else 'none'};">
          <div class="label">Simulation History</div>
          <div class="history-stack">{simulation_history_nav}</div>
        </section>
        """
    simulation_sections = simulation_controls + simulation_summary
    main_sections = paper_sections if view_mode == "paper" else backtest_sections if view_mode == "backtest" else simulation_sections
    system_mode_value = "Paper Trading" if view_mode == "paper" else "Backtesting" if view_mode == "backtest" else "Simulation"
    system_mode_text = (
        "The trade engine now separates base DCA holdings from opportunistic swing positions so ATR stop-loss exits can close swing trades without touching base accumulation."
        if view_mode == "paper"
        else "The backtest engine replays historical parquet candles through the same indicator, routing, and paper-execution path used by the live paper-trading runtime."
        if view_mode == "backtest"
        else "Simulation mode will host scenario-based experiments without affecting live paper-trading state."
    )

    body = f"""
    <section class="trade-page">
      <section class="trade-hero panel">
        <div class="trade-hero-top">
          <div>
            <div class="label">Trades Workspace</div>
            <div class="trade-hero-title">{'Paper Trading' if view_mode == 'paper' else 'Backtesting' if view_mode == 'backtest' else 'Simulation'}</div>
            <div class="trade-hero-sub">
              {'Live paper-trading state, execution history, and decision review in one cockpit.' if view_mode == 'paper' else 'Historical replay, saved run comparison, and decision-centric backtest review.' if view_mode == 'backtest' else 'Scenario analysis will live here once simulation workflows are implemented.'}
            </div>
          </div>
          <div class="trade-mode-pills">
            <a class="trade-mode-pill {'active' if view_mode == 'paper' else ''}" href="/trades?mode=paper">Paper</a>
            <a class="trade-mode-pill {'active' if view_mode == 'backtest' else ''}" href="/trades?mode=backtest">Backtest</a>
            <a class="trade-mode-pill {'active' if view_mode == 'simulation' else ''}" href="/trades?mode=simulation">Simulation</a>
          </div>
        </div>
        <div class="trade-banner">
          <div class="trade-banner-card"><div class="metric-label">Portfolio Equity</div><div class="metric-value">${portfolio["equity"]:.2f}</div></div>
          <div class="trade-banner-card"><div class="metric-label">Total PnL</div><div class="metric-value {pnl_class}">${portfolio["total_pnl"]:+.2f}</div></div>
          <div class="trade-banner-card"><div class="metric-label">Daily PnL</div><div class="metric-value {daily_pnl_class}">${daily_pnl:+.2f}</div></div>
          <div class="trade-banner-card"><div class="metric-label">BTC Allocation</div><div class="metric-value">{portfolio["exposure_percent"]:.2f}%</div></div>
          <div class="trade-banner-card"><div class="metric-label">Active Strategy</div><div class="metric-value">{escape(str(latest_cycle.get('strategy_name', 'n/a')).replace('Strategy', ''))}</div></div>
          <div class="trade-banner-card"><div class="metric-label">Latest Trade</div><div class="metric-value">{escape(latest_trade_summary)}</div><div class="metric-label" style="margin-top:.35rem;">{escape(latest_trade_timestamp)}</div></div>
        </div>
      </section>
      <section class="trade-layout">
      <div class="trade-main">
        {main_sections}
      </div>
      <aside class="trade-side">
        <section class="trade-section" style="display:{'block' if view_mode == 'paper' else 'none'};">
          <div class="label">Portfolio State</div>
          <div class="value">Current Holdings</div>
          <div class="market-mini">
            <div class="mini-row"><div class="mini-label">Cash</div><div class="mini-value">${portfolio["cash"]:.2f} USD</div></div>
            <div class="mini-row"><div class="mini-label">BTC Held</div><div class="mini-value">{portfolio["btc_units"]:.6f} BTC</div></div>
            <div class="mini-row"><div class="mini-label">DCA BTC</div><div class="mini-value">{portfolio["dca_btc_units"]:.6f} BTC</div></div>
            <div class="mini-row"><div class="mini-label">Swing BTC</div><div class="mini-value">{portfolio["swing_btc_units"]:.6f} BTC</div></div>
            <div class="mini-row"><div class="mini-label">Avg Entry</div><div class="mini-value">${portfolio["avg_entry"]:.2f}</div></div>
            <div class="mini-row"><div class="mini-label">Last Mark</div><div class="mini-value">${portfolio["last_mark"]:.2f}</div></div>
            <div class="mini-row"><div class="mini-label">Unrealized PnL</div><div class="mini-value">${portfolio["unrealized_pnl"]:+.2f} USD</div></div>
            <div class="mini-row"><div class="mini-label">Realized PnL</div><div class="mini-value">${portfolio["realized_pnl"]:+.2f} USD</div></div>
            <div class="mini-row"><div class="mini-label">Final Cost</div><div class="mini-value">${portfolio["total_execution_cost_usd"]:.2f} USD</div></div>
          </div>
        </section>
        {backtest_portfolio_side}
        <section class="trade-section" style="display:{'block' if view_mode == 'backtest' else 'none'};">
          <div class="label">Backtest History</div>
          <div class="history-stack">{backtest_history_nav}</div>
        </section>
        {simulation_side}
        <section class="trade-section" style="display:{'block' if view_mode == 'paper' else 'none'};">
          <div class="label">Active Swing Positions</div>
          <table>
            <thead>
              <tr><th>Opened</th><th>Entry</th><th>Stop</th><th>BTC</th></tr>
            </thead>
            <tbody>{swing_rows}</tbody>
          </table>
        </section>
        <section class="trade-section">
          <div class="label">System Mode</div>
          <div class="value">{system_mode_value}</div>
          <p>{system_mode_text}</p>
        </section>
      </aside>
      </section>
    </section>
    """
    script = f"""
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <script>
      const tradeChartPayload = {paper_chart_payload};
      const tradeMarkersPayload = {paper_trades_payload};
      const backtestChartsPayload = {backtest_payload or "{}"};
      const simulationChartsPayload = {simulation_payload or "{}"};
      const decisionHeadline = document.getElementById("decision-headline");
      const decisionTimestamp = document.getElementById("decision-timestamp");
      const decisionReasons = document.getElementById("decision-reasons");
      const decisionInterpretation = document.getElementById("decision-interpretation");
      const decisionRows = Array.from(document.querySelectorAll(".decision-row"));
      const expandButton = document.getElementById("decision-log-expand");
      const buyFilterButton = document.getElementById("decision-filter-buy");
      const sellFilterButton = document.getElementById("decision-filter-sell");
      const allFilterButton = document.getElementById("decision-filter-all");
      const backtestDecisionHeadline = document.getElementById("backtest-decision-headline");
      const backtestDecisionTimestamp = document.getElementById("backtest-decision-timestamp");
      const backtestDecisionReasons = document.getElementById("backtest-decision-reasons");
      const backtestDecisionInterpretation = document.getElementById("backtest-decision-interpretation");
      const backtestDecisionRows = Array.from(document.querySelectorAll(".backtest-decision-row"));
      const backtestExpandButton = document.getElementById("backtest-decision-expand");
      const backtestBuyFilterButton = document.getElementById("backtest-decision-filter-buy");
      const backtestSellFilterButton = document.getElementById("backtest-decision-filter-sell");
      const backtestAllFilterButton = document.getElementById("backtest-decision-filter-all");
      let decisionFilter = "BUY";
      let backtestDecisionFilter = "BUY";
      let visibleDecisionCount = 10;
      let visibleBacktestDecisionCount = 10;

      function setFilterButtons() {{
        if (buyFilterButton) {{
          buyFilterButton.classList.toggle("active", decisionFilter === "BUY");
        }}
        if (sellFilterButton) {{
          sellFilterButton.classList.toggle("active", decisionFilter === "SELL");
        }}
        if (allFilterButton) {{
          allFilterButton.classList.toggle("active", decisionFilter === "ALL");
        }}
      }}

      function filteredDecisionRows() {{
        if (decisionFilter === "ALL") {{
          return decisionRows;
        }}
        return decisionRows.filter((row) => {{
          const decisionCell = row.querySelector(".decision-cell");
          return (decisionCell?.textContent || "").trim().toUpperCase() === decisionFilter;
        }});
      }}

      function refreshDecisionTable() {{
        const matchingRows = filteredDecisionRows();
        decisionRows.forEach((row) => {{
          row.classList.add("decision-row-hidden");
        }});
        matchingRows.slice(0, visibleDecisionCount).forEach((row) => {{
          row.classList.remove("decision-row-hidden");
        }});

        if (expandButton) {{
          const hiddenCount = Math.max(matchingRows.length - visibleDecisionCount, 0);
          expandButton.style.display = hiddenCount > 0 ? "inline-flex" : "none";
          expandButton.textContent = hiddenCount > 10 ? "Show 10 more" : "Show remaining";
        }}

        const selectedVisible = decisionRows.find((row) => row.classList.contains("decision-row-active") && !row.classList.contains("decision-row-hidden"));
        if (!selectedVisible) {{
          const firstVisible = matchingRows.find((row) => !row.classList.contains("decision-row-hidden"));
          if (firstVisible) {{
            applyDecision(firstVisible);
          }}
        }}
      }}

      function applyDecision(row) {{
        if (!row) return;
        const payload = row.dataset.breakdown;
        if (!payload) return;
        const breakdown = JSON.parse(payload);
        decisionHeadline.textContent = breakdown.headline || "Decision";
        if (decisionTimestamp) {{
          decisionTimestamp.textContent = breakdown.timestamp || "";
        }}
        decisionReasons.innerHTML = "";
        (breakdown.reason_lines || []).forEach((line) => {{
          const item = document.createElement("li");
          item.textContent = line;
          decisionReasons.appendChild(item);
        }});
        decisionInterpretation.innerHTML = `<strong>Interpretation:</strong> ${{breakdown.interpretation || ""}}`;
        decisionRows.forEach((candidate) => candidate.classList.remove("decision-row-active"));
        row.classList.add("decision-row-active");
      }}

      decisionRows.forEach((row) => {{
        row.addEventListener("click", () => applyDecision(row));
      }});

      if (decisionRows.length > 0) {{
        applyDecision(decisionRows[0]);
      }}

      if (expandButton) {{
        expandButton.addEventListener("click", () => {{
          visibleDecisionCount += 10;
          refreshDecisionTable();
        }});
      }}

      if (buyFilterButton) {{
        buyFilterButton.addEventListener("click", () => {{
          decisionFilter = "BUY";
          visibleDecisionCount = 10;
          setFilterButtons();
          refreshDecisionTable();
        }});
      }}

      if (sellFilterButton) {{
        sellFilterButton.addEventListener("click", () => {{
          decisionFilter = "SELL";
          visibleDecisionCount = 10;
          setFilterButtons();
          refreshDecisionTable();
        }});
      }}

      if (allFilterButton) {{
        allFilterButton.addEventListener("click", () => {{
          decisionFilter = "ALL";
          visibleDecisionCount = 10;
          setFilterButtons();
          refreshDecisionTable();
        }});
      }}

      setFilterButtons();
      refreshDecisionTable();

      function setBacktestFilterButtons() {{
        if (backtestBuyFilterButton) {{
          backtestBuyFilterButton.classList.toggle("active", backtestDecisionFilter === "BUY");
        }}
        if (backtestSellFilterButton) {{
          backtestSellFilterButton.classList.toggle("active", backtestDecisionFilter === "SELL");
        }}
        if (backtestAllFilterButton) {{
          backtestAllFilterButton.classList.toggle("active", backtestDecisionFilter === "ALL");
        }}
      }}

      function filteredBacktestDecisionRows() {{
        if (backtestDecisionFilter === "ALL") {{
          return backtestDecisionRows;
        }}
        return backtestDecisionRows.filter((row) => {{
          const decisionCell = row.querySelector(".decision-cell");
          return (decisionCell?.textContent || "").trim().toUpperCase() === backtestDecisionFilter;
        }});
      }}

      function applyBacktestDecision(row) {{
        if (!row || !backtestDecisionHeadline) return;
        const payload = row.dataset.breakdown;
        if (!payload) return;
        const breakdown = JSON.parse(payload);
        backtestDecisionHeadline.textContent = breakdown.headline || "Decision";
        if (backtestDecisionTimestamp) {{
          backtestDecisionTimestamp.textContent = breakdown.timestamp || "";
        }}
        if (backtestDecisionReasons) {{
          backtestDecisionReasons.innerHTML = "";
          (breakdown.reason_lines || []).forEach((line) => {{
            const item = document.createElement("li");
            item.textContent = line;
            backtestDecisionReasons.appendChild(item);
          }});
        }}
        if (backtestDecisionInterpretation) {{
          backtestDecisionInterpretation.innerHTML = `<strong>Interpretation:</strong> ${{breakdown.interpretation || ""}}`;
        }}
        backtestDecisionRows.forEach((candidate) => candidate.classList.remove("decision-row-active"));
        row.classList.add("decision-row-active");
      }}

      function refreshBacktestDecisionTable() {{
        if (!backtestDecisionRows.length) return;
        const matchingRows = filteredBacktestDecisionRows();
        backtestDecisionRows.forEach((row) => {{
          row.classList.add("decision-row-hidden");
        }});
        matchingRows.slice(0, visibleBacktestDecisionCount).forEach((row) => {{
          row.classList.remove("decision-row-hidden");
        }});
        if (backtestExpandButton) {{
          const hiddenCount = Math.max(matchingRows.length - visibleBacktestDecisionCount, 0);
          backtestExpandButton.style.display = hiddenCount > 0 ? "inline-flex" : "none";
          backtestExpandButton.textContent = hiddenCount > 10 ? "Show 10 more" : "Show remaining";
        }}
        const selectedVisible = backtestDecisionRows.find((row) => row.classList.contains("decision-row-active") && !row.classList.contains("decision-row-hidden"));
        if (!selectedVisible) {{
          const firstVisible = matchingRows.find((row) => !row.classList.contains("decision-row-hidden"));
          if (firstVisible) {{
            applyBacktestDecision(firstVisible);
          }}
        }}
      }}

      backtestDecisionRows.forEach((row) => {{
        row.addEventListener("click", () => applyBacktestDecision(row));
      }});
      if (backtestExpandButton) {{
        backtestExpandButton.addEventListener("click", () => {{
          visibleBacktestDecisionCount += 10;
          refreshBacktestDecisionTable();
        }});
      }}
      if (backtestBuyFilterButton) {{
        backtestBuyFilterButton.addEventListener("click", () => {{
          backtestDecisionFilter = "BUY";
          visibleBacktestDecisionCount = 10;
          setBacktestFilterButtons();
          refreshBacktestDecisionTable();
        }});
      }}
      if (backtestSellFilterButton) {{
        backtestSellFilterButton.addEventListener("click", () => {{
          backtestDecisionFilter = "SELL";
          visibleBacktestDecisionCount = 10;
          setBacktestFilterButtons();
          refreshBacktestDecisionTable();
        }});
      }}
      if (backtestAllFilterButton) {{
        backtestAllFilterButton.addEventListener("click", () => {{
          backtestDecisionFilter = "ALL";
          visibleBacktestDecisionCount = 10;
          setBacktestFilterButtons();
          refreshBacktestDecisionTable();
        }});
      }}
      setBacktestFilterButtons();
      refreshBacktestDecisionTable();

      if (window.Plotly && document.getElementById("tradePaperChart") && tradeChartPayload.length) {{
        const chartStart = new Date(tradeChartPayload[0].timestamp).getTime();
        const chartEnd = new Date(tradeChartPayload[tradeChartPayload.length - 1].timestamp).getTime();
        const visibleTradeMarkers = tradeMarkersPayload.filter((trade) => {{
          const ts = new Date(String(trade.timestamp)).getTime();
          return Number.isFinite(ts) && ts >= chartStart && ts <= chartEnd;
        }});
        const closes = tradeChartPayload.map((point) => Number(point.close));
        const lows = tradeChartPayload.map((point) => Number(point.low));
        const highs = tradeChartPayload.map((point) => Number(point.high));
        const x = tradeChartPayload.map((point) => point.timestamp);
        const latestTrade = visibleTradeMarkers.length ? visibleTradeMarkers[visibleTradeMarkers.length - 1] : null;
        const atr = {float((latest_cycle.get('indicator_snapshot') or {}).get('atr', 0.0)):.6f};
        const lineTrace = {{
          type: "candlestick",
          x,
          open: tradeChartPayload.map((point) => Number(point.open)),
          high: highs,
          low: lows,
          close: closes,
          increasing: {{ line: {{ color: "#16c784", width: 1.1 }}, fillcolor: "#16c784" }},
          decreasing: {{ line: {{ color: "#ea3943", width: 1.1 }}, fillcolor: "#ea3943" }},
        }};
        const buyMarkers = visibleTradeMarkers.filter((trade) => String(trade.side).toLowerCase() === "buy");
        const sellMarkers = visibleTradeMarkers.filter((trade) => String(trade.side).toLowerCase() === "sell");
        const traces = [
          lineTrace,
          {{
            type: "scatter",
            mode: "markers",
            x: buyMarkers.map((trade) => trade.timestamp),
            y: buyMarkers.map((trade) => Number(trade.price)),
            marker: {{ color: "#22c55e", size: 9, line: {{ color: "#052e16", width: 1 }} }},
            name: "Buys",
            hovertemplate: "BUY<br>%{{x|%b %d, %-I:%M %p}}<br>%{{y:$,.2f}}<extra></extra>",
          }},
          {{
            type: "scatter",
            mode: "markers",
            x: sellMarkers.map((trade) => trade.timestamp),
            y: sellMarkers.map((trade) => Number(trade.price)),
            marker: {{ color: "#ef4444", size: 9, line: {{ color: "#450a0a", width: 1 }} }},
            name: "Sells",
            hovertemplate: "SELL<br>%{{x|%b %d, %-I:%M %p}}<br>%{{y:$,.2f}}<extra></extra>",
          }},
        ];
        if (latestTrade && atr > 0) {{
          const latestPrice = Number(latestTrade.price);
          traces.push(
            {{
              type: "scatter",
              mode: "lines",
              x,
              y: x.map(() => latestPrice + atr),
              line: {{ color: "rgba(59,130,246,0.40)", width: 1, dash: "dot" }},
              name: "ATR Upper",
              hoverinfo: "skip",
            }},
            {{
              type: "scatter",
              mode: "lines",
              x,
              y: x.map(() => latestPrice - atr),
              line: {{ color: "rgba(59,130,246,0.40)", width: 1, dash: "dot" }},
              name: "ATR Lower",
              hoverinfo: "skip",
            }}
          );
        }}
        Plotly.react("tradePaperChart", traces, {{
          paper_bgcolor: "rgba(13,21,32,1)",
          plot_bgcolor: "rgba(13,21,32,1)",
          margin: {{ t: 20, r: 24, b: 36, l: 48 }},
          showlegend: false,
          xaxis: {{ type: "date", showgrid: false, tickfont: {{ color: "rgba(148,163,184,0.8)" }} }},
          yaxis: {{ showgrid: true, gridcolor: "rgba(255,255,255,0.06)", tickformat: "$,.0f", tickfont: {{ color: "rgba(203,213,225,0.82)" }} }},
        }}, {{ responsive: true, displayModeBar: false }});
      }}

      if (window.Plotly && document.getElementById("backtestEquityChart") && backtestChartsPayload.equity_curve) {{
        Plotly.react("backtestEquityChart", [
          {{
            type: "scatter",
            mode: "lines",
            x: backtestChartsPayload.equity_curve.map((point) => point.timestamp),
            y: backtestChartsPayload.equity_curve.map((point) => point.equity_usd),
            name: "Strategy",
            line: {{ color: "#f59e0b", width: 3 }},
          }},
          {{
            type: "scatter",
            mode: "lines",
            x: backtestChartsPayload.benchmark_curve.map((point) => point.timestamp),
            y: backtestChartsPayload.benchmark_curve.map((point) => point.equity_usd),
            name: "Buy & Hold",
            line: {{ color: "#60a5fa", width: 2, dash: "dot" }},
          }},
        ], {{
          paper_bgcolor: "rgba(13,21,32,1)",
          plot_bgcolor: "rgba(13,21,32,1)",
          margin: {{ t: 20, r: 24, b: 36, l: 48 }},
          showlegend: true,
          legend: {{ font: {{ color: "#e2e8f0" }} }},
          xaxis: {{ type: "date", showgrid: false, tickfont: {{ color: "rgba(148,163,184,0.8)" }} }},
          yaxis: {{ showgrid: true, gridcolor: "rgba(255,255,255,0.06)", tickformat: "$,.0f", tickfont: {{ color: "rgba(203,213,225,0.82)" }} }},
        }}, {{ responsive: true, displayModeBar: false }});
        Plotly.react("backtestDrawdownChart", [
          {{
            type: "scatter",
            mode: "lines",
            x: backtestChartsPayload.drawdowns.map((point) => point.timestamp),
            y: backtestChartsPayload.drawdowns.map((point) => point.drawdown_percent),
            fill: "tozeroy",
            line: {{ color: "#ef4444", width: 2 }},
            fillcolor: "rgba(239,68,68,0.18)",
            name: "Drawdown",
          }},
        ], {{
          paper_bgcolor: "rgba(13,21,32,1)",
          plot_bgcolor: "rgba(13,21,32,1)",
          margin: {{ t: 20, r: 24, b: 36, l: 48 }},
          showlegend: false,
          xaxis: {{ type: "date", showgrid: false, tickfont: {{ color: "rgba(148,163,184,0.8)" }} }},
          yaxis: {{ showgrid: true, gridcolor: "rgba(255,255,255,0.06)", ticksuffix: "%", tickfont: {{ color: "rgba(203,213,225,0.82)" }} }},
        }}, {{ responsive: true, displayModeBar: false }});
      }}

      if (window.Plotly && document.getElementById("simulationEquityChart") && simulationChartsPayload.equity_curve) {{
        Plotly.react("simulationEquityChart", [
          {{
            type: "scatter",
            mode: "lines",
            x: simulationChartsPayload.equity_curve.map((point) => point.timestamp),
            y: simulationChartsPayload.equity_curve.map((point) => point.equity_usd),
            name: "Best Candidate",
            line: {{ color: "#16a34a", width: 3 }},
          }},
          {{
            type: "scatter",
            mode: "lines",
            x: simulationChartsPayload.benchmark_curve.map((point) => point.timestamp),
            y: simulationChartsPayload.benchmark_curve.map((point) => point.equity_usd),
            name: "Buy & Hold",
            line: {{ color: "#60a5fa", width: 2, dash: "dot" }},
          }},
        ], {{
          paper_bgcolor: "rgba(13,21,32,1)",
          plot_bgcolor: "rgba(13,21,32,1)",
          margin: {{ t: 20, r: 24, b: 36, l: 48 }},
          showlegend: true,
          legend: {{ font: {{ color: "#e2e8f0" }} }},
          xaxis: {{ type: "date", showgrid: false, tickfont: {{ color: "rgba(148,163,184,0.8)" }} }},
          yaxis: {{ showgrid: true, gridcolor: "rgba(255,255,255,0.06)", tickformat: "$,.0f", tickfont: {{ color: "rgba(203,213,225,0.82)" }} }},
        }}, {{ responsive: true, displayModeBar: false }});
        Plotly.react("simulationDrawdownChart", [
          {{
            type: "scatter",
            mode: "lines",
            x: simulationChartsPayload.drawdowns.map((point) => point.timestamp),
            y: simulationChartsPayload.drawdowns.map((point) => point.drawdown_percent),
            fill: "tozeroy",
            line: {{ color: "#ef4444", width: 2 }},
            fillcolor: "rgba(239,68,68,0.18)",
            name: "Drawdown",
          }},
        ], {{
          paper_bgcolor: "rgba(13,21,32,1)",
          plot_bgcolor: "rgba(13,21,32,1)",
          margin: {{ t: 20, r: 24, b: 36, l: 48 }},
          showlegend: false,
          xaxis: {{ type: "date", showgrid: false, tickfont: {{ color: "rgba(148,163,184,0.8)" }} }},
          yaxis: {{ showgrid: true, gridcolor: "rgba(255,255,255,0.06)", ticksuffix: "%", tickfont: {{ color: "rgba(203,213,225,0.82)" }} }},
        }}, {{ responsive: true, displayModeBar: false }});
      }}
    </script>
    """
    return _base_html("Trades | Adaptive BTC Trading Agent", "trades", body, script)
