"""
CPU Feature Engineering Worker.
Transforms raw M1/M15 OHLCV price series into normalized mathematical features
(Z-Score, ATR, RSI, EMAs, Wick Ratios, Relative Volume) for M1 Sniper & LightGBM filter.
"""
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd
from loguru import logger

class FeatureWorker:
    """Computes technical and statistical features on CPU using vectorized NumPy/Pandas."""

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df['high']
        low = df['low']
        close_prev = df['close'].shift(1)
        tr1 = high - low
        tr2 = (high - close_prev).abs()
        tr3 = (low - close_prev).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calculate_candlestick_anatomy(df: pd.DataFrame) -> pd.DataFrame:
        """Extract body and wick proportions for liquidity sweep detection."""
        body = (df['close'] - df['open']).abs()
        total_range = (df['high'] - df['low']).clip(lower=1e-6)
        upper_wick = df['high'] - df[['open', 'close']].max(axis=1)
        lower_wick = df[['open', 'close']].min(axis=1) - df['low']

        anatomy = pd.DataFrame(index=df.index)
        anatomy['body_ratio'] = body / total_range
        anatomy['upper_wick_ratio'] = upper_wick / total_range
        anatomy['lower_wick_ratio'] = lower_wick / total_range
        anatomy['total_range'] = total_range
        return anatomy

    @classmethod
    def extract_m1_features(cls, df_m1: pd.DataFrame, current_spread: float) -> Optional[Dict[str, float]]:
        """
        Extract tabular features from the latest 60 M1 bars for LightGBM meta-filter.
        """
        if df_m1 is None or len(df_m1) < 30:
            return None

        df = df_m1.copy()
        close = df['close']
        volume = df['tick_volume']

        # ATR & Volatility
        atr = cls.calculate_atr(df, period=14).iloc[-1]
        returns = close.pct_change()
        ret_mean = returns.rolling(20).mean().iloc[-1]
        ret_std = returns.rolling(20).std().iloc[-1] + 1e-9
        z_score = (returns.iloc[-1] - ret_mean) / ret_std

        # RSI
        rsi = cls.calculate_rsi(close, period=14).iloc[-1]

        # EMAs
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1] if len(df) >= 50 else ema20

        curr_close = close.iloc[-1]
        dist_ema20 = (curr_close - ema20) / (atr + 1e-6)
        dist_ema50 = (curr_close - ema50) / (atr + 1e-6)

        # Candlestick anatomy of trigger bar
        anatomy = cls.calculate_candlestick_anatomy(df).iloc[-1]

        # Relative volume
        vol_sma20 = volume.rolling(20, min_periods=5).mean().iloc[-1] + 1e-6
        rel_vol = volume.iloc[-1] / vol_sma20

        # Spread to ATR ratio
        spread_ratio = current_spread / (atr + 1e-6)

        features = {
            "z_score": float(z_score),
            "atr": float(atr),
            "rsi": float(rsi),
            "dist_ema20": float(dist_ema20),
            "dist_ema50": float(dist_ema50),
            "body_ratio": float(anatomy['body_ratio']),
            "upper_wick_ratio": float(anatomy['upper_wick_ratio']),
            "lower_wick_ratio": float(anatomy['lower_wick_ratio']),
            "rel_volume": float(rel_vol),
            "spread_ratio": float(spread_ratio),
        }
        return features
