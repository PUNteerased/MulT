"""
Position and Connection Watchdog Guard.
Monitors account health, drawdowns, connection heartbeats, and issues emergency halts.
"""
import asyncio
from typing import Optional
import MetaTrader5 as mt5
from loguru import logger
from config.settings import TOPIC_SYSTEM_STATE
from core.bus.events import SystemStateEvent, SystemState
from core.bus.zmq_bus import ZMQPublisher

class PositionGuard:
    """Monitors live MT5 terminal status and enforces account survival rules."""
    def __init__(self, publisher: Optional[ZMQPublisher] = None, check_interval_sec: float = 2.0):
        self.publisher = publisher or ZMQPublisher()
        self.check_interval = check_interval_sec
        self.running = False

    async def check_account_health(self) -> SystemState:
        """Inspect MT5 terminal and account status."""
        terminal_info = await asyncio.to_thread(mt5.terminal_info)
        if not terminal_info or not terminal_info.connected:
            logger.error("[PositionGuard] MT5 Terminal disconnected from broker!")
            return SystemState.HALT_TRADING

        account_info = await asyncio.to_thread(mt5.account_info)
        if not account_info:
            logger.error("[PositionGuard] Cannot read account info!")
            return SystemState.HALT_TRADING

        equity = account_info.equity
        # If equity is below $40.00 (20% total drawdown on $50 account)
        if equity < 40.00:
            logger.critical(f"[PositionGuard] EMERGENCY HALT: Account equity (${equity:.2f}) < $40.00!")
            return SystemState.HALT_TRADING

        return SystemState.NORMAL

    async def run(self):
        """Watchdog loop running in background."""
        self.running = True
        logger.info("[PositionGuard] Account and connection watchdog active.")
        while self.running:
            try:
                state = await self.check_account_health()
                if state == SystemState.HALT_TRADING:
                    event = SystemStateEvent(
                        state=SystemState.HALT_TRADING,
                        reason="Emergency equity drawdown or disconnect",
                        source="PositionGuard"
                    )
                    await self.publisher.publish(TOPIC_SYSTEM_STATE, event)
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PositionGuard] Exception in watchdog loop: {e}")
                await asyncio.sleep(1.0)

    def stop(self):
        self.running = False
