"""
Expectancy / calibration / drawdown gates for champion–challenger promotion.
Win rate is never the primary promote criterion.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


def expectancy(pnls: Sequence[float]) -> float:
    if not pnls:
        return 0.0
    arr = np.asarray(pnls, dtype=float)
    return float(np.mean(arr))


def max_drawdown(pnls: Sequence[float]) -> float:
    """Max peak-to-trough drawdown on equity curve built from trade PnLs (absolute $)."""
    if not pnls:
        return 0.0
    equity = np.cumsum(np.asarray(pnls, dtype=float))
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    return float(np.max(dd)) if len(dd) else 0.0


def bootstrap_expectancy_ci(
    pnls: Sequence[float],
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """Return (point, ci_low, ci_high) for mean PnL (expectancy)."""
    arr = np.asarray(list(pnls), dtype=float)
    if len(arr) == 0:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(seed)
    means = []
    n = len(arr)
    for _ in range(n_boot):
        sample = rng.choice(arr, size=n, replace=True)
        means.append(float(np.mean(sample)))
    means_arr = np.sort(np.asarray(means))
    lo = float(np.quantile(means_arr, alpha / 2))
    hi = float(np.quantile(means_arr, 1 - alpha / 2))
    return float(np.mean(arr)), lo, hi


def expected_calibration_error(
    probs: Sequence[float],
    outcomes: Sequence[int],
    n_bins: int = 10,
) -> float:
    """ECE for binary outcomes vs predicted win probabilities."""
    p = np.asarray(probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if len(p) == 0 or len(p) != len(y):
        return 0.0
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (p >= bins[i]) & (p < bins[i + 1] if i < n_bins - 1 else p <= bins[i + 1])
        if not np.any(mask):
            continue
        conf = float(np.mean(p[mask]))
        acc = float(np.mean(y[mask]))
        ece += (np.sum(mask) / len(p)) * abs(acc - conf)
    return float(ece)


def evaluate_promotion(
    champion: Dict[str, Any],
    challenger: Dict[str, Any],
    *,
    max_dd_worsen_pct: float = 0.20,
    min_signals: int = 30,
) -> Tuple[bool, List[str]]:
    """
    Promote when ALL hold:
    1) Calibration (ECE) not worse
    2) Challenger expectancy CI low > champion expectancy (or clear improvement)
    3) Max DD not worse by more than max_dd_worsen_pct relatively
    """
    reasons: List[str] = []
    n = int(challenger.get("n_signals") or challenger.get("n") or 0)
    if n < min_signals:
        reasons.append(f"insufficient_signals:{n}<{min_signals}")
        return False, reasons

    champ_ece = float(champion.get("ece", 0.0))
    chall_ece = float(challenger.get("ece", 0.0))
    if chall_ece > champ_ece + 1e-6:
        reasons.append(f"calibration_worse:ece {chall_ece:.4f}>{champ_ece:.4f}")

    champ_exp = float(champion.get("expectancy", 0.0))
    chall_ci_lo = float(challenger.get("expectancy_ci_low", challenger.get("expectancy", 0.0)))
    if chall_ci_lo <= champ_exp:
        reasons.append(
            f"expectancy_ci_not_better:ci_lo={chall_ci_lo:.4f} champ_exp={champ_exp:.4f}"
        )

    champ_dd = float(champion.get("max_dd", 0.0))
    chall_dd = float(challenger.get("max_dd", 0.0))
    if champ_dd <= 0:
        if chall_dd > abs(champ_exp) * 10 and chall_dd > 0:
            reasons.append(f"max_dd_unbounded_worsen:{chall_dd:.4f}")
    else:
        worsen = (chall_dd - champ_dd) / champ_dd
        if worsen > max_dd_worsen_pct:
            reasons.append(
                f"max_dd_worsen:{worsen:.2%}>{max_dd_worsen_pct:.2%} "
                f"(chall={chall_dd:.4f} champ={champ_dd:.4f})"
            )

    ok = len(reasons) == 0
    if ok:
        reasons.append("all_gates_passed")
    return ok, reasons


def metrics_from_shadow_frame(
    probs: Sequence[float],
    outcomes: Sequence[int],
    pnls: Sequence[float],
) -> Dict[str, Any]:
    point, lo, hi = bootstrap_expectancy_ci(pnls)
    return {
        "n": len(pnls),
        "n_signals": len(pnls),
        "expectancy": point,
        "expectancy_ci_low": lo,
        "expectancy_ci_high": hi,
        "ece": expected_calibration_error(probs, outcomes),
        "max_dd": max_drawdown(pnls),
        "win_rate": float(np.mean(outcomes)) if outcomes else 0.0,
    }
