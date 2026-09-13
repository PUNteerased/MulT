"""
Persistent halt / equity-peak state for survivability circuit breaker.
Human reset only when halt_requires_human_reset is enabled.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional

from loguru import logger

from config.settings import DATA_DIR

HALT_STATE_PATH = DATA_DIR / "halt_state.json"
_lock = threading.RLock()


def _defaults() -> Dict[str, Any]:
    return {
        "equity_peak": 0.0,
        "halt_locked": False,
        "halt_reason": "",
        "halt_at": None,
        "updated_at": time.time(),
    }


def load_halt_state() -> Dict[str, Any]:
    with _lock:
        if not HALT_STATE_PATH.exists():
            return _defaults()
        try:
            data = json.loads(HALT_STATE_PATH.read_text(encoding="utf-8"))
            base = _defaults()
            base.update(data)
            return base
        except Exception as e:
            logger.warning(f"[HaltState] load failed: {e}")
            return _defaults()


def save_halt_state(data: Dict[str, Any]) -> None:
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = dict(data)
        data["updated_at"] = time.time()
        HALT_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def update_equity_peak(equity: float) -> float:
    """Raise peak watermark; return current peak."""
    st = load_halt_state()
    peak = float(st.get("equity_peak") or 0.0)
    eq = float(equity)
    if eq > peak:
        st["equity_peak"] = eq
        save_halt_state(st)
        return eq
    return peak


def peak_drawdown_pct(equity: float) -> float:
    st = load_halt_state()
    peak = float(st.get("equity_peak") or 0.0)
    if peak <= 0:
        return 0.0
    return max(0.0, (peak - float(equity)) / peak)


def lock_halt(reason: str) -> Dict[str, Any]:
    st = load_halt_state()
    st["halt_locked"] = True
    st["halt_reason"] = reason
    st["halt_at"] = time.time()
    save_halt_state(st)
    logger.critical(f"[HaltState] LOCKED: {reason}")
    return st


def human_reset_halt(note: str = "human_reset") -> Dict[str, Any]:
    st = load_halt_state()
    st["halt_locked"] = False
    st["halt_reason"] = ""
    st["last_reset_note"] = note
    st["last_reset_at"] = time.time()
    save_halt_state(st)
    logger.info(f"[HaltState] human reset: {note}")
    return st


def is_halt_locked() -> bool:
    return bool(load_halt_state().get("halt_locked"))
