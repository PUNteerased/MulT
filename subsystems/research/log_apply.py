"""
Human-apply audit trail helper.

Does NOT write trading config values. Only appends APPLY_LOG.md when a human
records that they manually copied settings from a research report.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import List, Optional

from config.settings import RESEARCH_REPORTS_DIR
from subsystems.research.store import get_report

APPLY_LOG = RESEARCH_REPORTS_DIR / "APPLY_LOG.md"
CHAT_APPLY_LOG = RESEARCH_REPORTS_DIR / "CHAT_APPLY_LOG.md"


def log_apply(report_id: str, files: List[str], note: str = "") -> Path:
    report = get_report(report_id)
    if report is None:
        raise FileNotFoundError(f"report not found: {report_id}")
    RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    files_s = ", ".join(files) if files else "(unspecified)"
    line = (
        f"| {ts} | `{report_id}` | {report.get('module','')} | "
        f"{files_s} | {note or report.get('title','')} |\n"
    )
    if not APPLY_LOG.exists():
        APPLY_LOG.write_text(
            "# Research apply audit log\n\n"
            "Record manual config merges. Commit messages should include "
            "`research_report_id=RES_…`.\n\n"
            "| ts | report_id | module | files | note |\n"
            "|----|-----------|--------|-------|------|\n",
            encoding="utf-8",
        )
    with open(APPLY_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    return APPLY_LOG


def log_chat_action(
    *,
    actor: str,
    action_id: str,
    action_type: str,
    decision: str,
    web_sourced: bool = False,
    detail: Optional[dict] = None,
    tool_trace_ids: Optional[List[str]] = None,
) -> Path:
    """Append Research Chat confirm/reject audit with actor identity."""
    import json

    RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    detail_s = json.dumps(detail or {}, ensure_ascii=False)[:800]
    traces = ",".join(tool_trace_ids or [])
    line = (
        f"| {ts} | `{actor}` | `{action_id}` | {action_type} | {decision} | "
        f"{'yes' if web_sourced else 'no'} | {traces} | {detail_s} |\n"
    )
    if not CHAT_APPLY_LOG.exists():
        CHAT_APPLY_LOG.write_text(
            "# Research Chat apply audit\n\n"
            "| ts | actor | action_id | type | decision | web_sourced | tool_trace_ids | detail |\n"
            "|----|-------|-----------|------|----------|-------------|----------------|--------|\n",
            encoding="utf-8",
        )
    with open(CHAT_APPLY_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    return CHAT_APPLY_LOG


def link_backtest(report_id: str, validation_report_path: str) -> dict:
    """Mark approved report as backtested after human-run validation."""
    from subsystems.research.store import update_status

    return update_status(
        report_id,
        "backtested",
        note=f"validation={validation_report_path}",
        extra={"validation_report": validation_report_path},
    ) or {}


def main():
    p = argparse.ArgumentParser(description="Log manual research→config apply")
    p.add_argument("report_id")
    p.add_argument("--files", nargs="*", default=[], help="Config files touched")
    p.add_argument("--note", default="")
    p.add_argument("--backtest", default="", help="Path to validation JSON to mark backtested")
    args = p.parse_args()
    if args.backtest:
        r = link_backtest(args.report_id, args.backtest)
        print({"status": r.get("status"), "report_id": args.report_id})
    else:
        path = log_apply(args.report_id, args.files, args.note)
        print(f"logged → {path}")
        print(f"Commit hint: research_report_id={args.report_id}")


if __name__ == "__main__":
    main()
