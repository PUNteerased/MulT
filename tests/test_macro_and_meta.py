"""
Unit tests for Macro Sentiment, Calendar Crawler, HMM Regime, and LightGBM Filter.
"""
import pytest
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from subsystems.macro_sentiment.calendar_crawler import EconomicCalendarCrawler
from subsystems.macro_sentiment.finbert_engine import FinBERTSentimentEngine
from subsystems.macro_sentiment.hmm_regime import HMMRegimeClassifier
from subsystems.meta_labeling.lgbm_filter import LightGBMMetaFilter

def test_economic_calendar_red_folder_window():
    crawler = EconomicCalendarCrawler()
    now_utc = datetime.now(timezone.utc)

    # 1. Add event happening in 10 minutes (within 30m before -> MUST HALT)
    event_time_10m = now_utc + timedelta(minutes=10)
    crawler.add_event(title="US CPI MoM", currency="USD", event_time_utc=event_time_10m, impact="HIGH")
    halted, title = crawler.check_red_folder_status(now_utc)
    assert halted is True
    assert "CPI" in title

    # 2. Test time 40 minutes before event (Outside 30m window -> MUST NOT HALT)
    time_40m_before = event_time_10m - timedelta(minutes=40)
    halted_outside, _ = crawler.check_red_folder_status(time_40m_before)
    assert halted_outside is False

def test_finbert_sentiment_engine():
    engine = FinBERTSentimentEngine()
    # Bullish headline
    res_bull = engine.analyze_headline("US Nonfarm Payrolls Surge, Economy Shows Robust Growth")
    assert res_bull["sentiment"] == "POSITIVE"
    assert res_bull["is_risk_off"] is False

    # Extreme Bearish / Panic headline
    res_bear = engine.analyze_headline("Global Banking Collapse Fears Rise As Default Warnings Spread Panic")
    assert res_bear["sentiment"] == "NEGATIVE"
    assert res_bear["is_risk_off"] is True

def test_hmm_regime_classifier():
    hmm = HMMRegimeClassifier(n_states=4)
    # Generate 60 bars of synthetic upward trend
    closes = 1.0800 + np.cumsum(np.random.normal(0.0001, 0.0002, 60))
    df = pd.DataFrame({
        "close": closes,
        "high": closes + 0.0005,
        "low": closes - 0.0005,
        "open": closes - 0.0001,
        "tick_volume": np.full(60, 100),
        "spread": np.full(60, 10)
    })
    hmm.fit_on_bars(df)
    state, state_name, conf = hmm.predict_regime(df)
    assert state in [0, 1, 2, 3]
    assert len(state_name) > 0
    assert 0.0 <= conf <= 1.0

def test_lgbm_meta_filter():
    meta = LightGBMMetaFilter(min_win_prob=0.75)
    # Strong setup feature vector
    strong_features = {
        "model_confidence": 0.92,
        "vol_ratio": 2.2,
        "body_ratio": 0.45,
        "upper_wick_ratio": 0.10,
        "lower_wick_ratio": 0.45,
        "rsi": 32.0,
        "atr": 0.0015,
        "z_score": -1.8,
        "dist_ema20": -1.2,
        "dist_ema50": -1.5,
        "spread_ratio": 0.10,
        "sentiment_score": 0.20,
        "regime_state": 0
    }
    approved, win_prob = meta.evaluate_features(strong_features)
    assert 0.0 <= win_prob <= 1.0
    assert approved == (win_prob >= 0.75)
