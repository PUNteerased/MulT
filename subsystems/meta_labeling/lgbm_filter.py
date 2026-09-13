"""
LightGBM Meta-Labeling Filter.
Runs on CPU (< 5ms inference latency).
Loads champion from model registry; can score a challenger in parallel.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger
from config.settings import MODELS_DIR, MIN_WIN_PROBABILITY
from subsystems.evolution import model_registry

FEATURE_NAMES = [
    "model_confidence",
    "vol_ratio",
    "body_ratio",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "rsi",
    "atr",
    "z_score",
    "dist_ema20",
    "dist_ema50",
    "spread_ratio",
    "sentiment_score",
    "regime_state",
]


class LightGBMMetaFilter:
    """Gradient Boosting secondary decision gate."""

    def __init__(self, min_win_prob: float = MIN_WIN_PROBABILITY):
        self.min_win_prob = min_win_prob
        self.model_path = model_registry.champion_lgbm_path()
        self.booster: Optional[lgb.Booster] = None
        self.challenger: Optional[lgb.Booster] = None
        self._load_or_create_model()
        self.reload_challenger()

    def _load_or_create_model(self):
        """Load champion from registry / legacy path or train synthetic baseline."""
        model_registry.bootstrap_from_legacy_if_needed(FEATURE_NAMES)
        self.model_path = model_registry.champion_lgbm_path()
        if self.model_path.exists():
            try:
                self.booster = lgb.Booster(model_file=str(self.model_path))
                logger.info(f"[LightGBM] Loaded champion from {self.model_path}")
                return
            except Exception as e:
                logger.warning(f"[LightGBM] Error loading model: {e}")

        logger.info("[LightGBM] Training initial baseline filter model...")
        np.random.seed(42)
        n_samples = 1000
        conf = np.random.uniform(0.5, 0.95, n_samples)
        vol_r = np.random.uniform(0.8, 3.0, n_samples)
        body_r = np.random.uniform(0.1, 0.6, n_samples)
        u_wick = np.random.uniform(0.1, 0.7, n_samples)
        l_wick = np.random.uniform(0.1, 0.7, n_samples)
        rsi = np.random.uniform(20, 80, n_samples)
        atr = np.random.uniform(0.0005, 0.0030, n_samples)
        z_sc = np.random.normal(0, 1.5, n_samples)
        dist_ema20 = np.random.normal(0, 1.0, n_samples)
        dist_ema50 = np.random.normal(0, 1.5, n_samples)
        spr_ratio = np.random.uniform(0.05, 0.35, n_samples)
        sent = np.random.uniform(-0.5, 0.5, n_samples)
        regime = np.random.choice([0, 1, 2, 3], n_samples)

        X = np.column_stack(
            [
                conf,
                vol_r,
                body_r,
                u_wick,
                l_wick,
                rsi,
                atr,
                z_sc,
                dist_ema20,
                dist_ema50,
                spr_ratio,
                sent,
                regime,
            ]
        )
        win_score = (
            0.40 * conf
            + 0.20 * (vol_r > 1.2)
            - 0.20 * (spr_ratio > 0.25)
            - 0.25 * (regime == 3)
            + 0.15 * (np.abs(z_sc) > 1.0)
        )
        y = (win_score > np.median(win_score)).astype(int)
        dtrain = lgb.Dataset(X, label=y, feature_name=FEATURE_NAMES)
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.05,
            "num_leaves": 15,
            "verbose": -1,
        }
        self.booster = lgb.train(params, dtrain, num_boost_round=50)
        tmp = MODELS_DIR / "_lgbm_bootstrap.txt"
        self.booster.save_model(str(tmp))
        model_registry.register_lgbm(
            tmp,
            role="champion",
            feature_names=FEATURE_NAMES,
            feature_hash=self._feature_hash(),
            feature_snapshot=self._snapshot_from_X(X),
            metrics={"source": "synthetic_baseline"},
        )
        tmp.unlink(missing_ok=True)
        self.model_path = model_registry.champion_lgbm_path()

    @staticmethod
    def _feature_hash() -> str:
        return hashlib.sha256(",".join(FEATURE_NAMES).encode()).hexdigest()[:16]

    @staticmethod
    def _snapshot_from_X(X: np.ndarray) -> Dict[str, List[float]]:
        from subsystems.evolution.drift_monitor import snapshot_from_matrix

        return snapshot_from_matrix(X, FEATURE_NAMES)

    def reload_challenger(self) -> None:
        path = model_registry.challenger_lgbm_path()
        self.challenger = None
        if path and path.exists():
            try:
                self.challenger = lgb.Booster(model_file=str(path))
                logger.info(f"[LightGBM] Loaded challenger from {path}")
            except Exception as e:
                logger.warning(f"[LightGBM] Challenger load failed: {e}")

    def reload_champion(self) -> None:
        self.model_path = model_registry.champion_lgbm_path()
        if self.model_path.exists():
            self.booster = lgb.Booster(model_file=str(self.model_path))

    def save_model(self):
        """Legacy helper — writes temp then registers as challenger (does not promote)."""
        if not self.booster:
            return
        tmp = MODELS_DIR / "_lgbm_save_tmp.txt"
        self.booster.save_model(str(tmp))
        model_registry.register_lgbm(
            tmp,
            role="challenger",
            feature_names=FEATURE_NAMES,
            feature_hash=self._feature_hash(),
        )
        tmp.unlink(missing_ok=True)
        self.reload_challenger()

    def _row(self, feature_dict: Dict[str, float]) -> np.ndarray:
        return np.array(
            [[float(feature_dict.get(feat, 0.0)) for feat in FEATURE_NAMES]],
            dtype=np.float32,
        )

    def predict_proba(self, feature_dict: Dict[str, float], *, use_challenger: bool = False) -> float:
        model = self.challenger if use_challenger and self.challenger is not None else self.booster
        if model is None:
            return 0.80
        return float(model.predict(self._row(feature_dict))[0])

    def evaluate_features(self, feature_dict: Dict[str, float]) -> Tuple[bool, float]:
        """
        Evaluate candidate features with champion.
        Returns: (is_approved, win_probability)
        """
        if self.booster is None:
            return True, 0.80

        win_prob = self.predict_proba(feature_dict, use_challenger=False)
        try:
            from subsystems.config.system_runtime import load_settings

            threshold = float(load_settings().meta.min_win_probability)
        except Exception:
            threshold = float(self.min_win_prob)

        is_approved = win_prob >= threshold
        return is_approved, round(win_prob, 3)

    def train_challenger_from_matrices(
        self,
        X: np.ndarray,
        y: np.ndarray,
        *,
        metrics: Optional[Dict[str, Any]] = None,
        init_from_champion: bool = True,
    ) -> str:
        """Train a new booster and register as challenger only."""
        dtrain = lgb.Dataset(X, label=y, feature_name=FEATURE_NAMES)
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.03,
            "num_leaves": 15,
            "verbose": -1,
        }
        init = self.booster if init_from_champion and self.booster is not None else None
        booster = lgb.train(params, dtrain, num_boost_round=30, init_model=init)
        tmp = MODELS_DIR / "_lgbm_challenger_tmp.txt"
        booster.save_model(str(tmp))
        vid = model_registry.register_lgbm(
            tmp,
            role="challenger",
            feature_names=FEATURE_NAMES,
            feature_hash=self._feature_hash(),
            feature_snapshot=self._snapshot_from_X(X),
            metrics=metrics or {},
        )
        tmp.unlink(missing_ok=True)
        self.reload_challenger()
        return vid

    def retrain_on_trade_history(self, trades_df: pd.DataFrame):
        """
        Weekend path: train challenger from trade features (does NOT overwrite champion).
        """
        if len(trades_df) < 20 or "pnl" not in trades_df.columns:
            logger.info("[LightGBM] Insufficient trade records for retraining.")
            return None

        y = (trades_df["pnl"] > 0).astype(int).values
        feature_rows = []
        for feat_str in trades_df["features_json"]:
            try:
                fd = json.loads(feat_str) if isinstance(feat_str, str) else (feat_str or {})
            except Exception:
                fd = {}
            feature_rows.append([fd.get(k, 0.0) for k in FEATURE_NAMES])

        X = np.array(feature_rows, dtype=np.float32)
        if float(np.std(X)) < 1e-12:
            logger.warning("[LightGBM] Feature matrix empty/constant — skip challenger train")
            return None

        vid = self.train_challenger_from_matrices(
            X,
            y,
            metrics={"n_trades": int(len(trades_df)), "source": "trade_history"},
        )
        logger.info(f"[LightGBM] Challenger {vid} trained on {len(trades_df)} trades (champion unchanged).")
        return vid
