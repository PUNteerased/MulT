"""News & Macro Digest — context only, never feeds live models."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from subsystems.research.agent_loop import run_research_agent
from subsystems.research.store import save_report

SEED_QUERIES = [
    "EURUSD week ahead CPI FOMC",
    "USDJPY Bank of Japan Fed policy",
    "XAUUSD gold geopolitical risk week",
    "Bitcoin BTCUSD macro news week",
    "high impact forex calendar NFP CPI FOMC",
]

SYSTEM = (
    "You are a macro research assistant for a $50 forex/crypto sniper desk. "
    "Summarize why headlines may matter for EURUSD, USDJPY, XAUUSD, BTCUSD next week. "
    "Use only the provided search results. Do not invent numbers or URLs. "
    "This is context for humans — not a trading signal."
)


def run_news_digest(use_llm: bool = True) -> Dict[str, Any]:
    out = run_research_agent(
        system_prompt=SYSTEM,
        user_prompt=(
            "Produce a weekly macro digest for EURUSD, USDJPY, XAUUSD, BTCUSD. "
            "List concrete findings tied to citations."
        ),
        seed_queries=SEED_QUERIES,
        require_citations=True,
        use_llm=use_llm,
    )
    report: Dict[str, Any] = {
        "title": "News & Macro Digest",
        "module": "news_digest",
        "status": out["status_hint"],
        "mode": "lm_studio+web" if out.get("llm_meta", {}).get("used") else "search_only",
        "summary": out.get("summary") or "",
        "narrative": out.get("narrative") or "",
        "findings": out.get("findings") or [],
        "citations": out.get("citations") or [],
        "tool_trace": out.get("tool_trace") or [],
        "search_meta": out.get("search_meta") or {},
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
