"""Hybrid online/offline answer routing with dynamic policy and fallback tiers."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ai_audit import log_event as ai_log_event
from .ai_index2 import answer_query, search_index
from .ai_keyring import resolve_api_key
from .ai_perf import runtime_resource_state
from .ai_quota import apply_usage, estimate_tokens, quota_summary
from .ai_router_state import provider_available, provider_state, record_provider_result
from .ai_routing_policy import load_routing_policy


@dataclass(frozen=True)
class HybridResult:
    question: str
    answer: str
    provider_used: str
    model_used: str
    codex_attempted: bool
    online: bool
    fallback_reason: str
    citations: list[dict[str, Any]]
    route_chain: list[str] = field(default_factory=list)
    provider_attempts: list[dict[str, Any]] = field(default_factory=list)
    dynamic_threshold: float = 0.68
    quota_state: dict[str, Any] = field(default_factory=dict)
    resource_state: dict[str, Any] = field(default_factory=dict)
    task_features: dict[str, Any] = field(default_factory=dict)
    sensitive_similarity: float = 0.0
    user_override_applied: bool = False


def _is_online_for_url(base_url: str, timeout_s: float = 2.5) -> bool:
    try:
        parsed = urllib.parse.urlparse(base_url)
        host = parsed.hostname
        if not host:
            return False
        port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
        with socket.create_connection((host, port), timeout=max(0.5, float(timeout_s))):
            return True
    except OSError:
        return False


def _remote_chat_completion(
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    timeout_s: int = 40,
) -> str:
    base = base_url.rstrip("/")
    if not base.endswith("/chat/completions"):
        if base.endswith("/v1"):
            url = f"{base}/chat/completions"
        else:
            url = f"{base}/v1/chat/completions"
    else:
        url = base

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a coding and operations assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    with urllib.request.urlopen(req, timeout=max(3, int(timeout_s))) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))

    choices = payload.get("choices", []) if isinstance(payload, dict) else []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message", {})
        if isinstance(msg, dict):
            content = str(msg.get("content", "")).strip()
            if content:
                return content

    if isinstance(payload, dict) and "output_text" in payload:
        text = str(payload.get("output_text", "")).strip()
        if text:
            return text

    raise RuntimeError("remote response missing completion text")


def _build_context(root: Path, question: str, top_k: int) -> tuple[str, list[dict[str, Any]]]:
    hits = search_index(root=root, question=question, top_k=max(1, int(top_k)))
    lines: list[str] = []
    citations: list[dict[str, Any]] = []
    for idx, hit in enumerate(hits, 1):
        lines.append(f"[{idx}] {hit.path}#chunk{hit.chunk_id}")
        lines.append(hit.content)
        lines.append("")
        citations.append(
            {
                "path": hit.path,
                "source_id": hit.source_id,
                "chunk_id": hit.chunk_id,
                "score": hit.score,
                "lexical_score": hit.lexical_score,
                "vector_score": hit.vector_score,
            }
        )
    return "\n".join(lines).strip(), citations


def _provider_config(
    provider_id: str,
    policy: dict[str, Any],
    codex_model: str,
    codex_base_url: str,
) -> dict[str, Any]:
    pid = provider_id.strip().lower()
    remotes = [row for row in list(policy.get("remote_providers", [])) if isinstance(row, dict)]
    row = next((item for item in remotes if str(item.get("provider_id", "")).strip().lower() == pid), {})

    if pid == "codex":
        base_env = str(row.get("base_url_env", "OPENAI_BASE_URL") or "OPENAI_BASE_URL")
        key_ref = str(row.get("api_key_ref", "OPENAI_API_KEY") or "OPENAI_API_KEY")
        return {
            "provider_id": "codex",
            "enabled": bool(row.get("enabled", True)),
            "model": codex_model or str(row.get("model", "gpt-5")),
            "base_url": codex_base_url or os.environ.get(base_env, "https://api.openai.com/v1"),
            "api_key_ref": key_ref,
        }

    base_env = str(row.get("base_url_env", "OPENAI_BASE_URL_REMOTE2") or "OPENAI_BASE_URL_REMOTE2")
    key_ref = str(row.get("api_key_ref", "OPENAI_API_KEY_REMOTE2") or "OPENAI_API_KEY_REMOTE2")
    return {
        "provider_id": pid,
        "enabled": bool(row.get("enabled", False)),
        "model": str(row.get("model", "gpt-5-mini") or "gpt-5-mini"),
        "base_url": os.environ.get(base_env, "https://api.openai.com/v1"),
        "api_key_ref": key_ref,
    }


def _effective_quota(root: Path, incoming_quota_state: dict[str, Any] | None = None) -> dict[str, Any]:
    if incoming_quota_state and isinstance(incoming_quota_state, dict):
        return dict(incoming_quota_state)
    return quota_summary(root)


def run_hybrid_answer(
    root: Path,
    question: str,
    top_k: int = 5,
    use_codex: bool = True,
    force_local: bool = False,
    codex_model: str = "gpt-5",
    codex_base_url: str = "https://api.openai.com/v1",
    timeout_s: int = 40,
    local_provider: str = "extractive",
    local_model_id: str = "",
    local_reason: str = "",
    route_chain: list[str] | None = None,
    policy: dict[str, Any] | None = None,
    user_id: str = "local_user",
    metadata: dict[str, Any] | None = None,
    dynamic_threshold: float = 0.68,
    task_features: dict[str, Any] | None = None,
    sensitive_similarity: float = 0.0,
    quota_state: dict[str, Any] | None = None,
    resource_state: dict[str, Any] | None = None,
    user_override_applied: bool = False,
) -> HybridResult:
    del metadata
    q = question.strip()
    if not q:
        raise ValueError("question is required")

    policy_obj = policy if isinstance(policy, dict) else load_routing_policy(root)

    context, citations = _build_context(root=root, question=q, top_k=top_k)
    prompt = (
        "Answer using context when available. If uncertain, say uncertain and cite [n].\n\n"
        f"Question:\n{q}\n\n"
        f"Context:\n{context or '[no indexed context]'}\n"
    )

    codex_attempted = False
    fallback_reason = ""
    online = _is_online_for_url(codex_base_url)
    attempts: list[dict[str, Any]] = []
    route_taken: list[str] = []

    quota = _effective_quota(root, incoming_quota_state=quota_state)
    resources = dict(resource_state or runtime_resource_state())
    request_id = str(uuid.uuid4())
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    configured_chain = route_chain if isinstance(route_chain, list) and route_chain else ["codex", "remote2"]
    remote_chain = [str(item).strip().lower() for item in configured_chain if str(item).strip().lower() in {"codex", "remote2"}]

    if force_local or not use_codex:
        remote_chain = []

    cbreak_cfg = dict(policy_obj.get("circuit_breaker", {}))
    failures_to_open = max(1, int(cbreak_cfg.get("failures_to_open", 3)))
    cooldown_s_cfg = max(1, int(cbreak_cfg.get("cooldown_s", 60)))
    max_cooldown_s = max(cooldown_s_cfg, int(cbreak_cfg.get("max_cooldown_s", 600)))

    if remote_chain:
        for provider_id in remote_chain:
            cfg = _provider_config(provider_id, policy_obj, codex_model=codex_model, codex_base_url=codex_base_url)
            pid = str(cfg.get("provider_id", provider_id))
            route_taken.append(pid)
            if pid == "codex":
                codex_attempted = True

            if not bool(cfg.get("enabled", False)):
                attempts.append({"provider_id": pid, "status": "skipped", "reason": "provider_disabled"})
                continue

            if not provider_available(root, pid):
                state = provider_state(root, pid)
                attempts.append(
                    {
                        "provider_id": pid,
                        "status": "skipped",
                        "reason": "circuit_open",
                        "open_until": state.get("open_until", ""),
                    }
                )
                continue

            base_url = str(cfg.get("base_url", "")).strip()
            model = str(cfg.get("model", "")).strip() or codex_model
            if not base_url:
                attempts.append({"provider_id": pid, "status": "skipped", "reason": "missing_base_url"})
                continue

            if not _is_online_for_url(base_url, timeout_s=min(3.0, float(timeout_s))):
                attempts.append({"provider_id": pid, "status": "failed", "reason": "offline"})
                record_provider_result(
                    root=root,
                    provider_id=pid,
                    ok=False,
                    failures_to_open=failures_to_open,
                    cooldown_s=cooldown_s_cfg,
                    max_cooldown_s=max_cooldown_s,
                    error="offline",
                )
                continue

            api_key = resolve_api_key(root=root, provider_id=pid, user_id=user_id)
            if not api_key:
                attempts.append({"provider_id": pid, "status": "skipped", "reason": "missing_api_key"})
                continue

            t0 = time.perf_counter()
            ai_log_event(
                root=root,
                event_type="remote_call_attempt",
                actor=user_id,
                details={
                    "request_id": request_id,
                    "provider_id": pid,
                    "model": model,
                    "prompt_hash": prompt_hash,
                },
            )
            try:
                text = _remote_chat_completion(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    prompt=prompt,
                    timeout_s=timeout_s,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                token_est = estimate_tokens(prompt, text)
                apply_usage(root=root, used_tokens=token_est, used_cost_usd=max(0.0, token_est * 0.000002))
                quota = quota_summary(root)
                record_provider_result(
                    root=root,
                    provider_id=pid,
                    ok=True,
                    failures_to_open=failures_to_open,
                    cooldown_s=cooldown_s_cfg,
                    max_cooldown_s=max_cooldown_s,
                )
                attempts.append({"provider_id": pid, "status": "ok", "latency_ms": latency_ms})
                ai_log_event(
                    root=root,
                    event_type="remote_call_result",
                    actor=user_id,
                    details={
                        "request_id": request_id,
                        "provider_id": pid,
                        "model": model,
                        "latency_ms": latency_ms,
                        "outcome": "success",
                        "token_estimate": token_est,
                        "prompt_hash": prompt_hash,
                    },
                )
                return HybridResult(
                    question=q,
                    answer=text,
                    provider_used=pid,
                    model_used=model,
                    codex_attempted=codex_attempted,
                    online=True,
                    fallback_reason="",
                    citations=citations,
                    route_chain=route_taken,
                    provider_attempts=attempts,
                    dynamic_threshold=float(dynamic_threshold),
                    quota_state=quota,
                    resource_state=resources,
                    task_features=dict(task_features or {}),
                    sensitive_similarity=float(sensitive_similarity),
                    user_override_applied=bool(user_override_applied),
                )
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError, ValueError) as exc:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                err = str(exc)
                attempts.append({"provider_id": pid, "status": "failed", "reason": err[:240], "latency_ms": latency_ms})
                record_provider_result(
                    root=root,
                    provider_id=pid,
                    ok=False,
                    failures_to_open=failures_to_open,
                    cooldown_s=cooldown_s_cfg,
                    max_cooldown_s=max_cooldown_s,
                    error=err,
                )
                ai_log_event(
                    root=root,
                    event_type="remote_call_result",
                    actor=user_id,
                    details={
                        "request_id": request_id,
                        "provider_id": pid,
                        "model": model,
                        "latency_ms": latency_ms,
                        "outcome": "failed",
                        "error": err[:240],
                        "prompt_hash": prompt_hash,
                    },
                )
                fallback_reason = f"{pid}_failed:{err}"

    if local_reason.strip():
        fallback_reason = local_reason.strip()
    elif force_local:
        fallback_reason = "forced_local"
    elif not use_codex:
        fallback_reason = "codex_disabled"
    elif attempts and not fallback_reason:
        fallback_reason = "all_remote_providers_failed"

    route_taken.append("local")

    local = answer_query(
        root=root,
        question=q,
        top_k=max(1, int(top_k)),
        task="general",
        model_id=local_model_id,
        provider=local_provider,
    )
    return HybridResult(
        question=q,
        answer=str(local.get("answer", "")),
        provider_used=str(local.get("provider", "extractive")),
        model_used=str(local.get("model", local_model_id or "extractive")),
        codex_attempted=codex_attempted,
        online=online,
        fallback_reason=fallback_reason,
        citations=list(local.get("citations", citations)),
        route_chain=route_taken,
        provider_attempts=attempts,
        dynamic_threshold=float(dynamic_threshold),
        quota_state=quota,
        resource_state=resources,
        task_features=dict(task_features or {}),
        sensitive_similarity=float(sensitive_similarity),
        user_override_applied=bool(user_override_applied),
    )
