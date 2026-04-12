"""Remote provider router state (circuit-breaker) persistence."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .ai_storage import ai2_dir

DEFAULT_ROUTER_STATE: dict[str, Any] = {
    "version": "ai-router-state-v1",
    "providers": {},
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(value: str) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(str(value))
    except Exception:
        return dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)


def _path(root: Path) -> Path:
    out = ai2_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    return out / "router_state.json"


def _provider_default() -> dict[str, Any]:
    return {
        "state": "closed",  # closed | open | half_open
        "consecutive_failures": 0,
        "open_until": "",
        "cooldown_s": 60,
        "last_error": "",
        "last_attempt_at": "",
        "last_success_at": "",
    }


def _sanitize_provider(payload: dict[str, Any]) -> dict[str, Any]:
    out = _provider_default()
    state = str(payload.get("state", out["state"])).strip().lower()
    out["state"] = state if state in {"closed", "open", "half_open"} else "closed"
    out["consecutive_failures"] = max(0, int(payload.get("consecutive_failures", 0)))
    out["open_until"] = str(payload.get("open_until", "") or "")
    out["cooldown_s"] = max(1, int(payload.get("cooldown_s", 60)))
    out["last_error"] = str(payload.get("last_error", "") or "")
    out["last_attempt_at"] = str(payload.get("last_attempt_at", "") or "")
    out["last_success_at"] = str(payload.get("last_success_at", "") or "")
    return out


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULT_ROUTER_STATE)
    providers_in = payload.get("providers", {})
    providers_out: dict[str, Any] = {}
    if isinstance(providers_in, dict):
        for provider_id, value in providers_in.items():
            if not isinstance(value, dict):
                continue
            pid = str(provider_id).strip().lower()
            if not pid:
                continue
            providers_out[pid] = _sanitize_provider(value)
    out["providers"] = providers_out
    out["version"] = str(payload.get("version", out["version"]) or "ai-router-state-v1")
    return out


def load_router_state(root: Path) -> dict[str, Any]:
    path = _path(root)
    if not path.exists():
        save_router_state(root, dict(DEFAULT_ROUTER_STATE))
        return dict(DEFAULT_ROUTER_STATE)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = dict(DEFAULT_ROUTER_STATE)
    if not isinstance(payload, dict):
        payload = dict(DEFAULT_ROUTER_STATE)
    state = _sanitize(payload)
    if state != payload:
        save_router_state(root, state)
    return state


def save_router_state(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    state = _sanitize(payload if isinstance(payload, dict) else dict(DEFAULT_ROUTER_STATE))
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    return state


def provider_state(root: Path, provider_id: str) -> dict[str, Any]:
    pid = provider_id.strip().lower()
    state = load_router_state(root)
    providers = dict(state.get("providers", {}))
    row = providers.get(pid)
    if not isinstance(row, dict):
        row = _provider_default()
        providers[pid] = row
        state["providers"] = providers
        save_router_state(root, state)
    row = _sanitize_provider(row)

    # Auto-transition from open -> half_open when cooldown expires.
    if row["state"] == "open" and row["open_until"]:
        if _parse_iso(row["open_until"]) <= _now():
            row["state"] = "half_open"
            row["open_until"] = ""
            providers[pid] = row
            state["providers"] = providers
            save_router_state(root, state)
    return row


def provider_available(root: Path, provider_id: str) -> bool:
    row = provider_state(root, provider_id)
    if row["state"] == "open" and row["open_until"]:
        return _parse_iso(row["open_until"]) <= _now()
    return True


def record_provider_result(
    root: Path,
    provider_id: str,
    ok: bool,
    failures_to_open: int = 3,
    cooldown_s: int = 60,
    max_cooldown_s: int = 600,
    error: str = "",
) -> dict[str, Any]:
    pid = provider_id.strip().lower()
    state = load_router_state(root)
    providers = dict(state.get("providers", {}))
    row = _sanitize_provider(dict(providers.get(pid, {})))

    row["last_attempt_at"] = _now_iso()

    if ok:
        row["state"] = "closed"
        row["consecutive_failures"] = 0
        row["open_until"] = ""
        row["cooldown_s"] = max(1, int(cooldown_s))
        row["last_error"] = ""
        row["last_success_at"] = row["last_attempt_at"]
    else:
        row["consecutive_failures"] = int(row["consecutive_failures"]) + 1
        row["last_error"] = str(error or "provider_error")[:400]
        threshold = max(1, int(failures_to_open))
        if row["consecutive_failures"] >= threshold:
            row["state"] = "open"
            prev_cd = max(1, int(row.get("cooldown_s", cooldown_s)))
            base_cd = max(1, int(cooldown_s))
            cd = min(max(1, int(max_cooldown_s)), max(base_cd, prev_cd))
            # If opening repeatedly, exponential backoff.
            if row.get("open_until"):
                cd = min(max(1, int(max_cooldown_s)), cd * 2)
            row["cooldown_s"] = cd
            row["open_until"] = (_now() + dt.timedelta(seconds=cd)).isoformat()
        elif row["state"] == "half_open":
            row["state"] = "open"
            cd = min(max(1, int(max_cooldown_s)), max(1, int(cooldown_s)))
            row["cooldown_s"] = cd
            row["open_until"] = (_now() + dt.timedelta(seconds=cd)).isoformat()

    providers[pid] = row
    state["providers"] = providers
    save_router_state(root, state)
    return row

