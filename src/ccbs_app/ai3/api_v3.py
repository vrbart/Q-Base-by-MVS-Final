"""FastAPI route registration for ai3 first-class runtime APIs."""

from __future__ import annotations

import os
import re
import sqlite3
import shutil
import subprocess
import sys
import shlex
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..ai_model_catalog import discover_model_catalog
from ..ai_routing_policy import load_routing_policy
from ..multi_instance_agent import (
    discover_multi_instance_apps,
    get_multi_instance_runtime_summary,
    get_multi_instance_state,
    load_multi_instance_profile,
    optimize_multi_instance_bundle,
    route_message_to_lane,
    run_multi_instance_control_action,
    update_multi_instance_profile,
)
from ..capability_orchestrator import collect_capability_report, execute_capability_action
from .card_pack import resolve_card_deck, resolve_role_utility_mode, role_behavior
from .db import connect_runtime, runtime_db_path
from .chat_profile import (
    add_role_xp,
    get_chat_profile,
    get_role_xp,
    role_stage_from_xp,
    set_chat_profile,
)
from .language_modal import (
    build_language_model_decision,
    ensure_ui_backup,
    load_language_registry,
)
from .mcp.approvals import approve_tool_call, reject_tool_call
from .mcp.registry import seed_mcp_registry
from .question_routing import classify_question
from .orchestrator import (
    create_message,
    create_run,
    create_thread,
    ensure_endpoint,
    execute_run,
    get_run,
    list_run_artifacts,
    list_run_steps,
    resume_run,
)


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _list_or_empty(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _default_model_key(catalog: list[dict[str, Any]], preferred_key: str = "") -> str:
    pref = preferred_key.strip()
    if pref:
        for item in catalog:
            if str(item.get("key", "")) == pref:
                provider = str(item.get("provider", "")).strip().lower()
                if provider == "extractive" or bool(item.get("reachable")):
                    return pref
                break
    for item in catalog:
        if bool(item.get("reachable")) and str(item.get("provider", "")) in {"ollama", "lmstudio"}:
            return str(item.get("key", ""))
    for item in catalog:
        if str(item.get("provider", "")) in {"ollama", "lmstudio"}:
            return str(item.get("key", ""))
    return "extractive|extractive|"


def _split_model_key(raw: str) -> tuple[str, str, str]:
    parts = str(raw or "").split("|", 2)
    if len(parts) != 3:
        return "", "", ""
    return parts[0].strip().lower(), parts[1].strip(), parts[2].strip()


def _as_bool(value: Any, default: bool = False) -> bool:
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


def _role_xp_delta_for_send(*, provider: str, model: str, message: str, top_k: int, ok: bool) -> int:
    gain = 6
    prov = provider.strip().lower()
    model_name = model.strip().lower()
    if prov in {"ollama", "lmstudio"}:
        gain += 8
    elif prov not in {"extractive"}:
        gain += 5
    if model_name and model_name != "extractive":
        gain += 3
    if len(message.strip()) >= 20:
        gain += 2
    if int(top_k) >= 8:
        gain += 2
    if ok:
        gain += 2
    return max(1, gain)


def _preview_command(command: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


_OFFLINE_MODES = {"off", "guided", "strict"}
_REMOTE_PROVIDERS = {"openai", "codex"}
_ANSWER_SCOPES = {"repo_grounded", "general_local", "remote_allowed"}
_RAW_TERMINAL_MAX_CHARS = 800
_RAW_TERMINAL_BLOCK_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:invoke-expression|iex)\b", re.IGNORECASE),
        "PowerShell expression re-invocation is blocked for direct terminal exec",
    ),
    (
        re.compile(r"\b(?:certutil|bitsadmin|mshta|regsvr32|rundll32)\b", re.IGNORECASE),
        "download or inline execution helpers are blocked for direct terminal exec",
    ),
    (
        re.compile(r"\b(?:invoke-webrequest|iwr|curl(?:\.exe)?|wget(?:\.exe)?|start-bitstransfer)\b", re.IGNORECASE),
        "network download helpers are blocked for direct terminal exec",
    ),
    (
        re.compile(r"(?:downloadstring\s*\(|downloadfile\s*\(|new-object\s+net\.webclient|system\.net\.webclient)", re.IGNORECASE),
        "inline download cradles are blocked for direct terminal exec",
    ),
    (
        re.compile(r"\b(?:add-mppreference|set-mppreference)\b", re.IGNORECASE),
        "antivirus preference changes are blocked for direct terminal exec",
    ),
    (
        re.compile(r"\b(?:register-scheduledtask|schtasks(?:\.exe)?)\b", re.IGNORECASE),
        "scheduled task changes are blocked for direct terminal exec",
    ),
    (
        re.compile(r"currentversion\\run|start menu\\programs\\startup", re.IGNORECASE),
        "autostart persistence changes are blocked for direct terminal exec",
    ),
    (
        re.compile(r"\b(?:new-service|sc(?:\.exe)?\s+create)\b", re.IGNORECASE),
        "service creation is blocked for direct terminal exec",
    ),
    (
        re.compile(r"\b(?:powershell|pwsh)(?:\.exe)?\b[^\r\n]{0,120}\s-(?:enc|encodedcommand)\b", re.IGNORECASE),
        "encoded PowerShell payloads are blocked for direct terminal exec",
    ),
)


def _normalize_offline_mode(value: Any, default: str = "guided") -> str:
    raw = str(value or "").strip().lower()
    if raw in _OFFLINE_MODES:
        return raw
    return default if default in _OFFLINE_MODES else "guided"


def _normalize_answer_scope(value: Any, default: str = "repo_grounded") -> str:
    raw = str(value or "").strip().lower()
    if raw in _ANSWER_SCOPES:
        return raw
    return default if default in _ANSWER_SCOPES else "repo_grounded"


