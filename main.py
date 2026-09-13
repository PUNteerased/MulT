"""
Deep-Sniper AI Master Orchestrator.
Microservices-inspired Event-Driven Architecture for $50 Account on Acer Nitro V 16.
Manages 4 Layers & 7 Subsystems across EURUSD, USDJPY, XAUUSD, and BTCUSD.
"""
import asyncio
import argparse
import json
import signal
import sys
import time
from datetime import datetime
from loguru import logger

from config.settings import (
    TARGET_SYMBOLS,
    TOPIC_TICK,
    TOPIC_BAR_M1,
    TOPIC_TRIGGER_ALERT,
    TOPIC_KILL_ZONE,
    TOPIC_SYSTEM_STATE,
    LOGS_DIR
)
from core.bus.events import TickEvent, BarEvent, SystemState, SystemStateEvent, TriggerAlertEvent
from core.bus.zmq_bus import ZMQPublisher, ZMQSubscriber
from core.memory.in_memory_cache import MarketMemoryCache
from core.memory.duckdb_manager import DuckDBManager
from core.risk.money import atr_from_ohlc_df
from subsystems.data_ingestion.mt5_streamer import MT5AsyncStreamer
from subsystems.macro_sentiment.calendar_crawler import EconomicCalendarCrawler
from subsystems.macro_sentiment.finbert_engine import FinBERTSentimentEngine
from subsystems.macro_sentiment.hmm_regime import HMMRegimeClassifier
from subsystems.poi_radar.kill_zone_manager import KillZoneManager
from subsystems.m1_sniper.sniper_worker import M1SniperWorker
from subsystems.meta_labeling.lgbm_filter import LightGBMMetaFilter
from subsystems.risk_guard.guard_50 import RiskGuard50
from subsystems.execution.mt5_router import MT5OrderRouter
from subsystems.execution.position_guard import PositionGuard
from subsystems.evolution.weekend_learner import WeekendSelfEvolutionWorker
from subsystems.evolution import halt_state

# Configure file logging
logger.add(LOGS_DIR / "deep_sniper_{time:YYYY-MM-DD}.log", rotation="50 MB", retention="10 days")

