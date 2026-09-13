"""Strategy Literature Scanner — candidate ideas only; human selects."""
from __future__ import annotations

import time
from typing import Any, Dict

from subsystems.research.agent_loop import run_research_agent
from subsystems.research.store import save_report

CURRENT_STACK = (
    "Current MulT stack: M1 liquidity sweep sniper, LightGBM meta-label ≥75%, "
    "RiskGuard50 ($2.50 / 0.01 lot), ATR k1/k2 SL/trail, HMM regime labels, "
    "FinBERT/calendar Red Folder halt, Weekend Learner retrain (no research auto-apply)."
)

SEED_QUERIES = [
    "liquidity sweep detection forex research",
    "meta labeling Lopez de Prado calibration",
    "ATR position sizing stop loss",
    "order block kill zone ICT trading research",
]

SYSTEM = (
    "You scan trading research literature and compare ideas to an existing stack. "
    "Output candidate ideas for humans — never claim they should auto-deploy. "
    "Use only provided search results; do not invent paper titles or URLs."
)


def run_strategy_scanner(use_llm: bool = True) -> Dict[str, Any]:
    out = run_research_agent(
        system_prompt=SYSTEM,
        user_prompt=(
            f"{CURRENT_STACK}\n\n"
            "List candidate ideas on liquidity sweeps, meta-labeling calibration, "
            "and ATR/position sizing that differ from or could improve the current stack."
        ),
        seed_queries=SEED_QUERIES,
        require_citations=True,
        use_llm=use_llm,
    )
    ideas = out.get("candidate_ideas") or []
    findings = out.get("findings") or []
    if not ideas and findings:
        ideas = findings[:5]

    report: Dict[str, Any] = {
        "title": "Strategy Literature Scanner",
        "module": "strategy_scanner",
        "status": out["status_hint"],
        "mode": "lm_studio+web" if out.get("llm_meta", {}).get("used") else "search_only",
        "summary": out.get("summary") or "",
        "narrative": out.get("narrative") or "",
        "findings": findings,
        "candidate_ideas": ideas,
        "citations": out.get("citations") or [],
        "tool_trace": out.get("tool_trace") or [],
        "search_meta": out.get("search_meta") or {},
        "current_stack": CURRENT_STACK,
        "llm_meta": out.get("llm_meta") or {},
        "created_at": time.time(),
        "auto_apply": False,
    }
    if report["search_meta"].get("failed"):
        report["status"] = "needs_review"
        report["mode"] = "search_failed"
    path = save_report(report)
    report["path"] = str(path)
    return report
