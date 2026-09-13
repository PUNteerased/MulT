"""
Asynchronous MT5 Data Streamer.
Wraps blocking MetaTrader 5 C-API calls via asyncio.to_thread() to avoid stalling
the ZeroMQ event loop and AI pipelines.
Streams real-time ticks and M1 bars for TARGET_SYMBOLS.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional
import MetaTrader5 as mt5
from loguru import logger

from config.settings import (
    TARGET_SYMBOLS,
    TOPIC_TICK,
    TOPIC_BAR_M1,
    TOPIC_BAR_M15,
    TOPIC_BAR_H1,
    SYMBOLS_CONFIG
)
from core.bus.events import TickEvent, BarEvent
from core.bus.zmq_bus import ZMQPublisher
from core.memory.in_memory_cache import MarketMemoryCache
from core.memory.duckdb_manager import DuckDBManager

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
}

class MT5AsyncStreamer:
    """Async streamer fetching ticks and bars from MT5 Terminal using asyncio.to_thread()."""
    def __init__(self, symbols: Optional[List[str]] = None, poll_interval_ms: int = 50, zmq_endpoint: Optional[str] = None):
        self.symbols = symbols or TARGET_SYMBOLS
        self.poll_interval = poll_interval_ms / 1000.0
        self.running = False
        self.publisher = ZMQPublisher(endpoint=zmq_endpoint) if zmq_endpoint else ZMQPublisher()
        self.cache = MarketMemoryCache()
        self.duckdb = DuckDBManager()
        self.last_tick_time: Dict[str, int] = {}
        self.last_bar_time: Dict[str, int] = {}

    async def initialize(self) -> bool:
        """Initialize connection to local MT5 terminal in threadpool."""
        logger.info("[MT5 Streamer] Initializing MT5 connection...")
        init_ok = await asyncio.to_thread(mt5.initialize)
        if not init_ok:
            error = await asyncio.to_thread(mt5.last_error)
            logger.error(f"[MT5 Streamer] Failed to initialize MT5: {error}")
            return False

        account_info = await asyncio.to_thread(mt5.account_info)
        if account_info:
            logger.info(
                f"[MT5 Streamer] Connected to Account: {account_info.login} "
                f"({account_info.server}) Balance: ${account_info.balance:.2f} "
                f"Leverage: 1:{account_info.leverage}"
            )

        # Enable market watch for target symbols
        for sym in self.symbols:
            selected = await asyncio.to_thread(mt5.symbol_select, sym, True)
            if not selected:
                logger.warning(f"[MT5 Streamer] Could not select symbol {sym} in MarketWatch")

        self.publisher.bind()
        await self._backfill_initial_bars()
        return True

    async def _backfill_initial_bars(self):
        """Seed rolling cache and DuckDB with recent M1, M15, and H1 history."""
        logger.info("[MT5 Streamer] Backfilling initial history bars...")
        for sym in self.symbols:
            for tf_str, tf_mt5 in [("M1", mt5.TIMEFRAME_M1), ("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1)]:
                rates = await asyncio.to_thread(mt5.copy_rates_from_pos, sym, tf_mt5, 0, 100)
                if rates is not None and len(rates) > 0:
                    bars_to_insert = []
                    for r in rates:
                        bar = BarEvent(
                            symbol=sym,
                            timeframe=tf_str,
                            time=int(r['time']),
                            open=float(r['open']),
                            high=float(r['high']),
                            low=float(r['low']),
                            close=float(r['close']),
                            tick_volume=int(r['tick_volume']),
                            spread=int(r['spread']),
                            is_closed=True
                        )
                        self.cache.add_bar(bar)
                        if tf_str == "M1":
                            bars_to_insert.append(bar)
                    if bars_to_insert:
                        self.duckdb.insert_bars_batch(bars_to_insert)
            logger.info(f"[MT5 Streamer] Backfilled history for {sym}")

    async def _poll_ticks_nonblocking(self):
        """Poll tick updates for all target symbols without blocking the event loop."""
        for sym in self.symbols:
            tick = await asyncio.to_thread(mt5.symbol_info_tick, sym)
            if tick is None:
                continue

            last_time = self.last_tick_time.get(sym, 0)
            if tick.time_msc > last_time:
                self.last_tick_time[sym] = tick.time_msc
                tick_event = TickEvent(
                    symbol=sym,
                    time_msc=int(tick.time_msc),
                    bid=float(tick.bid),
                    ask=float(tick.ask),
                    spread=float(tick.ask - tick.bid),
                    volume=float(tick.volume)
                )
                self.cache.add_tick(tick_event)
                await self.publisher.publish(TOPIC_TICK, tick_event)

    async def _poll_bars_nonblocking(self):
        """Poll newly closed or developing M1 bars."""
        for sym in self.symbols:
            rates = await asyncio.to_thread(mt5.copy_rates_from_pos, sym, mt5.TIMEFRAME_M1, 0, 2)
            if rates is not None and len(rates) >= 2:
                # rates[-2] is the fully closed M1 bar
                closed_r = rates[-2]
                bar_time = int(closed_r['time'])
                last_time = self.last_bar_time.get(sym, 0)

                if bar_time > last_time:
                    self.last_bar_time[sym] = bar_time
                    bar_event = BarEvent(
                        symbol=sym,
                        timeframe="M1",
                        time=bar_time,
                        open=float(closed_r['open']),
                        high=float(closed_r['high']),
                        low=float(closed_r['low']),
                        close=float(closed_r['close']),
                        tick_volume=int(closed_r['tick_volume']),
                        spread=int(closed_r['spread']),
                        is_closed=True
                    )
                    self.cache.add_bar(bar_event)
                    self.duckdb.insert_bar(bar_event)
                    await self.publisher.publish(TOPIC_BAR_M1, bar_event)

    async def run(self):
        """Main streamer loop."""
        self.running = True
        logger.info(f"[MT5 Streamer] Polling loop running for {self.symbols} at {self.poll_interval*1000:.0f}ms...")
        while self.running:
            try:
                await self._poll_ticks_nonblocking()
                await self._poll_bars_nonblocking()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MT5 Streamer] Exception in streamer loop: {e}")
                await asyncio.sleep(0.5)

    async def stop(self):
        """Gracefully stop streamer and disconnect MT5."""
        self.running = False
        self.publisher.close()
        await asyncio.to_thread(mt5.shutdown)
        logger.info("[MT5 Streamer] Stopped and MT5 disconnected.")
