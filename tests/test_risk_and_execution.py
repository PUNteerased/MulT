"""
Unit tests for $50 Risk Guard and MT5 Order Router.
"""
import pytest
import asyncio
from subsystems.risk_guard.guard_50 import RiskGuard50
from subsystems.execution.mt5_router import MT5OrderRouter
from core.bus.events import TriggerAlertEvent, OrderDirection, TradeTicketEvent
from core.memory.duckdb_manager import DuckDBManager

def test_risk_guard_50_dollar_rule():
    # 1. EURUSD Valid Trade ($2.00 risk <= $2.50)
    alert_valid = TriggerAlertEvent(
        alert_id="alt_1", symbol="EURUSD", direction=OrderDirection.BUY,
        entry_price=1.08500, wick_sl_price=1.08300, model_confidence=0.85
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=alert_valid, current_spread_points=15, active_positions_count=0,
        account_equity=50.0, win_prob=0.80
    )
    assert ok is True
    assert ticket is not None
    assert ticket.risk_dollars == 2.00
    assert ticket.lot == 0.01
    assert ticket.be_trigger_price > ticket.entry_price

    # 2. EURUSD Invalid Trade ($4.00 risk > $2.50)
    alert_too_risky = TriggerAlertEvent(
        alert_id="alt_2", symbol="EURUSD", direction=OrderDirection.BUY,
        entry_price=1.08500, wick_sl_price=1.08100, model_confidence=0.85
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=alert_too_risky, current_spread_points=15, active_positions_count=0,
        account_equity=50.0, win_prob=0.80
    )
    assert ok is False
    assert "Risk exceeds limit" in reason

    # 3. XAUUSD Valid ($2.00 move = $2.00 risk)
    gold_valid = TriggerAlertEvent(
        alert_id="alt_3", symbol="XAUUSD", direction=OrderDirection.BUY,
        entry_price=2640.00, wick_sl_price=2638.00, model_confidence=0.85
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=gold_valid, current_spread_points=25, active_positions_count=0,
        account_equity=50.0, win_prob=0.80
    )
    assert ok is True
    assert ticket.risk_dollars == 2.00

    # 4. XAUUSD Invalid ($3.50 move = $3.50 risk > $2.50)
    gold_invalid = TriggerAlertEvent(
        alert_id="alt_4", symbol="XAUUSD", direction=OrderDirection.BUY,
        entry_price=2640.00, wick_sl_price=2636.50, model_confidence=0.85
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=gold_invalid, current_spread_points=25, active_positions_count=0,
        account_equity=50.0, win_prob=0.80
    )
    assert ok is False
    assert "Risk exceeds limit" in reason

    # 5. Concurrency Test
    ok, reason, _ = RiskGuard50.evaluate_trigger(
        alert=alert_valid, current_spread_points=15, active_positions_count=1,
        account_equity=50.0, win_prob=0.80
    )
    assert ok is False
    assert "Concurrency limit" in reason

    # 6. High Spread Test
    ok, reason, _ = RiskGuard50.evaluate_trigger(
        alert=alert_valid, current_spread_points=80, active_positions_count=0,
        account_equity=50.0, win_prob=0.80
    )
    assert ok is False
    assert "Spread too high" in reason

@pytest.mark.asyncio
async def test_order_router_dry_run_lifecycle():
    DuckDBManager.reset_instance()
    db = DuckDBManager(":memory:")
    router = MT5OrderRouter(dry_run=True)

    ticket = TradeTicketEvent(
        ticket_id="TKT_TEST_1", symbol="EURUSD", direction=OrderDirection.BUY,
        lot=0.01, entry_price=1.08500, sl_price=1.08300, be_trigger_price=1.08800,
        be_lock_price=1.08520, tp_target_price=1.09100, risk_dollars=2.00, win_probability=0.82
    )

    order_id = await router.send_order(ticket)
    assert order_id == 999999
    assert router.active_position is not None
    assert router.active_position["be_applied"] is False

    # Simulate price moving below BE trigger (no change)
    await router.update_active_position_trailing(current_bid=1.08700, current_ask=1.08710)
    assert router.active_position["be_applied"] is False
    assert router.active_position["current_sl"] == 1.08300

    # Simulate price reaching BE trigger (1.08800)
    await router.update_active_position_trailing(current_bid=1.08810, current_ask=1.08820)
    assert router.active_position["be_applied"] is True
    assert router.active_position["current_sl"] == 1.08520  # Locked +2 pips profit!

    # Simulate price climbing further (triggering trailing ratcheting)
    await router.update_active_position_trailing(current_bid=1.08900, current_ask=1.08910)
    assert router.active_position["current_sl"] > 1.08520

    # Simulate trade close
    await router._handle_position_closed(exit_price=1.08950)
    assert router.active_position is None

    # Verify trade is logged in DuckDB
    logs = db.get_trade_logs()
    assert len(logs) == 1
    assert logs.iloc[0]["ticket_id"] == "TKT_TEST_1"
    assert logs.iloc[0]["pnl"] > 0
    DuckDBManager.reset_instance()
