"""Cross-platform quality-of-life toolkit for CCBS repos.

This module is intentionally stdlib-only so it can run almost anywhere.
The goal is safe defaults, reproducible outputs, and reusable workflows.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import socket
import socketserver
import subprocess
import sys
import time
import webbrowser
import zipfile
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlparse


DEFAULT_CONFIG: dict[str, Any] = {
    "required_paths": ["src", "docs", "scripts", "tools", "tests", "config"],
    "recommended_commands": ["git", "rg"],
    "venv_candidates": [".venv-clean", ".venv-win", ".venv-1", ".venv"],
    "blocked_markers": ["cocosdashboard", "epicgames", "epiconlineservices"],
    "catalog": {
        "include": [
            "*.md",
            "*.bat",
            "*.ps1",
            "*.sh",
            "*.py",
            "*.json",
            "*.yaml",
            "*.yml",
            "*.html",
            "docs/**",
            "src/**",
            "scripts/**",
            "tools/**",
            "config/**",
            "assets/**",
            "tests/**",
        ],
        "exclude": [
            ".git/**",
            ".venv-clean/**",
            ".venv/**",
            ".venv-1/**",
            ".venv-win/**",
            ".pytest_cache/**",
            "dist/**",
            "build/**",
            "LLM CBBS/**",
            "**/__pycache__/**",
            "**/*.pyc",
        ],
    },
    "link_check": {
        "include": [
            "README.md",
            "USAGE.md",
            "docs/QOL_TOOLKIT.md",
        ]
    },
    "site": {
        "default_host": "127.0.0.1",
        "default_port": 8090,
        "candidates": [
            "../test/docs/repo_artifacts_portfolio.html",
            "docs/repo_artifacts_portfolio.html",
            "docs/index.html",
            "index.html",
        ],
    },
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _find_repo_root(start: Path) -> Path:
    node = start.resolve()
    for candidate in (node, *node.parents):
        if (candidate / ".git").exists():
            return candidate
    return node


def _resolve_root(raw_root: str | None) -> Path:
    if raw_root and raw_root.strip():
        return Path(raw_root).expanduser().resolve()
    return _find_repo_root(Path.cwd())


def _looks_like_windows_abs_path(raw: str) -> bool:
    return len(raw) >= 3 and raw[1] == ":" and raw[0].isalpha() and raw[2] in ("\\", "/")


def _coerce_path(raw: str, *, relative_to: Path | None = None) -> Path | None:
    text = str(raw or "").strip().strip('"').strip("'")
    if not text:
        return None

    if _looks_like_windows_abs_path(text):
        if os.name == "nt":
            return Path(text).resolve()
        win = PureWindowsPath(text)
        drive = str(win.drive).rstrip(":").lower()
        tail = [part for part in win.parts[1:] if part not in ("\\", "/")]
        return Path("/mnt", drive, *tail).resolve()

    normalized = text.replace("\\", os.sep)
    candidate = Path(normalized).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if relative_to is None:
        return candidate.resolve()
    return (relative_to / candidate).resolve()


def _resolve_workspace_setting_path(root: Path, raw: str) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    text = text.replace("${workspaceFolder}", str(root))
    text = text.replace("${workspaceRoot}", str(root))
    return _coerce_path(text, relative_to=root)


def _read_json_object(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, ""
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}, ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"{path}: {exc}"
    if not isinstance(payload, dict):
        return {}, f"{path}: expected a JSON object"
    return payload, ""


def _read_pyvenv_cfg(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            payload[key] = value
    return payload


def _locate_venv_python(env_root: Path) -> Path | None:
    for candidate in (
        env_root / "Scripts" / "python.exe",
        env_root / "bin" / "python",
    ):
        if candidate.exists():
            return candidate.resolve()
    return None


def _locate_venv_pip(env_root: Path) -> Path | None:
    for candidate in (
        env_root / "Scripts" / "pip.exe",
        env_root / "bin" / "pip",
    ):
        if candidate.exists():
            return candidate.resolve()
    return None


def _locate_venv_activate(env_root: Path) -> Path | None:
    for candidate in (
        env_root / "Scripts" / "Activate.ps1",
        env_root / "bin" / "activate",
    ):
        if candidate.exists():
            return candidate.resolve()
    return None


def _discover_repo_venv_roots(root: Path, approved_names: list[str]) -> list[Path]:
    found: dict[str, Path] = {}
    ignore_dirs = {".git", ".ccbs", ".pytest_cache", ".mypy_cache", "__pycache__", "node_modules", "dist", "build"}

    for rel in approved_names:
        candidate = (root / rel).resolve()
        if candidate.exists():
            found[str(candidate).lower()] = candidate

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in ignore_dirs]
        if "pyvenv.cfg" not in files:
            continue
        env_root = Path(current_root).resolve()
        found[str(env_root).lower()] = env_root
        dirs[:] = []

    for child in root.iterdir():
        if not child.is_dir():
            continue
        name = child.name.lower()
        looks_like_env = name.startswith(".venv") or name.startswith("venv") or name.startswith("env")
        if not looks_like_env and child.name not in approved_names:
            continue
        if any(
            candidate.exists()
            for candidate in (
                child / "pyvenv.cfg",
                child / "Scripts" / "python.exe",
                child / "bin" / "python",
            )
        ):
            found[str(child.resolve()).lower()] = child.resolve()

    return sorted(found.values(), key=lambda item: item.as_posix().lower())


def _windows_signature_info(path: Path | None) -> dict[str, Any]:
    if path is None or os.name != "nt":
        return {"available": False, "status": "", "status_message": "", "subject": ""}

    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell is None:
        return {"available": False, "status": "", "status_message": "", "subject": ""}

    escaped = str(path).replace("'", "''")
    script = (
        f"$sig = Get-AuthenticodeSignature -LiteralPath '{escaped}'; "
        "[pscustomobject]@{"
        "status = [string]$sig.Status; "
        "status_message = [string]$sig.StatusMessage; "
        "subject = [string]($sig.SignerCertificate.Subject)"
        "} | ConvertTo-Json -Compress"
    )
    proc = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return {
            "available": False,
            "status": "",
            "status_message": (proc.stderr or "").strip(),
            "subject": "",
        }
    try:
        payload = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return {
            "available": False,
            "status": "",
            "status_message": proc.stdout.strip(),
            "subject": "",
        }
    if not isinstance(payload, dict):
        return {"available": False, "status": "", "status_message": "", "subject": ""}
    return {
        "available": True,
        "status": str(payload.get("status", "")),
        "status_message": str(payload.get("status_message", "")),
        "subject": str(payload.get("subject", "")),
    }


def _path_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _detail_status(issues: list[str], warnings: list[str]) -> str:
    if issues:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def validate_python_environment_integrity(
    root: Path,
    config: dict[str, Any] | None = None,
    *,
    runtime_python: str = "",
) -> dict[str, Any]:
    merged_config = _deep_merge(DEFAULT_CONFIG, dict(config or {}))
    approved_names = [str(item).strip() for item in list(merged_config.get("venv_candidates", [])) if str(item).strip()]
    approved_roots = {(root / rel).resolve(): rel for rel in approved_names}
    discovered_roots = _discover_repo_venv_roots(root=root, approved_names=approved_names)

    settings_path = root / ".vscode" / "settings.json"
    settings_payload, settings_error = _read_json_object(settings_path)
    configured_raw = str(settings_payload.get("python.defaultInterpreterPath", "")).strip()
    configured_interpreter = _resolve_workspace_setting_path(root, configured_raw) if configured_raw else None

    runtime_path = _coerce_path(runtime_python or sys.executable)
    active_virtual_env_raw = str(os.environ.get("VIRTUAL_ENV", "")).strip()
    active_virtual_env = _coerce_path(active_virtual_env_raw) if active_virtual_env_raw else None

    env_rows: list[dict[str, Any]] = []
    unexpected_venvs: list[str] = []
    approved_detected: list[str] = []

    for env_root in discovered_roots:
        rel_path = env_root.relative_to(root).as_posix() if _path_within(root, env_root) else str(env_root)
        approved_name = approved_roots.get(env_root.resolve(), "")
        approved = bool(approved_name)
        pyvenv_path = env_root / "pyvenv.cfg"
        python_path = _locate_venv_python(env_root)
        pip_path = _locate_venv_pip(env_root)
        activate_path = _locate_venv_activate(env_root)
        pyvenv_cfg = _read_pyvenv_cfg(pyvenv_path)
        base_home = _coerce_path(pyvenv_cfg.get("home", ""), relative_to=env_root)
        base_executable = _coerce_path(pyvenv_cfg.get("executable", ""), relative_to=env_root)
        creation_command = str(pyvenv_cfg.get("command", "")).strip()
        include_system_site_packages = str(pyvenv_cfg.get("include-system-site-packages", "")).strip().lower()
        signature = _windows_signature_info(python_path)

        issues: list[str] = []
        warnings: list[str] = []
        if not approved:
            issues.append("unexpected_venv_location")
        if not pyvenv_path.exists():
            issues.append("missing_pyvenv_cfg")
        if python_path is None:
            issues.append("missing_python_executable")
        if pip_path is None:
            warnings.append("missing_pip_launcher")
        if activate_path is None:
            warnings.append("missing_activate_script")
        if include_system_site_packages == "true":
            warnings.append("system_site_packages_enabled")
        if pyvenv_cfg and not base_home:
            warnings.append("missing_base_home")
        elif base_home is not None and not base_home.exists():
            warnings.append("base_home_missing")
        if pyvenv_cfg and not base_executable:
            warnings.append("missing_base_executable")
        elif base_executable is not None and not base_executable.exists():
            warnings.append("base_executable_missing")
        if creation_command and "-m venv" not in creation_command.lower():
            warnings.append("nonstandard_creation_command")
        if python_path is not None and os.name == "nt" and signature.get("available"):
            if str(signature.get("status", "")).strip() not in {"0", "Valid"}:
                warnings.append("python_signature_not_verified")

        row = {
            "path": rel_path,
            "root": str(env_root),
            "approved": approved,
            "approved_name": approved_name,
            "status": _detail_status(issues, warnings),
            "pyvenv_cfg_path": str(pyvenv_path),
            "pyvenv_cfg_present": pyvenv_path.exists(),
            "python_path": str(python_path) if python_path else "",
            "python_present": bool(python_path),
            "pip_path": str(pip_path) if pip_path else "",
            "pip_present": bool(pip_path),
            "activate_path": str(activate_path) if activate_path else "",
            "activate_present": bool(activate_path),
            "base_home": str(base_home) if base_home else "",
            "base_home_exists": bool(base_home and base_home.exists()),
            "base_executable": str(base_executable) if base_executable else "",
            "base_executable_exists": bool(base_executable and base_executable.exists()),
            "creation_command": creation_command,
            "include_system_site_packages": include_system_site_packages or "",
            "version": str(pyvenv_cfg.get("version", "")).strip(),
            "signature_available": bool(signature.get("available", False)),
            "signature_status": str(signature.get("status", "")),
            "signature_message": str(signature.get("status_message", "")),
            "signature_subject": str(signature.get("subject", "")),
            "issues": issues,
            "warnings": warnings,
        }
        env_rows.append(row)
        if approved:
            approved_detected.append(rel_path)
        else:
            unexpected_venvs.append(rel_path)

    configured_exists = bool(configured_interpreter and configured_interpreter.exists())
    configured_approved = bool(
        configured_interpreter
        and any(
            row["approved"] and _path_within(Path(row["root"]), configured_interpreter)
            for row in env_rows
        )
    )
    runtime_matches_configured = None
    if runtime_path is not None and configured_interpreter is not None:
        runtime_matches_configured = runtime_path.resolve() == configured_interpreter.resolve()

    active_virtual_env_approved = None
    if active_virtual_env is not None:
        active_virtual_env_approved = any(
            row["approved"] and active_virtual_env.resolve() == Path(row["root"]).resolve()
            for row in env_rows
        )

    issues: list[str] = []
    warnings: list[str] = []
    if settings_error:
        warnings.append("vscode_settings_parse_error")
    if configured_raw:
        if not configured_exists:
            issues.append("vscode_interpreter_missing")
        elif not configured_approved:
            issues.append("vscode_interpreter_unapproved")
    else:
        warnings.append("vscode_interpreter_not_set")
    if unexpected_venvs:
        issues.append("unexpected_virtual_env_detected")
    if any(row["approved"] and row["status"] == "fail" for row in env_rows):
        issues.append("approved_virtual_env_validation_failed")
    if not approved_detected:
        warnings.append("no_approved_virtual_env_found")
    if runtime_matches_configured is False:
        warnings.append("runtime_python_mismatch")
    if active_virtual_env_approved is False:
        issues.append("active_virtual_env_unapproved")

    status = _detail_status(issues, warnings)
    if settings_error:
        warnings.append(settings_error)

    return {
        "generated_at": _utc_now_iso(),
        "root": str(root),
        "status": status,
        "approved_venv_names": approved_names,
        "approved_venv_count": len(approved_detected),
        "approved_venvs": approved_detected,
        "unexpected_venv_count": len(unexpected_venvs),
        "unexpected_venvs": unexpected_venvs,
        "settings_path": str(settings_path),
        "settings_exists": settings_path.exists(),
        "configured_interpreter_raw": configured_raw,
        "configured_interpreter": str(configured_interpreter) if configured_interpreter else "",
        "configured_interpreter_exists": configured_exists,
        "configured_interpreter_approved": configured_approved,
        "runtime_python": str(runtime_path) if runtime_path else "",
        "runtime_matches_configured": runtime_matches_configured,
        "active_virtual_env": str(active_virtual_env) if active_virtual_env else "",
        "active_virtual_env_approved": active_virtual_env_approved,
        "issues": issues,
        "warnings": warnings,
        "venvs": env_rows,
    }


def _default_config_path(root: Path) -> Path:
    return root / "config" / "qol_toolkit.json"


def load_config(root: Path, custom_path: str | None = None) -> dict[str, Any]:
    merged: dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))

    cfg_path = _default_config_path(root)
    if cfg_path.exists():
        try:
            merged = _deep_merge(merged, json.loads(cfg_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in config file {cfg_path}: {exc}") from exc

    if custom_path:
        manual = Path(custom_path).expanduser()
        if not manual.is_absolute():
            manual = (root / manual).resolve()
        if manual.exists():
            try:
                merged = _deep_merge(merged, json.loads(manual.read_text(encoding="utf-8")))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in config file {manual}: {exc}") from exc
    return merged


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pattern_variants(pattern: str) -> list[str]:
    variants = {pattern}
    if pattern.startswith("**/"):
        variants.add(pattern[3:])
    if "/**/" in pattern:
        variants.add(pattern.replace("/**/", "/"))
    return [item for item in variants if item]


def _matches_any(rel_posix: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    for pat in patterns:
        for variant in _pattern_variants(pat):
            if fnmatch.fnmatch(rel_posix, variant):
                return True
    return False


def collect_files(root: Path, include: list[str], exclude: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if include and not _matches_any(rel, include):
            continue
        if exclude and _matches_any(rel, exclude):
            continue
        files.append(path)
    files.sort(key=lambda item: item.relative_to(root).as_posix())
    return files


def run_doctor(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    py_ok = sys.version_info >= (3, 10)
    checks.append(
        {
            "name": "python_version",
            "status": "pass" if py_ok else "fail",
            "detail": f"{sys.version.split()[0]} ({sys.executable})",
        }
    )

    for command in list(config.get("recommended_commands", [])):
        present = shutil.which(command) is not None
        checks.append(
            {
                "name": f"command:{command}",
                "status": "pass" if present else "warn",
                "detail": "found in PATH" if present else "not found in PATH",
            }
        )

    missing_required: list[str] = []
    for rel in list(config.get("required_paths", [])):
        if not (root / rel).exists():
            missing_required.append(rel)
    checks.append(
        {
            "name": "required_paths",
            "status": "pass" if not missing_required else "fail",
            "detail": "all present" if not missing_required else f"missing: {', '.join(missing_required)}",
        }
    )

    venv_candidates: list[str] = list(config.get("venv_candidates", []))
    healthy_envs: list[str] = []
    broken_envs: list[str] = []
    for rel in venv_candidates:
        env_root = root / rel
        if not env_root.exists():
            continue
        candidates = [env_root / "Scripts" / "python.exe", env_root / "bin" / "python"]
        found = next((item for item in candidates if item.exists()), None)
        if found:
            healthy_envs.append(f"{rel} -> {found.relative_to(root)}")
        else:
            broken_envs.append(rel)
    if healthy_envs:
        checks.append(
            {
                "name": "virtual_env",
                "status": "pass",
                "detail": "; ".join(healthy_envs),
            }
        )
    else:
        checks.append(
            {
                "name": "virtual_env",
                "status": "warn",
                "detail": "no usable virtual environment found",
            }
        )
    if broken_envs:
        checks.append(
            {
                "name": "virtual_env_broken",
                "status": "warn",
                "detail": f"detected but missing python executable: {', '.join(broken_envs)}",
            }
        )

    env_report = validate_python_environment_integrity(root=root, config=config, runtime_python=sys.executable)
    approved = list(env_report.get("approved_venvs", []))
    unexpected = list(env_report.get("unexpected_venvs", []))
    checks.append(
        {
            "name": "venv_inventory",
            "status": str(env_report.get("status", "warn")),
            "detail": (
                f"approved={len(approved)} ({', '.join(approved) if approved else 'none'})"
                f"; unexpected={len(unexpected)} ({', '.join(unexpected) if unexpected else 'none'})"
            ),
        }
    )

    configured_raw = str(env_report.get("configured_interpreter_raw", "")).strip()
    configured_resolved = str(env_report.get("configured_interpreter", "")).strip()
    if configured_raw:
        vscode_status = "pass"
        if not bool(env_report.get("configured_interpreter_exists", False)):
            vscode_status = "fail"
        elif not bool(env_report.get("configured_interpreter_approved", False)):
            vscode_status = "fail"
        checks.append(
            {
                "name": "vscode_interpreter",
                "status": vscode_status,
                "detail": (
                    f"{configured_raw} -> {configured_resolved or '(unresolved)'}"
                    f" ({'approved' if bool(env_report.get('configured_interpreter_approved', False)) else 'not approved'})"
                ),
            }
        )
    else:
        checks.append(
            {
                "name": "vscode_interpreter",
                "status": "warn",
                "detail": "python.defaultInterpreterPath is not set in .vscode/settings.json",
            }
        )

    runtime_match = env_report.get("runtime_matches_configured", None)
    if runtime_match is None:
        runtime_status = "warn"
        runtime_detail = "runtime/configured comparison unavailable"
    else:
        runtime_status = "pass" if bool(runtime_match) else "warn"
        runtime_detail = (
            f"{env_report.get('runtime_python', '')} "
            + ("matches" if bool(runtime_match) else "does not match")
            + " configured interpreter"
        )
    checks.append(
        {
            "name": "runtime_python_binding",
            "status": runtime_status,
            "detail": runtime_detail,
        }
    )

    markers = [str(item).lower() for item in list(config.get("blocked_markers", []))]
    ignore_dirs = {".git", ".venv", ".venv-1", ".pytest_cache", "dist", "build", "node_modules"}
    marker_hits: list[str] = []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in ignore_dirs]
        rel_root = Path(current_root).resolve().relative_to(root.resolve())
        for name in dirs + files:
            lowered = name.lower()
            if any(marker in lowered for marker in markers):
                rel_hit = (rel_root / name).as_posix()
                marker_hits.append(rel_hit)
                if len(marker_hits) >= 20:
                    break
        if len(marker_hits) >= 20:
            break
    checks.append(
        {
            "name": "blocked_markers",
            "status": "pass" if not marker_hits else "fail",
            "detail": "none found" if not marker_hits else ", ".join(marker_hits),
        }
    )

    order = {"pass": 0, "warn": 1, "fail": 2}
    overall = "pass"
    for item in checks:
        if order[item["status"]] > order[overall]:
            overall = item["status"]

    return {
        "generated_at": _utc_now_iso(),
        "root": str(root),
        "overall": overall,
        "checks": checks,
        "python_environment": env_report,
    }


def build_catalog(
    root: Path,
    output: Path,
    include: list[str],
    exclude: list[str],
    max_files: int = 0,
) -> dict[str, Any]:
    files = collect_files(root=root, include=include, exclude=exclude)
    if max_files > 0:
        files = files[:max_files]

    entries: list[dict[str, Any]] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        entries.append(
            {
                "path": rel,
                "size": int(stat.st_size),
                "sha256": _sha256_file(path),
                "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )

    payload: dict[str, Any] = {
        "schema": "ccbs-qol-catalog-v1",
        "generated_at": _utc_now_iso(),
        "root": str(root),
        "include": include,
        "exclude": exclude,
        "entry_count": len(entries),
        "entries": entries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def verify_catalog(root: Path, catalog_path: Path, strict_new: bool = False) -> dict[str, Any]:
    raw = catalog_path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"catalog must be a JSON object: {catalog_path}")

    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError(f"catalog entries must be a list: {catalog_path}")

    by_path: dict[str, dict[str, Any]] = {}
    for row in entries:
        if not isinstance(row, dict):
            continue
        key = str(row.get("path", "")).strip()
        if key:
            by_path[key] = row

    missing: list[str] = []
    changed: list[str] = []
    for rel, row in by_path.items():
        target = root / rel
        if not target.exists():
            missing.append(rel)
            continue
        current_sha = _sha256_file(target)
        if str(row.get("sha256", "")) != current_sha:
            changed.append(rel)

    include = [str(item) for item in payload.get("include", []) if str(item).strip()]
    exclude = [str(item) for item in payload.get("exclude", []) if str(item).strip()]
    current_files = collect_files(root=root, include=include, exclude=exclude)
    current_rel = {item.relative_to(root).as_posix() for item in current_files}
    known_rel = set(by_path.keys())
    new_files = sorted(current_rel - known_rel)

    ok = not missing and not changed and (not strict_new or not new_files)
    return {
        "generated_at": _utc_now_iso(),
        "catalog_path": str(catalog_path),
        "ok": ok,
        "missing_count": len(missing),
        "changed_count": len(changed),
        "new_count": len(new_files),
        "missing": missing,
        "changed": changed,
        "new": new_files,
        "strict_new": bool(strict_new),
    }


def create_backup_zip(
    root: Path,
    output: Path,
    include: list[str],
    exclude: list[str],
) -> dict[str, Any]:
    files = collect_files(root=root, include=include, exclude=exclude)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(root).as_posix())
    size_bytes = output.stat().st_size if output.exists() else 0
    return {
        "generated_at": _utc_now_iso(),
        "root": str(root),
        "backup_path": str(output),
        "file_count": len(files),
        "size_bytes": int(size_bytes),
    }


def _extract_links(text: str) -> list[str]:
    out: list[str] = []

    i = 0
    while i < len(text):
        start = text.find("](", i)
        if start < 0:
            break
        end = text.find(")", start + 2)
        if end < 0:
            break
        target = text[start + 2 : end].strip()
        if target:
            out.append(target)
        i = end + 1

    lowered = text.lower()
    for token in ('href="', "href='", 'src="', "src='"):
        pos = 0
        while True:
            idx = lowered.find(token, pos)
            if idx < 0:
                break
            start = idx + len(token)
            quote = token[-1]
            end = text.find(quote, start)
            if end < 0:
                break
            target = text[start:end].strip()
            if target:
                out.append(target)
            pos = end + 1
    return out


def _resolve_link_target(root: Path, source: Path, raw_target: str) -> Path | None:
    target = unquote(raw_target.strip())
    if not target:
        return None
    if target.startswith("#"):
        return None

    parsed = urlparse(target)
    if parsed.scheme in {"http", "https", "ftp", "mailto", "data", "javascript"}:
        return None

    local = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not local:
        return None
    if local.startswith("/"):
        return (root / local.lstrip("/")).resolve()
    return (source.parent / local).resolve()


def check_local_links(root: Path, include: list[str]) -> dict[str, Any]:
    files = collect_files(root=root, include=include, exclude=[".git/**", ".venv/**", ".venv-1/**"])
    missing: list[dict[str, str]] = []
    for file_path in files:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        targets = _extract_links(text)
        for target in targets:
            resolved = _resolve_link_target(root=root, source=file_path, raw_target=target)
            if resolved is None:
                continue
            if not resolved.exists():
                missing.append(
                    {
                        "source": file_path.relative_to(root).as_posix(),
                        "target": target,
                        "resolved": resolved.as_posix(),
                    }
                )
    return {
        "generated_at": _utc_now_iso(),
        "root": str(root),
        "scanned_files": len(files),
        "missing_count": len(missing),
        "missing": missing,
        "ok": not missing,
    }


def _normalize_candidate_path(root: Path, raw: str) -> Path:
    item = Path(str(raw)).expanduser()
    if item.is_absolute():
        return item.resolve()
    return (root / item).resolve()


def discover_site_file(root: Path, config: dict[str, Any], explicit_site: str = "") -> Path | None:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(path)

    text = str(explicit_site or "").strip()
    if text:
        add(_normalize_candidate_path(root, text))

    env_site = str(os.environ.get("CCBS_SITE_PATH", "")).strip()
    if env_site:
        add(_normalize_candidate_path(root, env_site))

    for item in list(config.get("site", {}).get("candidates", [])):
        add(_normalize_candidate_path(root, str(item)))

    projects_root = root.parent.parent if len(root.parents) >= 2 else root.parent
    add((projects_root / "test" / "docs" / "repo_artifacts_portfolio.html").resolve())
    add((projects_root / "test" / "docs" / "index.html").resolve())
    add((projects_root / "test" / "index.html").resolve())
    add((root / "docs" / "repo_artifacts_portfolio.html").resolve())
    add((root / "docs" / "index.html").resolve())
    add((root / "index.html").resolve())

    for path in candidates:
        if path.exists() and path.is_file():
            return path

    fallback_dirs = [
        (projects_root / "test" / "docs").resolve(),
        (root / "docs").resolve(),
        root.resolve(),
    ]
    for folder in fallback_dirs:
        if not folder.exists() or not folder.is_dir():
            continue
        htmls = sorted(folder.glob("*.html"))
        if htmls:
            return htmls[0].resolve()

    return None


def _port_open(host: str, port: int, timeout_s: float = 0.35) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(max(0.1, float(timeout_s)))
    try:
        return sock.connect_ex((host, int(port))) == 0
    finally:
        sock.close()


def _server_python_command(root: Path) -> list[str] | None:
    local_candidates = [
        root / ".venv-clean" / "Scripts" / "python.exe",
        root / ".venv-win" / "Scripts" / "python.exe",
        root / ".venv-1" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv-1" / "bin" / "python",
        root / ".venv" / "bin" / "python",
    ]
    for item in local_candidates:
        if item.exists():
            return [str(item)]
    python_cmd = shutil.which("python")
    if python_cmd:
        return [python_cmd]
    py_cmd = shutil.which("py")
    if py_cmd:
        return [py_cmd, "-3"]
    return None


def _start_static_server(root: Path, site_dir: Path, host: str, port: int) -> dict[str, Any]:
    launcher = _server_python_command(root)
    if not launcher:
        return {
            "started": False,
            "reason": "python launcher not found",
            "command": [],
            "pid": None,
        }

    command = [*launcher, "-m", "http.server", str(int(port)), "--bind", str(host), "--directory", str(site_dir)]
    creationflags = 0
    if os.name == "nt":
        creationflags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    try:
        proc = subprocess.Popen(
            command,
            cwd=str(site_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            creationflags=creationflags,
        )
    except OSError as exc:
        return {
            "started": False,
            "reason": str(exc),
            "command": command,
            "pid": None,
        }

    for _ in range(40):
        if _port_open(host=host, port=port):
            return {
                "started": True,
                "reason": "started",
                "command": command,
                "pid": int(proc.pid),
            }
        time.sleep(0.15)

    return {
        "started": False,
        "reason": "server did not become reachable in time",
        "command": command,
        "pid": int(proc.pid),
    }


def open_site(
    root: Path,
    config: dict[str, Any],
    site: str = "",
    host: str = "",
    port: int = 0,
    no_server: bool = False,
    open_browser: bool = True,
) -> dict[str, Any]:
    site_path = discover_site_file(root=root, config=config, explicit_site=site)
    if site_path is None:
        return {
            "ok": False,
            "reason": "site HTML not found",
            "root": str(root),
            "site_path": "",
            "url": "",
            "server": {"started": False, "reason": "site not found"},
        }

    site_host = str(host or config.get("site", {}).get("default_host", "127.0.0.1"))
    site_port = int(port or int(config.get("site", {}).get("default_port", 8090)))
    site_dir = site_path.parent.resolve()
    rel_name = site_path.name

    server_report: dict[str, Any]
    if no_server:
        url = site_path.resolve().as_uri()
        server_report = {"started": False, "reason": "no-server mode"}
    else:
        already = _port_open(host=site_host, port=site_port)
        if already:
            server_report = {"started": False, "reason": "port already open (reusing existing server)"}
        else:
            server_report = _start_static_server(root=root, site_dir=site_dir, host=site_host, port=site_port)

        if _port_open(host=site_host, port=site_port):
            url = f"http://{site_host}:{site_port}/{rel_name}"
        else:
            # Final fallback so one-click still opens something.
            url = site_path.resolve().as_uri()
            server_report["fallback"] = "file-uri"

    opened = False
    if open_browser:
        try:
            opened = bool(webbrowser.open(url, new=2))
        except Exception:
            opened = False

    return {
        "ok": True,
        "root": str(root),
        "site_path": str(site_path),
        "url": url,
        "browser_open_attempted": bool(open_browser),
        "browser_opened": opened,
        "server": server_report,
    }


def _ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for idx in range(1, 1000):
        candidate = path.with_name(f"{stem}-{idx}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"unable to produce unique path for {path}")


def cleanup_paths(
    root: Path,
    raw_paths: list[str],
    apply_changes: bool = False,
    allow_outside: bool = False,
) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trash_root = root / ".ccbs" / "qol" / "trash" / stamp
    operations: list[dict[str, str]] = []

    for raw in raw_paths:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if not candidate.exists():
            operations.append({"path": str(candidate), "status": "missing", "detail": "path does not exist"})
            continue
        if not allow_outside and not _is_within(root, candidate):
            operations.append(
                {
                    "path": str(candidate),
                    "status": "blocked",
                    "detail": "outside repo root; re-run with --allow-outside to permit",
                }
            )
            continue

        if _is_within(root, candidate):
            rel = candidate.relative_to(root)
            destination = trash_root / rel
        else:
            destination = trash_root / f"outside_{candidate.name}"
        destination = _ensure_unique_path(destination)

        if not apply_changes:
            operations.append(
                {
                    "path": str(candidate),
                    "status": "planned",
                    "detail": f"would move to {destination}",
                }
            )
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(candidate), str(destination))
        operations.append(
            {
                "path": str(candidate),
                "status": "moved",
                "detail": f"moved to {destination}",
            }
        )

    moved_count = sum(1 for item in operations if item["status"] == "moved")
    return {
        "generated_at": _utc_now_iso(),
        "root": str(root),
        "apply_changes": bool(apply_changes),
        "trash_root": str(trash_root),
        "operation_count": len(operations),
        "moved_count": moved_count,
        "operations": operations,
    }


def apply_vscode_python_fix(
    root: Path,
    settings_relative_path: str,
    interpreter: str,
    pytest_path: str,
) -> dict[str, Any]:
    settings_path = Path(settings_relative_path).expanduser()
    if not settings_path.is_absolute():
        settings_path = (root / settings_path).resolve()
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {}
    if settings_path.exists():
        raw = settings_path.read_text(encoding="utf-8")
        if raw.strip():
            loaded = json.loads(raw)
            if not isinstance(loaded, dict):
                raise ValueError(f"settings file must contain a JSON object: {settings_path}")
            data = loaded

    desired = {
        "python.defaultInterpreterPath": interpreter,
        "python.testing.pytestEnabled": True,
        "python.testing.unittestEnabled": False,
        "python.testing.pytestArgs": [pytest_path],
    }
    changed_keys: list[str] = []
    for key, value in desired.items():
        if data.get(key) != value:
            changed_keys.append(key)
            data[key] = value

    if changed_keys:
        settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return {
        "generated_at": _utc_now_iso(),
        "settings_path": str(settings_path),
        "changed_keys": changed_keys,
        "updated": bool(changed_keys),
    }


def _print_doctor(report: dict[str, Any]) -> None:
    print(f"QOL doctor: {report['overall'].upper()}")
    for item in report["checks"]:
        print(f" - [{item['status'].upper()}] {item['name']}: {item['detail']}")


def _print_verify(report: dict[str, Any]) -> None:
    print(
        f"Catalog verify: {'PASS' if report['ok'] else 'FAIL'} "
        f"(missing={report['missing_count']} changed={report['changed_count']} new={report['new_count']})"
    )
    for key in ("missing", "changed", "new"):
        items = list(report.get(key, []))
        if items:
            print(f" - {key}:")
            for row in items[:20]:
                print(f"   - {row}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccbs-clean-qol",
        description="CCBS quality-of-life toolkit (safe, reusable, cross-platform).",
    )
    parser.add_argument("--root", default=".", help="Repo root path (default: current directory).")
    parser.add_argument("--config", default="", help="Optional custom config JSON path.")
    parser.add_argument("--json", action="store_true", help="Output JSON when supported.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Run repo health checks.")

    catalog = sub.add_parser("catalog", help="Build or verify file catalog/hash manifest.")
    catalog_sub = catalog.add_subparsers(dest="catalog_cmd", required=True)

    catalog_build = catalog_sub.add_parser("build", help="Build a catalog hash manifest.")
    catalog_build.add_argument("--output", default=".ccbs/qol/catalog.json", help="Output catalog path.")
    catalog_build.add_argument("--include", action="append", default=[], help="Include glob (repeatable).")
    catalog_build.add_argument("--exclude", action="append", default=[], help="Exclude glob (repeatable).")
    catalog_build.add_argument("--max-files", type=int, default=0, help="Optional max files to index.")

    catalog_verify = catalog_sub.add_parser("verify", help="Verify current repo against a catalog.")
    catalog_verify.add_argument("--catalog", default=".ccbs/qol/catalog.json", help="Catalog JSON path.")
    catalog_verify.add_argument("--strict-new", action="store_true", help="Fail when new files are present.")

    backup = sub.add_parser("backup", help="Create a deterministic zip backup.")
    backup.add_argument("--output", default="", help="Output zip path.")
    backup.add_argument("--include", action="append", default=[], help="Include glob (repeatable).")
    backup.add_argument("--exclude", action="append", default=[], help="Exclude glob (repeatable).")

    links = sub.add_parser("links", help="Check local links in docs/HTML.")
    links.add_argument("--include", action="append", default=[], help="Include glob (repeatable).")

    clean = sub.add_parser("cleanup", help="Move paths into repo trash (safe cleanup).")
    clean.add_argument("--path", action="append", required=True, dest="paths", help="Path to move.")
    clean.add_argument("--apply", action="store_true", help="Apply changes. Default is dry-run.")
    clean.add_argument("--allow-outside", action="store_true", help="Allow cleaning outside repo root.")

    vscode_fix = sub.add_parser("vscode-python-fix", help="Normalize VS Code Python testing settings.")
    vscode_fix.add_argument("--settings", default=".vscode/settings.json", help="Settings JSON path.")
    vscode_fix.add_argument(
        "--interpreter",
        default="${workspaceFolder}\\\\.venv-clean\\\\Scripts\\\\python.exe",
        help="Interpreter path value to set.",
    )
    vscode_fix.add_argument("--pytest-path", default="LLM CBBS", help="pytest discovery path argument.")

    serve = sub.add_parser("serve", help="Serve static files quickly for local preview.")
    serve.add_argument("--path", default="docs", help="Directory to serve.")
    serve.add_argument("--host", default="127.0.0.1", help="Bind host.")
    serve.add_argument("--port", type=int, default=8090, help="Bind port.")
    serve.add_argument("--open", action="store_true", help="Open browser tab on start.")

    open_site_parser = sub.add_parser(
        "open-site",
        help="One-click site opener with automatic site-path assumptions.",
    )
    open_site_parser.add_argument("--site", default="", help="Optional explicit HTML file path.")
    open_site_parser.add_argument("--host", default="", help="Host for local server (default from config).")
    open_site_parser.add_argument("--port", type=int, default=0, help="Port for local server (default from config).")
    open_site_parser.add_argument("--no-server", action="store_true", help="Open as file:// URL without starting server.")
    open_site_parser.add_argument("--no-open", action="store_true", help="Do not open browser (print URL only).")

    workflow = sub.add_parser("workflow", help="Run an opinionated safety workflow.")
    workflow.add_argument("--strict-new", action="store_true", help="Fail if catalog verify detects new files.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = _resolve_root(getattr(args, "root", "."))
    try:
        config = load_config(root=root, custom_path=str(getattr(args, "config", "") or ""))
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.command == "doctor":
        report = run_doctor(root=root, config=config)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_doctor(report)
        return 0 if report["overall"] != "fail" else 1

    if args.command == "catalog":
        if args.catalog_cmd == "build":
            include = args.include or list(config.get("catalog", {}).get("include", []))
            exclude = args.exclude or list(config.get("catalog", {}).get("exclude", []))
            output = Path(args.output)
            if not output.is_absolute():
                output = (root / output).resolve()
            report = build_catalog(
                root=root,
                output=output,
                include=include,
                exclude=exclude,
                max_files=max(0, int(args.max_files)),
            )
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(f"Catalog built: {output} (entries={report['entry_count']})")
            return 0

        catalog_path = Path(args.catalog)
        if not catalog_path.is_absolute():
            catalog_path = (root / catalog_path).resolve()
        if not catalog_path.exists():
            print(f"ERROR: catalog not found: {catalog_path}")
            return 2
        report = verify_catalog(root=root, catalog_path=catalog_path, strict_new=bool(args.strict_new))
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_verify(report)
        return 0 if report["ok"] else 1

    if args.command == "backup":
        include = args.include or list(config.get("catalog", {}).get("include", []))
        exclude = args.exclude or list(config.get("catalog", {}).get("exclude", []))
        if args.output:
            output = Path(args.output)
            if not output.is_absolute():
                output = (root / output).resolve()
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = (root / ".ccbs" / "qol" / "backups" / f"backup-{stamp}.zip").resolve()
        report = create_backup_zip(root=root, output=output, include=include, exclude=exclude)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"Backup created: {report['backup_path']} (files={report['file_count']}, bytes={report['size_bytes']})")
        return 0

    if args.command == "links":
        include = args.include or list(config.get("link_check", {}).get("include", []))
        report = check_local_links(root=root, include=include)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(
                f"Link check: {'PASS' if report['ok'] else 'FAIL'} "
                f"(files={report['scanned_files']} missing={report['missing_count']})"
            )
            for item in report["missing"][:20]:
                print(f" - {item['source']} -> {item['target']}")
        return 0 if report["ok"] else 1

    if args.command == "cleanup":
        report = cleanup_paths(
            root=root,
            raw_paths=list(args.paths or []),
            apply_changes=bool(args.apply),
            allow_outside=bool(args.allow_outside),
        )
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            mode = "APPLY" if args.apply else "DRY-RUN"
            print(f"Cleanup {mode}: operations={report['operation_count']} moved={report['moved_count']}")
            print(f"Trash root: {report['trash_root']}")
            for item in report["operations"]:
                print(f" - [{item['status']}] {item['path']}: {item['detail']}")
        blocked = any(item["status"] == "blocked" for item in report["operations"])
        return 1 if blocked else 0

    if args.command == "vscode-python-fix":
        report = apply_vscode_python_fix(
            root=root,
            settings_relative_path=str(args.settings),
            interpreter=str(args.interpreter),
            pytest_path=str(args.pytest_path),
        )
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            if report["updated"]:
                print(f"Updated {report['settings_path']}")
                for key in report["changed_keys"]:
                    print(f" - {key}")
            else:
                print(f"No changes needed in {report['settings_path']}")
        return 0

    if args.command == "serve":
        target = Path(args.path).expanduser()
        if not target.is_absolute():
            target = (root / target).resolve()
        if not target.exists() or not target.is_dir():
            print(f"ERROR: serve path is not a directory: {target}")
            return 2

        class _Handler(SimpleHTTPRequestHandler):
            def __init__(self, *handler_args: Any, **handler_kwargs: Any) -> None:
                super().__init__(*handler_args, directory=str(target), **handler_kwargs)

        url = f"http://{args.host}:{int(args.port)}"
        print(f"Serving {target} on {url}")
        if bool(args.open):
            webbrowser.open(url)
        with socketserver.TCPServer((args.host, int(args.port)), _Handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0

    if args.command == "open-site":
        report = open_site(
            root=root,
            config=config,
            site=str(args.site or ""),
            host=str(args.host or ""),
            port=int(args.port or 0),
            no_server=bool(args.no_server),
            open_browser=not bool(args.no_open),
        )
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            if not report["ok"]:
                print(f"ERROR: {report['reason']}")
                return 2
            print(f"Site file: {report['site_path']}")
            print(f"URL: {report['url']}")
            server = report.get("server", {})
            print(f"Server: {server.get('reason', 'n/a')}")
        return 0 if report.get("ok") else 1

    if args.command == "workflow":
        doctor_report = run_doctor(root=root, config=config)
        include = list(config.get("catalog", {}).get("include", []))
        exclude = list(config.get("catalog", {}).get("exclude", []))
        link_include = list(config.get("link_check", {}).get("include", []))

        catalog_path = (root / ".ccbs" / "qol" / "catalog.json").resolve()
        if catalog_path.exists():
            catalog_report = verify_catalog(root=root, catalog_path=catalog_path, strict_new=bool(args.strict_new))
            if not bool(catalog_report.get("ok")) and not bool(args.strict_new):
                drift_snapshot = {
                    "missing_count": int(catalog_report.get("missing_count", 0)),
                    "changed_count": int(catalog_report.get("changed_count", 0)),
                    "new_count": int(catalog_report.get("new_count", 0)),
                }
                build_catalog(root=root, output=catalog_path, include=include, exclude=exclude)
                catalog_report = {
                    "ok": True,
                    "missing_count": 0,
                    "changed_count": 0,
                    "new_count": 0,
                    "auto_refreshed_catalog": True,
                    "prior_drift": drift_snapshot,
                }
        else:
            build_catalog(root=root, output=catalog_path, include=include, exclude=exclude)
            catalog_report = {
                "ok": True,
                "missing_count": 0,
                "changed_count": 0,
                "new_count": 0,
                "built_new_catalog": True,
            }
        link_report = check_local_links(root=root, include=link_include)

        summary = {
            "generated_at": _utc_now_iso(),
            "root": str(root),
            "doctor": doctor_report,
            "catalog": catalog_report,
            "links": link_report,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            _print_doctor(doctor_report)
            print("")
            print(
                "Catalog gate: "
                f"{'PASS' if bool(catalog_report.get('ok')) else 'FAIL'} "
                f"(missing={catalog_report.get('missing_count', 0)} "
                f"changed={catalog_report.get('changed_count', 0)} "
                f"new={catalog_report.get('new_count', 0)})"
            )
            if bool(catalog_report.get("auto_refreshed_catalog")):
                prior = catalog_report.get("prior_drift", {})
                print(
                    "Catalog note: refreshed from drift "
                    f"(missing={prior.get('missing_count', 0)} "
                    f"changed={prior.get('changed_count', 0)} "
                    f"new={prior.get('new_count', 0)})."
                )
            print(
                "Link gate: "
                f"{'PASS' if link_report['ok'] else 'FAIL'} "
                f"(missing={link_report['missing_count']})"
            )
        ok = doctor_report["overall"] != "fail" and bool(catalog_report.get("ok")) and link_report["ok"]
        return 0 if ok else 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
