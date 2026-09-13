"""
Persist research proposals under data/research_reports/.

Statuses: needs_review | proposed | approved | rejected | backtested
Never writes config/settings.py or symbols.yaml.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from config.settings import DUCKDB_PATH, RESEARCH_REPORTS_DIR

ALLOWED_STATUSES: Set[str] = {
    "needs_review",
    "proposed",
    "approved",
    "rejected",
    "backtested",
}

# Human may set these via API / CLI
TRANSITION_STATUSES: Set[str] = {"approved", "rejected", "backtested", "proposed", "needs_review"}


def _ensure_dir() -> Path:
    RESEARCH_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESEARCH_REPORTS_DIR


def _archive_dir() -> Path:
    p = _ensure_dir() / "archive"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _report_path(report_id: str) -> Path:
    return _ensure_dir() / f"{report_id}.json"


def save_report(report: Dict[str, Any]) -> Path:
    out = _ensure_dir()
    rid = report.get("report_id") or f"RES_{uuid.uuid4().hex[:10].upper()}"
    report["report_id"] = rid
    report.setdefault("status", "proposed")
    if report["status"] not in ALLOWED_STATUSES:
        report["status"] = "proposed"
    report.setdefault("created_at", time.time())
    report.setdefault("auto_apply", False)
    report["auto_apply"] = False  # hard guarantee
    path = out / f"{rid}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    _maybe_duckdb_upsert(report)
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
                    "module": data.get("module"),
                    "mode": data.get("mode"),
                    "created_at": data.get("created_at"),
                    "title": data.get("title", "Research Report"),
                    "summary": data.get("summary", "")[:240],
                    "path": str(p),
                }
            )
        except Exception as e:
            logger.debug(f"[ResearchStore] skip {p}: {e}")
    return rows


def get_report(report_id: str) -> Optional[Dict[str, Any]]:
    path = _report_path(report_id)
    if not path.exists():
        matches = list(_ensure_dir().glob(f"*{report_id}*.json"))
        if not matches:
            return None
        path = matches[0]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_status(
    report_id: str,
    status: str,
    note: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Update status only — never mutates trading config files."""
    if status not in TRANSITION_STATUSES:
        raise ValueError(f"invalid status: {status}")
    report = get_report(report_id)
    if report is None:
        return None
    report["status"] = status
    report["status_updated_at"] = time.time()
    if note:
        history = report.setdefault("status_history", [])
        history.append({"status": status, "note": note, "at": report["status_updated_at"]})
    if extra:
        report.update(extra)
    report["auto_apply"] = False
    save_report(report)
    return report


def prune_reports(
    max_age_days: int = 90,
    reject_max_age_days: int = 30,
    archive: bool = True,
) -> Dict[str, int]:
    """
    Move old reports to archive/ (or delete if archive=False).
    - Any status older than max_age_days
    - rejected older than reject_max_age_days
    """
    now = time.time()
    max_age = max_age_days * 86400
    reject_age = reject_max_age_days * 86400
    moved = 0
    deleted = 0
    for path in list(_ensure_dir().glob("RES_*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        created = float(data.get("created_at") or path.stat().st_mtime)
        age = now - created
        status = data.get("status", "proposed")
        should = age > max_age or (status == "rejected" and age > reject_age)
        if not should:
            continue
        if archive:
            dest = _archive_dir() / path.name
            shutil.move(str(path), str(dest))
            moved += 1
            logger.info(f"[ResearchStore] archived {path.name} status={status} age_days={age/86400:.1f}")
        else:
            path.unlink(missing_ok=True)
            deleted += 1
        _maybe_duckdb_delete(data.get("report_id") or path.stem)
    return {"archived": moved, "deleted": deleted}


def _maybe_duckdb_upsert(report: Dict[str, Any]) -> None:
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
                report.get("mode") or report.get("module"),
                report.get("title", "Research Report"),
                report.get("created_at", time.time()),
                json.dumps(report),
            ],
        )
        con.close()
    except Exception as e:
        logger.debug(f"[ResearchStore] DuckDB optional upsert skipped: {e}")


def _maybe_duckdb_delete(report_id: Optional[str]) -> None:
    if not report_id:
        return
    try:
        import duckdb

        path = Path(DUCKDB_PATH)
        if not path.exists():
            return
        con = duckdb.connect(str(path))
        con.execute("DELETE FROM research_proposals WHERE report_id = ?", [report_id])
        con.close()
    except Exception as e:
        logger.debug(f"[ResearchStore] DuckDB optional delete skipped: {e}")
