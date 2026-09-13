"""
Hidden Markov Model (HMM) Market Regime Classifier.
Runs on CPU using hmmlearn GaussianHMM.
Identifies 4 macro regimes: Trending Bull, Trending Bear, Low-Vol Range, High-Vol Chaos.
"""
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from loguru import logger

class HMMRegimeClassifier:
    """Classifies current market state using a 4-state Gaussian HMM on CPU."""
    def __init__(self, n_states: int = 4):
        self.n_states = n_states
        self.model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=50,
            random_state=42
        )
        self.is_fitted = False

    def fit_on_bars(self, df: pd.DataFrame):
        """Fit HMM on historical returns and volatility."""
        if len(df) < 50:
            return

        close = df['close'].values
        returns = np.diff(np.log(close + 1e-9))
        vol = pd.Series(returns).rolling(window=10, min_periods=1).std().values

        features = np.column_stack([returns, vol])
        try:
            self.model.fit(features)
            self.is_fitted = True
            logger.info("[HMM] Model fitted successfully on market data.")
        except Exception as e:
            logger.warning(f"[HMM] Fit failed: {e}")

    def predict_regime(self, df: pd.DataFrame) -> Tuple[int, str, float]:
        """
        Predict regime for the latest bar.
        Returns: (state_id, state_name, confidence)
        """
        if not self.is_fitted or len(df) < 20:
            # Fallback heuristic
            c = df['close'].values
            ret = (c[-1] - c[-10]) / c[-10]
            if ret > 0.001:
                return 0, "TRENDING_BULL", 0.70
            elif ret < -0.001:
                return 1, "TRENDING_BEAR", 0.70
            else:
                return 2, "LOW_VOL_RANGE", 0.75

        close = df['close'].values
        returns = np.diff(np.log(close + 1e-9))
        vol = pd.Series(returns).rolling(window=10, min_periods=1).std().values
        features = np.column_stack([returns, vol])

        try:
            hidden_states = self.model.predict(features)
            latest_state = int(hidden_states[-1])
            posteriors = self.model.predict_proba(features)
            conf = float(posteriors[-1, latest_state])

            names = {
                0: "TRENDING_BULL",
                1: "TRENDING_BEAR",
                2: "LOW_VOL_RANGE",
                3: "HIGH_VOL_CHAOS"
            }
            return latest_state, names.get(latest_state, "UNKNOWN"), round(conf, 3)
        except Exception as e:
            logger.warning(f"[HMM] Prediction error: {e}")
            return 2, "LOW_VOL_RANGE", 0.50
