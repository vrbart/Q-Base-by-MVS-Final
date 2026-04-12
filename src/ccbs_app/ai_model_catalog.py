"""Merged model catalog for chat-only mode."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .ai3.db import connect_runtime
from .ai_models import list_models
from .ai_routing_policy import load_routing_policy
from .continue_config import load_continue_config, normalize_continue_config


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


def _flag_enabled(name: str, default: bool = True) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


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
    for row in candidates:
        if row and row not in deduped:
            deduped.append(row)
    return deduped


def _entry(
    *,
    provider: str,
    model: str,
    base_url: str = "",
    source: str,
    installed: bool | None = None,
    reachable: bool | None = None,
) -> dict[str, Any]:
    p = provider.strip().lower()
    m = model.strip()
    b = base_url.strip()
    key = f"{p}|{m}|{b}"
    return {
        "key": key,
        "provider": p,
        "model": m,
        "base_url": b,
        "source": source,
        "installed": installed,
        "reachable": reachable,
        "recommended_for_chat": bool(m and p in {"ollama", "lmstudio", "openai", "codex", "extractive"}),
    }


def _collect_registry(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in list_models(root):
        if not isinstance(row, dict):
            continue
        provider = str(row.get("provider", "")).strip().lower()
        model = str(row.get("model", "")).strip()
        if not provider or not model:
            continue
        base_url = "http://127.0.0.1:11434" if provider == "ollama" else ""
        out.append(
            _entry(
                provider=provider,
                model=model,
                base_url=base_url,
                source="registry",
                installed=bool(row.get("installed", False)),
            )
        )
    return out


def _collect_ollama(live: bool) -> tuple[list[dict[str, Any]], str]:
    if not live:
        return [], ""
    out: list[dict[str, Any]] = []
    try:
        payload = _http_json("http://127.0.0.1:11434/api/tags")
        rows = payload.get("models", [])
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                model = str(row.get("name", "")).strip()
                if not model:
                    continue
                out.append(
                    _entry(
                        provider="ollama",
                        model=model,
                        base_url="http://127.0.0.1:11434",
                        source="ollama_live",
                        installed=True,
                        reachable=True,
                    )
                )
        return out, ""
    except Exception as exc:  # noqa: BLE001
        return [], f"ollama_live:{exc}"


def _collect_lmstudio(live: bool) -> tuple[list[dict[str, Any]], str]:
    if not live:
        return [], ""
    token = _resolve_lmstudio_api_key()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    last_error = ""
    auth_required = False
    for base_url in _lmstudio_base_candidates():
        out: list[dict[str, Any]] = []
        try:
            payload = _http_json(f"{base_url}/models", headers=headers)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{base_url}:{exc}"
            continue
        rows = payload.get("data")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                model = str(row.get("id", "")).strip()
                if not model:
                    continue
                out.append(
                    _entry(
                        provider="lmstudio",
                        model=model,
                        base_url=base_url,
                        source="lmstudio_live",
                        installed=True,
                        reachable=True,
                    )
                )
            return out, ""

        error_obj = payload.get("error", {})
        if isinstance(error_obj, dict):
            code = str(error_obj.get("code", "")).strip().lower()
            message = str(error_obj.get("message", "")).strip().lower()
            if code == "invalid_api_key" or "api token is required" in message:
                auth_required = True
                last_error = "auth_required"
                continue
            if message:
                last_error = message
                continue
        last_error = f"{base_url}:invalid_payload"

    if auth_required:
        if token:
            return [], "lmstudio_live:auth_failed_check_token"
        return [], "lmstudio_live:auth_required_set_LM_API_TOKEN"
    if last_error:
        return [], f"lmstudio_live:{last_error}"
    return [], ""


def _collect_ai3_endpoints(root: Path) -> tuple[list[dict[str, Any]], str]:
    out: list[dict[str, Any]] = []
    try:
        conn = connect_runtime(root)
        try:
            rows = conn.execute(
                "SELECT provider, base_url, chat_model FROM model_endpoint ORDER BY created_at ASC"
            ).fetchall()
            for row in rows:
                provider = str(row["provider"] or "").strip().lower()
                model = str(row["chat_model"] or "").strip()
                base_url = str(row["base_url"] or "").strip()
                if not provider or not model:
                    continue
                out.append(
                    _entry(
                        provider=provider,
                        model=model,
                        base_url=base_url,
                        source="ai3_endpoint",
                        installed=None,
                    )
                )
        finally:
            conn.close()
        return out, ""
    except Exception as exc:  # noqa: BLE001
        return [], f"ai3_endpoint:{exc}"


def _collect_routing_presets(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        policy = load_routing_policy(root)
    except Exception:  # noqa: BLE001
        policy = {}

    local_provider = str(policy.get("default_local_provider", "ollama")).strip().lower()
    active_profile = str(policy.get("active_profile", "laptop")).strip().lower()
    profile = dict(policy.get("profiles", {}).get(active_profile, {}))
    default_local_model = str(profile.get("default_local_model", "llama3.1:8b")).strip() or "llama3.1:8b"
    if local_provider == "ollama":
        out.append(
            _entry(
                provider="ollama",
                model=default_local_model,
                base_url="http://127.0.0.1:11434",
                source="routing_policy",
                installed=None,
            )
        )
    elif local_provider == "lmstudio":
        out.append(
            _entry(
                provider="lmstudio",
                model=default_local_model or "local-model",
                base_url=str(os.environ.get("CCBS_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")).strip() or "http://127.0.0.1:1234/v1",
                source="routing_policy",
                installed=None,
            )
        )
    codex_model = str(policy.get("default_codex_model", "gpt-5")).strip() or "gpt-5"
    out.append(
        _entry(
            provider="codex",
            model=codex_model,
            base_url="https://api.openai.com/v1",
            source="routing_policy",
            installed=None,
        )
    )
    return out


def _collect_continue_presets(root: Path) -> list[dict[str, Any]]:
    if not _flag_enabled("CCBS_CONTINUE_IMPORT_ENABLE", True):
        return []
    candidates = [
        root / ".continue" / "config.json",
        root / ".continue" / "config.yaml",
        Path.home() / ".continue" / "config.yaml",
        Path.home() / ".continue" / "config.json",
    ]
    out: list[dict[str, Any]] = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            cfg = load_continue_config(path)
            norm = normalize_continue_config(cfg)
        except Exception:
            continue
        for row in norm.get("models", []):
            if not isinstance(row, dict):
                continue
            provider = str(row.get("provider", "")).strip().lower()
            model = str(row.get("model", "")).strip()
            base_url = str(row.get("apiBase", "")).strip()
            if not provider or not model:
                continue
            out.append(
                _entry(
                    provider=provider,
                    model=model,
                    base_url=base_url,
                    source=f"continue:{path.name}",
                    installed=None,
                )
            )
    return out


def _dedup(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("key", "")).strip()
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(row)
            merged[key]["sources"] = [str(row.get("source", ""))]
            continue
        item = merged[key]
        item["sources"] = sorted(
            {
                *[str(x) for x in item.get("sources", [])],
                str(row.get("source", "")),
            }
        )
        if row.get("installed") is True:
            item["installed"] = True
        if row.get("reachable") is True:
            item["reachable"] = True
        item["recommended_for_chat"] = bool(item.get("recommended_for_chat", False) or row.get("recommended_for_chat", False))
    out = list(merged.values())
    out.sort(
        key=lambda x: (
            0 if x.get("reachable") else 1,
            0 if x.get("provider") in {"ollama", "lmstudio"} else 1,
            str(x.get("provider", "")),
            str(x.get("model", "")),
            str(x.get("base_url", "")),
        )
    )
    return out


def discover_model_catalog(root: Path) -> dict[str, Any]:
    live = _flag_enabled("CCBS_MODEL_CATALOG_LIVE", True)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    rows.extend(_collect_registry(root))
    rows.extend(_collect_routing_presets(root))
    rows.extend(_collect_continue_presets(root))

    ai3_rows, ai3_err = _collect_ai3_endpoints(root)
    rows.extend(ai3_rows)
    if ai3_err:
        errors.append(ai3_err)

    ollama_rows, ollama_err = _collect_ollama(live=live)
    rows.extend(ollama_rows)
    if ollama_err:
        errors.append(ollama_err)

    lm_rows, lm_err = _collect_lmstudio(live=live)
    rows.extend(lm_rows)
    if lm_err:
        errors.append(lm_err)

    rows.append(
        _entry(
            provider="extractive",
            model="extractive",
            source="builtin",
            installed=True,
            reachable=True,
        )
    )

    merged = _dedup(rows)
    return {
        "models": merged,
        "errors": errors,
        "live_discovery_enabled": live,
    }
