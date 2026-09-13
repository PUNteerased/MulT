"""
Anti-martingale streak / cool-down helpers for RiskGuard50.

Reads recent closed trade PnLs from DuckDB (best-effort).
Never writes config.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger

from config.settings import (
    DUCKDB_PATH,
    RISK_COOLDOWN_AT,
    RISK_COOLDOWN_CLEAR_WINS,
    RISK_COOLDOWN_HOURS,
    RISK_STREAK_HALF_AT,
)


def get_recent_closed_pnls(limit: int = 20) -> List[Tuple[float, float]]:
    """
    Return list of (pnl, exit_timestamp) newest-first for closed trades.
    Empty on missing DB / errors.
    """
    try:
        import duckdb
        from pathlib import Path

        path = Path(DUCKDB_PATH)
        if not path.exists():
            return []
        con = duckdb.connect(str(path), read_only=True)
        rows = con.execute(
            """
            SELECT pnl, COALESCE(exit_timestamp, entry_timestamp, 0)
            FROM trade_logs
            WHERE status IS NOT NULL
              AND upper(status) LIKE 'CLOSED%'
              AND pnl IS NOT NULL
            ORDER BY COALESCE(exit_timestamp, entry_timestamp, 0) DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        con.close()
        out: List[Tuple[float, float]] = []
        for pnl, ts in rows:
            out.append((float(pnl or 0.0), float(ts or 0.0)))
        return out
    except Exception as e:
        logger.debug(f"[RiskStreak] DuckDB read skipped: {e}")
        return []


def compute_streak_state(
    pnls: Union[List[Tuple[float, float]], List[float]],
    now: Optional[float] = None,
    *,
    half_at: int = RISK_STREAK_HALF_AT,
    cooldown_at: int = RISK_COOLDOWN_AT,
    clear_wins: int = RISK_COOLDOWN_CLEAR_WINS,
    cooldown_hours: float = RISK_COOLDOWN_HOURS,
) -> Dict[str, Any]:
    """
    From newest-first closed PnLs, compute loss/win streaks and risk multiplier.

    Cool-down when loss_streak >= cooldown_at, unless:
      - win_streak >= clear_wins at the front, OR
      - newest trade is older than cooldown_hours (time expired)
    """
    now = now if now is not None else time.time()
    normalized: List[Tuple[float, float]] = []
    for item in pnls:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            normalized.append((float(item[0]), float(item[1])))
        else:
            normalized.append((float(item), now))

    loss_streak = 0
    win_streak = 0
    newest_ts = normalized[0][1] if normalized else 0.0

    for pnl, _ts in normalized:
        if pnl < 0:
            if win_streak > 0:
                break
            loss_streak += 1
        elif pnl > 0:
            if loss_streak > 0:
                break
            win_streak += 1
        else:
            break

    age_hours = (now - newest_ts) / 3600.0 if newest_ts > 0 else 999.0
    time_cleared = newest_ts > 0 and age_hours >= cooldown_hours

    # If we are currently on a win streak that clears cool-down, not in cool-down
    cooldown = False
    reason = "ok"
    multiplier = 1.0

    if loss_streak >= cooldown_at and not time_cleared:
        cooldown = True
        reason = f"cool_down_losses={loss_streak}"
        multiplier = 0.0
    elif loss_streak >= half_at and not time_cleared:
        multiplier = 0.5
        reason = f"half_risk_losses={loss_streak}"
    elif win_streak >= clear_wins:
        multiplier = 1.0
        reason = f"cleared_by_wins={win_streak}"
    elif time_cleared and loss_streak >= half_at:
        multiplier = 1.0
        reason = f"cleared_by_time_h={age_hours:.1f}"
    else:
        reason = "full_risk"

    return {
        "loss_streak": loss_streak,
        "win_streak": win_streak,
        "multiplier": multiplier,
        "cooldown": cooldown,
        "reason": reason,
        "newest_ts": newest_ts,
        "age_hours": age_hours,
    }


def load_streak_state(now: Optional[float] = None) -> Dict[str, Any]:
    return compute_streak_state(get_recent_closed_pnls(), now=now)
