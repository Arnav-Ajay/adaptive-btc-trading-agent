"""Weekly HTML report assembly from existing runtime artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config.schema import AppConfig
from app.scheduler.healthcheck import is_state_fresh


@dataclass(slots=True)
class WeeklyReport:
    """Container for the generated weekly email payload."""

    subject: str
    html: str
    report_key: str
    window_start: datetime
    window_end: datetime


def _timezone(config: AppConfig) -> ZoneInfo:
    """Resolve the report timezone from environment configuration."""
    timezone_name = config.env.get("REPORT_TIMEZONE", "UTC")
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def weekly_report_key(*, now: datetime, config: AppConfig) -> str:
    """Return the ISO year/week key for the scheduled report window."""
    local_now = now.astimezone(_timezone(config))
    iso_year, iso_week, _ = local_now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def should_send_weekly_report(
    *,
    now: datetime,
    config: AppConfig,
    last_sent_key: str | None,
) -> tuple[bool, str]:
    """Return whether the current local time falls within the report send window."""
    report_key = weekly_report_key(now=now, config=config)
    local_now = now.astimezone(_timezone(config))
    should_send = local_now.weekday() == 0 and local_now.hour == 9 and report_key != last_sent_key
    return should_send, report_key


def build_weekly_report(config: AppConfig, *, now: datetime | None = None) -> WeeklyReport:
    """Build the weekly HTML report from current persisted artifacts only."""
    current = (now or datetime.now(UTC)).astimezone(UTC)
    tz = _timezone(config)
    local_now = current.astimezone(tz)
    window_end = current
    window_start = current - timedelta(days=7)

    snapshot_payload = _load_json(Path(config.execution.paper_snapshot_path)) or {}
    snapshot = _dict(snapshot_payload.get("snapshot"))
    broker_state = _load_json(Path(config.execution.paper_state_path)) or {}
    trades = _load_jsonl_records(Path(config.execution.paper_trade_log_path))
    cycles = _load_jsonl_records(Path(config.execution.paper_cycle_log_path))
    weekly_trades = _filter_records(trades, "timestamp", window_start, window_end)
    weekly_cycles = _filter_records(cycles, "recorded_at", window_start, window_end)
    weekly_trades = _attach_trade_owners(weekly_trades=weekly_trades, weekly_cycles=weekly_cycles)
    ingestion_state = _load_json(Path(config.ingestion.state_path)) or {}
    gap_audit = _load_json(Path(config.data.data_lake_path) / "state" / "ingestion" / "ingestion_gap_audit.json") or {}

    current_equity = _float(snapshot.get("equity_usd"))
    starting_equity = current_equity
    if weekly_cycles:
        starting_equity = _float(_dict(weekly_cycles[0].get("snapshot")).get("equity_usd"), default=current_equity)
    weekly_equity_change = current_equity - starting_equity

    trading_activity = {
        "trade_count": len(weekly_trades),
        "buy_count": sum(1 for trade in weekly_trades if str(trade.get("side", "")).lower() == "buy"),
        "sell_count": sum(1 for trade in weekly_trades if str(trade.get("side", "")).lower() == "sell"),
        "gross_traded_usd": sum(_float(trade.get("size_usd")) for trade in weekly_trades),
        "fees_usd": sum(_float(trade.get("fee_usd")) for trade in weekly_trades),
        "spread_cost_usd": sum(_float(trade.get("spread_cost_usd")) for trade in weekly_trades),
        "slippage_cost_usd": sum(_float(trade.get("slippage_cost_usd")) for trade in weekly_trades),
        "realized_pnl_usd": sum(_float(trade.get("realized_pnl_usd")) for trade in weekly_trades),
    }

    strategy_rows = _cycle_strategy_breakdown(weekly_cycles=weekly_cycles)
    trade_breakdown_rows = _trade_strategy_breakdown(weekly_trades=weekly_trades)
    largest_trades = sorted(weekly_trades, key=lambda trade: _float(trade.get("size_usd")), reverse=True)[:3]
    realized_trades = [trade for trade in weekly_trades if trade.get("realized_pnl_usd") not in {None, ""}]
    top_winner = max(realized_trades, key=lambda trade: _float(trade.get("realized_pnl_usd")), default=None)
    top_loser = min(realized_trades, key=lambda trade: _float(trade.get("realized_pnl_usd")), default=None)

    latest_cycle_at = _latest_timestamp(cycles, "recorded_at")
    ingestion_ok = is_state_fresh(
        last_successful_run_at=str(ingestion_state.get("last_successful_run_at") or ""),
        max_staleness_minutes=config.ingestion.health_max_staleness_minutes,
        now=current,
    )
    trading_ok = is_state_fresh(
        last_successful_run_at=latest_cycle_at,
        max_staleness_minutes=config.runtime.health_max_staleness_minutes,
        now=current,
    )

    config_rows = [
        ("Strategy Profile", config.trading.strategy_profile),
        ("DCA Drop %", f"{config.trading.dca_drop_percent:.2f}"),
        ("DCA Order Size", _money(config.trading.dca_order_size_usd)),
        ("Max BTC Allocation", f"{config.trading.max_btc_allocation_percent:.2f}%"),
        ("ATR Multiplier", f"{config.trading.atr_multiplier:.2f}"),
        ("Swing RSI Max", f"{config.trading.swing_entry_rsi_max:.2f}"),
        ("Swing Take Profit %", f"{config.trading.swing_take_profit_percent:.2f}%"),
        ("Max Drawdown %", f"{config.trading.max_drawdown_percent:.2f}%"),
        (
            "Fee / Spread / Slippage",
            f"{config.execution.fee_pct:.4f} / {config.execution.spread_pct:.4f} / {config.execution.slippage_pct:.4f}",
        ),
        ("LLM Enabled", str(bool(config.llm.enabled)).lower()),
        ("Paper Trading Enabled", str(bool(config.execution.paper_trading_enabled)).lower()),
    ]

    html = f"""
    <html>
      <body style="margin:0;padding:24px;background:#f4f6f8;font-family:Segoe UI,sans-serif;color:#132033;">
        <div style="max-width:900px;margin:0 auto;background:#ffffff;border:1px solid #d9e1ea;border-radius:16px;overflow:hidden;">
          <div style="background:#0f1724;color:#f5f9ff;padding:24px 28px;">
            <div style="font-size:28px;font-weight:800;">Adaptive BTC Trading Agent Weekly Report</div>
            <div style="margin-top:6px;font-size:14px;opacity:.8;">Window: {escape(window_start.astimezone(tz).strftime("%Y-%m-%d %H:%M"))} to {escape(local_now.strftime("%Y-%m-%d %H:%M"))} {escape(str(tz.key))}</div>
            <div style="margin-top:4px;font-size:14px;opacity:.8;">Generated: {escape(local_now.strftime("%Y-%m-%d %H:%M"))} {escape(str(tz.key))}</div>
          </div>
          <div style="padding:24px 28px;">
            <h2 style="margin:0 0 12px 0;">Portfolio Summary</h2>
            {_kv_table([
                ("Current Equity", _money(current_equity)),
                ("Weekly Equity Change", _signed_money(weekly_equity_change)),
                ("Cash", _money(_float(snapshot.get("cash_usd")))),
                ("BTC Holdings", f"{_float(snapshot.get('btc_units')):.6f} BTC"),
                ("Avg Entry Price", _money(_float(snapshot.get("avg_entry_price")))),
                ("Current Mark Price", _money(_float(snapshot.get("last_mark_price")))),
                ("Current Drawdown", f"{_float(snapshot.get('drawdown_percent')):.2f}%"),
                ("Realized PnL", _money(_float(snapshot.get("realized_pnl_usd")))),
                (
                    "Total Fees / Spread / Slippage",
                    f"{_money(_float(snapshot.get('total_fees_usd')))} / {_money(_float(snapshot.get('total_spread_cost_usd')))} / {_money(_float(snapshot.get('total_slippage_cost_usd')))}",
                ),
            ])}
            <h2 style="margin:0 0 12px 0;">Trading Activity</h2>
            {_kv_table([
                ("Trades This Week", str(trading_activity['trade_count'])),
                ("Buys / Sells", f"{trading_activity['buy_count']} / {trading_activity['sell_count']}"),
                ("Gross Traded USD", _money(trading_activity["gross_traded_usd"])),
                ("Weekly Fees", _money(trading_activity["fees_usd"])),
                ("Weekly Spread Cost", _money(trading_activity["spread_cost_usd"])),
                ("Weekly Slippage Cost", _money(trading_activity["slippage_cost_usd"])),
                ("Weekly Realized PnL", _signed_money(trading_activity["realized_pnl_usd"])),
            ])}
            <h2 style="margin:0 0 12px 0;">Strategy Breakdown</h2>
            {_cycle_strategy_table(strategy_rows)}
            <h2 style="margin:24px 0 12px 0;">Trade Breakdown</h2>
            {_trade_strategy_table(trade_breakdown_rows)}
            <h2 style="margin:24px 0 12px 0;">Top Trades</h2>
            {_top_trades_table(largest_trades, top_winner, top_loser, tz)}
            <h2 style="margin:24px 0 12px 0;">Open Positions</h2>
            <p style="margin:0 0 8px 0;">DCA Base: {float(broker_state.get('dca_btc_units', 0.0)):.6f} BTC @ avg {_money(_float(broker_state.get('dca_avg_entry_price')))}</p>
            {_open_positions_table(_list(broker_state.get("open_swing_positions")), tz)}
            <h2 style="margin:24px 0 12px 0;">System Health</h2>
            {_kv_table([
                ("Last Ingestion Success", escape(str(ingestion_state.get("last_successful_run_at", "n/a")))),
                ("Last Ingested Candle", escape(str(ingestion_state.get("last_ingested_timestamp", "n/a")))),
                ("Last Trading Cycle", escape(latest_cycle_at or "n/a")),
                ("Source Gaps", str(int(gap_audit.get("source_gap_count", 0) or 0))),
                ("Lake Gaps", str(int(gap_audit.get("lake_gap_count", 0) or 0))),
                ("Ingestion Freshness", "OK" if ingestion_ok else "STALE"),
                ("Trading Freshness", "OK" if trading_ok else "STALE"),
            ])}
            <h2 style="margin:24px 0 12px 0;">Configuration Snapshot</h2>
            {_kv_table(config_rows)}
          </div>
        </div>
      </body>
    </html>
    """

    subject = f"Adaptive BTC Trading Agent Weekly Report | {window_start.astimezone(tz).strftime('%Y-%m-%d')} - {local_now.strftime('%Y-%m-%d')}"
    return WeeklyReport(
        subject=subject,
        html=html.strip(),
        report_key=weekly_report_key(now=current, config=config),
        window_start=window_start,
        window_end=window_end,
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _filter_records(
    records: list[dict[str, Any]],
    timestamp_field: str,
    window_start: datetime,
    window_end: datetime,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for record in records:
        timestamp_raw = record.get(timestamp_field)
        if not isinstance(timestamp_raw, str):
            continue
        try:
            timestamp = datetime.fromisoformat(timestamp_raw).astimezone(UTC)
        except ValueError:
            continue
        if window_start <= timestamp <= window_end:
            filtered.append(record)
    return filtered


def _latest_timestamp(records: list[dict[str, Any]], field: str) -> str | None:
    latest: datetime | None = None
    latest_value: str | None = None
    for record in records:
        raw_value = record.get(field)
        if not isinstance(raw_value, str):
            continue
        try:
            timestamp = datetime.fromisoformat(raw_value).astimezone(UTC)
        except ValueError:
            continue
        if latest is None or timestamp > latest:
            latest = timestamp
            latest_value = raw_value
    return latest_value


def _attach_trade_owners(
    *,
    weekly_trades: list[dict[str, Any]],
    weekly_cycles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach the cycle decision owner to each trade when a matching order_id exists."""
    owner_by_order_id: dict[str, str] = {}
    for cycle in weekly_cycles:
        decision_owner = str(cycle.get("strategy_name", "unknown"))
        for result in cycle.get("execution_results", []):
            if not isinstance(result, dict):
                continue
            order_id = str(result.get("order_id", "")).strip()
            if order_id:
                owner_by_order_id[order_id] = decision_owner
    enriched: list[dict[str, Any]] = []
    for trade in weekly_trades:
        payload = dict(trade)
        order_id = str(trade.get("order_id", "")).strip()
        payload["decision_owner_strategy"] = owner_by_order_id.get(order_id)
        payload["execution_strategy"] = str(trade.get("strategy_name", "unknown"))
        enriched.append(payload)
    return enriched


