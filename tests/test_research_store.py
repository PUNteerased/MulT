"""Store status transitions + retention."""
from __future__ import annotations

import time
from pathlib import Path

from subsystems.research.store import prune_reports, save_report, update_status, get_report


def test_update_status_and_prune(tmp_path, monkeypatch):
    monkeypatch.setattr("subsystems.research.store.RESEARCH_REPORTS_DIR", tmp_path)
    report = {
        "title": "t",
        "module": "news_digest",
        "status": "proposed",
        "summary": "s",
        "created_at": time.time() - 40 * 86400,
    }
    save_report(report)
    rid = report["report_id"]
    updated = update_status(rid, "rejected", note="nope")
    assert updated["status"] == "rejected"
    loaded = get_report(rid)
    assert loaded["status"] == "rejected"

    stats = prune_reports(max_age_days=90, reject_max_age_days=30, archive=True)
    assert stats["archived"] >= 1
    assert not (tmp_path / f"{rid}.json").exists()
    assert (tmp_path / "archive" / f"{rid}.json").exists()
