"""Unit tests for research foundation (web_search + quality gate + agent_loop)."""
from __future__ import annotations

from unittest.mock import patch

from subsystems.research.agent_loop import check_quality, run_research_agent
from subsystems.research.web_search import SearchResponse, SearchResult, search_web


def test_check_quality_news_requires_citations():
    assert (
        check_quality(citations=[], findings=["x"], require_citations=True)
        == "needs_review"
    )
    assert (
        check_quality(
            citations=[{"url": "https://example.com"}],
            findings=[],
            require_citations=True,
        )
        == "needs_review"
    )
    assert (
        check_quality(
            citations=[{"url": "https://example.com"}],
            findings=["ok"],
            require_citations=True,
        )
        == "proposed"
    )


def test_check_quality_auditor_skips_citation_requirement():
    # rules-only auditor: findings present, no citations → still proposed
    assert (
        check_quality(
            citations=[],
            findings=[{"id": "rule", "ok": True}],
            require_citations=False,
        )
        == "proposed"
    )
    assert (
        check_quality(citations=[], findings=[], require_citations=False)
        == "needs_review"
    )


def test_check_quality_search_failed():
    assert (
        check_quality(
            citations=[],
            findings=[],
            require_citations=True,
            search_failed=True,
        )
        == "needs_review"
    )


def test_search_web_retries_then_fail_soft():
    calls = {"n": 0}

    def boom(*_a, **_k):
        calls["n"] += 1
        raise RuntimeError("rate_limited")

    with patch("subsystems.research.web_search.time.sleep"), patch(
        "duckduckgo_search.DDGS", side_effect=boom
    ):
        resp = search_web("EURUSD CPI", max_retries=3, base_backoff_s=0.01)
    assert resp.ok is False
    assert resp.results == []
    assert resp.error
    assert calls["n"] == 3
    assert resp.attempts == 3


def test_agent_loop_search_failed_no_stale_data():
    failed = SearchResponse(
        results=[], query="q", ok=False, error="boom", attempts=3
    )
    with patch("subsystems.research.agent_loop.search_web", return_value=failed):
        out = run_research_agent(
            system_prompt="sys",
            user_prompt="user",
            seed_queries=["EURUSD news"],
            require_citations=True,
            use_llm=False,
        )
    assert out["status_hint"] == "needs_review"
    assert out["citations"] == []
    assert out["findings"] == []
    assert out["search_meta"]["failed"] is True
    assert "search_failed" in out["summary"]
    assert out["auto_apply"] is False


def test_agent_loop_search_only_with_hits():
    ok = SearchResponse(
        results=[
            SearchResult("Title A", "https://a.example/x", "snippet A"),
            SearchResult("Title B", "https://b.example/y", "snippet B"),
        ],
        query="q",
        ok=True,
        attempts=1,
    )
    with patch("subsystems.research.agent_loop.search_web", return_value=ok):
        out = run_research_agent(
            system_prompt="sys",
            user_prompt="user",
            seed_queries=["XAUUSD"],
            require_citations=True,
            use_llm=False,
        )
    assert out["status_hint"] == "proposed"
    assert len(out["citations"]) == 2
    assert len(out["findings"]) >= 1
