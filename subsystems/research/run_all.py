"""Run all research modules (off-hours friendly)."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from subsystems.research.auditor import run_calculation_audit
from subsystems.research.gates import gate_research_run
from subsystems.research.news_digest import run_news_digest
from subsystems.research.store import prune_reports
from subsystems.research.strategy_scanner import run_strategy_scanner


def is_weekend_utc() -> bool:
    return datetime.now(timezone.utc).weekday() >= 5


def run_all(
    *,
    force: bool = False,
    ignore_gpu: bool = False,
    halt: bool = False,
    use_llm: bool = True,
    modules: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    modules: auditor | news | strategy | all
    Off-hours: weekend or halt=True unless force=True.
    """
    allowed, gate_reason = gate_research_run(ignore_gpu=ignore_gpu)
    if not allowed:
        logger.warning(f"[ResearchAll] skipped: {gate_reason}")
        return {"ok": False, "reason": gate_reason, "reports": []}

    off_hours = is_weekend_utc() or halt
    if not force and not off_hours:
        logger.info("[ResearchAll] not weekend/halt — use --force to override")
        return {"ok": False, "reason": "not_off_hours", "reports": []}

    prune_stats = prune_reports()
    logger.info(f"[ResearchAll] prune={prune_stats} gate={gate_reason}")

    wanted = modules or ["all"]
    if "all" in wanted:
        wanted = ["auditor", "news", "strategy"]

    reports: List[Dict[str, Any]] = []
    if "auditor" in wanted:
        reports.append(run_calculation_audit(use_llm=use_llm))
    if "news" in wanted:
        if use_llm:
            reports.append(run_news_digest(use_llm=True))
        else:
            reports.append(run_news_digest(use_llm=False))
    if "strategy" in wanted:
        reports.append(run_strategy_scanner(use_llm=use_llm))

    return {
        "ok": True,
        "reason": gate_reason,
        "prune": prune_stats,
        "reports": [
            {
                "report_id": r.get("report_id"),
                "module": r.get("module"),
                "status": r.get("status"),
                "title": r.get("title"),
            }
            for r in reports
        ],
    }


def main():
    p = argparse.ArgumentParser(description="MulT Research Agent runner")
    p.add_argument("--force", action="store_true", help="Ignore weekend/halt check")
    p.add_argument("--ignore-gpu", action="store_true", help="Skip nvidia-smi util gate")
    p.add_argument("--halt", action="store_true", help="Treat as HALT_TRADING window")
    p.add_argument("--rules-only", action="store_true", help="No LLM (auditor rules; search-only digests)")
    p.add_argument(
        "--module",
        choices=["auditor", "news", "strategy", "all"],
        default="all",
    )
    args = p.parse_args()
    result = run_all(
        force=args.force,
        ignore_gpu=args.ignore_gpu,
        halt=args.halt,
        use_llm=not args.rules_only,
        modules=[args.module],
    )
    print(result)


if __name__ == "__main__":
    main()
