"""Quantum foundation helpers for CCBS setup and evidence generation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from apps.orchestrator.decision_contracts import (
    DecisionConstraints,
    DecisionWeights,
    TaskDecisionInput,
    VMModalProfile,
)
from apps.orchestrator.quantum_decision import quantum_decision
from .repo import RepoError, repo_root

DEFAULT_VENV_NAME = ".venv-quantum"
DEFAULT_SCAFFOLD_DIR = "quantum"
DEFAULT_LOCAL_OUTPUT = "dist/quantum/evidence/local_simulator_run.json"
DEFAULT_RUN_STORE_DIR = ".ccbs/quantum/runs"
DEFAULT_MATRIX_STORE_DIR = ".ccbs/quantum/matrix"
DEFAULT_COLLECT_OUTPUT_DIR = "dist/quantum/evidence"
DEFAULT_DASHBOARD_HTML = "dist/quantum/dashboard/quantum_dashboard.html"
DEFAULT_DASHBOARD_JSON = "dist/quantum/dashboard/quantum_dashboard.json"
SUPPORTED_PROVIDERS = ("azure", "ibm")
SUPPORTED_MODES = ("auto", "qaoa", "exact")
TOKEN_ENV_KEYS = ("QISKIT_IBM_TOKEN", "IBM_QUANTUM_TOKEN")
INSTANCE_ENV_KEYS = ("QISKIT_IBM_INSTANCE", "IBM_QUANTUM_INSTANCE")


class QuantumDependencyError(RuntimeError):
    """Raised when optional quantum dependencies are not installed."""


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def _has_module(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _resolve_output_path(root: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _detect_venv_python(venv_root: Path) -> Path | None:
    candidates = [
        venv_root / "bin" / "python",
        venv_root / "Scripts" / "python.exe",
        venv_root / "Scripts" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _collect_present_env(keys: tuple[str, ...]) -> list[str]:
    present: list[str] = []
    for key in keys:
        if str(os.getenv(key, "")).strip():
            present.append(key)
    return present


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    if isinstance(value, str):
        return {part.strip() for part in value.split(",") if part.strip()}
    raise ValueError("expected list/set/tuple/string value")


def _normalize_provider(value: str) -> str:
    provider = str(value or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"provider must be one of: {', '.join(SUPPORTED_PROVIDERS)}")
    return provider


def _normalize_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"mode must be one of: {', '.join(SUPPORTED_MODES)}")
    return mode


def _provider_chain(provider: str, failover_enabled: bool) -> list[str]:
    normalized = _normalize_provider(provider)
    if normalized == "azure":
        chain = ["azure-quantum-via-foundry", "ibm-quantum-runtime", "classical-baseline"]
    else:
        chain = ["ibm-quantum-runtime", "classical-baseline"]
    if not failover_enabled:
        return chain[:1]
    return chain


def _runs_root(root: Path) -> Path:
    path = _resolve_output_path(root, DEFAULT_RUN_STORE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _matrix_root(root: Path) -> Path:
    path = _resolve_output_path(root, DEFAULT_MATRIX_STORE_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_path(root: Path, run_id: str) -> Path:
    clean = str(run_id or "").strip()
    if not clean:
        raise ValueError("run_id is required")
    return (_runs_root(root) / clean).resolve()


def _matrix_path(root: Path, matrix_id: str) -> Path:
    clean = str(matrix_id or "").strip()
    if not clean:
        raise ValueError("matrix_id is required")
    return (_matrix_root(root) / clean).resolve()


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_json_digest(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_task(row: dict[str, Any], index: int) -> TaskDecisionInput:
    task_id = str(row.get("task_id", "")).strip()
    if not task_id:
        raise ValueError(f"tasks[{index}] missing task_id")
    name = str(row.get("name", task_id)).strip() or task_id
    metadata_value = row.get("metadata", {})
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    return TaskDecisionInput(
        task_id=task_id,
        name=name,
        value=_coerce_float(row.get("value"), 0.0),
        cost=_coerce_float(row.get("cost"), 0.0),
        risk=_coerce_float(row.get("risk"), 0.0),
        blocked=_coerce_bool(row.get("blocked"), False),
        dependencies=_coerce_string_set(row.get("dependencies", [])),
        required_resources=_coerce_string_set(row.get("required_resources", [])),
        conflicts_with=_coerce_string_set(row.get("conflicts_with", [])),
        vm_lane=(str(row.get("vm_lane", "")).strip() or None),
        estimated_vm_memory_mb=max(0, _coerce_int(row.get("estimated_vm_memory_mb"), 0)),
        requires_guest_model=_coerce_bool(row.get("requires_guest_model"), False),
        metadata=metadata,
    )


def _parse_constraints(row: Any) -> DecisionConstraints:
    if row is None:
        row = {}
    if not isinstance(row, dict):
        raise ValueError("constraints must be an object")
    vm_profile_obj = row.get("vm_profile")
    vm_profile: VMModalProfile | None = None
    if isinstance(vm_profile_obj, dict):
        vm_profile = VMModalProfile(
            mode_id=str(vm_profile_obj.get("mode_id", "host_shared_model")).strip() or "host_shared_model",
            allowed_vm_lanes=_coerce_string_set(vm_profile_obj.get("allowed_vm_lanes", [])),
            max_vm_memory_mb_per_task=max(0, _coerce_int(vm_profile_obj.get("max_vm_memory_mb_per_task"), 0)),
            prefer_host_inference=_coerce_bool(vm_profile_obj.get("prefer_host_inference"), True),
            notes=str(vm_profile_obj.get("notes", "")).strip(),
        )
    pairs_raw = row.get("mutual_exclusion_pairs", [])
    pairs: set[tuple[str, str]] = set()
    if isinstance(pairs_raw, list):
        for pair in pairs_raw:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            left = str(pair[0]).strip()
            right = str(pair[1]).strip()
            if left and right and left != right:
                pairs.add(tuple(sorted((left, right))))
    return DecisionConstraints(
        choose_exactly_one=_coerce_bool(row.get("choose_exactly_one"), True),
        max_selected=max(1, _coerce_int(row.get("max_selected"), 1)),
        blocked_task_ids=_coerce_string_set(row.get("blocked_task_ids", [])),
        mutual_exclusion_pairs=pairs,
        vm_profile=vm_profile,
    )


def _parse_weights(row: Any) -> DecisionWeights:
    if row is None:
        return DecisionWeights()
    if not isinstance(row, dict):
        raise ValueError("weights must be an object")
    defaults = DecisionWeights()
    return DecisionWeights(
        value_weight=_coerce_float(row.get("value_weight"), defaults.value_weight),
        cost_weight=_coerce_float(row.get("cost_weight"), defaults.cost_weight),
        risk_weight=_coerce_float(row.get("risk_weight"), defaults.risk_weight),
        dependency_penalty=_coerce_float(row.get("dependency_penalty"), defaults.dependency_penalty),
        resource_penalty=_coerce_float(row.get("resource_penalty"), defaults.resource_penalty),
        conflict_penalty=_coerce_float(row.get("conflict_penalty"), defaults.conflict_penalty),
        cardinality_penalty=_coerce_float(row.get("cardinality_penalty"), defaults.cardinality_penalty),
    )


def _load_batch(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("batch payload must be a JSON object")
    tasks_raw = payload.get("tasks", [])
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise ValueError("batch payload requires a non-empty tasks array")
    tasks = [_parse_task(item if isinstance(item, dict) else {}, idx) for idx, item in enumerate(tasks_raw)]
    constraints = _parse_constraints(payload.get("constraints", {}))
    weights = _parse_weights(payload.get("weights"))
    provider_options = payload.get("provider_options", {})
    if provider_options is None:
        provider_options = {}
    if not isinstance(provider_options, dict):
        raise ValueError("provider_options must be an object")
    return {
        "tasks": tasks,
        "constraints": constraints,
        "weights": weights,
        "provider_options": provider_options,
        "metadata": payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {},
        "raw_payload": payload,
    }


def _normalize_retry_budget(value: Any, default: int = 0) -> int:
    return max(0, _coerce_int(value, default))


def _normalize_timeout_budget(value: Any, default: int = 300) -> int:
    return max(1, _coerce_int(value, default))


def _backend_to_mode(requested_mode: str, backend: str) -> str:
    if backend == "classical-baseline":
        return "classical"
    return requested_mode


def _normalize_provider_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return list(SUPPORTED_PROVIDERS)
    providers: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in str(raw or "").split(","):
            candidate = part.strip()
            if not candidate:
                continue
            normalized = _normalize_provider(candidate)
            if normalized in seen:
                continue
            providers.append(normalized)
            seen.add(normalized)
    return providers or list(SUPPORTED_PROVIDERS)


def _normalize_text_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        for part in str(raw or "").split(","):
            clean = part.strip()
            if not clean or clean in seen:
                continue
            items.append(clean)
            seen.add(clean)
    return items


def _list_run_records(root: Path) -> list[dict[str, Any]]:
    runs_root = _resolve_output_path(root, DEFAULT_RUN_STORE_DIR)
    if not runs_root.exists():
        return []
    records: list[dict[str, Any]] = []
    for record_path in sorted(runs_root.glob("*/run_record.json")):
        try:
            payload = _load_json(record_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        payload["run_id"] = str(payload.get("run_id", record_path.parent.name))
        payload["run_dir"] = str(record_path.parent.resolve())
        payload["run_record_path"] = str(record_path.resolve())
        records.append(payload)
    return records


def _list_matrix_records(root: Path) -> list[dict[str, Any]]:
    matrix_root = _resolve_output_path(root, DEFAULT_MATRIX_STORE_DIR)
    if not matrix_root.exists():
        return []
    records: list[dict[str, Any]] = []
    for record_path in sorted(matrix_root.glob("*/matrix_record.json")):
        try:
            payload = _load_json(record_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        payload["matrix_id"] = str(payload.get("matrix_id", record_path.parent.name))
        payload["matrix_dir"] = str(record_path.parent.resolve())
        payload["matrix_record_path"] = str(record_path.resolve())
        records.append(payload)
    return records


def _render_quantum_dashboard_html(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    recent_runs = list(payload.get("recent_runs", []))
    matrix_runs = list(payload.get("matrix_runs", []))
    status_counts = dict(payload.get("status_counts", {}))
    provider_counts = dict(payload.get("provider_counts", {}))
    backend_counts = dict(payload.get("executed_backend_counts", {}))
    task_counts = dict(payload.get("selected_task_frequency", {}))

    def _render_key_value_rows(items: dict[str, Any], *, empty_label: str = "none") -> str:
        if not items:
            return f"<tr><td colspan='2'>{html_escape(empty_label)}</td></tr>"
        rows: list[str] = []
        for key, value in items.items():
            rows.append(
                "<tr>"
                f"<td>{html_escape(str(key))}</td>"
                f"<td>{html_escape(str(value))}</td>"
                "</tr>"
            )
        return "".join(rows)

    def _render_recent_runs(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='8'>No runs captured yet.</td></tr>"
        rendered: list[str] = []
        for row in rows:
            rendered.append(
                "<tr>"
                f"<td>{html_escape(str(row.get('run_id', '')))}</td>"
                f"<td>{html_escape(str(row.get('status', '')))}</td>"
                f"<td>{html_escape(str(row.get('provider', '')))}</td>"
                f"<td>{html_escape(str(row.get('executed_backend', '')))}</td>"
                f"<td>{html_escape(str(row.get('solver_mode', '')))}</td>"
                f"<td>{html_escape(', '.join(row.get('selected_task_ids', [])))}</td>"
                f"<td>{html_escape(str(row.get('objective_score', '')))}</td>"
                f"<td>{html_escape(str(row.get('completed_at_utc', '') or row.get('started_at_utc', '')))}</td>"
                "</tr>"
            )
        return "".join(rendered)

    def _render_matrix_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "<tr><td colspan='5'>No provider matrices captured yet.</td></tr>"
        rendered: list[str] = []
        for row in rows:
            rendered.append(
                "<tr>"
                f"<td>{html_escape(str(row.get('matrix_id', '')))}</td>"
                f"<td>{html_escape(str(row.get('status', '')))}</td>"
                f"<td>{html_escape(', '.join(row.get('providers', [])))}</td>"
                f"<td>{html_escape(str(row.get('recommended_provider', '')))}</td>"
                f"<td>{html_escape(str(row.get('completed_at_utc', '') or row.get('created_at_utc', '')))}</td>"
                "</tr>"
            )
        return "".join(rendered)

    return (
        "<!doctype html>"
        "<html lang='en'><head><meta charset='utf-8'>"
        "<title>CCBS Quantum Dashboard</title>"
        "<style>"
        "body{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f4f6f8;color:#16202a;}"
        "h1,h2{margin:0 0 12px 0;}"
        ".meta{margin:0 0 24px 0;color:#425466;}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-bottom:24px;}"
        ".card{background:#fff;border:1px solid #d9e2ec;border-radius:10px;padding:16px;box-shadow:0 1px 2px rgba(15,23,42,.04);}"
        "table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #d9e2ec;border-radius:10px;overflow:hidden;}"
        "th,td{padding:10px 12px;border-bottom:1px solid #e5edf5;text-align:left;font-size:14px;vertical-align:top;}"
        "th{background:#eef4fa;font-weight:600;}"
        "tr:last-child td{border-bottom:none;}"
        ".section{margin-bottom:24px;}"
        "</style></head><body>"
        "<h1>CCBS Quantum Dashboard</h1>"
        f"<p class='meta'>Generated at {html_escape(str(payload.get('generated_at_utc', '')))}</p>"
        "<div class='grid'>"
        "<div class='card'><h2>Summary</h2>"
        f"<p>Total runs: <strong>{html_escape(str(summary.get('run_count', 0)))}</strong></p>"
        f"<p>Completed: <strong>{html_escape(str(summary.get('completed_run_count', 0)))}</strong></p>"
        f"<p>Failed: <strong>{html_escape(str(summary.get('failed_run_count', 0)))}</strong></p>"
        f"<p>Fallbacks: <strong>{html_escape(str(summary.get('fallback_used_count', 0)))}</strong></p>"
        "</div>"
        "<div class='card'><h2>Status Counts</h2><table><tbody>"
        f"{_render_key_value_rows(status_counts)}"
        "</tbody></table></div>"
        "<div class='card'><h2>Providers</h2><table><tbody>"
        f"{_render_key_value_rows(provider_counts)}"
        "</tbody></table></div>"
        "<div class='card'><h2>Executed Backends</h2><table><tbody>"
        f"{_render_key_value_rows(backend_counts)}"
        "</tbody></table></div>"
        "</div>"
        "<div class='section'><h2>Recent Runs</h2><table><thead><tr>"
        "<th>Run ID</th><th>Status</th><th>Provider</th><th>Executed Backend</th>"
        "<th>Solver Mode</th><th>Selected Tasks</th><th>Objective</th><th>Completed</th>"
        "</tr></thead><tbody>"
        f"{_render_recent_runs(recent_runs)}"
        "</tbody></table></div>"
        "<div class='section'><h2>Provider Matrices</h2><table><thead><tr>"
        "<th>Matrix ID</th><th>Status</th><th>Providers</th><th>Recommended</th><th>Completed</th>"
        "</tr></thead><tbody>"
        f"{_render_matrix_rows(matrix_runs)}"
        "</tbody></table></div>"
        "<div class='section'><h2>Selected Task Frequency</h2><table><thead><tr>"
        "<th>Task ID</th><th>Selections</th>"
        "</tr></thead><tbody>"
        f"{_render_key_value_rows(task_counts, empty_label='No selected tasks recorded yet.')}"
        "</tbody></table></div>"
        "</body></html>\n"
    )


def build_quantum_preflight(root: Path, venv_name: str = DEFAULT_VENV_NAME) -> dict[str, Any]:
    venv_root = (root / venv_name).resolve()
    venv_exists = venv_root.exists()
    venv_python = _detect_venv_python(venv_root)
    token_keys = _collect_present_env(TOKEN_ENV_KEYS)
    instance_keys = _collect_present_env(INSTANCE_ENV_KEYS)

    packages = {
        "qiskit": _has_module("qiskit"),
        "qiskit_ibm_runtime": _has_module("qiskit_ibm_runtime"),
        "jupyterlab": _has_module("jupyterlab"),
    }

    local_simulator_ready = bool(packages["qiskit"])
    cloud_runtime_ready = bool(packages["qiskit_ibm_runtime"] and token_keys)
    next_steps: list[str] = []

    if not venv_exists:
        next_steps.append(f"Create a dedicated virtual environment: python -m venv {venv_name}")
    if not packages["qiskit"]:
        next_steps.append("Install core SDK: pip install qiskit")
    if not packages["qiskit_ibm_runtime"]:
        next_steps.append("Install IBM runtime client: pip install qiskit-ibm-runtime")
    if not packages["jupyterlab"]:
        next_steps.append("Install notebook tooling: pip install jupyterlab")
    if not token_keys:
        next_steps.append(
            "Set an IBM token in the environment (QISKIT_IBM_TOKEN or IBM_QUANTUM_TOKEN) before cloud runs."
        )
    if packages["qiskit_ibm_runtime"] and not instance_keys:
        next_steps.append(
            "Optional but recommended: set QISKIT_IBM_INSTANCE (or IBM_QUANTUM_INSTANCE) for explicit instance routing."
        )

    return {
        "workspace_root": str(root),
        "platform": platform.platform(),
        "python_executable": str(Path(sys.executable)),
        "venv": {
            "name": venv_name,
            "path": str(venv_root),
            "exists": venv_exists,
            "python": str(venv_python) if venv_python else "",
        },
        "packages": packages,
        "environment": {
            "token_keys_present": token_keys,
            "instance_keys_present": instance_keys,
        },
        "local_simulator_ready": local_simulator_ready,
        "cloud_runtime_ready": cloud_runtime_ready,
        "next_steps": next_steps,
    }


def _quantum_readme_text() -> str:
    return (
        "# CCBS Quantum Foundation\n\n"
        "This folder is the minimal, isolated quantum lane for CCBS.\n\n"
        "## Quick Start\n\n"
        "1. Create and activate a dedicated venv (`.venv-quantum`).\n"
        "2. Install `requirements-quantum.txt`.\n"
        "3. Set `QISKIT_IBM_TOKEN` (and optionally `QISKIT_IBM_INSTANCE`).\n"
        "4. Run a local sanity check: `PYTHONPATH=src python3 -m ccbs_app.cli quantum run-local --json`.\n\n"
        "Use this as a modular capability; do not block core CCBS submission work on quantum-only features.\n"
    )


def _requirements_text() -> str:
    return "qiskit>=1.2.0\nqiskit-ibm-runtime>=0.31.0\njupyterlab>=4.2.0\n"


def _runtime_service_text() -> str:
    return (
        "from __future__ import annotations\n\n"
        "import os\n"
        "from typing import Optional\n\n"
        "from qiskit_ibm_runtime import QiskitRuntimeService\n\n\n"
        "def create_runtime_service(\n"
        "    token: Optional[str] = None,\n"
        "    instance: Optional[str] = None,\n"
        ") -> QiskitRuntimeService:\n"
        "    \"\"\"Create a QiskitRuntimeService using env vars or explicit values.\n\n"
        "    Environment fallbacks:\n"
        "    - token: QISKIT_IBM_TOKEN, IBM_QUANTUM_TOKEN\n"
        "    - instance: QISKIT_IBM_INSTANCE, IBM_QUANTUM_INSTANCE\n"
        "    \"\"\"\n"
        "    resolved_token = token or os.getenv(\"QISKIT_IBM_TOKEN\") or os.getenv(\"IBM_QUANTUM_TOKEN\")\n"
        "    if not resolved_token:\n"
        "        raise ValueError(\"Missing IBM token. Set QISKIT_IBM_TOKEN or IBM_QUANTUM_TOKEN.\")\n\n"
        "    resolved_instance = (\n"
        "        instance or os.getenv(\"QISKIT_IBM_INSTANCE\") or os.getenv(\"IBM_QUANTUM_INSTANCE\")\n"
        "    )\n"
        "    kwargs = {\"channel\": \"ibm_quantum_platform\", \"token\": resolved_token}\n"
        "    if resolved_instance:\n"
        "        kwargs[\"instance\"] = resolved_instance\n"
        "    return QiskitRuntimeService(**kwargs)\n"
    )


def _hello_qpu_text() -> str:
    return (
        "from __future__ import annotations\n\n"
        "import json\n\n"
        "from qiskit import QuantumCircuit\n"
        "from qiskit.quantum_info import Statevector\n\n\n"
        "def run_local_bell_demo(shots: int = 1024) -> dict:\n"
        "    circuit = QuantumCircuit(2)\n"
        "    circuit.h(0)\n"
        "    circuit.cx(0, 1)\n"
        "    state = Statevector.from_instruction(circuit)\n"
        "    probabilities = {k: float(v) for k, v in state.probabilities_dict().items() if float(v) > 0}\n"
        "    counts = {k: int(round(v * shots)) for k, v in probabilities.items()}\n"
        "    return {\n"
        "        \"shots\": shots,\n"
        "        \"probabilities\": probabilities,\n"
        "        \"counts\": counts,\n"
        "        \"notes\": \"Local statevector sanity check only; no cloud hardware was used.\",\n"
        "    }\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    print(json.dumps(run_local_bell_demo(), indent=2))\n"
    )


def _env_template_text() -> str:
    return (
        "# Copy to your shell profile or .env file (do not commit real secrets)\n"
        "QISKIT_IBM_TOKEN=<replace_with_ibm_quantum_platform_api_key>\n"
        "QISKIT_IBM_INSTANCE=<optional_instance_crn>\n"
    )


def write_quantum_scaffold(root: Path, output_dir: Path, force: bool = False) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    templates = {
        "README_QUANTUM.md": _quantum_readme_text(),
        "requirements-quantum.txt": _requirements_text(),
        "runtime_service.py": _runtime_service_text(),
        "hello_qpu.py": _hello_qpu_text(),
        ".env.quantum.template": _env_template_text(),
    }
    written_files: list[str] = []
    kept_files: list[str] = []

    for rel_path, text in templates.items():
        path = output_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not force:
            kept_files.append(str(path))
            continue
        path.write_text(text, encoding="utf-8")
        written_files.append(str(path))

    return {
        "output_dir": str(output_dir),
        "written_files": written_files,
        "kept_files": kept_files,
    }


def _probs_to_counts(probabilities: dict[str, float], shots: int) -> dict[str, int]:
    items = sorted(probabilities.items(), key=lambda item: item[0])
    if not items:
        return {}
    counts: dict[str, int] = {}
    allocated = 0
    for index, (state, probability) in enumerate(items):
        if index == len(items) - 1:
            count = shots - allocated
        else:
            count = int(round(float(probability) * shots))
            count = max(0, min(shots - allocated, count))
        counts[state] = count
        allocated += count
    return counts


def run_local_quantum_demo(shots: int = 1024) -> dict[str, Any]:
    if shots <= 0:
        raise ValueError("shots must be > 0")
    try:
        from qiskit import QuantumCircuit
        from qiskit.quantum_info import Statevector
    except Exception as exc:  # noqa: BLE001
        raise QuantumDependencyError(
            "qiskit is required for local quantum demo. Install it in your quantum venv with: pip install qiskit"
        ) from exc

    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    state = Statevector.from_instruction(circuit)
    probabilities_raw = state.probabilities_dict()
    probabilities = {str(k): float(v) for k, v in probabilities_raw.items() if float(v) > 0}
    counts = _probs_to_counts(probabilities, shots=shots)

    p00 = float(probabilities.get("00", 0.0))
    p11 = float(probabilities.get("11", 0.0))
    leakage = float(sum(v for k, v in probabilities.items() if k not in {"00", "11"}))
    bell_like = abs(p00 - 0.5) <= 0.05 and abs(p11 - 0.5) <= 0.05 and leakage <= 0.05

    return {
        "scenario": "bell_state_local_simulator",
        "shots": shots,
        "probabilities": probabilities,
        "counts": counts,
        "bell_state_check": {
            "p00": p00,
            "p11": p11,
            "leakage": leakage,
            "passes": bell_like,
        },
    }


def run_quantum_batch(
    *,
    root: Path,
    batch_path: Path,
    provider: str,
    mode: str,
    max_retries: int,
    timeout_budget_seconds: int,
    failover_enabled: bool,
    dry_run: bool = False,
    run_id_override: str | None = None,
) -> dict[str, Any]:
    provider_normalized = _normalize_provider(provider)
    mode_normalized = _normalize_mode(mode)
    loaded = _load_batch(batch_path)
    provider_options = dict(loaded.get("provider_options", {}))
    batch_payload = loaded.get("raw_payload", {})
    batch_metadata = loaded.get("metadata", {})
    batch_sha256 = _canonical_json_digest(batch_payload)

    retry_budget = _normalize_retry_budget(
        max_retries if max_retries >= 0 else provider_options.get("max_retries"),
        default=0,
    )
    timeout_budget = _normalize_timeout_budget(
        timeout_budget_seconds if timeout_budget_seconds > 0 else provider_options.get("timeout_budget_seconds"),
        default=300,
    )
    failover = failover_enabled
    if "failover_enabled" in provider_options:
        failover = _coerce_bool(provider_options.get("failover_enabled"), failover_enabled)

    backend_chain = _provider_chain(provider_normalized, failover)
    run_id = str(run_id_override or "").strip() or str(provider_options.get("run_id", "")).strip() or f"qr_{uuid4().hex[:12]}"
    run_dir = _run_path(root, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "input_batch.json", batch_payload)

    forced_failures = _coerce_string_set(provider_options.get("force_fail_backends", []))
    command_matrix = [
        {
            "backend": backend,
            "mode": _backend_to_mode(mode_normalized, backend),
            "max_retries": retry_budget,
            "timeout_budget_seconds": timeout_budget,
        }
        for backend in backend_chain
    ]

    if dry_run:
        payload = {
            "run_id": run_id,
            "status": "validated",
            "provider": provider_normalized,
            "mode": mode_normalized,
            "backend_chain": backend_chain,
            "command_matrix": command_matrix,
            "task_count": len(loaded["tasks"]),
            "batch_metadata": batch_metadata,
            "batch_sha256": batch_sha256,
            "retry_policy": {
                "max_retries": retry_budget,
                "timeout_budget_seconds": timeout_budget,
                "failover_enabled": failover,
            },
            "provider_options": provider_options,
            "batch_path": str(batch_path),
            "files": {
                "run_record": str(run_dir / "run_record.json"),
                "input_batch": str(run_dir / "input_batch.json"),
            },
            "dry_run": True,
            "created_at_utc": _now_utc_iso(),
        }
        _write_json(run_dir / "run_record.json", payload)
        return payload

    attempts: list[dict[str, Any]] = []
    final_error = ""
    constraints = loaded["constraints"]
    weights = loaded["weights"]
    tasks = loaded["tasks"]
    started = _now_utc_iso()

    for backend_index, backend in enumerate(backend_chain):
        next_backend = backend_chain[backend_index + 1] if backend_index + 1 < len(backend_chain) else "classical-baseline"
        backend_mode = _backend_to_mode(mode_normalized, backend)
        for attempt_index in range(retry_budget + 1):
            attempt_record: dict[str, Any] = {
                "backend": backend,
                "attempt": attempt_index + 1,
                "mode": backend_mode,
                "started_at_utc": _now_utc_iso(),
            }
            try:
                if backend in forced_failures:
                    raise RuntimeError(f"forced_failure:{backend}")
                evidence = quantum_decision(
                    tasks,
                    constraints=constraints,
                    weights=weights,
                    mode=backend_mode,
                    primary_backend=backend_chain[0],
                    fallback_backend=next_backend,
                    manifest_json_path=str(run_dir / "decision_manifest.json"),
                    manifest_markdown_path=str(run_dir / "decision_manifest.md"),
                )
                attempt_record["status"] = "ok"
                attempt_record["completed_at_utc"] = _now_utc_iso()
                attempts.append(attempt_record)
                payload = {
                    "run_id": run_id,
                    "status": "completed",
                    "provider": provider_normalized,
                    "mode": mode_normalized,
                    "backend_chain": backend_chain,
                    "executed_backend": evidence.executed_backend,
                    "primary_backend": evidence.primary_backend,
                    "fallback_used": bool(evidence.fallback_used),
                    "fallback_reason": evidence.fallback_reason,
                    "solver_mode": evidence.solver_mode,
                    "selected_task_ids": list(evidence.selected_task_ids),
                    "constraint_report": dict(evidence.constraint_report),
                    "objective_score": evidence.objective_score,
                    "runtime_ms": evidence.runtime_ms,
                    "task_count": len(tasks),
                    "batch_metadata": batch_metadata,
                    "batch_sha256": batch_sha256,
                    "retry_policy": {
                        "max_retries": retry_budget,
                        "timeout_budget_seconds": timeout_budget,
                        "failover_enabled": failover,
                    },
                    "command_matrix": command_matrix,
                    "provider_options": provider_options,
                    "attempts": attempts,
                    "batch_path": str(batch_path),
                    "run_dir": str(run_dir),
                    "files": {
                        "run_record": str(run_dir / "run_record.json"),
                        "input_batch": str(run_dir / "input_batch.json"),
                        "decision_manifest_json": str(run_dir / "decision_manifest.json"),
                        "decision_manifest_markdown": str(run_dir / "decision_manifest.md"),
                    },
                    "dry_run": False,
                    "started_at_utc": started,
                    "completed_at_utc": _now_utc_iso(),
                }
                _write_json(run_dir / "run_record.json", payload)
                return payload
            except Exception as exc:  # noqa: BLE001
                final_error = str(exc)
                attempt_record["status"] = "failed"
                attempt_record["error"] = final_error
                attempt_record["completed_at_utc"] = _now_utc_iso()
                attempts.append(attempt_record)
                if attempt_index < retry_budget:
                    continue
                break

    payload = {
        "run_id": run_id,
        "status": "failed",
        "provider": provider_normalized,
        "mode": mode_normalized,
        "backend_chain": backend_chain,
        "retry_policy": {
            "max_retries": retry_budget,
            "timeout_budget_seconds": timeout_budget,
            "failover_enabled": failover,
        },
        "task_count": len(tasks),
        "batch_metadata": batch_metadata,
        "batch_sha256": batch_sha256,
        "command_matrix": command_matrix,
        "provider_options": provider_options,
        "attempts": attempts,
        "error": final_error or "all_backends_failed",
        "batch_path": str(batch_path),
        "run_dir": str(run_dir),
        "files": {
            "run_record": str(run_dir / "run_record.json"),
            "input_batch": str(run_dir / "input_batch.json"),
            "decision_manifest_json": str(run_dir / "decision_manifest.json"),
            "decision_manifest_markdown": str(run_dir / "decision_manifest.md"),
        },
        "dry_run": False,
        "started_at_utc": started,
        "completed_at_utc": _now_utc_iso(),
    }
    _write_json(run_dir / "run_record.json", payload)
    return payload


def monitor_quantum_run(*, root: Path, run_id: str) -> dict[str, Any]:
    run_dir = _run_path(root, run_id)
    run_path = run_dir / "run_record.json"
    if not run_path.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    payload = _load_json(run_path)
    payload["run_dir"] = str(run_dir)
    payload["run_id"] = str(payload.get("run_id", run_id))
    return payload


def collect_quantum_run(*, root: Path, run_id: str, output_path: Path) -> dict[str, Any]:
    run_payload = monitor_quantum_run(root=root, run_id=run_id)
    run_dir = _run_path(root, run_id)
    manifest_path = run_dir / "decision_manifest.json"
    markdown_path = run_dir / "decision_manifest.md"
    batch_copy_path = run_dir / "input_batch.json"
    manifest_payload: dict[str, Any] = {}
    batch_payload: dict[str, Any] = {}
    if manifest_path.exists():
        manifest_payload = _load_json(manifest_path)
    if batch_copy_path.exists():
        batch_payload = _load_json(batch_copy_path)

    bundle = {
        "run": run_payload,
        "manifest": manifest_payload,
        "batch": batch_payload,
        "summary": {
            "run_id": str(run_payload.get("run_id", run_id)),
            "status": run_payload.get("status"),
            "provider": run_payload.get("provider"),
            "executed_backend": run_payload.get("executed_backend"),
            "selected_task_ids": list(run_payload.get("selected_task_ids", [])),
            "task_count": run_payload.get("task_count"),
            "fallback_used": run_payload.get("fallback_used"),
            "objective_score": run_payload.get("objective_score"),
        },
        "files": {
            "run_record": str(run_dir / "run_record.json"),
            "input_batch_json": str(batch_copy_path) if batch_copy_path.exists() else "",
            "decision_manifest_json": str(manifest_path) if manifest_path.exists() else "",
            "decision_manifest_markdown": str(markdown_path) if markdown_path.exists() else "",
        },
        "collected_at_utc": _now_utc_iso(),
    }
    target = output_path
    if not target.is_absolute():
        target = (root / target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, bundle)
    return {
        "run_id": run_id,
        "status": run_payload.get("status"),
        "output_path": str(target),
        "manifest_present": manifest_path.exists(),
        "collected_at_utc": bundle["collected_at_utc"],
    }


def run_quantum_matrix(
    *,
    root: Path,
    batch_path: Path,
    providers: list[str] | tuple[str, ...] | None,
    mode: str,
    max_retries: int,
    timeout_budget_seconds: int,
    failover_enabled: bool,
    dry_run: bool = False,
    matrix_id: str = "",
) -> dict[str, Any]:
    provider_list = _normalize_provider_list(providers)
    matrix_identifier = str(matrix_id or "").strip() or f"qm_{uuid4().hex[:12]}"
    matrix_dir = _matrix_path(root, matrix_identifier)
    matrix_dir.mkdir(parents=True, exist_ok=True)
    started = _now_utc_iso()
    runs: list[dict[str, Any]] = []

    for provider in provider_list:
        run_payload = run_quantum_batch(
            root=root,
            batch_path=batch_path,
            provider=provider,
            mode=mode,
            max_retries=max_retries,
            timeout_budget_seconds=timeout_budget_seconds,
            failover_enabled=failover_enabled,
            dry_run=dry_run,
            run_id_override=f"{matrix_identifier}_{provider}",
        )
        runs.append(
            {
                "provider": provider,
                "run_id": run_payload.get("run_id"),
                "status": run_payload.get("status"),
                "executed_backend": run_payload.get("executed_backend"),
                "solver_mode": run_payload.get("solver_mode"),
                "objective_score": run_payload.get("objective_score"),
                "runtime_ms": run_payload.get("runtime_ms"),
                "fallback_used": run_payload.get("fallback_used"),
                "selected_task_ids": list(run_payload.get("selected_task_ids", [])),
                "batch_metadata": dict(run_payload.get("batch_metadata", {})),
                "completed_at_utc": run_payload.get("completed_at_utc"),
            }
        )

    success_status = "validated" if dry_run else "completed"
    successful_runs = [row for row in runs if row.get("status") == success_status]
    if dry_run:
        matrix_status = "validated"
    elif len(successful_runs) == len(runs):
        matrix_status = "completed"
    elif successful_runs:
        matrix_status = "completed_with_failures"
    else:
        matrix_status = "failed"

    recommended_provider = ""
    recommended_run_id = ""
    if successful_runs and not dry_run:
        scored = sorted(
            successful_runs,
            key=lambda row: (
                -(float(row.get("objective_score")) if row.get("objective_score") is not None else float("-inf")),
                float(row.get("runtime_ms")) if row.get("runtime_ms") is not None else float("inf"),
                str(row.get("provider", "")),
            ),
        )
        recommended_provider = str(scored[0].get("provider", ""))
        recommended_run_id = str(scored[0].get("run_id", ""))

    payload = {
        "matrix_id": matrix_identifier,
        "status": matrix_status,
        "providers": provider_list,
        "mode": _normalize_mode(mode),
        "batch_path": str(batch_path),
        "matrix_dir": str(matrix_dir),
        "runs": runs,
        "success_count": len(successful_runs),
        "failure_count": len([row for row in runs if row.get("status") == "failed"]),
        "recommended_provider": recommended_provider,
        "recommended_run_id": recommended_run_id,
        "dry_run": dry_run,
        "created_at_utc": started,
        "completed_at_utc": _now_utc_iso(),
    }
    _write_json(matrix_dir / "matrix_record.json", payload)
    return payload


def build_quantum_dashboard(
    *,
    root: Path,
    output_html_path: Path,
    output_json_path: Path,
    run_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    requested_run_ids = set(_normalize_text_list(run_ids))
    run_records = _list_run_records(root)
    if requested_run_ids:
        run_records = [row for row in run_records if str(row.get("run_id", "")) in requested_run_ids]
    matrix_records = _list_matrix_records(root)
    if requested_run_ids:
        matrix_records = [
            row
            for row in matrix_records
            if requested_run_ids.intersection({str(item.get("run_id", "")) for item in row.get("runs", [])})
        ]

    status_counts = Counter(str(row.get("status", "unknown")) for row in run_records)
    provider_counts = Counter(str(row.get("provider", "unknown")) for row in run_records)
    backend_counts = Counter(str(row.get("executed_backend", "none")) for row in run_records)
    selected_task_counts = Counter()
    fallback_used_count = 0
    runtime_values: list[float] = []
    for row in run_records:
        if row.get("fallback_used"):
            fallback_used_count += 1
        if row.get("runtime_ms") is not None:
            runtime_values.append(float(row["runtime_ms"]))
        for task_id in row.get("selected_task_ids", []):
            selected_task_counts[str(task_id)] += 1

    sorted_runs = sorted(
        run_records,
        key=lambda row: str(row.get("completed_at_utc") or row.get("started_at_utc") or row.get("created_at_utc") or ""),
        reverse=True,
    )
    recent_runs = [
        {
            "run_id": str(row.get("run_id", "")),
            "status": str(row.get("status", "")),
            "provider": str(row.get("provider", "")),
            "executed_backend": str(row.get("executed_backend", "")),
            "solver_mode": str(row.get("solver_mode", "")),
            "selected_task_ids": list(row.get("selected_task_ids", [])),
            "objective_score": row.get("objective_score"),
            "runtime_ms": row.get("runtime_ms"),
            "completed_at_utc": row.get("completed_at_utc"),
            "started_at_utc": row.get("started_at_utc"),
            "batch_name": str(row.get("batch_metadata", {}).get("name", "")),
            "fallback_used": bool(row.get("fallback_used")),
            "error": str(row.get("error", "")),
        }
        for row in sorted_runs[:20]
    ]
    matrix_runs = [
        {
            "matrix_id": str(row.get("matrix_id", "")),
            "status": str(row.get("status", "")),
            "providers": list(row.get("providers", [])),
            "recommended_provider": str(row.get("recommended_provider", "")),
            "completed_at_utc": row.get("completed_at_utc"),
            "created_at_utc": row.get("created_at_utc"),
        }
        for row in sorted(
            matrix_records,
            key=lambda row: str(row.get("completed_at_utc") or row.get("created_at_utc") or ""),
            reverse=True,
        )[:20]
    ]

    payload = {
        "generated_at_utc": _now_utc_iso(),
        "filters": {"run_ids": sorted(requested_run_ids)},
        "summary": {
            "run_count": len(run_records),
            "matrix_count": len(matrix_records),
            "completed_run_count": status_counts.get("completed", 0),
            "failed_run_count": status_counts.get("failed", 0),
            "validated_run_count": status_counts.get("validated", 0),
            "pending_run_count": status_counts.get("pending", 0),
            "fallback_used_count": fallback_used_count,
            "average_runtime_ms": round(sum(runtime_values) / len(runtime_values), 3) if runtime_values else None,
        },
        "status_counts": dict(status_counts),
        "provider_counts": dict(provider_counts),
        "executed_backend_counts": dict(backend_counts),
        "selected_task_frequency": dict(sorted(selected_task_counts.items(), key=lambda item: (-item[1], item[0]))),
        "recent_runs": recent_runs,
        "matrix_runs": matrix_runs,
    }
    output_html_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_html_path.write_text(_render_quantum_dashboard_html(payload), encoding="utf-8")
    _write_json(output_json_path, payload)
    payload["output_html_path"] = str(output_html_path)
    payload["output_json_path"] = str(output_json_path)
    return payload


def _cmd_quantum_preflight(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        payload = build_quantum_preflight(root=root, venv_name=str(args.venv_name))
    except (RepoError, OSError, RuntimeError, ValueError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    print("Quantum preflight:")
    print(f"- workspace_root: {payload['workspace_root']}")
    print(f"- venv: {payload['venv']['path']} (exists={payload['venv']['exists']})")
    if payload["venv"]["python"]:
        print(f"- venv_python: {payload['venv']['python']}")
    print(
        "- packages: "
        + ", ".join(f"{name}={bool(ok)}" for name, ok in payload["packages"].items())
    )
    print(
        f"- token_env_present: {', '.join(payload['environment']['token_keys_present']) or 'none'}"
    )
    print(
        f"- instance_env_present: {', '.join(payload['environment']['instance_keys_present']) or 'none'}"
    )
    print(f"- local_simulator_ready: {payload['local_simulator_ready']}")
    print(f"- cloud_runtime_ready: {payload['cloud_runtime_ready']}")
    if payload["next_steps"]:
        print("Next steps:")
        for step in payload["next_steps"]:
            print(f"- {step}")
    return 0


def _cmd_quantum_scaffold(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        output_dir = _resolve_output_path(root, str(args.output_dir))
        payload = write_quantum_scaffold(root=root, output_dir=output_dir, force=bool(args.force))
    except (RepoError, OSError, RuntimeError, ValueError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    print(f"Quantum scaffold directory: {payload['output_dir']}")
    if payload["written_files"]:
        print("Written:")
        for item in payload["written_files"]:
            print(f"- {item}")
    if payload["kept_files"]:
        print("Kept (already existed):")
        for item in payload["kept_files"]:
            print(f"- {item}")
    return 0


def _cmd_quantum_run_local(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        payload = run_local_quantum_demo(shots=max(1, int(args.shots)))
        output_path = str(getattr(args, "output", "") or "").strip()
        if output_path:
            target = _resolve_output_path(root, output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            payload["output_path"] = str(target)
    except QuantumDependencyError as exc:
        print(f"ERROR: {exc}")
        return 2
    except (RepoError, OSError, RuntimeError, ValueError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    print("Quantum local simulator run:")
    print(f"- shots: {payload['shots']}")
    print(
        f"- p00={payload['bell_state_check']['p00']:.4f} "
        f"p11={payload['bell_state_check']['p11']:.4f} "
        f"leakage={payload['bell_state_check']['leakage']:.4f}"
    )
    print(f"- bell_state_check_passes: {payload['bell_state_check']['passes']}")
    if "output_path" in payload:
        print(f"- output_path: {payload['output_path']}")
    return 0


def _cmd_quantum_run(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        batch_path = _resolve_output_path(root, str(args.batch))
        if not batch_path.exists():
            raise FileNotFoundError(f"batch file not found: {batch_path}")
        payload = run_quantum_batch(
            root=root,
            batch_path=batch_path,
            provider=str(args.provider),
            mode=str(args.mode),
            max_retries=_normalize_retry_budget(args.max_retries, 0),
            timeout_budget_seconds=_normalize_timeout_budget(args.timeout_budget, 300),
            failover_enabled=bool(args.failover),
            dry_run=bool(args.dry_run),
        )
    except (RepoError, OSError, RuntimeError, ValueError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    print("Quantum run:")
    print(f"- run_id: {payload.get('run_id', '')}")
    print(f"- status: {payload.get('status', '')}")
    print(f"- provider: {payload.get('provider', '')}")
    print(f"- mode: {payload.get('mode', '')}")
    print(f"- backend_chain: {', '.join(payload.get('backend_chain', []))}")
    if payload.get("solver_mode"):
        print(f"- solver_mode: {payload['solver_mode']}")
    if payload.get("executed_backend"):
        print(f"- executed_backend: {payload['executed_backend']}")
    if payload.get("fallback_used") is not None:
        print(f"- fallback_used: {payload.get('fallback_used')}")
    if payload.get("fallback_reason"):
        print(f"- fallback_reason: {payload['fallback_reason']}")
    if payload.get("selected_task_ids"):
        print(f"- selected_task_ids: {', '.join(payload['selected_task_ids'])}")
    if payload.get("error"):
        print(f"- error: {payload['error']}")
    return 0


def _cmd_quantum_matrix(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        batch_path = _resolve_output_path(root, str(args.batch))
        if not batch_path.exists():
            raise FileNotFoundError(f"batch file not found: {batch_path}")
        payload = run_quantum_matrix(
            root=root,
            batch_path=batch_path,
            providers=_normalize_provider_list(list(getattr(args, "providers", []) or [])),
            mode=str(args.mode),
            max_retries=_normalize_retry_budget(args.max_retries, 0),
            timeout_budget_seconds=_normalize_timeout_budget(args.timeout_budget, 300),
            failover_enabled=bool(args.failover),
            dry_run=bool(args.dry_run),
            matrix_id=str(getattr(args, "matrix_id", "") or ""),
        )
    except (RepoError, OSError, RuntimeError, ValueError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    print("Quantum provider matrix:")
    print(f"- matrix_id: {payload.get('matrix_id', '')}")
    print(f"- status: {payload.get('status', '')}")
    print(f"- providers: {', '.join(payload.get('providers', []))}")
    print(f"- success_count: {payload.get('success_count', 0)}")
    print(f"- failure_count: {payload.get('failure_count', 0)}")
    if payload.get("recommended_provider"):
        print(f"- recommended_provider: {payload['recommended_provider']}")
    print(f"- matrix_dir: {payload.get('matrix_dir', '')}")
    return 0


def _cmd_quantum_monitor(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        payload = monitor_quantum_run(root=root, run_id=str(args.run_id))
    except (RepoError, OSError, RuntimeError, ValueError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    print("Quantum monitor:")
    print(f"- run_id: {payload.get('run_id', '')}")
    print(f"- status: {payload.get('status', '')}")
    print(f"- provider: {payload.get('provider', '')}")
    print(f"- mode: {payload.get('mode', '')}")
    print(f"- run_dir: {payload.get('run_dir', '')}")
    if payload.get("error"):
        print(f"- error: {payload['error']}")
    return 0


def _cmd_quantum_collect(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        output_raw = str(getattr(args, "output", "") or "").strip()
        if not output_raw:
            output_path = _resolve_output_path(
                root,
                f"{DEFAULT_COLLECT_OUTPUT_DIR}/{str(args.run_id).strip()}_bundle.json",
            )
        else:
            output_path = _resolve_output_path(root, output_raw)
        payload = collect_quantum_run(root=root, run_id=str(args.run_id), output_path=output_path)
    except (RepoError, OSError, RuntimeError, ValueError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    print("Quantum collect:")
    print(f"- run_id: {payload.get('run_id', '')}")
    print(f"- status: {payload.get('status', '')}")
    print(f"- output_path: {payload.get('output_path', '')}")
    print(f"- manifest_present: {payload.get('manifest_present')}")
    return 0


def _cmd_quantum_dashboard(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        output_html_path = _resolve_output_path(root, str(args.output_html))
        output_json_path = _resolve_output_path(root, str(args.output_json))
        payload = build_quantum_dashboard(
            root=root,
            output_html_path=output_html_path,
            output_json_path=output_json_path,
            run_ids=_normalize_text_list(list(getattr(args, "run_ids", []) or [])),
        )
    except (RepoError, OSError, RuntimeError, ValueError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    print("Quantum dashboard:")
    print(f"- runs: {payload.get('summary', {}).get('run_count', 0)}")
    print(f"- matrices: {payload.get('summary', {}).get('matrix_count', 0)}")
    print(f"- completed: {payload.get('summary', {}).get('completed_run_count', 0)}")
    print(f"- failed: {payload.get('summary', {}).get('failed_run_count', 0)}")
    print(f"- output_html_path: {payload.get('output_html_path', '')}")
    print(f"- output_json_path: {payload.get('output_json_path', '')}")
    return 0


def add_quantum_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    quantum = sub.add_parser(
        "quantum",
        help="Quantum foundation setup and execution (preflight/scaffold/run/matrix/monitor/collect/dashboard)",
    )
    quantum_sub = quantum.add_subparsers(dest="quantum_cmd", required=True)

    preflight = quantum_sub.add_parser("preflight", help="Check quantum venv, packages, and env readiness")
    preflight.add_argument("--venv-name", default=DEFAULT_VENV_NAME, help="Quantum virtual environment directory name")
    preflight.add_argument("--json", action="store_true", help="Emit JSON output")
    preflight.set_defaults(func=_cmd_quantum_preflight)

    scaffold = quantum_sub.add_parser("scaffold", help="Write quantum starter files into the workspace")
    scaffold.add_argument("--output-dir", default=DEFAULT_SCAFFOLD_DIR, help="Output directory for quantum starter files")
    scaffold.add_argument("--force", action="store_true", help="Overwrite existing scaffold files")
    scaffold.add_argument("--json", action="store_true", help="Emit JSON output")
    scaffold.set_defaults(func=_cmd_quantum_scaffold)

    run_local = quantum_sub.add_parser("run-local", help="Run local Bell-state simulator and optionally write evidence")
    run_local.add_argument("--shots", type=int, default=1024, help="Number of simulated shots")
    run_local.add_argument(
        "--output",
        default=DEFAULT_LOCAL_OUTPUT,
        help="Output path for JSON evidence (empty string disables file output)",
    )
    run_local.add_argument("--json", action="store_true", help="Emit JSON output")
    run_local.set_defaults(func=_cmd_quantum_run_local)

    run = quantum_sub.add_parser(
        "run",
        help="Run one batch through provider-aware backend routing with bounded fallback",
    )
    run.add_argument("--provider", choices=SUPPORTED_PROVIDERS, required=True, help="Primary provider lane to start from")
    run.add_argument("--batch", required=True, help="Batch JSON path with tasks/constraints/weights/provider_options")
    run.add_argument("--mode", choices=SUPPORTED_MODES, default="auto", help="Solver mode")
    run.add_argument("--max-retries", type=int, default=0, help="Retry attempts per backend before failover")
    run.add_argument("--timeout-budget", type=int, default=300, help="Timeout budget in seconds (metadata contract)")
    run.add_argument(
        "--failover",
        dest="failover",
        action="store_true",
        default=True,
        help="Enable backend failover chain",
    )
    run.add_argument(
        "--no-failover",
        dest="failover",
        action="store_false",
        help="Disable backend failover chain",
    )
    run.add_argument("--dry-run", action="store_true", help="Validate batch and print command matrix without executing")
    run.add_argument("--json", action="store_true", help="Emit JSON output")
    run.set_defaults(func=_cmd_quantum_run)

    matrix = quantum_sub.add_parser(
        "matrix",
        help="Run one batch across multiple provider lanes and persist one matrix summary",
    )
    matrix.add_argument(
        "--provider",
        dest="providers",
        action="append",
        default=[],
        help="Provider lane to include; repeat or pass comma-separated values (default: azure,ibm)",
    )
    matrix.add_argument("--batch", required=True, help="Batch JSON path with tasks/constraints/weights/provider_options")
    matrix.add_argument("--mode", choices=SUPPORTED_MODES, default="auto", help="Solver mode")
    matrix.add_argument("--max-retries", type=int, default=0, help="Retry attempts per backend before failover")
    matrix.add_argument("--timeout-budget", type=int, default=300, help="Timeout budget in seconds (metadata contract)")
    matrix.add_argument(
        "--failover",
        dest="failover",
        action="store_true",
        default=True,
        help="Enable backend failover chain",
    )
    matrix.add_argument(
        "--no-failover",
        dest="failover",
        action="store_false",
        help="Disable backend failover chain",
    )
    matrix.add_argument("--matrix-id", default="", help="Optional stable matrix identifier")
    matrix.add_argument("--dry-run", action="store_true", help="Validate every provider lane without executing")
    matrix.add_argument("--json", action="store_true", help="Emit JSON output")
    matrix.set_defaults(func=_cmd_quantum_matrix)

    monitor = quantum_sub.add_parser(
        "monitor",
        help="Read one quantum run record from local run-store",
    )
    monitor.add_argument("--run-id", required=True, help="Run identifier")
    monitor.add_argument("--json", action="store_true", help="Emit JSON output")
    monitor.set_defaults(func=_cmd_quantum_monitor)

    collect = quantum_sub.add_parser(
        "collect",
        help="Collect one run into a portable evidence JSON bundle",
    )
    collect.add_argument("--run-id", required=True, help="Run identifier")
    collect.add_argument(
        "--output",
        default="",
        help="Output JSON path (default: dist/quantum/evidence/<run_id>_bundle.json)",
    )
    collect.add_argument("--json", action="store_true", help="Emit JSON output")
    collect.set_defaults(func=_cmd_quantum_collect)

    dashboard = quantum_sub.add_parser(
        "dashboard",
        help="Build HTML and JSON dashboard views from local quantum run-store records",
    )
    dashboard.add_argument(
        "--run-id",
        dest="run_ids",
        action="append",
        default=[],
        help="Limit the dashboard to specific run ids; repeat or pass comma-separated values",
    )
    dashboard.add_argument(
        "--output-html",
        default=DEFAULT_DASHBOARD_HTML,
        help="Output HTML path",
    )
    dashboard.add_argument(
        "--output-json",
        default=DEFAULT_DASHBOARD_JSON,
        help="Output JSON path",
    )
    dashboard.add_argument("--json", action="store_true", help="Emit JSON output")
    dashboard.set_defaults(func=_cmd_quantum_dashboard)
