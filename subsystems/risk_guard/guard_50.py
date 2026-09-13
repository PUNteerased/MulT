"""
$50 Fixed-Point Risk Guard Subsystem.
Strict rule-based gatekeeper with zero AI hallucination.
Enforces hard $2.50 max loss limit, 0.01 lot size, spread filter, and single-trade concurrency.
"""
from datetime import datetime, timezone
from typing import Tuple, Optional
import uuid
from loguru import logger

from config.settings import (
    MAX_RISK_DOLLARS_PER_TRADE,
    MAX_CONCURRENT_POSITIONS,
    FIXED_LOT_SIZE,
    MAX_SPREAD_RISK_PCT,
    SYMBOLS_CONFIG,
)
from core.bus.events import OrderDirection, TriggerAlertEvent, TradeTicketEvent
from core.risk.money import price_diff_to_usd, spread_points_to_usd, atr_stop_distance, trailing_offset_price


class RiskGuard50:
    """Rule-based hard safety shield for a $50 account."""

    @classmethod
    def calculate_risk_dollars(cls, symbol: str, entry_price: float, sl_price: float, lot: float = FIXED_LOT_SIZE) -> float:
        """Calculate exact monetary risk in USD for a 0.01 lot order."""
        return price_diff_to_usd(symbol, entry_price, sl_price, lot)

    @classmethod
    def is_rollover_period(cls) -> bool:
        """Check if current server/UTC time is during daily rollover (23:55 - 00:15 UTC)."""
        now_utc = datetime.now(timezone.utc)
        minute_of_day = now_utc.hour * 60 + now_utc.minute
        if minute_of_day >= 1435 or minute_of_day <= 15:
            return True
        return False

    @classmethod
    def resolve_sl_with_atr(
        cls,
        symbol: str,
        direction: OrderDirection,
        entry: float,
        wick_sl: float,
        atr: Optional[float] = None,
    ) -> Tuple[float, dict]:
        """
        Among wick SL and optional ATR SL, pick the farthest from entry that still
        risks <= $2.50. Reject if none fit.
        """
        cfg = SYMBOLS_CONFIG[symbol]
        meta = {
            "atr_at_entry": float(atr or 0.0),
            "k1": float(cfg.atr_k1),
            "k2": float(cfg.atr_k2),
            "use_atr_sizing": bool(cfg.use_atr_sizing),
        }
        candidates = [float(wick_sl)]
        if cfg.use_atr_sizing and atr and atr > 0:
            dist = atr_stop_distance(atr, cfg.atr_k1)
            if direction == OrderDirection.BUY:
                candidates.append(round(entry - dist, cfg.digits))
            else:
                candidates.append(round(entry + dist, cfg.digits))

        valid = []
        for sl in candidates:
            if direction == OrderDirection.BUY and sl >= entry:
                continue
            if direction == OrderDirection.SELL and sl <= entry:
                continue
            risk = price_diff_to_usd(symbol, entry, sl, FIXED_LOT_SIZE)
            if 0.05 < risk <= MAX_RISK_DOLLARS_PER_TRADE:
                valid.append((sl, risk))

        if not valid:
            meta["rejected"] = "no_sl_under_2_50"
            return wick_sl, meta

        # Farther from entry among valid
        if direction == OrderDirection.BUY:
            sl, risk = min(valid, key=lambda x: x[0])
        else:
            sl, risk = max(valid, key=lambda x: x[0])
        meta["sl_usd"] = round(risk, 4)
        return sl, meta

    @classmethod
    def evaluate_trigger(
        cls,
        alert: TriggerAlertEvent,
        current_spread_points: float,
        active_positions_count: int,
        account_equity: float,
        win_prob: float,
        atr: Optional[float] = None,
    ) -> Tuple[bool, str, Optional[TradeTicketEvent]]:
        """
        Evaluate if a sniper trigger passes the strict $50 account risk rules.
        Optional `atr` enables ATR-normalized SL when use_atr_sizing is true.
        """
        sym = alert.symbol
        cfg = SYMBOLS_CONFIG.get(sym)
        if not cfg:
            return False, f"Unknown symbol config: {sym}", None

        if active_positions_count >= MAX_CONCURRENT_POSITIONS:
            return False, f"Concurrency limit reached ({active_positions_count} active)", None

        if account_equity < 40.0:
            return False, f"Emergency drawdown lock: Equity ${account_equity:.2f} < $40.00", None

        if cls.is_rollover_period():
            return False, "Market rollover period (23:55-00:15 UTC) active", None

        if current_spread_points > cfg.max_spread_points:
            return False, f"Spread too high: {current_spread_points} > max {cfg.max_spread_points}", None

        lot = FIXED_LOT_SIZE
        entry = alert.entry_price
        wick_sl = alert.wick_sl_price

        if alert.direction == OrderDirection.BUY and wick_sl >= entry:
            return False, f"Invalid BUY SL: {wick_sl} >= entry {entry}", None
        if alert.direction == OrderDirection.SELL and wick_sl <= entry:
            return False, f"Invalid SELL SL: {wick_sl} <= entry {entry}", None

        # Spread-to-risk budget
        spread_usd = spread_points_to_usd(sym, current_spread_points, lot, mid_price=entry)
        max_spread_usd = MAX_RISK_DOLLARS_PER_TRADE * MAX_SPREAD_RISK_PCT
        if spread_usd > max_spread_usd:
            return (
                False,
                f"Spread risk ${spread_usd:.2f} > {MAX_SPREAD_RISK_PCT*100:.0f}% of "
                f"${MAX_RISK_DOLLARS_PER_TRADE:.2f} budget (${max_spread_usd:.2f})",
                None,
            )

        sl, atr_meta = cls.resolve_sl_with_atr(sym, alert.direction, entry, wick_sl, atr=atr)
        if atr_meta.get("rejected"):
            return False, "ATR/wick SL cannot fit under $2.50 risk cap", None

        if alert.direction == OrderDirection.BUY and sl >= entry:
            return False, f"Invalid BUY SL after ATR: {sl} >= entry {entry}", None
        if alert.direction == OrderDirection.SELL and sl <= entry:
            return False, f"Invalid SELL SL after ATR: {sl} <= entry {entry}", None

        risk_dollars = price_diff_to_usd(sym, entry, sl, lot)
        if risk_dollars > MAX_RISK_DOLLARS_PER_TRADE:
            return False, f"Risk exceeds limit: ${risk_dollars:.2f} > ${MAX_RISK_DOLLARS_PER_TRADE:.2f}", None
        if risk_dollars <= 0.05:
            return False, f"SL too tight / zero risk: ${risk_dollars:.2f}", None

        sl_distance = abs(entry - sl)
        trail_off = trailing_offset_price(cfg, float(atr or 0.0))

        if alert.direction == OrderDirection.BUY:
            be_trigger = entry + (sl_distance * cfg.be_trigger_rr)
            be_lock = entry + trail_off
            tp_target = entry + (sl_distance * 3.0)
        else:
            be_trigger = entry - (sl_distance * cfg.be_trigger_rr)
            be_lock = entry - trail_off
            tp_target = entry - (sl_distance * 3.0)

        ticket = TradeTicketEvent(
            ticket_id=f"TKT_{uuid.uuid4().hex[:8].upper()}",
            symbol=sym,
            direction=alert.direction,
            lot=lot,
            entry_price=round(entry, cfg.digits),
            sl_price=round(sl, cfg.digits),
            be_trigger_price=round(be_trigger, cfg.digits),
            be_lock_price=round(be_lock, cfg.digits),
            tp_target_price=round(tp_target, cfg.digits),
            risk_dollars=round(risk_dollars, 2),
            win_probability=round(win_prob, 3),
            atr_at_entry=round(float(atr or 0.0), 6),
            sl_usd=round(risk_dollars, 4),
            spread_usd=round(spread_usd, 4),
            atr_k1=float(cfg.atr_k1),
            atr_k2=float(cfg.atr_k2),
        )

        logger.info(
            f"[RiskGuard50] APPROVED: {ticket.ticket_id} {sym} {ticket.direction} "
            f"0.01 lot | Entry={ticket.entry_price} SL={ticket.sl_price} "
            f"Risk=${ticket.risk_dollars:.2f} ATR={ticket.atr_at_entry} spreadUSD=${ticket.spread_usd}"
        )
        return True, "APPROVED", ticket
