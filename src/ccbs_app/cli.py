"""Command line interface for CCBS app."""

from __future__ import annotations

import argparse
import json
import ipaddress
import os
import platform
import socket
import subprocess
import sys
import urllib.parse
from pathlib import Path, PureWindowsPath
from typing import Any

from .ai3.cli import add_ai3_parser
from .ai3.chat_profile import get_chat_profile as ai3_get_chat_profile
from .ai3.chat_profile import set_chat_profile as ai3_set_chat_profile
from .ai3.db import connect_runtime as ai3_connect_runtime
from .buildathon import add_buildathon_parser
from .ai_model_catalog import discover_model_catalog
from .ai_prompt_pack import (
    export_prompt_pack as ai_export_prompt_pack,
    find_prompt as ai_find_prompt_pack_prompt,
    list_prompt_packs as ai_list_prompt_packs,
    load_prompt_pack as ai_load_prompt_pack,
)
from .ai_usecase_library import build_usecase_library, write_library as write_usecase_library
from .assist_pack import build_assist_pack
from .assist_router import normalize_transcript
from .assist_runtime import run_assist_dry
from .assist_store import (
    add_command as assist_add_command,
    ack_profile as assist_ack_profile,
    create_profile as assist_create_profile,
    export_profile as assist_export_profile,
    import_profile as assist_import_profile,
    list_commands as assist_list_commands,
    list_profiles as assist_list_profiles,
    list_receipts as assist_list_receipts,
    get_profile as assist_get_profile,
)
from .assist_types import AssistAction, AssistDecision, AssistReceipt
from .ai_api import ApiDependencyError, api_status, serve_api
from .ai_audit import list_events as ai_list_events, log_event as ai_log_event
from .ai_auth import (
    create_user as ai_create_user,
    disable_owner_auto_auth as ai_disable_owner_auto_auth,
    get_owner_auto_auth as ai_get_owner_auto_auth,
    get_user_routing_pref as ai_get_user_routing_pref,
    issue_token as ai_issue_token,
    list_users as ai_list_users,
    list_user_routing_prefs as ai_list_user_routing_prefs,
    set_owner_auto_auth as ai_set_owner_auto_auth,
    set_user_routing_pref as ai_set_user_routing_pref,
    set_user_disabled as ai_set_user_disabled,
    set_user_password as ai_set_user_password,
    set_user_role as ai_set_user_role,
)
from .ai_codex_integration import (
    DEFAULT_CODEX_BRIDGE_HOST,
    DEFAULT_CODEX_BRIDGE_PORT,
    codex_bridge_status as ai_codex_bridge_status,
    codex_mcp_profile as ai_codex_mcp_profile,
    serve_codex_bridge,
)
from .ai_hybrid import run_hybrid_answer
from .ai_keyring import key_delete as ai_key_delete
from .ai_keyring import key_get as ai_key_get
from .ai_keyring import key_set as ai_key_set
from .ai_keyring import key_status as ai_key_status
from .ai_index2 import answer_query as ai2_answer_query
from .ai_index2 import build_index as ai2_build_index
from .ai_index2 import doctor_index as ai2_doctor_index
from .ai_index2 import index_stats as ai2_index_stats
from .ai_ingest import ingest_sources as ai_ingest_sources
from .ai_ingest import ingest_status as ai_ingest_status
from .ai_local import (
    LOCAL_PROVIDERS,
    answer_question,
    diagnose_target,
    diff_explain,
    index_repository,
    load_memory,
    route_request,
    store_memory,
)
from .ai_models import (
    add_or_update_model as ai_add_or_update_model,
    list_models as ai_list_models,
    recommend_models as ai_recommend_models,
    remove_model as ai_remove_model,
    set_default_model as ai_set_default_model,
)
from .ai_packs import (
    build_pack as ai_build_pack,
    install_pack as ai_install_pack,
    list_packs as ai_list_packs,
    verify_pack as ai_verify_pack,
)
from .ai_plugins import (
    disable_plugin as ai_disable_plugin,
    enable_plugin as ai_enable_plugin,
    install_plugin as ai_install_plugin,
    list_plugins as ai_list_plugins,
    verify_plugin as ai_verify_plugin,
)
from .ai_routing_policy import (
    TASK_TYPES as AI_ROUTING_TASK_TYPES,
    classify_task as ai_classify_task,
    compute_dynamic_threshold as ai_compute_dynamic_threshold,
    extract_task_features as ai_extract_task_features,
    load_routing_policy as ai_load_routing_policy,
    save_routing_policy as ai_save_routing_policy,
    update_routing_policy as ai_update_routing_policy,
    validate_routing_policy_payload as ai_validate_routing_policy_payload,
)
from .ai_perf import (
    run_benchmark as ai_run_benchmark,
    runtime_resource_state as ai_runtime_resource_state,
    summarize_perf_metrics as ai_summarize_perf_metrics,
    vram_tier_recommendation as ai_vram_tier_recommendation,
)
from .ai_quota import (
    quota_summary as ai_quota_summary,
    set_quota_budgets as ai_set_quota_budgets,
)
from .ai_router_state import load_router_state as ai_load_router_state
from .ai_sources import (
    add_allowed_domain as ai_add_allowed_domain,
    add_source as ai_add_source,
    list_sources as ai_list_sources,
    remove_source as ai_remove_source,
    sync_source as ai_sync_source,
)
from .ai_storage import (
    MAX_STORAGE_BYTES,
    StorageLimitError,
    gc_storage as ai_gc_storage,
    usage_report as ai_usage_report,
    verify_storage as ai_verify_storage,
)
from .ai_workspaces import (
    create_workspace as ai_create_workspace,
    list_workspaces as ai_list_workspaces,
    switch_workspace as ai_switch_workspace,
)
from .hardware_check import (
    assess_phase_support,
    collect_hardware_snapshot,
    format_hardware_report,
    hardware_report_payload,
)
from .jsonc_utils import dump_json as dump_jsonc_normalized
from .jsonc_utils import parse_jsonc
from .continue_config import (
    build_ccbs_continue_config,
    is_yaml_path as is_continue_yaml_path,
    load_continue_config as load_continue_config_file,
    merge_docs_context as merge_continue_docs_context,
    normalize_continue_config as normalize_continue_config_file,
    write_continue_config as write_continue_config_file,
)
from .book_library import (
    export_import_template as book_export_import_template,
    get_book as book_get_book,
    import_notes as book_import_notes,
    list_books as book_list_books,
    load_seed_books as book_load_seed_books,
    seed_books as book_seed_books,
)
_QUANTUM_IMPORT_ERROR: Exception | None = None
try:
    from .quantum_foundation import add_quantum_parser
except Exception as exc:  # noqa: BLE001
    _QUANTUM_IMPORT_ERROR = exc

    def add_quantum_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
        quantum = sub.add_parser(
            "quantum",
            help="Quantum foundation setup and execution (unavailable in this package build)",
        )
        quantum.set_defaults(func=_cmd_quantum_unavailable)
from .capability_orchestrator import (
    ACTION_FIX_ALL as CAP_ACTION_FIX_ALL,
    ACTION_REPAIR_CPP as CAP_ACTION_REPAIR_CPP,
    ACTION_REPAIR_NOTEBOOK as CAP_ACTION_REPAIR_NOTEBOOK,
    ACTION_START_LM_STUDIO as CAP_ACTION_START_LM_STUDIO,
    ACTION_START_OLLAMA as CAP_ACTION_START_OLLAMA,
    collect_capability_report,
    execute_capability_action,
)
from .lint import LintToolMissing, lint_one
from .log import utc_now, write_json_log
from .hyperv import add_hyperv_parser
from .pt_portmap import apply_link_ports, format_portmap_report
from .pt_preflight import MODES, format_report, run_preflight
from .qol_toolkit import validate_python_environment_integrity
from .repo import RepoError, repo_root
from .safety import (
    PERMISSION_LEVELS,
    TASK_REQUIREMENTS,
    permission_sufficient,
    recommend_permission,
    scan_path,
    write_scan_manifest,
)
from .spellcheck import run_spellcheck
from .validate import validate_all, validate_one
from .vscode_spell_sync import sync_vscode_spell_words

DEFAULT_PT_PATH = "public_menu/templates/packet_tracer/TPL-6-CAMPUS-3TIER"
VALIDATION_PROFILES = {
    "strict": {"mode": "deploy", "max_todo": 0, "max_unmapped_links": 0},
    "lab": {"mode": "deploy", "max_todo": 10, "max_unmapped_links": 10},
    "scaffold": {"mode": "scaffold", "max_todo": 9999, "max_unmapped_links": 9999},
}


def _common_paths() -> tuple[Path, Path, Path]:
    root = repo_root()
    schema = root / "tools" / "brick_schema.json"
    bricks = root / "bricks"
    return root, schema, bricks


def _looks_like_windows_abs_path(raw: str) -> bool:
    return len(raw) >= 3 and raw[1] == ":" and raw[0].isalpha() and raw[2] in ("\\", "/")


