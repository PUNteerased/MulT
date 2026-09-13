"""Derive dashboard system health, alerts, and display risk caps."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


CORE_SUBSYSTEMS = (
    "data_ingestion",
    "poi_radar",
    "execution",
    "m1_sniper",
)


def build_subsystem_status(
    *,
    mt5_connected: bool,
    zmq_alive: bool,
    cooldown: bool,
) -> Dict[str, str]:
    """Map live probes → ONLINE / OFFLINE / COOLDOWN (not hardcoded ONLINE)."""
    feed = "ONLINE" if mt5_connected else "OFFLINE"
    pipe = "ONLINE" if (mt5_connected and zmq_alive) else "OFFLINE"
    return {
        "data_ingestion": feed,
        "macro_sentiment": "ONLINE",  # calendar crawler runs in dashboard process
        "poi_radar": pipe,
        "m1_sniper": pipe,
        "meta_labeling": pipe,
        "risk_guard": "COOLDOWN" if cooldown else "ONLINE",
        "execution": "ONLINE" if mt5_connected else "OFFLINE",
    }


def derive_system_state(
    *,
    red_folder: bool,
    subsystems: Dict[str, str],
    mt5_connected: bool,
) -> str:
    if red_folder:
        return "HALT_TRADING"
    offline_core = [k for k in CORE_SUBSYSTEMS if subsystems.get(k) == "OFFLINE"]
    if not mt5_connected and len(offline_core) >= 3:
        return "OFFLINE"
    if offline_core:
        return "DEGRADED"
    return "NORMAL"


def build_alerts(
    *,
    subsystems: Dict[str, str],
    mt5_connected: bool,
    red_folder: bool,
    red_title: str | None,
    cooldown: bool,
) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []
    if red_folder:
        alerts.append(
            {
                "level": "critical",
                "code": "red_folder",
                "message": f"Red folder halt: {red_title or 'high-impact news'}",
            }
        )
    if not mt5_connected:
        alerts.append(
            {
                "level": "critical",
                "code": "mt5_offline",
                "message": "MT5 terminal disconnected — account feed offline",
            }
        )
    for name in CORE_SUBSYSTEMS:
        if subsystems.get(name) == "OFFLINE":
            alerts.append(
                {
                    "level": "warning",
                    "code": f"{name}_offline",
                    "message": f"Core service offline: {name}",
                }
            )
    if cooldown:
        alerts.append(
            {
                "level": "warning",
                "code": "risk_cooldown",
                "message": "Risk Guard cool-down active — no new entries",
            }
        )
    # de-dupe by code
    seen = set()
    out = []
    for a in alerts:
        if a["code"] in seen:
            continue
        seen.add(a["code"])
        out.append(a)
    return out


def resolve_equity(account: Dict[str, Any], last_equity: float | None = None) -> Tuple[float, bool]:
    """
    Prefer live MT5 equity; else last cached equity; else demo default 50.
    Returns (equity, is_stale).
    """
    if account.get("connected") and account.get("equity") is not None:
        try:
            return float(account["equity"]), False
        except (TypeError, ValueError):
            pass
    if last_equity is not None and last_equity > 0:
        return float(last_equity), True
    try:
        eq = float(account.get("equity") or 50.0)
    except (TypeError, ValueError):
        eq = 50.0
    return eq, True
