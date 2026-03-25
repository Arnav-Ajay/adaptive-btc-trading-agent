"""Tests for the navigated FastAPI pages."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import _decision_breakdown, _format_trade_row, app


def test_bitcoin_page_renders_navigation() -> None:
    """Bitcoin page should render the new navigation and chart section."""
    client = TestClient(app)
    response = client.get("/bitcoin")
    assert response.status_code == 200
    assert "Market Context" in response.text
    assert 'href="/trades"' in response.text
    assert "Built by <strong>Arnav</strong> / <strong>Kaijo</strong>" in response.text
    assert "github.com/Arnav-Ajay" in response.text


def test_trades_page_renders_trade_section() -> None:
    """Trades page should render the portfolio and execution table layout."""
    client = TestClient(app)
    response = client.get("/trades?mode=paper")
    assert response.status_code == 200
    assert "Portfolio State" in response.text
    assert "Executed Buys and Sells" in response.text
    assert "Final Cost" in response.text
    assert "Built by <strong>Arnav</strong> / <strong>Kaijo</strong>" in response.text


def test_trades_page_can_render_backtest_summary() -> None:
    """Backtest subview should render controls and saved-run navigation without auto-running."""
    client = TestClient(app)
    response = client.get("/trades?mode=backtest")
    assert response.status_code == 200
    assert "Backtest Controls" in response.text
    assert "Backtest History" in response.text
    assert "Run Backtest" in response.text
    assert 'name="start"' in response.text
    assert 'name="end"' in response.text
    assert 'name="fee_pct"' in response.text
    assert 'name="spread_pct"' in response.text
    assert 'name="slippage_pct"' in response.text


def test_trades_page_can_run_backtest_summary() -> None:
    """Trades page should render a backtest summary when explicitly requested."""
    client = TestClient(app)
    response = client.get("/trades?mode=backtest&run_backtest=1")
    assert response.status_code == 200
    assert "Backtest Results" in response.text
    assert "Equity Curve" in response.text
    assert "Decision Breakdown" in response.text
    assert "Decision Log" in response.text
    assert "Final Portfolio Value" in response.text
    assert "Run Status" in response.text


def test_trades_page_can_render_simulation_subview() -> None:
    """Trades page should render the simulation placeholder subview."""
    client = TestClient(app)
    response = client.get("/trades?mode=simulation")
    assert response.status_code == 200
    assert "Simulation" in response.text
    assert "Coming Soon" in response.text


def test_trades_page_legacy_run_backtest_still_works() -> None:
    """Legacy backtest query param should still open the backtesting subview."""
    client = TestClient(app)
    response = client.get("/trades?run_backtest=1")
    assert response.status_code == 200
    assert "Backtest Results" in response.text


def test_trades_page_backtest_accepts_datetime_local_inputs() -> None:
    """Backtest form inputs from datetime-local should be normalized instead of causing a 500."""
    client = TestClient(app)
    response = client.get("/trades?mode=backtest&run_backtest=1&interval=30m&start=2026-01-01T13:10&end=2026-03-24T13:10")
    assert response.status_code == 200
    assert "Backtest Results" in response.text


def test_backtest_api_returns_summary() -> None:
    """Backtest API should return a replay summary payload."""
    client = TestClient(app)
    response = client.get("/api/backtest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["interval"] == "30m"
    assert "metrics" in payload
    assert "execution_costs" in payload


def test_backtest_api_accepts_execution_cost_overrides() -> None:
    """Backtest API should accept explicit execution-cost configuration."""
    client = TestClient(app)
    response = client.get(
        "/api/backtest?interval=30m&execution_cost_preset=custom&fee_pct=0.0020&spread_pct=0.0010&slippage_pct=0.0015"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_costs"]["preset"] == "custom"
    assert payload["execution_costs"]["fee_pct"] == 0.002
    assert payload["execution_costs"]["spread_pct"] == 0.001
    assert payload["execution_costs"]["slippage_pct"] == 0.0015


def test_decision_breakdown_prefers_executed_swing_over_dca_skip_trace() -> None:
    """Hybrid cycles should explain the accepted swing entry, not the skipped DCA branch."""
    cycle = {
        "signal_count": 1,
        "strategy_name": "HybridStrategy",
        "execution_results": [
            {
                "accepted": True,
                "price": 70849.2,
                "size_usd": 250.0,
                "reason": "momentum_atr_setup",
                "strategy_name": "SwingATRStrategy",
                "stop_loss": 70762.49,
            }
        ],
        "decision_trace": [
            "component:DCAStrategy",
            "skip:price_above_drop_threshold latest_buy_fill_price=70719.09",
            "threshold:required_price_at_or_below=68597.52",
            "observed:last_price=70849.20",
            "component:SwingATRStrategy",
            "decision:momentum_conditions_met stop_loss=70762.49",
            "signal:momentum_atr_setup size_usd=250.00",
        ],
    }
    breakdown = _decision_breakdown(cycle, cycle)
    assert breakdown["decision"] == "BUY"
    assert "ATR stop-loss set at $70762.49." in breakdown["reason_lines"]
    assert "swing layer inside the hybrid strategy" in breakdown["interpretation"].lower()
    assert "momentum setup" in breakdown["interpretation"].lower()


def test_decision_breakdown_backfills_old_execution_details_from_trace() -> None:
    """Older cycle rows without full execution payload should still show price and size."""
    cycle = {
        "recorded_at": "2026-03-25T04:32:10+00:00",
        "signal_count": 1,
        "strategy_name": "HybridStrategy",
        "indicator_snapshot": {"last_price": 70849.2},
        "execution_results": [
            {
                "accepted": True,
                "order_id": "paper-123",
                "reason": "momentum_atr_setup",
            }
        ],
        "decision_trace": [
            "component:SwingATRStrategy",
            "decision:momentum_conditions_met stop_loss=70762.49",
            "signal:momentum_atr_setup size_usd=250.00",
        ],
    }
    breakdown = _decision_breakdown(cycle, cycle)
    assert "Entry executed at $70849.20 for $250.00." in breakdown["reason_lines"]
    assert "ATR stop-loss set at $70762.49." in breakdown["reason_lines"]
    assert breakdown["timestamp"] == "2026-03-25T04:32:10+00:00"


def test_decision_breakdown_explains_dca_threshold_basis() -> None:
    """DCA skip explanations should say what the threshold is derived from."""
    cycle = {
        "signal_count": 0,
        "execution_results": [],
        "decision_trace": [
            "skip:price_above_drop_threshold latest_buy_fill_price=70719.09",
            "threshold:required_price_at_or_below=68597.52",
            "observed:last_price=71571.64",
        ],
    }
    breakdown = _decision_breakdown(cycle, cycle)
    assert breakdown["decision"] == "NO BUY"
    assert any("last buy at $70719.09" in line for line in breakdown["reason_lines"])
    assert any("3.00% drop trigger" in line for line in breakdown["reason_lines"])


def test_decision_breakdown_explains_initial_dca_buy_with_order_size() -> None:
    """Initial DCA buys should explain that there was no prior fill and show order size."""
    cycle = {
        "recorded_at": "2026-03-24T22:56:06+00:00",
        "indicator_snapshot": {"last_price": 70210.01},
        "signal_count": 1,
        "execution_results": [{"accepted": True, "order_id": "paper-1", "reason": "filled"}],
        "decision_trace": ["decision:no_prior_buy_fill", "signal:initial_dca_entry size_usd=100.00"],
    }
    breakdown = _decision_breakdown(cycle, cycle)
    assert breakdown["decision"] == "BUY"
    assert "No prior DCA buy fill existed in the ledger." in breakdown["reason_lines"]
    assert "DCA order size was $100.00." in breakdown["reason_lines"]
    assert "Entry executed at $70210.01 for $100.00." in breakdown["reason_lines"]


def test_decision_breakdown_explains_threshold_triggered_dca_buy() -> None:
    """Threshold-triggered DCA buys should explain the drop-threshold basis."""
    cycle = {
        "recorded_at": "2026-03-25T16:00:00+00:00",
        "indicator_snapshot": {"last_price": 68720.0},
        "signal_count": 1,
        "execution_results": [{"accepted": True, "order_id": "paper-2", "reason": "price_drop_dca_entry"}],
        "decision_trace": [
            "decision:price_below_drop_threshold threshold=68723.72",
            "skip:price_above_drop_threshold latest_buy_fill_price=70849.20",
            "threshold:required_price_at_or_below=68723.72",
            "observed:last_price=68720.00",
            "signal:price_drop_dca_entry size_usd=100.00",
        ],
    }
    breakdown = _decision_breakdown(cycle, cycle)
    assert breakdown["decision"] == "BUY"
    assert "Current price crossed below the configured DCA threshold." in breakdown["reason_lines"]
    assert any("last buy at $70849.20" in line for line in breakdown["reason_lines"])
    assert "Entry executed at $68720.00 for $100.00." in breakdown["reason_lines"]


def test_trade_row_uses_initial_buy_label_for_initial_dca_fill() -> None:
    """The first DCA entry should not be labeled as a dip buy."""
    row = _format_trade_row(
        {
            "timestamp": "2026-03-24T22:56:06+00:00",
            "side": "buy",
            "symbol": "BTC-USD",
            "size_usd": 100.0,
            "price": 70210.01,
            "btc_units": 0.001424,
            "strategy_name": "DCAStrategy",
            "reason": "initial_dca_entry",
        }
    )
    assert "Initial Buy" in row
    assert "Dip Buy" not in row
