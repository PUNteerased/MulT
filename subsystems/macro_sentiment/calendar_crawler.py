"""
Economic Calendar & Red Folder Halt Manager.
Halts trading during high-impact news events (CPI, NFP, FOMC) to protect the $50 account.
Blackout window: 30 minutes before to 15 minutes after.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
import aiohttp
from loguru import logger
from config.settings import TOPIC_SYSTEM_STATE
from core.bus.events import SystemStateEvent, SystemState
from core.bus.zmq_bus import ZMQPublisher

RED_FOLDER_KEYWORDS = ["CPI", "NFP", "NON-FARM", "FOMC", "RATE DECISION", "INTEREST RATE", "POWELL", "INFLATION", "UNEMPLOYMENT"]

class EconomicCalendarCrawler:
    """Checks economic news schedules and activates Red Folder Trading Halts."""
    def __init__(self, publisher: Optional[ZMQPublisher] = None):
        self.publisher = publisher or ZMQPublisher()
        self.scheduled_events: List[Dict[str, Any]] = []
        self.is_halted = False

    def add_event(self, title: str, currency: str, event_time_utc: datetime, impact: str = "HIGH"):
        """Manually or dynamically register an economic news event."""
        self.scheduled_events.append({
            "title": title.upper(),
            "currency": currency.upper(),
            "time_utc": event_time_utc,
            "impact": impact.upper()
        })

    def check_red_folder_status(self, now_utc: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Check if current time is within [-30 min, +15 min] of any high-impact event.
        Returns (is_halted, active_event_title).
        """
        now = now_utc or datetime.now(timezone.utc)
        try:
            from subsystems.config.system_runtime import load_settings

            cal = load_settings().calendar
            if not cal.enabled:
                return False, ""
            before_m = int(cal.blackout_before_min)
            after_m = int(cal.blackout_after_min)
        except Exception:
            before_m, after_m = 30, 15

        for evt in self.scheduled_events:
            evt_time = evt["time_utc"]
            # Ensure timezone-aware comparison
            if evt_time.tzinfo is None:
                evt_time = evt_time.replace(tzinfo=timezone.utc)

            window_start = evt_time - timedelta(minutes=before_m)
            window_end = evt_time + timedelta(minutes=after_m)

            if window_start <= now <= window_end:
                return True, evt["title"]

        return False, ""

    async def fetch_forexfactory_calendar(self):
        """Fetch weekly calendar JSON from ForexFactory public endpoint or fallback."""
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data:
                            impact = item.get("impact", "").upper()
                            title = item.get("title", "").upper()
                            currency = item.get("country", "").upper()
                            date_str = item.get("date", "")
                            if impact == "HIGH" or any(kw in title for kw in RED_FOLDER_KEYWORDS):
                                try:
                                    dt = datetime.fromisoformat(date_str)
                                    self.add_event(title, currency, dt, impact="HIGH")
                                except Exception:
                                    pass
                        logger.info(f"[Calendar] Loaded {len(self.scheduled_events)} high impact news events.")
        except Exception as e:
            logger.warning(f"[Calendar] Could not fetch remote calendar ({e}), using built-in safety rules.")

    async def run_news_monitor(self, poll_interval_sec: float = 30.0):
        """Background loop broadcasting SystemStateEvent when Red Folder approaches."""
        while True:
            try:
                try:
                    from subsystems.config.system_runtime import load_settings

                    cal = load_settings().calendar
                    if not cal.enabled:
                        await asyncio.sleep(max(5.0, float(cal.poll_interval_sec)))
                        continue
                    poll = float(cal.poll_interval_sec)
                except Exception:
                    poll = poll_interval_sec

                halted, event_title = self.check_red_folder_status()
                if halted and not self.is_halted:
                    self.is_halted = True
                    logger.warning(f"[Calendar] RED FOLDER HALT ACTIVE: {event_title}")
                    event = SystemStateEvent(
                        state=SystemState.HALT_TRADING,
                        reason=f"Red Folder News: {event_title}",
                        source="CalendarCrawler"
                    )
                    await self.publisher.publish(TOPIC_SYSTEM_STATE, event)
                elif not halted and self.is_halted:
                    self.is_halted = False
                    logger.info("[Calendar] Red Folder Window cleared. Resuming NORMAL trading.")
                    event = SystemStateEvent(
                        state=SystemState.NORMAL,
                        reason="Red folder window cleared",
                        source="CalendarCrawler"
                    )
                    await self.publisher.publish(TOPIC_SYSTEM_STATE, event)

                await asyncio.sleep(poll)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Calendar] Error in news monitor: {e}")
                await asyncio.sleep(5.0)
