"""
Unified pip / price-diff → USD conversion for FBS-style CFD contracts.
Single source of truth for Risk Guard and MT5 router PnL.
"""
from __future__ import annotations

from typing import Optional

from config.settings import FIXED_LOT_SIZE, SYMBOLS_CONFIG, SymbolConfig


def get_symbol_config(symbol: str) -> Optional[SymbolConfig]:
    return SYMBOLS_CONFIG.get(symbol)


def price_diff_to_usd(
    symbol: str,
    entry_price: float,
    exit_or_sl: float,
    lot: float = FIXED_LOT_SIZE,
) -> float:
    """
    Convert absolute price distance to USD PnL/risk for `lot` size.

    Conventions (FBS-style, matching prior RiskGuard branches):
    - EURUSD / most USD-quoted: |dP| * contract_size * lot
    - USDJPY (JPY quote): |dP| * contract_size * lot / entry_price
    - XAUUSD: contract 100 oz → 0.01 lot = 1 oz → |dP| * 1.0
    - BTCUSD: contract 1 → 0.01 lot = 0.01 BTC → |dP| * 0.01
    """
    cfg = get_symbol_config(symbol)
    if not cfg or entry_price <= 0:
        return 999.0

    d = abs(float(entry_price) - float(exit_or_sl))
    lot = float(lot)

    if symbol == "USDJPY":
        # Quote in JPY: USD value of 1.0 price move on full lot = contract_size / price
        return round(d * (cfg.contract_size * lot) / float(entry_price), 6)

    # USD-quoted (EURUSD, XAUUSD, BTCUSD, generic)
    return round(d * cfg.contract_size * lot, 6)


def spread_points_to_usd(
    symbol: str,
    spread_points: float,
    lot: float = FIXED_LOT_SIZE,
    mid_price: float = 0.0,
) -> float:
    """Convert broker spread in *points* (symbol point units) to USD cost for `lot`."""
    cfg = get_symbol_config(symbol)
    if not cfg:
        return 999.0
    width = float(spread_points) * float(cfg.point)
    if mid_price > 0:
        mid = float(mid_price)
    elif symbol == "USDJPY":
        mid = 150.0
    elif symbol == "XAUUSD":
        mid = 2400.0
    elif symbol == "BTCUSD":
        mid = 67000.0
    else:
        mid = 1.10
    return price_diff_to_usd(symbol, mid, mid + width, lot)


def pnl_to_usd(symbol: str, entry_price: float, exit_price: float, lot: float, direction: str) -> float:
    """Signed PnL in USD (positive = profit). direction BUY/SELL or OrderDirection value."""
    raw = price_diff_to_usd(symbol, entry_price, exit_price, lot)
    d = str(direction).upper()
    is_buy = d in ("BUY", "ORDERDIRECTION.BUY", "LONG")
    moved_up = exit_price >= entry_price
    if is_buy:
        return raw if moved_up else -raw
    return raw if not moved_up else -raw


def assert_matches_mt5_spec(
    symbol: str,
    entry: float,
    exit_or_sl: float,
    lot: float,
    expected_usd: float,
    tol: float = 1e-4,
) -> None:
    """Test helper: raise AssertionError if money math drifts from expected USD."""
    got = price_diff_to_usd(symbol, entry, exit_or_sl, lot)
    if abs(got - expected_usd) > tol:
        raise AssertionError(
            f"{symbol} money mismatch: got ${got} expected ${expected_usd} "
            f"(entry={entry} exit/sl={exit_or_sl} lot={lot})"
        )


def atr_stop_distance(atr: float, k1: float) -> float:
    return max(0.0, float(atr) * float(k1))


def trailing_offset_price(cfg: SymbolConfig, atr_m1: float) -> float:
    """max(be_lock_pips * pip_mult, k2 * ATR_M1)."""
    pip_off = float(cfg.be_lock_pips) * float(cfg.pip_multiplier)
    atr_off = float(getattr(cfg, "atr_k2", 0.15) or 0.15) * float(atr_m1 or 0.0)
    return max(pip_off, atr_off)


def compute_atr(highs, lows, closes, period: int = 14) -> float:
    """Wilder ATR from parallel high/low/close sequences. Returns 0 if insufficient data."""
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return 0.0
    trs = []
    for i in range(1, n):
        h, l, prev_c = float(highs[i]), float(lows[i]), float(closes[i - 1])
        trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
    if len(trs) < period:
        return 0.0
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return float(atr)


def atr_from_ohlc_df(df, period: int = 14) -> float:
    if df is None or len(df) < period + 1:
        return 0.0
    return compute_atr(df["high"].tolist(), df["low"].tolist(), df["close"].tolist(), period)
