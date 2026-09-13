"""
Apply confirmed Research Chat pending actions (v1: runtime patch + research status).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from loguru import logger

from subsystems.research import chat_store
from subsystems.research.log_apply import log_chat_action


def confirm_action(
    session_id: str,
    action_id: str,
    *,
    actor: str = "dashboard_user",
) -> Dict[str, Any]:
    session = chat_store.load_session(session_id)
    if not session:
        return {"ok": False, "reason": "session_not_found"}
    action = chat_store.get_action(session, action_id)
    if not action:
        return {"ok": False, "reason": "action_not_found"}
    if action.get("status") != "pending":
        return {"ok": False, "reason": f"action_not_pending:{action.get('status')}"}

    atype = action.get("type")
    payload = action.get("payload") or {}
    result: Dict[str, Any] = {"ok": False}

    try:
        if atype == "runtime_patch":
            from subsystems.config.system_runtime import save_settings

            section = payload.get("section")
            patch = payload.get("patch") or {}
            if not section or not isinstance(patch, dict):
                raise ValueError("invalid_runtime_patch_payload")
            rt = save_settings(patch, section=section)
            result = {
                "ok": True,
                "applied": "runtime_patch",
                "section": section,
                "updated_at": rt.updated_at,
            }
        elif atype == "research_status":
            from subsystems.research.store import update_status

            report = update_status(
                payload.get("report_id"),
                payload.get("status"),
                note=payload.get("note") or f"chat_confirm:{actor}",
            )
            if not report:
                raise FileNotFoundError("report_not_found")
            result = {
                "ok": True,
                "applied": "research_status",
                "report_id": report.get("report_id"),
                "status": report.get("status"),
                "promotion_result": report.get("promotion_result"),
            }
        else:
            raise ValueError(f"unsupported_action_type:{atype}")
    except Exception as e:
        logger.error(f"[ChatApply] confirm failed: {e}")
        result = {"ok": False, "reason": str(e)}
        action["status"] = "pending"  # keep pending on failure so user can retry/reject
        action["last_error"] = str(e)
        chat_store.save_session(session)
        log_chat_action(
            actor=actor,
            action_id=action_id,
            action_type=str(atype),
            decision="confirm_failed",
            web_sourced=bool(action.get("web_sourced")),
            detail=result,
            tool_trace_ids=action.get("tool_trace_ids") or [],
        )
        return result

    action["status"] = "confirmed"
    action["confirmed_at"] = time.time()
    action["confirmed_by"] = actor
    action["apply_result"] = result
    chat_store.append_message(
        session,
        "system",
        f"Action {action_id} confirmed by {actor}: {action.get('preview', '')[:200]}",
        action_id=action_id,
    )
    chat_store.save_session(session)
    log_chat_action(
        actor=actor,
        action_id=action_id,
        action_type=str(atype),
        decision="confirmed",
        web_sourced=bool(action.get("web_sourced")),
        detail=result,
        tool_trace_ids=action.get("tool_trace_ids") or [],
    )
    return {"ok": True, "action": action, "result": result, "session": chat_store.public_session(session)}


def reject_action(
    session_id: str,
    action_id: str,
    *,
    actor: str = "dashboard_user",
) -> Dict[str, Any]:
    session = chat_store.load_session(session_id)
    if not session:
        return {"ok": False, "reason": "session_not_found"}
    action = chat_store.get_action(session, action_id)
    if not action:
        return {"ok": False, "reason": "action_not_found"}
    if action.get("status") != "pending":
        return {"ok": False, "reason": f"action_not_pending:{action.get('status')}"}

    action["status"] = "rejected"
    action["rejected_at"] = time.time()
    action["rejected_by"] = actor
    chat_store.append_message(
        session,
        "system",
        f"Action {action_id} rejected by {actor}",
        action_id=action_id,
    )
    chat_store.save_session(session)
    log_chat_action(
        actor=actor,
        action_id=action_id,
        action_type=str(action.get("type")),
        decision="rejected",
        web_sourced=bool(action.get("web_sourced")),
        detail={"preview": action.get("preview")},
        tool_trace_ids=action.get("tool_trace_ids") or [],
    )
    return {"ok": True, "action": action, "session": chat_store.public_session(session)}
