"""
Unit test for Core Bus, Memory Cache, and DuckDB storage.
"""
import pytest
import asyncio
import time
from core.bus.events import TickEvent, BarEvent, KillZoneEvent, OrderDirection
from core.bus.zmq_bus import ZMQPublisher, ZMQSubscriber
from core.memory.in_memory_cache import MarketMemoryCache
from core.memory.duckdb_manager import DuckDBManager

@pytest.mark.asyncio
async def test_zmq_pub_sub():
    test_endpoint = "tcp://127.0.0.1:5588"
    pub = ZMQPublisher(endpoint=test_endpoint)
    pub.bind()

    received = []
    sub = ZMQSubscriber(endpoint=test_endpoint, topics=["test.topic"])
    sub.connect()

    async def on_msg(topic, payload):
        received.append((topic, payload))

    listen_task = asyncio.create_task(sub.listen(on_msg))
    await asyncio.sleep(0.1)

    tick = TickEvent(symbol="EURUSD", time_msc=1720000000000, bid=1.08500, ask=1.08510, spread=10)
    for _ in range(3):
        await pub.publish("test.topic", tick)
        await asyncio.sleep(0.05)

    sub.stop()
    pub.close()
    listen_task.cancel()
    try:
        await listen_task
    except asyncio.CancelledError:
        pass

    assert len(received) >= 1
    assert received[0][0] == "test.topic"
    assert received[0][1]["symbol"] == "EURUSD"
    assert received[0][1]["bid"] == 1.08500

def test_market_memory_cache():
    cache = MarketMemoryCache()
    tick = TickEvent(symbol="XAUUSD", time_msc=1720000000000, bid=2650.50, ask=2650.80, spread=30)
    cache.add_tick(tick)
    latest = cache.get_latest_tick("XAUUSD")
    assert latest is not None
    assert latest.bid == 2650.50

    for i in range(10):
        bar = BarEvent(
            symbol="XAUUSD", timeframe="M1", time=1000 + i * 60,
            open=2650.0 + i, high=2652.0 + i, low=2649.0 + i, close=2651.0 + i,
            tick_volume=100, spread=20
        )
        cache.add_bar(bar)

    df = cache.get_m1_dataframe("XAUUSD", count=5)
    assert df is not None
    assert len(df) == 5

    kz = KillZoneEvent(
        zone_id="kz_1", symbol="XAUUSD", timeframe="M15",
        direction=OrderDirection.BUY, lower_bound=2645.0, upper_bound=2655.0,
        mid_price=2650.0, confidence=0.88, expires_at=time.time() + 600
    )
    cache.update_kill_zone(kz)
    in_zone, match = cache.check_kill_zone_penetration("XAUUSD", 2650.50)
    assert in_zone is True
    assert match.zone_id == "kz_1"

def test_duckdb_storage():
    DuckDBManager.reset_instance()
    db = DuckDBManager(":memory:")
    bar = BarEvent(
        symbol="EURUSD", timeframe="M1", time=1700000000,
        open=1.0800, high=1.0810, low=1.0790, close=1.0805,
        tick_volume=250, spread=12
    )
    db.insert_bar(bar)
    df = db.get_recent_bars("EURUSD", limit=10)
    assert not df.empty
    assert df.iloc[0]["symbol"] == "EURUSD"
    DuckDBManager.reset_instance()
