"""
Kill Zone Manager.
Intersects KDE institutional liquidity peaks with Chronos forecast quantiles to generate
high-probability sniper Kill Zones (e.g., Buy EURUSD @ 1.08500 - 1.08520).
"""
import time
import uuid
from typing import List, Optional
import numpy as np
import pandas as pd
from loguru import logger

from config.settings import TOPIC_KILL_ZONE, SYMBOLS_CONFIG
from core.bus.events import KillZoneEvent, OrderDirection
from core.bus.zmq_bus import ZMQPublisher
from core.memory.in_memory_cache import MarketMemoryCache
from subsystems.poi_radar.kde_zones import KDELiquidityDetector
from subsystems.poi_radar.chronos_engine import ChronosForecastEngine

class KillZoneManager:
    """Calculates, validates, and broadcasts active sniper Kill Zones."""
    def __init__(self, publisher: Optional[ZMQPublisher] = None):
        self.publisher = publisher or ZMQPublisher()
        self.cache = MarketMemoryCache()
        self.chronos = ChronosForecastEngine()
        self.kde = KDELiquidityDetector()

    def update_kill_zones_for_symbol(self, symbol: str, timeframe: str = "M15") -> List[KillZoneEvent]:
        """Scan historical bars and generate fresh Kill Zones."""
        bars = self.cache.get_bars(symbol, timeframe, count=60)
        if len(bars) < 25:
            return []

        df = pd.DataFrame([{
            "time": b.time,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "tick_volume": b.tick_volume,
            "spread": b.spread
        } for b in bars])

        current_price = float(df['close'].iloc[-1])
        closes = df['close'].values

        # 1. Compute Chronos Quantiles
        q10, q50, q90 = self.chronos.forecast_quantiles(closes)

        # 2. Compute KDE Liquidity Clusters
        kde_zones = self.kde.find_liquidity_zones(df, current_price=current_price)

        generated_zones = []
        cfg = SYMBOLS_CONFIG.get(symbol)
        digits = cfg.digits if cfg else 5

        for zone in kde_zones[:4]:  # Top 4 most relevant zones
            center = zone["center_price"]
            direction = OrderDirection.BUY if zone["type"] == "SUPPORT" else OrderDirection.SELL

            # Zone alignment condition:
            # If SUPPORT is near or below q10 -> High probability Institutional Demand
            # If RESISTANCE is near or above q90 -> High probability Institutional Supply
            is_extreme = False
            confidence = 0.70

            if direction == OrderDirection.BUY and center <= (q50 + (q50 - q10) * 0.2):
                is_extreme = True
                confidence = 0.85
            elif direction == OrderDirection.SELL and center >= (q50 + (q90 - q50) * 0.2):
                is_extreme = True
                confidence = 0.85

            if not is_extreme:
                continue

            kz = KillZoneEvent(
                zone_id=f"KZ_{symbol}_{uuid.uuid4().hex[:6].upper()}",
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                lower_bound=round(zone["lower_bound"], digits),
                upper_bound=round(zone["upper_bound"], digits),
                mid_price=round(center, digits),
                confidence=round(confidence, 2),
                created_at=time.time(),
                expires_at=time.time() + 3600.0  # 1 hour validity
            )

            self.cache.update_kill_zone(kz)
            generated_zones.append(kz)

            logger.info(
                f"[KillZoneManager] NEW ZONE: {kz.zone_id} {symbol} {kz.direction} "
                f"[{kz.lower_bound:.5f} - {kz.upper_bound:.5f}] Confidence={kz.confidence}"
            )

        return generated_zones

    async def broadcast_zones(self, zones: List[KillZoneEvent]):
        """Publish updated kill zones to ZeroMQ."""
        for kz in zones:
            await self.publisher.publish(TOPIC_KILL_ZONE, kz)
