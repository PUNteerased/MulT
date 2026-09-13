"""
Versioned model registry — champion pointer + challenger artifacts.
Never silently overwrite the live champion without promote().
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from config.settings import MODELS_DIR

REGISTRY_ROOT = MODELS_DIR / "registry"
ACTIVE_DIR = MODELS_DIR / "active"
POINTER_PATH = MODELS_DIR / "champion_pointer.json"


def _ensure_dirs() -> None:
    REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    (REGISTRY_ROOT / "lgbm").mkdir(parents=True, exist_ok=True)


def _new_version_id() -> str:
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    return f"{ts}_{uuid.uuid4().hex[:6]}"


def _pointer() -> Dict[str, Any]:
    _ensure_dirs()
    if POINTER_PATH.exists():
        try:
            return json.loads(POINTER_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"lgbm": None, "cnn_lstm": None, "challenger_lgbm": None}


def _save_pointer(data: Dict[str, Any]) -> None:
    _ensure_dirs()
    POINTER_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def champion_lgbm_path() -> Path:
    """Resolved path of the live LightGBM champion file."""
    _ensure_dirs()
    ptr = _pointer()
    vid = ptr.get("lgbm")
    if vid:
        p = REGISTRY_ROOT / "lgbm" / vid / "model.txt"
        if p.exists():
            return p
    legacy = MODELS_DIR / "lgbm_meta_filter.txt"
    active = ACTIVE_DIR / "lgbm_meta_filter.txt"
    if active.exists():
        return active
    return legacy


def challenger_lgbm_path() -> Optional[Path]:
    ptr = _pointer()
    vid = ptr.get("challenger_lgbm")
    if not vid:
        return None
    p = REGISTRY_ROOT / "lgbm" / vid / "model.txt"
    return p if p.exists() else None


def challenger_meta() -> Optional[Dict[str, Any]]:
    ptr = _pointer()
    vid = ptr.get("challenger_lgbm")
    if not vid:
        return None
    meta_path = REGISTRY_ROOT / "lgbm" / vid / "meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def register_lgbm(
    model_src: Path,
    *,
    role: str = "challenger",
    metrics: Optional[Dict[str, Any]] = None,
    feature_names: Optional[List[str]] = None,
    feature_hash: Optional[str] = None,
    feature_snapshot: Optional[Dict[str, Any]] = None,
    parent: Optional[str] = None,
) -> str:
    """
    Copy model into registry. role=challenger sets pointer; role=champion also activates.
    Returns version_id.
    """
    _ensure_dirs()
    if not model_src.exists():
        raise FileNotFoundError(str(model_src))
    vid = _new_version_id()
    dest_dir = REGISTRY_ROOT / "lgbm" / vid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_model = dest_dir / "model.txt"
    shutil.copy2(model_src, dest_model)
    meta = {
        "version_id": vid,
        "role": role,
        "train_ts": time.time(),
        "feature_names": feature_names or [],
        "feature_hash": feature_hash,
        "metrics": metrics or {},
        "parent": parent or _pointer().get("lgbm"),
        "feature_snapshot": feature_snapshot or {},
    }
    (dest_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    ptr = _pointer()
    if role == "challenger":
        ptr["challenger_lgbm"] = vid
    elif role == "champion":
        ptr["lgbm"] = vid
        ptr["challenger_lgbm"] = None
        _activate_lgbm(dest_model)
    _save_pointer(ptr)
    logger.info(f"[ModelRegistry] registered lgbm {vid} role={role}")
    return vid


def promote_challenger_lgbm() -> Optional[str]:
    """Promote current challenger to champion. Returns version_id or None."""
    ptr = _pointer()
    vid = ptr.get("challenger_lgbm")
    if not vid:
        logger.warning("[ModelRegistry] no challenger to promote")
        return None
    model = REGISTRY_ROOT / "lgbm" / vid / "model.txt"
    if not model.exists():
        return None
    ptr["lgbm"] = vid
    ptr["challenger_lgbm"] = None
    _save_pointer(ptr)
    _activate_lgbm(model)
    meta_path = REGISTRY_ROOT / "lgbm" / vid / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["role"] = "champion"
            meta["promoted_at"] = time.time()
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception:
            pass
    logger.info(f"[ModelRegistry] promoted challenger {vid} -> champion")
    return vid


def _activate_lgbm(model_path: Path) -> None:
    _ensure_dirs()
    active = ACTIVE_DIR / "lgbm_meta_filter.txt"
    shutil.copy2(model_path, active)
    legacy = MODELS_DIR / "lgbm_meta_filter.txt"
    shutil.copy2(model_path, legacy)


def list_lgbm_versions(limit: int = 20) -> List[Dict[str, Any]]:
    _ensure_dirs()
    rows = []
    root = REGISTRY_ROOT / "lgbm"
    if not root.exists():
        return rows
    dirs = sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    ptr = _pointer()
    for d in dirs[:limit]:
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        meta: Dict[str, Any] = {"version_id": d.name}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        meta["is_champion"] = ptr.get("lgbm") == d.name
        meta["is_challenger"] = ptr.get("challenger_lgbm") == d.name
        rows.append(meta)
    return rows


def bootstrap_from_legacy_if_needed(feature_names: Optional[List[str]] = None) -> None:
    """If no champion pointer, register existing lgbm_meta_filter.txt as champion."""
    ptr = _pointer()
    if ptr.get("lgbm"):
        return
    legacy = MODELS_DIR / "lgbm_meta_filter.txt"
    if legacy.exists():
        register_lgbm(legacy, role="champion", feature_names=feature_names or [], metrics={"source": "legacy_bootstrap"})
