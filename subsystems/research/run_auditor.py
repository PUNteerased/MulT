"""CLI: python -m subsystems.research.run_auditor

Run only when trading GPU inference is stopped (LM Studio ~4.94GB for qwen/qwen3-8b).
"""
from __future__ import annotations

import argparse
import json

from subsystems.research.auditor import run_calculation_audit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Local Calculation Auditor (LM Studio or rules)")
    parser.add_argument(
        "--rules-only",
        action="store_true",
        help="Skip LM Studio even if online",
    )
    parser.add_argument(
        "--with-web",
        action="store_true",
        help="Optional DuckDuckGo citations (does not change rule results)",
    )
    args = parser.parse_args(argv)
    report = run_calculation_audit(use_llm=not args.rules_only, with_web=args.with_web)
    print(json.dumps(
        {
            "report_id": report.get("report_id"),
            "status": report.get("status"),
            "mode": report.get("mode"),
            "path": report.get("path"),
            "checks_passed": sum(1 for c in report.get("checks", []) if c.get("ok")),
            "checks_total": len(report.get("checks", [])),
            "summary": report.get("summary"),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
