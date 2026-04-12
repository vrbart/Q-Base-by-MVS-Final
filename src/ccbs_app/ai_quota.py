"""Quota state and usage accounting for hybrid remote routing."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .ai_storage import ai2_dir

DEFAULT_QUOTA_STATE: dict[str, Any] = {
    "version": "ai-quota-v1",
    "monthly_token_budget": 2_000_000,
    "monthly_cost_budget_usd": 50.0,
    "month": "",
    "used_tokens": 0,
    "used_cost_usd": 0.0,
    "updated_at": "",
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _current_month() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


def _path(root: Path) -> Path:
    out = ai2_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    return out / "quota_state.json"


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULT_QUOTA_STATE)
    out["month"] = str(payload.get("month", out["month"]) or _current_month())
    out["updated_at"] = str(payload.get("updated_at", out["updated_at"]) or _now())

    try:
        out["monthly_token_budget"] = max(1, int(payload.get("monthly_token_budget", out["monthly_token_budget"])))
    except (TypeError, ValueError):
        out["monthly_token_budget"] = int(DEFAULT_QUOTA_STATE["monthly_token_budget"])

    try:
        out["monthly_cost_budget_usd"] = max(0.01, float(payload.get("monthly_cost_budget_usd", out["monthly_cost_budget_usd"])))
    except (TypeError, ValueError):
        out["monthly_cost_budget_usd"] = float(DEFAULT_QUOTA_STATE["monthly_cost_budget_usd"])

    try:
        out["used_tokens"] = max(0, int(payload.get("used_tokens", out["used_tokens"])))
    except (TypeError, ValueError):
        out["used_tokens"] = 0

    try:
        out["used_cost_usd"] = max(0.0, float(payload.get("used_cost_usd", out["used_cost_usd"])))
    except (TypeError, ValueError):
        out["used_cost_usd"] = 0.0

    out["version"] = str(payload.get("version", out["version"]) or "ai-quota-v1")
    return out


def load_quota_state(root: Path) -> dict[str, Any]:
    path = _path(root)
    if not path.exists():
        state = _sanitize(dict(DEFAULT_QUOTA_STATE))
        save_quota_state(root, state)
        return state

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = dict(DEFAULT_QUOTA_STATE)

    if not isinstance(payload, dict):
        payload = dict(DEFAULT_QUOTA_STATE)

    state = _sanitize(payload)
    if state["month"] != _current_month():
        state["month"] = _current_month()
        state["used_tokens"] = 0
        state["used_cost_usd"] = 0.0
        state["updated_at"] = _now()
        save_quota_state(root, state)
    elif state != payload:
        save_quota_state(root, state)
    return state


def save_quota_state(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    state = _sanitize(payload if isinstance(payload, dict) else dict(DEFAULT_QUOTA_STATE))
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    return state


def set_quota_budgets(root: Path, monthly_token_budget: int, monthly_cost_budget_usd: float) -> dict[str, Any]:
    state = load_quota_state(root)
    state["monthly_token_budget"] = max(1, int(monthly_token_budget))
    state["monthly_cost_budget_usd"] = max(0.01, float(monthly_cost_budget_usd))
    state["updated_at"] = _now()
    return save_quota_state(root, state)


def apply_usage(
    root: Path,
    used_tokens: int = 0,
    used_cost_usd: float = 0.0,
) -> dict[str, Any]:
    state = load_quota_state(root)
    state["used_tokens"] = max(0, int(state["used_tokens"]) + max(0, int(used_tokens)))
    state["used_cost_usd"] = max(0.0, float(state["used_cost_usd"]) + max(0.0, float(used_cost_usd)))
    state["updated_at"] = _now()
    return save_quota_state(root, state)


def _ratio(used: float, budget: float) -> float:
    if budget <= 0:
        return 1.0
    return min(1.0, max(0.0, used / budget))


def quota_summary(root: Path) -> dict[str, Any]:
    state = load_quota_state(root)
    token_ratio = _ratio(float(state["used_tokens"]), float(state["monthly_token_budget"]))
    cost_ratio = _ratio(float(state["used_cost_usd"]), float(state["monthly_cost_budget_usd"]))
    remaining_token_ratio = max(0.0, 1.0 - token_ratio)
    remaining_cost_ratio = max(0.0, 1.0 - cost_ratio)
    pressure_ratio = max(token_ratio, cost_ratio)
    return {
        **state,
        "token_usage_ratio": round(token_ratio, 4),
        "cost_usage_ratio": round(cost_ratio, 4),
        "remaining_token_ratio": round(remaining_token_ratio, 4),
        "remaining_cost_ratio": round(remaining_cost_ratio, 4),
        "pressure_ratio": round(pressure_ratio, 4),
        "under_20_percent_remaining": bool(remaining_token_ratio < 0.2 or remaining_cost_ratio < 0.2),
    }


def estimate_tokens(prompt: str, completion: str = "") -> int:
    # Heuristic approximation: roughly 0.75 token per word plus punctuation overhead.
    words = max(0, len(prompt.split())) + max(0, len(completion.split()))
    chars = len(prompt) + len(completion)
    token_est = int(words * 0.75 + chars / 22.0)
    return max(1, token_est)

