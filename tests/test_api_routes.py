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
    response = client.get("/trades")
    assert response.status_code == 200
    assert "Portfolio State" in response.text
    assert "Executed Buys and Sells" in response.text
    assert "Built by <strong>Arnav</strong> / <strong>Kaijo</strong>" in response.text


def test_trades_page_can_render_backtest_summary() -> None:
    """Trades page should render a backtest summary when requested."""
    client = TestClient(app)
    response = client.get("/trades?run_backtest=1")
    assert response.status_code == 200
    assert "Backtest Summary" in response.text


def test_backtest_api_returns_summary() -> None:
    """Backtest API should return a replay summary payload."""
    client = TestClient(app)
    response = client.get("/api/backtest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["interval"] == "30m"
    assert "metrics" in payload


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
