"""
Unit tests for dynamic equity risk + anti-martingale streak.
"""
from subsystems.risk_guard.guard_50 import RiskGuard50
from subsystems.risk_guard.streak import compute_streak_state
from core.bus.events import TriggerAlertEvent, OrderDirection
from config.settings import RISK_DOLLARS_FLOOR, RISK_DOLLARS_CEILING


FULL = {
    "loss_streak": 0,
    "win_streak": 0,
    "multiplier": 1.0,
    "cooldown": False,
    "reason": "test_full",
}


def test_compute_max_risk_floor_mid_ceiling():
    assert RiskGuard50.compute_max_risk_dollars(50.0) == RISK_DOLLARS_FLOOR
    assert abs(RiskGuard50.compute_max_risk_dollars(760.0) - 3.8) < 1e-6
    assert RiskGuard50.compute_max_risk_dollars(1200.0) == RISK_DOLLARS_CEILING
    assert abs(RiskGuard50.compute_max_risk_dollars(760.0, 0.5) - 1.9) < 1e-6


def test_streak_half_and_cooldown():
    half = compute_streak_state([(-1.0, 1e12), (-0.5, 1e12 - 1)])
    assert half["loss_streak"] == 2
    assert half["cooldown"] is False
    assert half["multiplier"] == 0.5

    cool = compute_streak_state([(-1.0, 1e12), (-1.0, 1e12), (-1.0, 1e12)])
    assert cool["loss_streak"] == 3
    assert cool["cooldown"] is True
    assert cool["multiplier"] == 0.0

    # time-cleared: old losses
    old = 1e12 - 5 * 3600
    cleared = compute_streak_state([(-1.0, old), (-1.0, old), (-1.0, old)], now=1e12)
    assert cleared["cooldown"] is False


def test_risk_guard_dynamic_cap_and_rejects():
    # At $50 equity, cap = $1 → 10 pips EURUSD OK
    alert_ok = TriggerAlertEvent(
        alert_id="a1",
        symbol="EURUSD",
        direction=OrderDirection.BUY,
        entry_price=1.08500,
        wick_sl_price=1.08400,
        model_confidence=0.85,
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=alert_ok,
        current_spread_points=15,
        active_positions_count=0,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is True, reason
    assert ticket is not None
    assert ticket.risk_dollars == 1.0
    assert ticket.risk_cap_usd == 1.0

    # 20 pips = $2 > $1 cap
    alert_big = TriggerAlertEvent(
        alert_id="a2",
        symbol="EURUSD",
        direction=OrderDirection.BUY,
        entry_price=1.08500,
        wick_sl_price=1.08300,
        model_confidence=0.85,
    )
    ok, reason, _ = RiskGuard50.evaluate_trigger(
        alert=alert_big,
        current_spread_points=15,
        active_positions_count=0,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is False
    assert ("Risk exceeds" in reason) or ("cannot fit under" in reason)

    # equity 760 → cap 3.8; $2 gold OK
    gold = TriggerAlertEvent(
        alert_id="a3",
        symbol="XAUUSD",
        direction=OrderDirection.BUY,
        entry_price=2640.00,
        wick_sl_price=2638.00,
        model_confidence=0.85,
    )
    ok, reason, ticket = RiskGuard50.evaluate_trigger(
        alert=gold,
        current_spread_points=25,
        active_positions_count=0,
        account_equity=760.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is True, reason
    assert ticket.risk_dollars == 2.0
    assert abs(ticket.risk_cap_usd - 3.8) < 1e-6


def test_half_risk_and_cooldown_gate():
    alert = TriggerAlertEvent(
        alert_id="a4",
        symbol="EURUSD",
        direction=OrderDirection.BUY,
        entry_price=1.08500,
        wick_sl_price=1.08300,  # $2 risk
        model_confidence=0.85,
    )
    # At eq 760, full cap 3.8 → $2 OK; half → 1.9 → $2 reject
    half_state = {
        "loss_streak": 2,
        "win_streak": 0,
        "multiplier": 0.5,
        "cooldown": False,
        "reason": "half",
    }
    ok, reason, _ = RiskGuard50.evaluate_trigger(
        alert=alert,
        current_spread_points=15,
        active_positions_count=0,
        account_equity=760.0,
        win_prob=0.80,
        streak_state=half_state,
    )
    assert ok is False
    assert ("Risk exceeds" in reason) or ("cannot fit under" in reason)

    cool_state = {
        "loss_streak": 3,
        "win_streak": 0,
        "multiplier": 0.0,
        "cooldown": True,
        "reason": "cool",
    }
    ok, reason, _ = RiskGuard50.evaluate_trigger(
        alert=alert,
        current_spread_points=15,
        active_positions_count=0,
        account_equity=760.0,
        win_prob=0.80,
        streak_state=cool_state,
    )
    assert ok is False
    assert "Cool-down" in reason


def test_spread_budget_uses_dynamic_cap():
    # eq 50 → cap $1 → 20% = $0.20; XAU 55 pts ≈ $0.55 → reject
    gold = TriggerAlertEvent(
        alert_id="a5",
        symbol="XAUUSD",
        direction=OrderDirection.BUY,
        entry_price=2640.00,
        wick_sl_price=2639.50,  # $0.50 risk under $1
        model_confidence=0.85,
    )
    ok, reason, _ = RiskGuard50.evaluate_trigger(
        alert=gold,
        current_spread_points=55,
        active_positions_count=0,
        account_equity=50.0,
        win_prob=0.80,
        streak_state=FULL,
    )
    assert ok is False
    assert "Spread risk" in reason
