"""
Calculation Auditor: always runs rule-based money/ATR checklist.
Optionally enriches narrative via local LM Studio (qwen/qwen3-8b).
Outputs status=proposed only — never writes settings.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from loguru import logger

from config.settings import (
    FIXED_LOT_SIZE,
    LLM_BASE_URL,
    LLM_MODEL,
    MAX_RISK_DOLLARS_PER_TRADE,
    MAX_SPREAD_RISK_PCT,
    SYMBOLS_CONFIG,
)
from core.risk.money import price_diff_to_usd, spread_points_to_usd
from subsystems.research.llm_client import LocalLLMClient
from subsystems.research.store import save_report


def _rule_checklist() -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []

    # EURUSD 25 pips = $2.50
    e = price_diff_to_usd("EURUSD", 1.10000, 1.09750, FIXED_LOT_SIZE)
    checks.append(
        {
            "id": "eurusd_25pip_cap",
            "ok": abs(e - 2.5) < 1e-4,
            "detail": f"EURUSD 25 pips @0.01 lot → ${e:.4f} (expect $2.50)",
        }
    )

    # USDJPY scales with price
    j = price_diff_to_usd("USDJPY", 150.0, 149.9, FIXED_LOT_SIZE)
    expect_j = 0.10 * 100000 * 0.01 / 150.0
    checks.append(
        {
            "id": "usdjpy_quote_div",
            "ok": abs(j - expect_j) < 1e-4,
            "detail": f"USDJPY 10 pips @150 → ${j:.4f} (expect ${expect_j:.4f})",
        }
    )

    # XAU / BTC
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

    # Spread budget
    s = spread_points_to_usd("EURUSD", 20, FIXED_LOT_SIZE, mid_price=1.10)
    max_spread = MAX_RISK_DOLLARS_PER_TRADE * MAX_SPREAD_RISK_PCT
    checks.append(
        {
            "id": "spread_budget_default",
            "ok": s <= max_spread,
            "detail": f"EURUSD 20 pts spread ≈ ${s:.4f}; budget ${max_spread:.2f} "
            f"({MAX_SPREAD_RISK_PCT*100:.0f}% of ${MAX_RISK_DOLLARS_PER_TRADE})",
        }
    )

    # Symbol ATR params present
    for sym, cfg in SYMBOLS_CONFIG.items():
        checks.append(
            {
                "id": f"atr_cfg_{sym}",
                "ok": cfg.use_atr_sizing and cfg.atr_k1 > 0 and cfg.atr_k2 > 0,
                "detail": f"{sym}: k1={cfg.atr_k1} k2={cfg.atr_k2} tf={cfg.atr_timeframe_sl} "
                f"use_atr={cfg.use_atr_sizing}",
            }
        )

    # Cap consistency
    checks.append(
        {
            "id": "hard_cap_2_50",
            "ok": MAX_RISK_DOLLARS_PER_TRADE == 2.50,
            "detail": f"MAX_RISK_DOLLARS_PER_TRADE={MAX_RISK_DOLLARS_PER_TRADE}",
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


def run_calculation_audit(use_llm: bool = True) -> Dict[str, Any]:
    checks = _rule_checklist()
    proposals = _proposals_from_checks(checks)
    passed = sum(1 for c in checks if c["ok"])
    mode = "rules_only"
    narrative = (
        f"Rule-based Calculation Auditor: {passed}/{len(checks)} checks passed. "
        f"Hard risk cap ${MAX_RISK_DOLLARS_PER_TRADE:.2f} @ {FIXED_LOT_SIZE} lot. "
        "No configuration files were modified."
    )
    llm_meta = {
        "requested": use_llm,
        "base_url": LLM_BASE_URL,
        "model": LLM_MODEL,
        "used": False,
        "error": None,
    }

    if use_llm:
        client = LocalLLMClient()
        if client.is_reachable():
            prompt_checks = "\n".join(f"- [{ 'OK' if c['ok'] else 'FAIL' }] {c['detail']}" for c in checks)
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

    report = {
        "title": "Calculation Auditor Report",
        "status": "proposed",
        "mode": mode,
        "summary": narrative[:400],
        "narrative": narrative,
        "checks": checks,
        "proposals": proposals,
        "llm": llm_meta,
        "created_at": time.time(),
        "auto_apply": False,
    }
    path = save_report(report)
    report["path"] = str(path)
    return report