def _resolve_cli_path(root: Path, raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate

    # Accept Windows drive-letter paths when ccbs runs in WSL/Linux.
    if _looks_like_windows_abs_path(raw):
        if sys.platform.startswith("win"):
            return Path(raw)
        win_path = PureWindowsPath(raw)
        drive = win_path.drive.rstrip(":").lower()
        suffix = win_path.as_posix()[2:].lstrip("/")
        return (Path("/mnt") / drive / suffix).resolve()

    return (root / candidate).resolve()


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def _cmd_quantum_unavailable(_args: argparse.Namespace) -> int:
    detail = ""
    if _QUANTUM_IMPORT_ERROR is not None:
        detail = f" ({_QUANTUM_IMPORT_ERROR})"
    print("ERROR: quantum commands are unavailable in this package build" + detail)
    return 2


def _parse_bool_like(value: str) -> bool:
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def _endpoint_reachable(base_url: str, timeout_s: float = 1.25) -> bool:
    try:
        parsed = urllib.parse.urlparse(base_url)
        host = parsed.hostname
        if not host:
            return False
        port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
        with socket.create_connection((host, port), timeout=max(0.2, float(timeout_s))):
            return True
    except OSError:
        return False


def _is_loopback_bind_host(host: str) -> bool:
    text = str(host or "").strip().lower()
    if not text:
        return True
    if text == "localhost":
        return True
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    try:
        return ipaddress.ip_address(text).is_loopback
    except ValueError:
        return False


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("metadata JSON must be an object")
    return value


def _flatten_path_list(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in values or []:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _load_json_or_jsonc(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    try:
        return parse_jsonc(raw)
    except ValueError as exc:
        raise ValueError(f"invalid JSON/JSONC in {path}: {exc}") from exc


def _is_yaml_path(path: Path) -> bool:
    return is_continue_yaml_path(path)


def _load_continue_config(path: Path) -> dict[str, Any]:
    return load_continue_config_file(path)


def _write_continue_config(path: Path, payload: dict[str, Any]) -> None:
    write_continue_config_file(path, payload)


def _load_continue_template(root: Path) -> dict[str, Any]:
    template_path = root / "config" / "continue.config.template.json"
    if not template_path.exists():
        return {}
    try:
        return _load_json_or_jsonc(template_path)
    except ValueError:
        return {}


def _build_continue_config(
    root: Path,
    provider: str,
    local_model: str,
    local_fast_model: str,
    local_base_url: str,
    codex_model: str,
    codex_base_url: str,
    output_yaml_style: bool,
) -> dict[str, Any]:
    template = _load_continue_template(root)
    cfg = build_ccbs_continue_config(
        output_yaml_style=output_yaml_style,
        provider=provider,
        local_model=local_model,
        local_fast_model=local_fast_model,
        local_base_url=local_base_url,
        codex_model=codex_model,
        codex_base_url=codex_base_url,
    )
    if isinstance(template, dict):
        # YAML output should stay in current-style shape (`context`/`prompts`).
        # Templates are JSON legacy shape by default, so normalize before merge.
        template_payload = normalize_continue_config_file(template) if output_yaml_style else template
        cfg = {**template_payload, **cfg}
    return cfg


def _ai_index_db_path(root: Path) -> Path:
    return root / ".ccbs" / "ai" / "index.db"


def _ensure_ai_index(
    root: Path,
    index_path: str,
    index_max_files: int,
    as_json: bool,
) -> bool:
    index_db = _ai_index_db_path(root)
    if index_db.exists():
        return True

    target = _resolve_cli_path(root, index_path)
    if not target.exists():
        print(f"ERROR: auto-index path not found: {target}")
        return False

    if not as_json:
        print(f"Auto-index: {index_db} not found, indexing {target}...")
    summary = index_repository(root=root, target=target, max_files=max(1, index_max_files))
    if not as_json:
        print(
            f"Auto-index complete: files={summary.indexed_files} chunks={summary.indexed_chunks} "
            f"skipped={summary.skipped_files}"
        )
    return True


def _resolve_validation_settings(
    mode: str | None,
    max_todo: int | None,
    max_unmapped_links: int | None,
    profile: str | None,
    default_mode: str,
) -> dict[str, Any]:
    profile_cfg = VALIDATION_PROFILES.get(profile or "")
    resolved_mode = mode or (str(profile_cfg["mode"]) if profile_cfg else default_mode)
    resolved_max_todo = max_todo if max_todo is not None else (int(profile_cfg["max_todo"]) if profile_cfg else 0)
    resolved_max_unmapped = (
        max_unmapped_links
        if max_unmapped_links is not None
        else (int(profile_cfg["max_unmapped_links"]) if profile_cfg else 0)
    )
    return {
        "profile": profile or "custom",
        "mode": resolved_mode,
        "max_todo": max(0, int(resolved_max_todo)),
        "max_unmapped_links": max(0, int(resolved_max_unmapped)),
    }


def _answer_payload(question: str, result: Any) -> dict[str, Any]:
    return {
        "question": question,
        "answer": result.answer,
        "provider": result.provider,
        "model": result.model,
        "confidence": result.confidence,
        "sources": [
            {
                "path": hit.path,
                "chunk_id": hit.chunk_id,
                "score": hit.score,
            }
            for hit in result.hits
        ],
    }


def _print_answer(question: str, result: Any, as_json: bool) -> None:
    payload = _answer_payload(question=question, result=result)
    if as_json:
        _print_json(payload)
        return

    print(f"Question: {question}")
    print(f"Provider: {result.provider} | Model: {result.model} | Confidence: {result.confidence:.2f}")
    print("")
    print(result.answer)
    if result.hits:
        print("")
        print("Sources:")
        for hit in result.hits:
            print(f"  - {hit.path}#chunk{hit.chunk_id} (score={hit.score:.2f})")


def _run_answer(
    root: Path,
    question: str,
    provider: str,
    model: str,
    top_k: int,
    persist_memory: bool,
    as_json: bool,
    memory_kind: str,
    auto_index: bool,
    index_path: str,
    index_max_files: int,
) -> int:
    if auto_index and not _ensure_ai_index(
        root=root,
        index_path=index_path,
        index_max_files=index_max_files,
        as_json=as_json,
    ):
        return 2

    result = answer_question(
        root=root,
        question=question,
        provider=provider,
        model=model,
        top_k=max(1, top_k),
        offline=True,
    )
    _print_answer(question=question, result=result, as_json=as_json)
    if persist_memory:
        store_memory(
            root=root,
            kind=memory_kind,
            question=question,
            answer=result.answer,
            metadata={
                "provider": result.provider,
                "model": result.model,
                "confidence": result.confidence,
                "sources": [hit.path for hit in result.hits],
            },
        )
    return 0


def _run_validation_gate(
    root: Path,
    target: Path,
    max_todo: int,
    max_unmapped_links: int,
    mode: str = "deploy",
    as_json: bool = False,
    emit_output: bool = True,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    validate_failures: list[str] = []
    checked_count = 0

    schema = root / "tools" / "brick_schema.json"
    bricks = root / "bricks"

    if not target.exists():
        issues.append(f"path_missing:{target}")
    if not schema.exists():
        issues.append(f"schema_missing:{schema}")
    if not bricks.exists():
        issues.append(f"bricks_missing:{bricks}")

    if not issues:
        try:
            valid_ok, validate_failures, checked_count = validate_all(bricks, schema)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"validate_all_error:{exc}")
            valid_ok = False
        if not valid_ok:
            issues.append("validate_all_failed")

    preflight = run_preflight(
        target=target,
        max_todo=max(0, max_todo),
        max_unmapped_links=max(0, max_unmapped_links),
    )
    selected = next(item for item in preflight.outcomes if item.mode == mode)
    if not selected.ok:
        issues.append(f"pt_preflight_{mode}_failed")

    ok = not issues
    if emit_output and as_json:
        _print_json(
            {
                "ok": ok,
                "checked_metadata_files": checked_count,
                "metadata_failures": validate_failures[:20],
                "preflight_mode": mode,
                "preflight_mode_ok": selected.ok,
                "preflight_blockers": selected.blockers,
                "issues": issues,
            }
        )
    elif emit_output:
        print("Validation gate:")
        print(f"  - metadata files checked: {checked_count}")
        print(f"  - metadata validation: {'PASS' if 'validate_all_failed' not in issues else 'FAIL'}")
        print(f"  - preflight {mode} mode: {'PASS' if selected.ok else 'FAIL'}")
        if validate_failures:
            print("  - validation sample failures:")
            for item in validate_failures[:5]:
                print(f"    - {item}")
        if selected.blockers:
            print(f"  - preflight blockers: {', '.join(selected.blockers)}")
    return ok, issues


def cmd_repo_root(_: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(root)
    return 0


def cmd_sewing(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    runner = root / "sewing_machine" / "runner.py"
    if not runner.exists():
        print(f"ERROR: sewing runner not found: {runner}")
        return 2

    forwarded = list(getattr(args, "sewing_args", []) or [])
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        forwarded = ["--help"]

    command = [sys.executable, str(runner), *forwarded]
    proc = subprocess.run(command, cwd=str(root), check=False)
    return int(proc.returncode)


def cmd_spell_check(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    result = run_spellcheck(
        root=root,
        paths=list(getattr(args, "paths", []) or []),
        config_path=str(getattr(args, "config", "cspell.json")),
    )

    payload = {
        "ok": result.ok,
        "tool_found": result.tool_found,
        "return_code": result.return_code,
        "command": result.command,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if args.json:
        _print_json(payload)
        if not result.tool_found:
            return 2
        return 0 if result.ok else 1

    if not result.tool_found:
        print("ERROR: cspell is not installed or not in PATH.")
        print("Install it with one of:")
        print("  - npm install -g cspell")
        print("  - npm install --save-dev cspell  (then run via local node_modules/.bin)")
        print("  - npx cspell --no-progress --config cspell.json <paths>")
        return 2

    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    return 0 if result.ok else 1


def cmd_spell_sync_vscode(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    settings_path_raw = str(getattr(args, "settings_path", "") or "").strip()
    settings_path = _resolve_cli_path(root, settings_path_raw) if settings_path_raw else None

    try:
        result = sync_vscode_spell_words(
            root=root,
            settings_path=settings_path,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "ok": result.ok,
        "settings_path": result.settings_path,
        "source_words_count": result.source_words_count,
        "existing_words_count": result.existing_words_count,
        "added_words_count": result.added_words_count,
        "total_words_count": result.total_words_count,
        "dry_run": result.dry_run,
        "warnings": list(result.warnings),
    }
    if args.json:
        _print_json(payload)
        return 0

    print("VS Code spell sync:")
    print(f"  - settings path: {result.settings_path}")
    print(f"  - source words: {result.source_words_count}")
    print(f"  - existing words: {result.existing_words_count}")
    print(f"  - added words: {result.added_words_count}")
    print(f"  - total words: {result.total_words_count}")
    print(f"  - mode: {'dry-run' if result.dry_run else 'write'}")
    if result.warnings:
        print("  - warnings:")
        for item in result.warnings:
            print(f"    - {item}")
    print("Next step: VS Code -> Developer: Reload Window (or Extensions: Restart Extension Host)")
    return 0


def cmd_hardware_check(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError:
        root = Path.cwd()

    target = _resolve_cli_path(root, getattr(args, "path", "."))
    if not target.exists():
        print(f"ERROR: path not found: {target}")
        return 2

    snapshot = collect_hardware_snapshot(target)
    phase_results = assess_phase_support(snapshot)
    if args.json:
        _print_json(hardware_report_payload(snapshot, phase_results))
    else:
        print(format_hardware_report(snapshot, phase_results))
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    report = {"timestamp": utc_now(), "checks": []}

    try:
        root, schema, bricks = _common_paths()
        report["checks"].append({"name": "repo_root", "ok": True, "value": str(root)})
    except RepoError as exc:
        report["checks"].append({"name": "repo_root", "ok": False, "error": str(exc)})
        print("[FAIL] repo_root: not inside git repository")
        return 2

    schema_ok = schema.exists()
    report["checks"].append({"name": "schema", "ok": schema_ok, "value": str(schema)})
    print(f"[{'OK' if schema_ok else 'FAIL'}] schema: {schema}")

    bricks_ok = bricks.exists()
    report["checks"].append({"name": "bricks_dir", "ok": bricks_ok, "value": str(bricks)})
    print(f"[{'OK' if bricks_ok else 'FAIL'}] bricks_dir: {bricks}")

    proc = subprocess.run([sys.executable, "--version"], text=True, capture_output=True, check=False)
    py_ok = proc.returncode == 0
    report["checks"].append({"name": "python", "ok": py_ok, "value": proc.stdout.strip() or proc.stderr.strip()})
    print(f"[{'OK' if py_ok else 'FAIL'}] python: {proc.stdout.strip() or proc.stderr.strip()}")
    print(f"[OK] platform: {platform.platform()}")

    python_env_report = validate_python_environment_integrity(root=root, config={}, runtime_python=sys.executable)
    python_env_ok = str(python_env_report.get("status", "warn")) != "fail"
    report["checks"].append(
        {
            "name": "python_env_validation",
            "ok": python_env_ok,
            "value": str(python_env_report.get("status", "unknown")),
        }
    )
    report["python_environment"] = python_env_report
    print("[INFO] Python environment validation:")
    print(f"  - status: {python_env_report.get('status', 'unknown')}")
    approved = [str(item) for item in python_env_report.get("approved_venvs", []) if str(item).strip()]
    unexpected = [str(item) for item in python_env_report.get("unexpected_venvs", []) if str(item).strip()]
    print(f"  - approved_venvs: {', '.join(approved) if approved else 'none'}")
    print(f"  - unexpected_venvs: {', '.join(unexpected) if unexpected else 'none'}")
    configured_raw = str(python_env_report.get("configured_interpreter_raw", "")).strip()
    configured_resolved = str(python_env_report.get("configured_interpreter", "")).strip()
    if configured_raw:
        print(
            "  - vscode_interpreter: "
            + configured_raw
            + (f" -> {configured_resolved}" if configured_resolved else "")
        )
        print(f"  - vscode_interpreter_exists: {bool(python_env_report.get('configured_interpreter_exists', False))}")
        print(
            f"  - vscode_interpreter_approved: {bool(python_env_report.get('configured_interpreter_approved', False))}"
        )
    else:
        print("  - vscode_interpreter: not set")

    runtime_match = python_env_report.get("runtime_matches_configured", None)
    if runtime_match is None:
        print("  - runtime_matches_vscode: unknown")
    else:
        print(f"  - runtime_matches_vscode: {bool(runtime_match)}")

    for row in python_env_report.get("venvs", []):
        if not isinstance(row, dict):
            continue
        issues = [str(item) for item in row.get("issues", []) if str(item).strip()]
        warnings = [str(item) for item in row.get("warnings", []) if str(item).strip()]
        if row.get("status") == "pass" and row.get("approved"):
            extras = []
            if row.get("signature_available"):
                extras.append(f"signature={row.get('signature_status', '')}")
            if row.get("base_executable_exists"):
                extras.append("base_executable=present")
            detail = f" ({', '.join(extras)})" if extras else ""
            print(f"    - {row.get('path', '')}: pass{detail}")
            continue
        reasons = issues + warnings
        suffix = f" -> {', '.join(reasons)}" if reasons else ""
        scope = "approved" if row.get("approved") else "unexpected"
        print(f"    - {row.get('path', '')}: {row.get('status', 'unknown')} [{scope}]{suffix}")

    capability_report = collect_capability_report(root)
    report["capabilities"] = capability_report
    print("[INFO] Capability Orchestrator:")
    print(
        "  - workflow: "
        + " -> ".join([str(x) for x in capability_report.get("workflow", []) if str(x).strip()])
    )
    print(
        f"  - windows_cpp: {capability_report.get('windows_cpp', {}).get('status', 'unknown')}"
        f" | wsl_cpp: {capability_report.get('wsl_cpp', {}).get('status', 'unknown')}"
    )
    print(
        f"  - python_notebook: {capability_report.get('python_notebook', {}).get('status', 'unknown')}"
        f" | lm_studio: {capability_report.get('lm_studio', {}).get('status', 'unknown')}"
        f" | ollama: {capability_report.get('ollama', {}).get('status', 'unknown')}"
    )
    print(f"  - overall_ready: {bool(capability_report.get('overall_ready', False))}")
    fix_actions = capability_report.get("fix_actions", [])
    if isinstance(fix_actions, list) and fix_actions:
        print("  - suggested_fix_actions:")
        for item in fix_actions:
            if not isinstance(item, dict):
                continue
            print(f"    - {item.get('action_id', '')}: {item.get('label', '')}")

    log_path = write_json_log(report, root / ".ccbs" / "logs")
    print(f"Doctor report: {log_path}")
    if schema_ok and bricks_ok and py_ok and python_env_ok:
        return 0
    return 1


def _print_capability_status(payload: dict[str, Any]) -> None:
    print("Capability Orchestrator:")
    print(
        "  - workflow: "
        + " -> ".join([str(x) for x in payload.get("workflow", []) if str(x).strip()])
    )
    print(f"  - overall_ready: {bool(payload.get('overall_ready', False))}")
    print(
        f"  - windows_cpp: {payload.get('windows_cpp', {}).get('status', 'unknown')}"
        f" | wsl_cpp: {payload.get('wsl_cpp', {}).get('status', 'unknown')}"
    )
    print(
        f"  - python_notebook: {payload.get('python_notebook', {}).get('status', 'unknown')}"
        f" | lm_studio: {payload.get('lm_studio', {}).get('status', 'unknown')}"
        f" | ollama: {payload.get('ollama', {}).get('status', 'unknown')}"
    )
    print(f"  - provider_policy: lmstudio -> ollama fallback")
    actions = payload.get("fix_actions", [])
    if isinstance(actions, list) and actions:
        print("  - fix_actions:")
        for item in actions:
            if not isinstance(item, dict):
                continue
            print(
                "    - {action_id}: {label} (approval={approval}, network={network})".format(
                    action_id=str(item.get("action_id", "")),
                    label=str(item.get("label", "")),
                    approval=bool(item.get("requires_approval", False)),
                    network=bool(item.get("requires_network", False)),
                )
            )


def cmd_capabilities_status(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        payload = collect_capability_report(root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(payload)
    else:
        _print_capability_status(payload)
    return 0 if bool(payload.get("overall_ready", False)) else 1


def cmd_capabilities_fix(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        action = str(args.action or "").strip().lower()
        lane = str(getattr(args, "lane", "") or "").strip().lower()
        payload = execute_capability_action(
            root,
            action_id=action,
            approve=bool(getattr(args, "approve", False)),
            lane=lane,
            actor=str(os.environ.get("USERNAME", "") or os.environ.get("USER", "") or "cli"),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(payload)
    else:
        print(f"Action: {payload.get('action_id', action)}")
        print(f"Status: {payload.get('status', 'unknown')} ok={bool(payload.get('ok', False))}")
        if str(payload.get("message", "")).strip():
            print(str(payload.get("message", "")).strip())
        steps = payload.get("steps", [])
        if isinstance(steps, list) and steps:
            print("Steps:")
            for row in steps:
                if not isinstance(row, dict):
                    continue
                print(
                    "  - {step}: ok={ok} exit={exit_code}".format(
                        step=str(row.get("step", "")),
                        ok=bool(row.get("ok", False)),
                        exit_code=int(row.get("exit_code", 1)) if row.get("exit_code") is not None else "n/a",
                    )
                )
                stderr = str(row.get("stderr", "")).strip()
                if stderr:
                    print(f"    stderr: {stderr.splitlines()[0]}")
        verify = payload.get("verify", {})
        if isinstance(verify, dict) and verify:
            print(f"Verify overall_ready: {bool(verify.get('overall_ready', False))}")
    return 0 if bool(payload.get("ok", False)) else 1


def cmd_capabilities_run(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        initial = collect_capability_report(root)
        approve = bool(getattr(args, "approve", False))
        if bool(initial.get("overall_ready", False)):
            payload = {
                "ok": True,
                "status": "already_ready",
                "discover": initial,
                "verify": initial,
            }
        elif not approve:
            payload = {
                "ok": False,
                "status": "approval_required",
                "discover": initial,
                "message": "Capability issues found. Re-run with --approve to execute guided auto-fix.",
            }
        else:
            fix = execute_capability_action(
                root,
                action_id=CAP_ACTION_FIX_ALL,
                approve=True,
                lane=str(getattr(args, "lane", "") or "").strip().lower(),
                actor=str(os.environ.get("USERNAME", "") or os.environ.get("USER", "") or "cli"),
            )
            payload = {
                "ok": bool(fix.get("ok", False)),
                "status": str(fix.get("status", "executed")),
                "discover": initial,
                "execute": fix,
                "verify": dict(fix.get("verify", {})),
            }
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
    else:
        print("Capability orchestration:")
        discover = payload.get("discover", {})
        if isinstance(discover, dict):
            _print_capability_status(discover)
        print(f"status: {payload.get('status', 'unknown')}")
        if str(payload.get("message", "")).strip():
            print(str(payload.get("message", "")).strip())
        verify = payload.get("verify", {})
        if isinstance(verify, dict) and verify:
            print("verify:")
            _print_capability_status(verify)
    verify_payload = payload.get("verify", {})
    if isinstance(verify_payload, dict):
        return 0 if bool(verify_payload.get("overall_ready", False)) else 1
    return 0 if bool(payload.get("ok", False)) else 1


def cmd_validate_one(args: argparse.Namespace) -> int:
    try:
        root, schema, _ = _common_paths()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    target = _resolve_cli_path(root, args.path)
    if not target.exists():
        print(f"ERROR: file not found: {target}")
        return 2
    if not schema.exists():
        print(f"ERROR: schema missing: {schema}")
        return 2

    try:
        ok, errors, parsed = validate_one(target, schema)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    print(f"Parsed keys: {', '.join(sorted(parsed.keys()))}")
    if ok:
        print(f"VALID: {target}")
        return 0
    print(f"INVALID: {target}")
    for err in errors:
        print(f"  - {err}")
    return 1


def cmd_validate_all(_args: argparse.Namespace) -> int:
    try:
        _root, schema, bricks = _common_paths()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    if not schema.exists():
        print(f"ERROR: schema missing: {schema}")
        return 2
    if not bricks.exists():
        print(f"ERROR: bricks directory missing: {bricks}")
        return 2

    try:
        ok, failures, count = validate_all(bricks, schema)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    print(f"Checked {count} metadata file(s).")
    if ok:
        print("All bricks valid.")
        return 0
    print("Validation failures:")
    for failure in failures:
        print(f"  - {failure}")
    return 1


def cmd_lint_one(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    target = _resolve_cli_path(root, args.path)
    if not target.exists():
        print(f"ERROR: file not found: {target}")
        return 2

    try:
        ok, code, out, err = lint_one(target)
    except LintToolMissing as exc:
        print(f"ERROR: {exc}")
        return 2

    if out.strip():
        print(out.strip())
    if err.strip():
        print(err.strip())
    return 0 if ok else (1 if code != 0 else 0)


def cmd_admin_check(_: argparse.Namespace) -> int:
    print("IDEMPOTENT: admin check performs read-only repo and git diagnostics.")
    commands = [
        ["git", "status", "-sb"],
        ["git", "remote", "-v"],
        ["git", "branch", "-a"],
    ]
    for cmd in commands:
        proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
        print(f"$ {' '.join(cmd)}")
        print(proc.stdout.strip())
        if proc.stderr.strip():
            print(proc.stderr.strip())
    return 0


def cmd_admin_danger(args: argparse.Namespace) -> int:
    print("DESTRUCTIVE: this command may reset local branch state.")
    if not args.yes:
        print("Refusing to run destructive action without --yes")
        return 2
    proc = subprocess.run(["git", "reset", "--hard", "HEAD"], text=True, capture_output=True, check=False)
    print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip())
    return 0 if proc.returncode == 0 else 2


def cmd_pt_preflight(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    target = _resolve_cli_path(root, args.path)
    settings = _resolve_validation_settings(
        mode=args.mode,
        max_todo=args.max_todo,
        max_unmapped_links=args.max_unmapped_links,
        profile=args.profile,
        default_mode="config",
    )
    report = run_preflight(
        target,
        max_todo=settings["max_todo"],
        max_unmapped_links=settings["max_unmapped_links"],
    )
    print(format_report(report=report, mode=settings["mode"], as_json=args.json))

    selected = next(item for item in report.outcomes if item.mode == settings["mode"])
    return 0 if selected.ok else 1


def cmd_pt_apply_link_ports(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    target = _resolve_cli_path(root, args.path)
    report = apply_link_ports(target, write=args.write)
    print(format_portmap_report(report))
    return 1 if report.issues else 0


def cmd_pt_autopilot(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    target = _resolve_cli_path(root, args.path)
    settings = _resolve_validation_settings(
        mode=args.mode,
        max_todo=args.max_todo,
        max_unmapped_links=args.max_unmapped_links,
        profile=args.profile,
        default_mode="deploy",
    )
    if not target.exists():
        print(f"ERROR: path not found: {target}")
        return 2

    payload: dict[str, Any] = {
        "target": str(target),
        "profile": settings["profile"],
        "mode": settings["mode"],
        "max_todo": settings["max_todo"],
        "max_unmapped_links": settings["max_unmapped_links"],
        "force": bool(args.force),
        "steps": [],
    }
    if not args.json:
        print(f"PT autopilot target: {target}")
        print(
            f"Validation profile: {settings['profile']} "
            f"(mode={settings['mode']}, max_todo={settings['max_todo']}, "
            f"max_unmapped_links={settings['max_unmapped_links']})"
        )

    gate_ok, gate_issues = _run_validation_gate(
        root=root,
        target=target,
        max_todo=settings["max_todo"],
        max_unmapped_links=settings["max_unmapped_links"],
        mode=settings["mode"],
        as_json=False,
        emit_output=False,
    )
    payload["steps"].append({"name": "validation_gate", "ok": gate_ok, "issues": gate_issues})
    if not args.json:
        print(f"Step validation_gate: {'PASS' if gate_ok else 'FAIL'}")
        if gate_issues:
            print(f"  - issues: {', '.join(gate_issues)}")
    if not gate_ok and not args.force:
        if args.json:
            payload["ok"] = False
            _print_json(payload)
        else:
            print("Autopilot stopped: validation gate failed (use --force to continue).")
        return 1

    apply_report = apply_link_ports(target=target, write=True)
    apply_ok = not apply_report.issues
    payload["steps"].append(
        {
            "name": "apply_link_ports",
            "ok": apply_ok,
            "changed_files": apply_report.changed_files,
            "issues": apply_report.issues,
            "unresolved_rows": apply_report.unresolved_rows,
        }
    )
    if not args.json:
        print(format_portmap_report(apply_report))
    if not apply_ok and not args.force:
        if args.json:
            payload["ok"] = False
            _print_json(payload)
        else:
            print("Autopilot stopped: apply-link-ports reported issues (use --force to continue).")
        return 1

    final_report = run_preflight(
        target=target,
        max_todo=settings["max_todo"],
        max_unmapped_links=settings["max_unmapped_links"],
    )
    final_selected = next(item for item in final_report.outcomes if item.mode == settings["mode"])
    payload["steps"].append(
        {
            "name": "final_preflight",
            "ok": final_selected.ok,
            "mode": settings["mode"],
            "blockers": final_selected.blockers,
        }
    )
    if not args.json:
        print(format_report(report=final_report, mode=settings["mode"], as_json=False))

    overall_ok = gate_ok and apply_ok and final_selected.ok
    payload["ok"] = overall_ok
    if args.json:
        _print_json(payload)
    elif not overall_ok and args.force:
        print("Autopilot completed with force, but one or more checks still failed.")
    return 0 if overall_ok else 1


def _assist_action_payload(action: AssistAction) -> dict[str, Any]:
    return {
        "type": action.action_type,
        "payload": action.payload,
        "order_index": action.order_index,
    }


def _assist_decision_payload(decision: AssistDecision, receipt: AssistReceipt) -> dict[str, Any]:
    return {
        "decision": {
            "status": decision.status,
            "reason": decision.reason,
            "dry_run": decision.dry_run,
            "blocked": decision.blocked,
            "transcript_normalized": decision.transcript_normalized,
            "command_id": decision.command_id,
            "command_name": decision.command_name,
            "requires_confirmation": decision.requires_confirmation,
            "action_plan": [_assist_action_payload(item) for item in decision.action_plan],
        },
        "receipt": {
            "ts": receipt.ts,
            "profile_id": receipt.profile_id,
            "transcript_normalized": receipt.transcript_normalized,
            "status": receipt.status,
            "reason": receipt.reason,
            "command_name": receipt.command_name,
            "action_summary": receipt.action_summary,
            "confirm_used": receipt.confirm_used,
            "metadata": receipt.metadata,
        },
    }


def _parse_assist_actions(action_tokens: list[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for raw in action_tokens:
        token = raw.strip()
        if ":" not in token:
            raise ValueError(f"invalid action '{raw}' (expected type:payload)")
        action_type, payload = token.split(":", 1)
        t = action_type.strip()
        p = payload.strip()
        if not t or not p:
            raise ValueError(f"invalid action '{raw}' (expected type:payload)")
        parsed.append((t, p))
    if not parsed:
        raise ValueError("at least one --action is required")
    return parsed


def cmd_assist_profile_create(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        profile = assist_create_profile(
            root=root,
            profile_id=args.profile_id,
            game_name=args.game_name,
            offline_only=bool(args.offline_only),
            allow_multiplayer=bool(args.allow_multiplayer),
        )
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "profile_id": profile.profile_id,
        "game_name": profile.game_name,
        "offline_only": profile.offline_only,
        "allow_multiplayer": profile.allow_multiplayer,
        "ack_offline_single_player": profile.ack_offline_single_player,
    }
    if args.json:
        _print_json({"profile": payload})
    else:
        print("Assist profile created:")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def cmd_assist_profile_ack(args: argparse.Namespace) -> int:
    if not args.offline_single_player:
        print("ERROR: --offline-single-player is required for acknowledgement")
        return 2
    try:
        root = repo_root()
        profile = assist_ack_profile(
            root=root,
            profile_id=args.profile_id,
            offline_single_player=True,
        )
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "profile_id": profile.profile_id,
        "ack_offline_single_player": profile.ack_offline_single_player,
        "offline_only": profile.offline_only,
        "allow_multiplayer": profile.allow_multiplayer,
    }
    if args.json:
        _print_json({"profile": payload})
    else:
        print("Assist profile acknowledgement updated:")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def cmd_assist_profile_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        profiles = assist_list_profiles(root=root)
    except (RepoError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "profiles": [
            {
                "profile_id": item.profile_id,
                "game_name": item.game_name,
                "offline_only": item.offline_only,
                "allow_multiplayer": item.allow_multiplayer,
                "ack_offline_single_player": item.ack_offline_single_player,
            }
            for item in profiles
        ]
    }
    if args.json:
        _print_json(payload)
        return 0

    print(f"Assist profiles: {len(payload['profiles'])}")
    for item in payload["profiles"]:
        print(
            f"- {item['profile_id']} ({item['game_name']}) "
            f"offline_only={item['offline_only']} "
            f"allow_multiplayer={item['allow_multiplayer']} "
            f"ack={item['ack_offline_single_player']}"
        )
    return 0


def cmd_assist_profile_show(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        profile = assist_get_profile(root=root, profile_id=args.profile_id)
    except (RepoError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if profile is None:
        print(f"ERROR: profile not found: {args.profile_id}")
        return 2

    payload = {
        "profile_id": profile.profile_id,
        "game_name": profile.game_name,
        "offline_only": profile.offline_only,
        "allow_multiplayer": profile.allow_multiplayer,
        "ack_offline_single_player": profile.ack_offline_single_player,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
    if args.json:
        _print_json({"profile": payload})
    else:
        print(json.dumps(payload, indent=2))
    return 0


def cmd_assist_profile_export(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out_path = _resolve_cli_path(root, args.out_path)
        saved = assist_export_profile(root=root, profile_id=args.profile_id, out_path=out_path)
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json({"profile_id": args.profile_id, "output": str(saved)})
    else:
        print(f"Exported assist profile {args.profile_id} -> {saved}")
    return 0


def cmd_assist_profile_import(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        in_path = _resolve_cli_path(root, args.in_path)
        if not in_path.exists():
            print(f"ERROR: path not found: {in_path}")
            return 2
        profile = assist_import_profile(root=root, in_path=in_path, profile_id_override=args.profile_id)
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "profile_id": profile.profile_id,
        "game_name": profile.game_name,
        "offline_only": profile.offline_only,
        "allow_multiplayer": profile.allow_multiplayer,
        "ack_offline_single_player": profile.ack_offline_single_player,
    }
    if args.json:
        _print_json({"profile": payload})
    else:
        print("Imported assist profile:")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def cmd_assist_command_add(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        actions = _parse_assist_actions(args.action)
        command = assist_add_command(
            root=root,
            profile_id=args.profile_id,
            name=args.name,
            phrase=args.phrase,
            phrase_norm=normalize_transcript(args.phrase),
            actions=actions,
            cooldown_ms=max(0, int(args.cooldown_ms)),
            confirm_level=args.confirm_level,
        )
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "command_id": command.command_id,
        "profile_id": command.profile_id,
        "name": command.name,
        "phrases": command.phrases,
        "actions": [_assist_action_payload(item) for item in command.actions],
        "cooldown_ms": command.cooldown_ms,
        "confirm_level": command.confirm_level,
    }
    if args.json:
        _print_json({"command": payload})
    else:
        print("Assist command added:")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def cmd_assist_command_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        commands = assist_list_commands(root=root, profile_id=args.profile_id)
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "profile_id": args.profile_id,
        "commands": [
            {
                "command_id": item.command_id,
                "name": item.name,
                "phrases": item.phrases,
                "actions": [_assist_action_payload(action) for action in item.actions],
                "cooldown_ms": item.cooldown_ms,
                "confirm_level": item.confirm_level,
                "enabled": item.enabled,
            }
            for item in commands
        ],
    }
    if args.json:
        _print_json(payload)
        return 0

    print(f"Assist commands for profile {args.profile_id}: {len(payload['commands'])}")
    for item in payload["commands"]:
        print(
            f"- #{item['command_id']} {item['name']} "
            f"cooldown_ms={item['cooldown_ms']} confirm_level={item['confirm_level']} "
            f"phrases={len(item['phrases'])} actions={len(item['actions'])}"
        )
    return 0


def cmd_assist_run(args: argparse.Namespace) -> int:
    if args.live_input:
        print("ERROR: --live-input is not supported in phase-1. Use dry-run only.")
        return 2
    try:
        root = repo_root()
        decision, receipt = run_assist_dry(
            root=root,
            profile_id=args.profile,
            transcript=args.transcript,
            confirm=bool(args.confirm),
        )
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = _assist_decision_payload(decision, receipt)
    if args.json:
        _print_json(payload)
    else:
        print("Assist run (dry-run only):")
        print(f"- status: {decision.status}")
        print(f"- reason: {decision.reason}")
        print(f"- transcript_normalized: {decision.transcript_normalized}")
        print(f"- command_name: {decision.command_name or '<none>'}")
        print(f"- blocked: {decision.blocked}")
        print(f"- action_count: {len(decision.action_plan)}")
        if decision.action_plan:
            print("Action plan:")
            for item in decision.action_plan:
                print(f"  - {item.order_index}. {item.action_type}:{item.payload}")
        print(f"Receipt: {receipt.ts}")
    return 0


def cmd_assist_receipts(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        receipts = assist_list_receipts(root=root, profile_id=args.profile, limit=max(1, args.limit))
    except (RepoError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "profile_id": args.profile or "",
        "receipts": [
            {
                "ts": item.ts,
                "profile_id": item.profile_id,
                "transcript_normalized": item.transcript_normalized,
                "status": item.status,
                "reason": item.reason,
                "command_name": item.command_name,
                "action_summary": item.action_summary,
                "confirm_used": item.confirm_used,
                "metadata": item.metadata,
            }
            for item in receipts
        ],
    }
    if args.json:
        _print_json(payload)
        return 0

    print(f"Assist receipts: {len(payload['receipts'])}")
    for item in payload["receipts"]:
        print(
            f"- {item['ts']} [{item['profile_id']}] status={item['status']} "
            f"command={item['command_name'] or '<none>'} reason={item['reason']}"
        )
    return 0


def cmd_assist_pack(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        output = _resolve_cli_path(root, args.output)
        result = build_assist_pack(root=root, output=output, include_local_profiles=bool(args.include_local_profiles))
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "output": result.output,
        "file_count": result.file_count,
        "manifest_entries": result.manifest_entries,
    }
    if args.json:
        _print_json(payload)
    else:
        print("Assist pack built:")
        for key, value in payload.items():
            print(f"- {key}: {value}")
    return 0


def cmd_book_seed(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        seed_path = _resolve_cli_path(root, args.path)
        if not seed_path.exists():
            print(f"ERROR: seed file not found: {seed_path}")
            return 2
        books = book_load_seed_books(seed_path)
        result = book_seed_books(root=root, books=books, replace=bool(args.replace))
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {"seed_path": str(seed_path), **result}
    if args.json:
        _print_json(payload)
    else:
        print("Book catalog seeded:")
        print(f"- seed_path: {payload['seed_path']}")
        print(f"- inserted: {payload['inserted']}")
        print(f"- updated: {payload['updated']}")
        print(f"- total_books: {payload['total_books']}")
        print(f"- library_path: {payload['library_path']}")
    return 0


def cmd_book_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        rows = book_list_books(root=root, query=args.query, tag=args.tag)
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {"count": len(rows), "books": rows}
    if args.json:
        _print_json(payload)
        return 0

    print(f"Books in local catalog: {payload['count']}")
    for item in rows:
        authors = ", ".join(str(x) for x in item.get("authors", []))
        print(
            f"- {item.get('book_id')} | {item.get('title')} | {item.get('edition')} "
            f"| notes={item.get('notes_count', 0)} | authors={authors}"
        )
    return 0


def cmd_book_show(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        book = book_get_book(root=root, book_id=args.book_id)
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if book is None:
        print(f"ERROR: book not found: {args.book_id}")
        return 2
    if args.json:
        _print_json({"book": book})
    else:
        print(json.dumps(book, indent=2))
    return 0


def cmd_book_import_notes(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        source_path = _resolve_cli_path(root, args.path)
        result = book_import_notes(
            root=root,
            book_id=args.book_id,
            source_path=source_path,
            fmt=args.format,
        )
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(result)
    else:
        print("Imported notes/highlights:")
        print(f"- book_id: {result['book_id']}")
        print(f"- format: {result['format']}")
        print(f"- notes_count: {result['notes_count']}")
        print(f"- saved_path: {result['saved_path']}")
        print(f"- library_path: {result['library_path']}")
    return 0


def cmd_book_export_template(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = _resolve_cli_path(root, args.output)
        saved = book_export_import_template(path=out, fmt=args.format)
    except (RepoError, ValueError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {"format": args.format, "output": str(saved)}
    if args.json:
        _print_json(payload)
    else:
        print(f"Template exported: {saved}")
    return 0


def cmd_ai_index(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    target = _resolve_cli_path(root, args.path)
    if not target.exists():
        print(f"ERROR: path not found: {target}")
        return 2

    summary = index_repository(root=root, target=target, max_files=max(1, args.max_files))
    payload = {
        "target": summary.target,
        "indexed_files": summary.indexed_files,
        "indexed_chunks": summary.indexed_chunks,
        "skipped_files": summary.skipped_files,
    }
    if args.json:
        _print_json(payload)
    else:
        print(f"Indexed target: {summary.target}")
        print(f"Indexed files: {summary.indexed_files}")
        print(f"Indexed chunks: {summary.indexed_chunks}")
        print(f"Skipped files: {summary.skipped_files}")
    return 0


def cmd_ai_answer(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    question = " ".join(args.question).strip()
    if not question:
        print("ERROR: empty question")
        return 2

    return _run_answer(
        root=root,
        question=question,
        provider=args.provider,
        model=args.model,
        top_k=args.top_k,
        persist_memory=args.memory,
        as_json=args.json,
        memory_kind="qa",
        auto_index=args.auto_index,
        index_path=args.index_path,
        index_max_files=args.index_max_files,
    )


def cmd_ai_chat(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    if getattr(args, "chat_cmd", "") == "models":
        catalog = discover_model_catalog(root)
        if args.json:
            _print_json(catalog)
            return 0
        rows = list(catalog.get("models", []))
        print(f"Chat model catalog: {len(rows)}")
        for row in rows:
            src = ",".join(row.get("sources", [])) if isinstance(row.get("sources"), list) else str(row.get("source", ""))
            print(
                f"- {row.get('provider')} {row.get('model')} base={row.get('base_url')} "
                f"reachable={row.get('reachable')} installed={row.get('installed')} src={src}"
            )
        if catalog.get("errors"):
            print("Warnings:")
            for item in catalog.get("errors", []):
                print(f"- {item}")
        return 0

    if getattr(args, "chat_cmd", "") == "profile":
        conn = ai3_connect_runtime(root)
        try:
            username = str(args.user_id or "default").strip() or "default"
            if args.profile_set:
                updates = {
                    "display_name": str(args.display_name or "").strip(),
                    "avatar_style": str(args.avatar_style or "").strip(),
                    "theme": str(args.theme or "").strip(),
                    "preferred_model": str(args.preferred_model or "").strip(),
                    "tone_preset": str(args.tone_preset or "").strip(),
                }
                updates = {k: v for k, v in updates.items() if v}
                out = ai3_set_chat_profile(conn, values=updates, user_id=username)
            else:
                out = ai3_get_chat_profile(conn, user_id=username)
        finally:
            conn.close()
        payload = {"user_id": username, "profile": out}
        if args.json:
            _print_json(payload)
        else:
            print(f"Chat profile ({username}):")
            for key in ("display_name", "avatar_style", "theme", "preferred_model", "tone_preset"):
                print(f"- {key}: {out.get(key, '')}")
        return 0

    print("Offline local chat. Type 'exit' to stop.")
    if args.auto_index and not _ensure_ai_index(
        root=root,
        index_path=args.index_path,
        index_max_files=args.index_max_files,
        as_json=False,
    ):
        return 2

    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            break
        _run_answer(
            root=root,
            question=question,
            provider=args.provider,
            model=args.model,
            top_k=args.top_k,
            persist_memory=args.memory,
            as_json=False,
            memory_kind="chat",
            auto_index=False,
            index_path=args.index_path,
            index_max_files=args.index_max_files,
        )
        print("")
    return 0


def cmd_ai_memory(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    rows = load_memory(root=root, limit=max(1, args.limit))
    if args.json:
        _print_json({"entries": rows})
        return 0

    if not rows:
        print("No local memory entries found.")
        return 0

    print(f"Recent memory entries: {len(rows)}")
    for item in rows:
        print(f"- {item['ts']} [{item['kind']}]")
        print(f"  Q: {item['question']}")
        print(f"  A: {item['answer']}")
    return 0


def cmd_ai_diagnose(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    target = _resolve_cli_path(root, args.path)
    report = diagnose_target(target)
    payload = {
        "target": report.target,
        "scanned_manifests": report.scanned_manifests,
        "items": [item.__dict__ for item in report.items],
        "recommendations": report.recommendations,
    }
    if args.json:
        _print_json(payload)
        return 0

    print(f"Diagnose target: {report.target}")
    print(f"Scanned manifests: {report.scanned_manifests}")
    for item in report.items[:20]:
        print(f"- {item.manifest}: {item.status} ({item.detail})")
    if report.recommendations:
        print("Recommendations:")
        for rec in report.recommendations:
            print(f"  - {rec}")
    return 0


def cmd_ai_diff_explain(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    old_path = _resolve_cli_path(root, args.old_path)
    new_path = _resolve_cli_path(root, args.new_path)
    if not old_path.exists():
        print(f"ERROR: old file not found: {old_path}")
        return 2
    if not new_path.exists():
        print(f"ERROR: new file not found: {new_path}")
        return 2

    report = diff_explain(old_path=old_path, new_path=new_path)
    payload = {
        "old_path": report.old_path,
        "new_path": report.new_path,
        "added_count": report.added_count,
        "removed_count": report.removed_count,
        "categories": report.categories,
        "highlights": report.highlights,
    }
    if args.json:
        _print_json(payload)
    else:
        print(f"Diff explain: {report.old_path} -> {report.new_path}")
        print(f"Added commands: {report.added_count}")
        print(f"Removed commands: {report.removed_count}")
        print("Categories:")
        for key, value in report.categories.items():
            print(f"  - {key}: {value}")
        if report.highlights:
            print("Highlights:")
            for line in report.highlights:
                print(f"  - {line}")
    return 0


def cmd_ai_model_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        models = ai_list_models(root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {"models": models}
    if args.json:
        _print_json(payload)
        return 0

    print(f"Models: {len(models)}")
    for item in models:
        tags = ",".join(item.get("tags", []))
        print(
            f"- {item.get('model_id')} provider={item.get('provider')} model={item.get('model')} "
            f"installed={item.get('installed')} tags={tags}"
        )
    return 0


def cmd_ai_model_install(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        item = ai_add_or_update_model(
            root=root,
            model_id=args.model_id,
            provider=args.provider,
            model=args.model,
            tags=args.tags or [],
            installed=True,
            notes=args.notes or "",
        )
        ai_log_event(root, "model_install", "local_admin", {"model_id": args.model_id, "provider": args.provider})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(item)
    else:
        print(f"Model installed: {item['model_id']}")
    return 0


def cmd_ai_model_remove(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_remove_model(root=root, model_id=args.model_id)
        ai_log_event(root, "model_remove", "local_admin", {"model_id": args.model_id})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Model removed: {out['removed']}")
    return 0


def cmd_ai_model_set_default(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_set_default_model(root=root, task=args.task, model_id=args.model_id)
        ai_log_event(root, "model_set_default", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Default model set: task={out['task']} model={out['model_id']}")
    return 0


def cmd_ai_model_recommend(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        target = _resolve_cli_path(root, args.path)
        out = ai_recommend_models(root=root, path_for_disk=target)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print("Model recommendation:")
        print(f"- RAM GB: {out['ram_gb']:.2f}")
        print(f"- CPU: {out['cpu']}")
        for task, model_id in out["recommended"].items():
            print(f"  - {task}: {model_id}")
        for hint in out.get("hints", []):
            print(f"- hint: {hint}")
    return 0


def cmd_ai_source_add(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        if args.allow_domain:
            ai_add_allowed_domain(root=root, domain=args.allow_domain)
        out = ai_add_source(
            root=root,
            source_id=args.source_id,
            uri=args.uri,
            license_name=args.license_name,
            source_name=args.name or "",
            notes=args.notes or "",
        )
        ai_log_event(root, "source_add", "local_admin", {"source_id": args.source_id, "uri": args.uri})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Source added: {out['source_id']} ({out['kind']})")
    return 0


def cmd_ai_source_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        rows = ai_list_sources(root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    payload = {"sources": rows}
    if args.json:
        _print_json(payload)
        return 0
    print(f"Sources: {len(rows)}")
    for item in rows:
        print(
            f"- {item.get('source_id')} status={item.get('status')} kind={item.get('kind')} "
            f"bytes={item.get('bytes')} uri={item.get('uri')}"
        )
    return 0


def cmd_ai_source_sync(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_sync_source(root=root, source_id=args.source_id)
        ai_log_event(root, "source_sync", "local_admin", {"source_id": args.source_id, "bytes": out.get("bytes", 0)})
    except StorageLimitError as exc:
        try:
            root = repo_root()
            ai_log_event(root, "storage_limit_reached", "local_admin", {"stage": "source_sync", "detail": str(exc)})
        except Exception:  # noqa: BLE001
            pass
        print(f"ERROR: {exc}")
        return 1
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Source synced: {out['source_id']} bytes={out.get('bytes', 0)}")
    return 0


def cmd_ai_source_remove(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_remove_source(root=root, source_id=args.source_id, delete_files=not args.keep_files)
        ai_log_event(root, "source_remove", "local_admin", {"source_id": args.source_id})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Source removed: {out['removed']}")
    return 0


def cmd_ai_ingest_run(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_ingest_sources(root=root, source_id=args.source_id or "", max_files=max(1, args.max_files))
        ai_log_event(root, "ingest_run", "local_admin", out)
    except StorageLimitError as exc:
        try:
            root = repo_root()
            ai_log_event(root, "storage_limit_reached", "local_admin", {"stage": "ingest_run", "detail": str(exc)})
        except Exception:  # noqa: BLE001
            pass
        print(f"ERROR: {exc}")
        return 1
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(out)
    else:
        print(
            f"Ingest complete: sources={out['sources_processed']} normalized={out['normalized_files']} "
            f"skipped={out['skipped_files']} bytes={out['written_bytes']}"
        )
    return 0


def cmd_ai_ingest_status(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_ingest_status(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Ingest status: sources={out['source_count']} normalized_files={out['normalized_files']}")
        for key, value in out["status_counts"].items():
            print(f"- {key}: {value}")
    return 0


def cmd_ai_ingest_rebuild(args: argparse.Namespace) -> int:
    rc = cmd_ai_ingest_run(args)
    if rc != 0:
        return rc
    build_args = argparse.Namespace(source_id=args.source_id, max_files=args.max_files, json=args.json)
    return cmd_ai_index_build2(build_args)


def cmd_ai_index_build2(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai2_build_index(root=root, source_id=args.source_id or "", max_files=max(1, args.max_files))
        ai_log_event(root, "index_build", "local_admin", out.__dict__)
    except StorageLimitError as exc:
        try:
            root = repo_root()
            ai_log_event(root, "storage_limit_reached", "local_admin", {"stage": "index_build", "detail": str(exc)})
        except Exception:  # noqa: BLE001
            pass
        print(f"ERROR: {exc}")
        return 1
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    payload = out.__dict__
    if args.json:
        _print_json(payload)
    else:
        print(
            f"Index build complete: docs={out.docs_indexed} chunks={out.chunks_indexed} "
            f"skipped={out.skipped_files} db={out.db_path}"
        )
    return 0


def cmd_ai_index_stats2(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai2_index_stats(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(
            f"Index stats: exists={out['exists']} docs={out['docs']} chunks={out['chunks']} bytes={out['bytes']}"
        )
    return 0


def cmd_ai_index_query2(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        question = " ".join(args.question).strip()
        out = ai2_answer_query(
            root=root,
            question=question,
            top_k=max(1, args.top_k),
            task=args.task,
            model_id=args.model_id,
            provider=args.provider,
        )
        if args.memory:
            store_memory(
                root=root,
                kind="ai2-query",
                question=question,
                answer=str(out.get("answer", "")),
                metadata={"citations": out.get("citations", [])},
            )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Question: {out['question']}")
        print("")
        print(out["answer"])
        print("")
        print("Citations:")
        for row in out.get("citations", []):
            print(f"- {row['path']}#chunk{row['chunk_id']} (score={row['score']:.4f})")
    return 0


def cmd_ai_index_doctor2(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai2_doctor_index(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Index doctor: {'OK' if out['ok'] else 'FAIL'}")
        for issue in out.get("issues", []):
            print(f"- {issue}")
    return 0 if out.get("ok") else 1


def cmd_ai_route_policy_show(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        policy = ai_load_routing_policy(root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(policy)
        return 0
    print(f"Routing policy mode: {policy.get('mode')}")
    print(f"Ask on uncertain: {policy.get('ask_on_uncertain')}")
    dyn = dict(policy.get("dynamic_thresholds", {}))
    profiles = dict(policy.get("profiles", {}))
    active_profile = str(policy.get("active_profile", "")).strip().lower()
    profile = dict(profiles.get(active_profile, {}))
    decision = dict(policy.get("decision_engine", {}))
    print(
        "Threshold:"
        f" base={policy.get('uncertain_threshold')} dynamic_base={dyn.get('base_uncertain_threshold')} "
        f"margin={policy.get('min_margin')}"
    )
    print(
        "Local routing:"
        f" provider={policy.get('default_local_provider')} local_model={profile.get('default_local_model', '')} "
        f"codex_model={policy.get('default_codex_model')}"
    )
    print(f"Remote providers: {[str(r.get('provider_id')) for r in policy.get('remote_providers', []) if isinstance(r, dict)]}")
    print(f"Active profile: {policy.get('active_profile')} baseline={policy.get('baseline_local_tier')}")
    print(
        "Decision engine:"
        f" mode={decision.get('primary_mode')} classical_baseline_required={decision.get('classical_baseline_required')} "
        f"quantum_preferred={decision.get('prefer_quantum_when_available')} quantum_enabled={decision.get('quantum_enabled')} "
        f"backend={decision.get('quantum_backend')} fallback={decision.get('fallback_mode')} "
        f"verification={decision.get('verification_boundary')}"
    )
    print(
        "Backends:"
        f" primary={decision.get('primary_backend')} fallback_backend={decision.get('fallback_backend')} "
        f"priority={decision.get('backend_priority')} sprint_mode={decision.get('sprint_mode')}"
    )
    use_cases = list(decision.get("quantum_use_cases", []))
    if use_cases:
        print(f"Decision engine use cases: {use_cases}")
    return 0


def cmd_ai_route_policy_set(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        current_policy = ai_load_routing_policy(root)
        updates: dict[str, Any] = {}

        if args.mode:
            updates["mode"] = args.mode
        if args.uncertain_threshold is not None:
            updates["uncertain_threshold"] = float(args.uncertain_threshold)
        if args.min_margin is not None:
            updates["min_margin"] = float(args.min_margin)
        if args.ask_on_uncertain is not None:
            updates["ask_on_uncertain"] = bool(args.ask_on_uncertain)
        if args.profile:
            updates["active_profile"] = args.profile.strip().lower()
        if args.default_local_provider:
            updates["default_local_provider"] = args.default_local_provider
        if args.default_codex_model:
            updates["default_codex_model"] = args.default_codex_model

        decision_updates = dict(current_policy.get("decision_engine", {}))
        touched_decision_engine = False
        if args.prefer_quantum_when_available is not None:
            decision_updates["prefer_quantum_when_available"] = bool(args.prefer_quantum_when_available)
            touched_decision_engine = True
        if args.quantum_enabled is not None:
            decision_updates["quantum_enabled"] = bool(args.quantum_enabled)
            touched_decision_engine = True
        if args.quantum_backend:
            decision_updates["quantum_backend"] = args.quantum_backend.strip()
            touched_decision_engine = True
        if args.quantum_use_case:
            use_cases: list[str] = []
            for chunk in args.quantum_use_case:
                for item in str(chunk).split(","):
                    text = item.strip().lower()
                    if text and text not in use_cases:
                        use_cases.append(text)
            decision_updates["quantum_use_cases"] = use_cases
            touched_decision_engine = True
        if touched_decision_engine:
            updates["decision_engine"] = decision_updates

        for item in args.set:
            if "=" not in item:
                raise ValueError(f"invalid --set expression (expected key=value): {item}")
            key, value = item.split("=", 1)
            key = key.strip()
            raw = value.strip()
            if not key:
                raise ValueError("invalid --set key")
            if raw.startswith("{") or raw.startswith("["):
                updates[key] = json.loads(raw)
                continue
            try:
                updates[key] = _parse_bool_like(raw)
                continue
            except ValueError:
                pass
            try:
                updates[key] = int(raw)
                continue
            except ValueError:
                pass
            try:
                updates[key] = float(raw)
                continue
            except ValueError:
                pass
            updates[key] = raw

        policy = ai_update_routing_policy(root, updates)
        validation = ai_validate_routing_policy_payload(policy)
        ai_log_event(root, "route_policy_set", "local_admin", {"updates": updates, "ok": validation["ok"]})
    except (json.JSONDecodeError, RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {"ok": bool(validation["ok"]), "issues": validation["issues"], "policy": validation["policy"]}
    if args.json:
        _print_json(payload)
    else:
        print(f"Route policy updated: ok={payload['ok']}")
        if payload["issues"]:
            print("Issues:")
            for issue in payload["issues"]:
                print(f"- {issue}")
    return 0 if payload["ok"] else 1


def cmd_ai_route_policy_validate(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        policy = ai_load_routing_policy(root)
        out = ai_validate_routing_policy_payload(policy)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(out)
    else:
        print(f"Routing policy validate: {'OK' if out['ok'] else 'FAIL'}")
        if out["issues"]:
            for issue in out["issues"]:
                print(f"- {issue}")
    return 0 if out["ok"] else 1


def cmd_ai_route_policy_simulate(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        prompt = " ".join(args.prompt).strip()
        if not prompt:
            raise ValueError("prompt is required")
        metadata = _parse_json_object(args.metadata_json)
        quota = ai_quota_summary(root)
        resources = ai_runtime_resource_state()
        policy = ai_load_routing_policy(root)
        decision = ai_classify_task(
            prompt,
            requested_task_type="auto",
            policy=policy,
            metadata=metadata,
            root=root,
            quota_state=quota,
            resource_state=resources,
        )
        payload = {
            "prompt": prompt,
            "decision": decision,
            "quota_state": quota,
            "resource_state": resources,
        }
    except (json.JSONDecodeError, RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
    else:
        print(f"Task type: {decision.get('task_type')} confidence={float(decision.get('confidence', 0.0)):.2f}")
        print(f"Recommended route: {decision.get('recommended_route')} uncertain={decision.get('uncertain')}")
        print(f"Dynamic threshold: {decision.get('dynamic_threshold')}")
    return 0


def cmd_ai_route_ask(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        task_summary = " ".join(args.task_summary).strip()
        if not task_summary:
            raise ValueError("task summary is required")

        options = [opt.strip().lower() for opt in str(args.options).split(",") if opt.strip()]
        if not options:
            options = ["local", "codex", "both"]
        options = [opt for opt in options if opt in {"local", "codex", "both"}]
        if not options:
            raise ValueError("options must include one of: local,codex,both")

        policy = ai_load_routing_policy(root)
        metadata = _parse_json_object(args.metadata_json)
        decision = ai_classify_task(
            task_summary,
            requested_task_type="auto",
            policy=policy,
            metadata=metadata,
            root=root,
            quota_state=ai_quota_summary(root),
            resource_state=ai_runtime_resource_state(),
        )
        recommended = str(decision.get("recommended_route", "local"))
        if recommended not in options:
            recommended = options[0]

        selected = recommended
        if args.choose:
            choice = str(args.choose).strip().lower()
            if choice not in options:
                raise ValueError(f"--choose must be one of: {','.join(options)}")
            selected = choice
        elif args.interactive and sys.stdin.isatty():
            joined = "/".join(options)
            raw = input(f"Route choice [{joined}] (recommended: {recommended}): ").strip().lower()
            if raw in options:
                selected = raw

        payload = {
            "task_summary": task_summary,
            "task_type": decision.get("task_type", "auto"),
            "confidence": decision.get("confidence", 0.0),
            "uncertain": bool(decision.get("uncertain", False)),
            "reasons": decision.get("reasons", []),
            "options": options,
            "recommended": recommended,
            "selected": selected,
        }
        ai_log_event(root, "route_ask", "local_user", payload)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
    else:
        print(f"Task type: {payload['task_type']} confidence={float(payload['confidence']):.2f}")
        print(f"Route recommendation: {payload['recommended']} (selected: {payload['selected']})")
        if payload["reasons"]:
            print("Reasons:")
            for reason in payload["reasons"]:
                print(f"- {reason}")
    return 0


def cmd_ai_continue_setup(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        output_path = _resolve_cli_path(root, args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        remote_base = args.codex_base_url.rstrip("/")
        cfg = _build_continue_config(
            root=root,
            provider=args.provider,
            local_model=args.local_model,
            local_fast_model=args.local_fast_model,
            local_base_url=args.local_base_url,
            codex_model=args.codex_model,
            codex_base_url=remote_base,
            output_yaml_style=_is_yaml_path(output_path),
        )

        if output_path.exists() and not args.force:
            raise ValueError(f"output already exists: {output_path} (use --force to overwrite)")

        _write_continue_config(output_path, cfg)
        payload = {
            "written": str(output_path),
            "provider": args.provider,
            "local_model": args.local_model,
            "codex_model": args.codex_model,
            "codex_base_url": remote_base,
            "format": "yaml" if _is_yaml_path(output_path) else "json",
        }
        ai_log_event(root, "continue_setup", "local_admin", payload)
    except (json.JSONDecodeError, RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
    else:
        print(f"Continue config written: {payload['written']}")
        print(f"Local provider/model: {payload['provider']} / {payload['local_model']}")
        print(f"Codex model/base: {payload['codex_model']} / {payload['codex_base_url']}")
    return 0


def cmd_ai_key_set(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_key_set(root=root, provider_id=args.provider, api_key=args.api_key, user_id=args.user_id or "default")
        ai_log_event(root, "key_set", args.user_id or "local_admin", {"provider_id": args.provider})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Key stored: provider={out['provider_id']} user={out['user_id']} masked={out['masked']}")
    return 0


def cmd_ai_key_get(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_key_get(root=root, provider_id=args.provider, user_id=args.user_id or "default")
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Key: provider={out['provider_id']} user={out['user_id']} masked={out['masked']}")
    return 0


def cmd_ai_key_delete(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_key_delete(root=root, provider_id=args.provider, user_id=args.user_id or "default")
        ai_log_event(root, "key_delete", args.user_id or "local_admin", {"provider_id": args.provider, "deleted": out["deleted"]})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Key deleted: provider={out['provider_id']} user={out['user_id']} deleted={out['deleted']}")
    return 0


def cmd_ai_key_status(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_key_status(root=root, provider_id=args.provider, user_id=args.user_id or "default")
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(
            f"Key status: provider={out['provider_id']} user={out['user_id']} "
            f"keyring_ref={out['keyring_reference_present']} env={out['env_key_present']}"
        )
    return 0


def cmd_ai_quota_status(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_quota_summary(root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(
            f"Quota month={out['month']} used_tokens={out['used_tokens']}/{out['monthly_token_budget']} "
            f"used_cost=${out['used_cost_usd']:.2f}/${out['monthly_cost_budget_usd']:.2f}"
        )
    return 0


def cmd_ai_quota_set(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_set_quota_budgets(
            root=root,
            monthly_token_budget=max(1, int(args.monthly_token_budget)),
            monthly_cost_budget_usd=max(0.01, float(args.monthly_cost_budget)),
        )
        ai_log_event(root, "quota_set", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(
            f"Quota updated: tokens={out['monthly_token_budget']} cost=${out['monthly_cost_budget_usd']:.2f}"
        )
    return 0


def cmd_ai_user_pref_set(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_set_user_routing_pref(
            root=root,
            username=args.username,
            task_type=args.task_type,
            preferred_provider=args.provider,
        )
        ai_log_event(root, "user_pref_set", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Preference set: {out['username']} {out['task_type']} -> {out['preferred_provider']}")
    return 0


def cmd_ai_user_pref_show(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        if args.username and args.task_type:
            selected = ai_get_user_routing_pref(root=root, username=args.username, task_type=args.task_type)
            out = {"username": args.username, "task_type": args.task_type, "preferred_provider": selected}
        else:
            out = {"preferences": ai_list_user_routing_prefs(root=root, username=args.username or "")}
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        if "preferences" in out:
            rows = list(out.get("preferences", []))
            print(f"Preferences: {len(rows)}")
            for row in rows:
                print(f"- {row['username']} {row['task_type']} -> {row['preferred_provider']}")
        else:
            print(f"Preference: {out['username']} {out['task_type']} -> {out['preferred_provider'] or '[unset]'}")
    return 0


def cmd_ai_add_context(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        manifest = ai_list_sources(root=root)
        selected_ids = {sid.strip().lower() for sid in args.source_id}
        paths: list[str] = []
        for row in manifest:
            sid = str(row.get("source_id", "")).strip().lower()
            if sid in selected_ids:
                raw_path = str(row.get("raw_path", "")).strip()
                if raw_path:
                    paths.append(raw_path)
                normalized = root / ".ccbs" / "ai2" / "sources" / "normalized" / sid
                if normalized.exists():
                    paths.append(str(normalized))
        if not paths:
            available_ids = sorted(
                {
                    str(row.get("source_id", "")).strip().lower()
                    for row in manifest
                    if str(row.get("source_id", "")).strip()
                }
            )
            requested = ",".join(sorted(selected_ids))
            if available_ids:
                raise ValueError(
                    "no context paths resolved from requested source ids: "
                    f"{requested}. available source ids: {','.join(available_ids)}"
                )
            raise ValueError(
                "no context paths resolved from requested source ids and no sources are configured. "
                "run `ccbs ai source add` then `ccbs ai source sync` first"
            )

        config_path = _resolve_cli_path(root, args.continue_config)
        config_created = False
        if not config_path.exists():
            local_provider = str(os.environ.get("CCBS_LOCAL_PROVIDER", "ollama")).strip().lower()
            if local_provider not in {"ollama"}:
                local_provider = "ollama"
            cfg = _build_continue_config(
                root=root,
                provider=local_provider,
                local_model=str(os.environ.get("CCBS_LOCAL_MODEL", "llama3.1:8b")).strip() or "llama3.1:8b",
                local_fast_model=str(os.environ.get("CCBS_LOCAL_FAST_MODEL", "qwen2.5-coder:7b")).strip() or "qwen2.5-coder:7b",
                local_base_url=str(os.environ.get("CCBS_LOCAL_BASE_URL", "http://127.0.0.1:11434")).strip() or "http://127.0.0.1:11434",
                codex_model=str(os.environ.get("CCBS_CODEX_MODEL", "gpt-5")).strip() or "gpt-5",
                codex_base_url=str(os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).strip() or "https://api.openai.com/v1",
                output_yaml_style=_is_yaml_path(config_path),
            )
            config_path.parent.mkdir(parents=True, exist_ok=True)
            _write_continue_config(config_path, cfg)
            config_created = True
            ai_log_event(root, "continue_setup_autocreate", "local_admin", {"written": str(config_path)})
        cfg = _load_continue_config(config_path)
        cfg = merge_continue_docs_context(cfg, paths=paths, mode=args.mode)
        _write_continue_config(config_path, cfg)
        out = {
            "continue_config": str(config_path),
            "source_ids": sorted(selected_ids),
            "paths": sorted(set(paths)),
            "mode": args.mode,
            "config_created": config_created,
            "format": "yaml" if _is_yaml_path(config_path) else "json",
        }
        ai_log_event(root, "add_context", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Continue context updated: {out['continue_config']}")
        for p in out["paths"]:
            print(f"- {p}")
    return 0


def cmd_ai_prompt_pack_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        rows = ai_list_prompt_packs(root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    payload = {"prompt_packs": rows}
    if args.json:
        _print_json(payload)
    else:
        print(f"Prompt packs: {len(rows)}")
        for row in rows:
            print(f"- {row['pack_id']} ({row['prompt_count']} prompts) {row['description']}")
    return 0


def cmd_ai_prompt_pack_show(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        pack = ai_load_prompt_pack(root, pack_id=args.pack)
        if args.prompt:
            prompt = ai_find_prompt_pack_prompt(pack, prompt_id=args.prompt)
            payload = {"pack_id": pack.get("pack_id", args.pack), "prompt": prompt}
        else:
            payload = pack
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(payload)
    else:
        if "prompt" in payload:
            row = payload["prompt"]
            print(f"{payload['pack_id']}::{row.get('prompt_id')}")
            print(str(row.get("content", "")).strip())
        else:
            print(f"Pack: {payload.get('pack_id', args.pack)}")
            for row in payload.get("prompts", []):
                if not isinstance(row, dict):
                    continue
                print(f"- {row.get('prompt_id')}: {row.get('title', '')}")
    return 0


def cmd_ai_prompt_pack_export(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_export_prompt_pack(
            root=root,
            pack_id=args.pack,
            output=_resolve_cli_path(root, args.output),
            fmt=args.format,
            prompt_id=args.prompt,
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Prompt pack exported: {out['output']}")
    return 0


def cmd_ai_usecase_build(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        source = _resolve_cli_path(root, args.source)
        payload = build_usecase_library(
            source_dir=source,
            include_docx=bool(args.include_docx),
            include_pdf=bool(args.include_pdf),
        )
        out = write_usecase_library(
            payload,
            output_md=_resolve_cli_path(root, args.output_md),
            output_json=_resolve_cli_path(root, args.output_json),
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Use-case library built: {out['entry_count']} entries")
        print(f"- {out['output_md']}")
        print(f"- {out['output_json']}")
        for row in out.get("warnings", []):
            print(f"warning: {row}")
    return 0


def cmd_ai_perf_status(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        snapshot = collect_hardware_snapshot(root)
        phase_results = assess_phase_support(snapshot)
        recommendations = ai_recommend_models(root=root, path_for_disk=root)
        policy = ai_load_routing_policy(root)
        quota = ai_quota_summary(root)
        router_state = ai_load_router_state(root)
        codex_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        perf_summary = ai_summarize_perf_metrics(root)
        resource_runtime = ai_runtime_resource_state()
        endpoint_status = {
            "ollama": _endpoint_reachable("http://127.0.0.1:11434"),
            "lm_studio": _endpoint_reachable("http://127.0.0.1:1234"),
            "codex_base": codex_base,
            "codex_reachable": _endpoint_reachable(codex_base),
        }

        max_vram = 0.0
        for gpu in snapshot.gpus:
            max_vram = max(max_vram, float(gpu.vram_gb or 0.0))
        vram_tier = ai_vram_tier_recommendation(max_vram if max_vram > 0 else None)
        if max_vram >= 40.0 or snapshot.ram_gb >= 96.0:
            profile = "high-end"
        elif max_vram >= 20.0 or snapshot.ram_gb >= 48.0:
            profile = "workstation"
        else:
            profile = "laptop"

        profile_cfg = dict(policy.get("profiles", {}).get(profile, {}))
        hints = [
            "Keep GPU prioritized for inference; run builds on CPU.",
            "Baseline local tier is 7-8B quantized (Q4_K_M).",
            "Use Codex for complex prompts when online; local-first for simple/sensitive tasks.",
        ]
        payload = {
            "profile_suggested": profile,
            "profile_policy": profile_cfg,
            "active_profile": policy.get("active_profile"),
            "hardware": hardware_report_payload(snapshot, phase_results),
            "model_recommendations": recommendations,
            "endpoint_status": endpoint_status,
            "quota_state": quota,
            "router_state": router_state,
            "runtime_resource_state": resource_runtime,
            "perf_metrics_summary": perf_summary,
            "vram_tier_recommendation": vram_tier,
            "hints": hints,
        }
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
    else:
        print(f"Profile suggested: {payload['profile_suggested']} (active: {payload['active_profile']})")
        print(f"Ollama reachable: {payload['endpoint_status']['ollama']}")
        print(f"LM Studio reachable: {payload['endpoint_status']['lm_studio']}")
        print(f"Codex reachable: {payload['endpoint_status']['codex_reachable']}")
        print("Hints:")
        for hint in payload["hints"]:
            print(f"- {hint}")
    return 0


def cmd_ai_perf_benchmark(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        prompt = args.prompt
        if args.prompt_file:
            prompt = _resolve_cli_path(root, args.prompt_file).read_text(encoding="utf-8")
        if not prompt.strip():
            raise ValueError("prompt is required")
        provider = str(args.provider).strip().lower()
        base_url = args.base_url or ("http://127.0.0.1:11434" if provider == "local" else "https://api.openai.com/v1")
        if provider == "remote2":
            api_key = os.environ.get("OPENAI_API_KEY_REMOTE2", "")
        else:
            api_key = os.environ.get("OPENAI_API_KEY", "") if provider != "local" else ""
        out = ai_run_benchmark(
            root=root,
            provider=provider,
            model=args.model,
            prompt=prompt,
            runs=max(1, int(args.runs)),
            timeout_s=max(3, int(args.timeout_s)),
            base_url=base_url,
            api_key=api_key,
        )
        ai_log_event(root, "perf_benchmark", "local_admin", {"provider": provider, "model": args.model, "ok": out.get("ok", False)})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        if out.get("ok"):
            print(
                f"Benchmark {out['provider']}/{out['model']} runs={out['successful_runs']}: "
                f"ttft={out['ttft_s_avg']}s tps={out['tokens_per_s_avg']} latency={out['latency_s_avg']}s"
            )
        else:
            print(f"Benchmark failed: {out.get('errors', [])}")
    return 0 if out.get("ok") else 1


def cmd_ai_hybrid_answer(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        question = " ".join(args.question).strip()
        if not question:
            print("ERROR: empty question")
            return 2

        policy = ai_load_routing_policy(root)
        metadata = _parse_json_object(getattr(args, "metadata_json", "{}"))
        attachments = _flatten_path_list(getattr(args, "attachment_path", []))
        if attachments:
            metadata["attachment_paths"] = attachments
        user_id = (getattr(args, "user_id", "") or str(metadata.get("user_id", "local_user"))).strip() or "local_user"
        metadata["user_id"] = user_id

        quota_state = ai_quota_summary(root)
        resource_state = ai_runtime_resource_state()
        provider_states = dict(ai_load_router_state(root).get("providers", {}))
        codex_state = dict(provider_states.get("codex", {}))
        if str(codex_state.get("state", "closed")).strip().lower() == "open":
            resource_state["primary_breaker_open"] = True

        task_type = str(getattr(args, "task_type", "auto") or "auto").strip().lower()
        if task_type not in AI_ROUTING_TASK_TYPES:
            task_type = "auto"

        decision = ai_classify_task(
            question,
            requested_task_type=task_type,
            policy=policy,
            metadata=metadata,
            root=root,
            quota_state=quota_state,
            resource_state=resource_state,
        )

        ask_flag = getattr(args, "ask_on_uncertain", None)
        if ask_flag is None:
            ask_on_uncertain = bool(policy.get("ask_on_uncertain", True))
        else:
            ask_on_uncertain = bool(ask_flag)

        route_selected = str(decision.get("recommended_route", "local"))
        options = [str(item) for item in decision.get("options", ["local", "codex", "remote2", "both"])]
        if route_selected not in options:
            route_selected = options[0]

        user_override_applied = False
        if bool(policy.get("user_override_enabled", True)) and getattr(args, "user_id", ""):
            pref = ai_get_user_routing_pref(
                root=root,
                username=getattr(args, "user_id", ""),
                task_type=str(decision.get("task_type", "auto")),
            )
            pref = pref.strip().lower()
            if pref and pref in {"local", "codex", "remote2", "both"}:
                route_selected = pref
                user_override_applied = True

        route_prompted = False
        if bool(decision.get("uncertain")) and ask_on_uncertain:
            route_prompted = True
            if not args.json and sys.stdin.isatty():
                raw = input(
                    f"Routing uncertain ({decision['task_type']} conf={float(decision['confidence']):.2f}). "
                    f"Choose route [{'/'.join(options)}] (recommended: {route_selected}): "
                ).strip().lower()
                if raw in options:
                    route_selected = raw

        use_codex = not bool(args.no_codex)
        force_local = bool(args.force_local)
        local_reason = ""
        route_chain: list[str] = []
        if force_local:
            route_selected = "local"
            use_codex = False
            local_reason = "forced_local"
        elif str(decision.get("task_type")) == "sensitive":
            route_selected = "local"
            use_codex = False
            force_local = True
            local_reason = "sensitive_local_only"
        elif route_selected == "local":
            use_codex = False
            force_local = True
            local_reason = "policy_local_first"
        elif route_selected == "codex":
            use_codex = not bool(args.no_codex)
            force_local = False
            route_chain = ["codex", "remote2"]
        elif route_selected == "remote2":
            use_codex = not bool(args.no_codex)
            force_local = False
            route_chain = ["remote2", "codex"]
        else:
            # both: try codex then remote2 then local fallback.
            use_codex = not bool(args.no_codex)
            force_local = False
            local_reason = "hybrid_local_fallback"
            route_chain = ["codex", "remote2"]

        if bool(args.no_codex):
            use_codex = False
            if route_selected in {"codex", "remote2", "both"}:
                route_selected = "local"
                force_local = True
                if not local_reason:
                    local_reason = "codex_disabled"
            route_chain = []

        dynamic_threshold = float(decision.get("dynamic_threshold", ai_compute_dynamic_threshold(policy, quota_state=quota_state, resource_state=resource_state)))

        result = run_hybrid_answer(
            root=root,
            question=question,
            top_k=max(1, int(args.top_k)),
            use_codex=use_codex,
            force_local=force_local,
            codex_model=args.codex_model,
            codex_base_url=args.codex_base_url,
            timeout_s=max(1, int(args.timeout_s)),
            local_provider=args.local_provider,
            local_model_id=args.local_model_id or "",
            local_reason=local_reason,
            route_chain=route_chain,
            policy=policy,
            user_id=user_id,
            metadata=metadata,
            dynamic_threshold=dynamic_threshold,
            task_features=dict(decision.get("task_features", {})),
            sensitive_similarity=float(decision.get("sensitive_similarity", 0.0)),
            quota_state=quota_state,
            resource_state=resource_state,
            user_override_applied=user_override_applied,
        )

        provider_origin = "remote" if result.provider_used in {"codex", "remote2"} else "local"

        payload = {
            "question": result.question,
            "answer": result.answer,
            "provider_used": result.provider_used,
            "model_used": result.model_used,
            "codex_attempted": result.codex_attempted,
            "online": result.online,
            "fallback_reason": result.fallback_reason,
            "citations": result.citations,
            "provider_origin": provider_origin,
            "task_type": decision.get("task_type"),
            "task_type_requested": task_type,
            "routing_confidence": decision.get("confidence"),
            "routing_uncertain": decision.get("uncertain"),
            "route_recommended": decision.get("recommended_route"),
            "route_selected": route_selected,
            "route_prompted": route_prompted,
            "routing_reasons": decision.get("reasons", []),
            "task_features": result.task_features or decision.get("task_features", {}),
            "sensitive_similarity": result.sensitive_similarity,
            "dynamic_threshold": result.dynamic_threshold,
            "route_chain": result.route_chain,
            "provider_attempts": result.provider_attempts,
            "quota_state": result.quota_state,
            "resource_state": result.resource_state,
            "user_override_applied": bool(result.user_override_applied),
        }

        if args.memory:
            store_memory(
                root=root,
                kind="hybrid",
                question=result.question,
                answer=result.answer,
                metadata={
                    "provider_used": result.provider_used,
                    "model_used": result.model_used,
                    "codex_attempted": result.codex_attempted,
                    "online": result.online,
                    "fallback_reason": result.fallback_reason,
                    "citations": result.citations,
                    "provider_origin": provider_origin,
                    "task_type": decision.get("task_type"),
                    "routing_confidence": decision.get("confidence"),
                    "routing_uncertain": decision.get("uncertain"),
                    "route_selected": route_selected,
                    "route_chain": result.route_chain,
                    "provider_attempts": result.provider_attempts,
                },
            )

        ai_log_event(
            root=root,
            event_type="hybrid_answer",
            actor="local_user",
            details={
                "provider_used": result.provider_used,
                "model_used": result.model_used,
                "codex_attempted": result.codex_attempted,
                "online": result.online,
                "fallback_reason": result.fallback_reason,
                "provider_origin": provider_origin,
                "task_type": decision.get("task_type"),
                "routing_confidence": decision.get("confidence"),
                "routing_uncertain": decision.get("uncertain"),
                "route_selected": route_selected,
                "route_prompted": route_prompted,
                "route_chain": result.route_chain,
                "provider_attempts": result.provider_attempts[:4],
                "dynamic_threshold": result.dynamic_threshold,
                "user_override_applied": bool(result.user_override_applied),
            },
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json(payload)
        return 0

    print(f"Provider: {result.provider_used} | Model: {result.model_used}")
    print(
        f"Task: {payload['task_type']} | Route: {payload['route_selected']} "
        f"(recommended: {payload['route_recommended']}, conf={float(payload['routing_confidence']):.2f})"
    )
    print(f"Codex attempted: {result.codex_attempted} | Online: {result.online}")
    if result.fallback_reason:
        print(f"Fallback: {result.fallback_reason}")
    print("")
    print(result.answer)
    if result.citations:
        print("")
        print("Citations:")
        for row in result.citations:
            path = row.get("path", "unknown")
            chunk = row.get("chunk_id", "?")
            score = float(row.get("score", 0.0))
            print(f"- {path}#chunk{chunk} (score={score:.4f})")
    return 0


def cmd_ai_storage_status(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        report = ai_usage_report(root)
        verify = ai_verify_storage(root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    payload = {
        "max_bytes": report.max_bytes,
        "hard_limit_bytes": MAX_STORAGE_BYTES,
        "total_bytes": report.total_bytes,
        "remaining_bytes": report.remaining_bytes,
        "sections": report.sections,
        "ok": verify["ok"],
    }
    if args.json:
        _print_json(payload)
    else:
        print(f"Storage: total={report.total_bytes} remaining={report.remaining_bytes} max={report.max_bytes}")
        for key, value in report.sections.items():
            print(f"- {key}: {value}")
    return 0 if verify["ok"] else 1


def cmd_ai_storage_gc(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_gc_storage(root=root, target_bytes=max(0, int(args.target_bytes)), dry_run=args.dry_run)
        ai_log_event(root, "storage_gc", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(
            f"GC: deleted_files={out['deleted_files']} before={out['before_bytes']} "
            f"after={out['after_bytes']} target={out['target_bytes']} dry_run={out['dry_run']}"
        )
    return 0


def cmd_ai_storage_verify(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_verify_storage(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Storage verify: {'OK' if out['ok'] else 'FAIL'} total={out['total_bytes']} max={out['max_bytes']}")
    return 0 if out["ok"] else 1


def cmd_ai_user_create(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_create_user(root=root, username=args.username, password=args.password, role=args.role)
        ai_log_event(root, "user_create", "local_admin", {"username": out["username"], "role": out["role"]})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"User created: {out['username']} role={out['role']}")
    return 0


def cmd_ai_user_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        rows = ai_list_users(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    payload = {"users": rows}
    if args.json:
        _print_json(payload)
        return 0
    print(f"Users: {len(rows)}")
    for row in rows:
        print(f"- {row['username']} role={row['role']} disabled={row['disabled']}")
    return 0


def cmd_ai_user_role(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_set_user_role(root=root, username=args.username, role=args.role)
        ai_log_event(root, "user_role", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"User role updated: {out['username']} -> {out['role']}")
    return 0


def cmd_ai_user_disable(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_set_user_disabled(root=root, username=args.username, disabled=not args.enable)
        ai_log_event(root, "user_disable", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"User status: {out['username']} disabled={out['disabled']}")
    return 0


def cmd_ai_user_passwd(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_set_user_password(root=root, username=args.username, password=args.password)
        ai_log_event(root, "user_password", "local_admin", {"username": args.username})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Password updated for user: {out['username']}")
    return 0


def cmd_ai_user_owner_auth_set(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_set_owner_auto_auth(root=root, username=args.username, enabled=True)
        ai_log_event(
            root,
            "owner_auto_auth_set",
            "local_admin",
            {"username": out["username"], "enabled": out["enabled"]},
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Owner auto-auth enabled for user={out['username']} role={out['role']}")
    return 0


def cmd_ai_user_owner_auth_status(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_get_owner_auto_auth(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(
            f"Owner auto-auth configured={out.get('configured')} enabled={out.get('enabled')} "
            f"user={out.get('username', '')} role={out.get('role', '')}"
        )
    return 0


def cmd_ai_user_owner_auth_disable(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_disable_owner_auto_auth(root=root)
        ai_log_event(
            root,
            "owner_auto_auth_disable",
            "local_admin",
            {"username": out.get("username", ""), "enabled": out.get("enabled", False)},
        )
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Owner auto-auth disabled (configured={out.get('configured')}, user={out.get('username', '')})")
    return 0


def cmd_ai_api_token(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_issue_token(root=root, username=args.username, password=args.password, ttl_hours=args.ttl_hours)
        ai_log_event(root, "api_token_issue", out["username"], {"role": out["role"], "expires_at": out["expires_at"]})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Token issued for {out['username']} role={out['role']} expires_at={out['expires_at']}")
        print(f"Bearer token: {out['token']}")
    return 0


def cmd_ai_api_status(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = api_status(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"API dependencies_ok={out.get('dependencies_ok')}")
        if "detail" in out:
            print(f"- detail: {out['detail']}")
    return 0 if out.get("dependencies_ok") else 1


def cmd_ai_api_serve(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        owner_auto = ai_get_owner_auto_auth(root=root)
        non_loopback_bind = not _is_loopback_bind_host(args.host)
        owner_auto_enabled = bool(owner_auto.get("enabled"))
        allow_remote_owner_auto_auth = bool(getattr(args, "allow_remote_owner_auto_auth", False))

        if non_loopback_bind and owner_auto_enabled and not allow_remote_owner_auto_auth:
            print(
                "ERROR: refusing non-loopback ai api serve while owner auto-auth is enabled. "
                "Disable owner auto-auth first or re-run with --allow-remote-owner-auto-auth to acknowledge the risk."
            )
            return 2

        if non_loopback_bind:
            print(
                f"WARN: serving the AI API on non-loopback host {args.host}. "
                "Remote clients will not receive loopback owner auto-auth."
            )
            if owner_auto_enabled:
                print(
                    "WARN: owner auto-auth remains enabled for loopback clients on this machine. "
                    "Confirm your remote exposure and token posture before continuing."
                )

        ai_log_event(root, "api_serve", "local_admin", {"host": args.host, "port": args.port})
        serve_api(root=root, host=args.host, port=max(1, int(args.port)))
    except ApiDependencyError as exc:
        print(f"ERROR: {exc}")
        return 2
    except (RepoError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    return 0


def cmd_ai_codex_status(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_codex_bridge_status(root=root, host=args.host, port=args.port)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        bridge = dict(out.get("bridge", {}))
        auth = dict(out.get("auth", {}))
        print(f"Codex bridge: {bridge.get('base_url', '')}")
        print(f"- chat completions: {bridge.get('chat_completions_url', '')}")
        print(f"- health: {bridge.get('health_url', '')}")
        print(f"- runtime: {bridge.get('runtime_url', '')}")
        print(f"- mcp profile: {bridge.get('mcp_profile_url', '')}")
        print(f"- full CCBS API mount: {bridge.get('full_api_mount_url', '')}")
        print(f"- auth: {auth.get('mode', '')} via {auth.get('api_key_env', '')}")
    return 0


def cmd_ai_codex_mcp_profile(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_codex_mcp_profile(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Codex MCP profile: {out.get('profile_id', '')}")
        for server in out.get("servers", []):
            if not isinstance(server, dict):
                continue
            print(f"- {server.get('server_id')} ({server.get('name')}): {server.get('endpoint')}")
            for tool in server.get("tools", []):
                if isinstance(tool, dict):
                    print(
                        f"  - {tool.get('tool_name')} mode={tool.get('mode')} risk={tool.get('risk_level')}"
                    )
    return 0


def cmd_ai_codex_bootstrap(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        status = ai_codex_bridge_status(root=root, host=args.host, port=args.port)
        profile = ai_codex_mcp_profile(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2

    bridge = dict(status.get("bridge", {}))
    auth = dict(status.get("auth", {}))
    continue_binding = dict(status.get("client_bindings", {}).get("continue", {}))
    vscode_tasks = dict(status.get("vscode_tasks", {}))
    task_hub_ids = dict(vscode_tasks.get("task_hub_ids", {}))
    auth_env = str(auth.get("api_key_env", "")).strip()

    print("Codex bridge bootstrap")
    print(f"- continue model: {continue_binding.get('model_title', '')}")
    print(f"- bridge: {bridge.get('base_url', '')}")
    print(f"- mcp profile: {profile.get('profile_id', '')}")
    print(f"- bootstrap task: {vscode_tasks.get('bridge_bootstrap_task_label', '')}")
    print(f"- task hub id: {task_hub_ids.get('bridge_bootstrap', '')}")
    if auth_env:
        print(f"- bearer env: {auth_env}")
        if not os.environ.get(auth_env):
            print(f"WARN: {auth_env} is not set in this shell. Bridge clients will need it.")
    print("Starting the loopback Codex bridge. Press Ctrl+C to stop.")
    return cmd_ai_codex_serve(args)


def cmd_ai_codex_serve(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        owner_auto = ai_get_owner_auto_auth(root=root)
        non_loopback_bind = not _is_loopback_bind_host(args.host)
        owner_auto_enabled = bool(owner_auto.get("enabled"))
        allow_remote_owner_auto_auth = bool(getattr(args, "allow_remote_owner_auto_auth", False))

        if non_loopback_bind and owner_auto_enabled and not allow_remote_owner_auto_auth:
            print(
                "ERROR: refusing non-loopback ai codex serve while owner auto-auth is enabled. "
                "Disable owner auto-auth first or re-run with --allow-remote-owner-auto-auth to acknowledge the risk."
            )
            return 2

        if non_loopback_bind:
            print(
                f"WARN: serving the Codex bridge on non-loopback host {args.host}. "
                "Remote clients will not receive loopback owner auto-auth."
            )
            if owner_auto_enabled:
                print(
                    "WARN: owner auto-auth remains enabled for loopback clients on this machine. "
                    "Confirm your remote exposure and token posture before continuing."
                )

        ai_log_event(root, "codex_bridge_serve", "local_admin", {"host": args.host, "port": args.port})
        serve_codex_bridge(root=root, host=args.host, port=max(1, int(args.port)))
    except ApiDependencyError as exc:
        print(f"ERROR: {exc}")
        return 2
    except (RepoError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    return 0


def cmd_ai_plugin_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        rows = ai_list_plugins(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    payload = {"plugins": rows}
    if args.json:
        _print_json(payload)
        return 0
    print(f"Plugins: {len(rows)}")
    for row in rows:
        print(f"- {row.get('plugin_id')} v{row.get('version')} enabled={row.get('enabled')} publisher={row.get('publisher')}")
    return 0


def cmd_ai_plugin_install(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        plugin_path = _resolve_cli_path(root, args.path)
        out = ai_install_plugin(root=root, zip_path=plugin_path)
        ai_log_event(root, "plugin_install", "local_admin", {"plugin_id": out["plugin_id"], "version": out["version"]})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Plugin installed: {out['plugin_id']} v{out['version']}")
    return 0


def cmd_ai_plugin_enable(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_enable_plugin(root=root, plugin_id=args.plugin_id)
        ai_log_event(root, "plugin_enable", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Plugin enabled: {out['plugin_id']}")
    return 0


def cmd_ai_plugin_disable(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_disable_plugin(root=root, plugin_id=args.plugin_id)
        ai_log_event(root, "plugin_disable", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Plugin disabled: {out['plugin_id']}")
    return 0


def cmd_ai_plugin_verify(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_verify_plugin(root=root, plugin_id=args.plugin_id)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Plugin verify: {out['plugin_id']} {'OK' if out['ok'] else 'FAIL'}")
    return 0 if out.get("ok") else 1


def cmd_ai_workspace_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_list_workspaces(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
        return 0
    print(f"Current workspace: {out['current']}")
    for row in out["workspaces"]:
        print(f"- {row.get('workspace_id')}: {row.get('name')}")
    return 0


def cmd_ai_workspace_create(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_create_workspace(root=root, workspace_id=args.workspace_id, name=args.name or "", description=args.description or "")
        ai_log_event(root, "workspace_create", "local_admin", {"workspace_id": out["workspace_id"]})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Workspace created: {out['workspace_id']}")
    return 0


def cmd_ai_workspace_switch(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_switch_workspace(root=root, workspace_id=args.workspace_id)
        ai_log_event(root, "workspace_switch", "local_admin", {"workspace_id": out["current"]})
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Workspace switched: {out['current']}")
    return 0


def cmd_ai_pack_build(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out_path = _resolve_cli_path(root, args.output)
        out = ai_build_pack(root=root, output=out_path, include_data=bool(args.include_data))
        ai_log_event(root, "pack_build", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Pack built: {out['output']} entries={out['entries']}")
    return 0


def cmd_ai_pack_install(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        pack_path = _resolve_cli_path(root, args.path)
        out = ai_install_pack(root=root, pack_path=pack_path)
        ai_log_event(root, "pack_install", "local_admin", out)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Pack installed: {out['pack_name']}")
    return 0


def cmd_ai_pack_list(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        rows = ai_list_packs(root=root)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    payload = {"packs": rows}
    if args.json:
        _print_json(payload)
        return 0
    print(f"Packs: {len(rows)}")
    for row in rows:
        print(f"- {row.get('pack_name')} entries={row.get('entry_count')} path={row.get('path')}")
    return 0


def cmd_ai_pack_verify(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        out = ai_verify_pack(root=root, pack_name=args.pack_name)
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    if args.json:
        _print_json(out)
    else:
        print(f"Pack verify: {out['pack_name']} {'OK' if out['ok'] else 'FAIL'}")
    return 0 if out.get("ok") else 1


def cmd_ai_audit(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        rows = ai_list_events(root=root, limit=max(1, int(args.limit)), event_type=args.event_type or "")
    except (RepoError, OSError, ValueError, RuntimeError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 2
    payload = {"events": rows}
    if args.json:
        _print_json(payload)
        return 0
    print(f"Audit events: {len(rows)}")
    for row in rows:
        print(f"- {row['ts']} {row['event_type']} actor={row['actor']}")
    return 0


def cmd_ai_permissions(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    target = _resolve_cli_path(root, args.path)
    if not target.exists():
        print(f"ERROR: path not found: {target}")
        return 2

    required_level, reason = recommend_permission(args.task)
    chosen_level = args.level or required_level

    if args.interactive:
        print("Select permission level:")
        ordered = ["read_only", "workspace_write", "full_access"]
        for idx, level in enumerate(ordered, 1):
            info = PERMISSION_LEVELS[level]
            marker = " (recommended)" if level == required_level else ""
            print(f"{idx}. {info['label']} [{level}]{marker}")
            print(f"   - capabilities: {info['capabilities']}")
            print(f"   - risk: {info['risk']}")
        raw = input(f"Choice [1-{len(ordered)}] (default {required_level}): ").strip()
        if raw in {"1", "2", "3"}:
            chosen_level = ordered[int(raw) - 1]

    sufficient = permission_sufficient(chosen_level=chosen_level, required_level=required_level)
    report = scan_path(target=target, max_files=max(1, args.max_files)) if args.scan else None
    manifest_path: Path | None = None
    if args.write_manifest and report is not None:
        manifest_path = write_scan_manifest(
            root=root,
            report=report,
            task=args.task,
            chosen_level=chosen_level,
            required_level=required_level,
            include_hashes=args.hashes,
            hash_limit=max(1, args.hash_limit),
        )

    payload: dict[str, Any] = {
        "task": args.task,
        "target": str(target),
        "required_level": required_level,
        "reason": reason,
        "chosen_level": chosen_level,
        "sufficient": sufficient,
        "permission_options": PERMISSION_LEVELS,
    }
    if report is not None:
        payload["scan"] = report.to_dict()
    if manifest_path is not None:
        payload["manifest_path"] = str(manifest_path)

    if args.json:
        _print_json(payload)
    else:
        print(f"Permission advisor for task: {args.task}")
        print(f"Target: {target}")
        print(f"Required permission: {required_level}")
        print(f"Why: {reason}")
        print(f"Chosen permission: {chosen_level} ({'sufficient' if sufficient else 'insufficient'})")
        print("")
        print("Permission options:")
        for level in ("read_only", "workspace_write", "full_access"):
            info = PERMISSION_LEVELS[level]
            print(f"- {info['label']} [{level}]")
            print(f"  capabilities: {info['capabilities']}")
            print(f"  risk: {info['risk']}")
        if report is not None:
            print("")
            print("Safety scan summary:")
            print(f"- scanned files: {report.scanned_files}")
            print(f"- skipped files: {report.skipped_files}")
            print(f"- symlinks: {report.symlink_count}")
            print(f"- executable-like files: {report.executable_like_count}")
            print(f"- binary files: {report.binary_file_count}")
            print(f"- sensitive keyword hits: {report.sensitive_hit_count}")
            if report.findings:
                print("Sample findings:")
                for item in report.findings[:20]:
                    print(f"- {item.category}: {item.path} ({item.detail})")
        print("")
        print("Safety/isolation checklist:")
        print("- Start with read-only mode and dry-run commands.")
        print("- Run in a test copy or disposable VM/container first.")
        print("- Keep network restricted unless task requires it.")
        print("- Escalate permissions only after scan + file review.")
        print("- Review diffs/logs before enabling write or full access.")
        print("")
        print("Transparency checklist:")
        print("- Review scan findings and confirm expected file scope.")
        if manifest_path is not None:
            print(f"- Manifest written: {manifest_path}")
        else:
            print("- Enable --write-manifest to persist scan evidence.")

    return 0 if sufficient else 1


def cmd_ai_route(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    request_text = " ".join(args.request).strip()
    plan = route_request(request_text)
    target = _resolve_cli_path(root, args.path)
    settings = _resolve_validation_settings(
        mode=args.mode,
        max_todo=args.max_todo,
        max_unmapped_links=args.max_unmapped_links,
        profile=getattr(args, "validation_profile", None),
        default_mode="deploy",
    )

    plan_payload = {
        "request": request_text,
        "action": plan.action,
        "confidence": plan.confidence,
        "reason": plan.reason,
        "suggested_command": plan.suggested_command,
        "path": str(target),
        "validation_profile": settings["profile"],
        "mode": settings["mode"],
        "max_todo": settings["max_todo"],
        "max_unmapped_links": settings["max_unmapped_links"],
        "execute": args.execute,
    }

    if not args.execute:
        if args.json:
            _print_json({"plan": plan_payload})
        else:
            print("AI route plan:")
            print(f"  - action: {plan.action}")
            print(f"  - confidence: {plan.confidence:.2f}")
            print(f"  - reason: {plan.reason}")
            print(f"  - suggested command: {plan.suggested_command}")
            print("Preview only. Re-run with --execute to run this action.")
        return 0

    if plan.action == "pt_apply_link_ports":
        write_requested = bool(args.write)
        if write_requested and args.validation_first:
            gate_ok, gate_issues = _run_validation_gate(
                root=root,
                target=target,
                max_todo=settings["max_todo"],
                max_unmapped_links=settings["max_unmapped_links"],
                mode=settings["mode"],
                as_json=args.json,
            )
            if not gate_ok and not args.force:
                if not args.json:
                    print("Route blocked by validation gate. Use --force to override.")
                return 1
            if not gate_ok and args.force and not args.json:
                print(f"WARNING: forcing route despite validation issues: {', '.join(gate_issues)}")

        report = apply_link_ports(target=target, write=write_requested)
        if args.json:
            _print_json(
                {
                    "plan": plan_payload,
                    "write": write_requested,
                    "changed_files": report.changed_files,
                    "skipped_files": report.skipped_files,
                    "unresolved_rows": report.unresolved_rows,
                    "issues": report.issues,
                }
            )
        else:
            print(format_portmap_report(report))
        return 1 if report.issues else 0

    if plan.action == "pt_preflight":
        report = run_preflight(
            target=target,
            max_todo=settings["max_todo"],
            max_unmapped_links=settings["max_unmapped_links"],
        )
        print(format_report(report=report, mode=settings["mode"], as_json=args.json))
        selected = next(item for item in report.outcomes if item.mode == settings["mode"])
        return 0 if selected.ok else 1

    if plan.action == "validate_all":
        return cmd_validate_all(args)
    if plan.action == "doctor":
        return cmd_doctor(args)
    if plan.action == "repo_root":
        return cmd_repo_root(args)
    if plan.action in {"none"}:
        if args.json:
            _print_json({"plan": plan_payload, "result": "no_action"})
        else:
            print("No action selected for empty request.")
        return 0

    # Fallback route: local repo Q&A.
    return _run_answer(
        root=root,
        question=request_text,
        provider=args.provider,
        model=args.model,
        top_k=args.top_k,
        persist_memory=args.memory,
        as_json=args.json,
        memory_kind="route",
        auto_index=args.auto_index,
        index_path=args.index_path,
        index_max_files=args.index_max_files,
    )


def _add_ai_answer_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("question", nargs="+", help="Question for local offline assistant")
    parser.add_argument(
        "--provider",
        choices=sorted(LOCAL_PROVIDERS),
        default="extractive",
        help="Local answer provider",
    )
    parser.add_argument(
        "--model",
        default="llama3.2:3b",
        help="Model name when using --provider ollama",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="How many indexed chunks to retrieve",
    )
    parser.add_argument(
        "--auto-index",
        dest="auto_index",
        action="store_true",
        help="Auto-index local files if no index exists yet",
    )
    parser.add_argument(
        "--no-auto-index",
        dest="auto_index",
        action="store_false",
        help="Require existing index database",
    )
    parser.add_argument(
        "--index-path",
        default=".",
        help="Path to index when auto-indexing is needed",
    )
    parser.add_argument(
        "--index-max-files",
        type=int,
        default=5000,
        help="Maximum files to index when auto-indexing",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument(
        "--no-memory",
        dest="memory",
        action="store_false",
        help="Do not persist Q/A exchange in local memory store",
    )
    parser.set_defaults(memory=True, auto_index=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccbs-clean", description="CCBS CLI app")
    sub = parser.add_subparsers(dest="command", required=True)

    add_hyperv_parser(sub)
    add_ai3_parser(sub)
    add_buildathon_parser(sub)
    add_quantum_parser(sub)
    assist = sub.add_parser("assist", help="Accessible gaming assistant (phase-1 dry-run foundation)")
    assist_subcommands = assist.add_subparsers(dest="assist_cmd", required=True)

    assist_profile = assist_subcommands.add_parser("profile", help="Manage assist profiles")
    assist_profile_sub = assist_profile.add_subparsers(dest="assist_profile_cmd", required=True)

    assist_profile_create = assist_profile_sub.add_parser("create", help="Create a new assist profile")
    assist_profile_create.add_argument("profile_id", help="Profile identifier")
    assist_profile_create.add_argument("--game-name", required=True, help="Display name for the game/profile")
    assist_profile_create.add_argument(
        "--offline-only",
        dest="offline_only",
        action="store_true",
        help="Mark profile as offline-only (default)",
    )
    assist_profile_create.add_argument(
        "--no-offline-only",
        dest="offline_only",
        action="store_false",
        help="Disable offline-only flag (will be blocked by strict policy)",
    )
    assist_profile_create.add_argument(
        "--allow-multiplayer",
        action="store_true",
        help="Allow multiplayer profile flag (will be blocked by strict policy)",
    )
    assist_profile_create.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_profile_create.set_defaults(offline_only=True, func=cmd_assist_profile_create)

    assist_profile_ack = assist_profile_sub.add_parser(
        "ack",
        help="Acknowledge offline/single-player policy for a profile",
    )
    assist_profile_ack.add_argument("profile_id", help="Profile identifier")
    assist_profile_ack.add_argument(
        "--offline-single-player",
        action="store_true",
        help="Required acknowledgement flag",
    )
    assist_profile_ack.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_profile_ack.set_defaults(func=cmd_assist_profile_ack)

    assist_profile_list = assist_profile_sub.add_parser("list", help="List assist profiles")
    assist_profile_list.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_profile_list.set_defaults(func=cmd_assist_profile_list)

    assist_profile_show = assist_profile_sub.add_parser("show", help="Show one assist profile")
    assist_profile_show.add_argument("profile_id", help="Profile identifier")
    assist_profile_show.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_profile_show.set_defaults(func=cmd_assist_profile_show)

    assist_profile_export = assist_profile_sub.add_parser("export", help="Export profile and commands to JSON")
    assist_profile_export.add_argument("profile_id", help="Profile identifier")
    assist_profile_export.add_argument("out_path", help="Destination JSON path")
    assist_profile_export.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_profile_export.set_defaults(func=cmd_assist_profile_export)

    assist_profile_import = assist_profile_sub.add_parser("import", help="Import profile JSON")
    assist_profile_import.add_argument("in_path", help="Source JSON path")
    assist_profile_import.add_argument(
        "--profile-id",
        default="",
        help="Optional profile id override",
    )
    assist_profile_import.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_profile_import.set_defaults(func=cmd_assist_profile_import)

    assist_command = assist_subcommands.add_parser("command", help="Manage assist voice command mappings")
    assist_command_sub = assist_command.add_subparsers(dest="assist_command_cmd", required=True)

    assist_command_add = assist_command_sub.add_parser("add", help="Add one voice command mapping")
    assist_command_add.add_argument("profile_id", help="Profile identifier")
    assist_command_add.add_argument("--name", required=True, help="Command name")
    assist_command_add.add_argument("--phrase", required=True, help="Trigger phrase")
    assist_command_add.add_argument(
        "--action",
        action="append",
        default=[],
        help="Action token in type:payload format (repeatable)",
    )
    assist_command_add.add_argument("--cooldown-ms", type=int, default=0, help="Per-command cooldown")
    assist_command_add.add_argument(
        "--confirm-level",
        choices=("none", "require"),
        default="none",
        help="Whether explicit --confirm is required on run",
    )
    assist_command_add.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_command_add.set_defaults(func=cmd_assist_command_add)

    assist_command_list = assist_command_sub.add_parser("list", help="List commands for a profile")
    assist_command_list.add_argument("profile_id", help="Profile identifier")
    assist_command_list.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_command_list.set_defaults(func=cmd_assist_command_list)

    assist_run = assist_subcommands.add_parser("run", help="Run transcript through deterministic dry-run engine")
    assist_run.add_argument("--profile", required=True, help="Profile identifier")
    assist_run.add_argument("--transcript", required=True, help="Transcript text to process")
    assist_run.add_argument("--confirm", action="store_true", help="Allow commands with confirm-level=require")
    assist_run.add_argument(
        "--live-input",
        action="store_true",
        help="Rejected in phase-1 (future placeholder for non-dry-run execution)",
    )
    assist_run.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_run.set_defaults(func=cmd_assist_run)

    assist_receipts = assist_subcommands.add_parser("receipts", help="Show recent assist receipts")
    assist_receipts.add_argument("--profile", default="", help="Optional profile filter")
    assist_receipts.add_argument("--limit", type=int, default=20, help="Maximum rows")
    assist_receipts.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_receipts.set_defaults(func=cmd_assist_receipts)

    assist_pack = assist_subcommands.add_parser("pack", help="Build offline assist zip pack")
    assist_pack.add_argument(
        "--output",
        default="dist/ccbs-assist-pack.zip",
        help="Output zip path (absolute or relative to repo root)",
    )
    assist_pack.add_argument(
        "--include-local-profiles",
        action="store_true",
        help="Include exported local profiles in the zip",
    )
    assist_pack.add_argument("--json", action="store_true", help="Emit JSON output")
    assist_pack.set_defaults(func=cmd_assist_pack)

    book = sub.add_parser("book", help="Local study book metadata + notes imports")
    book_sub = book.add_subparsers(dest="book_cmd", required=True)

    book_seed = book_sub.add_parser("seed", help="Seed local book catalog from JSON config")
    book_seed.add_argument(
        "--path",
        default="config/bookshelf_seed_books.json",
        help="Seed JSON path (absolute or relative to repo root)",
    )
    book_seed.add_argument(
        "--replace",
        action="store_true",
        help="Update existing books that share the same book_id",
    )
    book_seed.add_argument("--json", action="store_true", help="Emit JSON output")
    book_seed.set_defaults(func=cmd_book_seed)

    book_list = book_sub.add_parser("list", help="List books in local catalog")
    book_list.add_argument("--query", default="", help="Optional text filter")
    book_list.add_argument("--tag", default="", help="Optional tag filter")
    book_list.add_argument("--json", action="store_true", help="Emit JSON output")
    book_list.set_defaults(func=cmd_book_list)

    book_show = book_sub.add_parser("show", help="Show one book from local catalog")
    book_show.add_argument("book_id", help="Book identifier")
    book_show.add_argument("--json", action="store_true", help="Emit JSON output")
    book_show.set_defaults(func=cmd_book_show)

    book_import_notes = book_sub.add_parser(
        "import-notes",
        help="Import your exported notes/highlights file for one book",
    )
    book_import_notes.add_argument("book_id", help="Book identifier")
    book_import_notes.add_argument("path", help="Notes/highlights file path")
    book_import_notes.add_argument(
        "--format",
        default="auto",
        choices=("auto", "text", "json", "csv"),
        help="Input format hint",
    )
    book_import_notes.add_argument("--json", action="store_true", help="Emit JSON output")
    book_import_notes.set_defaults(func=cmd_book_import_notes)

    book_template = book_sub.add_parser(
        "export-template",
        help="Export a notes import template (JSON or CSV)",
    )
    book_template.add_argument(
        "--format",
        default="json",
        choices=("json", "csv"),
        help="Template format",
    )
    book_template.add_argument(
        "--output",
        default="docs/templates/book_notes_import_template.json",
        help="Template output path (absolute or relative to repo root)",
    )
    book_template.add_argument("--json", action="store_true", help="Emit JSON output")
    book_template.set_defaults(func=cmd_book_export_template)

    validate_parser = sub.add_parser("validate", help="Validate brick metadata")
    validate_subcommands = validate_parser.add_subparsers(dest="scope", required=True)
    validate_one_parser = validate_subcommands.add_parser("one", help="Validate one metadata.yaml")
    validate_one_parser.add_argument("path", help="Path to metadata.yaml")
    validate_one_parser.set_defaults(func=cmd_validate_one)
    validate_all_parser = validate_subcommands.add_parser("all", help="Validate all bricks/*/metadata.yaml")
    validate_all_parser.set_defaults(func=cmd_validate_all)

    lint = sub.add_parser("lint", help="Lint metadata YAML")
    lint_subcommands = lint.add_subparsers(dest="scope", required=True)
    lint_one_parser = lint_subcommands.add_parser("one", help="Lint one metadata.yaml")
    lint_one_parser.add_argument("path", help="Path to metadata.yaml")
    lint_one_parser.set_defaults(func=cmd_lint_one)

    doctor = sub.add_parser("doctor", help="Run environment diagnostics")
    doctor.set_defaults(func=cmd_doctor)

    capabilities = sub.add_parser(
        "capabilities",
        help="Unified capability readiness and guided remediation orchestration",
    )
    capabilities_sub = capabilities.add_subparsers(dest="cap_cmd", required=True)

    capabilities_status = capabilities_sub.add_parser("status", help="Discover/classify and print readiness report")
    capabilities_status.add_argument("--json", action="store_true", help="Emit JSON output")
    capabilities_status.set_defaults(func=cmd_capabilities_status)

    capabilities_run = capabilities_sub.add_parser(
        "run",
        help="Run discover -> classify -> propose fixes -> execute approved fixes -> verify -> report",
    )
    capabilities_run.add_argument("--approve", action="store_true", help="Approve guided auto-fix execution")
    capabilities_run.add_argument(
        "--lane",
        default="all",
        choices=("all", "cpp", "notebook", "provider"),
        help="Optional lane hint for remediation routing",
    )
    capabilities_run.add_argument("--json", action="store_true", help="Emit JSON output")
    capabilities_run.set_defaults(func=cmd_capabilities_run)

    capabilities_fix = capabilities_sub.add_parser("fix", help="Execute one remediation action")
    capabilities_fix.add_argument(
        "--action",
        required=True,
        choices=(
            CAP_ACTION_FIX_ALL,
            CAP_ACTION_REPAIR_CPP,
            CAP_ACTION_REPAIR_NOTEBOOK,
            CAP_ACTION_START_LM_STUDIO,
            CAP_ACTION_START_OLLAMA,
        ),
        help="Action id to execute",
    )
    capabilities_fix.add_argument("--approve", action="store_true", help="Required to execute side-effecting actions")
    capabilities_fix.add_argument(
        "--lane",
        default="all",
        choices=("all", "cpp", "notebook", "provider"),
        help="Optional lane hint for remediation routing",
    )
    capabilities_fix.add_argument("--json", action="store_true", help="Emit JSON output")
    capabilities_fix.set_defaults(func=cmd_capabilities_fix)

    hardware_check = sub.add_parser("hardware-check", help="Map current machine hardware to roadmap phase support")
    hardware_check.add_argument(
        "--path",
        default=".",
        help="Disk path used for free-space checks (absolute or relative to repo root)",
    )
    hardware_check.add_argument("--json", action="store_true", help="Emit JSON output")
    hardware_check.set_defaults(func=cmd_hardware_check)

    sewing = sub.add_parser("sewing", help="AI33 Virtual Sewing Machine runner passthrough")
    sewing.add_argument(
        "sewing_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to sewing_machine/runner.py",
    )
    sewing.set_defaults(func=cmd_sewing)

    repo_root_parser = sub.add_parser("repo-root", help="Print git repo root")
    repo_root_parser.set_defaults(func=cmd_repo_root)

    spellcheck = sub.add_parser("spell-check", help="Run cspell over repository targets")
    spellcheck.add_argument(
        "paths",
        nargs="*",
        help="Optional file/folder paths (defaults to README.md, USAGE.md, docs, src, tests, bricks)",
    )
    spellcheck.add_argument(
        "--config",
        default="cspell.json",
        help="Path to cspell config (default: cspell.json at repo root)",
    )
    spellcheck.add_argument("--json", action="store_true", help="Emit JSON output")
    spellcheck.set_defaults(func=cmd_spell_check)

    spell_sync = sub.add_parser("spell-sync-vscode", help="Sync cspell words into global VS Code user settings")
    spell_sync.add_argument(
        "--settings-path",
        default="",
        help="Optional override path to VS Code settings.json (absolute or relative to repo root)",
    )
    spell_sync.add_argument("--dry-run", action="store_true", help="Preview merge counts without writing settings")
    spell_sync.add_argument("--json", action="store_true", help="Emit JSON output")
    spell_sync.set_defaults(func=cmd_spell_sync_vscode)

    admin = sub.add_parser("admin", help="Admin helper commands")
    admin_subcommands = admin.add_subparsers(dest="admin_cmd", required=True)
    admin_check_parser = admin_subcommands.add_parser("check", help="Read-only git checks")
    admin_check_parser.set_defaults(func=cmd_admin_check)
    admin_reset_parser = admin_subcommands.add_parser(
        "reset-hard", help="Reset local checkout to HEAD (DESTRUCTIVE)"
    )
    admin_reset_parser.add_argument("--yes", action="store_true", help="Required flag for destructive action")
    admin_reset_parser.set_defaults(func=cmd_admin_danger)

    pt = sub.add_parser("pt", help="Packet Tracer helpers")
    pt_subcommands = pt.add_subparsers(dest="pt_cmd", required=True)
    pt_preflight_parser = pt_subcommands.add_parser(
        "preflight", help="Check unresolved topology state for PT automation"
    )
    pt_preflight_parser.add_argument(
        "path",
        nargs="?",
        default=DEFAULT_PT_PATH,
        help="Template/lab folder path (absolute or relative to repo root)",
    )
    pt_preflight_parser.add_argument(
        "--mode",
        choices=list(MODES),
        default=None,
        help="Readiness gate: scaffold, config, or deploy",
    )
    pt_preflight_parser.add_argument(
        "--profile",
        choices=sorted(VALIDATION_PROFILES),
        default=None,
        help="Validation profile shortcut for mode/tolerance defaults",
    )
    pt_preflight_parser.add_argument(
        "--max-todo",
        type=int,
        default=None,
        help="Allowed TODO/TBD/FIXME count before deploy mode fails",
    )
    pt_preflight_parser.add_argument(
        "--max-unmapped-links",
        type=int,
        default=None,
        help="Allowed blank-port links count before deploy mode fails",
    )
    pt_preflight_parser.add_argument("--json", action="store_true", help="Emit JSON report")
    pt_preflight_parser.set_defaults(func=cmd_pt_preflight)

    pt_apply_parser = pt_subcommands.add_parser(
        "apply-link-ports",
        help="Generate interface blocks in bootstrap_cli/* from links.csv",
    )
    pt_apply_parser.add_argument(
        "path",
        nargs="?",
        default=DEFAULT_PT_PATH,
        help="Template/lab folder path (absolute or relative to repo root)",
    )
    pt_apply_parser.add_argument(
        "--write",
        action="store_true",
        help="Write changes to files (default is dry-run report only)",
    )
    pt_apply_parser.set_defaults(func=cmd_pt_apply_link_ports)

    pt_autopilot_parser = pt_subcommands.add_parser(
        "autopilot",
        help="Run validation gate, apply-link-ports --write, and final preflight in sequence",
    )
    pt_autopilot_parser.add_argument(
        "path",
        nargs="?",
        default=DEFAULT_PT_PATH,
        help="Template/lab folder path (absolute or relative to repo root)",
    )
    pt_autopilot_parser.add_argument(
        "--profile",
        choices=sorted(VALIDATION_PROFILES),
        default="strict",
        help="Validation profile shortcut for mode/tolerance defaults",
    )
    pt_autopilot_parser.add_argument(
        "--mode",
        choices=list(MODES),
        default=None,
        help="Override profile mode for validation and final preflight",
    )
    pt_autopilot_parser.add_argument(
        "--max-todo",
        type=int,
        default=None,
        help="Override profile TODO tolerance",
    )
    pt_autopilot_parser.add_argument(
        "--max-unmapped-links",
        type=int,
        default=None,
        help="Override profile unmapped-link tolerance",
    )
    pt_autopilot_parser.add_argument(
        "--force",
        action="store_true",
        help="Continue to next step even if an earlier step fails",
    )
    pt_autopilot_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    pt_autopilot_parser.set_defaults(func=cmd_pt_autopilot)

    ai = sub.add_parser("ai", help="Offline-first local AI helpers")
    ai_subcommands = ai.add_subparsers(dest="ai_cmd", required=True)

    ai_model = ai_subcommands.add_parser("model", help="Manage local AI model registry")
    ai_model_sub = ai_model.add_subparsers(dest="ai_model_cmd", required=True)
    ai_model_list = ai_model_sub.add_parser("list", help="List registered models")
    ai_model_list.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_model_list.set_defaults(func=cmd_ai_model_list)

    ai_model_install = ai_model_sub.add_parser("install", help="Register/install one model")
    ai_model_install.add_argument("model_id", help="Unique model identifier")
    ai_model_install.add_argument("--provider", choices=("extractive", "ollama"), required=True, help="Runtime provider")
    ai_model_install.add_argument("--model", required=True, help="Provider model name")
    ai_model_install.add_argument("--tag", dest="tags", action="append", default=[], help="Model tag (repeatable)")
    ai_model_install.add_argument("--notes", default="", help="Optional notes")
    ai_model_install.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_model_install.set_defaults(func=cmd_ai_model_install)

    ai_model_remove = ai_model_sub.add_parser("remove", help="Remove one model from registry")
    ai_model_remove.add_argument("model_id", help="Model identifier")
    ai_model_remove.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_model_remove.set_defaults(func=cmd_ai_model_remove)

    ai_model_default = ai_model_sub.add_parser("set-default", help="Set default model for a task")
    ai_model_default.add_argument("task", help="Task lane (general/coding/summarization/translation)")
    ai_model_default.add_argument("model_id", help="Model identifier")
    ai_model_default.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_model_default.set_defaults(func=cmd_ai_model_set_default)

    ai_model_recommend = ai_model_sub.add_parser("recommend", help="Recommend models for current hardware")
    ai_model_recommend.add_argument("--path", default=".", help="Disk path for free-space checks")
    ai_model_recommend.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_model_recommend.set_defaults(func=cmd_ai_model_recommend)

    ai_source = ai_subcommands.add_parser("source", help="Manage curated offline source catalog")
    ai_source_sub = ai_source.add_subparsers(dest="ai_source_cmd", required=True)
    ai_source_add = ai_source_sub.add_parser("add", help="Add one source to curated manifest")
    ai_source_add.add_argument("source_id", help="Source identifier")
    ai_source_add.add_argument("--uri", required=True, help="Source URI (https URL, file path, or directory path)")
    ai_source_add.add_argument("--license", dest="license_name", required=True, help="License identifier")
    ai_source_add.add_argument("--name", default="", help="Display name")
    ai_source_add.add_argument("--notes", default="", help="Optional notes")
    ai_source_add.add_argument(
        "--allow-domain",
        default="",
        help="Optionally add this domain to allowlist before source add (URL sources)",
    )
    ai_source_add.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_source_add.set_defaults(func=cmd_ai_source_add)

    ai_source_list = ai_source_sub.add_parser("list", help="List sources")
    ai_source_list.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_source_list.set_defaults(func=cmd_ai_source_list)

    ai_source_sync = ai_source_sub.add_parser("sync", help="Sync one source into local raw mirror")
    ai_source_sync.add_argument("source_id", help="Source identifier")
    ai_source_sync.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_source_sync.set_defaults(func=cmd_ai_source_sync)

    ai_source_remove = ai_source_sub.add_parser("remove", help="Remove one source")
    ai_source_remove.add_argument("source_id", help="Source identifier")
    ai_source_remove.add_argument("--keep-files", action="store_true", help="Only remove manifest entry")
    ai_source_remove.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_source_remove.set_defaults(func=cmd_ai_source_remove)

    ai_ingest = ai_subcommands.add_parser("ingest", help="Normalize mirrored sources for index build")
    ai_ingest_sub = ai_ingest.add_subparsers(dest="ai_ingest_cmd", required=True)
    ai_ingest_run = ai_ingest_sub.add_parser("run", help="Normalize synced source files")
    ai_ingest_run.add_argument("--source-id", default="", help="Optional single source id")
    ai_ingest_run.add_argument("--max-files", type=int, default=50000, help="Maximum files to process")
    ai_ingest_run.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_ingest_run.set_defaults(func=cmd_ai_ingest_run)

    ai_ingest_status = ai_ingest_sub.add_parser("status", help="Show ingestion status")
    ai_ingest_status.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_ingest_status.set_defaults(func=cmd_ai_ingest_status)

    ai_ingest_rebuild = ai_ingest_sub.add_parser("rebuild", help="Run ingest then index build")
    ai_ingest_rebuild.add_argument("--source-id", default="", help="Optional single source id")
    ai_ingest_rebuild.add_argument("--max-files", type=int, default=50000, help="Maximum files to process")
    ai_ingest_rebuild.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_ingest_rebuild.set_defaults(func=cmd_ai_ingest_rebuild)

    ai_index_build = ai_subcommands.add_parser("index-build", help="Build ai2 hybrid index")
    ai_index_build.add_argument("--source-id", default="", help="Optional single source id")
    ai_index_build.add_argument("--max-files", type=int, default=50000, help="Maximum normalized files to index")
    ai_index_build.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_index_build.set_defaults(func=cmd_ai_index_build2)

    ai_index_stats = ai_subcommands.add_parser("index-stats", help="Show ai2 index statistics")
    ai_index_stats.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_index_stats.set_defaults(func=cmd_ai_index_stats2)

    ai_index_query = ai_subcommands.add_parser("index-query", help="Query ai2 hybrid index")
    ai_index_query.add_argument("question", nargs="+", help="Question for indexed offline corpus")
    ai_index_query.add_argument("--top-k", type=int, default=5, help="Top chunks to retrieve")
    ai_index_query.add_argument("--provider", choices=("extractive", "ollama"), default="extractive", help="Answer provider")
    ai_index_query.add_argument("--model-id", default="", help="Model registry id override")
    ai_index_query.add_argument("--task", default="general", help="Task lane for default model selection")
    ai_index_query.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_index_query.add_argument("--no-memory", dest="memory", action="store_false", help="Do not store query in memory db")
    ai_index_query.set_defaults(memory=True, func=cmd_ai_index_query2)

    ai_index_doctor = ai_subcommands.add_parser("index-doctor", help="Diagnose ai2 index health")
    ai_index_doctor.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_index_doctor.set_defaults(func=cmd_ai_index_doctor2)

    ai_hybrid_answer = ai_subcommands.add_parser(
        "hybrid-answer",
        help="Use Codex when available and automatically fall back to local offline stack",
    )
    ai_hybrid_answer.add_argument("question", nargs="+", help="Question for hybrid router")
    ai_hybrid_answer.add_argument("--top-k", type=int, default=5, help="Top retrieval chunks for context assembly")
    ai_hybrid_answer.add_argument(
        "--force-local",
        action="store_true",
        help="Force local answer path even when Codex is available",
    )
    ai_hybrid_answer.add_argument(
        "--no-codex",
        action="store_true",
        help="Disable Codex attempt and use local path only",
    )
    ai_hybrid_answer.add_argument("--codex-model", default="gpt-5", help="Remote model name for Codex path")
    ai_hybrid_answer.add_argument(
        "--codex-base-url",
        default="https://api.openai.com/v1",
        help="Base URL for OpenAI-compatible Codex endpoint",
    )
    ai_hybrid_answer.add_argument("--timeout-s", type=int, default=40, help="Remote request timeout in seconds")
    ai_hybrid_answer.add_argument(
        "--local-provider",
        choices=("extractive", "ollama"),
        default="extractive",
        help="Local fallback provider",
    )
    ai_hybrid_answer.add_argument(
        "--local-model-id",
        default="",
        help="Local registry model id override for fallback route",
    )
    ai_hybrid_answer.add_argument("--user-id", default="", help="User id for quota/audit/preference routing")
    ai_hybrid_answer.add_argument(
        "--attachment-path",
        action="append",
        default=[],
        help="Attachment path hint for task classifier (repeatable)",
    )
    ai_hybrid_answer.add_argument(
        "--metadata-json",
        default="{}",
        help="Additional metadata JSON object for routing classifier",
    )
    ai_hybrid_answer.add_argument(
        "--task-type",
        choices=sorted(AI_ROUTING_TASK_TYPES),
        default="auto",
        help="Task class override: simple, complex, sensitive, or auto classifier",
    )
    ai_hybrid_answer.add_argument(
        "--ask-on-uncertain",
        dest="ask_on_uncertain",
        action="store_true",
        default=None,
        help="Prompt for route choice when auto-classifier confidence is low",
    )
    ai_hybrid_answer.add_argument(
        "--no-ask-on-uncertain",
        dest="ask_on_uncertain",
        action="store_false",
        help="Do not prompt when classifier is uncertain; use recommended route",
    )
    ai_hybrid_answer.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_hybrid_answer.add_argument(
        "--no-memory",
        dest="memory",
        action="store_false",
        help="Do not persist hybrid exchanges in local memory store",
    )
    ai_hybrid_answer.set_defaults(memory=True, func=cmd_ai_hybrid_answer)

    ai_route_policy = ai_subcommands.add_parser("route-policy", help="Show/set/validate hybrid routing policy")
    ai_route_policy_sub = ai_route_policy.add_subparsers(dest="ai_route_policy_cmd", required=True)
    ai_route_policy_show = ai_route_policy_sub.add_parser("show", help="Show active routing policy")
    ai_route_policy_show.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_route_policy_show.set_defaults(func=cmd_ai_route_policy_show)

    ai_route_policy_set = ai_route_policy_sub.add_parser("set", help="Update routing policy fields")
    ai_route_policy_set.add_argument("--mode", choices=("auto", "manual"), default="", help="Routing policy mode")
    ai_route_policy_set.add_argument(
        "--uncertain-threshold",
        type=float,
        default=None,
        help="Confidence threshold below which route ask can trigger",
    )
    ai_route_policy_set.add_argument(
        "--min-margin",
        type=float,
        default=None,
        help="Minimum score margin before classifier is treated as confident",
    )
    ai_route_policy_set.add_argument(
        "--ask-on-uncertain",
        dest="ask_on_uncertain",
        action="store_true",
        default=None,
        help="Enable route ask fallback on low confidence",
    )
    ai_route_policy_set.add_argument(
        "--no-ask-on-uncertain",
        dest="ask_on_uncertain",
        action="store_false",
        help="Disable route ask fallback and use recommended route directly",
    )
    ai_route_policy_set.add_argument("--profile", default="", help="Active performance profile")
    ai_route_policy_set.add_argument(
        "--default-local-provider",
        choices=("extractive", "ollama", "lmstudio"),
        default="",
        help="Preferred local provider for policy routes",
    )
    ai_route_policy_set.add_argument("--default-codex-model", default="", help="Preferred remote model")
    ai_route_policy_set.add_argument(
        "--prefer-quantum-when-available",
        dest="prefer_quantum_when_available",
        action="store_true",
        default=None,
        help="Keep Azure Quantum as the preferred later optimizer when the classical baseline is already available",
    )
    ai_route_policy_set.add_argument(
        "--no-prefer-quantum-when-available",
        dest="prefer_quantum_when_available",
        action="store_false",
        help="Do not prefer the later quantum optimizer automatically",
    )
    ai_route_policy_set.add_argument(
        "--quantum-enabled",
        dest="quantum_enabled",
        action="store_true",
        default=None,
        help="Enable the later quantum decision lane in policy state",
    )
    ai_route_policy_set.add_argument(
        "--no-quantum-enabled",
        dest="quantum_enabled",
        action="store_false",
        help="Disable the later quantum decision lane in policy state",
    )
    ai_route_policy_set.add_argument(
        "--quantum-backend",
        default="",
        help="Named backend for the later quantum optimizer",
    )
    ai_route_policy_set.add_argument(
        "--quantum-use-case",
        action="append",
        default=[],
        help="Decision-engine use case to prefer for later quantum optimization (repeatable or comma-separated)",
    )
    ai_route_policy_set.add_argument(
        "--set",
        action="append",
        default=[],
        help="Generic key=value override (repeatable; supports JSON values)",
    )
    ai_route_policy_set.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_route_policy_set.set_defaults(func=cmd_ai_route_policy_set)

    ai_route_policy_validate = ai_route_policy_sub.add_parser("validate", help="Validate routing policy schema")
    ai_route_policy_validate.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_route_policy_validate.set_defaults(func=cmd_ai_route_policy_validate)

    ai_route_policy_sim = ai_route_policy_sub.add_parser(
        "simulate",
        help="Simulate routing decision with dynamic threshold and metadata",
    )
    ai_route_policy_sim.add_argument("prompt", nargs="+", help="Prompt text to classify")
    ai_route_policy_sim.add_argument(
        "--metadata-json",
        default="{}",
        help="Optional metadata object for feature extraction",
    )
    ai_route_policy_sim.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_route_policy_sim.set_defaults(func=cmd_ai_route_policy_simulate)

    ai_route_ask = ai_subcommands.add_parser("route-ask", help="Ask user to confirm local/codex/both route")
    ai_route_ask.add_argument("task_summary", nargs="+", help="Task summary used to compute recommendation")
    ai_route_ask.add_argument(
        "--options",
        default="local,codex,both",
        help="Comma-separated route options (subset of local,codex,both)",
    )
    ai_route_ask.add_argument(
        "--choose",
        default="",
        help="Non-interactive explicit choice (local/codex/both)",
    )
    ai_route_ask.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for a route choice in terminal",
    )
    ai_route_ask.add_argument(
        "--metadata-json",
        default="{}",
        help="Optional metadata object for classifier features",
    )
    ai_route_ask.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_route_ask.set_defaults(func=cmd_ai_route_ask)

    ai_continue_setup = ai_subcommands.add_parser(
        "continue-setup",
        help="Generate Continue VS Code config for CCBS local+Codex hybrid use",
    )
    ai_continue_setup.add_argument(
        "--provider",
        choices=("ollama",),
        default="ollama",
        help="Primary local provider used by Continue",
    )
    ai_continue_setup.add_argument(
        "--local-model",
        default="llama3.1:8b",
        help="Local model id for Continue primary path",
    )
    ai_continue_setup.add_argument(
        "--local-fast-model",
        default="qwen2.5-coder:7b",
        help="Fast local model id for autocomplete/light tasks",
    )
    ai_continue_setup.add_argument(
        "--local-base-url",
        default="http://127.0.0.1:11434",
        help="Local provider API base URL",
    )
    ai_continue_setup.add_argument(
        "--codex-model",
        default="gpt-5",
        help="Remote Codex model for complex routing",
    )
    ai_continue_setup.add_argument(
        "--codex-base-url",
        default="https://api.openai.com/v1",
        help="Remote OpenAI-compatible API base URL",
    )
    ai_continue_setup.add_argument(
        "--output",
        default=".continue/config.json",
        help="Output Continue config path",
    )
    ai_continue_setup.add_argument("--force", action="store_true", help="Overwrite existing output config")
    ai_continue_setup.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_continue_setup.set_defaults(func=cmd_ai_continue_setup)

    ai_perf = ai_subcommands.add_parser("perf", help="Hardware/runtime profile and endpoint diagnostics")
    ai_perf_sub = ai_perf.add_subparsers(dest="ai_perf_cmd", required=True)
    ai_perf_status = ai_perf_sub.add_parser("status", help="Show profile recommendation + endpoint status")
    ai_perf_status.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_perf_status.set_defaults(func=cmd_ai_perf_status)
    ai_perf_bench = ai_perf_sub.add_parser("benchmark", help="Benchmark TTFT/tokens-per-second")
    ai_perf_bench.add_argument("--provider", choices=("local", "codex", "remote2"), required=True, help="Provider lane")
    ai_perf_bench.add_argument("--model", required=True, help="Model identifier for benchmark")
    ai_perf_bench.add_argument("--runs", type=int, default=3, help="Number of benchmark runs")
    ai_perf_bench.add_argument("--prompt", default="Explain routing fallback briefly.", help="Prompt text")
    ai_perf_bench.add_argument("--prompt-file", default="", help="Optional prompt file path")
    ai_perf_bench.add_argument("--base-url", default="", help="Optional provider base URL override")
    ai_perf_bench.add_argument("--timeout-s", type=int, default=40, help="Request timeout seconds")
    ai_perf_bench.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_perf_bench.set_defaults(func=cmd_ai_perf_benchmark)

    ai_key = ai_subcommands.add_parser("key", help="Manage provider API keys (OS keyring + env fallback)")
    ai_key_sub = ai_key.add_subparsers(dest="ai_key_cmd", required=True)
    ai_key_set = ai_key_sub.add_parser("set", help="Store one provider API key in OS keyring")
    ai_key_set.add_argument("--provider", choices=("codex", "remote2"), required=True, help="Provider id")
    ai_key_set.add_argument("--api-key", required=True, help="Provider API key")
    ai_key_set.add_argument("--user-id", default="default", help="User id namespace for key reference")
    ai_key_set.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_key_set.set_defaults(func=cmd_ai_key_set)

    ai_key_get = ai_key_sub.add_parser("get", help="Show masked key status for one provider/user")
    ai_key_get.add_argument("--provider", choices=("codex", "remote2"), required=True, help="Provider id")
    ai_key_get.add_argument("--user-id", default="default", help="User id namespace")
    ai_key_get.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_key_get.set_defaults(func=cmd_ai_key_get)

    ai_key_del = ai_key_sub.add_parser("delete", help="Delete one provider key reference from keyring")
    ai_key_del.add_argument("--provider", choices=("codex", "remote2"), required=True, help="Provider id")
    ai_key_del.add_argument("--user-id", default="default", help="User id namespace")
    ai_key_del.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_key_del.set_defaults(func=cmd_ai_key_delete)

    ai_key_status = ai_key_sub.add_parser("status", help="Show provider key resolution status")
    ai_key_status.add_argument("--provider", choices=("codex", "remote2"), required=True, help="Provider id")
    ai_key_status.add_argument("--user-id", default="default", help="User id namespace")
    ai_key_status.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_key_status.set_defaults(func=cmd_ai_key_status)

    ai_quota = ai_subcommands.add_parser("quota", help="Manage local soft quota for dynamic routing")
    ai_quota_sub = ai_quota.add_subparsers(dest="ai_quota_cmd", required=True)
    ai_quota_status = ai_quota_sub.add_parser("status", help="Show quota usage and budget")
    ai_quota_status.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_quota_status.set_defaults(func=cmd_ai_quota_status)
    ai_quota_set = ai_quota_sub.add_parser("set", help="Set monthly token/cost soft budget")
    ai_quota_set.add_argument("--monthly-token-budget", type=int, required=True, help="Monthly token budget")
    ai_quota_set.add_argument("--monthly-cost-budget", type=float, required=True, help="Monthly cost budget (USD)")
    ai_quota_set.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_quota_set.set_defaults(func=cmd_ai_quota_set)

    ai_add_context = ai_subcommands.add_parser(
        "add-context",
        help="Sync source context paths into Continue config managed block",
    )
    ai_add_context.add_argument("--source-id", action="append", required=True, help="Source id (repeatable)")
    ai_add_context.add_argument(
        "--continue-config",
        default=".continue/config.json",
        help="Continue config path to update",
    )
    ai_add_context.add_argument(
        "--mode",
        choices=("append", "replace"),
        default="append",
        help="Append or replace managed context block",
    )
    ai_add_context.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_add_context.set_defaults(func=cmd_ai_add_context)

    ai_prompt_pack = ai_subcommands.add_parser("prompt-pack", help="Manage curated safe prompt packs")
    ai_prompt_pack_sub = ai_prompt_pack.add_subparsers(dest="ai_prompt_pack_cmd", required=True)

    ai_prompt_pack_list = ai_prompt_pack_sub.add_parser("list", help="List available prompt packs")
    ai_prompt_pack_list.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_prompt_pack_list.set_defaults(func=cmd_ai_prompt_pack_list)

    ai_prompt_pack_show = ai_prompt_pack_sub.add_parser("show", help="Show one prompt pack or prompt")
    ai_prompt_pack_show.add_argument("--pack", required=True, help="Prompt pack id")
    ai_prompt_pack_show.add_argument("--prompt", default="", help="Optional prompt id")
    ai_prompt_pack_show.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_prompt_pack_show.set_defaults(func=cmd_ai_prompt_pack_show)

    ai_prompt_pack_export = ai_prompt_pack_sub.add_parser("export", help="Export prompt pack markdown/json")
    ai_prompt_pack_export.add_argument("--pack", required=True, help="Prompt pack id")
    ai_prompt_pack_export.add_argument("--prompt", default="", help="Optional single prompt id")
    ai_prompt_pack_export.add_argument("--output", required=True, help="Output path")
    ai_prompt_pack_export.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format",
    )
    ai_prompt_pack_export.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_prompt_pack_export.set_defaults(func=cmd_ai_prompt_pack_export)

    ai_usecase = ai_subcommands.add_parser("usecase", help="Build derived AI use-case library from docs")
    ai_usecase_sub = ai_usecase.add_subparsers(dest="ai_usecase_cmd", required=True)

    ai_usecase_build = ai_usecase_sub.add_parser("build", help="Build markdown/json use-case library")
    ai_usecase_build.add_argument("--source", default="docs", help="Source folder or file")
    ai_usecase_build.add_argument(
        "--output-md",
        default="docs/AI_BRICKS_LOOPS_USECASE_LIBRARY.md",
        help="Output markdown path",
    )
    ai_usecase_build.add_argument(
        "--output-json",
        default="docs/AI_BRICKS_LOOPS_USECASE_LIBRARY.json",
        help="Output JSON path",
    )
    ai_usecase_build.add_argument("--include-docx", action="store_true", help="Include .docx files")
    ai_usecase_build.add_argument("--include-pdf", action="store_true", help="Include .pdf files")
    ai_usecase_build.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_usecase_build.set_defaults(func=cmd_ai_usecase_build)

    ai_storage = ai_subcommands.add_parser("storage", help="Storage cap status/gc/verify (200 GiB hard cap)")
    ai_storage_sub = ai_storage.add_subparsers(dest="ai_storage_cmd", required=True)
    ai_storage_status = ai_storage_sub.add_parser("status", help="Show storage usage/cap sections")
    ai_storage_status.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_storage_status.set_defaults(func=cmd_ai_storage_status)

    ai_storage_gc = ai_storage_sub.add_parser("gc", help="Manual reclaim to target bytes")
    ai_storage_gc.add_argument("--target-bytes", type=int, required=True, help="Target total bytes after cleanup")
    ai_storage_gc.add_argument("--dry-run", action="store_true", help="Preview without deleting files")
    ai_storage_gc.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_storage_gc.set_defaults(func=cmd_ai_storage_gc)

    ai_storage_verify = ai_storage_sub.add_parser("verify", help="Verify storage policy and hard cap")
    ai_storage_verify.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_storage_verify.set_defaults(func=cmd_ai_storage_verify)

    ai_user = ai_subcommands.add_parser("user", help="Manage local in-app AI users")
    ai_user_sub = ai_user.add_subparsers(dest="ai_user_cmd", required=True)
    ai_user_create = ai_user_sub.add_parser("create", help="Create/update a user")
    ai_user_create.add_argument("username", help="Username")
    ai_user_create.add_argument("--password", required=True, help="User password (>=8 chars)")
    ai_user_create.add_argument("--role", choices=("admin", "user"), default="user", help="Role")
    ai_user_create.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_create.set_defaults(func=cmd_ai_user_create)

    ai_user_list = ai_user_sub.add_parser("list", help="List users")
    ai_user_list.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_list.set_defaults(func=cmd_ai_user_list)

    ai_user_role = ai_user_sub.add_parser("role", help="Update user role")
    ai_user_role.add_argument("username", help="Username")
    ai_user_role.add_argument("--role", choices=("admin", "user"), required=True, help="Role")
    ai_user_role.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_role.set_defaults(func=cmd_ai_user_role)

    ai_user_disable = ai_user_sub.add_parser("disable", help="Disable/enable user")
    ai_user_disable.add_argument("username", help="Username")
    ai_user_disable.add_argument("--enable", action="store_true", help="Enable user instead of disable")
    ai_user_disable.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_disable.set_defaults(func=cmd_ai_user_disable)

    ai_user_passwd = ai_user_sub.add_parser("passwd", help="Set user password")
    ai_user_passwd.add_argument("username", help="Username")
    ai_user_passwd.add_argument("--password", required=True, help="New password (>=8 chars)")
    ai_user_passwd.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_passwd.set_defaults(func=cmd_ai_user_passwd)

    ai_user_pref = ai_user_sub.add_parser("pref", help="Manage per-user routing provider preferences")
    ai_user_pref_sub = ai_user_pref.add_subparsers(dest="ai_user_pref_cmd", required=True)
    ai_user_pref_set = ai_user_pref_sub.add_parser("set", help="Set preferred provider for one task class")
    ai_user_pref_set.add_argument("--username", required=True, help="Username")
    ai_user_pref_set.add_argument(
        "--task-type",
        choices=("simple", "complex", "sensitive", "auto"),
        required=True,
        help="Task class",
    )
    ai_user_pref_set.add_argument(
        "--provider",
        choices=("local", "codex", "remote2", "both"),
        required=True,
        help="Preferred provider for this task class",
    )
    ai_user_pref_set.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_pref_set.set_defaults(func=cmd_ai_user_pref_set)

    ai_user_pref_show = ai_user_pref_sub.add_parser("show", help="Show one/all user routing preferences")
    ai_user_pref_show.add_argument("--username", default="", help="Optional username filter")
    ai_user_pref_show.add_argument(
        "--task-type",
        choices=("simple", "complex", "sensitive", "auto"),
        default=None,
        help="Optional single task class lookup (requires --username)",
    )
    ai_user_pref_show.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_pref_show.set_defaults(func=cmd_ai_user_pref_show)

    ai_user_owner_auth = ai_user_sub.add_parser("owner-auth", help="Configure passwordless owner auto-auth on loopback")
    ai_user_owner_auth_sub = ai_user_owner_auth.add_subparsers(dest="ai_user_owner_auth_cmd", required=True)

    ai_user_owner_auth_set = ai_user_owner_auth_sub.add_parser("set", help="Enable owner auto-auth for an admin user")
    ai_user_owner_auth_set.add_argument("--username", required=True, help="Admin username to trust on loopback")
    ai_user_owner_auth_set.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_owner_auth_set.set_defaults(func=cmd_ai_user_owner_auth_set)

    ai_user_owner_auth_status = ai_user_owner_auth_sub.add_parser("status", help="Show owner auto-auth status")
    ai_user_owner_auth_status.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_owner_auth_status.set_defaults(func=cmd_ai_user_owner_auth_status)

    ai_user_owner_auth_disable = ai_user_owner_auth_sub.add_parser("disable", help="Disable owner auto-auth")
    ai_user_owner_auth_disable.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_user_owner_auth_disable.set_defaults(func=cmd_ai_user_owner_auth_disable)

    ai_api = ai_subcommands.add_parser("api", help="Serve or inspect local AI API")
    ai_api_sub = ai_api.add_subparsers(dest="ai_api_cmd", required=True)
    ai_api_serve = ai_api_sub.add_parser("serve", help="Run local API server")
    ai_api_serve.add_argument("--host", default="127.0.0.1", help="Bind host")
    ai_api_serve.add_argument("--port", type=int, default=11435, help="Bind port")
    ai_api_serve.add_argument(
        "--allow-remote-owner-auto-auth",
        action="store_true",
        help="Acknowledge the risk and allow non-loopback bind even when owner auto-auth is enabled.",
    )
    ai_api_serve.set_defaults(func=cmd_ai_api_serve)

    ai_api_status = ai_api_sub.add_parser("status", help="Show API dependency status")
    ai_api_status.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_api_status.set_defaults(func=cmd_ai_api_status)

    ai_api_token = ai_api_sub.add_parser("token", help="Issue bearer token using username/password")
    ai_api_token.add_argument("--username", required=True, help="Username")
    ai_api_token.add_argument("--password", required=True, help="Password")
    ai_api_token.add_argument("--ttl-hours", type=int, default=24, help="Token TTL hours")
    ai_api_token.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_api_token.set_defaults(func=cmd_ai_api_token)

    ai_codex = ai_subcommands.add_parser("codex", help="Serve or inspect the Codex integration layer")
    ai_codex_sub = ai_codex.add_subparsers(dest="ai_codex_cmd", required=True)

    ai_codex_status = ai_codex_sub.add_parser("status", help="Show Codex bridge URLs and integration metadata")
    ai_codex_status.add_argument("--host", default=DEFAULT_CODEX_BRIDGE_HOST, help="Advertised bind host")
    ai_codex_status.add_argument("--port", type=int, default=DEFAULT_CODEX_BRIDGE_PORT, help="Advertised bind port")
    ai_codex_status.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_codex_status.set_defaults(func=cmd_ai_codex_status)

    ai_codex_mcp = ai_codex_sub.add_parser("mcp-profile", help="Show the Codex MCP tool profile")
    ai_codex_mcp.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_codex_mcp.set_defaults(func=cmd_ai_codex_mcp_profile)

    ai_codex_bootstrap = ai_codex_sub.add_parser(
        "bootstrap",
        help="Print the Codex bridge summary and then start the loopback bridge",
    )
    ai_codex_bootstrap.add_argument("--host", default=DEFAULT_CODEX_BRIDGE_HOST, help="Bind host")
    ai_codex_bootstrap.add_argument("--port", type=int, default=DEFAULT_CODEX_BRIDGE_PORT, help="Bind port")
    ai_codex_bootstrap.add_argument(
        "--allow-remote-owner-auto-auth",
        action="store_true",
        help="Acknowledge the risk and allow non-loopback bind even when owner auto-auth is enabled.",
    )
    ai_codex_bootstrap.set_defaults(func=cmd_ai_codex_bootstrap)

    ai_codex_serve = ai_codex_sub.add_parser("serve", help="Run the Codex-facing bridge service")
    ai_codex_serve.add_argument("--host", default=DEFAULT_CODEX_BRIDGE_HOST, help="Bind host")
    ai_codex_serve.add_argument("--port", type=int, default=DEFAULT_CODEX_BRIDGE_PORT, help="Bind port")
    ai_codex_serve.add_argument(
        "--allow-remote-owner-auto-auth",
        action="store_true",
        help="Acknowledge the risk and allow non-loopback bind even when owner auto-auth is enabled.",
    )
    ai_codex_serve.set_defaults(func=cmd_ai_codex_serve)

    ai_plugin = ai_subcommands.add_parser("plugin", help="Manage signed plugins")
    ai_plugin_sub = ai_plugin.add_subparsers(dest="ai_plugin_cmd", required=True)
    ai_plugin_list = ai_plugin_sub.add_parser("list", help="List plugins")
    ai_plugin_list.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_plugin_list.set_defaults(func=cmd_ai_plugin_list)

    ai_plugin_install = ai_plugin_sub.add_parser("install", help="Install signed plugin zip")
    ai_plugin_install.add_argument("path", help="Plugin zip path")
    ai_plugin_install.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_plugin_install.set_defaults(func=cmd_ai_plugin_install)

    ai_plugin_enable = ai_plugin_sub.add_parser("enable", help="Enable plugin")
    ai_plugin_enable.add_argument("plugin_id", help="Plugin identifier")
    ai_plugin_enable.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_plugin_enable.set_defaults(func=cmd_ai_plugin_enable)

    ai_plugin_disable = ai_plugin_sub.add_parser("disable", help="Disable plugin")
    ai_plugin_disable.add_argument("plugin_id", help="Plugin identifier")
    ai_plugin_disable.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_plugin_disable.set_defaults(func=cmd_ai_plugin_disable)

    ai_plugin_verify = ai_plugin_sub.add_parser("verify", help="Verify installed plugin signature")
    ai_plugin_verify.add_argument("plugin_id", help="Plugin identifier")
    ai_plugin_verify.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_plugin_verify.set_defaults(func=cmd_ai_plugin_verify)

    ai_workspace = ai_subcommands.add_parser("workspace", help="Manage local workspaces")
    ai_workspace_sub = ai_workspace.add_subparsers(dest="ai_workspace_cmd", required=True)
    ai_workspace_list = ai_workspace_sub.add_parser("list", help="List workspaces")
    ai_workspace_list.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_workspace_list.set_defaults(func=cmd_ai_workspace_list)

    ai_workspace_create = ai_workspace_sub.add_parser("create", help="Create workspace")
    ai_workspace_create.add_argument("workspace_id", help="Workspace identifier")
    ai_workspace_create.add_argument("--name", default="", help="Display name")
    ai_workspace_create.add_argument("--description", default="", help="Description")
    ai_workspace_create.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_workspace_create.set_defaults(func=cmd_ai_workspace_create)

    ai_workspace_switch = ai_workspace_sub.add_parser("switch", help="Set active workspace")
    ai_workspace_switch.add_argument("workspace_id", help="Workspace identifier")
    ai_workspace_switch.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_workspace_switch.set_defaults(func=cmd_ai_workspace_switch)

    ai_pack = ai_subcommands.add_parser("pack", help="Build/install/verify offline AI packs")
    ai_pack_sub = ai_pack.add_subparsers(dest="ai_pack_cmd", required=True)
    ai_pack_build = ai_pack_sub.add_parser("build", help="Build AI pack zip")
    ai_pack_build.add_argument("--output", default="dist/ccbs-ai2-pack.zip", help="Output zip path")
    ai_pack_build.add_argument("--include-data", action="store_true", help="Include normalized and index data")
    ai_pack_build.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_pack_build.set_defaults(func=cmd_ai_pack_build)

    ai_pack_install = ai_pack_sub.add_parser("install", help="Install pack zip")
    ai_pack_install.add_argument("path", help="Pack zip path")
    ai_pack_install.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_pack_install.set_defaults(func=cmd_ai_pack_install)

    ai_pack_list = ai_pack_sub.add_parser("list", help="List installed packs")
    ai_pack_list.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_pack_list.set_defaults(func=cmd_ai_pack_list)

    ai_pack_verify = ai_pack_sub.add_parser("verify", help="Verify installed pack checksums")
    ai_pack_verify.add_argument("pack_name", help="Installed pack name")
    ai_pack_verify.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_pack_verify.set_defaults(func=cmd_ai_pack_verify)

    ai_audit = ai_subcommands.add_parser("audit", help="List AI admin audit events")
    ai_audit.add_argument("--limit", type=int, default=100, help="Max events")
    ai_audit.add_argument("--event-type", default="", help="Optional event type filter")
    ai_audit.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_audit.set_defaults(func=cmd_ai_audit)

    ai_index_parser = ai_subcommands.add_parser("index", help="Index local files for offline Q&A")
    ai_index_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to file or folder to index (absolute or relative to repo root)",
    )
    ai_index_parser.add_argument("--max-files", type=int, default=5000, help="Maximum files to index")
    ai_index_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_index_parser.set_defaults(func=cmd_ai_index)

    ai_answer_parser = ai_subcommands.add_parser("answer", help="Answer a question from local index")
    _add_ai_answer_args(ai_answer_parser)
    ai_answer_parser.set_defaults(func=cmd_ai_answer)

    ai_ask_parser = ai_subcommands.add_parser("ask", help="Alias for `ai answer`")
    _add_ai_answer_args(ai_ask_parser)
    ai_ask_parser.set_defaults(func=cmd_ai_answer)

    ai_chat_parser = ai_subcommands.add_parser("chat", help="Interactive local chat loop")
    ai_chat_parser.add_argument(
        "chat_cmd",
        nargs="?",
        choices=("models", "profile"),
        help="Optional chat utility command (models/profile)",
    )
    ai_chat_parser.add_argument(
        "--provider",
        choices=sorted(LOCAL_PROVIDERS),
        default="extractive",
        help="Local answer provider",
    )
    ai_chat_parser.add_argument("--model", default="llama3.2:3b", help="Model name for provider=ollama")
    ai_chat_parser.add_argument("--top-k", type=int, default=5, help="How many chunks to retrieve per question")
    ai_chat_parser.add_argument(
        "--auto-index",
        dest="auto_index",
        action="store_true",
        help="Auto-index local files before chat if no index exists",
    )
    ai_chat_parser.add_argument(
        "--no-auto-index",
        dest="auto_index",
        action="store_false",
        help="Require an existing index for chat",
    )
    ai_chat_parser.add_argument(
        "--index-path",
        default=".",
        help="Path to index when auto-indexing is needed",
    )
    ai_chat_parser.add_argument(
        "--index-max-files",
        type=int,
        default=5000,
        help="Maximum files to index when auto-indexing",
    )
    ai_chat_parser.add_argument(
        "--no-memory",
        dest="memory",
        action="store_false",
        help="Do not persist chat entries in local memory store",
    )
    ai_chat_parser.add_argument("--json", action="store_true", help="Emit JSON output for utility commands")
    ai_chat_parser.add_argument("--user-id", default="default", help="User id for chat profile utility")
    ai_chat_parser.add_argument("--profile-set", action="store_true", help="Set profile values for `ai chat profile`")
    ai_chat_parser.add_argument("--display-name", default="", help="Chat profile display name")
    ai_chat_parser.add_argument("--avatar-style", default="", help="Chat profile avatar style")
    ai_chat_parser.add_argument("--theme", default="", help="Chat profile theme")
    ai_chat_parser.add_argument("--preferred-model", default="", help="Preferred model key/provider model")
    ai_chat_parser.add_argument("--tone-preset", default="", help="Chat profile tone preset")
    ai_chat_parser.set_defaults(memory=True, auto_index=True, func=cmd_ai_chat)

    ai_route_parser = ai_subcommands.add_parser("route", help="Route plain-English intent to a CLI action")
    ai_route_parser.add_argument("request", nargs="+", help="Plain-English request to route")
    ai_route_parser.add_argument(
        "--path",
        default=DEFAULT_PT_PATH,
        help="Target path for Packet Tracer actions (absolute or relative to repo root)",
    )
    ai_route_parser.add_argument("--execute", action="store_true", help="Execute routed action (default is preview)")
    ai_route_parser.add_argument(
        "--write",
        action="store_true",
        help="Allow write mode for mutating actions like apply-link-ports",
    )
    ai_route_parser.add_argument(
        "--validation-first",
        dest="validation_first",
        action="store_true",
        help="Run validation gates before mutating actions",
    )
    ai_route_parser.add_argument(
        "--no-validation-first",
        dest="validation_first",
        action="store_false",
        help="Skip validation gate before mutating actions",
    )
    ai_route_parser.add_argument("--force", action="store_true", help="Proceed even if validation gate fails")
    ai_route_parser.add_argument(
        "--validation-profile",
        choices=sorted(VALIDATION_PROFILES),
        default="strict",
        help="Validation profile shortcut for mode/tolerance defaults",
    )
    ai_route_parser.add_argument(
        "--max-unmapped-links",
        type=int,
        default=None,
        help="Deploy tolerance for links with blank ports",
    )
    ai_route_parser.add_argument("--max-todo", type=int, default=None, help="Deploy tolerance for TODO markers")
    ai_route_parser.add_argument("--mode", choices=list(MODES), default=None, help="Preflight mode")
    ai_route_parser.add_argument(
        "--provider",
        choices=sorted(LOCAL_PROVIDERS),
        default="extractive",
        help="Provider when route falls back to local Q&A",
    )
    ai_route_parser.add_argument("--model", default="llama3.2:3b", help="Model for provider=ollama")
    ai_route_parser.add_argument("--top-k", type=int, default=5, help="Top retrieval chunks for Q&A fallback")
    ai_route_parser.add_argument(
        "--auto-index",
        dest="auto_index",
        action="store_true",
        help="Auto-index local files before route Q&A fallback if needed",
    )
    ai_route_parser.add_argument(
        "--no-auto-index",
        dest="auto_index",
        action="store_false",
        help="Require an existing index for route Q&A fallback",
    )
    ai_route_parser.add_argument(
        "--index-path",
        default=".",
        help="Path to index when auto-indexing is needed",
    )
    ai_route_parser.add_argument(
        "--index-max-files",
        type=int,
        default=5000,
        help="Maximum files to index when auto-indexing",
    )
    ai_route_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_route_parser.add_argument(
        "--no-memory",
        dest="memory",
        action="store_false",
        help="Do not persist route fallback Q/A entries",
    )
    ai_route_parser.set_defaults(memory=True, auto_index=True, validation_first=True, func=cmd_ai_route)

    ai_permissions_parser = ai_subcommands.add_parser(
        "permissions",
        help="Advise permission level, scan files, and emit transparency guidance",
    )
    ai_permissions_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to scan (absolute or relative to repo root)",
    )
    ai_permissions_parser.add_argument(
        "--task",
        choices=sorted(TASK_REQUIREMENTS),
        default="general",
        help="Task type used to recommend minimum permission level",
    )
    ai_permissions_parser.add_argument(
        "--level",
        choices=sorted(PERMISSION_LEVELS),
        default=None,
        help="User-selected permission level (defaults to recommended)",
    )
    ai_permissions_parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt user to choose permission level interactively",
    )
    ai_permissions_parser.add_argument(
        "--scan",
        dest="scan",
        action="store_true",
        help="Run file safety scan (default)",
    )
    ai_permissions_parser.add_argument(
        "--no-scan",
        dest="scan",
        action="store_false",
        help="Skip file safety scan",
    )
    ai_permissions_parser.add_argument(
        "--max-files",
        type=int,
        default=2000,
        help="Maximum files to scan",
    )
    ai_permissions_parser.add_argument(
        "--write-manifest",
        dest="write_manifest",
        action="store_true",
        help="Write scan manifest to .ccbs/security/scan_manifest.json (default)",
    )
    ai_permissions_parser.add_argument(
        "--no-write-manifest",
        dest="write_manifest",
        action="store_false",
        help="Do not write scan manifest file",
    )
    ai_permissions_parser.add_argument(
        "--hashes",
        action="store_true",
        help="Include SHA256 hashes in manifest for transparent verification",
    )
    ai_permissions_parser.add_argument(
        "--hash-limit",
        type=int,
        default=200,
        help="Maximum number of files to hash when --hashes is set",
    )
    ai_permissions_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_permissions_parser.set_defaults(scan=True, write_manifest=True, func=cmd_ai_permissions)

    ai_diagnose_parser = ai_subcommands.add_parser("diagnose", help="Summarize statuses from manifest.json files")
    ai_diagnose_parser.add_argument(
        "path",
        nargs="?",
        default="evidence",
        help="Path to a manifest.json file or directory containing manifests",
    )
    ai_diagnose_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_diagnose_parser.set_defaults(func=cmd_ai_diagnose)

    ai_memory_parser = ai_subcommands.add_parser("memory", help="Show local AI memory entries")
    ai_memory_parser.add_argument("--limit", type=int, default=20, help="Number of entries to show")
    ai_memory_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_memory_parser.set_defaults(func=cmd_ai_memory)

    ai_diff_parser = ai_subcommands.add_parser("diff-explain", help="Explain config deltas between two files")
    ai_diff_parser.add_argument("old_path", help="Older/original file path")
    ai_diff_parser.add_argument("new_path", help="New/updated file path")
    ai_diff_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    ai_diff_parser.set_defaults(func=cmd_ai_diff_explain)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
