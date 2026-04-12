"""Continue config parsing/normalization helpers.

Supports both legacy JSON shape (contextProviders/customCommands) and
current YAML-friendly shape (context/prompts).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .jsonc_utils import dump_json, parse_jsonc


def is_yaml_path(path: Path) -> bool:
    return path.suffix.strip().lower() in {".yaml", ".yml"}


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ValueError("YAML support requires dependency `PyYAML` (install with: pip install pyyaml)") from exc
    raw = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid YAML in {path}: {exc}") from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"invalid YAML in {path}: root must be an object")
    return payload


def _dump_yaml(payload: dict[str, Any]) -> str:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ValueError("YAML support requires dependency `PyYAML` (install with: pip install pyyaml)") from exc
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def load_continue_config(path: Path) -> dict[str, Any]:
    if is_yaml_path(path):
        return _load_yaml(path)
    raw = path.read_text(encoding="utf-8")
    try:
        payload = parse_jsonc(raw)
    except ValueError as exc:
        raise ValueError(f"invalid JSON/JSONC in {path}: {exc}") from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON in {path}: root must be an object")
    return payload


def write_continue_config(path: Path, payload: dict[str, Any]) -> None:
    if is_yaml_path(path):
        path.write_text(_dump_yaml(payload), encoding="utf-8")
        return
    path.write_text(dump_json(payload), encoding="utf-8")


def _normalize_models(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("models", [])
    out: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for item in rows:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider", "")).strip().lower()
        model = str(item.get("model", "")).strip()
        if not provider or not model:
            continue
        out.append(
            {
                "name": str(item.get("name") or item.get("title") or model).strip(),
                "provider": provider,
                "model": model,
                "apiBase": str(item.get("apiBase", "")).strip(),
                "apiKey": str(item.get("apiKey", "")).strip(),
                "roles": list(item.get("roles", [])) if isinstance(item.get("roles"), list) else [],
            }
        )
    return out


def _normalize_context(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    raw_new = payload.get("context", [])
    if isinstance(raw_new, list):
        for item in raw_new:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("provider", "")).strip().lower()
            if provider:
                out.append(
                    {
                        "provider": provider,
                        "name": str(item.get("name", "")).strip(),
                        "params": dict(item.get("params", {})) if isinstance(item.get("params"), dict) else {},
                    }
                )
    raw_old = payload.get("contextProviders", [])
    if isinstance(raw_old, list):
        for item in raw_old:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("name", "")).strip().lower()
            if provider:
                out.append(
                    {
                        "provider": provider,
                        "name": str(item.get("name", "")).strip(),
                        "params": dict(item.get("params", {})) if isinstance(item.get("params"), dict) else {},
                    }
                )
    # preserve first-seen by provider+params blob
    dedup: dict[str, dict[str, Any]] = {}
    for item in out:
        key = f"{item['provider']}|{json.dumps(item.get('params', {}), sort_keys=True)}"
        if key not in dedup:
            dedup[key] = item
    return list(dedup.values())


def _normalize_prompts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("prompts", "customCommands"):
        rows = payload.get(key, [])
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            prompt = str(item.get("prompt", "")).strip()
            if not name or not prompt:
                continue
            out.append(
                {
                    "name": name,
                    "description": str(item.get("description", "")).strip(),
                    "prompt": prompt,
                }
            )
    dedup: dict[str, dict[str, Any]] = {}
    for item in out:
        dedup[item["name"]] = item
    return list(dedup.values())


def normalize_continue_config(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    return {
        "name": str(payload.get("name", "CCBS Hybrid")).strip() or "CCBS Hybrid",
        "version": str(payload.get("version", "")).strip(),
        "models": _normalize_models(payload),
        "context": _normalize_context(payload),
        "prompts": _normalize_prompts(payload),
    }


def build_ccbs_continue_config(
    *,
    output_yaml_style: bool,
    provider: str,
    local_model: str,
    local_fast_model: str,
    local_base_url: str,
    codex_model: str,
    codex_base_url: str,
) -> dict[str, Any]:
    remote_base = codex_base_url.rstrip("/")
    local_base = local_base_url.rstrip("/")
    if output_yaml_style:
        return {
            "name": "CCBS Hybrid",
            "version": "1.0.0",
            "models": [
                {
                    "name": "CCBS Local Chat",
                    "provider": provider,
                    "model": local_model,
                    "apiBase": local_base,
                    "roles": ["chat"],
                },
                {
                    "name": "CCBS Codex",
                    "provider": "openai",
                    "model": codex_model,
                    "apiBase": remote_base,
                    "apiKey": "${env:OPENAI_API_KEY}",
                    "roles": ["chat"],
                },
                {
                    "name": "CCBS Local Fast",
                    "provider": provider,
                    "model": local_fast_model,
                    "apiBase": local_base,
                    "roles": ["autocomplete"],
                },
            ],
            "context": [
                {"provider": "codebase"},
                {"provider": "docs"},
            ],
            "prompts": [
                {
                    "name": "ccbs-hybrid",
                    "description": "Route through CCBS hybrid backend",
                    "prompt": "{{{ input }}}",
                },
                {
                    "name": "ccbs-network-config",
                    "description": "Network config assistant prompt",
                    "prompt": "You are a precise network configuration assistant. Focus on safe, validated CLI output.\n\n{{{ input }}}",
                },
                {
                    "name": "ccbs-general-coding",
                    "description": "General coding assistant prompt",
                    "prompt": "You are a pragmatic software engineer. Return concise, testable changes.\n\n{{{ input }}}",
                },
            ],
        }
    return {
        "name": "CCBS Hybrid",
        "models": [
            {
                "title": "CCBS Local Chat",
                "provider": provider,
                "model": local_model,
                "apiBase": local_base,
            },
            {
                "title": "CCBS Codex",
                "provider": "openai",
                "model": codex_model,
                "apiBase": remote_base,
                "apiKey": "${env:OPENAI_API_KEY}",
            },
            {
                "title": "CCBS Local Fast",
                "provider": provider,
                "model": local_fast_model,
                "apiBase": local_base,
            },
        ],
        "contextProviders": [
            {"name": "codebase"},
            {"name": "docs"},
        ],
        "customCommands": [
            {
                "name": "ccbs-hybrid",
                "description": "Route through CCBS hybrid backend",
                "prompt": "{{{ input }}}",
            },
            {
                "name": "ccbs-network-config",
                "description": "Network config assistant prompt",
                "prompt": "You are a precise network configuration assistant. Focus on safe, validated CLI output.\\n\\n{{{ input }}}",
            },
            {
                "name": "ccbs-general-coding",
                "description": "General coding assistant prompt",
                "prompt": "You are a pragmatic software engineer. Return concise, testable changes.\\n\\n{{{ input }}}",
            },
        ],
    }


def merge_docs_context(
    payload: dict[str, Any],
    *,
    paths: list[str],
    mode: str = "append",
) -> dict[str, Any]:
    out = dict(payload if isinstance(payload, dict) else {})
    clean_paths = sorted({str(p).strip() for p in paths if str(p).strip()})
    if "context" in out and isinstance(out.get("context"), list):
        current = list(out.get("context", []))
        docs_entry = {
            "provider": "docs",
            "params": {"CCBS_MANAGED_CONTEXT": clean_paths},
        }
        if mode == "replace":
            current = [
                item
                for item in current
                if not (isinstance(item, dict) and str(item.get("provider", "")).strip().lower() == "docs")
            ]
            current.append(docs_entry)
        else:
            replaced = False
            for idx, item in enumerate(current):
                if not (isinstance(item, dict) and str(item.get("provider", "")).strip().lower() == "docs"):
                    continue
                merged = list(item.get("params", {}).get("CCBS_MANAGED_CONTEXT", [])) if isinstance(item.get("params"), dict) else []
                merged.extend(clean_paths)
                current[idx] = {
                    **item,
                    "params": {
                        **(dict(item.get("params", {})) if isinstance(item.get("params"), dict) else {}),
                        "CCBS_MANAGED_CONTEXT": sorted({str(v) for v in merged if str(v).strip()}),
                    },
                }
                replaced = True
                break
            if not replaced:
                current.append(docs_entry)
        out["context"] = current
        return out

    current = list(out.get("contextProviders", [])) if isinstance(out.get("contextProviders", []), list) else []
    docs_entry_legacy = {
        "name": "docs",
        "params": {"CCBS_MANAGED_CONTEXT": clean_paths},
    }
    if mode == "replace":
        current = [
            item
            for item in current
            if not (isinstance(item, dict) and str(item.get("name", "")).strip().lower() == "docs")
        ]
        current.append(docs_entry_legacy)
    else:
        replaced = False
        for idx, item in enumerate(current):
            if not (isinstance(item, dict) and str(item.get("name", "")).strip().lower() == "docs"):
                continue
            merged = list(item.get("params", {}).get("CCBS_MANAGED_CONTEXT", [])) if isinstance(item.get("params"), dict) else []
            merged.extend(clean_paths)
            current[idx] = {
                **item,
                "params": {
                    **(dict(item.get("params", {})) if isinstance(item.get("params"), dict) else {}),
                    "CCBS_MANAGED_CONTEXT": sorted({str(v) for v in merged if str(v).strip()}),
                },
            }
            replaced = True
            break
        if not replaced:
            current.append(docs_entry_legacy)
    out["contextProviders"] = current
    return out

