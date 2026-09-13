"""
Population Stability Index (PSI) drift monitoring vs train-time feature snapshot.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from loguru import logger


def _hist_pct(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    counts, _ = np.histogram(values, bins=edges)
    total = max(int(np.sum(counts)), 1)
    pct = counts.astype(float) / total
    return np.clip(pct, 1e-4, None)


def psi_for_feature(
    baseline: Sequence[float],
    current: Sequence[float],
    n_bins: int = 10,
) -> float:
    b = np.asarray(list(baseline), dtype=float)
    c = np.asarray(list(current), dtype=float)
    if len(b) < 5 or len(c) < 5:
        return 0.0
    qs = np.linspace(0, 1, n_bins + 1)
    edges = np.unique(np.quantile(b, qs))
    if len(edges) < 3:
        return 0.0
    pb = _hist_pct(b, edges)
    pc = _hist_pct(c, edges)
    # Align lengths if unique edges collapsed
    n = min(len(pb), len(pc))
    pb, pc = pb[:n], pc[:n]
    return float(np.sum((pc - pb) * np.log(pc / pb)))


def compute_feature_psi(
    baseline_snapshot: Mapping[str, Sequence[float]],
    live_rows: Sequence[Mapping[str, float]],
    feature_names: Optional[List[str]] = None,
) -> Dict[str, float]:
    names = feature_names or list(baseline_snapshot.keys())
    out: Dict[str, float] = {}
    for name in names:
        base = baseline_snapshot.get(name) or []
        cur = [float(r.get(name, 0.0)) for r in live_rows]
        out[name] = psi_for_feature(base, cur)
    return out


def max_psi(psi_by_feature: Mapping[str, float]) -> Tuple[float, str]:
    if not psi_by_feature:
        return 0.0, ""
    name = max(psi_by_feature, key=lambda k: psi_by_feature[k])
    return float(psi_by_feature[name]), name


def check_drift(
    baseline_snapshot: Mapping[str, Sequence[float]],
    live_rows: Sequence[Mapping[str, float]],
    *,
    threshold: float = 0.25,
    feature_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    psi_map = compute_feature_psi(baseline_snapshot, live_rows, feature_names)
    worst, feat = max_psi(psi_map)
    breached = worst >= threshold
    if breached:
        logger.warning(f"[DriftMonitor] PSI breach feature={feat} psi={worst:.3f} thr={threshold}")
    return {
        "psi_by_feature": psi_map,
        "max_psi": worst,
        "max_psi_feature": feat,
        "threshold": threshold,
        "breached": breached,
    }


def snapshot_from_matrix(
    X: np.ndarray,
    feature_names: List[str],
    max_store: int = 2000,
) -> Dict[str, List[float]]:
    """Store up to max_store samples per feature for PSI baselines."""
    n = min(len(X), max_store)
    snap: Dict[str, List[float]] = {}
    for i, name in enumerate(feature_names):
        if i >= X.shape[1]:
            break
        snap[name] = [float(v) for v in X[:n, i]]
    return snap
