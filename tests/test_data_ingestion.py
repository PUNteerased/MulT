"""
Unit tests for MT5 Streamer and Feature Worker.
"""
import pytest
import asyncio
import numpy as np
import pandas as pd
from subsystems.data_ingestion.feature_worker import FeatureWorker
from subsystems.data_ingestion.mt5_streamer import MT5AsyncStreamer
from core.memory.in_memory_cache import MarketMemoryCache

def test_feature_worker_calculation():
    # Build 50 mock M1 bars
    np.random.seed(42)
    closes = 1.0800 + np.cumsum(np.random.normal(0, 0.0002, 50))
    highs = closes + np.random.uniform(0.0001, 0.0003, 50)
    lows = closes - np.random.uniform(0.0001, 0.0003, 50)
    opens = closes - np.random.normal(0, 0.0001, 50)
    volumes = np.random.randint(50, 300, 50)
    spreads = np.full(50, 10)

    df = pd.DataFrame({
        "time": np.arange(1000, 1000 + 50 * 60, 60),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": volumes,
        "spread": spreads
    })

    feats = FeatureWorker.extract_m1_features(df, current_spread=0.00010)
    assert feats is not None
    assert "atr" in feats
    assert "rsi" in feats
    assert "z_score" in feats
    assert "rel_volume" in feats
    assert 0 <= feats["rsi"] <= 100

@pytest.mark.asyncio
async def test_mt5_streamer_init_and_backfill():
    streamer = MT5AsyncStreamer(symbols=["EURUSD"], zmq_endpoint="tcp://127.0.0.1:5588")
    init_ok = await streamer.initialize()
    assert init_ok is True

    cache = MarketMemoryCache()
    m1_df = cache.get_m1_dataframe("EURUSD", count=10)
    assert m1_df is not None
    assert len(m1_df) >= 10

    # Test single tick poll
    await streamer._poll_ticks_nonblocking()
    tick = cache.get_latest_tick("EURUSD")
    assert tick is not None
    assert tick.bid > 0

    await streamer.stop()
