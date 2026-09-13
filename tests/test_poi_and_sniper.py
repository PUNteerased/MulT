"""
Unit tests for POI Radar and M1 Sniper subsystems.
"""
import pytest
import asyncio
import numpy as np
import pandas as pd
from subsystems.poi_radar.kde_zones import KDELiquidityDetector
from subsystems.poi_radar.chronos_engine import ChronosForecastEngine
from subsystems.poi_radar.kill_zone_manager import KillZoneManager
from subsystems.m1_sniper.sweep_detector import LiquiditySweepDetector
from subsystems.m1_sniper.cnn_lstm_model import SniperModelEngine
from subsystems.m1_sniper.sniper_worker import M1SniperWorker
from core.bus.events import KillZoneEvent, OrderDirection, TickEvent, BarEvent
from core.memory.in_memory_cache import MarketMemoryCache

def test_kde_liquidity_detection():
    # Build 60 bars with oscillating swing peaks and troughs
    np.random.seed(42)
    t = np.linspace(0, 4 * np.pi, 60)
    closes = 1.0850 + 0.0030 * np.sin(t)
    highs = closes + 0.0005
    lows = closes - 0.0005
    opens = closes - 0.0001
    volumes = np.random.randint(100, 500, 60)

    df = pd.DataFrame({
        "time": np.arange(1000, 1000 + 60 * 60, 60),
        "open": opens, "high": highs, "low": lows, "close": closes,
        "tick_volume": volumes, "spread": np.full(60, 10)
    })

    zones = KDELiquidityDetector.find_liquidity_zones(df, current_price=1.0850)
    assert len(zones) > 0
    assert any(z["type"] == "SUPPORT" for z in zones) or any(z["type"] == "RESISTANCE" for z in zones)

def test_chronos_quantiles_and_vram_cleanup():
    engine = ChronosForecastEngine()
    series = np.linspace(1.0800, 1.0850, 40)
    q10, q50, q90 = engine.forecast_quantiles(series)
    assert q10 < q90
    assert q10 <= q50 <= q90
    # Confirm model was unloaded from memory
    assert engine.model is None

def test_liquidity_sweep_detector():
    zone = KillZoneEvent(
        zone_id="KZ_BUY_1", symbol="EURUSD", timeframe="M15",
        direction=OrderDirection.BUY, lower_bound=1.08450, upper_bound=1.08550,
        mid_price=1.08500, confidence=0.85, expires_at=9999999999
    )

    # Construct bars leading to a bullish liquidity sweep
    bars = []
    for i in range(25):
        bars.append({"open": 1.0860, "high": 1.0865, "low": 1.0855, "close": 1.0858, "tick_volume": 100})

    # Trigger bar: low pierced down to 1.08440 (below zone), rejected strongly, closed at 1.08530
    bars.append({
        "open": 1.08500,
        "high": 1.08540,
        "low": 1.08440,   # Deep lower wick (10 pips)
        "close": 1.08530,  # Bullish close
        "tick_volume": 350 # Heavy volume spike
    })
    df_m1 = pd.DataFrame(bars)

    ok, setup = LiquiditySweepDetector.detect_sweep_rejection(df_m1, zone, "EURUSD")
    assert ok is True
    assert setup["direction"] == OrderDirection.BUY
    assert setup["wick_sl_price"] < setup["entry_price"]
    assert setup["pattern"] == "BULLISH_SWEEP_HAMMER"

def test_cnn_lstm_model():
    engine = SniperModelEngine()
    arr = np.random.randn(60, 5).astype(np.float32)
    score = engine.predict_reversal_confidence(arr)
    assert 0.0 <= score <= 1.0

@pytest.mark.asyncio
async def test_m1_sniper_worker_awake_flow():
    cache = MarketMemoryCache()
    # Register Kill Zone
    kz = KillZoneEvent(
        zone_id="KZ_SNIPER_1", symbol="EURUSD", timeframe="M15",
        direction=OrderDirection.BUY, lower_bound=1.08450, upper_bound=1.08550,
        mid_price=1.08500, confidence=0.88, expires_at=9999999999
    )
    cache.update_kill_zone(kz)

    # Seed 60 M1 bars
    for i in range(50):
        b = BarEvent(
            symbol="EURUSD", timeframe="M1", time=1000 + i*60,
            open=1.0860, high=1.0865, low=1.0855, close=1.0858,
            tick_volume=100, spread=10
        )
        cache.add_bar(b)

    # Trigger bar with sweep
    sweep_bar = BarEvent(
        symbol="EURUSD", timeframe="M1", time=1000 + 51*60,
        open=1.0850, high=1.0854, low=1.0844, close=1.0853,
        tick_volume=300, spread=10
    )
    cache.add_bar(sweep_bar)

    worker = M1SniperWorker()
    tick_inside_zone = TickEvent(symbol="EURUSD", time_msc=1720000000000, bid=1.08490, ask=1.08500, spread=10)
    alert = await worker.on_tick(tick_inside_zone)
    assert alert is not None
    assert alert.symbol == "EURUSD"
    assert alert.direction == OrderDirection.BUY
