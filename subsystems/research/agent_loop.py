"""
Shared Research Agent loop: LM Studio + optional web_search tool.

Quality gate is parameterized:
  - News/Strategy: require_citations=True (0 citations or empty findings → needs_review)
  - Auditor: require_citations=False (status driven by rule checks, not citations)
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from subsystems.research.llm_client import LocalLLMClient
from subsystems.research.web_search import (
    format_results_for_prompt,
    search_web,
)

WEB_SEARCH_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the public web for recent news, research, or definitions.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max hits (1-8)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


def check_quality(
    *,
    citations: List[Dict[str, Any]],
    findings: List[Any],
    require_citations: bool = True,
    search_failed: bool = False,
    summary: str = "",
    narrative: str = "",
) -> str:
    """
    Return status_hint: 'proposed' | 'needs_review'.

    Auditor should call with require_citations=False so rules-only runs
    are not forced into needs_review solely for missing URLs.
    """
    if search_failed:
        return "needs_review"
    if require_citations and len(citations) == 0:
        return "needs_review"
    if require_citations and not findings:
        return "needs_review"
    if not require_citations and not findings:
        return "needs_review"

    blob = f"{summary or ''}\n{narrative or ''}".lower()
    irrelevance_markers = (
        "no direct relevance",
        "not directly relevant",
        "not related",
        "unrelated to",
        "unable to find",
        "no relevant",
        "nothing relevant",
        "no trading relevance",
        "not about trading",
        "focus on meta platforms",  # common off-topic DDG hit
        "social media ecosystem",
    )
    if any(m in blob for m in irrelevance_markers):
        return "needs_review"

    return "proposed"


def _parse_json_blob(text: Optional[str]) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}
    return {}


def _citations_from_search(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out = []
    for r in rows:
        if not r.get("url"):
            continue
        out.append(
            {
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "snippet": (r.get("snippet") or "")[:280],
            }
        )
    return out


def run_research_agent(
    *,
    system_prompt: str,
    user_prompt: str,
    seed_queries: Optional[List[str]] = None,
    require_citations: bool = True,
    use_llm: bool = True,
    max_search_per_query: int = 5,
    client: Optional[LocalLLMClient] = None,
) -> Dict[str, Any]:
    """
    Execute search (+ optional LLM synthesis).

    Always attempts seed_queries first so we have citations even when the
    model cannot native-tool-call. Never recycles prior report content.
    """
    seed_queries = seed_queries or []
    tool_trace: List[Dict[str, Any]] = []
    all_hits: List[Dict[str, str]] = []
    search_errors: List[str] = []
    search_failed = False

    for q in seed_queries:
        resp = search_web(q, max_results=max_search_per_query)
        tool_trace.append(
            {
                "tool": "web_search",
                "args": {"query": q},
                "ok": resp.ok,
                "hits": len(resp.results),
                "error": resp.error,
                "attempts": resp.attempts,
            }
        )
        if not resp.ok:
            search_errors.append(resp.error or "search_failed")
            search_failed = True
        else:
            all_hits.extend(resp.as_dicts())

    # Dedupe by URL
    seen = set()
    unique_hits: List[Dict[str, str]] = []
    for h in all_hits:
        u = h.get("url") or ""
        if u and u not in seen:
            seen.add(u)
            unique_hits.append(h)

    citations = _citations_from_search(unique_hits)
    llm_meta: Dict[str, Any] = {"provider": "lm_studio", "used": False}
    narrative = ""
    findings: List[Any] = []

    # Hard fail path: no usable search for citation-required modules
    if require_citations and (search_failed and not unique_hits):
        status = check_quality(
            citations=[],
            findings=[],
            require_citations=True,
            search_failed=True,
        )
        return {
            "narrative": "Web search failed; no digest generated (refusing to reuse stale data).",
            "summary": "search_failed — needs human review",
            "findings": [],
            "citations": [],
            "candidate_ideas": [],
            "tool_trace": tool_trace,
            "search_meta": {
                "failed": True,
                "errors": search_errors,
                "hit_count": 0,
            },
            "status_hint": status,
            "llm_meta": llm_meta,
            "auto_apply": False,
        }

    summary = ""
    ideas: List[str] = []

    llm = client or LocalLLMClient.from_runtime()
    if use_llm and getattr(llm, "enabled", True) and llm.is_reachable():
        llm_meta["used"] = True
        llm_meta["model"] = llm.model
        llm_meta["base_url"] = llm.base_url

        def _tool_web_search(args: Dict[str, Any]) -> str:
            q = str(args.get("query") or "").strip()
            n = int(args.get("max_results") or 5)
            n = max(1, min(n, 8))
            resp = search_web(q, max_results=n)
            tool_trace.append(
                {
                    "tool": "web_search",
                    "args": {"query": q, "max_results": n},
                    "ok": resp.ok,
                    "hits": len(resp.results),
                    "error": resp.error,
                }
            )
            if not resp.ok:
                search_errors.append(resp.error or "search_failed")
                return json.dumps({"ok": False, "error": resp.error, "results": []})
            rows = resp.as_dicts()
            for r in rows:
                u = r.get("url") or ""
                if u and u not in seen:
                    seen.add(u)
                    unique_hits.append(r)
            return json.dumps({"ok": True, "results": rows})

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"{user_prompt}\n\n"
                    f"## Search results (pre-fetched)\n"
                    f"{format_results_for_prompt(unique_hits)}\n\n"
                    "Respond with a single JSON object containing keys: "
                    "summary (string), narrative (string), findings (array of strings), "
                    "candidate_ideas (array of strings, may be empty). "
                    "Cite only facts supported by the search results. Do not invent URLs."
                ),
            },
        ]

        content, native_trace, used_native = llm.chat_with_tools(
            messages,
            tools=[WEB_SEARCH_TOOL],
            tool_handlers={"web_search": _tool_web_search},
        )
        tool_trace.extend(native_trace)
        llm_meta["native_tools"] = used_native

        if content is None and not used_native:
            # Fallback: plain chat with injected search context
            content = llm.chat(messages, temperature=0.2, max_tokens=1200)

        parsed = _parse_json_blob(content)
        narrative = str(parsed.get("narrative") or content or "").strip()
        summary = str(parsed.get("summary") or narrative[:240])
        raw_findings = parsed.get("findings") or []
        if isinstance(raw_findings, list):
            findings = [str(x) for x in raw_findings if str(x).strip()]
        raw_ideas = parsed.get("candidate_ideas") or []
        if not isinstance(raw_ideas, list):
            raw_ideas = []
        ideas = [str(x) for x in raw_ideas if str(x).strip()]
    else:
        # No LLM: structured stub from search snippets only
        llm_meta["used"] = False
        summary = (
            f"Search-only digest ({len(unique_hits)} hits)."
            if unique_hits
            else "No LLM and no search hits."
        )
        narrative = summary
        findings = [
            f"{h.get('title')}: {(h.get('snippet') or '')[:160]}"
            for h in unique_hits[:8]
        ]
        ideas = []

    citations = _citations_from_search(unique_hits)
    if search_errors and not citations:
        search_failed = True

    status = check_quality(
        citations=citations,
        findings=findings,
        require_citations=require_citations,
        search_failed=search_failed and require_citations,
        summary=summary,
        narrative=narrative,
    )

    logger.info(
        f"[agent_loop] status_hint={status} citations={len(citations)} "
        f"findings={len(findings)} require_citations={require_citations}"
    )

    return {
        "narrative": narrative,
        "summary": summary,
        "findings": findings,
        "citations": citations,
        "candidate_ideas": ideas,
        "tool_trace": tool_trace,
        "search_meta": {
            "failed": bool(search_errors and not citations),
            "errors": search_errors,
            "hit_count": len(citations),
        },
        "status_hint": status,
        "llm_meta": llm_meta,
        "auto_apply": False,
    }
