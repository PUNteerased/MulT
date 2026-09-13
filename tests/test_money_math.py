"""Unit tests for unified USD risk / PnL conversion (0.01 lot FBS-style)."""
from core.risk.money import price_diff_to_usd, spread_points_to_usd, pnl_to_usd, assert_matches_mt5_spec
from subsystems.risk_guard.guard_50 import RiskGuard50


def test_eurusd_10_pips_is_one_dollar():
    # 10 pips = 0.0010 price → 0.01 lot → $1.00
    # Expected: |dP| * 100000 * 0.01 = 0.001 * 1000 = 1.0
    assert_matches_mt5_spec("EURUSD", 1.10000, 1.09900, 0.01, 1.0)


def test_eurusd_25_pips_is_two_fifty():
    # 25 pips = 0.0025 → $2.50 exactly at risk cap
    r = price_diff_to_usd("EURUSD", 1.10000, 1.09750, 0.01)
    assert abs(r - 2.5) < 1e-6


def test_usdjpy_risk_scales_with_price():
    # |dP|=0.10 (10 pips), entry=150 → 0.10 * 100000 * 0.01 / 150 ≈ 0.6667
    r = price_diff_to_usd("USDJPY", 150.000, 149.900, 0.01)
    assert abs(r - (0.10 * 100000 * 0.01 / 150.0)) < 1e-6


def test_xauusd_one_dollar_move():
    # 0.01 lot = 1 oz → $1 price move = $1
    r = price_diff_to_usd("XAUUSD", 2400.00, 2399.00, 0.01)
    assert abs(r - 1.0) < 1e-6


def test_btcusd_hundred_dollar_move():
    # 0.01 lot = 0.01 BTC → $100 move = $1
    r = price_diff_to_usd("BTCUSD", 67000.0, 66900.0, 0.01)
    assert abs(r - 1.0) < 1e-6


def test_pnl_sign_buy_sell():
    assert pnl_to_usd("EURUSD", 1.10, 1.1010, 0.01, "BUY") > 0
    assert pnl_to_usd("EURUSD", 1.10, 1.0990, 0.01, "BUY") < 0
    assert pnl_to_usd("EURUSD", 1.10, 1.0990, 0.01, "SELL") > 0


def test_risk_guard_uses_money_module():
    r = RiskGuard50.calculate_risk_dollars("EURUSD", 1.10, 1.0975, 0.01)
    assert abs(r - 2.5) < 1e-6


def test_spread_points_positive():
    # 20 points EURUSD (point=0.00001) = 0.0002 price ≈ 2 pips → $0.20
    s = spread_points_to_usd("EURUSD", 20, 0.01, mid_price=1.10)
    assert s > 0
    assert abs(s - 0.20) < 1e-3
