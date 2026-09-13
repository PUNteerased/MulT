"""
Unit tests for Risk Guard and MT5 Order Router (dynamic equity risk).
"""
import pytest
from subsystems.risk_guard.guard_50 import RiskGuard50
from subsystems.execution.mt5_router import MT5OrderRouter
from core.bus.events import TriggerAlertEvent, OrderDirection, TradeTicketEvent
from core.memory.duckdb_manager import DuckDBManager

FULL = {
    "loss_streak": 0,
    "win_streak": 0,
    "multiplier": 1.0,
    "cooldown": False,
    "reason": "test",
}


def test_risk_guard_50_dollar_rule():
    # At equity $50, cap = $1 floor — 10 pips EURUSD = $1.00
    alert_valid = TriggerAlertEvent(
        alert_id="alt_1",
        symbol="EURUSD",
        direction=OrderDirection.BUY,
        entry_price=1.08500,
        wick_sl_price=1.08400,
        model_confidence=0.85,
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=alert_valid,
        current_spread_points=15,
        active_positions_count=0,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is True, reason
    assert ticket is not None
    assert ticket.risk_dollars == 1.00
    assert ticket.lot == 0.01
    assert ticket.be_trigger_price > ticket.entry_price
    assert ticket.risk_cap_usd == 1.0

    # 25 pips = $2.50 > $1 cap at eq 50
    alert_too_risky = TriggerAlertEvent(
        alert_id="alt_2",
        symbol="EURUSD",
        direction=OrderDirection.BUY,
        entry_price=1.08500,
        wick_sl_price=1.08250,
        model_confidence=0.85,
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=alert_too_risky,
        current_spread_points=15,
        active_positions_count=0,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is False
    assert ("Risk exceeds limit" in reason) or ("cannot fit under" in reason)

    # XAUUSD $1 move OK at floor
    gold_valid = TriggerAlertEvent(
        alert_id="alt_3",
        symbol="XAUUSD",
        direction=OrderDirection.BUY,
        entry_price=2640.00,
        wick_sl_price=2639.00,
        model_confidence=0.85,
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=gold_valid,
        current_spread_points=15,
        active_positions_count=0,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is True, reason
    assert ticket.risk_dollars == 1.00

    # XAUUSD $2 > $1 at eq 50
    gold_invalid = TriggerAlertEvent(
        alert_id="alt_4",
        symbol="XAUUSD",
        direction=OrderDirection.BUY,
        entry_price=2640.00,
        wick_sl_price=2638.00,
        model_confidence=0.85,
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=gold_invalid,
        current_spread_points=15,
        active_positions_count=0,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is False
    assert ("Risk exceeds limit" in reason) or ("cannot fit under" in reason)

    # Concurrency
    ok, reason, _ = RiskGuard50.evaluate_trigger(
        alert=alert_valid,
        current_spread_points=15,
        active_positions_count=1,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is False
    assert "Concurrency limit" in reason

    # High spread points
    ok, reason, _ = RiskGuard50.evaluate_trigger(
        alert=alert_valid,
        current_spread_points=80,
        active_positions_count=0,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is False
    assert "Spread too high" in reason

    # Spread-to-risk: 55 pts XAU ≈ $0.55 > 20% of $1 (= $0.20)
    gold_spread = TriggerAlertEvent(
        alert_id="alt_spread",
        symbol="XAUUSD",
        direction=OrderDirection.BUY,
        entry_price=2640.00,
        wick_sl_price=2639.50,
        model_confidence=0.85,
    )
    ok, reason, _ = RiskGuard50.evaluate_trigger(
        alert=gold_spread,
        current_spread_points=55,
        active_positions_count=0,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is False
    assert "Spread risk" in reason


@pytest.mark.asyncio
async def test_order_router_dry_run_lifecycle():
    DuckDBManager.reset_instance()
    db = DuckDBManager(":memory:")
    router = MT5OrderRouter(dry_run=True)

    ticket = TradeTicketEvent(
        ticket_id="TKT_TEST_1",
        symbol="EURUSD",
        direction=OrderDirection.BUY,
        lot=0.01,
        entry_price=1.08500,
        sl_price=1.08400,
        be_trigger_price=1.08650,
        be_lock_price=1.08520,
        tp_target_price=1.08800,
        risk_dollars=1.00,
        win_probability=0.82,
        risk_cap_usd=1.0,
    )

    order_id = await router.send_order(ticket)
    assert order_id == 999999
    assert router.active_position is not None
    assert router.active_position["be_applied"] is False

    await router.update_active_position_trailing(current_bid=1.08580, current_ask=1.08590)
    assert router.active_position["be_applied"] is False
    assert router.active_position["current_sl"] == 1.08400

    await router.update_active_position_trailing(current_bid=1.08660, current_ask=1.08670)
    assert router.active_position["be_applied"] is True
    assert router.active_position["current_sl"] == 1.08520

    await router.update_active_position_trailing(current_bid=1.08750, current_ask=1.08760)
    assert router.active_position["current_sl"] > 1.08520

    await router._handle_position_closed(exit_price=1.08780)
    assert router.active_position is None

    logs = db.get_trade_logs()
    assert len(logs) == 1
    assert logs.iloc[0]["ticket_id"] == "TKT_TEST_1"
    assert logs.iloc[0]["pnl"] > 0
    DuckDBManager.reset_instance()
