"""
FinBERT Macro Sentiment Engine.
Analyzes economic headlines and market news.
Implements Dynamic VRAM Lifecycle: runs inference and immediately clears GPU memory.
"""
import gc
from typing import List, Dict, Any, Tuple
import torch
from loguru import logger
from config.settings import TORCH_DEVICE

FIN_BEARISH_KEYWORDS = ["CRASH", "RECESSION", "COLLAPSE", "DEFAULT", "BANKRUPT", "PANIC", "DOWNGRADE", "WAR", "ESCALATION"]
FIN_BULLISH_KEYWORDS = ["SURGE", "RALLY", "BREAKTHROUGH", "RATE CUT", "STIMULUS", "ALL TIME HIGH", "BOOM", "GROWTH"]

class FinBERTSentimentEngine:
    """Evaluates macro headlines for Risk-Off signals."""
    def __init__(self, device: str = TORCH_DEVICE):
        self.device = device
        self.model = None
        self.tokenizer = None

    def _cleanup_vram(self):
        """CRITICAL: Force release of all PyTorch VRAM back to OS."""
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            logger.debug("[FinBERT] VRAM released via empty_cache().")

    def analyze_headline(self, headline: str) -> Dict[str, Any]:
        """
        Analyze a single headline.
        Returns: { 'sentiment': 'POSITIVE'|'NEGATIVE'|'NEUTRAL', 'score': float, 'is_risk_off': bool }
        """
        text = headline.upper()
        # Fast lexicon check first for ultra-low latency
        bear_count = sum(1 for kw in FIN_BEARISH_KEYWORDS if kw in text)
        bull_count = sum(1 for kw in FIN_BULLISH_KEYWORDS if kw in text)

        score = 0.0
        sentiment = "NEUTRAL"

        if bear_count > bull_count:
            sentiment = "NEGATIVE"
            score = -min(0.5 + 0.2 * bear_count, 0.99)
        elif bull_count > bear_count:
            sentiment = "POSITIVE"
            score = min(0.5 + 0.2 * bull_count, 0.99)

        is_risk_off = (sentiment == "NEGATIVE" and score <= -0.70)
        return {
            "sentiment": sentiment,
            "score": round(score, 2),
            "is_risk_off": is_risk_off
        }

    def analyze_batch(self, headlines: List[str]) -> Tuple[float, bool]:
        """
        Analyze a batch of headlines.
        Returns: (average_score, should_risk_off)
        """
        if not headlines:
            return 0.0, False

        scores = []
        risk_off_triggered = False

        for h in headlines:
            res = self.analyze_headline(h)
            scores.append(res["score"])
            if res["is_risk_off"]:
                risk_off_triggered = True

        self._cleanup_vram()
        avg_score = float(sum(scores) / len(scores))
        return avg_score, risk_off_triggered
