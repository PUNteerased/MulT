"""
$50 Fixed-Point Risk Guard Subsystem.
Strict rule-based gatekeeper with zero AI hallucination.
Enforces hard $2.50 max loss limit, 0.01 lot size, spread filter, and single-trade concurrency.
"""
from datetime import datetime, timezone
from typing import Tuple, Optional
import MetaTrader5 as mt5
from loguru import logger

from config.settings import (
    MAX_RISK_DOLLARS_PER_TRADE,
    MAX_CONCURRENT_POSITIONS,
    FIXED_LOT_SIZE,
    SYMBOLS_CONFIG,
    SymbolConfig
)
from core.bus.events import OrderDirection, TriggerAlertEvent, TradeTicketEvent

class RiskGuard50:
    """Rule-based hard safety shield for a $50 account."""

    @classmethod
    def calculate_risk_dollars(cls, symbol: str, entry_price: float, sl_price: float, lot: float = FIXED_LOT_SIZE) -> float:
        """Calculate exact monetary risk in USD for a 0.01 lot order."""
        cfg = SYMBOLS_CONFIG.get(symbol)
        if not cfg:
            return 999.0  # Unknown symbol, reject

        price_diff = abs(entry_price - sl_price)

        if symbol == "EURUSD":
            # 1 pip = 0.0001. For 0.01 lot, 1 pip = $0.10
            pips = price_diff / cfg.pip_multiplier
            return pips * 0.10
        elif symbol == "USDJPY":
            # 1 pip = 0.01. For 0.01 lot, 1 pip = (0.01 / entry_price) * 1000
            pips = price_diff / cfg.pip_multiplier
            pip_val_usd = (cfg.pip_multiplier / entry_price) * (cfg.contract_size * lot)
            return pips * pip_val_usd
        elif symbol == "XAUUSD":
            # Contract size = 100 oz. 0.01 lot = 1 oz. $1 price change = $1.00
            return price_diff * 1.0
        elif symbol == "BTCUSD":
            # Contract size = 1 BTC. 0.01 lot = 0.01 BTC. $100 price change = $1.00
            return price_diff * 0.01
        else:
            # Generic fallback
            points = price_diff / cfg.point
            return points * (cfg.pip_value_usd_per_lot / 10.0) * lot

    @classmethod
    def is_rollover_period(cls) -> bool:
        """Check if current server/UTC time is during daily rollover (23:55 - 00:15 UTC)."""
        now_utc = datetime.now(timezone.utc)
        minute_of_day = now_utc.hour * 60 + now_utc.minute
        # 23:55 (1435) to 00:15 (15)
        if minute_of_day >= 1435 or minute_of_day <= 15:
            return True
        return False

    @classmethod
    def evaluate_trigger(
        cls,
        alert: TriggerAlertEvent,
        current_spread_points: float,
        active_positions_count: int,
        account_equity: float,
        win_prob: float
    ) -> Tuple[bool, str, Optional[TradeTicketEvent]]:
        """
        Evaluate if a sniper trigger passes the strict $50 account risk rules.
        Returns (is_approved, reject_reason, trade_ticket).
        """
        sym = alert.symbol
        cfg = SYMBOLS_CONFIG.get(sym)
        if not cfg:
            return False, f"Unknown symbol config: {sym}", None

        # 1. Concurrency limit: Maximum 1 position active across entire account
        if active_positions_count >= MAX_CONCURRENT_POSITIONS:
            return False, f"Concurrency limit reached ({active_positions_count} active)", None

        # 2. Emergency equity guard: Never trade if equity dropped below $40.00
        if account_equity < 40.0:
            return False, f"Emergency drawdown lock: Equity ${account_equity:.2f} < $40.00", None

        # 3. Rollover time filter (widened spreads & swap gap)
        if cls.is_rollover_period():
            return False, "Market rollover period (23:55-00:15 UTC) active", None

        # 4. Spread filter
        if current_spread_points > cfg.max_spread_points:
            return False, f"Spread too high: {current_spread_points} > max {cfg.max_spread_points}", None

        # 5. Fixed lot size validation
        lot = FIXED_LOT_SIZE

        # 6. Directional sanity check
        entry = alert.entry_price
        sl = alert.wick_sl_price
        if alert.direction == OrderDirection.BUY and sl >= entry:
            return False, f"Invalid BUY SL: {sl} >= entry {entry}", None
        if alert.direction == OrderDirection.SELL and sl <= entry:
            return False, f"Invalid SELL SL: {sl} <= entry {entry}", None

        # 7. THE $50 RULE: Hard $2.50 maximum loss cap (5% of $50)
        risk_dollars = cls.calculate_risk_dollars(sym, entry, sl, lot)
        if risk_dollars > MAX_RISK_DOLLARS_PER_TRADE:
            return False, f"Risk exceeds limit: ${risk_dollars:.2f} > ${MAX_RISK_DOLLARS_PER_TRADE:.2f}", None

        if risk_dollars <= 0.05:
            return False, f"SL too tight / zero risk: ${risk_dollars:.2f}", None

        # 8. Calculate Break-Even & Trailing Targets
        sl_distance = abs(entry - sl)
        pip_distance = cfg.pip_multiplier

        if alert.direction == OrderDirection.BUY:
            be_trigger = entry + (sl_distance * cfg.be_trigger_rr)
            be_lock = entry + (cfg.be_lock_pips * pip_distance)
            tp_target = entry + (sl_distance * 3.0)  # Initial anchor target
        else:
            be_trigger = entry - (sl_distance * cfg.be_trigger_rr)
            be_lock = entry - (cfg.be_lock_pips * pip_distance)
            tp_target = entry - (sl_distance * 3.0)

        import uuid
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
            win_probability=round(win_prob, 3)
        )

        logger.info(
            f"[RiskGuard50] APPROVED: {ticket.ticket_id} {sym} {ticket.direction} "
            f"0.01 lot | Entry={ticket.entry_price} SL={ticket.sl_price} "
            f"Risk=${ticket.risk_dollars:.2f} | BE_Trigger={ticket.be_trigger_price}"
        )
        return True, "APPROVED", ticket
