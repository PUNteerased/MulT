"""
Event-Driven M1 Sniper Subsystem Worker.
Sleeps until live tick price penetrates an active Kill Zone.
Awakes to detect Liquidity Sweep wicks and runs PyTorch CNN-LSTM pattern inference.
"""
import asyncio
import time
import uuid
from typing import Optional
import numpy as np
import torch
from loguru import logger

from config.settings import TOPIC_TRIGGER_ALERT, TOPIC_TICK
from core.bus.events import TickEvent, TriggerAlertEvent
from core.bus.zmq_bus import ZMQPublisher
from core.memory.in_memory_cache import MarketMemoryCache
from subsystems.data_ingestion.feature_worker import FeatureWorker
from subsystems.m1_sniper.sweep_detector import LiquiditySweepDetector
from subsystems.m1_sniper.cnn_lstm_model import SniperModelEngine

class M1SniperWorker:
    """Event-driven sniper agent monitoring price action inside Kill Zones."""
    def __init__(self, publisher: Optional[ZMQPublisher] = None):
        self.publisher = publisher or ZMQPublisher()
        self.cache = MarketMemoryCache()
        self.sweep_detector = LiquiditySweepDetector()
        self.model_engine = SniperModelEngine()
        self.last_alert_time = {}

    async def on_tick(self, tick: TickEvent) -> Optional[TriggerAlertEvent]:
        """
        Invoked on each incoming market tick.
        Only runs compute if price has penetrated an active institutional Kill Zone.
        """
        sym = tick.symbol
        # Check if live price is inside any active Kill Zone
        in_zone, active_zone = self.cache.check_kill_zone_penetration(sym, tick.bid)
        if not in_zone or not active_zone:
            return None

        # Prevent duplicate alerts on the same bar/minute
        now = time.time()
        if now - self.last_alert_time.get(sym, 0) < 45.0:
            return None

        # Fetch recent M1 bars
        df_m1 = self.cache.get_m1_dataframe(sym, count=60)
        if df_m1 is None or len(df_m1) < 40:
            return None

        # 1. Algorithmic Liquidity Sweep Detection
        sweep_ok, setup_info = self.sweep_detector.detect_sweep_rejection(df_m1, active_zone, sym)
        if not sweep_ok or not setup_info:
            return None

        # 2. 1D-CNN + LSTM Neural Network Verification
        ohlcv_cols = ['open', 'high', 'low', 'close', 'tick_volume']
        arr = df_m1[ohlcv_cols].values
        # Pad to 60 if needed
        if arr.shape[0] < 60:
            pad = np.repeat(arr[:1], 60 - arr.shape[0], axis=0)
            arr = np.vstack([pad, arr])

        confidence = self.model_engine.predict_reversal_confidence(arr)

        # 3. CPU Feature extraction for Meta-Labeling
        features = FeatureWorker.extract_m1_features(df_m1, current_spread=tick.spread) or {}
        features["model_confidence"] = confidence
        features["vol_ratio"] = setup_info["vol_ratio"]

        # Cleanup CUDA cache after inference
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Build Alert Event
        alert = TriggerAlertEvent(
            alert_id=f"ALT_{sym}_{uuid.uuid4().hex[:6].upper()}",
            symbol=sym,
            direction=setup_info["direction"],
            entry_price=setup_info["entry_price"],
            wick_sl_price=setup_info["wick_sl_price"],
            zone_id=active_zone.zone_id,
            pattern_name=setup_info["pattern"],
            model_confidence=round(confidence, 3),
            created_at=now,
            features=features
        )

        self.last_alert_time[sym] = now
        logger.info(
            f"[M1SniperWorker] SNIPER ALERT: {alert.alert_id} {sym} {alert.direction} "
            f"Entry={alert.entry_price} WickSL={alert.wick_sl_price} "
            f"Pattern={alert.pattern_name} Conf={alert.model_confidence:.2f}"
        )

        await self.publisher.publish(TOPIC_TRIGGER_ALERT, alert)
        return alert
