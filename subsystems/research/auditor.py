"""
Calculation Auditor: rule-based money/ATR checklist is source of truth.
Optional LM Studio narrative; optional web enrichment for citations only.
Never writes settings. Status from rules — require_citations=False.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from loguru import logger

from config.settings import (
    FIXED_LOT_SIZE,
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_SPREAD_RISK_PCT,
    RISK_PCT_PER_TRADE,
    RISK_DOLLARS_FLOOR,
    RISK_DOLLARS_CEILING,
    SYMBOLS_CONFIG,
)
from core.risk.money import price_diff_to_usd, spread_points_to_usd
from subsystems.research.agent_loop import check_quality
from subsystems.research.llm_client import LocalLLMClient
from subsystems.research.store import save_report
from subsystems.risk_guard.guard_50 import RiskGuard50


def _rule_checklist() -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    e = price_diff_to_usd("EURUSD", 1.10000, 1.09750, FIXED_LOT_SIZE)
    checks.append(
        {
            "id": "eurusd_25pip_cap",
            "ok": abs(e - 2.5) < 1e-4,
            "detail": f"EURUSD 25 pips @0.01 lot → ${e:.4f} (expect $2.50)",
        }
    )

    j = price_diff_to_usd("USDJPY", 150.0, 149.9, FIXED_LOT_SIZE)
    expect_j = 0.10 * 100000 * 0.01 / 150.0
    checks.append(
        {
            "id": "usdjpy_quote_div",
            "ok": abs(j - expect_j) < 1e-4,
            "detail": f"USDJPY 10 pips @150 → ${j:.4f} (expect ${expect_j:.4f})",
        }
    )

    x = price_diff_to_usd("XAUUSD", 2400.0, 2399.0, FIXED_LOT_SIZE)
    checks.append(
        {
            "id": "xauusd_1usd",
            "ok": abs(x - 1.0) < 1e-4,
            "detail": f"XAUUSD $1 move @0.01 → ${x:.4f} (expect $1.00)",
        }
    )
    b = price_diff_to_usd("BTCUSD", 67000.0, 66900.0, FIXED_LOT_SIZE)
    checks.append(
        {
            "id": "btcusd_100usd",
            "ok": abs(b - 1.0) < 1e-4,
            "detail": f"BTCUSD $100 move @0.01 → ${b:.4f} (expect $1.00)",
        }
    )

    s = spread_points_to_usd("EURUSD", 20, FIXED_LOT_SIZE, mid_price=1.10)
    cap50 = RiskGuard50.compute_max_risk_dollars(50.0, 1.0)
    max_spread = cap50 * MAX_SPREAD_RISK_PCT
    checks.append(
        {
            "id": "spread_budget_default",
            "ok": s <= max_spread,
            "detail": f"EURUSD 20 pts spread ≈ ${s:.4f}; budget ${max_spread:.2f} "
            f"({MAX_SPREAD_RISK_PCT*100:.0f}% of ${cap50:.2f} @ eq=$50)",
        }
    )

    for sym, cfg in SYMBOLS_CONFIG.items():
        checks.append(
            {
                "id": f"atr_cfg_{sym}",
                "ok": cfg.use_atr_sizing and cfg.atr_k1 > 0 and cfg.atr_k2 > 0,
                "detail": f"{sym}: k1={cfg.atr_k1} k2={cfg.atr_k2} tf={cfg.atr_timeframe_sl} "
                f"use_atr={cfg.use_atr_sizing}",
            }
        )

    checks.append(
        {
            "id": "risk_pct_floor_at_50",
            "ok": abs(RiskGuard50.compute_max_risk_dollars(50.0) - RISK_DOLLARS_FLOOR) < 1e-6,
            "detail": f"eq=$50 → cap=${RiskGuard50.compute_max_risk_dollars(50.0):.2f} "
            f"(floor ${RISK_DOLLARS_FLOOR}, pct={RISK_PCT_PER_TRADE})",
        }
    )
    checks.append(
        {
            "id": "risk_ceiling_at_1200",
            "ok": abs(RiskGuard50.compute_max_risk_dollars(1200.0) - RISK_DOLLARS_CEILING) < 1e-6,
            "detail": f"eq=$1200 → cap=${RiskGuard50.compute_max_risk_dollars(1200.0):.2f} "
            f"(ceiling ${RISK_DOLLARS_CEILING})",
        }
    )
    checks.append(
        {
            "id": "risk_bounds_sane",
            "ok": (
                0 < RISK_PCT_PER_TRADE <= 0.02
                and RISK_DOLLARS_FLOOR > 0
                and RISK_DOLLARS_CEILING >= RISK_DOLLARS_FLOOR
            ),
            "detail": f"pct={RISK_PCT_PER_TRADE} floor={RISK_DOLLARS_FLOOR} ceiling={RISK_DOLLARS_CEILING}",
        }
    )
    return checks


def _proposals_from_checks(checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    failed = [c for c in checks if not c["ok"]]
    proposals = []
    if failed:
        proposals.append(
            {
                "type": "fix",
                "status": "proposed",
                "message": "One or more money/ATR checklist items failed — review before demo scale.",
                "failed_ids": [c["id"] for c in failed],
            }
        )
    else:
        proposals.append(
            {
                "type": "info",
                "status": "proposed",
                "message": "Money math + ATR config checklist passed. No settings auto-write.",
            }
        )
    proposals.append(
        {
            "type": "tuning_hint",
            "status": "proposed",
            "message": "Keep k1=1.2 / k2=0.15 until ≥50–100 demo trades; log atr_at_entry/sl_usd per ticket.",
        }
    )
    return proposals


def run_calculation_audit(
    use_llm: bool = True,
    with_web: bool = False,
) -> Dict[str, Any]:
    checks = _rule_checklist()
    proposals = _proposals_from_checks(checks)
    passed = sum(1 for c in checks if c["ok"])
    all_ok = passed == len(checks)
    mode = "rules_only"
    narrative = (
        f"Rule-based Calculation Auditor: {passed}/{len(checks)} checks passed. "
        f"Dynamic risk {RISK_PCT_PER_TRADE*100:.2f}% eq "
        f"(floor ${RISK_DOLLARS_FLOOR:.2f} / ceiling ${RISK_DOLLARS_CEILING:.2f}) "
        f"@ {FIXED_LOT_SIZE} lot. "
        "No configuration files were modified."
    )
    llm_meta = {
        "requested": use_llm,
        "base_url": LLM_BASE_URL,
        "model": LLM_MODEL,
        "used": False,
        "error": None,
    }
    citations: List[Dict[str, Any]] = []
    tool_trace: List[Dict[str, Any]] = []

    if use_llm:
        client = LocalLLMClient()
        if client.is_reachable():
            prompt_checks = "\n".join(
                f"- [{ 'OK' if c['ok'] else 'FAIL' }] {c['detail']}" for c in checks
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a trading risk calculation auditor. "
                        "Do NOT invent broker specs. Summarize checklist results in under 180 words. "
                        "Propose only human-reviewable hints. Never instruct to auto-change production settings."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Local Deep-Sniper $50 account audit.\n"
                        f"Model endpoint: {LLM_BASE_URL} model={LLM_MODEL}\n"
                        f"Checklist:\n{prompt_checks}\n"
                        "Write a short narrative + 2-3 proposed follow-ups (status proposed only)."
                    ),
                },
            ]
            text = client.chat(messages)
            if text:
                mode = "lm_studio+rules"
                narrative = text.strip()
                llm_meta["used"] = True
            else:
                llm_meta["error"] = "chat_failed"
                logger.warning("[Auditor] LM Studio reachable but chat failed — rules only")
        else:
            llm_meta["error"] = "offline"
            logger.info("[Auditor] LM Studio offline — rule-based checklist only")

    if with_web:
        # Optional citations only — never override rule results
        from subsystems.research.agent_loop import run_research_agent

        enrich = run_research_agent(
            system_prompt=(
                "You enrich a calculation audit with public references on pip value / ATR sizing. "
                "Do not invent numbers that contradict the checklist."
            ),
            user_prompt="Find references for forex pip value and ATR stop sizing conventions.",
            seed_queries=[
                "forex pip value calculation standard lot",
                "ATR multiple stop loss trading risk",
            ],
            require_citations=False,  # auditor status from rules
            use_llm=False,  # snippets only; rules remain source of truth
        )
        citations = enrich.get("citations") or []
        tool_trace = enrich.get("tool_trace") or []
        if citations:
            mode = f"{mode}+web"

    findings = [{"id": c["id"], "ok": c["ok"], "detail": c["detail"]} for c in checks]
    # Auditor: require_citations=False — empty citations OK; empty findings not OK
    status = check_quality(
        citations=citations,
        findings=findings,
        require_citations=False,
        search_failed=False,
    )
    if not all_ok:
        status = "needs_review"

    report = {
        "title": "Calculation Auditor Report",
        "module": "auditor",
        "status": status,
        "mode": mode,
        "summary": narrative[:400],
        "narrative": narrative,
        "findings": findings,
        "checks": checks,
        "proposals": proposals,
        "citations": citations,
        "tool_trace": tool_trace,
        "llm": llm_meta,
        "llm_meta": llm_meta,
        "created_at": time.time(),
        "auto_apply": False,
    }
    path = save_report(report)
    report["path"] = str(path)
    return report