def _cycle_strategy_breakdown(*, weekly_cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate cycle-selected strategy usage from journal artifacts only."""
    cycle_counts: dict[str, int] = {}
    for cycle in weekly_cycles:
        strategy_name = str(cycle.get("strategy_name", "unknown"))
        cycle_counts[strategy_name] = cycle_counts.get(strategy_name, 0) + 1
    signal_counts: dict[str, int] = {}
    execution_counts: dict[str, int] = {}
    regime_samples: dict[str, list[str]] = {}
    for cycle in weekly_cycles:
        strategy_name = str(cycle.get("strategy_name", "unknown"))
        signal_counts[strategy_name] = signal_counts.get(strategy_name, 0) + int(cycle.get("signal_count", 0) or 0)
        execution_count = 0
        for result in cycle.get("execution_results", []):
            if isinstance(result, dict) and bool(result.get("accepted", False)):
                execution_count += 1
        execution_counts[strategy_name] = execution_counts.get(strategy_name, 0) + execution_count
        regime = str(cycle.get("regime", "n/a"))
        regime_samples.setdefault(strategy_name, []).append(regime)

    rows: list[dict[str, Any]] = []
    for strategy_name, cycle_count in cycle_counts.items():
        regimes = regime_samples.get(strategy_name, [])
        rows.append(
            {
                "strategy_name": strategy_name,
                "cycle_count": cycle_count,
                "signal_count": signal_counts.get(strategy_name, 0),
                "execution_count": execution_counts.get(strategy_name, 0),
                "common_regime": max(set(regimes), key=regimes.count) if regimes else "n/a",
            }
        )
    return sorted(rows, key=lambda row: int(row["cycle_count"]), reverse=True)


def _trade_strategy_breakdown(*, weekly_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate execution-source trade activity from the ledger only."""
    trade_rows: dict[str, dict[str, float | int | str]] = {}
    for trade in weekly_trades:
        strategy_name = str(trade.get("execution_strategy") or trade.get("strategy_name", "unknown"))
        current = trade_rows.setdefault(
            strategy_name,
            {
                "strategy_name": strategy_name,
                "trade_count": 0,
                "buy_count": 0,
                "sell_count": 0,
                "volume_usd": 0.0,
                "realized_pnl_usd": 0.0,
            },
        )
        current["trade_count"] = int(current["trade_count"]) + 1
        if str(trade.get("side", "")).lower() == "buy":
            current["buy_count"] = int(current["buy_count"]) + 1
        if str(trade.get("side", "")).lower() == "sell":
            current["sell_count"] = int(current["sell_count"]) + 1
        current["volume_usd"] = float(current["volume_usd"]) + _float(trade.get("size_usd"))
        current["realized_pnl_usd"] = float(current["realized_pnl_usd"]) + _float(trade.get("realized_pnl_usd"))
    return sorted(trade_rows.values(), key=lambda row: (int(row["trade_count"]), float(row["volume_usd"])), reverse=True)


def _kv_table(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f"<tr><td style=\"padding:8px 0;border-bottom:1px solid #eef2f7;\">{escape(label)}</td><td style=\"padding:8px 0;border-bottom:1px solid #eef2f7;font-weight:700;\">{value}</td></tr>"
        for label, value in rows
    )
    return f"<table style=\"width:100%;border-collapse:collapse;margin-bottom:24px;\">{body}</table>"


def _cycle_strategy_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p style=\"margin:0 0 24px 0;\">No strategy activity recorded this week.</p>"
    body = "".join(
        "<tr>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(row['strategy_name']))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{int(row['cycle_count'])}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{int(row['signal_count'])}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{int(row['execution_count'])}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(row['common_regime']))}</td>"
        "</tr>"
        for row in rows
    )
    return (
        "<table style=\"width:100%;border-collapse:collapse;margin-bottom:24px;border:1px solid #e5e7eb;\">"
        "<tr><th align=\"left\" style=\"padding:8px;\">Decision Owner</th><th align=\"left\" style=\"padding:8px;\">Cycles</th><th align=\"left\" style=\"padding:8px;\">Signals</th><th align=\"left\" style=\"padding:8px;\">Accepted Executions</th><th align=\"left\" style=\"padding:8px;\">Common Regime</th></tr>"
        f"{body}</table>"
    )


def _trade_strategy_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p style=\"margin:0 0 24px 0;\">No trade activity recorded this week.</p>"
    body = "".join(
        "<tr>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(row['strategy_name']))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{int(row['trade_count'])}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{int(row['buy_count'])} / {int(row['sell_count'])}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{_money(float(row['volume_usd']))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{_signed_money(float(row['realized_pnl_usd']))}</td>"
        "</tr>"
        for row in rows
    )
    return (
        "<table style=\"width:100%;border-collapse:collapse;margin-bottom:24px;border:1px solid #e5e7eb;\">"
        "<tr><th align=\"left\" style=\"padding:8px;\">Execution Source</th><th align=\"left\" style=\"padding:8px;\">Trades</th><th align=\"left\" style=\"padding:8px;\">Buys / Sells</th><th align=\"left\" style=\"padding:8px;\">Volume</th><th align=\"left\" style=\"padding:8px;\">Realized PnL</th></tr>"
        f"{body}</table>"
    )


def _top_trades_table(
    largest_trades: list[dict[str, Any]],
    top_winner: dict[str, Any] | None,
    top_loser: dict[str, Any] | None,
    tz: ZoneInfo,
) -> str:
    if not largest_trades and top_winner is None and top_loser is None:
        return "<p style=\"margin:0 0 24px 0;\">No trades recorded this week.</p>"
    largest_rows = "".join(
        "<tr>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(_display_timestamp(str(trade.get('timestamp', '')), tz))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(trade.get('side', '')).upper())}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(trade.get('decision_owner_strategy') or 'n/a'))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(trade.get('execution_strategy') or trade.get('strategy_name', '')))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{_money(_float(trade.get('size_usd')))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{_money(_float(trade.get('price')))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(trade.get('reason', '')))}</td>"
        "</tr>"
        for trade in largest_trades
    )
    callouts: list[str] = []
    if top_winner is not None:
        callouts.append(
            f"<p style=\"margin:8px 0 0 0;\">Top realized winner: <strong>{escape(str(top_winner.get('decision_owner_strategy') or 'n/a'))}</strong> → <strong>{escape(str(top_winner.get('execution_strategy') or top_winner.get('strategy_name', '')))}</strong> {escape(str(top_winner.get('side', '')).upper())} {_signed_money(_float(top_winner.get('realized_pnl_usd')))}</p>"
        )
    if top_loser is not None and top_loser is not top_winner:
        callouts.append(
            f"<p style=\"margin:8px 0 0 0;\">Top realized loser: <strong>{escape(str(top_loser.get('decision_owner_strategy') or 'n/a'))}</strong> → <strong>{escape(str(top_loser.get('execution_strategy') or top_loser.get('strategy_name', '')))}</strong> {escape(str(top_loser.get('side', '')).upper())} {_signed_money(_float(top_loser.get('realized_pnl_usd')))}</p>"
        )
    return (
        "<table style=\"width:100%;border-collapse:collapse;margin-bottom:8px;border:1px solid #e5e7eb;\">"
        "<tr><th align=\"left\" style=\"padding:8px;\">Time</th><th align=\"left\" style=\"padding:8px;\">Side</th><th align=\"left\" style=\"padding:8px;\">Decision Owner</th><th align=\"left\" style=\"padding:8px;\">Execution Source</th><th align=\"left\" style=\"padding:8px;\">Size USD</th><th align=\"left\" style=\"padding:8px;\">Price</th><th align=\"left\" style=\"padding:8px;\">Reason</th></tr>"
        f"{largest_rows}</table>{''.join(callouts)}"
    )


def _open_positions_table(positions: list[dict[str, Any]], tz: ZoneInfo) -> str:
    if not positions:
        return "<p style=\"margin:0 0 24px 0;\">Open Swing Positions: none</p>"
    body = "".join(
        "<tr>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(position.get('position_id', '')))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(position.get('symbol', '')))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{_money(_float(position.get('entry_price')))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{_money(_float(position.get('stop_loss')))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{_float(position.get('btc_units')):.6f}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{_money(_float(position.get('size_usd')))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(_display_timestamp(str(position.get('opened_at', '')), tz))}</td>"
        f"<td style=\"padding:8px;border-bottom:1px solid #eef2f7;\">{escape(str(position.get('origin_strategy') or position.get('strategy_name', '')))}</td>"
        "</tr>"
        for position in positions
    )
    return (
        "<table style=\"width:100%;border-collapse:collapse;margin-bottom:24px;border:1px solid #e5e7eb;\">"
        "<tr><th align=\"left\" style=\"padding:8px;\">Position ID</th><th align=\"left\" style=\"padding:8px;\">Symbol</th><th align=\"left\" style=\"padding:8px;\">Entry</th><th align=\"left\" style=\"padding:8px;\">Stop</th><th align=\"left\" style=\"padding:8px;\">BTC</th><th align=\"left\" style=\"padding:8px;\">Size USD</th><th align=\"left\" style=\"padding:8px;\">Opened</th><th align=\"left\" style=\"padding:8px;\">Strategy</th></tr>"
        f"{body}</table>"
    )


def _display_timestamp(raw_value: str, tz: ZoneInfo) -> str:
    try:
        return datetime.fromisoformat(raw_value).astimezone(tz).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return raw_value


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _signed_money(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"
