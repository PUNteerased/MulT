"""GPU / enable gates for Research Agent off-hours runner."""
from __future__ import annotations

import os
import re
import subprocess
from typing import Optional, Tuple

from loguru import logger


def research_agent_enabled() -> bool:
    raw = os.environ.get("RESEARCH_AGENT_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def gpu_util_percent() -> Optional[float]:
    """Return GPU util % from nvidia-smi, or None if unavailable."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            timeout=5,
            text=True,
        )
        vals = []
        for line in out.strip().splitlines():
            m = re.search(r"(\d+(?:\.\d+)?)", line)
            if m:
                vals.append(float(m.group(1)))
        if not vals:
            return None
        return max(vals)
    except Exception as e:
        logger.debug(f"[ResearchGate] nvidia-smi unavailable: {e}")
        return None


def should_skip_for_gpu(
    threshold_pct: Optional[float] = None,
) -> Tuple[bool, str]:
    """
    Returns (skip, reason).
    If nvidia-smi missing → do not skip (still respect RESEARCH_AGENT_ENABLED elsewhere).
    """
    if threshold_pct is None:
        threshold_pct = float(os.environ.get("RESEARCH_GPU_SKIP_PCT", "40"))
    util = gpu_util_percent()
    if util is None:
        return False, "no_nvidia_smi"
    if util >= threshold_pct:
        return True, f"gpu_util={util:.0f}>={threshold_pct:.0f}"
    return False, f"gpu_util={util:.0f}<{threshold_pct:.0f}"


def gate_research_run(ignore_gpu: bool = False) -> Tuple[bool, str]:
    """
    Three-layer gate:
      1) RESEARCH_AGENT_ENABLED kill-switch
      2) nvidia-smi util >= RESEARCH_GPU_SKIP_PCT (default 40)
      3) if no nvidia-smi, skip GPU check only
    Returns (allowed, reason).
    """
    if not research_agent_enabled():
        return False, "RESEARCH_AGENT_ENABLED=0"
    if ignore_gpu:
        return True, "ignore_gpu"
    skip, reason = should_skip_for_gpu()
    if skip:
        return False, reason
    return True, reason
