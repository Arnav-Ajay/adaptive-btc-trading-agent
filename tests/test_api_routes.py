"""Tests for the navigated FastAPI pages."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app


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
