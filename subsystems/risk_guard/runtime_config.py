"""
Risk runtime thin wrapper — delegates to system_runtime.risk section.
Keeps GET/POST /api/risk/config working.
"""
from __future__ import annotations

from typing import Any, Dict

from subsystems.config.system_runtime import (
    RiskSection,
    load_settings,
    save_settings,
)

# Back-compat alias for tests that patch RUNTIME_PATH
from config.settings import DATA_DIR

RUNTIME_PATH = DATA_DIR / "risk_runtime.json"


def load_risk_config(*, force: bool = False) -> RiskSection:
    return load_settings(force=force).risk


def save_risk_config(payload: Dict[str, Any]) -> RiskSection:
    rt = save_settings(payload, section="risk")
    return rt.risk
