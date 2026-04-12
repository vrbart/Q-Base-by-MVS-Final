"""Routing policy config and deterministic task classification for hybrid AI routing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .ai_index2 import embedding_for_text
from .ai_storage import ai2_dir

TASK_TYPES = {"simple", "complex", "sensitive", "auto"}
ROUTE_OPTIONS = {"local", "codex", "remote2", "both"}

DEFAULT_SENSITIVE_TOPICS = [
    "private key",
    "api key",
    "password",
    "security token",
    "customer pii",
    "confidential legal document",
    "proprietary source code",
    "credential vault",
    "internal secret",
    "restricted personal data",
]

DEFAULT_ROUTING_POLICY: dict[str, Any] = {
    "version": "ai-routing-policy-v3-local-first",
    "mode": "auto",
    "ask_on_uncertain": True,
    "uncertain_threshold": 0.68,
    "min_margin": 0.14,
    "simple_max_chars": 240,
    "complex_min_chars": 520,
    "dynamic_thresholds": {
        "enabled": True,
        "base_uncertain_threshold": 0.68,
        "load_adjustments": {
            "breaker_open": 0.06,
            "gpu_over_85": 0.03,
        },
        "quota_adjustments": {
            "remaining_below_20pct": 0.08,
        },
        "clamp_min": 0.55,
        "clamp_max": 0.97,
    },
    "baseline_local_tier": "7-8b-q4_k_m",
    "default_local_provider": "ollama",
    "default_codex_model": "gpt-5",
    "decision_engine": {
        "primary_mode": "binary",
        "classical_baseline_required": True,
        "prefer_quantum_when_available": True,
        "quantum_enabled": False,
        "quantum_backend": "azure-quantum-via-foundry",
        "backend_priority": [
            "azure-quantum-via-foundry",
            "ibm-quantum-runtime",
            "classical-baseline",
        ],
        "primary_backend": "azure-quantum-via-foundry",
        "fallback_backend": "ibm-quantum-runtime",
        "sprint_mode": "azure-primary-2026-04-15",
        "quantum_use_cases": [
            "binary_portfolio_selection",
            "binary_task_routing",
            "binary_continue_or_stop",
            "binary_approval_or_escalate",
        ],
        "fallback_mode": "classical",
        "verification_boundary": "required",
    },
    "sensitive": {
        "semantic_threshold": 0.82,
        "topic_library_version": "v1",
    },
    "sensitive_keywords": [
        "password",
        "secret",
        "token",
        "api key",
        "private key",
        "confidential",
        "proprietary",
        "customer data",
        "pii",
        "internal only",
        "restricted",
        "credential",
    ],
    "simple_keywords": [
        "summarize",
        "translate",
        "quick",
        "short",
        "snippet",
        "autocomplete",
        "refactor",
        "explain this",
        "small",
        "one file",
        "single file",
        "minor fix",
    ],
    "complex_keywords": [
        "architecture",
        "multi-file",
        "cross-repository",
        "deep analysis",
        "migration",
        "tradeoff",
        "root cause",
        "design",
        "optimize",
        "planning",
        "security review",
        "performance bottleneck",
        "distributed",
        "scalability",
    ],
    "ask_options": ["local", "codex", "both"],
    "remote_providers": [
        {
            "provider_id": "codex",
            "enabled": True,
            "base_url_env": "OPENAI_BASE_URL",
            "api_key_ref": "OPENAI_API_KEY",
            "model": "gpt-5",
        },
        {
            "provider_id": "remote2",
            "enabled": False,
            "base_url_env": "OPENAI_BASE_URL_REMOTE2",
            "api_key_ref": "OPENAI_API_KEY_REMOTE2",
            "model": "gpt-5-mini",
        },
    ],
    "circuit_breaker": {
        "failures_to_open": 3,
        "cooldown_s": 60,
        "max_cooldown_s": 600,
    },
    "user_override_enabled": True,
    "profiles": {
        "laptop": {
            "recommended_local_model": "7-8b-q4_k_m",
            "default_local_model": "llama3.1:8b",
            "max_context_tokens": 8192,
            "notes": "Run Ollama on the host; reserve Codex for multi-file reasoning, architecture, and migration work.",
        },
        "vm-host": {
            "recommended_local_model": "7-8b-q4_k_m",
            "default_local_model": "llama3.1:8b",
            "max_context_tokens": 8192,
            "notes": "Keep the model runtime on the host and let guests consume it over an explicit internal network only.",
        },
        "workstation": {
            "recommended_local_model": "14b-q4_k_m",
            "default_local_model": "qwen2.5-coder:14b",
            "max_context_tokens": 16384,
            "notes": "Use a stronger local coding model for routine development and keep Codex for the hardest reasoning tasks.",
        },
        "high-end": {
            "recommended_local_model": "30b-q4_k_m",
            "default_local_model": "qwen2.5-coder:32b",
            "max_context_tokens": 32768,
            "notes": "Large local contexts are viable; remote stays for evaluation, overflow, and top-tier reasoning.",
        },
    },
    "active_profile": "laptop",
}

_WS_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_FILE_REF_RE = re.compile(r"\b[\w./\\-]+\.(py|md|json|yaml|yml|txt|cfg|ini|csv|docx|pdf|ipynb|js|ts|tsx|jsx)\b", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```", re.MULTILINE)


def _policy_path(root: Path) -> Path:
    return ai2_dir(root) / "routing_policy.json"


def _topics_path(root: Path) -> Path:
    return ai2_dir(root) / "sensitive_topics.json"


def _normalize_keywords(values: Any, fallback: list[str]) -> list[str]:
    if not isinstance(values, list):
        return list(fallback)
    out: list[str] = []
    for item in values:
        text = str(item).strip().lower()
        if text:
            out.append(text)
    return sorted(set(out)) if out else list(fallback)


def _normalize_ask_options(values: Any) -> list[str]:
    if not isinstance(values, list):
        return list(DEFAULT_ROUTING_POLICY["ask_options"])
    out: list[str] = []
    for item in values:
        text = str(item).strip().lower()
        if text in ROUTE_OPTIONS and text not in out:
            out.append(text)
    if not out:
        return list(DEFAULT_ROUTING_POLICY["ask_options"])
    return out


def _normalize_decision_use_cases(values: Any) -> list[str]:
    fallback = list(DEFAULT_ROUTING_POLICY["decision_engine"]["quantum_use_cases"])
    allowed = {
        "binary_portfolio_selection",
        "binary_task_routing",
        "binary_continue_or_stop",
        "binary_approval_or_escalate",
        "binary_scheduling",
    }
    if not isinstance(values, list):
        return fallback
    out: list[str] = []
    for item in values:
        text = str(item).strip().lower()
        if text in allowed and text not in out:
            out.append(text)
    return out or fallback


def _normalize_backend_priority(values: Any) -> list[str]:
    fallback = list(DEFAULT_ROUTING_POLICY["decision_engine"]["backend_priority"])
    allowed = {
        "azure-quantum-via-foundry",
        "ibm-quantum-runtime",
        "classical-baseline",
    }
    if not isinstance(values, list):
        return fallback
    out: list[str] = []
    for item in values:
        text = str(item).strip().lower()
        if text in allowed and text not in out:
            out.append(text)
    if "classical-baseline" not in out:
        out.append("classical-baseline")
    return out or fallback


def _sanitize_remote_providers(values: Any) -> list[dict[str, Any]]:
    default = list(DEFAULT_ROUTING_POLICY["remote_providers"])
    if not isinstance(values, list):
        return default
    out: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("provider_id", "")).strip().lower()
        if pid not in {"codex", "remote2"}:
            continue
        out.append(
            {
                "provider_id": pid,
                "enabled": bool(item.get("enabled", True)),
                "base_url_env": str(item.get("base_url_env", "OPENAI_BASE_URL")).strip() or "OPENAI_BASE_URL",
                "api_key_ref": str(item.get("api_key_ref", "OPENAI_API_KEY")).strip() or "OPENAI_API_KEY",
                "model": str(item.get("model", "gpt-5")).strip() or "gpt-5",
            }
        )
    if not out:
        return default
    ids = {r["provider_id"] for r in out}
    for row in default:
        if row["provider_id"] not in ids:
            out.append(dict(row))
    return out


def _sanitize_policy(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(DEFAULT_ROUTING_POLICY)

    mode = str(payload.get("mode", out["mode"]))
    out["mode"] = mode if mode in {"auto", "manual"} else "auto"

    try:
        threshold = float(payload.get("uncertain_threshold", out["uncertain_threshold"]))
    except (TypeError, ValueError):
        threshold = float(out["uncertain_threshold"])
    out["uncertain_threshold"] = min(0.95, max(0.5, threshold))

    try:
        margin = float(payload.get("min_margin", out["min_margin"]))
    except (TypeError, ValueError):
        margin = float(out["min_margin"])
    out["min_margin"] = min(0.6, max(0.02, margin))

    for key in ("simple_max_chars", "complex_min_chars"):
        try:
            value = int(payload.get(key, out[key]))
        except (TypeError, ValueError):
            value = int(out[key])
        if key == "simple_max_chars":
            value = min(2000, max(60, value))
        else:
            value = min(6000, max(200, value))
        out[key] = value

    dyn_in = payload.get("dynamic_thresholds")
    dyn_out = dict(DEFAULT_ROUTING_POLICY["dynamic_thresholds"])
    if isinstance(dyn_in, dict):
        dyn_out["enabled"] = bool(dyn_in.get("enabled", dyn_out["enabled"]))
        try:
            dyn_out["base_uncertain_threshold"] = float(dyn_in.get("base_uncertain_threshold", dyn_out["base_uncertain_threshold"]))
        except (TypeError, ValueError):
            pass
        load_adj = dyn_in.get("load_adjustments")
        if isinstance(load_adj, dict):
            current = dict(dyn_out["load_adjustments"])
            for key in ("breaker_open", "gpu_over_85"):
                try:
                    current[key] = float(load_adj.get(key, current[key]))
                except (TypeError, ValueError):
                    pass
            dyn_out["load_adjustments"] = current
        quota_adj = dyn_in.get("quota_adjustments")
        if isinstance(quota_adj, dict):
            current = dict(dyn_out["quota_adjustments"])
            try:
                current["remaining_below_20pct"] = float(quota_adj.get("remaining_below_20pct", current["remaining_below_20pct"]))
            except (TypeError, ValueError):
                pass
            dyn_out["quota_adjustments"] = current
        for key in ("clamp_min", "clamp_max"):
            try:
                dyn_out[key] = float(dyn_in.get(key, dyn_out[key]))
            except (TypeError, ValueError):
                pass

    dyn_out["base_uncertain_threshold"] = min(0.97, max(0.5, float(dyn_out["base_uncertain_threshold"])))
    dyn_out["clamp_min"] = min(0.95, max(0.5, float(dyn_out["clamp_min"])))
    dyn_out["clamp_max"] = min(0.99, max(float(dyn_out["clamp_min"]) + 0.01, float(dyn_out["clamp_max"])))
    out["dynamic_thresholds"] = dyn_out

    out["ask_on_uncertain"] = bool(payload.get("ask_on_uncertain", out["ask_on_uncertain"]))
    out["baseline_local_tier"] = str(payload.get("baseline_local_tier", out["baseline_local_tier"])).strip() or str(
        out["baseline_local_tier"]
    )
    local_provider = str(payload.get("default_local_provider", out["default_local_provider"])).strip().lower()
    if local_provider not in {"extractive", "ollama", "lmstudio"}:
        local_provider = str(out["default_local_provider"])
    out["default_local_provider"] = local_provider
    out["default_codex_model"] = str(payload.get("default_codex_model", out["default_codex_model"])).strip() or "gpt-5"

    decision_in = payload.get("decision_engine")
    decision_out = dict(DEFAULT_ROUTING_POLICY["decision_engine"])
    if isinstance(decision_in, dict):
        decision_out["prefer_quantum_when_available"] = bool(
            decision_in.get("prefer_quantum_when_available", decision_out["prefer_quantum_when_available"])
        )
        decision_out["quantum_enabled"] = bool(decision_in.get("quantum_enabled", decision_out["quantum_enabled"]))
        decision_out["quantum_backend"] = str(decision_in.get("quantum_backend", decision_out["quantum_backend"])).strip() or str(
            decision_out["quantum_backend"]
        )
        decision_out["backend_priority"] = _normalize_backend_priority(decision_in.get("backend_priority"))
        decision_out["primary_backend"] = str(
            decision_in.get("primary_backend", decision_out["primary_backend"])
        ).strip().lower() or str(decision_out["primary_backend"])
        decision_out["fallback_backend"] = str(
            decision_in.get("fallback_backend", decision_out["fallback_backend"])
        ).strip().lower() or str(decision_out["fallback_backend"])
        decision_out["sprint_mode"] = str(decision_in.get("sprint_mode", decision_out["sprint_mode"])).strip() or str(
            decision_out["sprint_mode"]
        )
        decision_out["quantum_use_cases"] = _normalize_decision_use_cases(decision_in.get("quantum_use_cases"))
    decision_out["primary_mode"] = "binary"
    decision_out["classical_baseline_required"] = True
    decision_out["backend_priority"] = _normalize_backend_priority(decision_out.get("backend_priority"))
    primary_backend = str(decision_out.get("primary_backend", "azure-quantum-via-foundry")).strip().lower() or "azure-quantum-via-foundry"
    fallback_backend = str(decision_out.get("fallback_backend", "ibm-quantum-runtime")).strip().lower() or "ibm-quantum-runtime"
    priority = list(decision_out["backend_priority"])
    if primary_backend not in priority:
        priority.insert(0, primary_backend)
    if fallback_backend == primary_backend:
        fallback_backend = "ibm-quantum-runtime" if primary_backend != "ibm-quantum-runtime" else "classical-baseline"
    if fallback_backend not in priority:
        priority.append(fallback_backend)
    if "classical-baseline" not in priority:
        priority.append("classical-baseline")
    decision_out["backend_priority"] = priority
    decision_out["primary_backend"] = primary_backend
    decision_out["fallback_backend"] = fallback_backend
    decision_out["sprint_mode"] = str(decision_out.get("sprint_mode", "azure-primary-2026-04-15")).strip() or "azure-primary-2026-04-15"
    decision_out["fallback_mode"] = "classical"
    decision_out["verification_boundary"] = "required"
    out["decision_engine"] = decision_out

    sensitive_in = payload.get("sensitive")
    sensitive_out = dict(DEFAULT_ROUTING_POLICY["sensitive"])
    if isinstance(sensitive_in, dict):
        try:
            sensitive_out["semantic_threshold"] = float(sensitive_in.get("semantic_threshold", sensitive_out["semantic_threshold"]))
        except (TypeError, ValueError):
            pass
        sensitive_out["topic_library_version"] = str(
            sensitive_in.get("topic_library_version", sensitive_out["topic_library_version"])
        ).strip() or "v1"
    sensitive_out["semantic_threshold"] = min(0.99, max(0.5, float(sensitive_out["semantic_threshold"])))
    out["sensitive"] = sensitive_out

    out["sensitive_keywords"] = _normalize_keywords(payload.get("sensitive_keywords"), out["sensitive_keywords"])
    out["simple_keywords"] = _normalize_keywords(payload.get("simple_keywords"), out["simple_keywords"])
    out["complex_keywords"] = _normalize_keywords(payload.get("complex_keywords"), out["complex_keywords"])
    out["ask_options"] = _normalize_ask_options(payload.get("ask_options"))
    out["remote_providers"] = _sanitize_remote_providers(payload.get("remote_providers"))

    cb_in = payload.get("circuit_breaker")
    cb_out = dict(DEFAULT_ROUTING_POLICY["circuit_breaker"])
    if isinstance(cb_in, dict):
        for key in ("failures_to_open", "cooldown_s", "max_cooldown_s"):
            try:
                cb_out[key] = int(cb_in.get(key, cb_out[key]))
            except (TypeError, ValueError):
                pass
    cb_out["failures_to_open"] = max(1, int(cb_out["failures_to_open"]))
    cb_out["cooldown_s"] = max(1, int(cb_out["cooldown_s"]))
    cb_out["max_cooldown_s"] = max(cb_out["cooldown_s"], int(cb_out["max_cooldown_s"]))
    out["circuit_breaker"] = cb_out

    out["user_override_enabled"] = bool(payload.get("user_override_enabled", out["user_override_enabled"]))

    raw_profiles = payload.get("profiles")
    profiles = dict(DEFAULT_ROUTING_POLICY["profiles"])
    if isinstance(raw_profiles, dict):
        for name, value in raw_profiles.items():
            if not isinstance(value, dict):
                continue
            item = {
                "recommended_local_model": str(
                    value.get("recommended_local_model", profiles.get(name, {}).get("recommended_local_model", "7-8b-q4_k_m"))
                ).strip()
                or "7-8b-q4_k_m",
                "default_local_model": str(
                    value.get("default_local_model", profiles.get(name, {}).get("default_local_model", "llama3.1:8b"))
                ).strip()
                or "llama3.1:8b",
                "max_context_tokens": max(1024, int(value.get("max_context_tokens", profiles.get(name, {}).get("max_context_tokens", 8192)))),
                "notes": str(value.get("notes", profiles.get(name, {}).get("notes", ""))).strip(),
            }
            profiles[str(name).strip().lower()] = item
    out["profiles"] = profiles

    active_profile = str(payload.get("active_profile", out["active_profile"])).strip().lower()
    if active_profile not in profiles:
        active_profile = "laptop"
    out["active_profile"] = active_profile

    out["version"] = str(payload.get("version", out["version"]))
    return out


def load_routing_policy(root: Path) -> dict[str, Any]:
    path = _policy_path(root)
    if not path.exists():
        save_routing_policy(root, dict(DEFAULT_ROUTING_POLICY))
        return dict(DEFAULT_ROUTING_POLICY)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = dict(DEFAULT_ROUTING_POLICY)

    if not isinstance(payload, dict):
        payload = dict(DEFAULT_ROUTING_POLICY)

    sanitized = _sanitize_policy(payload)
    if sanitized != payload:
        save_routing_policy(root, sanitized)
    return sanitized


def save_routing_policy(root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_policy(policy if isinstance(policy, dict) else dict(DEFAULT_ROUTING_POLICY))
    path = _policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")
    return sanitized


def validate_routing_policy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    sanitized = _sanitize_policy(payload if isinstance(payload, dict) else {})

    if float(sanitized["uncertain_threshold"]) < 0.5 or float(sanitized["uncertain_threshold"]) > 0.95:
        issues.append("uncertain_threshold_out_of_bounds")
    if float(sanitized["min_margin"]) <= 0.0:
        issues.append("min_margin_must_be_positive")
    if int(sanitized["simple_max_chars"]) >= int(sanitized["complex_min_chars"]):
        issues.append("simple_max_chars_should_be_less_than_complex_min_chars")
    if str(sanitized["active_profile"]) not in dict(sanitized["profiles"]):
        issues.append("active_profile_not_defined")

    dyn = dict(sanitized.get("dynamic_thresholds", {}))
    if float(dyn.get("clamp_min", 0.55)) >= float(dyn.get("clamp_max", 0.97)):
        issues.append("dynamic_thresholds_clamp_min_must_be_less_than_clamp_max")

    cbreak = dict(sanitized.get("circuit_breaker", {}))
    if int(cbreak.get("cooldown_s", 60)) > int(cbreak.get("max_cooldown_s", 600)):
        issues.append("circuit_breaker_cooldown_s_exceeds_max")

    return {"ok": not issues, "issues": issues, "policy": sanitized}


def update_routing_policy(root: Path, updates: dict[str, Any]) -> dict[str, Any]:
    current = load_routing_policy(root)
    merged = dict(current)
    for key, value in updates.items():
        merged[key] = value
    return save_routing_policy(root, merged)


def _normalize_text(text: str) -> str:
    return _WS_RE.sub(" ", text.strip().lower())


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        key = keyword.strip().lower()
        if key and key in text:
            hits.append(key)
    return sorted(set(hits))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = sum(float(x) * float(x) for x in a) ** 0.5
    norm_b = sum(float(y) * float(y) for y in b) ** 0.5
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _load_sensitive_topics(root: Path | None) -> dict[str, Any]:
    if root is None:
        topics = [{"text": t, "embedding": embedding_for_text(t)} for t in DEFAULT_SENSITIVE_TOPICS]
        return {"version": "v1", "topics": topics}

    path = _topics_path(root)
    if not path.exists():
        payload = {"version": "v1", "topics": [{"text": t, "embedding": embedding_for_text(t)} for t in DEFAULT_SENSITIVE_TOPICS]}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {"version": "v1", "topics": []}
    if not isinstance(payload, dict):
        payload = {"version": "v1", "topics": []}
    topics_in = payload.get("topics", [])
    topics_out: list[dict[str, Any]] = []
    if isinstance(topics_in, list):
        for item in topics_in:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            emb = item.get("embedding", [])
            if not isinstance(emb, list) or not emb:
                emb = embedding_for_text(text)
            topics_out.append({"text": text, "embedding": [float(x) for x in emb]})
    if not topics_out:
        topics_out = [{"text": t, "embedding": embedding_for_text(t)} for t in DEFAULT_SENSITIVE_TOPICS]
    sanitized = {"version": str(payload.get("version", "v1") or "v1"), "topics": topics_out}
    if sanitized != payload:
        path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")
    return sanitized


def extract_task_features(
    question: str,
    policy: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    settings = policy or dict(DEFAULT_ROUTING_POLICY)
    meta = metadata or {}
    raw = question or ""
    clean = _normalize_text(raw)

    lines = raw.splitlines() if raw else []
    line_count = len(lines) if lines else (1 if raw else 0)
    url_count = len(_URL_RE.findall(raw))
    code_fence_count = len(_CODE_FENCE_RE.findall(raw))
    code_block_count = code_fence_count // 2
    indented_code_lines = sum(1 for line in lines if line.startswith("    ") or line.startswith("\t"))
    if indented_code_lines >= 3:
        code_block_count += 1

    attachments = meta.get("attachment_paths", [])
    if not isinstance(attachments, list):
        attachments = []
    attachment_count = len([a for a in attachments if str(a).strip()])

    file_ref_count = len(_FILE_REF_RE.findall(raw))
    shell_markers = [" --", " sudo ", " bash ", " python ", " pip ", " git ", " docker ", " kubectl "]
    command_hits = sum(1 for marker in shell_markers if marker in f" {clean} ")
    command_density = min(1.0, (raw.count("--") + command_hits + file_ref_count) / max(1.0, len(clean.split()) / 6.0 + 1.0))

    sensitive_hits = _keyword_hits(clean, list(settings.get("sensitive_keywords", [])))

    topics = _load_sensitive_topics(root)
    q_emb = embedding_for_text(raw or clean)
    similarity = 0.0
    for topic in topics.get("topics", []):
        emb = topic.get("embedding", [])
        if isinstance(emb, list) and emb:
            similarity = max(similarity, _cosine([float(x) for x in q_emb], [float(x) for x in emb]))

    return {
        "char_count": len(clean),
        "token_count": len([tok for tok in clean.split(" ") if tok]),
        "line_count": line_count,
        "url_count": url_count,
        "code_block_count": code_block_count,
        "attachment_count": attachment_count,
        "file_ref_count": file_ref_count,
        "command_density": round(command_density, 4),
        "sensitive_keyword_hits": sensitive_hits,
        "sensitive_similarity": round(float(similarity), 4),
        "has_urls": bool(meta.get("has_urls", False) or url_count > 0),
        "has_code_blocks": bool(meta.get("has_code_blocks", False) or code_block_count > 0),
    }


def compute_dynamic_threshold(
    policy: dict[str, Any],
    quota_state: dict[str, Any] | None = None,
    resource_state: dict[str, Any] | None = None,
) -> float:
    settings = dict(policy.get("dynamic_thresholds", {}))
    base = float(settings.get("base_uncertain_threshold", policy.get("uncertain_threshold", 0.68)))
    if not bool(settings.get("enabled", True)):
        return round(base, 4)

    threshold = base
    quota = quota_state or {}
    load = resource_state or {}

    if bool(quota.get("under_20_percent_remaining", False)):
        q_adj = float(dict(settings.get("quota_adjustments", {})).get("remaining_below_20pct", 0.08))
        threshold += q_adj

    if bool(load.get("primary_breaker_open", False)):
        l_adj = float(dict(settings.get("load_adjustments", {})).get("breaker_open", 0.06))
        threshold += l_adj

    gpu_util = load.get("max_gpu_utilization_pct", 0.0)
    try:
        gpu_util_f = float(gpu_util)
    except (TypeError, ValueError):
        gpu_util_f = 0.0
    if gpu_util_f > 85.0:
        l_adj = float(dict(settings.get("load_adjustments", {})).get("gpu_over_85", 0.03))
        threshold += l_adj

    clamp_min = float(settings.get("clamp_min", 0.55))
    clamp_max = float(settings.get("clamp_max", 0.97))
    threshold = min(clamp_max, max(clamp_min, threshold))
    return round(threshold, 4)


def classify_task(
    question: str,
    requested_task_type: str = "auto",
    policy: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    root: Path | None = None,
    quota_state: dict[str, Any] | None = None,
    resource_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = policy or dict(DEFAULT_ROUTING_POLICY)
    requested = str(requested_task_type or "auto").strip().lower()
    if requested not in TASK_TYPES:
        requested = "auto"

    raw = question.strip()
    clean = _normalize_text(raw)
    features = extract_task_features(raw, policy=settings, metadata=metadata, root=root)

    if not clean:
        return {
            "task_type": "simple",
            "requested_task_type": requested,
            "confidence": 0.99,
            "uncertain": False,
            "reasons": ["empty_input_defaults_to_simple"],
            "recommended_route": "local",
            "options": list(settings.get("ask_options", ["local", "codex", "remote2", "both"])),
            "task_features": features,
            "sensitive_similarity": features["sensitive_similarity"],
            "dynamic_threshold": compute_dynamic_threshold(settings, quota_state=quota_state, resource_state=resource_state),
        }

    sensitive_threshold = float(dict(settings.get("sensitive", {})).get("semantic_threshold", 0.82))
    sensitive_hits = list(features.get("sensitive_keyword_hits", []))
    sensitive_similarity = float(features.get("sensitive_similarity", 0.0))
    if requested == "sensitive" or sensitive_hits or sensitive_similarity >= sensitive_threshold:
        reasons = ["sensitive_task_policy"]
        if sensitive_hits:
            reasons.append(f"matched_sensitive_keywords:{','.join(sensitive_hits[:6])}")
        if sensitive_similarity >= sensitive_threshold:
            reasons.append("sensitive_semantic_match")
        return {
            "task_type": "sensitive",
            "requested_task_type": requested,
            "confidence": 0.99,
            "uncertain": False,
            "reasons": reasons,
            "recommended_route": "local",
            "options": list(settings.get("ask_options", ["local", "codex", "remote2", "both"])),
            "task_features": features,
            "sensitive_similarity": round(sensitive_similarity, 4),
            "dynamic_threshold": compute_dynamic_threshold(settings, quota_state=quota_state, resource_state=resource_state),
        }

    if requested in {"simple", "complex"}:
        return {
            "task_type": requested,
            "requested_task_type": requested,
            "confidence": 0.96,
            "uncertain": False,
            "reasons": ["explicit_task_type"],
            "recommended_route": "local" if requested == "simple" else "codex",
            "options": list(settings.get("ask_options", ["local", "codex", "remote2", "both"])),
            "task_features": features,
            "sensitive_similarity": round(sensitive_similarity, 4),
            "dynamic_threshold": compute_dynamic_threshold(settings, quota_state=quota_state, resource_state=resource_state),
        }

    char_count = int(features["char_count"])
    token_count = int(features["token_count"])

    simple_score = 0.34
    complex_score = 0.34
    reasons: list[str] = []

    if char_count <= int(settings.get("simple_max_chars", 240)):
        simple_score += 0.18
        reasons.append("short_request")
    if char_count >= int(settings.get("complex_min_chars", 520)):
        complex_score += 0.22
        reasons.append("long_request")

    if token_count <= 45:
        simple_score += 0.12
    elif token_count >= 120:
        complex_score += 0.14

    if int(features["line_count"]) > 16:
        complex_score += 0.06
    if int(features["url_count"]) > 0:
        complex_score += 0.09
        reasons.append("has_urls")
    if int(features["code_block_count"]) > 0:
        complex_score += 0.13
        reasons.append("has_code_blocks")
    if int(features["attachment_count"]) > 0:
        complex_score += 0.13
        reasons.append("has_attachments")
    if int(features["file_ref_count"]) > 1:
        complex_score += 0.08
        reasons.append("has_file_refs")
    if float(features["command_density"]) >= 0.5:
        complex_score += 0.07
        reasons.append("high_command_density")

    simple_hits = _keyword_hits(clean, list(settings.get("simple_keywords", [])))
    complex_hits = _keyword_hits(clean, list(settings.get("complex_keywords", [])))
    simple_score += min(0.36, 0.08 * len(simple_hits))
    complex_score += min(0.42, 0.09 * len(complex_hits))
    if len(complex_hits) >= 2:
        complex_score += 0.14
        reasons.append("multiple_complex_signals")
    if any(term in clean for term in ("architecture", "migration", "multi-file", "cross-repository", "root cause")):
        complex_score += 0.08

    if simple_hits:
        reasons.append(f"simple_keywords:{','.join(simple_hits[:5])}")
    if complex_hits:
        reasons.append(f"complex_keywords:{','.join(complex_hits[:5])}")

    total = max(0.001, simple_score + complex_score)
    if complex_score > simple_score:
        task_type = "complex"
        top = complex_score
        second = simple_score
        recommended_route = "codex"
    else:
        task_type = "simple"
        top = simple_score
        second = complex_score
        recommended_route = "local"

    diff = max(0.0, top - second)
    confidence = min(0.99, max(0.51, top / total + min(0.2, diff / 2.0)))

    dynamic_threshold = compute_dynamic_threshold(settings, quota_state=quota_state, resource_state=resource_state)
    min_margin = float(settings.get("min_margin", 0.14))
    uncertain = confidence < dynamic_threshold or diff < min_margin
    if uncertain:
        reasons.append("low_routing_confidence")

    return {
        "task_type": task_type,
        "requested_task_type": requested,
        "confidence": round(confidence, 4),
        "uncertain": bool(uncertain),
        "reasons": reasons or ["auto_classification"],
        "recommended_route": recommended_route,
        "options": list(settings.get("ask_options", ["local", "codex", "remote2", "both"])),
        "signals": {
            "token_count": token_count,
            "char_count": char_count,
            "simple_score": round(simple_score, 4),
            "complex_score": round(complex_score, 4),
            "score_margin": round(diff, 4),
        },
        "task_features": features,
        "sensitive_similarity": round(sensitive_similarity, 4),
        "dynamic_threshold": dynamic_threshold,
    }
