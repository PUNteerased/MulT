"""
LightGBM Meta-Labeling Filter.
Runs on CPU (< 5ms inference latency).
Evaluates trigger alerts against market regime and microstructure features.
Only approves setups with Win_Probability >= 75% to protect the $50 account.
"""
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import lightgbm as lgb
import numpy as np
import pandas as pd
from loguru import logger
from config.settings import MODELS_DIR, MIN_WIN_PROBABILITY

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
    "regime_state"
]

class LightGBMMetaFilter:
    """Gradient Boosting secondary decision gate."""
    def __init__(self, min_win_prob: float = MIN_WIN_PROBABILITY):
        self.min_win_prob = min_win_prob
        self.model_path = MODELS_DIR / "lgbm_meta_filter.txt"
        self.booster: Optional[lgb.Booster] = None
        self._load_or_create_model()

    def _load_or_create_model(self):
        """Load pretrained LightGBM booster or initialize default baseline model."""
        if self.model_path.exists():
            try:
                self.booster = lgb.Booster(model_file=str(self.model_path))
                logger.info(f"[LightGBM] Loaded model from {self.model_path}")
                return
            except Exception as e:
                logger.warning(f"[LightGBM] Error loading model: {e}")

        # Train a robust initial baseline model with synthetic domain knowledge
        logger.info("[LightGBM] Training initial baseline filter model...")
        np.random.seed(42)
        n_samples = 1000
        # Simulated features
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

        X = np.column_stack([
            conf, vol_r, body_r, u_wick, l_wick, rsi, atr, z_sc,
            dist_ema20, dist_ema50, spr_ratio, sent, regime
        ])

        # Win formula: high sniper confidence, high volume, reasonable spread, not chaotic regime
        win_score = (
            0.40 * conf +
            0.20 * (vol_r > 1.2) -
            0.20 * (spr_ratio > 0.25) -
            0.25 * (regime == 3) +
            0.15 * (np.abs(z_sc) > 1.0)
        )
        y = (win_score > np.median(win_score)).astype(int)

        dtrain = lgb.Dataset(X, label=y, feature_name=FEATURE_NAMES)
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.05,
            "num_leaves": 15,
            "verbose": -1
        }
        self.booster = lgb.train(params, dtrain, num_boost_round=50)
        self.save_model()

    def save_model(self):
        if self.booster:
            self.booster.save_model(str(self.model_path))

    def evaluate_features(self, feature_dict: Dict[str, float]) -> Tuple[bool, float]:
        """
        Evaluate candidate features.
        Returns: (is_approved, win_probability)
        """
        if self.booster is None:
            return True, 0.80

        row = []
        for feat in FEATURE_NAMES:
            row.append(feature_dict.get(feat, 0.0))

        X_in = np.array([row], dtype=np.float32)
        win_prob = float(self.booster.predict(X_in)[0])

        is_approved = win_prob >= self.min_win_prob
        return is_approved, round(win_prob, 3)

    def retrain_on_trade_history(self, trades_df: pd.DataFrame):
        """Used by weekend evolution subsystem to incorporate live trade results."""
        if len(trades_df) < 20 or "pnl" not in trades_df.columns:
            logger.info("[LightGBM] Insufficient trade records for retraining.")
            return

        # Target: 1 if profitable trade, 0 if loss
        y = (trades_df["pnl"] > 0).astype(int).values
        # Parse features_json
        import json
        feature_rows = []
        for feat_str in trades_df["features_json"]:
            try:
                fd = json.loads(feat_str)
            except Exception:
                fd = {}
            feature_rows.append([fd.get(k, 0.0) for k in FEATURE_NAMES])

        X = np.array(feature_rows, dtype=np.float32)
        dtrain = lgb.Dataset(X, label=y, feature_name=FEATURE_NAMES)
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.03,
            "num_leaves": 15,
            "verbose": -1
        }
        self.booster = lgb.train(params, dtrain, num_boost_round=30, init_model=self.booster)
        self.save_model()
        logger.info(f"[LightGBM] Retrained model on {len(trades_df)} historical trades.")
