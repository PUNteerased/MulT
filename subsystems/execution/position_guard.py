"""
Position and Connection Watchdog Guard.
Monitors account health, peak drawdown, connection heartbeats, and issues emergency halts.
"""
import asyncio
from typing import Optional
import MetaTrader5 as mt5
from loguru import logger
from config.settings import TOPIC_SYSTEM_STATE
from core.bus.events import SystemStateEvent, SystemState
from core.bus.zmq_bus import ZMQPublisher
from subsystems.evolution import halt_state


class PositionGuard:
    """Monitors live MT5 terminal status and enforces account survival rules."""

    def __init__(self, publisher: Optional[ZMQPublisher] = None, check_interval_sec: float = 2.0):
        self.publisher = publisher or ZMQPublisher()
        self.check_interval = check_interval_sec
        self.running = False

    def _max_peak_dd_pct(self) -> float:
        try:
            from subsystems.config.system_runtime import load_settings

            return float(load_settings().risk.max_peak_dd_pct)
        except Exception:
            return 0.15

    def _human_reset_required(self) -> bool:
        try:
            from subsystems.config.system_runtime import load_settings

            return bool(load_settings().risk.halt_requires_human_reset)
        except Exception:
            return True

    async def check_account_health(self) -> SystemState:
        """Inspect MT5 terminal and account status."""
        if halt_state.is_halt_locked() and self._human_reset_required():
            return SystemState.HALT_TRADING

        terminal_info = await asyncio.to_thread(mt5.terminal_info)
        if not terminal_info or not terminal_info.connected:
            logger.error("[PositionGuard] MT5 Terminal disconnected from broker!")
            return SystemState.HALT_TRADING

        account_info = await asyncio.to_thread(mt5.account_info)
        if not account_info:
            logger.error("[PositionGuard] Cannot read account info!")
            return SystemState.HALT_TRADING

        equity = float(account_info.equity)
        halt_state.update_equity_peak(equity)

        if equity < 40.00:
            reason = f"Emergency equity floor: ${equity:.2f} < $40.00"
            logger.critical(f"[PositionGuard] {reason}")
            if self._human_reset_required():
                halt_state.lock_halt(reason)
            return SystemState.HALT_TRADING

        dd_pct = halt_state.peak_drawdown_pct(equity)
        max_dd = self._max_peak_dd_pct()
        if dd_pct >= max_dd:
            reason = f"Peak drawdown {dd_pct:.1%} >= max {max_dd:.1%} (equity=${equity:.2f})"
            logger.critical(f"[PositionGuard] {reason}")
            if self._human_reset_required():
                halt_state.lock_halt(reason)
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
                    st = halt_state.load_halt_state()
                    event = SystemStateEvent(
                        state=SystemState.HALT_TRADING,
                        reason=st.get("halt_reason")
                        or "Emergency equity drawdown, peak DD, or disconnect",
                        source="PositionGuard",
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
