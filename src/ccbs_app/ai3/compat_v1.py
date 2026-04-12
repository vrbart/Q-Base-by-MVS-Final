"""Compatibility shim: map /v1/chat/completions onto ai3 threads/runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .db import connect_runtime
from .mcp.registry import seed_mcp_registry
from .orchestrator import create_message, create_run, create_thread, ensure_endpoint, execute_run


def _extract_question(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "")).strip().lower()
        if role != "user":
            continue
        content = str(msg.get("content", "")).strip()
        if content:
            return content
    return ""


def _normalized_messages(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        if role not in {"user", "assistant", "system", "tool"}:
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        out.append({"role": role, "content": content})
    return out


def run_v1_chat_completion(root: Path, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    messages = _normalized_messages(payload.get("messages", []))
    if not messages:
        raise ValueError("messages list is required")
    question = _extract_question(messages)
    if not question:
        raise ValueError("last user message content required")

    provider = str(payload.get("provider", "auto")).strip().lower()
    model_id = str(payload.get("model", "")).strip()

    use_remote = bool(payload.get("allow_remote", False)) and provider not in {"extractive", "ollama", "lmstudio", "local"}
    endpoint_provider = "ollama"
    if provider == "lmstudio":
        endpoint_provider = "lmstudio"

    conn = connect_runtime(root)
    seed_mcp_registry(conn)
    try:
        endpoint_id = ensure_endpoint(
            conn,
            provider=endpoint_provider,
            base_url=str(payload.get("base_url", "")),
            chat_model=model_id,
        )

        thread = create_thread(
            conn,
            title="/v1 chat completion",
            tags=["compat", "v1"],
            metadata={"compatibility": "v1/chat/completions"},
        )

        for msg in messages:
            create_message(conn, thread_id=thread["thread_id"], role=str(msg["role"]), content=str(msg["content"]))

        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = dict(metadata)
        metadata.setdefault("question", question)
        metadata.setdefault("top_k", int(payload.get("top_k", 5)))
        metadata.setdefault("timeout_s", int(payload.get("timeout_s", 40)))
        metadata.setdefault("user_id", str(metadata.get("user_id", user.get("username", "api-user"))))
        metadata.setdefault("codex_model", model_id or str(payload.get("codex_model", "gpt-5")))
        metadata.setdefault(
            "codex_base_url",
            str(payload.get("codex_base_url", payload.get("base_url", "https://api.openai.com/v1"))),
        )
        metadata.setdefault("offline_only", bool(payload.get("offline_only", False)))
        metadata.setdefault("local_attempts_max", int(payload.get("local_attempts_max", 3)))
        metadata.setdefault("compat_mode", "v1")

        run = create_run(conn, thread_id=str(thread["thread_id"]), endpoint_id=endpoint_id, metadata=metadata)
        result = execute_run(
            root=root,
            conn=conn,
            run_id=str(run["run_id"]),
            actor=str(user.get("username", "api-user")),
            allow_remote=use_remote,
        )

        run_row = result.get("run", run)
        taskmaster = result.get("taskmaster", {}) if isinstance(result.get("taskmaster", {}), dict) else {}
        answer = str(taskmaster.get("answer", "")).strip()
        if not answer:
            assistant_msg = result.get("assistant_message", {})
            if isinstance(assistant_msg, dict):
                answer = str(assistant_msg.get("content", "")).strip()

        steps = result.get("steps", [])
        route_chain: list[str] = []
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    route_chain.append(str(step.get("step_type", "")))

        response = {
            "id": str(run_row.get("run_id", "chatcmpl-local")),
            "object": "chat.completion",
            "model": model_id or str(taskmaster.get("provider_used", endpoint_provider)),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
            "citations": result.get("citations", []),
            "route_chain": route_chain,
            "provider_attempts": taskmaster.get("attempts", []),
            "dynamic_threshold": None,
            "quota_state": None,
            "resource_state": None,
            "task_features": {},
            "sensitive_similarity": 0.0,
            "user_override_applied": False,
            "thread_id": thread["thread_id"],
            "run_id": run_row.get("run_id", ""),
        }
        return response
    finally:
        conn.close()