class DeepSniperOrchestrator:
    """Master controller orchestrating all 7 subsystems."""
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.running = False

        # Core Memory & Bus
        self.cache = MarketMemoryCache()
        self.duckdb = DuckDBManager()
        self.publisher = ZMQPublisher()
        self.subscriber = ZMQSubscriber(
            topics=["market.tick", "market.bar.m1", TOPIC_SYSTEM_STATE]
        )

        # Subsystems
        self.streamer = MT5AsyncStreamer()
        self.calendar = EconomicCalendarCrawler(publisher=self.publisher)
        self.finbert = FinBERTSentimentEngine()
        self.hmm = HMMRegimeClassifier()
        self.poi_radar = KillZoneManager(publisher=self.publisher)
        self.sniper = M1SniperWorker(publisher=self.publisher)
        self.meta_filter = LightGBMMetaFilter()
        self.risk_guard = RiskGuard50()
        self.order_router = MT5OrderRouter(publisher=self.publisher, dry_run=self.dry_run)
        self.pos_guard = PositionGuard(publisher=self.publisher)
        self.evolution = WeekendSelfEvolutionWorker(duckdb=self.duckdb)

        # System State
        self.system_state = SystemState.NORMAL
        if halt_state.is_halt_locked():
            self.system_state = SystemState.HALT_TRADING
        self.macro_sentiment_score = 0.0
        self.regime_by_symbol = {}

    def _log_shadow(
        self,
        alert: TriggerAlertEvent,
        *,
        gate: str,
        reason: str,
        win_prob: float = 0.0,
        challenger_win_prob: float = None,
        features: dict = None,
    ) -> None:
        feats = features if features is not None else (alert.features or {})
        try:
            self.duckdb.log_shadow_signal(
                {
                    "symbol": alert.symbol,
                    "direction": str(alert.direction),
                    "gate": gate,
                    "win_prob": float(win_prob or 0.0),
                    "challenger_win_prob": challenger_win_prob,
                    "features_json": json.dumps(feats),
                    "reason": reason,
                    "alert_id": alert.alert_id,
                    "ts": time.time(),
                }
            )
        except Exception as e:
            logger.debug(f"[Shadow] log failed: {e}")

    async def start(self):
        """Bootstrap all subsystems and launch event loops."""
        logger.info("=" * 60)
        logger.info("🚀 STARTING DEEP-SNIPER AI ($50 ACCOUNT ARCHITECTURE)")
        logger.info(f"Mode: {'DRY RUN (Simulation)' if self.dry_run else 'LIVE MT5 TRADING'}")
        logger.info(f"Assets: {TARGET_SYMBOLS}")
        logger.info("=" * 60)

        # 1. Connect MT5 Streamer & ZeroMQ
        init_ok = await self.streamer.initialize()
        if not init_ok:
            logger.critical("Failed to connect to MT5. Exiting...")
            return

        self.subscriber.connect()

        # 2. Initial POI Radar Scan
        logger.info("[POI Radar] Generating initial Kill Zones...")
        for sym in TARGET_SYMBOLS:
            zones = self.poi_radar.update_kill_zones_for_symbol(sym, timeframe="M15")
            await self.poi_radar.broadcast_zones(zones)

        # 3. Calendar Check
        await self.calendar.fetch_forexfactory_calendar()

        self.running = True

        # Launch concurrent background tasks
        tasks = [
            asyncio.create_task(self.streamer.run(), name="StreamerLoop"),
            asyncio.create_task(self.subscriber.listen(self._on_bus_message), name="ZMQListener"),
            asyncio.create_task(self._poi_radar_periodic_loop(), name="POIRadarLoop"),
            asyncio.create_task(self.calendar.run_news_monitor(), name="CalendarMonitor"),
            asyncio.create_task(self.pos_guard.run(), name="PositionGuardLoop"),
            asyncio.create_task(self._weekend_evolution_loop(), name="EvolutionLoop"),
            asyncio.create_task(self._research_agent_loop(), name="ResearchAgentLoop"),
        ]

        logger.info("✅ All 7 Subsystems successfully started.")

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Shutdown signal received.")
        finally:
            await self.stop()

    async def _on_bus_message(self, topic: str, payload: dict):
        """Central message handler dispatching events."""
        if topic == TOPIC_SYSTEM_STATE:
            try:
                event = SystemStateEvent(**payload)
                prev = self.system_state
                # Human-locked halt cannot be cleared by NORMAL publishes
                if (
                    event.state == SystemState.NORMAL
                    and halt_state.is_halt_locked()
                ):
                    try:
                        from subsystems.config.system_runtime import load_settings

                        if load_settings().risk.halt_requires_human_reset:
                            logger.warning(
                                "[Orchestrator] Ignoring NORMAL while halt is human-locked"
                            )
                            self.system_state = SystemState.HALT_TRADING
                            return
                    except Exception:
                        self.system_state = SystemState.HALT_TRADING
                        return
                self.system_state = event.state
                if event.state == SystemState.HALT_TRADING:
                    logger.critical(
                        f"[Orchestrator] HALT_TRADING from {event.source}: {event.reason}"
                    )
                elif prev != event.state:
                    logger.info(f"[Orchestrator] system_state -> {event.state} ({event.source})")
            except Exception as e:
                logger.warning(f"[Orchestrator] bad system.state payload: {e}")
            return

        if topic == TOPIC_TICK:
            tick = TickEvent(**payload)
            # Update live position trailing SL
            await self.order_router.update_active_position_trailing(current_bid=tick.bid, current_ask=tick.ask)

            # Check if trading is allowed
            if self.system_state == SystemState.HALT_TRADING or halt_state.is_halt_locked():
                return

            # Evaluate M1 Sniper trigger if price in Kill Zone
            alert = await self.sniper.on_tick(tick)
            if alert:
                await self._process_sniper_alert(alert, tick)

        elif topic == TOPIC_BAR_M1:
            bar = BarEvent(**payload)
            # Live HMM regime update — cache for meta features
            df = self.cache.get_m1_dataframe(bar.symbol, count=40)
            if df is not None and len(df) >= 30:
                state, name, conf = self.hmm.predict_regime(df)
                self.regime_by_symbol[bar.symbol] = {
                    "state": state,
                    "name": name,
                    "conf": conf,
                }

    async def _process_sniper_alert(self, alert: TriggerAlertEvent, current_tick: TickEvent):
        """Full Gate Pipeline: Meta-Labeling -> $50 Risk Guard -> Order Router."""
        logger.info(f"[Pipeline] Processing incoming Sniper Alert: {alert.alert_id}")

        # 1. Meta-Labeling Filter (LightGBM)
        features = dict(alert.features or {})
        features["sentiment_score"] = self.macro_sentiment_score
        regime = self.regime_by_symbol.get(alert.symbol) or {}
        features["regime_state"] = float(regime.get("state", 0))
        alert.features = features

        is_approved, win_prob = self.meta_filter.evaluate_features(features)

        # Champion–challenger shadow scoring (challenger never sends live orders)
        chall_prob = None
        if self.meta_filter.challenger is not None:
            try:
                chall_prob = round(
                    self.meta_filter.predict_proba(features, use_challenger=True), 3
                )
            except Exception as e:
                logger.debug(f"[Challenger] score failed: {e}")

        if not is_approved:
            logger.info(f"[MetaFilter] Alert {alert.alert_id} REJECTED: Win Prob {win_prob:.2%} < threshold")
            self._log_shadow(
                alert,
                gate="meta",
                reason=f"win_prob={win_prob}",
                win_prob=win_prob,
                challenger_win_prob=chall_prob,
                features=features,
            )
            return

        logger.info(f"[MetaFilter] Alert {alert.alert_id} PASSED: Win Prob {win_prob:.2%}")

        # 2. $50 Fixed-Point Risk Guard
        active_count = await self.order_router.get_active_positions_count()
        equity = await self.order_router.get_account_equity() if not self.dry_run else 50.0
        if equity > 0:
            halt_state.update_equity_peak(equity)

        current_spread_pts = current_tick.spread / (0.00001 if "USD" in alert.symbol else 0.01)

        # ATR(M15) for SL sizing when use_atr_sizing is enabled
        atr_val = 0.0
        m15 = self.cache.get_m15_dataframe(alert.symbol, count=40)
        if m15 is not None:
            atr_val = atr_from_ohlc_df(m15, period=14)

        ok, reason, ticket = self.risk_guard.evaluate_trigger(
            alert=alert,
            current_spread_points=current_spread_pts,
            active_positions_count=active_count,
            account_equity=equity,
            win_prob=win_prob,
            atr=atr_val if atr_val > 0 else None,
        )

        if not ok or not ticket:
            logger.warning(f"[RiskGuard50] Alert {alert.alert_id} REJECTED: {reason}")
            self._log_shadow(
                alert,
                gate="risk",
                reason=str(reason),
                win_prob=win_prob,
                challenger_win_prob=chall_prob,
                features=features,
            )
            return

        # 3. Execution via MT5 Order Router
        logger.info(f"[RiskGuard50] Executing Ticket {ticket.ticket_id}...")
        order_id = await self.order_router.send_order(ticket)
        if order_id:
            logger.info(f"🎯 SNIPER TRADE ACTIVE! Order #{order_id} on {ticket.symbol}")
            self._log_shadow(
                alert,
                gate="passed",
                reason=f"order_id={order_id}",
                win_prob=win_prob,
                challenger_win_prob=chall_prob,
                features=features,
            )
        else:
            self._log_shadow(
                alert,
                gate="execution",
                reason="send_order_failed",
                win_prob=win_prob,
                challenger_win_prob=chall_prob,
                features=features,
            )

    async def _poi_radar_periodic_loop(self):
        """Update Kill Zones every 15 minutes."""
        while self.running:
            try:
                await asyncio.sleep(900)  # 15 minutes
                logger.info("[POI Radar] Running 15-minute Kill Zone scan...")
                for sym in TARGET_SYMBOLS:
                    zones = self.poi_radar.update_kill_zones_for_symbol(sym, timeframe="M15")
                    await self.poi_radar.broadcast_zones(zones)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[POI Radar] Loop error: {e}")
                await asyncio.sleep(10)

    async def _weekend_evolution_loop(self):
        """Check for weekend schedule once per hour; also run PSI drift check."""
        while self.running:
            try:
                await asyncio.sleep(3600)  # 1 hour
                if self.evolution.is_weekend():
                    logger.info("[WeekendEvolution] Weekend detected. Starting retraining...")
                    result = self.evolution.run_evolution_cycle()
                    logger.info(f"[WeekendEvolution] Retraining result: {result}")
                    # Reload challenger into live meta filter
                    self.meta_filter.reload_challenger()
                else:
                    # Mid-week light drift check
                    drift = self.evolution.run_drift_check()
                    if drift.get("breached"):
                        logger.warning(f"[DriftMonitor] mid-week breach: {drift}")
                        self.evolution._propose_drift_retrain(drift)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WeekendEvolution] Loop error: {e}")

    async def _research_agent_loop(self):
        """Off-hours Research Agent: weekend or HALT — proposals only, no auto-apply."""
        from subsystems.research.run_all import run_all as research_run_all

        while self.running:
            try:
                await asyncio.sleep(3600)
                weekend = self.evolution.is_weekend()
                halted = self.system_state == SystemState.HALT_TRADING
                if not (weekend or halted):
                    continue
                logger.info(
                    f"[ResearchAgent] off-hours run weekend={weekend} halt={halted}"
                )
                result = await asyncio.to_thread(
                    research_run_all,
                    force=True,
                    ignore_gpu=False,
                    halt=halted,
                    use_llm=True,
                    modules=["all"],
                )
                logger.info(f"[ResearchAgent] result={result}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ResearchAgent] Loop error: {e}")

    async def stop(self):
        """Clean shutdown protocol."""
        logger.info("Initiating Deep-Sniper AI shutdown...")
        self.running = False
        await self.streamer.stop()
        self.subscriber.stop()
        self.publisher.close()
        self.pos_guard.stop()
        self.duckdb.close()
        logger.info("Deep-Sniper AI stopped safely.")

def main():
    parser = argparse.ArgumentParser(description="Deep-Sniper AI Runner")
    parser.add_argument("--dry-run", action="store_true", help="Run in paper simulation mode without real orders")
    args = parser.parse_args()

    orchestrator = DeepSniperOrchestrator(dry_run=args.dry_run)

    loop = asyncio.get_event_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(orchestrator.stop()))
        except NotImplementedError:
            pass  # On Windows add_signal_handler may not be implemented for all signals

    try:
        loop.run_until_complete(orchestrator.start())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        loop.run_until_complete(orchestrator.stop())

if __name__ == "__main__":
    main()
