"""Smoke tests for research auditor (rules mode — no LM Studio required)."""
from subsystems.research.auditor import run_calculation_audit
from subsystems.research.store import list_reports, get_report


def test_auditor_rules_only_writes_proposed():
    report = run_calculation_audit(use_llm=False)
    assert report["status"] == "proposed"
    assert report["auto_apply"] is False
    assert report["mode"] == "rules_only"
    assert report.get("report_id")
    assert all(c["ok"] for c in report["checks"])
    loaded = get_report(report["report_id"])
    assert loaded is not None
    assert loaded["status"] == "proposed"
    rows = list_reports(limit=5)
    assert any(r["report_id"] == report["report_id"] for r in rows)
