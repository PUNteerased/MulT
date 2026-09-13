"""
In-memory high-speed ring buffer cache.
Provides O(1) rolling windows for ticks, M1/M15/H1 bars, and active Kill Zones.
"""
from collections import deque
import threading
import time
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from core.bus.events import TickEvent, BarEvent, KillZoneEvent

class MarketMemoryCache:
    """Thread-safe fast in-memory store for high-frequency trading loops."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_structures()
            return cls._instance

    def _init_structures(self):
        # Rolling deques per symbol
        self._ticks: Dict[str, deque] = {}
        self._m1_bars: Dict[str, deque] = {}
        self._m15_bars: Dict[str, deque] = {}
        self._h1_bars: Dict[str, deque] = {}
        # Active kill zones per symbol
        self._kill_zones: Dict[str, List[KillZoneEvent]] = {}
        self._data_lock = threading.RLock()

    def add_tick(self, tick: TickEvent, maxlen: int = 1000):
        with self._data_lock:
            if tick.symbol not in self._ticks:
                self._ticks[tick.symbol] = deque(maxlen=maxlen)
            self._ticks[tick.symbol].append(tick)

    def get_latest_tick(self, symbol: str) -> Optional[TickEvent]:
        with self._data_lock:
            dq = self._ticks.get(symbol)
            if dq and len(dq) > 0:
                return dq[-1]
            return None

    def add_bar(self, bar: BarEvent):
        with self._data_lock:
            if bar.timeframe == "M1":
                target = self._m1_bars
                maxlen = 120  # Keep 120 M1 bars
            elif bar.timeframe == "M15":
                target = self._m15_bars
                maxlen = 100
            elif bar.timeframe == "H1":
                target = self._h1_bars
                maxlen = 100
            else:
                return

            if bar.symbol not in target:
                target[bar.symbol] = deque(maxlen=maxlen)

            # Avoid duplicate bars by time
            dq = target[bar.symbol]
            if len(dq) > 0 and dq[-1].time == bar.time:
                dq[-1] = bar  # update current bar
            else:
                dq.append(bar)

    def get_m1_dataframe(self, symbol: str, count: int = 60) -> Optional[pd.DataFrame]:
        with self._data_lock:
            dq = self._m1_bars.get(symbol)
            if not dq or len(dq) == 0:
                return None
            bars = list(dq)[-count:]
            data = {
                "time": [b.time for b in bars],
                "open": [b.open for b in bars],
                "high": [b.high for b in bars],
                "low": [b.low for b in bars],
                "close": [b.close for b in bars],
                "tick_volume": [b.tick_volume for b in bars],
                "spread": [b.spread for b in bars],
            }
            return pd.DataFrame(data)

    def get_m15_dataframe(self, symbol: str, count: int = 60) -> Optional[pd.DataFrame]:
        with self._data_lock:
            dq = self._m15_bars.get(symbol)
            if not dq or len(dq) == 0:
                return None
            bars = list(dq)[-count:]
            data = {
                "time": [b.time for b in bars],
                "open": [b.open for b in bars],
                "high": [b.high for b in bars],
                "low": [b.low for b in bars],
                "close": [b.close for b in bars],
                "tick_volume": [b.tick_volume for b in bars],
                "spread": [b.spread for b in bars],
            }
            return pd.DataFrame(data)

    def get_bars(self, symbol: str, timeframe: str, count: int = 50) -> List[BarEvent]:
        with self._data_lock:
            if timeframe == "M1":
                dq = self._m1_bars.get(symbol)
            elif timeframe == "M15":
                dq = self._m15_bars.get(symbol)
            elif timeframe == "H1":
                dq = self._h1_bars.get(symbol)
            else:
                dq = None
            if not dq:
                return []
            return list(dq)[-count:]

    def update_kill_zone(self, zone: KillZoneEvent):
        with self._data_lock:
            if zone.symbol not in self._kill_zones:
                self._kill_zones[zone.symbol] = []
            # Remove expired zones first
            now = time.time()
            self._kill_zones[zone.symbol] = [
                z for z in self._kill_zones[zone.symbol] if z.expires_at > now
            ]
            self._kill_zones[zone.symbol].append(zone)

    def get_active_kill_zones(self, symbol: str) -> List[KillZoneEvent]:
        with self._data_lock:
            now = time.time()
            zones = self._kill_zones.get(symbol, [])
            valid_zones = [z for z in zones if z.expires_at > now]
            self._kill_zones[symbol] = valid_zones
            return valid_zones

    def check_kill_zone_penetration(self, symbol: str, current_price: float) -> Tuple[bool, Optional[KillZoneEvent]]:
        """
        Check if the live price is inside any active Kill Zone for this symbol.
        Returns (is_inside, matching_zone).
        """
        zones = self.get_active_kill_zones(symbol)
        for zone in zones:
            if zone.lower_bound <= current_price <= zone.upper_bound:
                return True, zone
        return False, None
