"""CLI: News & Macro Digest."""
from __future__ import annotations

import argparse
import json

from subsystems.research.news_digest import run_news_digest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rules-only", action="store_true", help="Search only, no LM Studio")
    args = p.parse_args()
    report = run_news_digest(use_llm=not args.rules_only)
    print(json.dumps({"report_id": report.get("report_id"), "status": report.get("status")}, indent=2))


if __name__ == "__main__":
    main()
