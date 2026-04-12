"""Unified capability readiness and guided remediation orchestration."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NOTEBOOK_MODULES = ["notebook", "jupyterlab", "ipykernel", "pandas", "sklearn"]

ACTION_FIX_ALL = "fix_all_capabilities"
ACTION_REPAIR_CPP = "repair_cpp"
ACTION_REPAIR_NOTEBOOK = "repair_notebook_runtime"
ACTION_START_LM_STUDIO = "start_lm_studio"
ACTION_START_OLLAMA = "start_ollama"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip()


def _run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout_sec: int = 120,
) -> dict[str, Any]:
    started = _utc_now()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=max(3, int(timeout_sec)),
            check=False,
        )
        return {
            "started_at": started,
            "ended_at": _utc_now(),
            "command": command,
            "exit_code": int(proc.returncode),
            "ok": proc.returncode == 0,
            "stdout": str(proc.stdout or "")[-12000:],
            "stderr": str(proc.stderr or "")[-8000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "started_at": started,
            "ended_at": _utc_now(),
            "command": command,
            "exit_code": 124,
            "ok": False,
            "stdout": str(exc.stdout or "")[-12000:],
            "stderr": str(exc.stderr or "")[-8000:] or "command timed out",
            "timed_out": True,
        }


def _append_action_log(root: Path, row: dict[str, Any]) -> None:
    log_dir = root / ".ccbs" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "capability-orchestrator-actions.jsonl"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def _write_resume_marker(root: Path, marker: dict[str, Any]) -> None:
    state_dir = root / ".ccbs" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    marker_path = state_dir / "capability-orchestrator-resume.json"
    marker_payload = dict(marker)
    marker_payload.setdefault("updated_at", _utc_now())
    marker_path.write_text(json.dumps(marker_payload, indent=2), encoding="utf-8")


def _http_json(url: str, timeout_s: float = 1.25, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url=url, method="GET", headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(req, timeout=max(0.2, float(timeout_s))) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
    payload = json.loads(body) if body.strip() else {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _endpoint_reachable(host: str, port: int, timeout_s: float = 1.0, attempts: int = 2) -> bool:
    for _ in range(max(1, int(attempts))):
        try:
            with socket.create_connection((host, int(port)), timeout=max(0.2, float(timeout_s))):
                return True
        except OSError:
            continue
    return False


def _resolve_lmstudio_api_key() -> str:
    for name in ("LM_API_TOKEN", "LMSTUDIO_API_KEY", "LM_STUDIO_API_KEY"):
        value = str(os.environ.get(name, "")).strip()
        if value:
            return value
    return ""


def _normalize_lmstudio_base_url(raw: str) -> str:
    value = str(raw or "").strip().rstrip("/")
    if not value:
        return ""
    if value.endswith("/v1/models"):
        return value[:-7]
    if value.endswith("/v1"):
        return value
    return f"{value}/v1"


def _wsl_host_candidate() -> str:
    if not str(os.environ.get("WSL_DISTRO_NAME", "")).strip():
        return ""
    resolv = Path("/etc/resolv.conf")
    if not resolv.exists():
        return ""
    for raw in resolv.read_text(encoding="utf-8", errors="replace").splitlines():
        line = str(raw).strip()
        if not line.startswith("nameserver "):
            continue
        host = line.split(None, 1)[1].strip()
        if host:
            return host
    return ""


def _lmstudio_base_candidates() -> list[str]:
    candidates: list[str] = []
    explicit = _normalize_lmstudio_base_url(str(os.environ.get("CCBS_LMSTUDIO_BASE_URL", "")))
    if explicit:
        candidates.append(explicit)
    candidates.append("http://127.0.0.1:1234/v1")

    explicit_host = str(os.environ.get("CCBS_LMSTUDIO_HOST", "")).strip()
    if explicit_host:
        candidates.append(_normalize_lmstudio_base_url(f"http://{explicit_host}:1234"))

    wsl_host = _wsl_host_candidate()
    if wsl_host:
        candidates.append(_normalize_lmstudio_base_url(f"http://{wsl_host}:1234"))

    deduped: list[str] = []
    for item in candidates:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _resolve_python(root: Path) -> str:
    candidates: list[Path] = []
    if os.name == "nt":
        candidates.extend(
            [
                root / ".venv-clean" / "Scripts" / "python.exe",
                root / ".venv-1" / "Scripts" / "python.exe",
                root / ".venv-win" / "Scripts" / "python.exe",
                root / ".venv" / "Scripts" / "python.exe",
            ]
        )
    else:
        candidates.extend(
            [
                root / ".venv-wsl" / "bin" / "python",
                root / ".venv" / "bin" / "python",
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(sys.executable or shutil.which("python") or shutil.which("python3") or "python")


def _python_notebook_status(root: Path) -> dict[str, Any]:
    selected_python = _resolve_python(root)
    app_python = str(sys.executable or "")
    launcher_python = ""
    if os.name == "nt":
        probe = _run_command(["py", "-3.12", "-c", "import sys; print(sys.executable)"], cwd=root, timeout_sec=20)
        if probe.get("ok"):
            launcher_python = str(probe.get("stdout", "")).strip().splitlines()[-1].strip()
    else:
        py_bin = shutil.which("python3") or shutil.which("python")
        if py_bin:
            probe = _run_command([py_bin, "-c", "import sys; print(sys.executable)"], cwd=root, timeout_sec=20)
            if probe.get("ok"):
                launcher_python = str(probe.get("stdout", "")).strip().splitlines()[-1].strip()

    notebook_probe = (
        "import importlib.util as u, json; "
        f"mods={NOTEBOOK_MODULES!r}; "
        "missing=[m for m in mods if u.find_spec(m) is None]; "
        "print(json.dumps({'missing': missing, 'ok': len(missing)==0}))"
    )
    probe = _run_command([selected_python, "-c", notebook_probe], cwd=root, timeout_sec=40)
    missing: list[str] = []
    notebook_ok = False
    if probe.get("ok"):
        try:
            parsed = json.loads(str(probe.get("stdout", "")).strip().splitlines()[-1])
            if isinstance(parsed, dict):
                missing = [str(x) for x in parsed.get("missing", [])]
                notebook_ok = bool(parsed.get("ok", False))
        except Exception:  # noqa: BLE001
            missing = list(NOTEBOOK_MODULES)
            notebook_ok = False
    else:
        missing = list(NOTEBOOK_MODULES)
        notebook_ok = False

    kernel_probe = _run_command(
        [selected_python, "-m", "jupyter", "kernelspec", "list", "--json"],
        cwd=root,
        timeout_sec=35,
    )
    kernel_registered = False
    if kernel_probe.get("ok"):
        try:
            payload = json.loads(str(kernel_probe.get("stdout", "")).strip())
            specs = payload.get("kernelspecs", {}) if isinstance(payload, dict) else {}
            if isinstance(specs, dict):
                kernel_registered = "ccbs-pro" in specs
        except Exception:  # noqa: BLE001
            kernel_registered = False

    mismatch = bool(launcher_python and selected_python and Path(launcher_python) != Path(selected_python))
    status = "ready" if notebook_ok and kernel_registered else ("partial_install" if notebook_ok else "missing")
    issues: list[str] = []
    if missing:
        issues.append(f"missing_notebook_modules:{','.join(missing)}")
    if not kernel_registered:
        issues.append("kernel_not_registered:ccbs-pro")
    if mismatch:
        issues.append("interpreter_mismatch")

    return {
        "status": status,
        "ready": status == "ready",
        "python_executable": selected_python,
        "app_python": app_python,
        "launcher_python": launcher_python,
        "interpreter_mismatch": mismatch,
        "missing_modules": missing,
        "kernel_registered": kernel_registered,
        "issues": issues,
        "state": (
            "installed_not_running" if notebook_ok and not kernel_registered else ("missing" if missing else "ready")
        ),
    }


def _find_vswhere() -> str:
    paths = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
    ]
    for path in paths:
        if path.exists():
            return str(path)
    return ""


def _windows_cpp_status() -> dict[str, Any]:
    if os.name != "nt":
        return {
            "status": "blocked",
            "state": "blocked",
            "ready": False,
            "reason": "windows_host_required",
            "issues": ["windows_host_required"],
        }

    vswhere = _find_vswhere()
    vs_install = ""
    if vswhere:
        probe = _run_command(
            [
                vswhere,
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Workload.VCTools",
                "-property",
                "installationPath",
            ],
            timeout_sec=20,
        )
        if probe.get("ok"):
            vs_install = str(probe.get("stdout", "")).strip().splitlines()[-1].strip()

    cl_path = shutil.which("cl")
    cmake_path = shutil.which("cmake")
    if not cmake_path:
        common = [
            Path(os.environ.get("ProgramFiles", "")) / "CMake" / "bin" / "cmake.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "CMake" / "bin" / "cmake.exe",
        ]
        for candidate in common:
            if candidate.exists():
                cmake_path = str(candidate)
                break

    has_vs_toolchain = bool(vs_install)
    cl_found = bool(cl_path)
    cmake_found = bool(cmake_path)
    if cl_found and cmake_found:
        status = "ready"
    elif has_vs_toolchain and not cl_found:
        status = "path_refresh_required"
    elif has_vs_toolchain or cmake_found:
        status = "partial_install"
    else:
        status = "missing"
    issues: list[str] = []
    if not cl_found:
        issues.append("missing_cl")
    if not cmake_found:
        issues.append("missing_cmake")
    if status == "path_refresh_required":
        issues.append("refresh_terminal_or_reopen_required")

    return {
        "status": status,
        "state": "ready" if status == "ready" else ("missing" if status == "missing" else "blocked"),
        "ready": status == "ready",
        "vswhere": vswhere,
        "vs_installation": vs_install,
        "cl": str(cl_path or ""),
        "cmake": str(cmake_path or ""),
        "issues": issues,
    }


def _resolve_wsl_distro(wsl_exe: str) -> str:
    probe = _run_command([wsl_exe, "-l", "-q"], timeout_sec=25)
    if not probe.get("ok"):
        return "Ubuntu"
    rows = [_clean_text(x) for x in str(probe.get("stdout", "")).splitlines() if _clean_text(x)]
    ubuntu = next((x for x in rows if x.lower().startswith("ubuntu")), "")
    return ubuntu or (rows[0] if rows else "Ubuntu")


def _wsl_cpp_status(root: Path) -> dict[str, Any]:
    wsl_exe = shutil.which("wsl.exe") or shutil.which("wsl")
    if not wsl_exe:
        return {
            "status": "blocked",
            "state": "blocked",
            "ready": False,
            "reason": "wsl_unavailable",
            "issues": ["wsl_unavailable"],
            "distro": "",
        }
    distro = _resolve_wsl_distro(wsl_exe)
    distro = _clean_text(distro) or "Ubuntu"
    probe_script = (
        "set -e; "
        "echo HAS_GPP=$(command -v g++ >/dev/null && echo 1 || echo 0); "
        "echo HAS_CLANG=$(command -v clang++ >/dev/null && echo 1 || echo 0); "
        "echo HAS_CMAKE=$(command -v cmake >/dev/null && echo 1 || echo 0); "
        "echo GPP=$(command -v g++ || true); "
        "echo CLANG=$(command -v clang++ || true); "
        "echo CMAKE=$(command -v cmake || true)"
    )
    probe = _run_command([wsl_exe, "-d", distro, "--", "bash", "-lc", probe_script], cwd=root, timeout_sec=35)
    if not probe.get("ok"):
        return {
            "status": "blocked",
            "state": "blocked",
            "ready": False,
            "reason": "wsl_probe_failed",
            "issues": ["wsl_probe_failed"],
            "distro": distro,
            "stderr": str(probe.get("stderr", ""))[:600],
        }

    values: dict[str, str] = {}
    for line in str(probe.get("stdout", "")).splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()
    has_compiler = values.get("HAS_GPP") == "1" or values.get("HAS_CLANG") == "1"
    has_cmake = values.get("HAS_CMAKE") == "1"

    smoke_ok = False
    smoke_err = ""
    if has_compiler and has_cmake:
        smoke_script = (
            "set -e; "
            "tmp=$(mktemp -d); "
            "cat > \"\\$tmp/main.cpp\" <<'EOF'\n"
            "#include <iostream>\n"
            "int main(){ std::cout << \"ccbs-cpp-ok\\n\"; return 0; }\n"
            "EOF\n"
            "if command -v g++ >/dev/null; then CC=g++; else CC=clang++; fi; "
            "\\$CC \"\\$tmp/main.cpp\" -std=c++17 -O2 -o \"\\$tmp/main\"; "
            "\"\\$tmp/main\""
        )
        smoke = _run_command([wsl_exe, "-d", distro, "--", "bash", "-lc", smoke_script], cwd=root, timeout_sec=45)
        smoke_ok = bool(smoke.get("ok", False))
        smoke_err = str(smoke.get("stderr", ""))[:600]

    if has_compiler and has_cmake and smoke_ok:
        status = "ready"
    elif has_compiler or has_cmake:
        status = "partial_install"
    else:
        status = "missing"
    issues: list[str] = []
    if not has_compiler:
        issues.append("missing_compiler")
    if not has_cmake:
        issues.append("missing_cmake")
    if has_compiler and has_cmake and not smoke_ok:
        issues.append("compile_smoke_failed")

    return {
        "status": status,
        "state": "ready" if status == "ready" else "missing",
        "ready": status == "ready",
        "distro": distro,
        "wsl_exe": wsl_exe,
        "gpp": values.get("GPP", ""),
        "clangpp": values.get("CLANG", ""),
        "cmake": values.get("CMAKE", ""),
        "compile_smoke_ok": smoke_ok,
        "compile_smoke_error": smoke_err,
        "issues": issues,
    }


def _find_lmstudio_executable() -> str:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "LM Studio" / "LM Studio.exe",
        Path(os.environ.get("ProgramFiles", "")) / "LM Studio" / "LM Studio.exe",
        Path.home() / "AppData" / "Local" / "Programs" / "LM Studio" / "LM Studio.exe",
    ]
    for item in candidates:
        if item.exists():
            return str(item)
    return ""


def _lmstudio_process_running() -> bool:
    if os.name == "nt":
        probe = _run_command(["tasklist", "/FI", "IMAGENAME eq LM Studio.exe"], timeout_sec=15)
        if not probe.get("ok"):
            return False
        text = str(probe.get("stdout", "")).lower()
        return "lm studio.exe" in text
    if str(os.environ.get("WSL_DISTRO_NAME", "")).strip():
        tasklist_exe = Path("/mnt/c/Windows/System32/tasklist.exe")
        if tasklist_exe.exists():
            probe = _run_command([str(tasklist_exe), "/FI", "IMAGENAME eq LM Studio.exe"], timeout_sec=15)
            if probe.get("ok"):
                text = str(probe.get("stdout", "")).lower()
                if "lm studio.exe" in text:
                    return True
    pgrep = shutil.which("pgrep")
    if pgrep:
        probe = _run_command([pgrep, "-f", "lm studio"], timeout_sec=15)
        return bool(probe.get("ok"))
    return False


def _lmstudio_status() -> dict[str, Any]:
    exe = _find_lmstudio_executable()
    installed = bool(exe)
    process_running = _lmstudio_process_running()
    api_reachable = False
    model_count = 0
    api_error = ""
    selected_base_url = ""
    api_requires_token = False
    token = _resolve_lmstudio_api_key()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    for base_url in _lmstudio_base_candidates():
        parsed = urllib.parse.urlparse(base_url)
        host = str(parsed.hostname or "").strip()
        if not host:
            continue
        port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
        if not _endpoint_reachable(host, port, attempts=2):
            continue
        api_reachable = True
        selected_base_url = base_url
        try:
            payload = _http_json(f"{base_url}/models", timeout_s=1.6, headers=headers)
        except Exception as exc:  # noqa: BLE001
            api_error = str(exc)
            continue

        data = payload.get("data")
        if isinstance(data, list):
            model_count = len([row for row in data if isinstance(row, dict)])
            if model_count > 0:
                break
            continue

        error_obj = payload.get("error", {})
        if isinstance(error_obj, dict):
            code = str(error_obj.get("code", "")).strip().lower()
            message = str(error_obj.get("message", "")).strip().lower()
            if code == "invalid_api_key" or "api token is required" in message:
                api_requires_token = True
                api_error = "lmstudio_api_token_required"
                break
            if message:
                api_error = message
                continue
        api_error = "invalid_lmstudio_response"

    if api_reachable and model_count > 0:
        status = "ready"
    elif api_reachable and api_requires_token:
        status = "running_auth_required"
    elif api_reachable:
        status = "running_no_models"
    elif installed and process_running:
        status = "installed_not_running"
    elif installed:
        status = "installed_not_running"
    else:
        status = "missing"
    issues: list[str] = []
    if status == "missing":
        issues.append("lmstudio_not_installed")
    if status == "installed_not_running":
        issues.append("lmstudio_server_not_running")
    if status == "running_no_models":
        issues.append("lmstudio_no_models")
    if status == "running_auth_required":
        issues.append("lmstudio_auth_required")
    if api_error:
        issues.append("lmstudio_api_error")

    return {
        "status": status,
        "state": (
            "ready"
            if status == "ready"
            else (
                "installed_not_running"
                if status in {"installed_not_running", "running_no_models", "running_auth_required"}
                else "missing"
            )
        ),
        "ready": status == "ready",
        "installed": installed,
        "running_process": process_running,
        "api_reachable": api_reachable,
        "model_count": model_count,
        "executable": exe,
        "api_error": api_error,
        "api_requires_token": api_requires_token,
        "issues": issues,
        "base_url": selected_base_url or "http://127.0.0.1:1234/v1",
    }


def _ollama_status() -> dict[str, Any]:
    exe = shutil.which("ollama")
    if os.name == "nt" and not exe:
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.exists():
            exe = str(candidate)
    installed = bool(exe)
    api_reachable = _endpoint_reachable("127.0.0.1", 11434, attempts=2)
    model_count = 0
    api_error = ""
    if api_reachable:
        try:
            payload = _http_json("http://127.0.0.1:11434/api/tags", timeout_s=1.6)
            models = payload.get("models", [])
            if isinstance(models, list):
                model_count = len(models)
        except Exception as exc:  # noqa: BLE001
            api_error = str(exc)

    if api_reachable and model_count > 0:
        status = "ready"
    elif api_reachable:
        status = "running_no_models"
    elif installed:
        status = "installed_not_running"
    else:
        status = "missing"
    return {
        "status": status,
        "state": (
            "ready"
            if status == "ready"
            else ("installed_not_running" if status in {"installed_not_running", "running_no_models"} else "missing")
        ),
        "ready": status == "ready",
        "installed": installed,
        "api_reachable": api_reachable,
        "model_count": model_count,
        "executable": str(exe or ""),
        "api_error": api_error,
        "issues": [] if status == "ready" else [f"ollama_{status}"],
        "base_url": "http://127.0.0.1:11434",
    }


def _vscode_status(root: Path) -> dict[str, Any]:
    code_cli = shutil.which("code") or shutil.which("code.cmd")
    managed_cfg = root / "config" / "vscode-extensions.txt"
    wanted_exts: list[str] = []
    if managed_cfg.exists():
        for raw in managed_cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            line = str(raw).strip().lstrip("\ufeff")
            if line and not line.startswith("#"):
                wanted_exts.append(line.lower())
    installed_exts: list[str] = []
    missing_managed: list[str] = []
    error = ""
    if code_cli:
        probe = _run_command([str(code_cli), "--list-extensions"], cwd=root, timeout_sec=25)
        if probe.get("ok"):
            installed_exts = [x.strip().lower() for x in str(probe.get("stdout", "")).splitlines() if x.strip()]
            missing_managed = [x for x in wanted_exts if x not in installed_exts]
        else:
            error = str(probe.get("stderr", "") or probe.get("stdout", "")).strip()[:500]
    else:
        missing_managed = list(wanted_exts)
        error = "vscode_cli_not_found"
    return {
        "status": "ready" if bool(code_cli) and not missing_managed and not error else "partial_install",
        "state": "ready" if bool(code_cli) and not missing_managed and not error else "missing",
        "ready": bool(code_cli) and not missing_managed and not error,
        "code_cli": str(code_cli or ""),
        "managed_total": len(wanted_exts),
        "missing_managed": missing_managed,
        "error": error,
    }


def _build_fix_actions(report: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = [
        {
            "action_id": ACTION_FIX_ALL,
            "label": "Fix All Capabilities",
            "description": "Run guided orchestration across C++, notebook runtime, and local providers.",
            "lane": "all",
            "requires_approval": True,
            "requires_network": True,
            "state": "available",
        }
    ]
    windows_cpp = report.get("windows_cpp", {})
    wsl_cpp = report.get("wsl_cpp", {})
    notebook = report.get("python_notebook", {})
    lmstudio = report.get("lm_studio", {})
    ollama = report.get("ollama", {})

    if not bool(windows_cpp.get("ready", False)) or not bool(wsl_cpp.get("ready", False)):
        actions.append(
            {
                "action_id": ACTION_REPAIR_CPP,
                "label": "Repair C++",
                "description": "Repair Windows and/or WSL C++ toolchains and re-run smoke checks.",
                "lane": "cpp",
                "requires_approval": True,
                "requires_network": True,
                "state": "available",
            }
        )
    if not bool(notebook.get("ready", False)):
        actions.append(
            {
                "action_id": ACTION_REPAIR_NOTEBOOK,
                "label": "Repair Notebook Runtime",
                "description": "Install notebook stack, then register CCBS Jupyter kernel.",
                "lane": "notebook",
                "requires_approval": True,
                "requires_network": True,
                "state": "available",
            }
        )
    if str(lmstudio.get("status", "")) in {"installed_not_running", "running_no_models"}:
        actions.append(
            {
                "action_id": ACTION_START_LM_STUDIO,
                "label": "Start LM Studio",
                "description": "Launch LM Studio and re-check local API reachability.",
                "lane": "provider",
                "requires_approval": True,
                "requires_network": False,
                "state": "available",
            }
        )
    if not bool(lmstudio.get("ready", False)) and str(ollama.get("status", "")) in {"installed_not_running", "running_no_models"}:
        actions.append(
            {
                "action_id": ACTION_START_OLLAMA,
                "label": "Start Ollama",
                "description": "Start Ollama as local provider fallback if LM Studio is unavailable.",
                "lane": "provider",
                "requires_approval": True,
                "requires_network": False,
                "state": "available",
            }
        )
    return actions


def collect_capability_report(root: Path) -> dict[str, Any]:
    root = root.resolve()
    windows_cpp = _windows_cpp_status()
    wsl_cpp = _wsl_cpp_status(root)
    notebook = _python_notebook_status(root)
    lmstudio = _lmstudio_status()
    ollama = _ollama_status()
    vscode = _vscode_status(root)

    if os.name == "nt":
        cpp_ready = bool(windows_cpp.get("ready", False) and wsl_cpp.get("ready", False))
    else:
        # Non-Windows runtime: treat Windows lane as informational.
        cpp_ready = bool(wsl_cpp.get("ready", False) or windows_cpp.get("status") == "blocked")
    provider_ready = bool(lmstudio.get("ready", False) or ollama.get("ready", False))
    overall_ready = bool(cpp_ready and notebook.get("ready", False) and provider_ready)

    report: dict[str, Any] = {
        "workflow": ["discover", "classify", "propose_fixes", "execute_approved_fixes", "verify", "report"],
        "timestamp": _utc_now(),
        "repo_root": str(root),
        "windows_cpp": windows_cpp,
        "wsl_cpp": wsl_cpp,
        "python_notebook": notebook,
        "lm_studio": lmstudio,
        "ollama": ollama,
        "vscode": vscode,
        "overall_ready": overall_ready,
        "provider_policy": {
            "default_local_provider": "lmstudio",
            "fallback_provider": "ollama",
        },
        "resume_marker_path": str(root / ".ccbs" / "state" / "capability-orchestrator-resume.json"),
    }
    report["fix_actions"] = _build_fix_actions(report)
    return report


def _action_not_approved(action_id: str) -> dict[str, Any]:
    return {
        "ok": False,
        "action_id": action_id,
        "status": "approval_required",
        "message": "Guided auto-fix requires explicit approval. Re-run with approve=true/--approve.",
    }


def _powershell_start(exe_path: str) -> dict[str, Any]:
    if not exe_path:
        return {"ok": False, "exit_code": 1, "stdout": "", "stderr": "executable_not_found"}
    if os.name == "nt":
        return _run_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"Start-Process -FilePath '{exe_path}'",
            ],
            timeout_sec=25,
        )
    proc = subprocess.Popen([exe_path])  # noqa: S603
    return {
        "ok": True,
        "exit_code": 0,
        "stdout": f"started pid={proc.pid}",
        "stderr": "",
        "command": [exe_path],
        "started_at": _utc_now(),
        "ended_at": _utc_now(),
    }


def _repair_notebook_runtime(root: Path) -> dict[str, Any]:
    py = _resolve_python(root)
    install = _run_command(
        [
            py,
            "-m",
            "pip",
            "install",
            "-U",
            "notebook",
            "jupyterlab",
            "ipykernel",
            "pandas",
            "scikit-learn",
        ],
        cwd=root,
        timeout_sec=1200,
    )
    kernel = _run_command(
        [py, "-m", "ipykernel", "install", "--user", "--name", "ccbs-pro", "--display-name", "Python (CCBS PRO)"],
        cwd=root,
        timeout_sec=120,
    )
    ok = bool(install.get("ok", False) and kernel.get("ok", False))
    return {
        "ok": ok,
        "steps": [
            {
                "step": "pip_install_notebook_stack",
                **install,
            },
            {
                "step": "register_ccbs_kernel",
                **kernel,
            },
        ],
    }


def _repair_cpp(root: Path) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    if os.name == "nt":
        winget = shutil.which("winget")
        if winget:
            cmake_install = _run_command(
                [
                    winget,
                    "install",
                    "--id",
                    "Kitware.CMake",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--silent",
                ],
                cwd=root,
                timeout_sec=900,
            )
            cmake_install["step"] = "install_cmake_windows"
            steps.append(cmake_install)
        else:
            steps.append(
                {
                    "step": "install_cmake_windows",
                    "ok": False,
                    "exit_code": 127,
                    "stdout": "",
                    "stderr": "winget_not_found",
                }
            )
        vs_url = _run_command(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Start-Process 'https://visualstudio.microsoft.com/visual-cpp-build-tools/'",
            ],
            cwd=root,
            timeout_sec=30,
        )
        vs_url["step"] = "open_vs_build_tools_download"
        steps.append(vs_url)
        _write_resume_marker(
            root,
            {
                "restart_required": True,
                "reason": "windows_cpp_install_or_path_refresh",
                "next_step": "Reopen terminal and run: ccbs capabilities status",
            },
        )

    wsl_exe = shutil.which("wsl.exe") or shutil.which("wsl")
    auto_wsl_cpp = str(os.environ.get("CCBS_CAP_AUTO_WSL_CPP", "0")).strip().lower() in {"1", "true", "yes", "on"}
    if wsl_exe and auto_wsl_cpp:
        distro = _resolve_wsl_distro(wsl_exe)
        wsl_install = _run_command(
            [
                wsl_exe,
                "-d",
                distro,
                "--",
                "bash",
                "-lc",
                "sudo apt-get update && sudo apt-get install -y build-essential g++ gcc clang cmake gdb",
            ],
            cwd=root,
            timeout_sec=1800,
        )
        wsl_install["step"] = "install_wsl_cpp_toolchain"
        steps.append(wsl_install)
    elif wsl_exe:
        steps.append(
            {
                "step": "install_wsl_cpp_toolchain",
                "ok": True,
                "exit_code": 0,
                "stdout": "",
                "stderr": "skipped_set_CCBS_CAP_AUTO_WSL_CPP=1_to_enable",
            }
        )

    ok = all(bool(step.get("ok", False)) for step in steps if "ok" in step)
    return {"ok": ok, "steps": steps}


def execute_capability_action(
    root: Path,
    *,
    action_id: str,
    approve: bool = False,
    lane: str = "",
    actor: str = "",
) -> dict[str, Any]:
    root = root.resolve()
    action = str(action_id or "").strip().lower()
    if not action:
        return {"ok": False, "status": "invalid_action", "message": "action_id is required"}
    if not approve:
        out = _action_not_approved(action)
        _append_action_log(
            root,
            {
                "timestamp": _utc_now(),
                "action_id": action,
                "actor": actor or "unknown",
                "lane": lane or "",
                "result": out,
            },
        )
        return out

    result: dict[str, Any]
    if action == ACTION_START_LM_STUDIO:
        exe = _find_lmstudio_executable()
        started = _powershell_start(exe)
        result = {
            "ok": bool(started.get("ok", False)),
            "action_id": action,
            "status": "executed",
            "steps": [{"step": "start_lm_studio", **started}],
        }
    elif action == ACTION_START_OLLAMA:
        exe = shutil.which("ollama") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe")
        if exe and Path(exe).exists():
            started = _powershell_start(str(exe))
            result = {
                "ok": bool(started.get("ok", False)),
                "action_id": action,
                "status": "executed",
                "steps": [{"step": "start_ollama", **started}],
            }
        else:
            result = {
                "ok": False,
                "action_id": action,
                "status": "failed",
                "steps": [{"step": "start_ollama", "ok": False, "exit_code": 127, "stderr": "ollama_not_installed"}],
            }
    elif action == ACTION_REPAIR_NOTEBOOK:
        repaired = _repair_notebook_runtime(root)
        result = {"ok": bool(repaired.get("ok", False)), "action_id": action, "status": "executed", **repaired}
    elif action == ACTION_REPAIR_CPP:
        repaired = _repair_cpp(root)
        result = {"ok": bool(repaired.get("ok", False)), "action_id": action, "status": "executed", **repaired}
    elif action == ACTION_FIX_ALL:
        initial = collect_capability_report(root)
        plan = [item.get("action_id") for item in list(initial.get("fix_actions", []))]
        executed: list[dict[str, Any]] = []
        ok = True
        for sub_action in plan:
            sid = str(sub_action or "").strip().lower()
            if sid == ACTION_FIX_ALL:
                continue
            sub = execute_capability_action(root, action_id=sid, approve=True, lane=lane, actor=actor)
            executed.append(sub)
            ok = ok and bool(sub.get("ok", False))
        result = {
            "ok": ok,
            "action_id": action,
            "status": "executed",
            "planned_actions": plan,
            "executed_actions": executed,
        }
    else:
        result = {"ok": False, "action_id": action, "status": "invalid_action", "message": f"unknown action_id: {action}"}

    verify = collect_capability_report(root)
    result["verify"] = verify
    _append_action_log(
        root,
        {
            "timestamp": _utc_now(),
            "action_id": action,
            "actor": actor or "unknown",
            "lane": lane or "",
            "approve": bool(approve),
            "result_ok": bool(result.get("ok", False)),
            "result": result,
        },
    )
    return result
