"""
Research chatbot session persistence under data/research_chat/.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from config.settings import DATA_DIR

CHAT_DIR = DATA_DIR / "research_chat"


def _ensure_dir() -> Path:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    return CHAT_DIR


def _path(session_id: str) -> Path:
    safe = "".join(c for c in session_id if c.isalnum() or c in ("_", "-"))[:64]
    return _ensure_dir() / f"{safe}.json"


def new_session_id() -> str:
    return f"CHS_{uuid.uuid4().hex[:12].upper()}"


def new_action_id() -> str:
    return f"ACT_{uuid.uuid4().hex[:10].upper()}"


def empty_session(session_id: Optional[str] = None) -> Dict[str, Any]:
    sid = session_id or new_session_id()
    return {
        "session_id": sid,
        "created_at": time.time(),
        "updated_at": time.time(),
        "messages": [],
        "pending_actions": [],
        "tool_trace": [],
    }


def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    path = _path(session_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[ChatStore] load failed {session_id}: {e}")
        return None


def save_session(session: Dict[str, Any]) -> Path:
    sid = session.get("session_id") or new_session_id()
    session["session_id"] = sid
    session["updated_at"] = time.time()
    path = _path(sid)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, indent=2, ensure_ascii=False)
    return path


def get_or_create(session_id: Optional[str] = None) -> Dict[str, Any]:
    if session_id:
        existing = load_session(session_id)
        if existing:
            return existing
    return empty_session(session_id)


def append_message(session: Dict[str, Any], role: str, content: str, **extra: Any) -> None:
    msg: Dict[str, Any] = {
        "role": role,
        "content": content,
        "ts": time.time(),
    }
    msg.update(extra)
    session.setdefault("messages", []).append(msg)


def append_tool_trace(session: Dict[str, Any], entry: Dict[str, Any]) -> str:
    tid = entry.get("id") or f"TR_{uuid.uuid4().hex[:8].upper()}"
    row = {"id": tid, "ts": time.time(), **entry}
    session.setdefault("tool_trace", []).append(row)
    # Cap trace length
    if len(session["tool_trace"]) > 200:
        session["tool_trace"] = session["tool_trace"][-200:]
    return tid


def add_pending_action(
    session: Dict[str, Any],
    *,
    action_type: str,
    payload: Dict[str, Any],
    preview: str,
    web_sourced: bool = False,
    tool_trace_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    action = {
        "id": new_action_id(),
        "type": action_type,
        "payload": payload,
        "preview": preview,
        "created_at": time.time(),
        "status": "pending",
        "web_sourced": bool(web_sourced),
        "tool_trace_ids": tool_trace_ids or [],
    }
    session.setdefault("pending_actions", []).append(action)
    return action


def get_action(session: Dict[str, Any], action_id: str) -> Optional[Dict[str, Any]]:
    for a in session.get("pending_actions") or []:
        if a.get("id") == action_id:
            return a
    return None


def public_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Strip oversized tool results for API responses."""
    return {
        "session_id": session.get("session_id"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "messages": session.get("messages") or [],
        "pending_actions": [
            a for a in (session.get("pending_actions") or []) if a.get("status") == "pending"
        ],
        "all_actions": session.get("pending_actions") or [],
    }
