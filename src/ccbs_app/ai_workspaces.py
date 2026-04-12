"""Workspace registry and active workspace tracking."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .ai_storage import ai2_dir


def _dir(root: Path) -> Path:
    out = ai2_dir(root) / "workspaces"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _path_registry(root: Path) -> Path:
    return _dir(root) / "workspace_registry.json"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _load(root: Path) -> dict[str, Any]:
    path = _path_registry(root)
    if not path.exists():
        payload = {
            "version": "workspace-registry-v1",
            "current": "default",
            "workspaces": [
                {
                    "workspace_id": "default",
                    "name": "Default Workspace",
                    "description": "Primary local offline workspace",
                    "created_at": _now(),
                }
            ],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {"version": "workspace-registry-v1", "current": "default", "workspaces": []}
    if "workspaces" not in payload or not isinstance(payload["workspaces"], list):
        payload["workspaces"] = []
    if "current" not in payload:
        payload["current"] = "default"
    return payload


def _save(root: Path, payload: dict[str, Any]) -> None:
    path = _path_registry(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def list_workspaces(root: Path) -> dict[str, Any]:
    payload = _load(root)
    return {
        "current": str(payload.get("current", "default")),
        "workspaces": list(payload.get("workspaces", [])),
    }


def create_workspace(root: Path, workspace_id: str, name: str = "", description: str = "") -> dict[str, Any]:
    wid = workspace_id.strip().lower()
    if not wid:
        raise ValueError("workspace_id is required")
    payload = _load(root)
    workspaces = list(payload.get("workspaces", []))
    for item in workspaces:
        if str(item.get("workspace_id", "")) == wid:
            raise ValueError(f"workspace exists: {wid}")

    rec = {
        "workspace_id": wid,
        "name": name.strip() or wid,
        "description": description.strip(),
        "created_at": _now(),
    }
    workspaces.append(rec)
    payload["workspaces"] = sorted(workspaces, key=lambda x: str(x.get("workspace_id", "")))
    _save(root, payload)
    return rec


def switch_workspace(root: Path, workspace_id: str) -> dict[str, Any]:
    wid = workspace_id.strip().lower()
    payload = _load(root)
    exists = any(str(item.get("workspace_id", "")) == wid for item in payload.get("workspaces", []))
    if not exists:
        raise ValueError(f"workspace not found: {wid}")
    payload["current"] = wid
    _save(root, payload)
    return {"current": wid}
