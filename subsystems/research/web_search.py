"""
DuckDuckGo web search for Research Agent (zero-cost, no API key).

Fail-soft: after retries, return empty results + error meta — never recycle stale news.
Logs search.query and search.failure separately.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

_FAILURE_COUNT = 0
_QUERY_COUNT = 0


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str

    def as_dict(self) -> Dict[str, str]:
        return {"title": self.title, "url": self.url, "snippet": self.snippet}


@dataclass
class SearchResponse:
    results: List[SearchResult] = field(default_factory=list)
    query: str = ""
    ok: bool = True
    error: Optional[str] = None
    attempts: int = 0

    def as_dicts(self) -> List[Dict[str, str]]:
        return [r.as_dict() for r in self.results]

    @property
    def search_failed(self) -> bool:
        return not self.ok or (self.ok and len(self.results) == 0 and self.error is not None)


def search_stats() -> Dict[str, int]:
    return {"queries": _QUERY_COUNT, "failures": _FAILURE_COUNT}


def search_web(
    query: str,
    max_results: int = 5,
    max_retries: int = 3,
    base_backoff_s: float = 0.8,
) -> SearchResponse:
    """
    Search via duckduckgo_search.DDGS with exponential backoff.

    On total failure: ok=False, results=[], error set — callers must emit
    needs_review / search_failed reports (do not reuse prior headlines).
    """
    global _QUERY_COUNT, _FAILURE_COUNT
    q = (query or "").strip()
    if not q:
        return SearchResponse(query=q, ok=False, error="empty_query", attempts=0)

    _QUERY_COUNT += 1
    logger.info(f"[search.query] q={q!r} max_results={max_results}")

    last_err: Optional[str] = None
    for attempt in range(1, max_retries + 1):
        try:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                from ddgs import DDGS  # type: ignore

            rows: List[SearchResult] = []
            ddgs = DDGS()
            try:
                iterator = ddgs.text(q, max_results=max_results)
            except TypeError:
                # older signatures
                iterator = ddgs.text(q)

            for item in iterator or []:
                rows.append(
                    SearchResult(
                        title=str(item.get("title") or ""),
                        url=str(item.get("href") or item.get("link") or ""),
                        snippet=str(item.get("body") or item.get("snippet") or ""),
                    )
                )
                if len(rows) >= max_results:
                    break

            # Close if context-manager style
            close = getattr(ddgs, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

            logger.info(f"[search.query] ok attempt={attempt} hits={len(rows)} q={q!r}")
            return SearchResponse(results=rows, query=q, ok=True, error=None, attempts=attempt)
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            _FAILURE_COUNT += 1
            logger.warning(
                f"[search.failure] attempt={attempt}/{max_retries} q={q!r} err={last_err} "
                f"totals={search_stats()}"
            )
            if attempt < max_retries:
                time.sleep(base_backoff_s * (2 ** (attempt - 1)))

    return SearchResponse(
        results=[],
        query=q,
        ok=False,
        error=last_err or "unknown_search_error",
        attempts=max_retries,
    )


def format_results_for_prompt(results: List[Dict[str, Any]], limit: int = 8) -> str:
    if not results:
        return "(no search results)"
    lines = []
    for i, r in enumerate(results[:limit], 1):
        lines.append(
            f"{i}. {r.get('title', '')}\n"
            f"   URL: {r.get('url', '')}\n"
            f"   {r.get('snippet', '')}"
        )
    return "\n".join(lines)
