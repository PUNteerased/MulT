"""
Unified system runtime config — editable from dashboard Settings / Risk Lab.

Persists to data/system_runtime.json. Does not rewrite settings.py / symbols.yaml.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Literal, Optional

from loguru import logger
from pydantic import BaseModel, Field, field_validator

from config.settings import (
    DATA_DIR,
    FIXED_LOT_SIZE,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_CONCURRENT_POSITIONS,
    MAX_SPREAD_RISK_PCT,
    MIN_WIN_PROBABILITY,
    RISK_COOLDOWN_AT,
    RISK_COOLDOWN_CLEAR_WINS,
    RISK_COOLDOWN_HOURS,
    RISK_DOLLARS_CEILING,
    RISK_DOLLARS_FLOOR,
    RISK_PCT_PER_TRADE,
    RISK_STREAK_HALF_AT,
    SYMBOLS_CONFIG,
    TARGET_SYMBOLS,
)

SYSTEM_RUNTIME_PATH = DATA_DIR / "system_runtime.json"
LEGACY_RISK_PATH = DATA_DIR / "risk_runtime.json"
_lock = threading.RLock()
_cache: Optional["SystemRuntime"] = None

SECTIONS = ("risk", "llm", "meta", "sniper", "calendar", "execution", "symbols")


class RiskSection(BaseModel):
    mode: Literal["pct", "fixed"] = "pct"
    risk_pct: float = Field(default=RISK_PCT_PER_TRADE, ge=0.0001, le=0.05)
    floor: float = Field(default=RISK_DOLLARS_FLOOR, ge=0.1, le=100.0)
    ceiling: float = Field(default=RISK_DOLLARS_CEILING, ge=0.1, le=100.0)
    fixed_dollars: float = Field(default=2.5, ge=0.1, le=100.0)
    max_concurrent_positions: int = Field(default=MAX_CONCURRENT_POSITIONS, ge=1, le=10)
    fixed_lot_size: float = Field(default=FIXED_LOT_SIZE, ge=0.01, le=1.0)
    max_spread_risk_pct: float = Field(default=MAX_SPREAD_RISK_PCT, ge=0.01, le=1.0)
    streak_half_at: int = Field(default=RISK_STREAK_HALF_AT, ge=1, le=20)
    cooldown_at: int = Field(default=RISK_COOLDOWN_AT, ge=1, le=50)
    cooldown_clear_wins: int = Field(default=RISK_COOLDOWN_CLEAR_WINS, ge=1, le=20)
    cooldown_hours: float = Field(default=RISK_COOLDOWN_HOURS, ge=0.1, le=168.0)

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
        d = self.model_dump()
        d["risk_cap_usd"] = self.effective_cap(equity, streak_mult)
        d["pct"] = self.risk_pct
        d["label"] = (
            f"${self.fixed_dollars:.2f} fixed"
            if self.mode == "fixed"
            else f"{self.risk_pct * 100:.2f}% eq"
        )
        return d


class LlmSection(BaseModel):
    provider: Literal["lm_studio", "openai_compatible"] = "lm_studio"
    base_url: str = LLM_BASE_URL
    model: str = LLM_MODEL
    api_key: str = LLM_API_KEY
    timeout_s: float = Field(default=90.0, ge=5.0, le=600.0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1200, ge=64, le=8000)
    enabled: bool = True

    def apply_provider_defaults(self) -> "LlmSection":
        if self.provider == "lm_studio":
            return self.model_copy(
                update={
                    "base_url": self.base_url or "http://127.0.0.1:1234/v1",
                    "api_key": self.api_key or "lm-studio",
                }
            )
        return self


class MetaSection(BaseModel):
    min_win_probability: float = Field(default=MIN_WIN_PROBABILITY, ge=0.5, le=0.99)


class SniperSection(BaseModel):
    alert_cooldown_s: float = Field(default=45.0, ge=1.0, le=600.0)
    m1_lookback: int = Field(default=60, ge=20, le=500)
    min_bars: int = Field(default=40, ge=10, le=500)
    wick_ratio_min: float = Field(default=0.35, ge=0.05, le=0.95)


class CalendarSection(BaseModel):
    enabled: bool = True
    blackout_before_min: int = Field(default=30, ge=0, le=180)
    blackout_after_min: int = Field(default=15, ge=0, le=180)
    poll_interval_sec: float = Field(default=30.0, ge=5.0, le=600.0)


class ExecutionSection(BaseModel):
    fixed_lot_size: float = Field(default=FIXED_LOT_SIZE, ge=0.01, le=1.0)
    max_concurrent_positions: int = Field(default=MAX_CONCURRENT_POSITIONS, ge=1, le=10)


class SymbolOverlay(BaseModel):
    atr_k1: Optional[float] = Field(default=None, ge=0.1, le=10.0)
    atr_k2: Optional[float] = Field(default=None, ge=0.01, le=5.0)
    max_spread_points: Optional[int] = Field(default=None, ge=1, le=100000)
    use_atr_sizing: Optional[bool] = None
    be_trigger_rr: Optional[float] = Field(default=None, ge=0.5, le=10.0)
    be_lock_pips: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    trailing_step_pips: Optional[float] = Field(default=None, ge=0.0, le=100.0)


def _default_symbols() -> Dict[str, SymbolOverlay]:
    out: Dict[str, SymbolOverlay] = {}
    for sym in TARGET_SYMBOLS:
        cfg = SYMBOLS_CONFIG.get(sym)
        if not cfg:
            continue
        out[sym] = SymbolOverlay(
            atr_k1=cfg.atr_k1,
            atr_k2=cfg.atr_k2,
            max_spread_points=cfg.max_spread_points,
            use_atr_sizing=cfg.use_atr_sizing,
            be_trigger_rr=cfg.be_trigger_rr,
            be_lock_pips=cfg.be_lock_pips,
            trailing_step_pips=cfg.trailing_step_pips,
        )
    return out


class SystemRuntime(BaseModel):
    risk: RiskSection = Field(default_factory=RiskSection)
    llm: LlmSection = Field(default_factory=LlmSection)
    meta: MetaSection = Field(default_factory=MetaSection)
    sniper: SniperSection = Field(default_factory=SniperSection)
    calendar: CalendarSection = Field(default_factory=CalendarSection)
    execution: ExecutionSection = Field(default_factory=ExecutionSection)
    symbols: Dict[str, SymbolOverlay] = Field(default_factory=_default_symbols)
    updated_at: float = Field(default_factory=time.time)

    def public_dict(self, *, mask_secrets: bool = True) -> Dict[str, Any]:
        d = self.model_dump()
        if mask_secrets and d.get("llm", {}).get("api_key"):
            key = d["llm"]["api_key"]
            d["llm"]["api_key"] = "***" if key and key not in ("", "lm-studio") else key
            d["llm"]["api_key_set"] = bool(key)
        d["risk"] = self.risk.public_dict()
        return d


def _normalize_risk_pct(payload: Dict[str, Any]) -> None:
    if "risk_pct" in payload and payload["risk_pct"] is not None:
        rp = float(payload["risk_pct"])
        if rp > 0.05:
            payload["risk_pct"] = rp / 100.0


def _migrate_legacy_risk() -> Optional[Dict[str, Any]]:
    if not LEGACY_RISK_PATH.exists():
        return None
    try:
        data = json.loads(LEGACY_RISK_PATH.read_text(encoding="utf-8"))
        _normalize_risk_pct(data)
        return data
    except Exception as e:
        logger.warning(f"[SystemRuntime] legacy risk migrate skip: {e}")
        return None


def defaults() -> SystemRuntime:
    return SystemRuntime()


def _sync_legacy_risk(rt: SystemRuntime) -> None:
    try:
        LEGACY_RISK_PATH.write_text(
            json.dumps(
                {
                    "mode": rt.risk.mode,
                    "risk_pct": rt.risk.risk_pct,
                    "floor": rt.risk.floor,
                    "ceiling": rt.risk.ceiling,
                    "fixed_dollars": rt.risk.fixed_dollars,
                    "updated_at": rt.updated_at,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def load_settings(*, force: bool = False) -> SystemRuntime:
    global _cache
    with _lock:
        if _cache is not None and not force:
            return _cache
        if SYSTEM_RUNTIME_PATH.exists():
            try:
                raw = json.loads(SYSTEM_RUNTIME_PATH.read_text(encoding="utf-8"))
                _cache = SystemRuntime(**raw)
                _sync_legacy_risk(_cache)
                return _cache
            except Exception as e:
                logger.warning(f"[SystemRuntime] bad file, using defaults: {e}")

        rt = defaults()
        legacy = _migrate_legacy_risk()
        if legacy:
            try:
                rt.risk = RiskSection(**{**rt.risk.model_dump(), **legacy})
                logger.info("[SystemRuntime] migrated risk_runtime.json → system_runtime")
            except Exception as e:
                logger.warning(f"[SystemRuntime] legacy risk merge failed: {e}")
        _cache = rt
        try:
            SYSTEM_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
            SYSTEM_RUNTIME_PATH.write_text(rt.model_dump_json(indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"[SystemRuntime] initial write skip: {e}")
        _sync_legacy_risk(rt)
        return _cache


def save_settings(payload: Dict[str, Any], section: Optional[str] = None) -> SystemRuntime:
    """
    Merge payload into runtime.
    - section=None: payload may contain top-level section keys
    - section='risk': payload is risk fields only
    """
    global _cache
    with _lock:
        current = load_settings(force=True)
        data = current.model_dump()

        if section:
            if section not in SECTIONS:
                raise ValueError(f"unknown section: {section}")
            patch = dict(payload)
            if section == "risk":
                _normalize_risk_pct(patch)
            if section == "llm" and patch.get("api_key") in (None, "", "***"):
                patch.pop("api_key", None)
            if section == "symbols":
                # payload is {EURUSD: {...}, ...}
                merged_syms = {k: (v if isinstance(v, dict) else {}) for k, v in data["symbols"].items()}
                for sym, ov in patch.items():
                    if isinstance(ov, dict):
                        merged_syms[sym] = {**merged_syms.get(sym, {}), **ov}
                data["symbols"] = merged_syms
            else:
                data[section] = {**data[section], **patch}
        else:
            for sec in SECTIONS:
                if sec in payload and isinstance(payload[sec], dict):
                    patch = dict(payload[sec])
                    if sec == "risk":
                        _normalize_risk_pct(patch)
                    if sec == "llm" and patch.get("api_key") in (None, "", "***"):
                        patch.pop("api_key", None)
                    if sec == "symbols":
                        merged_syms = {k: dict(v) for k, v in data["symbols"].items()}
                        for sym, ov in patch.items():
                            if isinstance(ov, dict):
                                merged_syms[sym] = {**merged_syms.get(sym, {}), **ov}
                        data["symbols"] = merged_syms
                    else:
                        data[sec] = {**data[sec], **patch}

        data["updated_at"] = time.time()
        if data.get("llm"):
            llm = LlmSection(**data["llm"]).apply_provider_defaults()
            data["llm"] = llm.model_dump()

        rt = SystemRuntime(**data)
        if rt.risk.ceiling < rt.risk.floor:
            rt.risk.ceiling = rt.risk.floor

        SYSTEM_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYSTEM_RUNTIME_PATH.write_text(rt.model_dump_json(indent=2), encoding="utf-8")
        _sync_legacy_risk(rt)
        _cache = rt
        logger.info(f"[SystemRuntime] saved sections updated_at={rt.updated_at}")
        return rt


def get_section(name: str) -> Any:
    rt = load_settings()
    if name not in SECTIONS:
        raise ValueError(f"unknown section: {name}")
    return getattr(rt, name)


def merged_symbol_config(symbol: str):
    """Return SymbolConfig-like object with runtime overlay applied."""
    base = SYMBOLS_CONFIG.get(symbol)
    if base is None:
        return None
    ov = load_settings().symbols.get(symbol)
    if ov is None:
        return base
    data = base.model_dump()
    for k, v in ov.model_dump(exclude_none=True).items():
        data[k] = v
    from config.settings import SymbolConfig

    return SymbolConfig(**data)
