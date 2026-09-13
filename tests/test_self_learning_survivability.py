"""
Tests for self-learning survivability: shadow log, registry, expectancy gate, PSI, halt.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.memory.duckdb_manager import DuckDBManager
from subsystems.evolution.expectancy_gate import (
    evaluate_promotion,
    expectancy,
    expected_calibration_error,
    metrics_from_shadow_frame,
)
from subsystems.evolution.drift_monitor import check_drift, psi_for_feature, snapshot_from_matrix
from subsystems.evolution import model_registry, halt_state
from subsystems.evolution.weekend_learner import WeekendSelfEvolutionWorker
from subsystems.meta_labeling.lgbm_filter import FEATURE_NAMES, LightGBMMetaFilter


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    DuckDBManager.reset_instance()
    db_path = str(tmp_path / "test.duckdb")
    monkeypatch.setattr("config.settings.DUCKDB_PATH", db_path)
    monkeypatch.setattr("core.memory.duckdb_manager.DUCKDB_PATH", db_path)
    db = DuckDBManager(db_path)
    yield db
    DuckDBManager.reset_instance()


def test_shadow_signal_roundtrip(fresh_db):
    fresh_db.log_shadow_signal(
        {
            "symbol": "EURUSD",
            "direction": "BUY",
            "gate": "meta",
            "win_prob": 0.61,
            "challenger_win_prob": 0.72,
            "features_json": json.dumps({"rsi": 30.0}),
            "reason": "below_threshold",
            "alert_id": "ALT_TEST",
        }
    )
    df = fresh_db.get_shadow_signals(limit=10)
    assert len(df) == 1
    assert df.iloc[0]["gate"] == "meta"
    assert float(df.iloc[0]["win_prob"]) == pytest.approx(0.61)


def test_expectancy_gate_blocks_worse_calibration():
    champ = {"expectancy": 0.5, "ece": 0.05, "max_dd": 2.0, "n_signals": 40}
    chall = {
        "expectancy": 1.0,
        "expectancy_ci_low": 0.8,
        "ece": 0.20,
        "max_dd": 1.5,
        "n_signals": 40,
    }
    ok, reasons = evaluate_promotion(champ, chall, min_signals=30)
    assert ok is False
    assert any("calibration" in r for r in reasons)


def test_expectancy_gate_passes_when_better():
    champ = {"expectancy": 0.1, "ece": 0.15, "max_dd": 5.0, "n_signals": 40}
    chall = {
        "expectancy": 0.5,
        "expectancy_ci_low": 0.3,
        "ece": 0.10,
        "max_dd": 4.0,
        "n_signals": 40,
    }
    ok, reasons = evaluate_promotion(champ, chall, min_signals=30, max_dd_worsen_pct=0.25)
    assert ok is True


def test_psi_detects_shift():
    base = np.random.normal(0, 1, 500)
    shifted = np.random.normal(2, 1, 500)
    psi = psi_for_feature(base, shifted)
    assert psi > 0.1


def test_drift_check_breach():
    X = np.random.normal(0, 1, size=(200, len(FEATURE_NAMES)))
    snap = snapshot_from_matrix(X, FEATURE_NAMES)
    live = [{n: float(np.random.normal(3, 1)) for n in FEATURE_NAMES} for _ in range(100)]
    res = check_drift(snap, live, threshold=0.1, feature_names=FEATURE_NAMES)
    assert res["breached"] is True


def test_model_registry_challenger_not_champion(tmp_path, monkeypatch):
    monkeypatch.setattr(model_registry, "MODELS_DIR", tmp_path)
    monkeypatch.setattr(model_registry, "REGISTRY_ROOT", tmp_path / "registry")
    monkeypatch.setattr(model_registry, "ACTIVE_DIR", tmp_path / "active")
    monkeypatch.setattr(model_registry, "POINTER_PATH", tmp_path / "champion_pointer.json")

    # Fake model file
    src = tmp_path / "m1.txt"
    src.write_text("dummy", encoding="utf-8")
    vid_c = model_registry.register_lgbm(src, role="champion", metrics={"n": 1})
    src2 = tmp_path / "m2.txt"
    src2.write_text("dummy2", encoding="utf-8")
    vid_ch = model_registry.register_lgbm(src2, role="challenger", metrics={"n": 2})
    ptr = json.loads((tmp_path / "champion_pointer.json").read_text(encoding="utf-8"))
    assert ptr["lgbm"] == vid_c
    assert ptr["challenger_lgbm"] == vid_ch
    promoted = model_registry.promote_challenger_lgbm()
    assert promoted == vid_ch
    ptr2 = json.loads((tmp_path / "champion_pointer.json").read_text(encoding="utf-8"))
    assert ptr2["lgbm"] == vid_ch
    assert ptr2["challenger_lgbm"] is None


def test_halt_human_reset(tmp_path, monkeypatch):
    monkeypatch.setattr(halt_state, "HALT_STATE_PATH", tmp_path / "halt_state.json")
    halt_state.lock_halt("test_dd")
    assert halt_state.is_halt_locked() is True
    halt_state.human_reset_halt("ok")
    assert halt_state.is_halt_locked() is False


def test_purged_walk_forward_splits():
    splits = WeekendSelfEvolutionWorker.purged_walk_forward_splits(60, n_folds=3, embargo=5)
    assert len(splits) >= 1
    for train_idx, test_idx in splits:
        assert train_idx.max() < test_idx.min() - 4  # embargo gap


def test_metrics_from_shadow_frame():
    probs = [0.8, 0.7, 0.2, 0.3]
    outcomes = [1, 1, 0, 0]
    pnls = [1.0, 0.5, -0.8, -0.4]
    m = metrics_from_shadow_frame(probs, outcomes, pnls)
    assert m["n"] == 4
    assert m["expectancy"] == pytest.approx(expectancy(pnls))
    assert m["ece"] == pytest.approx(expected_calibration_error(probs, outcomes))


@pytest.mark.asyncio
async def test_feature_persistence_on_close(fresh_db):
    from core.bus.events import TradeTicketEvent, OrderDirection
    from subsystems.execution.mt5_router import MT5OrderRouter

    router = MT5OrderRouter(dry_run=True)
    feats = {"model_confidence": 0.9, "rsi": 28.0}
    ticket = TradeTicketEvent(
        ticket_id="TKT_FEAT",
        symbol="EURUSD",
        direction=OrderDirection.BUY,
        lot=0.01,
        entry_price=1.08500,
        sl_price=1.08400,
        be_trigger_price=1.08650,
        be_lock_price=1.08520,
        tp_target_price=1.08800,
        risk_dollars=1.00,
        win_probability=0.82,
        features_json=json.dumps(feats),
        alert_id="ALT_1",
    )
    await router.send_order(ticket)
    await router._handle_position_closed(exit_price=1.08600)
    logs = fresh_db.get_trade_logs()
    assert len(logs) >= 1
    parsed = json.loads(logs.iloc[0]["features_json"])
    assert parsed.get("model_confidence") == 0.9
