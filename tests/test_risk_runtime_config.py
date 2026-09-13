"""Tests for runtime risk config (pct vs fixed)."""
from pathlib import Path

from subsystems.risk_guard.guard_50 import RiskGuard50
from subsystems.risk_guard import runtime_config as rc


def test_runtime_pct_and_fixed(tmp_path, monkeypatch):
    path = tmp_path / "risk_runtime.json"
    monkeypatch.setattr(rc, "RUNTIME_PATH", path)
    monkeypatch.setattr(rc, "_cache", None)

    cfg = rc.save_risk_config(
        {"mode": "pct", "risk_pct": 0.5, "floor": 1.0, "ceiling": 5.0}
    )
    assert abs(cfg.risk_pct - 0.005) < 1e-9  # 0.5 entered as percent points
    assert abs(RiskGuard50.compute_max_risk_dollars(760.0) - 3.8) < 1e-6

    cfg2 = rc.save_risk_config({"mode": "fixed", "fixed_dollars": 2.5})
    assert cfg2.mode == "fixed"
    assert RiskGuard50.compute_max_risk_dollars(50.0) == 2.5
    assert RiskGuard50.compute_max_risk_dollars(1200.0) == 2.5
    assert path.exists()
