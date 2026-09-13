"""Persist research proposals under data/research_reports/ (status=proposed only)."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from config.settings import DUCKDB_PATH, RESEARCH_REPORTS_DIR


def _ensure_dir() -> Path:
    RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESEARCH_REPORTS_DIR


def save_report(report: Dict[str, Any]) -> Path:
    out = _ensure_dir()
    rid = report.get("report_id") or f"RES_{uuid.uuid4().hex[:10].upper()}"
    report["report_id"] = rid
    report.setdefault("status", "proposed")
    report.setdefault("created_at", time.time())
    path = out / f"{rid}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    _maybe_duckdb_insert(report)
    logger.info(f"[ResearchStore] Saved {path} status={report['status']}")
    return path


def list_reports(limit: int = 50) -> List[Dict[str, Any]]:
    out = _ensure_dir()
    files = sorted(out.glob("RES_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for p in files[:limit]:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            rows.append(
                {
                    "report_id": data.get("report_id", p.stem),
                    "status": data.get("status", "proposed"),
                    "mode": data.get("mode"),
                    "created_at": data.get("created_at"),
                    "title": data.get("title", "Calculation Audit"),
                    "summary": data.get("summary", "")[:240],
                    "path": str(p),
                }
            )
        except Exception as e:
            logger.debug(f"[ResearchStore] skip {p}: {e}")
    return rows


def get_report(report_id: str) -> Optional[Dict[str, Any]]:
    path = _ensure_dir() / f"{report_id}.json"
    if not path.exists():
        # allow bare id without RES_ prefix mismatch
        matches = list(_ensure_dir().glob(f"*{report_id}*.json"))
        if not matches:
            return None
        path = matches[0]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _maybe_duckdb_insert(report: Dict[str, Any]) -> None:
    """Optional DuckDB table for proposals — best effort, never raises."""
    try:
        import duckdb

        path = Path(DUCKDB_PATH)
        if not path.exists():
            return
        con = duckdb.connect(str(path))
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS research_proposals (
                report_id VARCHAR PRIMARY KEY,
                status VARCHAR,
                mode VARCHAR,
                title VARCHAR,
                created_at DOUBLE,
                payload_json VARCHAR
            );
            """
        )
        con.execute(
            """
            INSERT OR REPLACE INTO research_proposals
            (report_id, status, mode, title, created_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            [
                report.get("report_id"),
                report.get("status", "proposed"),
                report.get("mode"),
                report.get("title", "Calculation Audit"),
                report.get("created_at", time.time()),
                json.dumps(report),
            ],
        )
        con.close()
    except Exception as e:
        logger.debug(f"[ResearchStore] DuckDB optional insert skipped: {e}")
