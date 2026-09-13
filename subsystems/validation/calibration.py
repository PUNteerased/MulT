"""Probability calibration helpers for meta-label win_prob vs outcomes."""
from __future__ import annotations

from typing import Any, Dict, List, Sequence


def reliability_bins(
    trades: Sequence[Dict[str, Any]],
    n_bins: int = 5,
) -> List[Dict[str, Any]]:
    """Bucket predicted win_prob and compare to empirical win rate."""
    rows = [t for t in trades if t.get("win_probability") is not None]
    if not rows:
        return []

    bins: List[Dict[str, Any]] = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        bucket = [
            t
            for t in rows
            if lo <= float(t["win_probability"]) < hi
            or (i == n_bins - 1 and float(t["win_probability"]) == hi)
        ]
        if not bucket:
            bins.append(
                {
                    "bin_lo": lo,
                    "bin_hi": hi,
                    "n": 0,
                    "avg_pred": 0.0,
                    "emp_win_rate": 0.0,
                }
            )
            continue
        preds = [float(t["win_probability"]) for t in bucket]
        wins = sum(1 for t in bucket if float(t.get("pnl", 0.0)) > 0)
        bins.append(
            {
                "bin_lo": round(lo, 3),
                "bin_hi": round(hi, 3),
                "n": len(bucket),
                "avg_pred": round(sum(preds) / len(preds), 4),
                "emp_win_rate": round(wins / len(bucket), 4),
            }
        )
    return bins


def calibration_summary(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    bins = reliability_bins(trades)
    # Simple ECE-like score
    total_n = sum(b["n"] for b in bins) or 1
    ece = sum(b["n"] * abs(b["avg_pred"] - b["emp_win_rate"]) for b in bins) / total_n
    return {
        "ece": round(ece, 4),
        "bins": bins,
        "note": "Offline heuristic — not a live production gate",
    }
