"""
M1 Algorithmic Liquidity Sweep and Wick Rejection Detector.
Identifies false breakouts / retail stop runs at institutional Kill Zones.
"""
from typing import Optional, Dict, Any, Tuple
import numpy as np
import pandas as pd
from loguru import logger
from core.bus.events import KillZoneEvent, OrderDirection
from config.settings import SYMBOLS_CONFIG

class LiquiditySweepDetector:
    """Detects liquidity sweeps and calculates pinpoint wick Stop Loss levels."""

    @classmethod
    def detect_sweep_rejection(
        cls,
        df_m1: pd.DataFrame,
        zone: KillZoneEvent,
        symbol: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check the most recent 1-3 M1 bars for a liquidity sweep and wick rejection.
        Returns (is_detected, setup_details).
        """
        if len(df_m1) < 20:
            return False, None

        try:
            from subsystems.config.system_runtime import load_settings, merged_symbol_config

            cfg = merged_symbol_config(symbol)
            wick_min = float(load_settings().sniper.wick_ratio_min)
        except Exception:
            cfg = SYMBOLS_CONFIG.get(symbol)
            wick_min = 0.35
        digits = cfg.digits if cfg else 5
        pip_mult = cfg.pip_multiplier if cfg else 0.0001

        # Examine the last bar
        last_bar = df_m1.iloc[-1]
        prev_bar = df_m1.iloc[-2]

        o = float(last_bar['open'])
        h = float(last_bar['high'])
        l = float(last_bar['low'])
        c = float(last_bar['close'])
        vol = float(last_bar['tick_volume'])

        # Volume confirmation: tick volume higher than 1.1x average
        avg_vol = float(df_m1['tick_volume'].iloc[-20:].mean()) + 1e-6
        vol_ratio = vol / avg_vol

        bar_range = max(h - l, pip_mult * 0.5)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l

        # 1. Bullish Liquidity Sweep (For BUY in Demand Kill Zone)
        if zone.direction == OrderDirection.BUY:
            # Low swept below or into the zone
            swept_zone = l <= zone.mid_price or l <= zone.lower_bound
            # Strong rejection from bottom: lower wick accounts for >= wick_min of total bar range
            has_rejection_wick = (lower_wick / bar_range) >= wick_min
            # Close finishes back up inside or above zone
            closed_favorable = c >= l + (lower_wick * 0.8) and c > o

            if swept_zone and has_rejection_wick and closed_favorable and vol_ratio >= 1.0:
                # Place SL safely under the rejection wick tip + 1.5 pips buffer
                sl_price = round(l - (1.5 * pip_mult), digits)
                entry_price = round(c, digits)
                setup = {
                    "direction": OrderDirection.BUY,
                    "entry_price": entry_price,
                    "wick_sl_price": sl_price,
                    "pattern": "BULLISH_SWEEP_HAMMER",
                    "vol_ratio": round(vol_ratio, 2),
                    "lower_wick_ratio": round(lower_wick / bar_range, 3),
                    "wick_tip": l
                }
                return True, setup

        # 2. Bearish Liquidity Sweep (For SELL in Supply Kill Zone)
        elif zone.direction == OrderDirection.SELL:
            # High swept above or into the zone
            swept_zone = h >= zone.mid_price or h >= zone.upper_bound
            # Strong rejection from top: upper wick accounts for >= wick_min of total range
            has_rejection_wick = (upper_wick / bar_range) >= wick_min
            # Close finishes back down inside or below zone
            closed_favorable = c <= h - (upper_wick * 0.8) and c < o

            if swept_zone and has_rejection_wick and closed_favorable and vol_ratio >= 1.0:
                # Place SL safely above the rejection wick tip + 1.5 pips buffer
                sl_price = round(h + (1.5 * pip_mult), digits)
                entry_price = round(c, digits)
                setup = {
                    "direction": OrderDirection.SELL,
                    "entry_price": entry_price,
                    "wick_sl_price": sl_price,
                    "pattern": "BEARISH_SWEEP_SHOOTING_STAR",
                    "vol_ratio": round(vol_ratio, 2),
                    "upper_wick_ratio": round(upper_wick / bar_range, 3),
                    "wick_tip": h
                }
                return True, setup

        return False, None
