"""Historical bar replay sources for offline validation."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from config.settings import DATA_DIR, DUCKDB_PATH


def _months_to_bars(months: float, timeframe_minutes: int = 1) -> int:
    # ~21 trading days/month * 24h * 60 / tf — crypto includes weekends; FX approx
    days = max(1.0, float(months) * 21.0)
    return int(days * 24 * 60 / timeframe_minutes)


def load_bars_from_parquet(symbol: str, months: float = 6.0) -> Optional[pd.DataFrame]:
    path = DATA_DIR / "bars_m1.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        df = df[df["symbol"] == symbol].copy()
        if df.empty:
            return None
        df = df.sort_values("time").reset_index(drop=True)
        n = _months_to_bars(months)
        return df.tail(n).reset_index(drop=True)
    except Exception as e:
        logger.warning(f"[Replay] parquet load failed: {e}")
        return None


def load_bars_from_duckdb(symbol: str, months: float = 6.0) -> Optional[pd.DataFrame]:
    path = Path(DUCKDB_PATH)
    if not path.exists():
        return None
    try:
        import duckdb

        n = _months_to_bars(months)
        con = duckdb.connect(str(path), read_only=True)
        df = con.execute(
            """
            SELECT * FROM bars_m1
            WHERE symbol = ?
            ORDER BY time DESC
            LIMIT ?
            """,
            [symbol, n],
        ).df()
        con.close()
        if df is None or df.empty:
            return None
        return df.sort_values("time").reset_index(drop=True)
    except Exception as e:
        logger.warning(f"[Replay] DuckDB load failed: {e}")
        return None


def synthesize_bars(symbol: str, months: float = 6.0, seed: int = 42) -> pd.DataFrame:
    """Deterministic synthetic OHLC for offline demos when no warehouse data exists."""
    rng = np.random.default_rng(seed + sum(ord(c) for c in symbol))
    n = min(_months_to_bars(months), 20_000)
    if symbol == "USDJPY":
        px0 = 150.0
        vol = 0.02
    elif symbol == "XAUUSD":
        px0 = 2400.0
        vol = 0.8
    elif symbol == "BTCUSD":
        px0 = 67000.0
        vol = 80.0
    else:
        px0 = 1.08500
        vol = 0.00012

    rets = rng.normal(0.0, vol, size=n)
    close = px0 + np.cumsum(rets)
    # mild mean reversion
    close = px0 + (close - px0) * 0.15 + np.cumsum(rng.normal(0, vol * 0.35, size=n))
    high = close + np.abs(rng.normal(0, vol * 0.6, size=n))
    low = close - np.abs(rng.normal(0, vol * 0.6, size=n))
    open_ = np.roll(close, 1)
    open_[0] = px0
    now = int(time.time())
    start = now - n * 60
    times = np.arange(start, start + n * 60, 60, dtype=np.int64)
    spreads = {
        "EURUSD": 12,
        "USDJPY": 15,
        "XAUUSD": 25,
        "BTCUSD": 800,
    }.get(symbol, 15)

    return pd.DataFrame(
        {
            "symbol": symbol,
            "time": times[:n],
            "open": open_[:n],
            "high": high[:n],
            "low": low[:n],
            "close": close[:n],
            "tick_volume": rng.integers(50, 500, size=n),
            "spread": np.full(n, spreads, dtype=np.int32),
        }
    )


def load_replay_bars(symbol: str, months: float = 6.0, allow_synthetic: bool = True) -> pd.DataFrame:
    """Prefer DuckDB → parquet → synthetic."""
    df = load_bars_from_duckdb(symbol, months)
    if df is not None and len(df) >= 100:
        logger.info(f"[Replay] {symbol}: {len(df)} bars from DuckDB")
        return df
    df = load_bars_from_parquet(symbol, months)
    if df is not None and len(df) >= 100:
        logger.info(f"[Replay] {symbol}: {len(df)} bars from parquet")
        return df
    if not allow_synthetic:
        raise FileNotFoundError(f"No historical bars for {symbol}")
    logger.warning(f"[Replay] {symbol}: no warehouse bars — using synthetic series")
    return synthesize_bars(symbol, months)
