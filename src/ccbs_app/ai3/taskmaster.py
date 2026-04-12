"""Continue-style taskmaster for ai3 routing decisions and provider execution."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from ..ai_keyring import resolve_api_key
from .question_routing import simple_fact_answer
from .providers.codex import codex_chat
from .providers.lmstudio import lmstudio_chat
from .providers.ollama import ollama_chat


def _is_online(base_url: str) -> bool:
    try:
        host = base_url.split("://", 1)[-1].split("/", 1)[0]
        if ":" in host:
            name, port_raw = host.split(":", 1)
            port = int(port_raw)
        else:
            name = host
            port = 443 if base_url.startswith("https://") else 80
        with socket.create_connection((name, port), timeout=1.5):
            return True
    except Exception:
        return False


def _extractive_answer(question: str, context: str, *, simple_qa: bool = False) -> str:
    if simple_qa:
        direct = simple_fact_answer(question)
        if direct:
            return direct
    if not context.strip():
        return "No local context found. I am uncertain without indexed evidence."
    lines = [line.strip() for line in context.splitlines() if line.strip()]
    snippets = [line for line in lines if not line.startswith("[")][:5]
    if not snippets:
        snippets = lines[:5]
    return "\n".join(snippets)


def run_taskmaster(
    root: Path,
    question: str,
    context: str,
    offline_only: bool = False,
    simple_qa: bool = False,
    strict_local_models: bool = True,
    allow_extractive_fallback: bool = False,
    local_attempts_max: int = 3,
    preferred_provider: str = "",
    local_base_urls: dict[str, str] | None = None,
    local_models: dict[str, str] | None = None,
    codex_base_url: str = "https://api.openai.com/v1",
    codex_model: str = "gpt-5",
    user_id: str = "default",
    timeout_s: int = 40,
) -> dict[str, Any]:
    bases = dict(local_base_urls or {})
    models = dict(local_models or {})
    chain = ["ollama", "lmstudio"]
    preferred = preferred_provider.strip().lower()
    if preferred in chain:
        chain = [preferred] + [p for p in chain if p != preferred]
    local_chain = chain[: max(1, int(local_attempts_max))]
    prompt = (
        "You are an offline-first assistant. Prefer local evidence and cite where possible.\n\n"
        f"Question:\n{question}\n\nContext:\n{context or '[no context]'}\n"
    )
    route_policy = "simple_qa_fast_path" if bool(simple_qa) else "offline_3_then_online_1"

    attempts: list[dict[str, Any]] = []
    for provider in local_chain:
        text = ""
        try:
            if provider == "ollama":
                text = ollama_chat(
                    base_url=str(bases.get("ollama", "http://127.0.0.1:11434")),
                    model=str(models.get("ollama", "llama3.1:8b")),
                    prompt=prompt,
                    timeout_s=timeout_s,
                )
            elif provider == "lmstudio":
                text = lmstudio_chat(
                    base_url=str(bases.get("lmstudio", "http://127.0.0.1:1234/v1")),
                    model=str(models.get("lmstudio", "local-model")),
                    prompt=prompt,
                    timeout_s=timeout_s,
                )

            if text.strip():
                attempts.append({"provider": provider, "ok": True})
                return {
                    "ok": True,
                    "failure_code": "",
                    "next_steps": [],
                    "answer": text.strip(),
                    "provider_used": provider,
                    "attempts": attempts,
                    "online_prompt_required": False,
                    "route_policy": route_policy,
                }
            attempts.append({"provider": provider, "ok": False, "error": "empty_response"})
        except Exception as exc:  # noqa: BLE001
            attempts.append({"provider": provider, "ok": False, "error": str(exc)[:240]})

    if bool(simple_qa):
        quick = simple_fact_answer(question)
        if quick:
            attempts.append({"provider": "builtin_simple_qa", "ok": True, "reason": "deterministic_fact_fallback"})
            return {
                "ok": True,
                "failure_code": "",
                "next_steps": [],
                "answer": quick,
                "provider_used": "builtin_simple_qa",
                "attempts": attempts,
                "online_prompt_required": False,
                "route_policy": route_policy,
            }

    if bool(allow_extractive_fallback):
        text = _extractive_answer(question=question, context=context, simple_qa=bool(simple_qa)).strip()
        attempts.append({"provider": "extractive", "ok": True, "reason": "explicit_fallback"})
        return {
            "ok": True,
            "failure_code": "",
            "next_steps": [],
            "answer": text,
            "provider_used": "extractive",
            "attempts": attempts,
            "online_prompt_required": False,
            "route_policy": route_policy,
        }

    if offline_only:
        strict_hint = (
            "Strict local-model mode is enabled; extractive fallback is disabled."
            if bool(strict_local_models)
            else "Local model attempts failed."
        )
        return {
            "ok": False,
            "failure_code": "LOCAL_MODELS_UNAVAILABLE",
            "next_steps": [
                "Start Ollama or LM Studio local server.",
                "Retry with allow_extractive_fallback=true if you accept non-model extractive output.",
                "Disable offline-only and allow remote escalation if policy permits.",
            ],
            "answer": (
                f"{strict_hint} Offline-only workflow exhausted local attempts."
            ),
            "provider_used": "offline_only",
            "attempts": attempts,
            "online_prompt_required": True,
            "route_policy": route_policy,
        }

    api_key = resolve_api_key(root=root, provider_id="codex", user_id=user_id)
    if not api_key.strip() or not _is_online(codex_base_url):
        return {
            "ok": False,
            "failure_code": "REMOTE_UNAVAILABLE",
            "next_steps": [
                "Configure/verify Codex API key.",
                "Ensure remote base URL is reachable.",
                "Retry with offline_only=true once local models are online.",
            ],
            "answer": "Local attempts failed and remote Codex is not reachable/configured.",
            "provider_used": "none",
            "attempts": attempts,
            "online_prompt_required": False,
            "route_policy": route_policy,
        }

    try:
        remote = codex_chat(
            api_key=api_key,
            base_url=codex_base_url,
            model=codex_model,
            prompt=prompt,
            timeout_s=timeout_s,
        )
        attempts.append({"provider": "codex", "ok": True})
        return {
            "ok": True,
            "failure_code": "",
            "next_steps": [],
            "answer": remote.strip(),
            "provider_used": "codex",
            "attempts": attempts,
            "online_prompt_required": False,
            "route_policy": route_policy,
        }
    except Exception as exc:  # noqa: BLE001
        attempts.append({"provider": "codex", "ok": False, "error": str(exc)[:240]})
        return {
            "ok": False,
            "failure_code": "REMOTE_FAILED",
            "next_steps": [
                "Check remote model health and credentials.",
                "Retry once remote service is healthy.",
            ],
            "answer": "Local and remote attempts failed.",
            "provider_used": "none",
            "attempts": attempts,
            "online_prompt_required": False,
            "route_policy": route_policy,
        }
