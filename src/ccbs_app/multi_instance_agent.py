"""CCBS multi-instance control and optimization helpers.

This module provides a single in-process surface for:
- Discovering apps that can run multi-instance lanes.
- Computing lane readiness and availability counters.
- Syncing configured workspace ids.
- Running guarded control actions for launch/sync/status.
- Producing an optimized app bundle using the quantum-ready selector.
- Routing asks to priority lanes via directives (`-1`, `-2`, `-3`, ...).
- Tracking runtime lane tasks and token telemetry (daily/weekly/paid snapshots).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ai_quota import (
    apply_usage as apply_quota_usage,
    estimate_tokens,
    quota_summary,
)
from .ai_storage import ai2_dir
from .ai_workspaces import create_workspace, list_workspaces
from .planner.quantum_select import (
    QuantumSelector,
    SchedulerWeights,
    TaskFeatures,
    make_decision_packet,
)


@dataclass(frozen=True)
class AppDefinition:
    app_id: str
    name: str
    commands: tuple[str, ...]
    process_names: tuple[str, ...]
    supports_multi_instance: bool
    supports_workspace_isolation: bool
    supports_automation: bool
    ccbs_fit: float
    category: str
    notes: str


APP_CATALOG: tuple[AppDefinition, ...] = (
    AppDefinition(
        app_id="codex_cli",
        name="OpenAI Codex CLI",
        commands=("codex",),
        process_names=("codex", "node"),
        supports_multi_instance=True,
        supports_workspace_isolation=True,
        supports_automation=True,
        ccbs_fit=0.98,
        category="agent",
        notes="Primary CCBS coding lane; supports multiple shell-launched sessions.",
    ),
    AppDefinition(
        app_id="vscode",
        name="Visual Studio Code",
        commands=("code",),
        process_names=("Code.exe", "code"),
        supports_multi_instance=True,
        supports_workspace_isolation=True,
        supports_automation=True,
        ccbs_fit=0.92,
        category="ui",
        notes="Supports many independent windows/workspaces for split operator lanes.",
    ),
    AppDefinition(
        app_id="powershell",
        name="PowerShell",
        commands=("powershell.exe", "pwsh"),
        process_names=("powershell.exe", "pwsh"),
        supports_multi_instance=True,
        supports_workspace_isolation=False,
        supports_automation=True,
        ccbs_fit=0.88,
        category="runtime",
        notes="Reliable local control plane for lane orchestration scripts.",
    ),
    AppDefinition(
        app_id="windows_terminal",
        name="Windows Terminal",
        commands=("wt.exe", "wt"),
        process_names=("WindowsTerminal.exe", "wt"),
        supports_multi_instance=True,
        supports_workspace_isolation=False,
        supports_automation=True,
        ccbs_fit=0.84,
        category="runtime",
        notes="Good shell multiplexer for operators running multiple CCBS lanes.",
    ),
    AppDefinition(
        app_id="python",
        name="Python Runtime",
        commands=("python", "python3"),
        process_names=("python.exe", "python", "python3"),
        supports_multi_instance=True,
        supports_workspace_isolation=True,
        supports_automation=True,
        ccbs_fit=0.79,
        category="runtime",
        notes="Useful for scriptable worker lanes and task executors.",
    ),
    AppDefinition(
        app_id="node",
        name="Node.js Runtime",
        commands=("node",),
        process_names=("node.exe", "node"),
        supports_multi_instance=True,
        supports_workspace_isolation=True,
        supports_automation=True,
        ccbs_fit=0.74,
        category="runtime",
        notes="Optional app execution lane for JS/TS-based workers.",
    ),
    AppDefinition(
        app_id="ollama",
        name="Ollama",
        commands=("ollama",),
        process_names=("ollama",),
        supports_multi_instance=False,
        supports_workspace_isolation=False,
        supports_automation=True,
        ccbs_fit=0.65,
        category="model",
        notes="Prefer single shared daemon with serialized requests on 32 GB systems.",
    ),
)

_DIRECTIVE_RE = re.compile(r"^\s*(-\d+)\b\s*(.*)$", re.DOTALL)
_DIRECTIVE_ALIAS_RE = re.compile(r"^\s*#?\s*[Rr](\d+)\b\s*(.*)$", re.DOTALL)
_DIRECTIVE_LANE_RE = re.compile(r"^\s*lane\s+(\d+)\b\s*(.*)$", re.IGNORECASE | re.DOTALL)
ORCHESTRATOR_NAME = "Q-Base by CCBS"
ORCHESTRATOR_SHORTHAND = "QB"


def _orchestrator_identity() -> dict[str, str]:
    return {"name": ORCHESTRATOR_NAME, "shorthand": ORCHESTRATOR_SHORTHAND}


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _today_key() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _week_key() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _month_key() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")


def _runtime_path(root: Path) -> Path:
    out = ai2_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    return out / "multi_instance_runtime.json"


def _profile_path(root: Path) -> Path:
    out = root / "config"
    out.mkdir(parents=True, exist_ok=True)
    return out / "multi_instance_profile.json"


def _which_any(commands: tuple[str, ...]) -> tuple[bool, str]:
    for cmd in commands:
        path = shutil.which(cmd)
        if path:
            return True, path
    return False, ""


def _is_windows_path(raw: str) -> bool:
    text = str(raw or "")
    return len(text) >= 3 and text[1:3] in {":\\", ":/"}


def _resolve_instance_path(raw: str) -> Path:
    text = str(raw or "").strip()
    if not text:
        return Path(".")
    candidate = Path(text)
    if candidate.exists():
        return candidate
    if os.name != "nt" and _is_windows_path(text):
        drive = text[0].lower()
        suffix = text[2:].replace("\\", "/")
        return Path(f"/mnt/{drive}{suffix}")
    return candidate


def _count_running_processes(names: tuple[str, ...]) -> int:
    aliases = {str(name).strip().lower() for name in names if str(name).strip()}
    if not aliases:
        return 0
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            rows = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
            count = 0
            for row in rows:
                if not row.startswith('"'):
                    continue
                image = row.split('","', 1)[0].strip('"').strip().lower()
                if image in aliases:
                    count += 1
            return count
        proc = subprocess.run(
            ["ps", "-A", "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        rows = [line.strip().lower() for line in (proc.stdout or "").splitlines() if line.strip()]
        count = 0
        for row in rows:
            base = Path(row).name.lower()
            if row in aliases or base in aliases:
                count += 1
        return count
    except Exception:
        return 0


def discover_multi_instance_apps(root: Path) -> dict[str, Any]:
    del root
    rows: list[dict[str, Any]] = []
    for spec in APP_CATALOG:
        installed, detected_command = _which_any(spec.commands)
        running = _count_running_processes(spec.process_names)
        availability = bool(installed and spec.supports_multi_instance)
        score = round(
            spec.ccbs_fit
            + (0.08 if installed else 0.0)
            + (0.04 if running > 0 else 0.0)
            + (0.03 if spec.supports_workspace_isolation else 0.0)
            + (0.02 if spec.supports_automation else 0.0),
            4,
        )
        rows.append(
            {
                "app_id": spec.app_id,
                "name": spec.name,
                "category": spec.category,
                "commands": list(spec.commands),
                "detected_command": detected_command,
                "installed": installed,
                "running_processes": running,
                "supports_multi_instance": spec.supports_multi_instance,
                "supports_workspace_isolation": spec.supports_workspace_isolation,
                "supports_automation": spec.supports_automation,
                "ccbs_fit": spec.ccbs_fit,
                "ccbs_score": score,
                "available_for_multi_lane": availability,
                "notes": spec.notes,
            }
        )
    rows.sort(
        key=lambda item: (
            not bool(item.get("available_for_multi_lane", False)),
            -float(item.get("ccbs_score", 0.0)),
            str(item.get("name", "")),
        )
    )
    total = len(rows)
    supported = sum(1 for row in rows if bool(row.get("supports_multi_instance", False)))
    installed_supported = sum(
        1
        for row in rows
        if bool(row.get("supports_multi_instance", False)) and bool(row.get("installed", False))
    )
    return {
        "catalog_version": "ccbs-multi-instance-app-catalog-v2",
        "orchestrator": _orchestrator_identity(),
        "summary": {
            "total_apps": total,
            "supports_multi_instance": supported,
            "installed_supporting_apps": installed_supported,
        },
        "apps": rows,
    }


def _load_lane_config(root: Path) -> list[dict[str, Any]]:
    raw_path = os.environ.get("CCBS_CODEX_INSTANCES_CONFIG", "").strip()
    if raw_path:
        candidate = Path(raw_path)
        path = candidate if candidate.is_absolute() else (root / candidate)
    else:
        path = root / "config" / "codex_instances.json"

    if not path.exists():
        return []

    def expand_path_template(raw: str) -> str:
        text = str(raw or "").strip()
        if not text:
            return text
        # Keep public repos portable: allow placeholders instead of hardcoding per-user paths.
        text = (
            text.replace("{REPO_ROOT}", str(root))
            .replace("${REPO_ROOT}", str(root))
            .replace("__REPO_ROOT__", str(root))
        )
        userprofile = os.environ.get("USERPROFILE", "").strip()
        if userprofile:
            text = text.replace("{USERPROFILE}", userprofile).replace("${USERPROFILE}", userprofile)
        home = os.environ.get("HOME", "").strip()
        if home:
            text = text.replace("{HOME}", home).replace("${HOME}", home)
        # Expand %VAR% / $VAR style env vars if present.
        try:
            text = os.path.expandvars(text)
        except Exception:
            pass
        # Resolve relative paths relative to repo root.
        try:
            if not Path(text).is_absolute() and not _is_windows_path(text):
                text = str(root / text)
        except Exception:
            pass
        return text

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("instances", [])
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            cloned = dict(row)
            if "path" in cloned:
                cloned["path"] = str(_resolve_instance_path(expand_path_template(str(cloned.get("path", "")))))
            out.append(cloned)
    return out


def _default_lane_weights(count: int) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [1.0]
    if count == 2:
        return [0.62, 0.38]
    if count == 3:
        return [0.5, 0.3, 0.2]
    head = [0.46, 0.27, 0.17]
    remaining = max(0.0, 1.0 - sum(head))
    tail_count = count - 3
    tail_each = remaining / tail_count if tail_count > 0 else 0.0
    return head + [tail_each] * tail_count


def _normalize_weights(raw_weights: list[float]) -> list[float]:
    safe = [max(0.0, float(x)) for x in raw_weights]
    total = sum(safe)
    if total <= 1e-9:
        return [1.0 / len(safe)] * len(safe) if safe else []
    return [x / total for x in safe]


def _default_profile(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    weights = _normalize_weights(_default_lane_weights(len(lanes)))
    lane_rows: list[dict[str, Any]] = []
    for idx, lane in enumerate(lanes):
        instance_id = str(lane.get("instance_id", f"lane-{idx+1}")).strip() or f"lane-{idx+1}"
        lane_rows.append(
            {
                "instance_id": instance_id,
                "name": str(lane.get("name", instance_id)).strip() or instance_id,
                "priority": idx + 1,
                "directive": f"-{idx + 1}",
                "role": "primary" if idx == 0 else ("secondary" if idx == 1 else ("tertiary" if idx == 2 else "auxiliary")),
            }
        )
    return {
        "version": "ccbs-multi-instance-profile-v1",
        "updated_at": _utc_now(),
        "routing": {
            "prefix_directive_enabled": True,
            "fallback_strategy": "priority_available",
        },
        "token_policy": {
            "daily_budget_tokens": 120000,
            "weekly_budget_tokens": 600000,
            "paid_budget_tokens": 0,
            "budget_source": "ccbs_quota_if_paid_zero",
        },
        "lane_weights": {row["instance_id"]: round(weights[idx], 6) for idx, row in enumerate(lane_rows)},
        "lanes": lane_rows,
        "app_preferences": [spec.app_id for spec in APP_CATALOG if spec.supports_multi_instance],
    }


def _coerce_int(value: Any, default: int, min_value: int = 0) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = int(default)
    return max(min_value, out)


def _sanitize_profile(payload: dict[str, Any], lanes: list[dict[str, Any]]) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    base = _default_profile(lanes)

    lane_by_id: dict[str, dict[str, Any]] = {}
    for raw in source.get("lanes", []):
        if not isinstance(raw, dict):
            continue
        lid = str(raw.get("instance_id", "")).strip()
        if not lid:
            continue
        lane_by_id[lid] = dict(raw)

    merged_lanes: list[dict[str, Any]] = []
    for idx, lane in enumerate(lanes):
        instance_id = str(lane.get("instance_id", f"lane-{idx+1}")).strip() or f"lane-{idx+1}"
        existing = lane_by_id.get(instance_id, {})
        merged_lanes.append(
            {
                "instance_id": instance_id,
                "name": str(existing.get("name", lane.get("name", instance_id))).strip() or instance_id,
                "priority": _coerce_int(existing.get("priority", idx + 1), idx + 1, min_value=1),
                "directive": str(existing.get("directive", f"-{idx + 1}")).strip() or f"-{idx + 1}",
                "role": str(existing.get("role", "auxiliary")).strip() or "auxiliary",
            }
        )

    merged_lanes.sort(key=lambda row: (int(row.get("priority", 99)), str(row.get("instance_id", ""))))
    for idx, row in enumerate(merged_lanes):
        row["priority"] = idx + 1
        row["directive"] = f"-{idx + 1}"
        if idx == 0:
            row["role"] = "primary"
        elif idx == 1:
            row["role"] = "secondary"
        elif idx == 2:
            row["role"] = "tertiary"
        else:
            row["role"] = "auxiliary"

    token_policy = dict(base.get("token_policy", {}))
    token_policy.update(source.get("token_policy", {}) if isinstance(source.get("token_policy"), dict) else {})
    token_policy["daily_budget_tokens"] = _coerce_int(token_policy.get("daily_budget_tokens", 120000), 120000, min_value=0)
    token_policy["weekly_budget_tokens"] = _coerce_int(token_policy.get("weekly_budget_tokens", 600000), 600000, min_value=0)
    token_policy["paid_budget_tokens"] = _coerce_int(token_policy.get("paid_budget_tokens", 0), 0, min_value=0)

    routing = dict(base.get("routing", {}))
    routing.update(source.get("routing", {}) if isinstance(source.get("routing"), dict) else {})
    routing["prefix_directive_enabled"] = bool(routing.get("prefix_directive_enabled", True))
    strategy = str(routing.get("fallback_strategy", "priority_available")).strip().lower()
    routing["fallback_strategy"] = strategy if strategy in {"priority_available", "priority_order"} else "priority_available"

    incoming_weights = source.get("lane_weights", {})
    normalized = _normalize_weights(_default_lane_weights(len(merged_lanes)))
    lane_weights: dict[str, float] = {}
    if isinstance(incoming_weights, dict):
        raw_weights: list[float] = []
        for idx, lane in enumerate(merged_lanes):
            key = str(lane.get("instance_id", ""))
            try:
                val = float(incoming_weights.get(key, normalized[idx] if idx < len(normalized) else 0.0))
            except (TypeError, ValueError):
                val = normalized[idx] if idx < len(normalized) else 0.0
            raw_weights.append(max(0.0, val))
        fixed = _normalize_weights(raw_weights)
    else:
        fixed = normalized
    for idx, lane in enumerate(merged_lanes):
        lane_weights[str(lane.get("instance_id", ""))] = round(float(fixed[idx] if idx < len(fixed) else 0.0), 6)

    app_preferences = source.get("app_preferences", base.get("app_preferences", []))
    if not isinstance(app_preferences, list):
        app_preferences = list(base.get("app_preferences", []))
    app_pref = [str(x).strip() for x in app_preferences if str(x).strip()]
    known_apps = {spec.app_id for spec in APP_CATALOG}
    app_pref = [x for x in app_pref if x in known_apps]
    if not app_pref:
        app_pref = list(base.get("app_preferences", []))

    return {
        "version": "ccbs-multi-instance-profile-v1",
        "updated_at": _utc_now(),
        "routing": routing,
        "token_policy": token_policy,
        "lane_weights": lane_weights,
        "lanes": merged_lanes,
        "app_preferences": app_pref,
    }


def load_multi_instance_profile(root: Path) -> dict[str, Any]:
    path = _profile_path(root)
    lanes = _load_lane_config(root)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except Exception:
            raw = {}
    profile = _sanitize_profile(raw, lanes)
    if raw != profile:
        path.write_text(json.dumps(profile, indent=2, sort_keys=True), encoding="utf-8")
    return profile


def update_multi_instance_profile(root: Path, updates: dict[str, Any]) -> dict[str, Any]:
    current = load_multi_instance_profile(root)
    merged = dict(current)
    if isinstance(updates, dict):
        for key in ("routing", "token_policy", "lane_weights", "lanes", "app_preferences"):
            if key in updates:
                merged[key] = updates.get(key)
    profile = _sanitize_profile(merged, _load_lane_config(root))
    _profile_path(root).write_text(json.dumps(profile, indent=2, sort_keys=True), encoding="utf-8")
    return profile


def _default_runtime(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    lane_runtime: dict[str, Any] = {}
    for lane in lanes:
        lid = str(lane.get("instance_id", "")).strip()
        if not lid:
            continue
        lane_runtime[lid] = {
            "active_task": "",
            "last_message_preview": "",
            "last_assigned_at": "",
            "assignment_count": 0,
            "last_directive": "",
        }
    return {
        "version": "ccbs-multi-instance-runtime-v1",
        "updated_at": _utc_now(),
        "day_key": _today_key(),
        "week_key": _week_key(),
        "month_key": _month_key(),
        "daily_used_tokens": 0,
        "weekly_used_tokens": 0,
        "paid_used_tokens": 0,
        "assignment_seq": 0,
        "lane_runtime": lane_runtime,
        "history": [],
    }


def _load_runtime(root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    path = _runtime_path(root)
    lanes = list(profile.get("lanes", []))
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except Exception:
            raw = {}
    runtime = _default_runtime(lanes)
    runtime.update({k: raw.get(k, runtime[k]) for k in runtime.keys() if k != "lane_runtime"})
    lane_runtime = raw.get("lane_runtime", {})
    if not isinstance(lane_runtime, dict):
        lane_runtime = {}
    fixed_lane_runtime: dict[str, Any] = {}
    for lane in lanes:
        lid = str(lane.get("instance_id", "")).strip()
        base = _default_runtime([lane])["lane_runtime"].get(lid, {})
        incoming = lane_runtime.get(lid, {})
        if not isinstance(incoming, dict):
            incoming = {}
        merged = dict(base)
        merged.update(incoming)
        merged["assignment_count"] = _coerce_int(merged.get("assignment_count", 0), 0, min_value=0)
        fixed_lane_runtime[lid] = merged
    runtime["lane_runtime"] = fixed_lane_runtime
    runtime["history"] = list(raw.get("history", [])) if isinstance(raw.get("history"), list) else []
    runtime["assignment_seq"] = _coerce_int(runtime.get("assignment_seq", 0), 0, min_value=0)

    # reset rolling windows when boundary changed
    today = _today_key()
    week = _week_key()
    month = _month_key()
    if str(runtime.get("day_key", "")) != today:
        runtime["day_key"] = today
        runtime["daily_used_tokens"] = 0
    if str(runtime.get("week_key", "")) != week:
        runtime["week_key"] = week
        runtime["weekly_used_tokens"] = 0
    if str(runtime.get("month_key", "")) != month:
        runtime["month_key"] = month
        runtime["paid_used_tokens"] = 0

    runtime["daily_used_tokens"] = _coerce_int(runtime.get("daily_used_tokens", 0), 0, min_value=0)
    runtime["weekly_used_tokens"] = _coerce_int(runtime.get("weekly_used_tokens", 0), 0, min_value=0)
    runtime["paid_used_tokens"] = _coerce_int(runtime.get("paid_used_tokens", 0), 0, min_value=0)
    runtime["updated_at"] = _utc_now()
    path.write_text(json.dumps(runtime, indent=2, sort_keys=True), encoding="utf-8")
    return runtime


def _save_runtime(root: Path, runtime: dict[str, Any]) -> None:
    runtime["updated_at"] = _utc_now()
    _runtime_path(root).write_text(json.dumps(runtime, indent=2, sort_keys=True), encoding="utf-8")


def _lane_rows_from_state(root: Path, profile: dict[str, Any], runtime: dict[str, Any]) -> tuple[list[dict[str, Any]], bool, str]:
    lanes = _load_lane_config(root)
    codex_found, codex_cmd = _which_any(("codex",))
    workspace_state = list_workspaces(root)
    known_ids = {
        str(item.get("workspace_id", "")).strip().lower()
        for item in workspace_state.get("workspaces", [])
        if isinstance(item, dict)
    }
    registration_enforced = bool(known_ids)
    profile_by_id = {str(item.get("instance_id", "")): dict(item) for item in profile.get("lanes", []) if isinstance(item, dict)}

    lane_rows: list[dict[str, Any]] = []
    for lane in lanes:
        lane_id = str(lane.get("instance_id", "")).strip()
        lane_name = str(lane.get("name", lane_id or "lane")).strip()
        workspace_id = str(lane.get("workspace_id", "")).strip().lower()
        lane_path_raw = str(lane.get("path", "")).strip()
        lane_path = _resolve_instance_path(lane_path_raw)
        path_exists = lane_path.exists()
        registered = (workspace_id in known_ids if workspace_id else False) if registration_enforced else True
        available = bool(codex_found and path_exists and registered)

        meta = profile_by_id.get(lane_id, {})
        lane_runtime = runtime.get("lane_runtime", {}).get(lane_id, {}) if isinstance(runtime.get("lane_runtime"), dict) else {}
        if not isinstance(lane_runtime, dict):
            lane_runtime = {}
        lane_rows.append(
            {
                "instance_id": lane_id,
                "name": lane_name,
                "workspace_id": workspace_id,
                "path": lane_path_raw,
                "path_exists": path_exists,
                "registered": registered if registration_enforced else "n/a",
                "available": available,
                "launch_args": str(lane.get("launch_args", "")),
                "priority": _coerce_int(meta.get("priority", 99), 99, min_value=1),
                "directive": str(meta.get("directive", "")).strip(),
                "role": str(meta.get("role", "auxiliary")).strip(),
                "active_task": str(lane_runtime.get("active_task", "")).strip(),
                "last_message_preview": str(lane_runtime.get("last_message_preview", "")).strip(),
                "last_assigned_at": str(lane_runtime.get("last_assigned_at", "")).strip(),
                "assignment_count": _coerce_int(lane_runtime.get("assignment_count", 0), 0, min_value=0),
            }
        )
    lane_rows.sort(key=lambda row: (int(row.get("priority", 99)), str(row.get("name", ""))))
    return lane_rows, codex_found, codex_cmd


def _lane_token_allocations(profile: dict[str, Any], budget: int) -> list[dict[str, Any]]:
    lanes = [dict(x) for x in profile.get("lanes", []) if isinstance(x, dict)]
    weights_map = profile.get("lane_weights", {})
    if not isinstance(weights_map, dict):
        weights_map = {}
    raw_weights: list[float] = []
    for lane in lanes:
        lid = str(lane.get("instance_id", ""))
        try:
            raw_weights.append(max(0.0, float(weights_map.get(lid, 0.0))))
        except (TypeError, ValueError):
            raw_weights.append(0.0)
    fixed = _normalize_weights(raw_weights if any(raw_weights) else _default_lane_weights(len(lanes)))
    rows: list[dict[str, Any]] = []
    for idx, lane in enumerate(lanes):
        weight = float(fixed[idx] if idx < len(fixed) else 0.0)
        allocation = int(round(max(0, budget) * weight)) if budget > 0 else 0
        rows.append(
            {
                "instance_id": str(lane.get("instance_id", "")),
                "directive": str(lane.get("directive", "")),
                "priority": int(lane.get("priority", idx + 1)),
                "weight": round(weight, 6),
                "allocated_tokens": allocation,
            }
        )
    return rows


def get_token_telemetry(root: Path, profile: dict[str, Any] | None = None, runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    profile_payload = profile or load_multi_instance_profile(root)
    runtime_payload = runtime or _load_runtime(root, profile_payload)
    quota = quota_summary(root)
    policy = profile_payload.get("token_policy", {})
    if not isinstance(policy, dict):
        policy = {}

    daily_budget = _coerce_int(policy.get("daily_budget_tokens", 0), 0, min_value=0)
    weekly_budget = _coerce_int(policy.get("weekly_budget_tokens", 0), 0, min_value=0)
    paid_budget_cfg = _coerce_int(policy.get("paid_budget_tokens", 0), 0, min_value=0)
    paid_budget = paid_budget_cfg if paid_budget_cfg > 0 else _coerce_int(quota.get("monthly_token_budget", 0), 0, min_value=0)

    daily_used = _coerce_int(runtime_payload.get("daily_used_tokens", 0), 0, min_value=0)
    weekly_used = _coerce_int(runtime_payload.get("weekly_used_tokens", 0), 0, min_value=0)
    paid_used_runtime = _coerce_int(runtime_payload.get("paid_used_tokens", 0), 0, min_value=0)
    paid_used_quota = _coerce_int(quota.get("used_tokens", 0), 0, min_value=0)
    paid_used = max(paid_used_runtime, paid_used_quota)

    def _remaining(budget: int, used: int) -> int | None:
        if budget <= 0:
            return None
        return max(0, budget - used)

    daily_remaining = _remaining(daily_budget, daily_used)
    weekly_remaining = _remaining(weekly_budget, weekly_used)
    paid_remaining = _remaining(paid_budget, paid_used)

    return {
        "version": "ccbs-token-telemetry-v1",
        "source": {
            "daily_weekly": "multi_instance_runtime",
            "paid": "ai_quota_state+runtime",
            "note": "Provider-native token counters may differ; CCBS counters are local authoritative estimates.",
        },
        "daily": {
            "budget_tokens": daily_budget,
            "used_tokens": daily_used,
            "remaining_tokens": daily_remaining,
            "window_key": str(runtime_payload.get("day_key", "")),
            "lane_allocations": _lane_token_allocations(profile_payload, daily_budget),
        },
        "weekly": {
            "budget_tokens": weekly_budget,
            "used_tokens": weekly_used,
            "remaining_tokens": weekly_remaining,
            "window_key": str(runtime_payload.get("week_key", "")),
            "lane_allocations": _lane_token_allocations(profile_payload, weekly_budget),
        },
        "paid": {
            "budget_tokens": paid_budget,
            "used_tokens": paid_used,
            "remaining_tokens": paid_remaining,
            "window_key": str(runtime_payload.get("month_key", "")),
            "lane_allocations": _lane_token_allocations(profile_payload, paid_budget),
        },
    }


def get_multi_instance_state(root: Path) -> dict[str, Any]:
    profile = load_multi_instance_profile(root)
    runtime = _load_runtime(root, profile)
    lane_rows, codex_found, codex_cmd = _lane_rows_from_state(root, profile, runtime)
    available = sum(1 for row in lane_rows if bool(row.get("available", False)))
    total = len(lane_rows)
    workspace_state = list_workspaces(root)
    known_ids = {
        str(item.get("workspace_id", "")).strip().lower()
        for item in workspace_state.get("workspaces", [])
        if isinstance(item, dict)
    }
    registration_enforced = bool(known_ids)
    return {
        "version": "ccbs-multi-instance-state-v2",
        "orchestrator": _orchestrator_identity(),
        "codex_cli_found": codex_found,
        "codex_cli": codex_cmd,
        "workspace_registry_enforced": registration_enforced,
        "availability_counter": f"{available}/{total}",
        "available_lanes": available,
        "total_lanes": total,
        "lanes": lane_rows,
        "workspace_registry": {
            "current": str(workspace_state.get("current", "default")),
            "known_workspace_ids": sorted(known_ids),
        },
        "routing_contract": {
            "directive_prefix": "-<lane_number>",
            "examples": ["-1 run this in primary lane", "-2 check fallback lane", "-3 run lowest-priority lane"],
        },
        "token_telemetry": get_token_telemetry(root, profile=profile, runtime=runtime),
    }


def get_multi_instance_runtime_summary(root: Path) -> dict[str, Any]:
    profile = load_multi_instance_profile(root)
    runtime = _load_runtime(root, profile)
    state = get_multi_instance_state(root)
    history = runtime.get("history", [])
    if not isinstance(history, list):
        history = []
    return {
        "orchestrator": _orchestrator_identity(),
        "profile": profile,
        "state": state,
        "runtime": {
            "updated_at": str(runtime.get("updated_at", "")),
            "assignment_seq": _coerce_int(runtime.get("assignment_seq", 0), 0, min_value=0),
            "history_tail": history[-30:],
        },
        "token_telemetry": state.get("token_telemetry", {}),
    }


def sync_multi_instance_workspaces(root: Path) -> dict[str, Any]:
    lanes = _load_lane_config(root)
    state = list_workspaces(root)
    known_ids = {
        str(item.get("workspace_id", "")).strip().lower()
        for item in state.get("workspaces", [])
        if isinstance(item, dict)
    }
    created: list[str] = []
    existing: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for lane in lanes:
        workspace_id = str(lane.get("workspace_id", "")).strip().lower()
        lane_name = str(lane.get("name", workspace_id or "lane")).strip()
        if not workspace_id:
            skipped.append(lane_name)
            continue
        if workspace_id in known_ids:
            existing.append(workspace_id)
            continue
        try:
            create_workspace(
                root=root,
                workspace_id=workspace_id,
                name=lane_name,
                description="Managed by CCBS multi-instance agent",
            )
            created.append(workspace_id)
            known_ids.add(workspace_id)
        except Exception as exc:
            errors.append(f"{workspace_id}: {exc}")
    return {
        "ok": not errors,
        "created": created,
        "existing": existing,
        "skipped": skipped,
        "errors": errors,
        "state": get_multi_instance_state(root),
    }


def _build_optimizer_tasks(discovery_rows: list[dict[str, Any]]) -> list[TaskFeatures]:
    tasks: list[TaskFeatures] = []
    for row in discovery_rows:
        if not bool(row.get("supports_multi_instance", False)):
            continue
        installed = bool(row.get("installed", False))
        category = str(row.get("category", "general")).strip().lower()
        score = float(row.get("ccbs_score", 0.0))
        goal_impact = max(0.0, min(score / 1.2, 1.0))
        unlock_value = 1.0 if bool(row.get("supports_workspace_isolation", False)) else 0.55
        critical_path = 0.95 if str(row.get("app_id", "")).strip() == "codex_cli" else 0.7
        information_gain = 0.85 if installed else 0.35
        parallelization_gain = 0.95 if installed else 0.4
        duration_cost = 0.12 if installed else 0.75
        switch_cost = 0.22 if category in {"agent", "ui"} else 0.32
        risk_penalty = 0.08 if installed else 0.45
        retry_penalty = 0.06 if installed else 0.5
        tasks.append(
            TaskFeatures(
                task_id=str(row.get("app_id", "")).strip() or "unknown",
                name=str(row.get("name", "app")).strip(),
                goal_impact=goal_impact,
                unlock_value=unlock_value,
                critical_path=critical_path,
                information_gain=information_gain,
                parallelization_gain=parallelization_gain,
                duration_cost=duration_cost,
                switch_cost=switch_cost,
                risk_penalty=risk_penalty,
                retry_penalty=retry_penalty,
                required_resources={f"category:{category}"} if category in {"runtime"} else set(),
                tool_group=category,
                environment_group="host-local",
                conflicts_with=set(),
                synergy_with={"codex_cli": 0.35} if str(row.get("app_id", "")).strip() in {"vscode", "powershell"} else {},
            )
        )
    return tasks


def optimize_multi_instance_bundle(root: Path, *, max_parallel: int = 3, mode: str = "auto") -> dict[str, Any]:
    safe_parallel = max(1, min(int(max_parallel), 8))
    discovery = discover_multi_instance_apps(root)
    rows = list(discovery.get("apps", []))
    tasks = _build_optimizer_tasks(rows)
    weights = SchedulerWeights(
        goal_impact=5.4,
        unlock_value=3.2,
        critical_path=4.6,
        information_gain=2.0,
        parallelization_gain=2.6,
        duration_cost=1.8,
        switch_cost=1.2,
        risk_penalty=2.3,
        retry_penalty=1.0,
    )
    selector = QuantumSelector(weights)
    selection = selector.solve(tasks, max_parallel=safe_parallel)
    packet = make_decision_packet(
        selected=list(selection.get("selected_tasks", [])),
        tasks=tasks,
        weights=weights,
        solver_mode=str(selection.get("solver_mode", "classical_bundle")),
    )
    packet["objective_score"] = selection.get("objective_score")
    packet["frontier_size"] = len(tasks)
    packet["mode_requested"] = mode
    packet["optimizer_target"] = "ccbs_multi_instance_app_bundle"
    packet["max_parallel"] = safe_parallel
    return {
        "orchestrator": _orchestrator_identity(),
        "selection": packet,
        "state": get_multi_instance_state(root),
        "discovery_summary": discovery.get("summary", {}),
        "candidates": [
            {
                "task_id": task.task_id,
                "name": task.name,
                "goal_impact": task.goal_impact,
                "parallelization_gain": task.parallelization_gain,
                "risk_penalty": task.risk_penalty,
            }
            for task in tasks
        ],
    }


def _run_manager_script(root: Path, *, action: str) -> dict[str, Any]:
    script = root / "scripts" / "codex_multi_manager.ps1"
    if not script.exists():
        return {
            "ok": False,
            "action": action,
            "status": "script_missing",
            "detail": f"Missing script: {script}",
        }
    runner = shutil.which("powershell.exe") or shutil.which("pwsh")
    if not runner:
        return {
            "ok": False,
            "action": action,
            "status": "runner_missing",
            "detail": "PowerShell runner not found (powershell.exe/pwsh).",
        }
    cmd: list[str] = [runner, "-NoProfile"]
    if runner.lower().endswith("powershell.exe"):
        cmd += ["-ExecutionPolicy", "Bypass"]
    cmd += ["-File", str(script), "-Action", action]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "status": "completed" if proc.returncode == 0 else "failed",
            "action": action,
            "exit_code": proc.returncode,
            "command": shlex.join(cmd),
            "stdout": str(proc.stdout or "").strip(),
            "stderr": str(proc.stderr or "").strip(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "action": action,
            "status": "failed",
            "detail": str(exc),
            "command": shlex.join(cmd),
        }


def _extract_directive(message: str) -> tuple[str, str]:
    text = str(message or "")
    match = _DIRECTIVE_RE.match(text)
    if not match:
        alias = _DIRECTIVE_ALIAS_RE.match(text)
        if alias:
            lane_num = str(alias.group(1)).strip()
            rest = str(alias.group(2)).strip()
            if lane_num.isdigit():
                return f"-{int(lane_num)}", rest
        lane_alias = _DIRECTIVE_LANE_RE.match(text)
        if lane_alias:
            lane_num = str(lane_alias.group(1)).strip()
            rest = str(lane_alias.group(2)).strip()
            if lane_num.isdigit():
                return f"-{int(lane_num)}", rest
        return "", text.strip()
    directive_raw = str(match.group(1)).strip()
    rest = str(match.group(2)).strip()
    lane_num = directive_raw.lstrip("-")
    if lane_num.isdigit():
        return f"-{int(lane_num)}", rest
    return directive_raw, rest


def _normalize_user_request_text(message: str) -> str:
    raw = str(message or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in raw.split("\n")]
    normalized_lines = [line for line in lines if line]
    if not normalized_lines:
        return ""
    normalized = "\n".join(normalized_lines).strip()
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _infer_workstreams(message: str) -> list[str]:
    text = str(message or "").lower()
    streams: list[tuple[str, tuple[str, ...]]] = [
        ("frontend", ("web interface", "frontend", "front-end", "ui", "react", "vue", "svelte")),
        ("backend", ("backend", "back-end", "api", "server", "flask", "fastapi", "django", "express")),
        ("auth", ("auth", "login", "log in", "signin", "sign in", "jwt", "oauth")),
        ("database", ("database", "db", "sqlite", "postgres", "mysql", "storage")),
        ("testing", ("test", "qa", "validation", "smoke test", "integration test")),
        ("docs", ("docs", "documentation", "readme", "guide")),
        ("deployment", ("deploy", "deployment", "docker", "kubernetes", "host", "publish")),
    ]
    out: list[str] = []
    for name, tokens in streams:
        if any(token in text for token in tokens):
            out.append(name)
    if not out:
        out.append("implementation")
    return out


def _infer_complexity(workstreams: list[str], message: str) -> str:
    size = len([x for x in workstreams if x])
    word_count = len([x for x in str(message or "").split() if x.strip()])
    if size >= 5 or word_count >= 120:
        return "high"
    if size >= 3 or word_count >= 50:
        return "medium"
    return "low"


def _build_task_label_from_request(message: str, workstreams: list[str]) -> str:
    text = str(message or "").strip()
    lower = text.lower()
    verb = "Implement"
    if any(token in lower for token in ("build", "create", "develop")):
        verb = "Build"
    elif any(token in lower for token in ("fix", "repair", "debug")):
        verb = "Fix"
    elif any(token in lower for token in ("refine", "optimize", "improve", "streamline")):
        verb = "Refine"

    app_target = "task"
    if any(token in lower for token in ("todo", "to-do")):
        app_target = "to-do app"
    elif "productivity" in lower:
        app_target = "productivity app"
    elif "api" in lower and "web" not in lower:
        app_target = "api service"
    elif "web" in lower or "ui" in lower or "interface" in lower:
        app_target = "web app"

    ordered = [x for x in ("frontend", "backend", "auth", "database", "testing", "docs", "deployment") if x in workstreams]
    stream_hint = ", ".join(ordered[:3]).strip()
    label = f"{verb} {app_target}".strip()
    if stream_hint:
        label = f"{label} ({stream_hint})"
    return label[:120].strip()


def _parse_request(message: str) -> dict[str, Any]:
    normalized = _normalize_user_request_text(message)
    workstreams = _infer_workstreams(normalized)
    complexity = _infer_complexity(workstreams, normalized)
    default_task_label = _build_task_label_from_request(normalized, workstreams)
    recommended_parallelism = max(1, min(3, len(workstreams)))
    return {
        "normalized_message": normalized,
        "workstreams": workstreams,
        "complexity": complexity,
        "recommended_parallelism": recommended_parallelism,
        "default_task_label": default_task_label,
    }


def _choose_lane_for_route(
    state: dict[str, Any],
    profile: dict[str, Any],
    directive: str,
    requested_lane_id: str = "",
) -> dict[str, Any] | None:
    lanes = [dict(x) for x in state.get("lanes", []) if isinstance(x, dict)]
    if not lanes:
        return None
    by_id = {str(lane.get("instance_id", "")): lane for lane in lanes}
    by_directive = {str(lane.get("directive", "")): lane for lane in lanes}
    rid = str(requested_lane_id or "").strip()
    if rid and rid in by_id:
        return by_id[rid]
    if directive and directive in by_directive:
        return by_directive[directive]
    strategy = str(profile.get("routing", {}).get("fallback_strategy", "priority_available")).strip().lower()
    if strategy == "priority_order":
        return sorted(lanes, key=lambda row: int(row.get("priority", 99)))[0]
    available = [lane for lane in lanes if bool(lane.get("available", False))]
    if available:
        return sorted(available, key=lambda row: int(row.get("priority", 99)))[0]
    return sorted(lanes, key=lambda row: int(row.get("priority", 99)))[0]


def route_message_to_lane(
    root: Path,
    *,
    message: str,
    task_label: str = "",
    requested_lane_id: str = "",
    apply_usage: bool = False,
    estimated_tokens_override: int = 0,
) -> dict[str, Any]:
    profile = load_multi_instance_profile(root)
    runtime = _load_runtime(root, profile)
    state = get_multi_instance_state(root)
    routing = profile.get("routing", {})
    prefix_enabled = bool(routing.get("prefix_directive_enabled", True)) if isinstance(routing, dict) else True

    directive, message_without_directive = (
        _extract_directive(message) if prefix_enabled else ("", str(message or "").strip())
    )
    parser_info = _parse_request(message_without_directive or str(message or ""))
    clean_message = str(parser_info.get("normalized_message", "")).strip() or str(message_without_directive or "").strip()
    lane = _choose_lane_for_route(state, profile, directive=directive, requested_lane_id=requested_lane_id)
    if lane is None:
        return {
            "ok": False,
            "status": "no_lanes_configured",
            "detail": "No lanes configured in config/codex_instances.json",
        }

    lane_id = str(lane.get("instance_id", "")).strip()
    lane_runtime = runtime.get("lane_runtime", {}).get(lane_id, {}) if isinstance(runtime.get("lane_runtime"), dict) else {}
    if not isinstance(lane_runtime, dict):
        lane_runtime = {}

    task = str(task_label or "").strip()
    if not task:
        task = str(parser_info.get("default_task_label", "")).strip()
    if not task:
        task = (clean_message[:120].strip() or "lane assignment")

    est = _coerce_int(estimated_tokens_override, 0, min_value=0)
    if est <= 0:
        est = estimate_tokens(clean_message or message or "")
    est = max(1, est)

    lane_runtime["active_task"] = task
    lane_runtime["last_message_preview"] = (clean_message or message or "")[:220]
    lane_runtime["last_assigned_at"] = _utc_now()
    lane_runtime["assignment_count"] = _coerce_int(lane_runtime.get("assignment_count", 0), 0, min_value=0) + 1
    lane_runtime["last_directive"] = directive
    runtime.setdefault("lane_runtime", {})
    runtime["lane_runtime"][lane_id] = lane_runtime

    runtime["assignment_seq"] = _coerce_int(runtime.get("assignment_seq", 0), 0, min_value=0) + 1
    runtime["daily_used_tokens"] = _coerce_int(runtime.get("daily_used_tokens", 0), 0, min_value=0) + est
    runtime["weekly_used_tokens"] = _coerce_int(runtime.get("weekly_used_tokens", 0), 0, min_value=0) + est
    runtime["paid_used_tokens"] = _coerce_int(runtime.get("paid_used_tokens", 0), 0, min_value=0) + est

    history = runtime.get("history", [])
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "seq": int(runtime["assignment_seq"]),
            "timestamp": _utc_now(),
            "directive": directive,
            "lane_id": lane_id,
            "lane_name": str(lane.get("name", lane_id)),
            "task": task,
            "message_preview": (clean_message or message or "")[:220],
            "estimated_tokens": est,
        }
    )
    runtime["history"] = history[-200:]
    _save_runtime(root, runtime)

    if apply_usage:
        apply_quota_usage(root, used_tokens=est)

    refreshed = get_multi_instance_runtime_summary(root)
    return {
        "ok": True,
        "orchestrator": _orchestrator_identity(),
        "directive": directive,
        "normalized_message": clean_message or str(message or "").strip(),
        "lane_selected": {
            "instance_id": lane_id,
            "name": str(lane.get("name", lane_id)),
            "priority": int(lane.get("priority", 99)),
            "directive": str(lane.get("directive", "")),
            "available": bool(lane.get("available", False)),
            "path": str(lane.get("path", "")),
        },
        "task_assigned": task,
        "estimated_tokens": est,
        "token_telemetry": refreshed.get("token_telemetry", {}),
        "execution_view": refreshed.get("state", {}),
        "runtime": refreshed.get("runtime", {}),
        "parser": {
            "workstreams": list(parser_info.get("workstreams", [])),
            "complexity": str(parser_info.get("complexity", "low")),
            "recommended_parallelism": int(parser_info.get("recommended_parallelism", 1) or 1),
            "default_task_label": str(parser_info.get("default_task_label", "")),
        },
    }


def run_multi_instance_control_action(
    root: Path,
    *,
    action: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    normalized = str(action or "").strip().lower()
    if normalized == "status":
        return {"ok": True, "action": normalized, "state": get_multi_instance_state(root)}
    if normalized == "sync-workspaces":
        out = sync_multi_instance_workspaces(root)
        out["action"] = normalized
        return out
    if normalized == "launch":
        if not confirmed:
            return {
                "ok": False,
                "action": normalized,
                "status": "confirmation_required",
                "detail": "launch requires confirmed=true",
            }
        out = _run_manager_script(root, action="launch")
        out["state"] = get_multi_instance_state(root)
        return out
    return {
        "ok": False,
        "action": normalized,
        "status": "unknown_action",
        "detail": "supported actions: status | sync-workspaces | launch",
    }
