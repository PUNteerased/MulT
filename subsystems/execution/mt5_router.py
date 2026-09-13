"""
Asynchronous MT5 Execution Router & Dynamic Position Manager.
Enforces non-blocking execution via asyncio.to_thread(), single 0.01 lot order,
Break-Even (+2 pips) lock at 1:1.5 R:R, and aggressive trailing runner.
"""
import asyncio
import time
from typing import Optional, Dict, Any
import MetaTrader5 as mt5
from loguru import logger

from config.settings import (
    SYMBOLS_CONFIG,
    TOPIC_EXECUTION,
    FIXED_LOT_SIZE
)
from core.bus.events import TradeTicketEvent, ExecutionEvent, OrderDirection
from core.bus.zmq_bus import ZMQPublisher
from core.memory.duckdb_manager import DuckDBManager
from core.risk.money import pnl_to_usd, trailing_offset_price

MAGIC_NUMBER = 20250913


def _runtime_lot() -> float:
    try:
        from subsystems.config.system_runtime import load_settings

        return float(load_settings().execution.fixed_lot_size)
    except Exception:
        return float(FIXED_LOT_SIZE)


class MT5OrderRouter:
    """Non-blocking MT5 order execution and trailing stop manager."""
    def __init__(self, publisher: Optional[ZMQPublisher] = None, dry_run: bool = False):
        self.publisher = publisher or ZMQPublisher()
        self.duckdb = DuckDBManager()
        self.dry_run = dry_run
        self.active_position: Optional[Dict[str, Any]] = None
        self._lock = asyncio.Lock()

    def _determine_filling_mode(self, symbol: str) -> int:
        """Query symbol filling mode to prevent order rejection due to unsupported filling."""
        sym_info = mt5.symbol_info(symbol)
        if not sym_info:
            return mt5.ORDER_FILLING_IOC
        fill_flags = sym_info.filling_mode
        if fill_flags & mt5.ORDER_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC
        elif fill_flags & mt5.ORDER_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
        else:
            return mt5.ORDER_FILLING_RETURN

    async def get_active_positions_count(self) -> int:
        """Non-blocking count of open positions for our magic number."""
        positions = await asyncio.to_thread(mt5.positions_get)
        if positions is None:
            return 0
        return len([p for p in positions if p.magic == MAGIC_NUMBER])

    async def get_account_equity(self) -> float:
        """Non-blocking query of current account equity."""
        acc = await asyncio.to_thread(mt5.account_info)
        return float(acc.equity) if acc else 0.0

    async def send_order(self, ticket: TradeTicketEvent) -> Optional[int]:
        """Send 0.01 lot market order asynchronously."""
        async with self._lock:
            if self.active_position is not None:
                logger.warning("[MT5 Router] An order is already active in router! Rejecting new.")
                return None

            cfg = SYMBOLS_CONFIG.get(ticket.symbol)
            if not cfg:
                logger.error(f"[MT5 Router] Missing config for {ticket.symbol}")
                return None

            if self.dry_run:
                logger.info(f"[MT5 Router DRY RUN] Simulated order execution for {ticket.ticket_id}")
                self.active_position = {
                    "ticket_id": ticket.ticket_id,
                    "order_id": 999999,
                    "symbol": ticket.symbol,
                    "direction": ticket.direction,
                    "lot": ticket.lot,
                    "fill_price": ticket.entry_price,
                    "initial_sl": ticket.sl_price,
                    "current_sl": ticket.sl_price,
                    "be_trigger_price": ticket.be_trigger_price,
                    "be_lock_price": ticket.be_lock_price,
                    "tp_target_price": ticket.tp_target_price,
                    "be_applied": False,
                    "entry_time": time.time(),
                    "atr_at_entry": getattr(ticket, "atr_at_entry", 0.0),
                    "sl_usd": getattr(ticket, "sl_usd", ticket.risk_dollars),
                    "spread_usd": getattr(ticket, "spread_usd", 0.0),
                    "atr_k1": getattr(ticket, "atr_k1", 1.2),
                    "atr_k2": getattr(ticket, "atr_k2", 0.15),
                }
                return 999999

            # Live MT5 order preparation
            tick = await asyncio.to_thread(mt5.symbol_info_tick, ticket.symbol)
            if not tick:
                logger.error(f"[MT5 Router] Cannot get tick for {ticket.symbol}")
                return None

            order_type = mt5.ORDER_TYPE_BUY if ticket.direction == OrderDirection.BUY else mt5.ORDER_TYPE_SELL
            price = tick.ask if ticket.direction == OrderDirection.BUY else tick.bid
            filling_mode = await asyncio.to_thread(self._determine_filling_mode, ticket.symbol)

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": ticket.symbol,
                "volume": _runtime_lot(),
                "type": order_type,
                "price": price,
                "sl": ticket.sl_price,
                "tp": ticket.tp_target_price,
                "deviation": 20,
                "magic": MAGIC_NUMBER,
                "comment": f"DS_{ticket.ticket_id[:6]}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }

            result = await asyncio.to_thread(mt5.order_send, request)
            if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
                ret = result.retcode if result else "None"
                comment = result.comment if result else "Unknown"
                logger.error(f"[MT5 Router] order_send failed: retcode={ret}, comment={comment}")
                return None

            fill_price = float(result.price) if result.price > 0 else price
            order_id = int(result.order)

            self.active_position = {
                "ticket_id": ticket.ticket_id,
                "order_id": order_id,
                "symbol": ticket.symbol,
                "direction": ticket.direction,
                "lot": _runtime_lot(),
                "fill_price": fill_price,
                "initial_sl": ticket.sl_price,
                "current_sl": ticket.sl_price,
                "be_trigger_price": ticket.be_trigger_price,
                "be_lock_price": ticket.be_lock_price,
                "tp_target_price": ticket.tp_target_price,
                "be_applied": False,
                "entry_time": time.time(),
                "atr_at_entry": getattr(ticket, "atr_at_entry", 0.0),
                "sl_usd": getattr(ticket, "sl_usd", ticket.risk_dollars),
                "spread_usd": getattr(ticket, "spread_usd", 0.0),
                "atr_k1": getattr(ticket, "atr_k1", 1.2),
                "atr_k2": getattr(ticket, "atr_k2", 0.15),
            }

            logger.info(
                f"[MT5 Router] Order Filled! OrderID={order_id} {ticket.symbol} {ticket.direction} "
                f"at {fill_price:.5f} | SL={ticket.sl_price:.5f} BE_Trigger={ticket.be_trigger_price:.5f}"
            )

            # Publish ExecutionEvent
            exec_event = ExecutionEvent(
                ticket_id=ticket.ticket_id,
                order_id=order_id,
                symbol=ticket.symbol,
                direction=ticket.direction,
                lot=_runtime_lot(),
                fill_price=fill_price,
                initial_sl=ticket.sl_price,
                current_sl=ticket.sl_price,
                status="PLACED",
                comment="Initial order opened"
            )
            await self.publisher.publish(TOPIC_EXECUTION, exec_event)
            return order_id

    async def update_active_position_trailing(self, current_bid: float, current_ask: float):
        """
        Evaluate live position against BE trigger and trailing stop rules.
        Runs tick-by-tick without blocking.
        """
        if self.active_position is None:
            return

        pos = self.active_position
        sym = pos["symbol"]
        cfg = SYMBOLS_CONFIG.get(sym)
        if not cfg:
            return

        direction = pos["direction"]
        current_sl = pos["current_sl"]
        pip_dist = cfg.pip_multiplier
        atr_m1 = float(pos.get("atr_at_entry") or 0.0)
        trail_off = trailing_offset_price(cfg, atr_m1)

        # Check if position was closed externally in MT5
        if not self.dry_run:
            mt5_positions = await asyncio.to_thread(mt5.positions_get, symbol=sym)
            my_pos = [p for p in (mt5_positions or []) if p.ticket == pos["order_id"]]
            if not my_pos:
                # Position has closed!
                await self._handle_position_closed(exit_price=current_bid if direction == OrderDirection.BUY else current_ask)
                return

        # 1. Break-Even Check (1:1.5 R:R)
        if not pos["be_applied"]:
            be_triggered = False
            if direction == OrderDirection.BUY and current_bid >= pos["be_trigger_price"]:
                be_triggered = True
            elif direction == OrderDirection.SELL and current_ask <= pos["be_trigger_price"]:
                be_triggered = True

            if be_triggered:
                target_sl = pos["be_lock_price"]
                success = await self._modify_position_sl(pos["order_id"], sym, target_sl, pos["tp_target_price"])
                if success:
                    pos["current_sl"] = target_sl
                    pos["be_applied"] = True
                    logger.info(f"[MT5 Router] BREAK-EVEN LOCKED (ATR/pip offset) for Order #{pos['order_id']} at SL={target_sl}")
                    exec_event = ExecutionEvent(
                        ticket_id=pos["ticket_id"],
                        order_id=pos["order_id"],
                        symbol=sym,
                        direction=direction,
                        lot=pos["lot"],
                        fill_price=pos["fill_price"],
                        initial_sl=pos["initial_sl"],
                        current_sl=target_sl,
                        status="MODIFIED_BE",
                        comment="Moved to Break-Even + ATR/pip offset"
                    )
                    await self.publisher.publish(TOPIC_EXECUTION, exec_event)

        # 2. Aggressive Runner Trailing (After BE locked)
        elif pos["be_applied"]:
            trailing_step = cfg.trailing_step_pips * pip_dist
            if direction == OrderDirection.BUY:
                candidate_sl = round(current_bid - trail_off, cfg.digits)
                if candidate_sl > current_sl + (trailing_step * 0.5):
                    success = await self._modify_position_sl(pos["order_id"], sym, candidate_sl, pos["tp_target_price"])
                    if success:
                        pos["current_sl"] = candidate_sl
                        logger.info(f"[MT5 Router] Trailing SL ratcheted to {candidate_sl} on Order #{pos['order_id']}")
            elif direction == OrderDirection.SELL:
                candidate_sl = round(current_ask + trail_off, cfg.digits)
                if candidate_sl < current_sl - (trailing_step * 0.5):
                    success = await self._modify_position_sl(pos["order_id"], sym, candidate_sl, pos["tp_target_price"])
                    if success:
                        pos["current_sl"] = candidate_sl
                        logger.info(f"[MT5 Router] Trailing SL ratcheted to {candidate_sl} on Order #{pos['order_id']}")

    async def _modify_position_sl(self, order_id: int, symbol: str, new_sl: float, tp: float) -> bool:
        """Call MT5 TRADE_ACTION_SLTP asynchronously."""
        if self.dry_run:
            return True

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": order_id,
            "symbol": symbol,
            "sl": new_sl,
            "tp": tp
        }
        res = await asyncio.to_thread(mt5.order_send, request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            return True
        logger.warning(f"[MT5 Router] Modify SL failed: {res.comment if res else 'Unknown'}")
        return False

    async def _handle_position_closed(self, exit_price: float):
        """Clean up state and log trade to DuckDB when trade finishes."""
        pos = self.active_position
        if not pos:
            return

        exit_time = time.time()
        pnl_usd = pnl_to_usd(
            pos["symbol"],
            pos["fill_price"],
            exit_price,
            pos["lot"],
            pos["direction"],
        )

        trade_log = {
            "ticket_id": pos["ticket_id"],
            "order_id": pos["order_id"],
            "symbol": pos["symbol"],
            "direction": pos["direction"],
            "lot": pos["lot"],
            "fill_price": pos["fill_price"],
            "exit_price": exit_price,
            "initial_sl": pos["initial_sl"],
            "exit_sl": pos["current_sl"],
            "pnl": round(pnl_usd, 2),
            "status": "CLOSED",
            "comment": (
                f"Hit trailing SL / target | atr={pos.get('atr_at_entry', 0)} "
                f"sl_usd={pos.get('sl_usd', 0)} k1={pos.get('atr_k1', 1.2)} k2={pos.get('atr_k2', 0.15)}"
            ),
            "entry_timestamp": pos["entry_time"],
            "exit_timestamp": exit_time,
            "features_json": "{}"
        }
        self.duckdb.log_trade(trade_log)
        logger.info(f"[MT5 Router] Trade #{pos['order_id']} Closed! Realized PnL: ${pnl_usd:.2f}")

        exec_event = ExecutionEvent(
            ticket_id=pos["ticket_id"],
            order_id=pos["order_id"],
            symbol=pos["symbol"],
            direction=pos["direction"],
            lot=pos["lot"],
            fill_price=pos["fill_price"],
            initial_sl=pos["initial_sl"],
            current_sl=pos["current_sl"],
            status="CLOSED",
            pnl=round(pnl_usd, 2),
            comment="Position fully closed"
        )
        await self.publisher.publish(TOPIC_EXECUTION, exec_event)
        self.active_position = None
