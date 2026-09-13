"""
Runtime risk config editable from the dashboard.

Persists to data/risk_runtime.json — does not rewrite settings.py.
RiskGuard50 reads this on every compute_max_risk_dollars call.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from loguru import logger
from pydantic import BaseModel, Field, field_validator

from config.settings import (
    DATA_DIR,
    RISK_DOLLARS_CEILING,
    RISK_DOLLARS_FLOOR,
    RISK_PCT_PER_TRADE,
)

RUNTIME_PATH = DATA_DIR / "risk_runtime.json"
_lock = threading.RLock()
_cache: Optional["RiskRuntimeConfig"] = None


class RiskRuntimeConfig(BaseModel):
    mode: Literal["pct", "fixed"] = "pct"
    risk_pct: float = Field(default=RISK_PCT_PER_TRADE, ge=0.0001, le=0.05)
    floor: float = Field(default=RISK_DOLLARS_FLOOR, ge=0.1, le=100.0)
    ceiling: float = Field(default=RISK_DOLLARS_CEILING, ge=0.1, le=100.0)
    fixed_dollars: float = Field(default=2.5, ge=0.1, le=100.0)
    updated_at: float = Field(default_factory=time.time)

    @field_validator("ceiling")
    @classmethod
    def ceiling_gte_floor(cls, v: float, info):
        floor = info.data.get("floor")
        if floor is not None and v < floor:
            raise ValueError("ceiling must be >= floor")
        return v

    def effective_cap(self, equity: float, streak_mult: float = 1.0) -> float:
        mult = max(0.0, float(streak_mult))
        if self.mode == "fixed":
            base = float(self.fixed_dollars)
        else:
            raw = max(0.0, float(equity)) * float(self.risk_pct)
            base = min(float(self.ceiling), max(float(self.floor), raw))
        return round(base * mult, 4)

    def public_dict(self, equity: float = 50.0, streak_mult: float = 1.0) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "risk_pct": self.risk_pct,
            "floor": self.floor,
            "ceiling": self.ceiling,
            "fixed_dollars": self.fixed_dollars,
            "updated_at": self.updated_at,
            "risk_cap_usd": self.effective_cap(equity, streak_mult),
            "label": (
                f"${self.fixed_dollars:.2f} fixed"
                if self.mode == "fixed"
                else f"{self.risk_pct * 100:.2f}% eq"
            ),
        }


def _defaults() -> RiskRuntimeConfig:
    return RiskRuntimeConfig()


def load_risk_config(*, force: bool = False) -> RiskRuntimeConfig:
    global _cache
    with _lock:
        if _cache is not None and not force:
            return _cache
        if RUNTIME_PATH.exists():
            try:
                data = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
                _cache = RiskRuntimeConfig(**data)
                return _cache
            except Exception as e:
                logger.warning(f"[RiskRuntime] bad file, using defaults: {e}")
        _cache = _defaults()
        return _cache


def save_risk_config(payload: Dict[str, Any]) -> RiskRuntimeConfig:
    global _cache
    with _lock:
        current = load_risk_config(force=True)
        merged = current.model_dump()
        for k in ("mode", "risk_pct", "floor", "ceiling", "fixed_dollars"):
            if k in payload and payload[k] is not None:
                merged[k] = payload[k]
        # UX: if user types percent as 0.5 meaning 0.5%, accept values > 0.05 as percent points
        if "risk_pct" in payload and payload["risk_pct"] is not None:
            rp = float(payload["risk_pct"])
            if rp > 0.05:  # e.g. 0.5 or 1 meaning 0.5% / 1%
                merged["risk_pct"] = rp / 100.0
        merged["updated_at"] = time.time()
        cfg = RiskRuntimeConfig(**merged)
        if cfg.ceiling < cfg.floor:
            cfg.ceiling = cfg.floor
        RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_PATH.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
        _cache = cfg
        logger.info(f"[RiskRuntime] saved mode={cfg.mode} pct={cfg.risk_pct} fixed={cfg.fixed_dollars}")
        return cfg
