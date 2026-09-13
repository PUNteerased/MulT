"""
Unit and integration tests for Deep-Sniper AI Web Dashboard & Health Monitoring.
"""
import pytest
from fastapi.testclient import TestClient
from dashboard.app import app
from dashboard.system_telemetry import get_system_telemetry

client = TestClient(app)

def test_system_telemetry_hardware():
    """Verify hardware and MT5 telemetry collection returns valid schema."""
    telemetry = get_system_telemetry()
    assert "vram_used_mb" in telemetry
    assert "vram_total_mb" in telemetry
    assert "vram_percent" in telemetry
    assert "vram_warning" in telemetry
    assert "cpu_percent" in telemetry
    assert "ram_percent" in telemetry
    assert "disk_free_gb" in telemetry
    assert "account" in telemetry

    # Value ranges
    assert isinstance(telemetry["vram_used_mb"], (int, float))
    assert telemetry["vram_total_mb"] >= 0
    assert 0.0 <= telemetry["ram_percent"] <= 100.0
    assert isinstance(telemetry["account"], dict)
    assert "balance" in telemetry["account"]
    assert "equity" in telemetry["account"]

def test_api_status_endpoint():
    """Verify /api/status endpoint response."""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "subsystems" in data
    assert "account" in data
    assert "hardware" in data
    assert "symbols" in data
    assert len(data["symbols"]) > 0

def test_api_telemetry_endpoint():
    """Verify /api/telemetry returns real-time hardware snapshot."""
    response = client.get("/api/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert "hardware" in data
    assert "account" in data
    assert "active_positions" in data["account"]

def test_api_kill_zones_endpoint():
    """Verify /api/kill-zones returns configured symbols and active zones."""
    response = client.get("/api/kill-zones")
    assert response.status_code == 200
    data = response.json()
    assert "EURUSD" in data
    assert "USDJPY" in data
    assert "XAUUSD" in data
    assert "BTCUSD" in data
    assert "bounds" in data["EURUSD"]

def test_api_trades_endpoint():
    """Verify /api/trades returns historical trades list."""
    response = client.get("/api/trades?limit=10")
    assert response.status_code == 200
    data = response.json()
    trades = data["trades"] if isinstance(data, dict) else data
    assert isinstance(trades, list)

def test_api_analytics_endpoint():
    """Verify /api/analytics returns win rate, profit factor, equity stats."""
    response = client.get("/api/analytics")
    assert response.status_code == 200
    data = response.json()
    assert "win_rate" in data
    assert "profit_factor" in data
    assert "total_trades" in data
    assert "current_equity" in data

def test_api_symbols_endpoint():
    """Verify /api/symbols endpoint returns symbols config."""
    response = client.get("/api/symbols")
    assert response.status_code == 200
    data = response.json()
    assert "EURUSD" in data

def test_api_portfolio_endpoint():
    """Verify /api/portfolio returns MT5 (or fallback) history with ICT timezone."""
    response = client.get("/api/portfolio?days=180")
    assert response.status_code == 200
    data = response.json()
    assert "initial_balance" in data
    assert "current_balance" in data
    assert "current_equity" in data
    assert "net_pnl" in data
    assert "net_pnl_pct" in data
    assert "equity_curve" in data
    assert "closed_trades" in data
    assert "analytics" in data
    assert data.get("timezone") == "Asia/Bangkok"
    assert isinstance(data["initial_balance"], (int, float))
    assert isinstance(data["current_balance"], (int, float))
    assert isinstance(data["closed_trades"], list)
    assert isinstance(data["equity_curve"], list)
    assert len(data["equity_curve"]) >= 1

def test_websocket_telemetry_stream():
    """Verify WebSocket client connection and initial data streaming."""
    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_json()
        assert "type" in data
        assert data["type"] == "telemetry"
        assert "hardware" in data
        assert "account" in data
        assert "vram_used_mb" in data["hardware"]