def _payload_confirmed(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return _as_bool(payload.get("confirmed"), False) or _as_bool(payload.get("confirm"), False)


def _short_command_preview(value: str, max_chars: int = 180) -> str:
    text = " ".join(str(value or "").strip().split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."


def _terminal_meta(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "offline_safe": bool(item.get("offline_safe", True)),
        "requires_network": bool(item.get("requires_network", False)),
        "requires_confirmation": bool(item.get("requires_confirmation", False)),
        "category": str(item.get("category", "general")).strip().lower() or "general",
    }


def _present_terminal_entry(entry_id: str, item: dict[str, Any], key_name: str) -> dict[str, Any]:
    command = [str(part) for part in item.get("command", []) if str(part).strip()]
    meta = _terminal_meta(item)
    try:
        timeout_sec = int(item.get("timeout_sec", 25))
    except (TypeError, ValueError):
        timeout_sec = 25
    timeout_sec = max(3, min(300, timeout_sec))
    return {
        key_name: entry_id,
        "label": str(item.get("label", entry_id)),
        "description": str(item.get("description", "")),
        "command_preview": _preview_command(command),
        "timeout_sec": timeout_sec,
        "stream_output": bool(item.get("stream_output", False)),
        "offline_safe": meta["offline_safe"],
        "requires_network": meta["requires_network"],
        "requires_confirmation": meta["requires_confirmation"],
        "category": meta["category"],
    }


def register_v3_routes(app: Any, root: Path, Depends: Any, HTTPException: Any, require_user: Any) -> None:
    api_events: list[dict[str, Any]] = []
    event_seq = 0
    terminal_runs: dict[str, dict[str, Any]] = {}
    terminal_runs_lock = threading.Lock()

    def _open_conn():
        conn = connect_runtime(root)
        seed_mcp_registry(conn)
        return conn

    def _build_remote_foundry_binary_gate(
        answer_scope: str,
        *,
        capability_report: dict[str, Any] | None = None,
        policy_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_scope = _normalize_answer_scope(answer_scope, default="repo_grounded")
        report = capability_report if isinstance(capability_report, dict) else None
        if report is None and normalized_scope == "remote_allowed":
            report = collect_capability_report(root)

        policy = policy_payload if isinstance(policy_payload, dict) else load_routing_policy(root)
        decision_engine = dict(policy.get("decision_engine", {}))
        remote_requested = normalized_scope == "remote_allowed"
        local_tools_ready = bool(report.get("overall_ready", False)) if isinstance(report, dict) else not remote_requested
        continue_or_stop = (not remote_requested) or local_tools_ready
        return {
            "decision_engine_mode": str(decision_engine.get("primary_mode", "binary")).strip().lower() or "binary",
            "classical_fallback_required": bool(decision_engine.get("classical_baseline_required", True)),
            "verification_boundary": str(decision_engine.get("verification_boundary", "required")).strip() or "required",
            "local_tools_ready": local_tools_ready,
            "remote_or_foundry_requested": remote_requested,
            "continue_or_stop": continue_or_stop,
            "stop_and_optimize_local": remote_requested and not continue_or_stop,
            "required_action": "" if continue_or_stop else "fix_all_capabilities",
            "reason": (
                ""
                if continue_or_stop
                else "Optimize all local tools and the repo venv before continuing to Remote Allowed or Foundry lanes."
            ),
        }

    def _assert_remote_foundry_gate(
        answer_scope: str,
        *,
        capability_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        gate = _build_remote_foundry_binary_gate(answer_scope, capability_report=capability_report)
        if bool(gate.get("remote_or_foundry_requested", False)) and not bool(gate.get("continue_or_stop", False)):
            raise HTTPException(
                status_code=400,
                detail=str(
                    gate.get(
                        "reason",
                        "Remote Allowed or Foundry lanes are blocked until local tools are ready.",
                    )
                ),
            )
        return gate

    def _build_foundry_gate_contract(
        *,
        capability_report: dict[str, Any] | None = None,
        policy_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report = capability_report if isinstance(capability_report, dict) else collect_capability_report(root)
        policy = policy_payload if isinstance(policy_payload, dict) else load_routing_policy(root)
        gate = _build_remote_foundry_binary_gate(
            "remote_allowed",
            capability_report=report,
            policy_payload=policy,
        )
        remote_providers = policy.get("remote_providers", [])
        provider_row: dict[str, Any] = {}
        if isinstance(remote_providers, list):
            provider_row = next(
                (
                    dict(item)
                    for item in remote_providers
                    if isinstance(item, dict) and str(item.get("provider_id", "")).strip().lower() == "remote2"
                ),
                {},
            )
        next_actions = [
            str(item.get("action_id", "")).strip()
            for item in list(report.get("fix_actions", []))
            if isinstance(item, dict) and str(item.get("action_id", "")).strip()
        ]
        return {
            "contract_version": "ai3-foundry-gate-v1",
            "lane_id": "foundry",
            "display_name": "Foundry Section",
            "phase": "future",
            "provider_id": str(provider_row.get("provider_id", "remote2")).strip() or "remote2",
            "base_url_env": str(provider_row.get("base_url_env", "OPENAI_BASE_URL_REMOTE2")).strip()
            or "OPENAI_BASE_URL_REMOTE2",
            "api_key_ref": str(provider_row.get("api_key_ref", "OPENAI_API_KEY_REMOTE2")).strip()
            or "OPENAI_API_KEY_REMOTE2",
            "configured_model": str(provider_row.get("model", "gpt-5-mini")).strip() or "gpt-5-mini",
            "continue_or_stop": bool(gate.get("continue_or_stop", False)),
            "pane_enabled": bool(gate.get("continue_or_stop", False)),
            "requires_local_optimization": not bool(gate.get("continue_or_stop", False)),
            "local_tools_ready": bool(gate.get("local_tools_ready", False)),
            "classical_fallback_required": bool(gate.get("classical_fallback_required", True)),
            "verification_boundary": str(gate.get("verification_boundary", "required")).strip() or "required",
            "required_action": str(gate.get("required_action", "")).strip(),
            "reason": str(gate.get("reason", "")).strip(),
            "next_actions": next_actions,
        }

    # Backup-first workflow for modal updates: keep a restorable copy on first startup.
    ensure_ui_backup(root)

    def _terminal_env() -> dict[str, str]:
        env = dict(os.environ)
        src_path = str((root / "src").resolve())
        current = str(env.get("PYTHONPATH", "")).strip()
        env["PYTHONPATH"] = src_path if not current else f"{src_path}{os.pathsep}{current}"
        return env

    def _terminal_profiles() -> dict[str, dict[str, Any]]:
        repo_path = str(root.resolve())
        repo_path_wsl = repo_path
        if os.name == "nt":
            normalized = repo_path.replace("\\", "/")
            if len(normalized) >= 3 and normalized[1] == ":":
                repo_path_wsl = f"/mnt/{normalized[0].lower()}{normalized[2:]}"
        profiles: dict[str, dict[str, Any]] = {}

        if os.name == "nt":
            powershell = shutil.which("powershell.exe") or shutil.which("powershell")
            cmd_exe = shutil.which("cmd.exe") or shutil.which("cmd")
            wsl_exe = shutil.which("wsl.exe")
            node_exe = shutil.which("node.exe") or shutil.which("node")
            git_bash = shutil.which("bash.exe") if shutil.which("bash.exe") else None
            if not git_bash:
                fallback_git = Path("C:/Program Files/Git/bin/bash.exe")
                if fallback_git.exists():
                    git_bash = str(fallback_git)

            ccbs_user_script = root / "scripts" / "ccbs_terminal_env.ps1"
            if powershell and ccbs_user_script.exists():
                profiles["powershell_ccbs_user"] = {
                    "label": "PowerShell (CCBS Clean User)",
                    "description": "Open CCBS user terminal profile with repo env bootstrap.",
                    "command": [str(powershell), "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(ccbs_user_script)],
                    "offline_safe": True,
                    "requires_network": False,
                    "requires_confirmation": False,
                    "category": "terminal",
                }
            if powershell:
                profiles["powershell"] = {
                    "label": "PowerShell",
                    "description": "Open a plain PowerShell terminal in the repo.",
                    "command": [str(powershell), "-NoExit", "-Command", f"Set-Location '{repo_path}'"],
                    "offline_safe": True,
                    "requires_network": False,
                    "requires_confirmation": False,
                    "category": "terminal",
                }
            if cmd_exe:
                profiles["cmd"] = {
                    "label": "Command Prompt",
                    "description": "Open a Command Prompt terminal in the repo.",
                    "command": [str(cmd_exe), "/k", f'cd /d "{repo_path}"'],
                    "offline_safe": True,
                    "requires_network": False,
                    "requires_confirmation": False,
                    "category": "terminal",
                }
            if git_bash:
                profiles["git_bash"] = {
                    "label": "Git Bash",
                    "description": "Open Git Bash in the repository.",
                    "command": [str(git_bash), "--login", "-i"],
                    "offline_safe": True,
                    "requires_network": False,
                    "requires_confirmation": False,
                    "category": "terminal",
                }
            if wsl_exe:
                profiles["wsl_bash"] = {
                    "label": "WSL Bash",
                    "description": "Open WSL bash in the repository.",
                    "command": [str(wsl_exe), "bash", "-lc", f"cd '{repo_path_wsl}' && exec bash"],
                    "offline_safe": True,
                    "requires_network": False,
                    "requires_confirmation": False,
                    "category": "terminal",
                }
            if node_exe:
                profiles["node_repl"] = {
                    "label": "Node REPL",
                    "description": "Open Node.js REPL in a terminal window.",
                    "command": [str(node_exe)],
                    "offline_safe": True,
                    "requires_network": False,
                    "requires_confirmation": False,
                    "category": "terminal",
                }
        else:
            shell_bin = shutil.which("bash") or shutil.which("sh")
            node_exe = shutil.which("node")
            if shell_bin:
                profiles["bash"] = {
                    "label": "Bash",
                    "description": "Open bash in the repository.",
                    "command": [str(shell_bin), "-lc", "exec bash"],
                    "offline_safe": True,
                    "requires_network": False,
                    "requires_confirmation": False,
                    "category": "terminal",
                }
            if node_exe:
                profiles["node_repl"] = {
                    "label": "Node REPL",
                    "description": "Open Node.js REPL in terminal.",
                    "command": [str(node_exe)],
                    "offline_safe": True,
                    "requires_network": False,
                    "requires_confirmation": False,
                    "category": "terminal",
                }

        python_bin = sys.executable or "python"
        profiles["python_repl"] = {
            "label": "Python REPL",
            "description": "Open interactive Python in terminal.",
            "command": [python_bin, "-i"],
            "offline_safe": True,
            "requires_network": False,
            "requires_confirmation": False,
            "category": "terminal",
        }
        return profiles

    def _terminal_presets() -> dict[str, dict[str, Any]]:
        python_bin = sys.executable or "python"
        language_catalog_test_script = str((root / "scripts" / "test_language_catalog.py").resolve())
        notebook_doctor_script = (
            "import importlib.util as u; "
            "mods=['notebook','jupyterlab','ipykernel','pandas','sklearn']; "
            "missing=[x for x in mods if u.find_spec(x) is None]; "
            "print('OK notebook deps installed' if not missing else 'MISSING: ' + ', '.join(missing)); "
            "raise SystemExit(0 if not missing else 1)"
        )
        notebook_install_script = (
            "import subprocess, sys; "
            "cmd=[sys.executable,'-m','pip','install','-U','jupyter','notebook','ipykernel','jupyterlab','pandas','scikit-learn']; "
            "print('$ ' + ' '.join(cmd)); "
            "raise SystemExit(subprocess.call(cmd))"
        )
        cpp_toolchain_script = (
            "import shutil; "
            "gpp=shutil.which('g++'); clang=shutil.which('clang++'); cmake=shutil.which('cmake'); "
            "print('g++: ' + (gpp or 'MISSING')); "
            "print('clang++: ' + (clang or 'MISSING')); "
            "print('cmake: ' + (cmake or 'MISSING')); "
            "raise SystemExit(0 if ((gpp or clang) and cmake) else 1)"
        )
        cpp_smoke_script = (
            "import pathlib, shutil, subprocess, sys, tempfile\n"
            "compiler = shutil.which('g++') or shutil.which('clang++')\n"
            "if not compiler:\n"
            "    print('MISSING compiler: install g++ or clang++')\n"
            "    raise SystemExit(1)\n"
            "code = '#include <iostream>\\nint main(){ std::cout << \"ccbs-cpp-ok\\\\n\"; return 0; }\\n'\n"
            "with tempfile.TemporaryDirectory() as d:\n"
            "    src = pathlib.Path(d) / 'main.cpp'\n"
            "    exe = pathlib.Path(d) / ('main.exe' if sys.platform.startswith('win') else 'main')\n"
            "    src.write_text(code, encoding='utf-8')\n"
            "    build_cmd = [compiler, str(src), '-std=c++17', '-O2', '-o', str(exe)]\n"
            "    print('$ ' + ' '.join(build_cmd))\n"
            "    build = subprocess.run(build_cmd, capture_output=True, text=True)\n"
            "    if build.stdout:\n"
            "        print(build.stdout, end='')\n"
            "    if build.stderr:\n"
            "        print(build.stderr, end='')\n"
            "    if build.returncode != 0:\n"
            "        raise SystemExit(build.returncode)\n"
            "    run = subprocess.run([str(exe)], capture_output=True, text=True)\n"
            "    if run.stdout:\n"
            "        print(run.stdout, end='')\n"
            "    if run.stderr:\n"
            "        print(run.stderr, end='')\n"
            "    raise SystemExit(run.returncode)\n"
        )
        vscode_extensions_doctor_script = (
            "import pathlib, subprocess, shutil, sys\n"
            "cfg = pathlib.Path('config/vscode-extensions.txt')\n"
            "wanted = []\n"
            "if cfg.exists():\n"
            "    for raw in cfg.read_text(encoding='utf-8').splitlines():\n"
            "        line = raw.strip().lstrip('\\ufeff')\n"
            "        if line and not line.startswith('#'):\n"
            "            wanted.append(line.lower())\n"
            "code = shutil.which('code') or shutil.which('code.cmd')\n"
            "if not code:\n"
            "    print('MISSING: VS Code CLI (code) not found in PATH')\n"
            "    raise SystemExit(1)\n"
            "proc = subprocess.run([code, '--list-extensions'], capture_output=True, text=True)\n"
            "if proc.returncode != 0:\n"
            "    print(proc.stdout or '', end='')\n"
            "    print(proc.stderr or '', end='')\n"
            "    raise SystemExit(proc.returncode)\n"
            "installed = [x.strip().lower() for x in proc.stdout.splitlines() if x.strip()]\n"
            "missing = [x for x in wanted if x not in installed]\n"
            "print(f'installed={len(installed)} managed={len(wanted)} missing={len(missing)}')\n"
            "if missing:\n"
            "    print('MISSING_MANAGED: ' + ', '.join(missing))\n"
            "    raise SystemExit(1)\n"
            "print('OK managed extensions installed')\n"
        )
        return {
            "ccbs_doctor": {
                "label": "CCBS Doctor",
                "description": "Run full CCBS environment diagnostics.",
                "command": [python_bin, "-m", "ccbs_app.cli", "doctor"],
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "diagnostics",
            },
            "ccbs_repo_root": {
                "label": "CCBS Repo Root",
                "description": "Show the active repository root used by CCBS.",
                "command": [python_bin, "-m", "ccbs_app.cli", "repo-root"],
                "timeout_sec": 20,
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "diagnostics",
            },
            "ccbs_language_catalog_test": {
                "label": "Language Catalog Test",
                "description": "Validate 1800+ language catalog coverage and write JSON report.",
                "command": [
                    python_bin,
                    "-u",
                    language_catalog_test_script,
                    "--min-catalog-count",
                    "1800",
                    "--min-coverage",
                    "0.98",
                    "--max-missing",
                    "20",
                    "--print-all",
                    "--show-check-expr",
                ],
                "timeout_sec": 120,
                "stream_output": True,
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "diagnostics",
            },
            "ccbs_api_status": {
                "label": "AI API Status",
                "description": "Check CCBS API runtime endpoint status.",
                "command": [python_bin, "-m", "ccbs_app.cli", "ai", "api", "status"],
                "timeout_sec": 20,
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "diagnostics",
            },
            "ccbs_foundry_codex_sewing_tests": {
                "label": "Foundry/Codex/Sewing Tests",
                "description": "Run deterministic surface tests for sewing machine, Foundry pane, and Codex bridge.",
                "command": [
                    python_bin,
                    "-m",
                    "pytest",
                    "tests/test_sewing_machine.py",
                    "tests/test_ai3_foundry_pane.py",
                    "tests/test_codex_integration_surface.py",
                    "-v",
                    "--tb=short",
                ],
                "timeout_sec": 240,
                "stream_output": True,
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "tests",
            },
            "ccbs_all_apps_agents_tests": {
                "label": "All Apps + Agents Tests",
                "description": "Run expanded app and agent surface tests in one deterministic pack.",
                "command": [
                    python_bin,
                    "-m",
                    "pytest",
                    "tests/test_sewing_machine.py",
                    "tests/test_sewing_cli_alias.py",
                    "tests/test_ai3_foundry_pane.py",
                    "tests/test_codex_integration_surface.py",
                    "tests/test_ai3_api_offline_mode.py",
                    "tests/test_ai3_gui.py",
                    "tests/test_ai_chat_only_features.py",
                    "-v",
                    "--tb=short",
                ],
                "timeout_sec": 300,
                "stream_output": True,
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "tests",
            },
            "ccbs_notebook_doctor": {
                "label": "Notebook Runtime Check",
                "description": "Verify notebook dependencies used by analytics and assignments.",
                "command": [python_bin, "-c", notebook_doctor_script],
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "notebook",
            },
            "ccbs_jupyter_version": {
                "label": "Jupyter Version",
                "description": "Show installed Jupyter component versions.",
                "command": [python_bin, "-m", "jupyter", "--version"],
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "notebook",
            },
            "ccbs_notebook_install_core": {
                "label": "Install Notebook Stack",
                "description": "Install Jupyter, notebook, kernel, pandas, and scikit-learn in current Python env.",
                "command": [python_bin, "-c", notebook_install_script],
                "offline_safe": False,
                "requires_network": True,
                "requires_confirmation": True,
                "category": "notebook",
            },
            "ccbs_notebook_register_kernel": {
                "label": "Register CCBS Kernel",
                "description": "Register this Python env as VS Code/Jupyter kernel 'Python (CCBS PRO)'.",
                "command": [python_bin, "-m", "ipykernel", "install", "--user", "--name", "ccbs-pro", "--display-name", "Python (CCBS PRO)"],
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": True,
                "category": "notebook",
            },
            "ccbs_cpp_toolchain_doctor": {
                "label": "C++ Toolchain Check",
                "description": "Verify g++/clang++/cmake availability for C++ workflows.",
                "command": [python_bin, "-c", cpp_toolchain_script],
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "cpp",
            },
            "ccbs_cpp_compile_smoke": {
                "label": "C++ Compile Smoke Test",
                "description": "Compile and run a tiny C++ program to confirm build/run path.",
                "command": [python_bin, "-c", cpp_smoke_script],
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "cpp",
            },
            "ccbs_vscode_extensions_doctor": {
                "label": "VS Code Extensions Check",
                "description": "Verify managed VS Code extensions required by CCBS are installed.",
                "command": [python_bin, "-c", vscode_extensions_doctor_script],
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "vscode",
            },
            "ccbs_capabilities_status": {
                "label": "Capability Status",
                "description": "Run unified capability discover/classify report.",
                "command": [python_bin, "-m", "ccbs_app.cli", "capabilities", "status"],
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": False,
                "category": "capability",
            },
            "ccbs_fix_all_capabilities": {
                "label": "Fix All Capabilities",
                "description": "Run guided remediation across C++, notebook runtime, and local providers.",
                "command": [python_bin, "-m", "ccbs_app.cli", "capabilities", "run", "--approve"],
                "offline_safe": False,
                "requires_network": True,
                "requires_confirmation": True,
                "category": "capability",
            },
            "ccbs_repair_cpp": {
                "label": "Repair C++",
                "description": "Repair Windows/WSL C++ toolchain and refresh readiness state.",
                "command": [python_bin, "-m", "ccbs_app.cli", "capabilities", "fix", "--action", "repair_cpp", "--approve"],
                "offline_safe": False,
                "requires_network": True,
                "requires_confirmation": True,
                "category": "capability",
            },
            "ccbs_repair_notebook_runtime": {
                "label": "Repair Notebook Runtime",
                "description": "Install notebook dependencies and register the CCBS kernel.",
                "command": [python_bin, "-m", "ccbs_app.cli", "capabilities", "fix", "--action", "repair_notebook_runtime", "--approve"],
                "offline_safe": False,
                "requires_network": True,
                "requires_confirmation": True,
                "category": "capability",
            },
            "ccbs_start_lm_studio": {
                "label": "Start LM Studio",
                "description": "Launch LM Studio local runtime and re-check API reachability.",
                "command": [python_bin, "-m", "ccbs_app.cli", "capabilities", "fix", "--action", "start_lm_studio", "--approve"],
                "offline_safe": True,
                "requires_network": False,
                "requires_confirmation": True,
                "category": "capability",
            },
        }

    def _profile_scope(user: dict[str, Any]) -> str:
        return str(user.get("username", "default")).strip() or "default"

    def _load_profile_for_user(user: dict[str, Any]) -> dict[str, Any]:
        conn = _open_conn()
        try:
            return get_chat_profile(conn, user_id=_profile_scope(user))
        finally:
            conn.close()

    def _resolve_offline_mode(user: dict[str, Any], payload: dict[str, Any] | None = None, profile: dict[str, Any] | None = None) -> str:
        profile_row = profile if isinstance(profile, dict) else _load_profile_for_user(user)
        default_mode = _normalize_offline_mode(profile_row.get("offline_mode", "guided"), default="guided")
        if isinstance(payload, dict):
            return _normalize_offline_mode(payload.get("offline_mode", default_mode), default=default_mode)
        return default_mode

    def _assert_terminal_allowed_for_mode(mode: str, item: dict[str, Any]) -> None:
        meta = _terminal_meta(item)
        if mode != "strict":
            return
        if bool(meta.get("requires_network")) or not bool(meta.get("offline_safe")):
            raise HTTPException(
                status_code=403,
                detail=(
                    "strict offline mode blocked this terminal action "
                    "(requires network or is not marked offline-safe). "
                    "Switch offline mode to guided/off to allow it."
                ),
            )

    def _assert_terminal_confirmation(
        payload: dict[str, Any] | None,
        *,
        label: str,
        command_preview: str,
        item: dict[str, Any] | None = None,
        always: bool = False,
    ) -> None:
        needs_confirmation = bool(always)
        if isinstance(item, dict):
            meta = _terminal_meta(item)
            needs_confirmation = needs_confirmation or bool(meta.get("requires_confirmation")) or bool(meta.get("requires_network"))
        if not needs_confirmation:
            return
        if _payload_confirmed(payload):
            return
        preview = _short_command_preview(command_preview)
        raise HTTPException(
            status_code=400,
            detail=(
                f"terminal action requires confirmation: {label}. "
                f"Re-submit with confirmed=true to run: {preview}"
            ),
        )

    def _assert_raw_terminal_exec_allowed(raw_command: str, *, offline_mode: str) -> None:
        cleaned = str(raw_command or "").strip()
        if not cleaned:
            raise HTTPException(status_code=400, detail="command is required")
        if "\x00" in cleaned:
            raise HTTPException(status_code=400, detail="command contains an invalid NUL byte")
        if "\r" in cleaned or "\n" in cleaned:
            raise HTTPException(status_code=400, detail="direct terminal exec only accepts a single-line command")
        if len(cleaned) > _RAW_TERMINAL_MAX_CHARS:
            raise HTTPException(
                status_code=400,
                detail=f"direct terminal exec is limited to {_RAW_TERMINAL_MAX_CHARS} characters",
            )
        if offline_mode == "strict":
            raise HTTPException(
                status_code=403,
                detail=(
                    "strict offline mode blocks direct terminal exec. "
                    "Use reviewed presets/profiles or switch offline mode to guided/off."
                ),
            )
        for pattern, reason in _RAW_TERMINAL_BLOCK_RULES:
            if pattern.search(cleaned):
                raise HTTPException(
                    status_code=400,
                    detail=f"direct terminal exec blocked: {reason}. Use a reviewed preset/profile or local shell instead.",
                )

    def _record_api_event(
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nonlocal event_seq
        event_seq += 1
        scope = _profile_scope(user or {})
        row = {
            "event_id": f"evt_{event_seq:08d}",
            "seq": event_seq,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kind": str(kind or "event"),
            "profile_scope": scope,
            "payload": dict(payload or {}),
        }
        api_events.append(row)
        if len(api_events) > 400:
            del api_events[:-400]
        return row

    def _events_for_scope(scope: str, *, limit: int) -> list[dict[str, Any]]:
        selected = [row for row in api_events if str(row.get("profile_scope", "")) in {scope, "default"}]
        if limit > 0:
            selected = selected[-limit:]
        return selected

    def _run_terminal_command(*, command: list[str], timeout_sec: int) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                command,
                cwd=str(root),
                env=_terminal_env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            stdout = (proc.stdout or "")[-400000:]
            stderr = (proc.stderr or "")[-80000:]
            return {
                "exit_code": int(proc.returncode),
                "ok": proc.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            stdout = str(exc.stdout or "")[-400000:]
            stderr = str(exc.stderr or "")[-80000:]
            return {
                "exit_code": 124,
                "ok": False,
                "stdout": stdout,
                "stderr": stderr or f"Command timed out after {timeout_sec}s",
                "timed_out": True,
            }

    def _truncate_terminal_runs() -> None:
        now = time.time()
        with terminal_runs_lock:
            stale: list[str] = []
            for run_id, row in terminal_runs.items():
                finished = bool(row.get("finished", False))
                ended_at_ts = float(row.get("ended_at_ts", 0.0) or 0.0)
                if not finished:
                    continue
                if ended_at_ts <= 0.0:
                    continue
                if (now - ended_at_ts) > 900.0:
                    stale.append(run_id)
            for run_id in stale:
                terminal_runs.pop(run_id, None)

    def _append_terminal_stream_text(run: dict[str, Any], key: str, chunk: str, *, max_chars: int) -> None:
        prev = str(run.get(key, ""))
        next_text = f"{prev}{chunk}"
        truncated = False
        if len(next_text) > max_chars:
            next_text = next_text[-max_chars:]
            truncated = True
        run[key] = next_text
        if truncated:
            run[f"{key}_truncated"] = True
        run["updated_at"] = datetime.now(timezone.utc).isoformat()

    def _stream_reader_worker(run_id: str, stream: Any, key: str) -> None:
        if stream is None:
            return
        try:
            while True:
                chunk = stream.readline()
                if chunk == "":
                    break
                with terminal_runs_lock:
                    row = terminal_runs.get(run_id)
                    if row is None:
                        break
                    _append_terminal_stream_text(row, key, chunk, max_chars=700000 if key == "stdout" else 220000)
        except Exception:
            return
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _stream_watch_worker(run_id: str) -> None:
        while True:
            with terminal_runs_lock:
                row = terminal_runs.get(run_id)
                if row is None:
                    return
                proc = row.get("process")
                timeout_sec = int(row.get("timeout_sec", 25) or 25)
                started_monotonic = float(row.get("started_monotonic", 0.0) or 0.0)
            if proc is None:
                return
            if proc.poll() is not None:
                break
            if started_monotonic > 0.0 and (time.monotonic() - started_monotonic) > timeout_sec:
                try:
                    proc.kill()
                except Exception:
                    pass
                with terminal_runs_lock:
                    row = terminal_runs.get(run_id)
                    if row is not None:
                        row["timed_out"] = True
                break
            time.sleep(0.12)

        exit_code = 1
        with terminal_runs_lock:
            row = terminal_runs.get(run_id)
            proc = None if row is None else row.get("process")
        if proc is not None:
            try:
                exit_code = int(proc.wait(timeout=1))
            except Exception:
                try:
                    exit_code = int(proc.returncode if proc.returncode is not None else 1)
                except Exception:
                    exit_code = 1
        with terminal_runs_lock:
            row = terminal_runs.get(run_id)
            if row is None:
                return
            timed_out = bool(row.get("timed_out", False))
            if timed_out and exit_code == 0:
                exit_code = 124
            row["exit_code"] = int(exit_code if not timed_out else 124)
            row["ok"] = bool((not timed_out) and int(row["exit_code"]) == 0)
            row["finished"] = True
            row["process"] = None
            row["ended_at"] = datetime.now(timezone.utc).isoformat()
            row["ended_at_ts"] = time.time()
            row["updated_at"] = row["ended_at"]

    def _start_terminal_stream_run(
        *,
        preset_id: str,
        preset: dict[str, Any],
        command: list[str],
        timeout_sec: int,
        offline_mode: str,
        profile_scope: str,
    ) -> dict[str, Any]:
        _truncate_terminal_runs()
        proc = subprocess.Popen(  # noqa: S603
            command,
            cwd=str(root),
            env=_terminal_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        run_id = f"trun_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        row: dict[str, Any] = {
            "run_id": run_id,
            "profile_scope": profile_scope,
            "preset_id": preset_id,
            "label": str(preset.get("label", preset_id)),
            "command": _preview_command(command),
            "cwd": str(root.resolve()),
            "timeout_sec": timeout_sec,
            "offline_mode": offline_mode,
            "started_at": now,
            "updated_at": now,
            "ended_at": "",
            "ended_at_ts": 0.0,
            "started_monotonic": time.monotonic(),
            "finished": False,
            "timed_out": False,
            "ok": False,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "finish_event_sent": False,
            "process": proc,
        }
        with terminal_runs_lock:
            terminal_runs[run_id] = row

        threading.Thread(
            target=_stream_reader_worker,
            args=(run_id, proc.stdout, "stdout"),
            daemon=True,
        ).start()
        threading.Thread(
            target=_stream_reader_worker,
            args=(run_id, proc.stderr, "stderr"),
            daemon=True,
        ).start()
        threading.Thread(
            target=_stream_watch_worker,
            args=(run_id,),
            daemon=True,
        ).start()
        return {"run_id": run_id}

    def _terminal_stream_status(run_id: str, *, scope: str) -> dict[str, Any]:
        with terminal_runs_lock:
            row = terminal_runs.get(run_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id}")
            if str(row.get("profile_scope", "")) != str(scope):
                raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id}")
            return {
                "run_id": run_id,
                "preset_id": str(row.get("preset_id", "")),
                "label": str(row.get("label", "")),
                "command": str(row.get("command", "")),
                "cwd": str(row.get("cwd", "")),
                "timeout_sec": int(row.get("timeout_sec", 25) or 25),
                "offline_mode": str(row.get("offline_mode", "")),
                "started_at": str(row.get("started_at", "")),
                "updated_at": str(row.get("updated_at", "")),
                "ended_at": str(row.get("ended_at", "")),
                "finished": bool(row.get("finished", False)),
                "timed_out": bool(row.get("timed_out", False)),
                "ok": bool(row.get("ok", False)),
                "exit_code": int(row.get("exit_code", 0) or 0),
                "stdout": str(row.get("stdout", "")),
                "stderr": str(row.get("stderr", "")),
                "stdout_truncated": bool(row.get("stdout_truncated", False)),
                "stderr_truncated": bool(row.get("stderr_truncated", False)),
            }

    def _shell_command_for_terminal(raw_command: str) -> list[str]:
        command = str(raw_command or "").strip()
        if not command:
            return []
        if os.name == "nt":
            powershell = (
                shutil.which("pwsh.exe")
                or shutil.which("powershell.exe")
                or shutil.which("pwsh")
                or shutil.which("powershell")
            )
            if powershell:
                return [
                    str(powershell),
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    command,
                ]
            cmd_exe = shutil.which("cmd.exe") or shutil.which("cmd")
            if cmd_exe:
                return [str(cmd_exe), "/d", "/s", "/c", command]
            return ["cmd.exe", "/d", "/s", "/c", command]

        shell_bin = shutil.which("bash") or shutil.which("sh")
        if shell_bin:
            return [str(shell_bin), "-lc", command]
        return ["/bin/sh", "-lc", command]

    def _offline_dependency_checks(
        *,
        capability_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cap = capability_report if isinstance(capability_report, dict) else collect_capability_report(root)
        py = dict(cap.get("python_notebook", {}))
        windows_cpp = dict(cap.get("windows_cpp", {}))
        wsl_cpp = dict(cap.get("wsl_cpp", {}))
        vscode = dict(cap.get("vscode", {}))
        notebook_missing = [str(x) for x in py.get("missing_modules", [])]
        cpp_ok = bool(windows_cpp.get("ready", False) and wsl_cpp.get("ready", False))
        if os.name != "nt":
            cpp_ok = bool(wsl_cpp.get("ready", False))
        return {
            "python": {
                "ok": bool(py.get("python_executable", "")),
                "path": str(py.get("python_executable", "")),
                "interpreter_mismatch": bool(py.get("interpreter_mismatch", False)),
                "app_python": str(py.get("app_python", "")),
                "launcher_python": str(py.get("launcher_python", "")),
            },
            "notebook": {
                "ok": bool(py.get("ready", False)),
                "missing": notebook_missing,
                "kernel_registered": bool(py.get("kernel_registered", False)),
            },
            "cpp": {
                "ok": cpp_ok,
                "windows_status": str(windows_cpp.get("status", "")),
                "wsl_status": str(wsl_cpp.get("status", "")),
                "gpp": str(wsl_cpp.get("gpp", "")),
                "clangpp": str(wsl_cpp.get("clangpp", "")),
                "cmake": str(wsl_cpp.get("cmake", "") or windows_cpp.get("cmake", "")),
            },
            "vscode": {
                "ok": bool(vscode.get("ready", False)),
                "code_cli": str(vscode.get("code_cli", "")),
                "managed_total": int(vscode.get("managed_total", 0) or 0),
                "missing_managed": [str(x) for x in vscode.get("missing_managed", [])],
                "error": str(vscode.get("error", "")),
            },
        }

    @app.get("/v3/chat/me")
    def v3_chat_me(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        auth_mode = str(user.get("auth_mode", "")).strip()
        if not auth_mode:
            auth_mode = "bearer_token"
        scope = _profile_scope(user)
        return {
            "username": scope,
            "role": str(user.get("role", "")),
            "auth_mode": auth_mode,
            "profile_scope": scope,
        }

    @app.get("/v3/chat/offline-capabilities")
    def v3_chat_offline_capabilities(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        profile = _load_profile_for_user(user)
        mode = _resolve_offline_mode(user, profile=profile)
        catalog = discover_model_catalog(root)
        models = list(catalog.get("models", []))
        local_models = [
            row
            for row in models
            if str(row.get("provider", "")).strip().lower() in {"ollama", "lmstudio", "extractive"}
        ]
        reachable_local = [row for row in local_models if bool(row.get("reachable", False))]

        presets = [
            _present_terminal_entry(preset_id, item, "preset_id")
            for preset_id, item in _terminal_presets().items()
        ]
        profiles = [
            _present_terminal_entry(profile_id, item, "profile_id")
            for profile_id, item in _terminal_profiles().items()
        ]
        capability_report = collect_capability_report(root)
        policy = load_routing_policy(root)
        binary_gate = _build_remote_foundry_binary_gate(
            "remote_allowed",
            capability_report=capability_report,
            policy_payload=policy,
        )
        foundry_gate = _build_foundry_gate_contract(
            capability_report=capability_report,
            policy_payload=policy,
        )
        checks = _offline_dependency_checks(capability_report=capability_report)

        return {
            "offline_modes": ["off", "guided", "strict"],
            "active_offline_mode": mode,
            "model_live_discovery_enabled": bool(catalog.get("live_discovery_enabled", True)),
            "local_models": {
                "total": len(local_models),
                "reachable": len(reachable_local),
                "entries": [
                    {
                        "key": str(row.get("key", "")),
                        "provider": str(row.get("provider", "")),
                        "model": str(row.get("model", "")),
                        "reachable": bool(row.get("reachable", False)),
                    }
                    for row in local_models
                ],
            },
            "terminal": {
                "presets": presets,
                "profiles": profiles,
            },
            "checks": checks,
            "windows_cpp": capability_report.get("windows_cpp", {}),
            "wsl_cpp": capability_report.get("wsl_cpp", {}),
            "python_notebook": capability_report.get("python_notebook", {}),
            "lm_studio": capability_report.get("lm_studio", {}),
            "ollama": capability_report.get("ollama", {}),
            "vscode": capability_report.get("vscode", {}),
            "overall_ready": bool(capability_report.get("overall_ready", False)),
            "fix_actions": list(capability_report.get("fix_actions", [])),
            "provider_policy": dict(capability_report.get("provider_policy", {})),
            "workflow": list(capability_report.get("workflow", [])),
            "binary_gate": binary_gate,
            "foundry_gate": foundry_gate,
            "profile_scope": _profile_scope(user),
        }

    @app.get("/v3/chat/foundry-gate")
    def v3_chat_foundry_gate(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        capability_report = collect_capability_report(root)
        policy = load_routing_policy(root)
        return {
            "foundry_gate": _build_foundry_gate_contract(
                capability_report=capability_report,
                policy_payload=policy,
            ),
            "overall_ready": bool(capability_report.get("overall_ready", False)),
            "fix_actions": list(capability_report.get("fix_actions", [])),
            "profile_scope": _profile_scope(user),
        }

    @app.post("/v3/chat/capabilities/remediate")
    def v3_chat_capabilities_remediate(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        action_id = str(payload.get("action_id", "")).strip().lower()
        if not action_id:
            raise HTTPException(status_code=400, detail="action_id is required")
        approve = _as_bool(payload.get("approve", False), default=False)
        lane = str(payload.get("lane", "")).strip().lower()
        out = execute_capability_action(
            root,
            action_id=action_id,
            approve=approve,
            lane=lane,
            actor=str(user.get("username", "api-user")),
        )
        _record_api_event(
            "capability.remediate",
            {
                "action_id": action_id,
                "approve": approve,
                "lane": lane,
                "ok": bool(out.get("ok", False)),
                "status": str(out.get("status", "")),
            },
            user=user,
        )
        return out

    @app.get("/v3/chat/api-events")
    def v3_chat_api_events(limit: int = 120, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        scope = _profile_scope(user)
        cap = max(1, min(500, int(limit)))
        rows = _events_for_scope(scope, limit=cap)
        return {
            "profile_scope": scope,
            "events": rows,
            "count": len(rows),
        }

    @app.post("/v3/threads")
    def v3_create_thread(payload: dict[str, Any], _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        conn = _open_conn()
        try:
            thread = create_thread(
                conn,
                title=str(payload.get("title", "")).strip(),
                tags=[str(item) for item in _list_or_empty(payload.get("tags"))],
                metadata=_dict_or_empty(payload.get("metadata")),
            )
            return {"thread": thread, "runtime_db": str(runtime_db_path(root))}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.post("/v3/threads/{thread_id}/messages")
    def v3_add_message(
        thread_id: str,
        payload: dict[str, Any],
        _user: dict[str, Any] = Depends(require_user),
    ) -> dict[str, Any]:
        del _user
        conn = _open_conn()
        try:
            row = create_message(
                conn,
                thread_id=thread_id,
                role=str(payload.get("role", "user")),
                content=str(payload.get("content", "")),
                content_json=_dict_or_empty(payload.get("content_json")),
                parent_message_id=str(payload.get("parent_message_id", "")),
                metadata=_dict_or_empty(payload.get("metadata")),
            )
            return {"message": row}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.post("/v3/runs")
    def v3_create_run(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        conn = _open_conn()
        try:
            thread_id = str(payload.get("thread_id", "")).strip()
            if not thread_id:
                raise HTTPException(status_code=400, detail="thread_id is required")

            question = str(payload.get("question", "")).strip()
            if question:
                create_message(conn, thread_id=thread_id, role="user", content=question)
            question_profile = classify_question(question) if question else {}
            simple_qa = bool(question_profile.get("simple_qa", False))

            endpoint_id = str(payload.get("endpoint_id", "")).strip()
            if endpoint_id:
                selected_endpoint = endpoint_id
            else:
                selected_endpoint = ensure_endpoint(
                    conn,
                    provider=str(payload.get("provider", "ollama")),
                    base_url=str(payload.get("base_url", "")),
                    chat_model=str(payload.get("model", "")),
                    embed_model=str(payload.get("embed_model", "")),
                    endpoint_id=str(payload.get("new_endpoint_id", "")),
                )

            metadata = _dict_or_empty(payload.get("metadata"))
            if question:
                metadata.setdefault("question", question)
                metadata.setdefault("question_profile", question_profile)
                metadata.setdefault("simple_qa", simple_qa)
            metadata.setdefault("top_k", int(payload.get("top_k", metadata.get("top_k", 5))))
            metadata.setdefault("offline_only", bool(payload.get("offline_only", metadata.get("offline_only", False))))
            metadata.setdefault("strict_local_models", _as_bool(payload.get("strict_local_models", not simple_qa), default=not simple_qa))
            metadata.setdefault(
                "allow_extractive_fallback",
                _as_bool(payload.get("allow_extractive_fallback", simple_qa), default=simple_qa),
            )
            metadata.setdefault("local_attempts_max", int(payload.get("local_attempts_max", metadata.get("local_attempts_max", 3))))
            metadata.setdefault("codex_model", str(payload.get("codex_model", metadata.get("codex_model", "gpt-5"))))
            metadata.setdefault(
                "codex_base_url",
                str(payload.get("codex_base_url", metadata.get("codex_base_url", "https://api.openai.com/v1"))),
            )
            metadata.setdefault("user_id", str(payload.get("user_id", user.get("username", "api-user"))))
            if "tool_calls" in payload and isinstance(payload.get("tool_calls"), list):
                metadata["tool_calls"] = payload.get("tool_calls")

            run = create_run(conn, thread_id=thread_id, endpoint_id=selected_endpoint, metadata=metadata)
            auto_execute = bool(payload.get("execute", True))
            if not auto_execute:
                return {"run": run, "steps": []}

            result = execute_run(
                root=root,
                conn=conn,
                run_id=str(run["run_id"]),
                actor=str(user.get("username", "api-user")),
                allow_remote=bool(payload.get("allow_remote", False)),
            )
            return result
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.get("/v3/runs/{run_id}")
    def v3_get_run(run_id: str, _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        conn = _open_conn()
        try:
            return {"run": get_run(conn, run_id)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.get("/v3/runs/{run_id}/steps")
    def v3_get_run_steps(run_id: str, _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        conn = _open_conn()
        try:
            get_run(conn, run_id)
            return {"steps": list_run_steps(conn, run_id)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.post("/v3/runs/{run_id}/resume")
    def v3_resume_run(
        run_id: str,
        payload: dict[str, Any],
        user: dict[str, Any] = Depends(require_user),
    ) -> dict[str, Any]:
        conn = _open_conn()
        try:
            result = resume_run(
                root=root,
                conn=conn,
                run_id=run_id,
                actor=str(user.get("username", "api-user")),
                allow_remote=bool(payload.get("allow_remote", False)),
            )
            return result
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.post("/v3/tool-calls/{tool_call_id}/approvals")
    def v3_tool_approval(
        tool_call_id: str,
        payload: dict[str, Any],
        user: dict[str, Any] = Depends(require_user),
    ) -> dict[str, Any]:
        conn = _open_conn()
        try:
            decision = str(payload.get("decision", "approved")).strip().lower()
            rationale = str(payload.get("rationale", "")).strip()
            approved_by = str(user.get("username", "user"))
            if decision == "approved":
                approval = approve_tool_call(conn, tool_call_id=tool_call_id, approved_by=approved_by, rationale=rationale)
            elif decision == "rejected":
                approval = reject_tool_call(conn, tool_call_id=tool_call_id, approved_by=approved_by, rationale=rationale)
            else:
                raise HTTPException(status_code=400, detail="decision must be approved|rejected")

            row = conn.execute("SELECT run_id FROM tool_call WHERE tool_call_id = ?", (tool_call_id,)).fetchone()
            run_id = str(row["run_id"]) if row else ""
            response: dict[str, Any] = {"approval": approval, "run_id": run_id}

            if decision == "approved" and bool(payload.get("resume", True)) and run_id:
                resumed = resume_run(
                    root=root,
                    conn=conn,
                    run_id=run_id,
                    actor=str(user.get("username", "api-user")),
                    allow_remote=bool(payload.get("allow_remote", False)),
                )
                response["run"] = resumed.get("run")
                response["steps"] = resumed.get("steps", [])
            return response
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.get("/v3/runs/{run_id}/artifacts")
    def v3_get_run_artifacts(run_id: str, _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        conn = _open_conn()
        try:
            get_run(conn, run_id)
            return {"artifacts": list_run_artifacts(conn, run_id)}
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.get("/v3/chat/models")
    def v3_chat_models(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        catalog = discover_model_catalog(root)
        conn = _open_conn()
        try:
            profile = get_chat_profile(conn, user_id=str(user.get("username", "default")))
        finally:
            conn.close()
        models = list(catalog.get("models", []))
        default_key = _default_model_key(models, preferred_key=str(profile.get("preferred_model", "")))
        return {
            "models": models,
            "errors": list(catalog.get("errors", [])),
            "default_model_key": default_key,
            "live_discovery_enabled": bool(catalog.get("live_discovery_enabled", True)),
        }

    @app.get("/v3/multi-instance/apps")
    def v3_multi_instance_apps(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        return discover_multi_instance_apps(root)

    @app.get("/v3/multi-instance/state")
    def v3_multi_instance_state(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        return get_multi_instance_state(root)

    @app.get("/v3/multi-instance/runtime")
    def v3_multi_instance_runtime(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        return get_multi_instance_runtime_summary(root)

    @app.get("/v3/multi-instance/profile")
    def v3_multi_instance_profile(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        return {"profile": load_multi_instance_profile(root)}

    @app.post("/v3/multi-instance/profile")
    def v3_multi_instance_profile_set(payload: dict[str, Any], _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        updates = payload if isinstance(payload, dict) else {}
        return {"profile": update_multi_instance_profile(root, updates)}

    @app.post("/v3/multi-instance/optimize")
    def v3_multi_instance_optimize(payload: dict[str, Any], _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        try:
            max_parallel = int(payload.get("max_parallel", 3))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="max_parallel must be an integer") from None
        if max_parallel < 1 or max_parallel > 12:
            raise HTTPException(status_code=400, detail="max_parallel must be between 1 and 12")
        mode = str(payload.get("mode", "auto")).strip().lower() or "auto"
        return optimize_multi_instance_bundle(root, max_parallel=max_parallel, mode=mode)

    @app.post("/v3/multi-instance/control")
    def v3_multi_instance_control(payload: dict[str, Any], _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        action = str(payload.get("action", "status")).strip().lower()
        confirmed = _payload_confirmed(payload)
        out = run_multi_instance_control_action(root, action=action, confirmed=confirmed)
        if not bool(out.get("ok", False)):
            status = str(out.get("status", "")).strip().lower()
            if status == "confirmation_required":
                raise HTTPException(status_code=400, detail=str(out.get("detail", "confirmation required")))
            if status == "unknown_action":
                raise HTTPException(status_code=400, detail=str(out.get("detail", "unknown action")))
        return out

    @app.post("/v3/multi-instance/route")
    def v3_multi_instance_route(payload: dict[str, Any], _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        message = str(payload.get("message", "")).strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        task_label = str(payload.get("task_label", "")).strip()
        requested_lane_id = str(payload.get("requested_lane_id", "")).strip()
        apply_usage = _as_bool(payload.get("apply_usage"), default=False)
        try:
            estimated_tokens_override = int(payload.get("estimated_tokens_override", 0))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="estimated_tokens_override must be an integer") from None
        return route_message_to_lane(
            root,
            message=message,
            task_label=task_label,
            requested_lane_id=requested_lane_id,
            apply_usage=apply_usage,
            estimated_tokens_override=estimated_tokens_override,
        )

    @app.get("/v3/chat/language-modal/backup")
    def v3_chat_language_modal_backup(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        return ensure_ui_backup(root)

    @app.get("/v3/chat/language-catalog")
    def v3_chat_language_catalog(
        storage_mode: str = "",
        include_external: bool = False,
        refresh: bool = False,
        user: dict[str, Any] = Depends(require_user),
    ) -> dict[str, Any]:
        conn = _open_conn()
        try:
            profile = get_chat_profile(conn, user_id=str(user.get("username", "default")))
        finally:
            conn.close()

        preferred = str(storage_mode or profile.get("language_storage_mode", "auto")).strip().lower() or "auto"
        external_enabled = bool(include_external) or _as_bool(profile.get("language_external_enrichment", False), default=False)
        registry = load_language_registry(
            root,
            preferred_storage_mode=preferred,
            include_external_github=external_enabled,
            refresh=bool(refresh),
        )
        rows = list(registry.get("languages", []))
        return {
            "languages": rows,
            "aliases": dict(registry.get("alias_index", {})),
            "counts": dict(registry.get("counts", {})),
            "source_health": dict(registry.get("source_health", {})),
            "active_storage_mode": str(registry.get("active_storage_mode", "json")),
            "preferred_storage_mode": str(registry.get("preferred_storage_mode", preferred)),
            "storage_attempts": list(registry.get("storage_attempts", [])),
        }

    @app.post("/v3/chat/language-decision")
    def v3_chat_language_decision(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        message = str(payload.get("message", "")).strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")

        conn = _open_conn()
        try:
            profile = get_chat_profile(conn, user_id=str(user.get("username", "default")))
        finally:
            conn.close()

        offline_mode = _normalize_offline_mode(payload.get("offline_mode", profile.get("offline_mode", "guided")), default="guided")
        requested_answer_scope = _normalize_answer_scope(
            payload.get("answer_scope", profile.get("default_answer_scope", "repo_grounded")),
            default="repo_grounded",
        )
        policy = load_routing_policy(root)
        binary_gate = _build_remote_foundry_binary_gate(requested_answer_scope, policy_payload=policy)
        answer_scope = requested_answer_scope
        if bool(binary_gate.get("remote_or_foundry_requested", False)) and not bool(binary_gate.get("continue_or_stop", False)):
            answer_scope = "repo_grounded"
        catalog = discover_model_catalog(root)
        rows = list(catalog.get("models", []))
        decision = build_language_model_decision(
            root=root,
            message=message,
            catalog_rows=rows,
            offline_mode=offline_mode,
            answer_scope=answer_scope,
            profile=profile,
            payload=payload,
        )
        if bool(binary_gate.get("remote_or_foundry_requested", False)) and not bool(binary_gate.get("continue_or_stop", False)):
            decision["scope_recommendation"] = "repo_grounded"
            decision["scope_prompt_required"] = False
            decision["scope_reason"] = str(binary_gate.get("reason", "")).strip()
            decision["hybrid_mode"] = "local_only"
        return {
            "decision": decision,
            "catalog_size": len(rows),
            "offline_mode": offline_mode,
            "answer_scope": answer_scope,
            "requested_answer_scope": requested_answer_scope,
            "binary_gate": binary_gate,
            "foundry_gate": _build_foundry_gate_contract(policy_payload=policy),
        }

    @app.get("/v3/chat/profile")
    def v3_chat_profile_get(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        conn = _open_conn()
        try:
            profile = get_chat_profile(conn, user_id=str(user.get("username", "default")))
            return {"profile": profile}
        finally:
            conn.close()

    @app.post("/v3/chat/profile")
    def v3_chat_profile_set(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        conn = _open_conn()
        try:
            values = _dict_or_empty(payload)
            binary_gate: dict[str, Any] = {}
            if "offline_mode" in values:
                values["offline_mode"] = _normalize_offline_mode(values.get("offline_mode"), default="guided")
            if "default_answer_scope" in values:
                values["default_answer_scope"] = _normalize_answer_scope(values.get("default_answer_scope"), default="repo_grounded")
                binary_gate = _build_remote_foundry_binary_gate(str(values.get("default_answer_scope", "repo_grounded")))
                if bool(binary_gate.get("remote_or_foundry_requested", False)) and not bool(binary_gate.get("continue_or_stop", False)):
                    values["default_answer_scope"] = "repo_grounded"
            if "scope_prompt_mode" in values:
                raw = str(values.get("scope_prompt_mode", "")).strip().lower()
                values["scope_prompt_mode"] = raw if raw in {"always", "manual"} else "always"
            if "live_output_mode" in values:
                raw = str(values.get("live_output_mode", "")).strip().lower()
                values["live_output_mode"] = raw if raw in {"collapsed", "summary", "raw"} else "collapsed"
            if "language_mode" in values:
                raw = str(values.get("language_mode", "")).strip().lower()
                values["language_mode"] = raw if raw in {"auto", "manual"} else "auto"
            if "language_storage_mode" in values:
                raw = str(values.get("language_storage_mode", "")).strip().lower()
                values["language_storage_mode"] = raw if raw in {"auto", "json", "sqlite", "parquet", "feather"} else "auto"
            if "language_external_enrichment" in values:
                values["language_external_enrichment"] = "true" if _as_bool(values.get("language_external_enrichment"), default=False) else "false"
            if "manual_language" in values:
                values["manual_language"] = str(values.get("manual_language", "")).strip()
            profile = set_chat_profile(
                conn,
                values=values,
                user_id=str(user.get("username", "default")),
            )
            return {"profile": profile, "binary_gate": binary_gate}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            conn.close()

    @app.get("/v3/chat/cards")
    def v3_chat_cards(
        thread_id: str = "",
        surface: str = "ui",
        user: dict[str, Any] = Depends(require_user),
    ) -> dict[str, Any]:
        conn = _open_conn()
        try:
            profile = get_chat_profile(conn, user_id=str(user.get("username", "default")))
            role_xp = get_role_xp(conn, user_id=str(user.get("username", "default")))
        finally:
            conn.close()

        active_role = str(profile.get("active_role", "core")).strip().lower()
        deck = resolve_card_deck(
            root=root,
            thread_id=thread_id,
            user_id=str(user.get("username", "default")),
            surface=surface,
            active_role=active_role,
            pack_id=str(profile.get("card_pack", "")).strip(),
            extras_count=4,
            role_xp=role_xp,
        )
        return {
            "pack": deck.get("pack", {}),
            "surface": deck.get("surface", surface),
            "thread_seed": deck.get("thread_seed", ""),
            "cards": list(deck.get("cards", [])),
            "active_role": str(deck.get("active_role", active_role)),
            "card_pack_enabled": bool(deck.get("card_pack_enabled", True)),
            "role_xp": role_xp,
        }

    @app.get("/v3/chat/terminal/presets")
    def v3_chat_terminal_presets(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        presets = _terminal_presets()
        mode = _resolve_offline_mode(user)
        rows: list[dict[str, Any]] = [_present_terminal_entry(preset_id, item, "preset_id") for preset_id, item in presets.items()]
        return {"presets": rows, "cwd": str(root.resolve()), "offline_mode": mode}

    @app.post("/v3/chat/terminal/run")
    def v3_chat_terminal_run(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        preset_id = str(payload.get("preset_id", "")).strip()
        if not preset_id:
            raise HTTPException(status_code=400, detail="preset_id is required")

        presets = _terminal_presets()
        preset = presets.get(preset_id)
        if preset is None:
            raise HTTPException(status_code=400, detail=f"unknown preset_id: {preset_id}")

        command = [str(part) for part in preset.get("command", []) if str(part).strip()]
        if not command:
            raise HTTPException(status_code=500, detail=f"invalid command preset: {preset_id}")

        try:
            timeout_sec = int(payload.get("timeout_sec", 25))
        except (TypeError, ValueError):
            timeout_sec = 25
        timeout_sec = max(3, min(120, timeout_sec))

        offline_mode = _resolve_offline_mode(user, payload=payload)
        _assert_terminal_allowed_for_mode(offline_mode, preset)
        _assert_terminal_confirmation(
            payload,
            label=str(preset.get("label", preset_id)),
            command_preview=_preview_command(command),
            item=preset,
        )
        proc_out = _run_terminal_command(command=command, timeout_sec=timeout_sec)
        meta = _terminal_meta(preset)
        result = {
            "preset_id": preset_id,
            "label": str(preset.get("label", preset_id)),
            "command": _preview_command(command),
            "cwd": str(root.resolve()),
            "timeout_sec": timeout_sec,
            "exit_code": int(proc_out.get("exit_code", 1)),
            "ok": bool(proc_out.get("ok", False)),
            "timed_out": bool(proc_out.get("timed_out", False)),
            "stdout": str(proc_out.get("stdout", "")),
            "stderr": str(proc_out.get("stderr", "")),
            "offline_mode": offline_mode,
            "offline_safe": meta["offline_safe"],
            "requires_network": meta["requires_network"],
            "requires_confirmation": meta["requires_confirmation"],
        }
        _record_api_event(
            "terminal.run",
            {
                "preset_id": preset_id,
                "label": str(preset.get("label", preset_id)),
                "ok": bool(result.get("ok", False)),
                "exit_code": int(result.get("exit_code", 1)),
                "offline_mode": offline_mode,
                "stdout_tail": str(result.get("stdout", ""))[-400:],
                "stderr_tail": str(result.get("stderr", ""))[-400:],
            },
            user=user,
        )
        return result

    @app.post("/v3/chat/terminal/run-stream-start")
    def v3_chat_terminal_run_stream_start(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        preset_id = str(payload.get("preset_id", "")).strip()
        if not preset_id:
            raise HTTPException(status_code=400, detail="preset_id is required")

        presets = _terminal_presets()
        preset = presets.get(preset_id)
        if preset is None:
            raise HTTPException(status_code=400, detail=f"unknown preset_id: {preset_id}")

        command = [str(part) for part in preset.get("command", []) if str(part).strip()]
        if not command:
            raise HTTPException(status_code=500, detail=f"invalid command preset: {preset_id}")

        try:
            default_timeout = int(preset.get("timeout_sec", 25))
        except (TypeError, ValueError):
            default_timeout = 25
        try:
            timeout_sec = int(payload.get("timeout_sec", default_timeout))
        except (TypeError, ValueError):
            timeout_sec = default_timeout
        timeout_sec = max(3, min(300, timeout_sec))

        offline_mode = _resolve_offline_mode(user, payload=payload)
        _assert_terminal_allowed_for_mode(offline_mode, preset)
        _assert_terminal_confirmation(
            payload,
            label=str(preset.get("label", preset_id)),
            command_preview=_preview_command(command),
            item=preset,
        )

        try:
            start_meta = _start_terminal_stream_run(
                preset_id=preset_id,
                preset=preset,
                command=command,
                timeout_sec=timeout_sec,
                offline_mode=offline_mode,
                profile_scope=_profile_scope(user),
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        run_id = str(start_meta.get("run_id", "")).strip()
        status = _terminal_stream_status(run_id, scope=_profile_scope(user))
        _record_api_event(
            "terminal.run_stream.start",
            {
                "run_id": run_id,
                "preset_id": preset_id,
                "label": str(preset.get("label", preset_id)),
                "timeout_sec": timeout_sec,
                "offline_mode": offline_mode,
            },
            user=user,
        )
        return status

    @app.get("/v3/chat/terminal/run-stream-status")
    def v3_chat_terminal_run_stream_status(run_id: str, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        rid = str(run_id or "").strip()
        if not rid:
            raise HTTPException(status_code=400, detail="run_id is required")
        status = _terminal_stream_status(rid, scope=_profile_scope(user))
        should_emit_finish = False
        with terminal_runs_lock:
            row = terminal_runs.get(rid)
            if row is not None and bool(row.get("finished", False)) and not bool(row.get("finish_event_sent", False)):
                row["finish_event_sent"] = True
                should_emit_finish = True
        if should_emit_finish:
            _record_api_event(
                "terminal.run_stream.finish",
                {
                    "run_id": rid,
                    "preset_id": str(status.get("preset_id", "")),
                    "ok": bool(status.get("ok", False)),
                    "exit_code": int(status.get("exit_code", 1)),
                    "timed_out": bool(status.get("timed_out", False)),
                },
                user=user,
            )
        return status

    @app.post("/v3/chat/terminal/exec")
    def v3_chat_terminal_exec(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        raw_command = str(payload.get("command", "")).strip()
        if not raw_command:
            raise HTTPException(status_code=400, detail="command is required")

        try:
            timeout_sec = int(payload.get("timeout_sec", 45))
        except (TypeError, ValueError):
            timeout_sec = 45
        timeout_sec = max(3, min(300, timeout_sec))

        offline_mode = _resolve_offline_mode(user, payload=payload)
        _assert_terminal_confirmation(
            payload,
            label="Direct terminal command",
            command_preview=raw_command,
            always=True,
        )
        _assert_raw_terminal_exec_allowed(raw_command, offline_mode=offline_mode)
        shell_command = _shell_command_for_terminal(raw_command)
        if not shell_command:
            raise HTTPException(status_code=500, detail="unable to resolve terminal shell")

        proc_out = _run_terminal_command(command=shell_command, timeout_sec=timeout_sec)
        result = {
            "command": raw_command,
            "shell_command": _preview_command(shell_command),
            "cwd": str(root.resolve()),
            "timeout_sec": timeout_sec,
            "exit_code": int(proc_out.get("exit_code", 1)),
            "ok": bool(proc_out.get("ok", False)),
            "timed_out": bool(proc_out.get("timed_out", False)),
            "stdout": str(proc_out.get("stdout", "")),
            "stderr": str(proc_out.get("stderr", "")),
            "offline_mode": offline_mode,
            "raw_exec": True,
        }
        _record_api_event(
            "terminal.exec",
            {
                "command": raw_command,
                "ok": bool(result.get("ok", False)),
                "exit_code": int(result.get("exit_code", 1)),
                "offline_mode": offline_mode,
                "stdout_tail": str(result.get("stdout", ""))[-400:],
                "stderr_tail": str(result.get("stderr", ""))[-400:],
            },
            user=user,
        )
        return result

    @app.get("/v3/chat/terminal/profiles")
    def v3_chat_terminal_profiles(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        catalog = _terminal_profiles()
        mode = _resolve_offline_mode(user)
        rows: list[dict[str, Any]] = [_present_terminal_entry(profile_id, item, "profile_id") for profile_id, item in catalog.items()]
        return {"profiles": rows, "cwd": str(root.resolve()), "offline_mode": mode}

    @app.post("/v3/chat/terminal/open-profile")
    def v3_chat_terminal_open_profile(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        profile_id = str(payload.get("profile_id", "")).strip()
        if not profile_id:
            raise HTTPException(status_code=400, detail="profile_id is required")

        catalog = _terminal_profiles()
        profile = catalog.get(profile_id)
        if profile is None:
            raise HTTPException(status_code=400, detail=f"unknown profile_id: {profile_id}")

        command = [str(part) for part in profile.get("command", []) if str(part).strip()]
        if not command:
            raise HTTPException(status_code=500, detail=f"invalid profile command: {profile_id}")

        offline_mode = _resolve_offline_mode(user, payload=payload)
        _assert_terminal_allowed_for_mode(offline_mode, profile)
        _assert_terminal_confirmation(
            payload,
            label=str(profile.get("label", profile_id)),
            command_preview=_preview_command(command),
            item=profile,
        )
        try:
            kwargs: dict[str, Any] = {"cwd": str(root), "env": _terminal_env()}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            proc = subprocess.Popen(command, **kwargs)  # noqa: S603
            meta = _terminal_meta(profile)
            result = {
                "profile_id": profile_id,
                "label": str(profile.get("label", profile_id)),
                "command": _preview_command(command),
                "cwd": str(root.resolve()),
                "pid": int(proc.pid),
                "ok": True,
                "offline_mode": offline_mode,
                "offline_safe": meta["offline_safe"],
                "requires_network": meta["requires_network"],
                "requires_confirmation": meta["requires_confirmation"],
            }
            _record_api_event(
                "terminal.open_profile",
                {
                    "profile_id": profile_id,
                    "label": str(profile.get("label", profile_id)),
                    "pid": int(proc.pid),
                    "offline_mode": offline_mode,
                },
                user=user,
            )
            return result
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v3/chat/terminal/audit")
    def v3_chat_terminal_audit(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        presets = _terminal_presets()
        offline_mode = _resolve_offline_mode(user, payload=payload)
        default_ids = [
            "ccbs_repo_root",
            "ccbs_api_status",
            "ccbs_capabilities_status",
            "ccbs_notebook_doctor",
            "ccbs_cpp_toolchain_doctor",
            "ccbs_vscode_extensions_doctor",
        ]
        selected_raw = payload.get("preset_ids", default_ids)
        selected: list[str] = []
        if isinstance(selected_raw, list):
            for item in selected_raw:
                pid = str(item).strip()
                if pid and pid not in selected:
                    selected.append(pid)
        if not selected:
            selected = list(default_ids)

        try:
            timeout_sec = int(payload.get("timeout_sec", 25))
        except (TypeError, ValueError):
            timeout_sec = 25
        timeout_sec = max(3, min(120, timeout_sec))

        results: list[dict[str, Any]] = []
        for preset_id in selected:
            preset = presets.get(preset_id)
            if preset is None:
                results.append(
                    {
                        "preset_id": preset_id,
                        "label": preset_id,
                        "ok": False,
                        "exit_code": 127,
                        "reason": "unknown_preset",
                        "stdout_tail": "",
                        "stderr_tail": f"unknown preset_id: {preset_id}",
                    }
                )
                continue

            try:
                _assert_terminal_allowed_for_mode(offline_mode, preset)
            except HTTPException as exc:
                results.append(
                    {
                        "preset_id": preset_id,
                        "label": str(preset.get("label", preset_id)),
                        "ok": False,
                        "exit_code": 403,
                        "reason": "strict_blocked",
                        "stdout_tail": "",
                        "stderr_tail": str(getattr(exc, "detail", exc)),
                    }
                )
                continue

            command = [str(part) for part in preset.get("command", []) if str(part).strip()]
            if not command:
                results.append(
                    {
                        "preset_id": preset_id,
                        "label": str(preset.get("label", preset_id)),
                        "ok": False,
                        "exit_code": 500,
                        "reason": "invalid_command",
                        "stdout_tail": "",
                        "stderr_tail": f"invalid command preset: {preset_id}",
                    }
                )
                continue

            proc_out = _run_terminal_command(command=command, timeout_sec=timeout_sec)
            results.append(
                {
                    "preset_id": preset_id,
                    "label": str(preset.get("label", preset_id)),
                    "ok": bool(proc_out.get("ok", False)),
                    "exit_code": int(proc_out.get("exit_code", 1)),
                    "reason": "ok" if bool(proc_out.get("ok", False)) else ("timeout" if bool(proc_out.get("timed_out", False)) else "exit_nonzero"),
                    "stdout_tail": str(proc_out.get("stdout", ""))[-1200:],
                    "stderr_tail": str(proc_out.get("stderr", ""))[-1200:],
                }
            )

        out = {
            "offline_mode": offline_mode,
            "ok": all(bool(item.get("ok", False)) for item in results) if results else False,
            "results": results,
            "cwd": str(root.resolve()),
        }
        _record_api_event(
            "terminal.audit",
            {
                "offline_mode": offline_mode,
                "ok": bool(out.get("ok", False)),
                "results": [
                    {
                        "preset_id": str(item.get("preset_id", "")),
                        "ok": bool(item.get("ok", False)),
                        "exit_code": int(item.get("exit_code", 1)),
                        "reason": str(item.get("reason", "")),
                    }
                    for item in results
                ],
            },
            user=user,
        )
        return out

    @app.post("/v3/chat/role-select")
    def v3_chat_role_select(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        conn = _open_conn()
        try:
            role_id = str(payload.get("role_id", "core")).strip().lower() or "core"
            user_id = str(user.get("username", "default"))
            # Easy XP: each explicit role switch/tap gives +1.
            new_xp = add_role_xp(conn, user_id=user_id, role_id=role_id, delta=1)
            profile = set_chat_profile(conn, values={"active_role": role_id}, user_id=user_id)
            out = {
                "role_id": role_id,
                "xp": new_xp,
                "stage": role_stage_from_xp(new_xp),
                "profile": profile,
            }
            _record_api_event(
                "chat.role_select",
                {"role_id": role_id, "xp": new_xp, "stage": str(out.get("stage", ""))},
                user=user,
            )
            return out
        finally:
            conn.close()

    def _resolve_chat_send_thread(conn: sqlite3.Connection, payload: dict[str, Any], message: str) -> str:
        thread_id = str(payload.get("thread_id", "")).strip()
        if thread_id:
            row = conn.execute("SELECT thread_id FROM thread WHERE thread_id = ?", (thread_id,)).fetchone()
            if row is None:
                thread_id = ""
        if not thread_id:
            thread = create_thread(conn, title="Chat Only Session", tags=["chat-ui"])
            thread_id = str(thread["thread_id"])

        try:
            create_message(conn, thread_id=thread_id, role="user", content=message)
        except sqlite3.IntegrityError:
            thread = create_thread(conn, title="Chat Only Session", tags=["chat-ui"])
            thread_id = str(thread["thread_id"])
            create_message(conn, thread_id=thread_id, role="user", content=message)
        return thread_id

    def _resolve_chat_send_context(
        conn: sqlite3.Connection,
        payload: dict[str, Any],
        user: dict[str, Any],
        message: str,
    ) -> dict[str, Any]:
        profile = get_chat_profile(conn, user_id=str(user.get("username", "default")))
        catalog = discover_model_catalog(root)
        catalog_rows = list(catalog.get("models", []))

        ui_surface = str(payload.get("ui_surface", "chat-ui")).strip().lower() or "chat-ui"
        active_role = (
            str(payload.get("active_role", "")).strip().lower()
            or str(profile.get("active_role", "core")).strip().lower()
            or "core"
        )
        utility_mode = resolve_role_utility_mode(
            root=root,
            role_id=active_role,
            pack_id=str(profile.get("card_pack", "")).strip(),
        )
        explicit_role_hint = str(payload.get("role_hint", "")).strip()
        behavior = role_behavior(active_role, utility_mode)
        effective_role = str(behavior.get("effective_role", active_role)).strip().lower() or active_role
        question_profile = classify_question(message)
        simple_qa = bool(question_profile.get("simple_qa", False))
        offline_mode = _resolve_offline_mode(user, payload=payload, profile=profile)
        if bool(behavior.get("enforce_offline_only")) and bool(behavior.get("enforce_allow_remote") is False):
            offline_mode = "strict"

        scope_prompt_mode = str(profile.get("scope_prompt_mode", "always")).strip().lower() or "always"
        answer_scope_default = _normalize_answer_scope(
            profile.get("default_answer_scope", "repo_grounded"),
            default="repo_grounded",
        )
        answer_scope = _normalize_answer_scope(
            payload.get("answer_scope", answer_scope_default),
            default=answer_scope_default,
        )
        scope_confirmed = _as_bool(payload.get("scope_confirmed", False), default=False)
        if active_role == "ranger" and scope_prompt_mode == "always" and not scope_confirmed:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Ranger lane requires Neon Compass scope confirmation before send. "
                    "Pick a scope and confirm, then send again."
                ),
            )
        if offline_mode == "strict" and answer_scope == "remote_allowed":
            raise HTTPException(
                status_code=400,
                detail=(
                    "strict offline mode blocks Neon Compass scope 'Remote Allowed'. "
                    "Switch offline mode to guided/off or pick Repo Grounded/General Local."
                ),
            )
        binary_gate: dict[str, Any] = {}
        if answer_scope == "remote_allowed":
            binary_gate = _assert_remote_foundry_gate(answer_scope)

        return {
            "profile": profile,
            "catalog_rows": catalog_rows,
            "ui_surface": ui_surface,
            "active_role": active_role,
            "utility_mode": utility_mode,
            "explicit_role_hint": explicit_role_hint,
            "behavior": behavior,
            "effective_role": effective_role,
            "question_profile": question_profile,
            "simple_qa": simple_qa,
            "offline_mode": offline_mode,
            "scope_prompt_mode": scope_prompt_mode,
            "answer_scope": answer_scope,
            "scope_confirmed": bool(scope_confirmed),
            "binary_gate": binary_gate,
        }

    def _resolve_chat_send_language_decision(
        payload: dict[str, Any],
        *,
        message: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        supplied = payload.get("decision_payload")
        if isinstance(supplied, dict):
            decision = dict(supplied)
        else:
            decision = build_language_model_decision(
                root=root,
                message=message,
                catalog_rows=list(context.get("catalog_rows", [])),
                offline_mode=str(context.get("offline_mode", "guided")),
                answer_scope=str(context.get("answer_scope", "repo_grounded")),
                profile=dict(context.get("profile", {})),
                payload=payload,
            )

        route = decision.get("provider_route")
        if not isinstance(route, dict):
            route = {}
            decision["provider_route"] = route
        route.setdefault("provider", "")
        route.setdefault("model", "")
        route.setdefault("base_url", "")
        route.setdefault(
            "model_key",
            f"{str(route.get('provider', '')).strip().lower()}|{str(route.get('model', '')).strip()}|{str(route.get('base_url', '')).strip()}",
        )
        decision.setdefault("selected_language", "Plain text")
        decision.setdefault("use_case_class", "simple")
        decision.setdefault("confidence", 0.6)
        decision.setdefault("workload_class", "general")
        if not isinstance(decision.get("language_rankings"), list):
            decision["language_rankings"] = []
        if not isinstance(decision.get("explanation_trace"), list):
            decision["explanation_trace"] = []
        decision.setdefault("override_applied", False)
        scope_default = str(context.get("answer_scope", "repo_grounded"))
        decision.setdefault("scope_recommendation", scope_default)
        decision.setdefault("scope_prompt_required", False)
        decision.setdefault("hybrid_mode", "local_only")
        decision.setdefault("scope_reason", "")
        decision.setdefault("scope_confidence", 0.0)
        if not isinstance(decision.get("scope_signals"), dict):
            decision["scope_signals"] = {}
        decision.setdefault("active_role", str(context.get("active_role", "core")))
        return decision

    def _resolve_chat_send_model(
        payload: dict[str, Any],
        profile: dict[str, Any],
        catalog_rows: list[dict[str, Any]],
        offline_mode: str,
        answer_scope: str,
        language_decision: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        decision_route = dict((language_decision or {}).get("provider_route", {}))
        model_key = str(payload.get("model_key", "")).strip() or str(profile.get("preferred_model", "")).strip()
        provider = str(payload.get("provider", "")).strip().lower() or str(decision_route.get("provider", "")).strip().lower()
        model = str(payload.get("model", "")).strip() or str(decision_route.get("model", "")).strip()
        base_url = str(payload.get("base_url", "")).strip() or str(decision_route.get("base_url", "")).strip()
        if not model_key:
            model_key = str(decision_route.get("model_key", "")).strip()

        if model_key:
            key_provider, key_model, key_base = _split_model_key(model_key)
            if key_provider and key_model:
                provider = provider or key_provider
                model = model or key_model
                base_url = base_url or key_base
        if not provider or not model:
            fallback_key = _default_model_key(catalog_rows, preferred_key=model_key)
            key_provider, key_model, key_base = _split_model_key(fallback_key)
            provider = provider or key_provider or "extractive"
            model = model or key_model or "extractive"
            base_url = base_url or key_base
            model_key = fallback_key

        if offline_mode == "strict" and provider in _REMOTE_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"strict offline mode blocks remote provider '{provider}'. "
                    "Choose a local/extractive model or switch offline mode to guided/off."
                ),
            )

        strict_default = answer_scope in {"repo_grounded", "general_local"}
        strict_local_models = _as_bool(payload.get("strict_local_models", strict_default), default=strict_default)
        allow_extractive_fallback = _as_bool(payload.get("allow_extractive_fallback", False), default=False)
        if offline_mode == "strict":
            strict_local_models = True
            allow_extractive_fallback = False
        if answer_scope in {"repo_grounded", "general_local"} and "allow_extractive_fallback" not in payload:
            allow_extractive_fallback = False
        if provider == "extractive" and strict_local_models and not allow_extractive_fallback:
            lm_choice = next(
                (
                    row
                    for row in catalog_rows
                    if str(row.get("provider", "")).strip().lower() == "lmstudio" and bool(row.get("reachable", False))
                ),
                None,
            )
            ollama_choice = next(
                (
                    row
                    for row in catalog_rows
                    if str(row.get("provider", "")).strip().lower() == "ollama" and bool(row.get("reachable", False))
                ),
                None,
            )
            if isinstance(lm_choice, dict):
                provider = "lmstudio"
                model = str(lm_choice.get("model", "")).strip() or "local-model"
                base_url = str(lm_choice.get("base_url", "")).strip() or "http://127.0.0.1:1234/v1"
            elif isinstance(ollama_choice, dict):
                provider = "ollama"
                model = str(ollama_choice.get("model", "")).strip() or "llama3.1:8b"
                base_url = str(ollama_choice.get("base_url", "")).strip() or "http://127.0.0.1:11434"
            else:
                provider = "ollama"
                model = str(profile.get("preferred_model_local", "")).strip() or "llama3.1:8b"
                base_url = base_url or "http://127.0.0.1:11434"
            model_key = f"{provider}|{model}|{base_url}"

        return {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "model_key": model_key,
            "strict_local_models": strict_local_models,
            "allow_extractive_fallback": allow_extractive_fallback,
        }

    def _build_chat_send_metadata(
        payload: dict[str, Any],
        user: dict[str, Any],
        message: str,
        context: dict[str, Any],
        model_state: dict[str, Any],
        language_decision: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        behavior = dict(context.get("behavior", {}))
        answer_scope = str(context.get("answer_scope", "repo_grounded"))
        offline_mode = str(context.get("offline_mode", "guided"))
        active_role = str(context.get("active_role", "core")).strip().lower() or "core"
        role_hint = str(context.get("explicit_role_hint", "")).strip() or str(behavior.get("role_hint", ""))
        if active_role == "hacker":
            role_hint = (
                "Hacker lane is code-only: prioritize commands, patches, scripts, and concise technical steps. "
                "Avoid non-technical conversational filler."
            )
        elif active_role == "samurai":
            role_hint = (
                "Samurai lane converts verbal requests into implementation: infer the right stack, produce runnable code, "
                "and include short execution checks."
            )
        default_offline_only = answer_scope != "remote_allowed"
        default_allow_remote = answer_scope == "remote_allowed"
        metadata = {
            "question": message,
            "top_k": int(payload.get("top_k", int(behavior.get("top_k", 5)))),
            "offline_only": _as_bool(payload.get("offline_only", default_offline_only), default=default_offline_only),
            "allow_remote": _as_bool(payload.get("allow_remote", default_allow_remote), default=default_allow_remote),
            "offline_mode": offline_mode,
            "answer_scope": answer_scope,
            "scope_confirmed": bool(context.get("scope_confirmed", False)),
            "strict_local_models": bool(model_state.get("strict_local_models", False)),
            "allow_extractive_fallback": bool(model_state.get("allow_extractive_fallback", False)),
            "local_attempts_max": int(payload.get("local_attempts_max", 3)),
            "preferred_provider": str(model_state.get("provider", "")),
            "user_id": str(user.get("username", "api-user")),
            "simple_qa": bool(context.get("simple_qa", False)),
            "question_profile": context.get("question_profile", {}),
            "binary_gate": dict(context.get("binary_gate", {})),
            "chat_ui": {
                "profile": context.get("profile", {}),
                "selected_model_key": str(model_state.get("model_key", "")),
                "language_decision": dict(language_decision or {}),
                "role": {
                    "active_role": active_role,
                    "effective_role": str(context.get("effective_role", "core")),
                    "utility_mode": str(context.get("utility_mode", "balanced")),
                    "role_hint": role_hint,
                    "ui_mode": str(behavior.get("ui_mode", "balanced")),
                    "surface": str(context.get("ui_surface", "chat-ui")),
                },
                "scope": {
                    "prompt_mode": str(context.get("scope_prompt_mode", "always")),
                    "answer_scope": answer_scope,
                    "scope_confirmed": bool(context.get("scope_confirmed", False)),
                },
            },
        }
        if isinstance(language_decision, dict):
            metadata["selected_language"] = str(language_decision.get("selected_language", "")).strip()
            metadata["use_case_class"] = str(language_decision.get("use_case_class", "")).strip()
            metadata["workload_class"] = str(language_decision.get("workload_class", "")).strip()
            metadata["scope_recommendation"] = str(language_decision.get("scope_recommendation", answer_scope)).strip()
            metadata["hybrid_mode"] = str(language_decision.get("hybrid_mode", "local_only")).strip()
            metadata["scope_prompt_required"] = bool(language_decision.get("scope_prompt_required", False))
            try:
                metadata["language_decision_confidence"] = float(language_decision.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                metadata["language_decision_confidence"] = 0.0
        top_k_min = int(behavior.get("top_k_min", 0) or 0)
        if top_k_min > 0 and int(metadata.get("top_k", 1)) < top_k_min:
            metadata["top_k"] = top_k_min
        if answer_scope == "repo_grounded":
            metadata["offline_only"] = True
            metadata["allow_remote"] = False
            metadata["top_k"] = max(6, int(metadata.get("top_k", 6)))
            metadata["strict_local_models"] = True
            metadata["allow_extractive_fallback"] = False
        elif answer_scope == "general_local":
            metadata["offline_only"] = True
            metadata["allow_remote"] = False
            metadata["strict_local_models"] = True
        elif answer_scope == "remote_allowed":
            metadata["offline_only"] = False

        if offline_mode == "strict":
            metadata["offline_only"] = True
            metadata["allow_remote"] = False
        if behavior.get("enforce_offline_only") is True:
            metadata["offline_only"] = True
            metadata["offline_mode"] = "strict"
        if behavior.get("enforce_allow_remote") is False:
            metadata["allow_remote"] = False

        provider = str(model_state.get("provider", ""))
        model = str(model_state.get("model", ""))
        base_url = str(model_state.get("base_url", ""))
        if provider in {"openai", "codex"}:
            metadata["codex_model"] = model
            metadata["codex_base_url"] = base_url or "https://api.openai.com/v1"
        return metadata

    def _finalize_chat_send_result(
        conn: sqlite3.Connection,
        result: dict[str, Any],
        user: dict[str, Any],
        message: str,
        thread_id: str,
        context: dict[str, Any],
        model_state: dict[str, Any],
        metadata: dict[str, Any],
        language_decision: dict[str, Any] | None = None,
        multi_instance_route: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_row = dict(result.get("run", {}))
        task = dict(result.get("taskmaster", {}))
        assistant_message = dict(result.get("assistant_message", {}))
        answer = str(assistant_message.get("content", "")).strip() or str(task.get("answer", "")).strip()
        citations = list(result.get("citations", []))
        provider_used = str(task.get("provider_used", ""))
        evidence_available = bool(citations)
        if not evidence_available:
            lowered = answer.lower()
            risky_tokens = (
                "according to",
                "source:",
                "sources:",
                "citation",
                "local evidence",
                "provided context",
            )
            if any(tok in lowered for tok in risky_tokens):
                answer = (
                    f"{answer}\n\n"
                    "Note: This run had no verified citations in local context. "
                    "Treat specific source claims as unverified."
                )

        conf_score = 0.25
        if bool(task.get("ok", True)):
            conf_score += 0.25
        if provider_used in {"ollama", "lmstudio"}:
            conf_score += 0.15
        elif provider_used in {"codex", "openai"}:
            conf_score += 0.1
        elif provider_used in {"extractive", "builtin_simple_qa"}:
            conf_score += 0.05
        if evidence_available:
            conf_score += 0.3
        conf_score = max(0.05, min(0.98, conf_score))
        confidence_label = "high" if conf_score >= 0.8 else ("medium" if conf_score >= 0.6 else "low")

        answer_scope = str(context.get("answer_scope", "repo_grounded"))
        active_role = str(context.get("active_role", "core"))
        effective_role = str(context.get("effective_role", active_role))
        utility_mode = str(context.get("utility_mode", "balanced"))
        offline_mode = str(context.get("offline_mode", "guided"))
        scope_confirmed = bool(context.get("scope_confirmed", False))
        question_profile = dict(context.get("question_profile", {}))
        behavior = dict(context.get("behavior", {}))

        provenance = {
            "answer_scope": answer_scope,
            "scope_confirmed": scope_confirmed,
            "effective_role": effective_role,
            "utility_mode": utility_mode,
            "provider_used": provider_used,
            "evidence_available": evidence_available,
            "citation_count": len(citations),
            "source_type": "citations" if evidence_available else ("model_output" if provider_used else "none"),
        }
        next_step_options = list(task.get("next_steps", []))
        if not evidence_available:
            if answer_scope != "repo_grounded":
                next_step_options.append("Switch Neon Compass scope to Repo Grounded for citation-backed local answers.")
            next_step_options.append("Run Retriever or Scientist lane for deeper evidence retrieval.")
        if offline_mode == "strict" and answer_scope == "remote_allowed":
            next_step_options.append("Switch offline mode to guided/off to enable Remote Allowed scope.")

        role_gain = _role_xp_delta_for_send(
            provider=str(model_state.get("provider", "")),
            model=str(model_state.get("model", "")),
            message=message,
            top_k=int(metadata.get("top_k", 5)),
            ok=bool(task.get("ok", True)),
        )
        role_xp_total = add_role_xp(
            conn,
            user_id=str(user.get("username", "default")),
            role_id=active_role,
            delta=role_gain,
        )
        profile_updates: dict[str, Any] = {"active_role": active_role}
        if scope_confirmed:
            profile_updates["default_answer_scope"] = answer_scope
        set_chat_profile(conn, values=profile_updates, user_id=str(user.get("username", "default")))

        out = {
            "thread_id": thread_id,
            "run_id": str(run_row.get("run_id", "")),
            "run_status": str(run_row.get("status", "")),
            "assistant_message": assistant_message,
            "answer": answer,
            "ok": bool(task.get("ok", True)),
            "failure_code": str(task.get("failure_code", "")),
            "next_steps": list(task.get("next_steps", [])),
            "next_step_options": next_step_options,
            "provider_used": provider_used,
            "model_selected": str(model_state.get("model", "")),
            "model_key": str(model_state.get("model_key", "")),
            "requires_action": list(result.get("requires_action", [])),
            "step_summary": [
                {"step_index": row.get("step_index"), "step_type": row.get("step_type"), "status": row.get("status")}
                for row in list(result.get("steps", []))
            ],
            "role_applied": active_role,
            "effective_role": effective_role,
            "utility_mode": utility_mode,
            "ui_mode_applied": str(behavior.get("ui_mode", "balanced")),
            "ops_hint": str(behavior.get("ops_hint", "balanced")),
            "offline_mode": str(metadata.get("offline_mode", offline_mode)),
            "answer_scope": answer_scope,
            "scope_confirmed": scope_confirmed,
            "provenance": provenance,
            "confidence": {"label": confidence_label, "score": round(conf_score, 3)},
            "question_class": question_profile,
            "language_decision": dict(language_decision or {}),
            "binary_gate": dict(context.get("binary_gate", {})),
            "role_xp_gain": role_gain,
            "role_xp_total": role_xp_total,
            "role_stage": role_stage_from_xp(role_xp_total),
        }
        if isinstance(multi_instance_route, dict) and bool(multi_instance_route.get("ok", False)):
            lane_selected = dict(multi_instance_route.get("lane_selected", {}))
            parser_payload = dict(multi_instance_route.get("parser", {}))
            out["multi_instance"] = {
                "directive": str(multi_instance_route.get("directive", "")),
                "lane_selected": lane_selected,
                "task_assigned": str(multi_instance_route.get("task_assigned", "")),
                "estimated_tokens": int(multi_instance_route.get("estimated_tokens", 0) or 0),
                "parser": {
                    "workstreams": list(parser_payload.get("workstreams", [])),
                    "complexity": str(parser_payload.get("complexity", "")),
                    "recommended_parallelism": int(parser_payload.get("recommended_parallelism", 0) or 0),
                    "default_task_label": str(parser_payload.get("default_task_label", "")),
                },
            }
            out["token_telemetry"] = dict(multi_instance_route.get("token_telemetry", {}))
        _record_api_event(
            "chat.send.result",
            {
                "thread_id": thread_id,
                "run_id": str(out.get("run_id", "")),
                "run_status": str(out.get("run_status", "")),
                "ok": bool(out.get("ok", False)),
                "active_role": active_role,
                "effective_role": effective_role,
                "utility_mode": utility_mode,
                "offline_mode": str(out.get("offline_mode", offline_mode)),
                "answer_scope": answer_scope,
                "provider_used": provider_used,
                "confidence": dict(out.get("confidence", {})),
                "selected_language": str((language_decision or {}).get("selected_language", "")),
                "citation_count": len(citations),
                "step_summary": list(out.get("step_summary", [])),
                "lane_instance_id": str(
                    (out.get("multi_instance", {}).get("lane_selected", {}) if isinstance(out.get("multi_instance"), dict) else {}).get("instance_id", "")
                ),
            },
            user=user,
        )
        return out

    @app.post("/v3/chat/send")
    def v3_chat_send(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        conn = _open_conn()
        stage = "init"
        multi_instance_route: dict[str, Any] = {}
        try:
            stage = "read_message"
            message = str(payload.get("message", "")).strip()
            if not message:
                raise HTTPException(status_code=400, detail="message is required")

            if _as_bool(payload.get("route_multi_instance", True), default=True):
                try:
                    multi_instance_route = route_message_to_lane(
                        root,
                        message=message,
                        task_label=str(payload.get("task_label", "")).strip(),
                        requested_lane_id=str(payload.get("requested_lane_id", "")).strip(),
                        apply_usage=_as_bool(payload.get("apply_multi_instance_usage", True), default=True),
                        estimated_tokens_override=int(payload.get("estimated_tokens_override", 0) or 0),
                    )
                    if bool(multi_instance_route.get("ok", False)):
                        normalized = str(multi_instance_route.get("normalized_message", "")).strip()
                        if normalized:
                            message = normalized
                except Exception:
                    # Keep chat send resilient; routing metadata is additive.
                    multi_instance_route = {}

            stage = "resolve_thread"
            thread_id = _resolve_chat_send_thread(conn, payload, message)

            stage = "resolve_model"
            stage = "resolve_context"
            context = _resolve_chat_send_context(conn, payload, user, message)
            profile = dict(context.get("profile", {}))
            stage = "resolve_language_decision"
            language_decision = _resolve_chat_send_language_decision(payload, message=message, context=context)
            if (
                str(context.get("scope_prompt_mode", "always")).strip().lower() == "always"
                and not bool(context.get("scope_confirmed", False))
                and bool(language_decision.get("scope_prompt_required", False))
            ):
                recommended_scope = str(language_decision.get("scope_recommendation", context.get("answer_scope", "repo_grounded")))
                scope_reason = str(language_decision.get("scope_reason", "")).strip()
                reason_suffix = f" ({scope_reason})." if scope_reason else "."
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Neon Compass scope confirmation is required for this request. "
                        f"Recommended scope: {recommended_scope}{reason_suffix} "
                        "Confirm scope and send again."
                    ),
                )
            model_state = _resolve_chat_send_model(
                payload,
                profile=profile,
                catalog_rows=list(context.get("catalog_rows", [])),
                offline_mode=str(context.get("offline_mode", "guided")),
                answer_scope=str(context.get("answer_scope", "repo_grounded")),
                language_decision=language_decision,
            )

            stage = "ensure_endpoint"
            endpoint_id = ensure_endpoint(
                conn,
                provider=str(model_state.get("provider", "")),
                base_url=str(model_state.get("base_url", "")),
                chat_model=str(model_state.get("model", "")),
            )

            stage = "build_metadata"
            metadata = _build_chat_send_metadata(
                payload,
                user,
                message,
                context,
                model_state,
                language_decision=language_decision,
            )
            _record_api_event(
                "chat.send.request",
                {
                    "thread_id": thread_id,
                    "active_role": str(context.get("active_role", "core")),
                    "effective_role": str(context.get("effective_role", "core")),
                    "utility_mode": str(context.get("utility_mode", "balanced")),
                    "offline_mode": str(context.get("offline_mode", "guided")),
                    "answer_scope": str(context.get("answer_scope", "repo_grounded")),
                    "scope_confirmed": bool(context.get("scope_confirmed", False)),
                    "provider": str(model_state.get("provider", "")),
                    "model": str(model_state.get("model", "")),
                    "selected_language": str(language_decision.get("selected_language", "")),
                    "use_case_class": str(language_decision.get("use_case_class", "")),
                },
                user=user,
            )

            stage = "create_run"
            run = create_run(conn, thread_id=thread_id, endpoint_id=endpoint_id, metadata=metadata)
            stage = "execute_run"
            result = execute_run(
                root=root,
                conn=conn,
                run_id=str(run["run_id"]),
                actor=str(user.get("username", "api-user")),
                allow_remote=bool(metadata.get("allow_remote", False)),
            )
            stage = "build_response"
            return _finalize_chat_send_result(
                conn,
                result=result,
                user=user,
                message=message,
                thread_id=thread_id,
                context=context,
                model_state=model_state,
                metadata=metadata,
                language_decision=language_decision,
                multi_instance_route=multi_instance_route,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"{stage}: {exc}") from exc
        finally:
            conn.close()

    @app.get("/v3/chat/history/{thread_id}")
    def v3_chat_history(thread_id: str, limit: int = 120, _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        conn = _open_conn()
        try:
            row = conn.execute("SELECT thread_id FROM thread WHERE thread_id = ?", (thread_id.strip(),)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"thread not found: {thread_id}")
            rows = conn.execute(
                """
                SELECT message_id, role, content, created_at
                FROM message
                WHERE thread_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (thread_id.strip(), max(1, int(limit))),
            ).fetchall()
            rows = list(rows)[::-1]
            return {
                "thread_id": thread_id,
                "messages": [
                    {
                        "message_id": str(item["message_id"]),
                        "role": str(item["role"]),
                        "content": str(item["content"]),
                        "created_at": str(item["created_at"]),
                    }
                    for item in rows
                ],
            }
        finally:
            conn.close()
