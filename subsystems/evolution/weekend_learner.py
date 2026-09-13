"""
Weekend Self-Evolution Subsystem.
Trains LightGBM challengers via purged walk-forward; never overwrites champion.
CNN fine-tune is skipped until real M1 window store exists (Phase B2).
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import numpy as np
import pandas as pd
from loguru import logger

from config.settings import DATA_DIR, MODELS_DIR
from core.memory.duckdb_manager import DuckDBManager
from subsystems.meta_labeling.lgbm_filter import LightGBMMetaFilter, FEATURE_NAMES
from subsystems.evolution import model_registry
from subsystems.evolution.expectancy_gate import (
    evaluate_promotion,
    metrics_from_shadow_frame,
)
from subsystems.evolution.drift_monitor import check_drift
from subsystems.research import store as research_store

EVOLUTION_MARKER = DATA_DIR / "last_weekend_evolution.json"


class WeekendSelfEvolutionWorker:
    """Evolutionary engine updating AI models during weekend market close."""

    def __init__(self, duckdb: Optional[DuckDBManager] = None):
        self.duckdb = duckdb or DuckDBManager()
        self.lgbm_filter = LightGBMMetaFilter()

    def is_weekend(self) -> bool:
        return datetime.utcnow().weekday() in [5, 6]

    def _evo_settings(self) -> Dict[str, Any]:
        try:
            from subsystems.config.system_runtime import load_settings

            e = load_settings().evolution
            return e.model_dump()
        except Exception:
            return {
                "once_per_weekend": True,
                "embargo_bars": 5,
                "shadow_min_signals": 30,
                "shadow_min_days": 14,
                "psi_threshold": 0.25,
                "max_dd_worsen_pct": 0.20,
            }

    def _already_ran_this_weekend(self) -> bool:
        cfg = self._evo_settings()
        if not cfg.get("once_per_weekend", True):
            return False
        if not EVOLUTION_MARKER.exists():
            return False
        try:
            data = json.loads(EVOLUTION_MARKER.read_text(encoding="utf-8"))
            last = float(data.get("ts") or 0)
            # Same ISO week
            last_dt = datetime.utcfromtimestamp(last)
            now = datetime.utcnow()
            return last_dt.isocalendar()[:2] == now.isocalendar()[:2]
        except Exception:
            return False

    def _mark_ran(self, result: Dict[str, Any]) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        EVOLUTION_MARKER.write_text(
            json.dumps({"ts": time.time(), "result": result}, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def purged_walk_forward_splits(
        n: int,
        n_folds: int = 3,
        embargo: int = 5,
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Time-ordered folds with embargo gap between train and test.
        Returns list of (train_idx, test_idx).
        """
        if n < 20:
            return []
        fold_sizes = [n // n_folds] * n_folds
        for i in range(n % n_folds):
            fold_sizes[i] += 1
        indices = np.arange(n)
        splits = []
        start = 0
        for fold in range(n_folds):
            test_start = start
            test_end = start + fold_sizes[fold]
            test_idx = indices[test_start:test_end]
            train_end = max(0, test_start - embargo)
            train_idx = indices[:train_end]
            if len(train_idx) >= 10 and len(test_idx) >= 3:
                splits.append((train_idx, test_idx))
            start = test_end
        return splits

    def _extract_xy(self, trades_df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        y = (trades_df["pnl"] > 0).astype(int).values
        rows = []
        for feat_str in trades_df["features_json"]:
            try:
                fd = json.loads(feat_str) if isinstance(feat_str, str) else (feat_str or {})
            except Exception:
                fd = {}
            rows.append([float(fd.get(k, 0.0)) for k in FEATURE_NAMES])
        return np.asarray(rows, dtype=np.float32), y

    def run_drift_check(self) -> Dict[str, Any]:
        meta = model_registry.challenger_meta() or {}
        # Prefer champion meta snapshot
        ptr = model_registry._pointer()
        champ_id = ptr.get("lgbm")
        snap = {}
        if champ_id:
            meta_path = model_registry.REGISTRY_ROOT / "lgbm" / champ_id / "meta.json"
            if meta_path.exists():
                try:
                    snap = json.loads(meta_path.read_text(encoding="utf-8")).get(
                        "feature_snapshot"
                    ) or {}
                except Exception:
                    snap = {}
        if not snap:
            return {"breached": False, "reason": "no_snapshot"}

        shadows = self.duckdb.get_shadow_signals(limit=500)
        if shadows is None or shadows.empty:
            return {"breached": False, "reason": "no_shadow_rows"}

        live_rows = []
        for _, row in shadows.iterrows():
            try:
                fd = json.loads(row.get("features_json") or "{}")
            except Exception:
                fd = {}
            live_rows.append(fd)

        cfg = self._evo_settings()
        return check_drift(
            snap,
            live_rows,
            threshold=float(cfg.get("psi_threshold", 0.25)),
            feature_names=FEATURE_NAMES,
        )

    def run_evolution_cycle(self, *, force: bool = False) -> Dict[str, Any]:
        """Execute weekend challenger training + drift check + research proposal."""
        logger.info("[WeekendEvolution] Starting evolutionary retraining cycle...")
        if not force and self._already_ran_this_weekend():
            logger.info("[WeekendEvolution] Already ran this weekend — skip")
            return {"status": "SKIPPED_DEBOUNCE"}

        drift = self.run_drift_check()
        trades_df = self.duckdb.get_trade_logs()
        if trades_df is None or trades_df.empty:
            logger.info("[WeekendEvolution] No trades found in DuckDB yet. Skipping retraining.")
            result = {"status": "SKIPPED_NO_DATA", "drift": drift}
            if drift.get("breached"):
                self._propose_drift_retrain(drift)
            self._mark_ran(result)
            return result

        # Chronological order for WF
        if "entry_timestamp" in trades_df.columns:
            trades_df = trades_df.sort_values("entry_timestamp").reset_index(drop=True)

        X, y = self._extract_xy(trades_df)
        if float(np.std(X)) < 1e-12:
            logger.warning("[WeekendEvolution] Empty features — fix feature-persistence first")
            result = {"status": "SKIPPED_EMPTY_FEATURES", "drift": drift}
            self._mark_ran(result)
            return result

        cfg = self._evo_settings()
        embargo = int(cfg.get("embargo_bars", 5))
        splits = self.purged_walk_forward_splits(len(X), n_folds=3, embargo=embargo)

        oof_probs = np.full(len(X), np.nan)
        if splits:
            import lightgbm as lgb

            for train_idx, test_idx in splits:
                dtrain = lgb.Dataset(X[train_idx], label=y[train_idx], feature_name=FEATURE_NAMES)
                params = {
                    "objective": "binary",
                    "metric": "binary_logloss",
                    "learning_rate": 0.03,
                    "num_leaves": 15,
                    "verbose": -1,
                }
                booster = lgb.train(params, dtrain, num_boost_round=40)
                oof_probs[test_idx] = booster.predict(X[test_idx])

        mask = ~np.isnan(oof_probs)
        if mask.sum() >= 5:
            pnls = trades_df["pnl"].values[mask]
            metrics = metrics_from_shadow_frame(
                oof_probs[mask],
                y[mask],
                pnls,
            )
        else:
            metrics = {"n": int(len(X)), "expectancy": 0.0, "source": "insufficient_oof"}

        # Train full-sample challenger (registered, not promoted)
        vid = self.lgbm_filter.train_challenger_from_matrices(
            X,
            y,
            metrics={**metrics, "drift": drift},
            init_from_champion=True,
        )

        # Export parquet
        try:
            self.duckdb.export_to_parquet()
        except Exception as e:
            logger.warning(f"[WeekendEvolution] Parquet export error: {e}")

        # Research proposal for human review (promotion gated later)
        report = {
            "title": f"LGBM Challenger {vid}",
            "module": "evolution",
            "mode": "model_challenger",
            "kind": "model_challenger",
            "summary": (
                f"Challenger {vid} trained with purged WF. "
                f"expectancy={metrics.get('expectancy')} ece={metrics.get('ece')} "
                f"max_dd={metrics.get('max_dd')} drift_breached={drift.get('breached')}"
            ),
            "status": "proposed",
            "challenger_version": vid,
            "metrics": metrics,
            "drift": drift,
            "auto_apply": False,
        }
        path = research_store.save_report(report)

        result = {
            "status": "COMPLETED",
            "challenger_version": vid,
            "trades_processed": int(len(trades_df)),
            "metrics": metrics,
            "drift": drift,
            "research_report": str(path),
            "cnn_finetune": "SKIPPED_NO_SEQUENCE_STORE",
        }
        self._mark_ran(result)
        logger.info(f"[WeekendEvolution] Challenger ready: {vid}")
        return result

    def _propose_drift_retrain(self, drift: Dict[str, Any]) -> None:
        research_store.save_report(
            {
                "title": "Feature Drift PSI Breach",
                "module": "evolution",
                "mode": "drift_alert",
                "kind": "drift_alert",
                "summary": (
                    f"PSI breach on {drift.get('max_psi_feature')} "
                    f"psi={drift.get('max_psi')} thr={drift.get('threshold')}"
                ),
                "status": "needs_review",
                "drift": drift,
                "auto_apply": False,
            }
        )


def try_promote_from_research(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    After human approves a model_challenger report, run expectancy gate then promote.
    """
    if report.get("kind") != "model_challenger" and report.get("mode") != "model_challenger":
        return {"ok": False, "reason": "not_model_challenger"}

    try:
        from subsystems.config.system_runtime import load_settings

        evo = load_settings().evolution
        min_signals = int(evo.shadow_min_signals)
        max_dd_worsen = float(evo.max_dd_worsen_pct)
        min_days = int(evo.shadow_min_days)
    except Exception:
        min_signals, max_dd_worsen, min_days = 30, 0.20, 14

    duck = DuckDBManager()
    shadows = duck.get_shadow_signals(limit=5000)
    challenger_metrics = report.get("metrics") or {}

    # Prefer live shadow scores for challenger if available
    if shadows is not None and not shadows.empty and "challenger_win_prob" in shadows.columns:
        sub = shadows.dropna(subset=["challenger_win_prob"])
        # Age filter
        cutoff = time.time() - min_days * 86400
        if "ts" in sub.columns:
            sub = sub[sub["ts"] >= cutoff]
        # Without resolved outcomes, fall back to report OOF metrics
        if len(sub) >= min_signals and "shadow_pnl" in sub.columns:
            if "resolved" in sub.columns:
                resolved = sub[sub["resolved"] == 1]
            else:
                resolved = sub.dropna(subset=["shadow_pnl"])
            if len(resolved) >= min_signals:
                probs = resolved["challenger_win_prob"].astype(float).tolist()
                pnls = resolved["shadow_pnl"].astype(float).tolist()
                outcomes = [1 if p > 0 else 0 for p in pnls]
                challenger_metrics = metrics_from_shadow_frame(probs, outcomes, pnls)

    # Champion baseline from closed trades
    trades = duck.get_trade_logs()
    if trades is not None and not trades.empty and "pnl" in trades.columns:
        pnls = trades["pnl"].astype(float).tolist()
        # Approximate champion probs from win_prob if stored in features — else binary
        probs = []
        outcomes = []
        for _, row in trades.iterrows():
            outcomes.append(1 if float(row["pnl"]) > 0 else 0)
            try:
                fd = json.loads(row.get("features_json") or "{}")
                probs.append(float(fd.get("model_confidence", 0.5)))
            except Exception:
                probs.append(0.5)
        champion_metrics = metrics_from_shadow_frame(probs, outcomes, pnls)
    else:
        champion_metrics = {
            "expectancy": 0.0,
            "ece": 1.0,
            "max_dd": 0.0,
            "n_signals": 0,
        }

    # Ensure n_signals on challenger metrics
    challenger_metrics.setdefault("n_signals", challenger_metrics.get("n", 0))
    if int(challenger_metrics.get("n_signals") or 0) < min_signals:
        # Allow promotion gate to use OOF n from weekend metrics
        pass

    ok, reasons = evaluate_promotion(
        champion_metrics,
        challenger_metrics,
        max_dd_worsen_pct=max_dd_worsen,
        min_signals=min_signals,
    )
    if not ok:
        return {
            "ok": False,
            "reason": "expectancy_gate_failed",
            "details": reasons,
            "champion": champion_metrics,
            "challenger": challenger_metrics,
        }

    vid = model_registry.promote_challenger_lgbm()
    if not vid:
        return {"ok": False, "reason": "no_challenger_in_registry"}
    return {
        "ok": True,
        "promoted_version": vid,
        "details": reasons,
        "champion": champion_metrics,
        "challenger": challenger_metrics,
    }
