"""
Offline pipeline backtest: wick-sweep style entries + RiskGuard50 + fixed R exits.

Does not call MT5 or cloud LLMs. Uses DuckDB/parquet history or synthetic bars.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger

from config.settings import (
    FIXED_LOT_SIZE,
    RISK_DOLLARS_CEILING,
    RISK_PCT_PER_TRADE,
    SYMBOLS_CONFIG,
    VALIDATION_REPORTS_DIR,
)
from core.bus.events import OrderDirection, TriggerAlertEvent
from core.risk.money import atr_from_ohlc_df, pnl_to_usd
from subsystems.risk_guard.guard_50 import RiskGuard50
from subsystems.validation.calibration import calibration_summary
from subsystems.validation.metrics import summarize_trades
from subsystems.validation.replay import load_replay_bars


def _detect_sweep(df, i: int, lookback: int = 20) -> Optional[str]:
    """Simple liquidity-sweep heuristic: pierce prior swing then close back inside."""
    if i < lookback + 2:
        return None
    window = df.iloc[i - lookback : i]
    prior_high = float(window["high"].max())
    prior_low = float(window["low"].min())
    row = df.iloc[i]
    hi, lo, cl, op = float(row["high"]), float(row["low"]), float(row["close"]), float(row["open"])
    # Bearish sweep then reclaim (SELL)
    if hi > prior_high and cl < prior_high and cl < op:
        return "SELL"
    # Bullish sweep then reclaim (BUY)
    if lo < prior_low and cl > prior_low and cl > op:
        return "BUY"
    return None


def _simulate_exit(
    df,
    entry_i: int,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    be_trigger: float,
    be_lock: float,
    max_bars: int = 240,
) -> Dict[str, Any]:
    """Bar-based exit: SL / TP / BE lock then trail-ish lock; no tick trail."""
    current_sl = sl
    be_applied = False
    end = min(len(df) - 1, entry_i + max_bars)
    for j in range(entry_i + 1, end + 1):
        hi = float(df.iloc[j]["high"])
        lo = float(df.iloc[j]["low"])
        cl = float(df.iloc[j]["close"])
        if direction == "BUY":
            if not be_applied and hi >= be_trigger:
                current_sl = max(current_sl, be_lock)
                be_applied = True
            if lo <= current_sl:
                return {"exit": current_sl, "status": "CLOSED_SL" if not be_applied else "CLOSED_BE", "exit_i": j}
            if hi >= tp:
                return {"exit": tp, "status": "CLOSED_TP", "exit_i": j}
        else:
            if not be_applied and lo <= be_trigger:
                current_sl = min(current_sl, be_lock)
                be_applied = True
            if hi >= current_sl:
                return {"exit": current_sl, "status": "CLOSED_SL" if not be_applied else "CLOSED_BE", "exit_i": j}
            if lo <= tp:
                return {"exit": tp, "status": "CLOSED_TP", "exit_i": j}
    return {"exit": float(df.iloc[end]["close"]), "status": "CLOSED_TIME", "exit_i": end}


def run_pipeline_backtest(
    symbol: str,
    months: float = 6.0,
    allow_synthetic: bool = True,
    win_prob: float = 0.80,
    max_trades: int = 200,
) -> Dict[str, Any]:
    cfg = SYMBOLS_CONFIG.get(symbol)
    if not cfg:
        raise ValueError(f"Unknown symbol: {symbol}")

    df = load_replay_bars(symbol, months=months, allow_synthetic=allow_synthetic)
    trades: List[Dict[str, Any]] = []
    rejects = {"risk": 0, "spread": 0, "other": 0}
    i = 40
    cooldown_until = 0

    while i < len(df) - 5 and len(trades) < max_trades:
        if i < cooldown_until:
            i += 1
            continue
        side = _detect_sweep(df, i)
        if not side:
            i += 1
            continue

        row = df.iloc[i]
        entry = float(row["close"])
        spread_pts = float(row.get("spread", 15))
        # Wick SL = extreme of signal bar with small buffer
        if side == "BUY":
            wick_sl = float(row["low"]) - cfg.pip_multiplier
            direction = OrderDirection.BUY
        else:
            wick_sl = float(row["high"]) + cfg.pip_multiplier
            direction = OrderDirection.SELL

        atr = atr_from_ohlc_df(df.iloc[max(0, i - 40) : i + 1], period=14)
        alert = TriggerAlertEvent(
            alert_id=f"BT_{uuid.uuid4().hex[:8]}",
            symbol=symbol,
            direction=direction,
            entry_price=entry,
            wick_sl_price=round(wick_sl, cfg.digits),
            model_confidence=win_prob,
        )
        ok, reason, ticket = RiskGuard50.evaluate_trigger(
            alert=alert,
            current_spread_points=spread_pts,
            active_positions_count=0,
            account_equity=50.0,
            win_prob=win_prob,
            atr=atr if atr > 0 else None,
            streak_state={"loss_streak": 0, "win_streak": 0, "multiplier": 1.0, "cooldown": False, "reason": "backtest"},
        )
        if not ok or not ticket:
            if reason and "Spread" in reason:
                rejects["spread"] += 1
            elif reason and ("Risk" in reason or "risk cap" in reason.lower() or "Cool-down" in reason):
                rejects["risk"] += 1
            else:
                rejects["other"] += 1
            i += 1
            continue

        exit_info = _simulate_exit(
            df,
            i,
            side,
            ticket.entry_price,
            ticket.sl_price,
            ticket.tp_target_price,
            ticket.be_trigger_price,
            ticket.be_lock_price,
        )
        pnl = pnl_to_usd(symbol, ticket.entry_price, exit_info["exit"], FIXED_LOT_SIZE, side)
        trades.append(
            {
                "ticket_id": ticket.ticket_id,
                "symbol": symbol,
                "direction": side,
                "entry": ticket.entry_price,
                "sl": ticket.sl_price,
                "exit": exit_info["exit"],
                "pnl": round(pnl, 4),
                "status": exit_info["status"],
                "risk_dollars": ticket.risk_dollars,
                "sl_usd": ticket.sl_usd,
                "spread_usd": ticket.spread_usd,
                "atr_at_entry": ticket.atr_at_entry,
                "atr_k1": ticket.atr_k1,
                "atr_k2": ticket.atr_k2,
                "win_probability": win_prob,
                "bar_time": int(row["time"]),
            }
        )
        cooldown_until = exit_info["exit_i"] + 5
        i = exit_info["exit_i"] + 1

    metrics = summarize_trades(trades)
    calib = calibration_summary(trades)
    report = {
        "symbol": symbol,
        "months": months,
        "generated_at": time.time(),
        "n_bars": len(df),
        "rejects": rejects,
        "metrics": metrics,
        "calibration": calib,
        "max_risk_cap": RiskGuard50.compute_max_risk_dollars(50.0),
        "risk_pct": RISK_PCT_PER_TRADE,
        "risk_ceiling": RISK_DOLLARS_CEILING,
        "atr_defaults": {"k1": cfg.atr_k1, "k2": cfg.atr_k2, "tf": cfg.atr_timeframe_sl},
        "trades": trades,
        "source_note": "Offline pipeline backtest (sweep heuristic + RiskGuard50). Not tick-level trail.",
    }
    return report


def write_report(report: Dict[str, Any], out_dir: Optional[Path] = None) -> Path:
    out = Path(out_dir or VALIDATION_REPORTS_DIR)
    out.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = out / f"backtest_{report['symbol']}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"[Validation] Wrote {path}")
    return path
