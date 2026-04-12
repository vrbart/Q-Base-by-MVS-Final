"""Codex-facing integration layer around the CCBS AI runtime."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request as FastAPIRequest
else:
    FastAPIRequest = Any

from .ai_api import ApiDependencyError, _require_fastapi, create_app
from .ai_audit import log_event
from .ai_auth import resolve_owner_auto_auth_user, verify_token
from .ai_hybrid import run_hybrid_answer
from .ai_models import list_models
from .ai_routing_policy import load_routing_policy
from .ai3.compat_v1 import run_v1_chat_completion


DEFAULT_CODEX_BRIDGE_HOST = "127.0.0.1"
DEFAULT_CODEX_BRIDGE_PORT = 11436


def _extract_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    auth = authorization.strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _client_host(request: Any) -> str:
    client = getattr(request, "client", None)
    if client is None:
        return ""
    return str(getattr(client, "host", "") or "")


def _safe_base_url(host: str, port: int) -> str:
    clean_host = str(host or DEFAULT_CODEX_BRIDGE_HOST).strip() or DEFAULT_CODEX_BRIDGE_HOST
    if clean_host in {"0.0.0.0", "::"}:
        clean_host = DEFAULT_CODEX_BRIDGE_HOST
    return f"http://{clean_host}:{max(1, int(port))}"


def _default_local_provider(root: Path) -> str:
    policy = load_routing_policy(root)
    provider = str(policy.get("default_local_provider", "ollama")).strip().lower()
    if provider in {"ollama", "lmstudio", "extractive"}:
        return provider
    return "ollama"


def _continue_codex_bridge_binding() -> dict[str, Any]:
    return {
        "client_id": "continue",
        "config_path": ".continue/config.json",
        "template_path": "config/continue.config.template.json",
        "model_title": "CCBS Codex Bridge",
        "provider": "openai",
        "api_base": _safe_base_url(DEFAULT_CODEX_BRIDGE_HOST, DEFAULT_CODEX_BRIDGE_PORT) + "/v1",
        "api_key_env": "CCBS_API_BEARER_TOKEN",
    }


def _codex_vscode_task_bindings() -> dict[str, Any]:
    return {
        "bridge_bootstrap_task_label": "Ops Core: AI Codex Bridge Bootstrap [Win]",
        "bridge_status_task_label": "Ops Core: AI Codex Bridge Status [Win]",
        "mcp_profile_task_label": "Ops Core: AI Codex MCP Profile [Win]",
        "bridge_serve_task_label": "Ops Core: AI Codex Bridge Serve [Win]",
        "task_hub_ids": {
            "bridge_bootstrap": "ai.codex.bridge.bootstrap",
            "bridge_status": "ai.codex.bridge.status",
            "mcp_profile": "ai.codex.bridge.mcp_profile",
            "bridge_serve": "ai.codex.bridge.serve",
        },
    }


def codex_mcp_profile(root: Path) -> dict[str, Any]:
    policy = load_routing_policy(root)
    return {
        "profile_id": "ccbs-codex-default",
        "version": "ccbs-codex-mcp-profile-v2",
        "description": "Codex-facing MCP tool profile for the CCBS runtime. Read-oriented tools are allowed by default; mutating and shell tools stay approval-gated.",
        "client_binding": {
            **_continue_codex_bridge_binding(),
            "adapter_template_path": "config/codex_adapter.template.json",
        },
        "route_policy": {
            "active_profile": str(policy.get("active_profile", "laptop")),
            "default_local_provider": str(policy.get("default_local_provider", "ollama")),
            "default_codex_model": str(policy.get("default_codex_model", "gpt-5")),
        },
        "servers": [
            {
                "server_id": "mcp_fs",
                "name": "filesystem",
                "endpoint": "stdio://filesystem",
                "purpose": "Repo and config reads for Codex workflows.",
                "tools": [
                    {"tool_name": "filesystem.read_file", "mode": "allow", "risk_level": "low"},
                    {"tool_name": "filesystem.write_file", "mode": "approval_required", "risk_level": "high"},
                ],
            },
            {
                "server_id": "mcp_zip",
                "name": "zip_vault",
                "endpoint": "stdio://zip_vault",
                "purpose": "Read evidence bundles and archived source artifacts.",
                "tools": [
                    {"tool_name": "zip_vault.list_entries", "mode": "allow", "risk_level": "medium"},
                    {"tool_name": "zip_vault.read_entry", "mode": "allow", "risk_level": "medium"},
                ],
            },
            {
                "server_id": "mcp_shell",
                "name": "shell",
                "endpoint": "stdio://shell",
                "purpose": "Explicit shell execution only after human approval.",
                "tools": [
                    {"tool_name": "shell.exec", "mode": "approval_required", "risk_level": "high"},
                ],
            },
        ],
        "notes": [
            "Keep one host agent service with many callers.",
            "Prefer repo reads and retrieval before shell execution.",
            "Do not let Codex mutate the repo or run shell commands without approval.",
        ],
    }


def codex_bridge_status(root: Path, host: str = DEFAULT_CODEX_BRIDGE_HOST, port: int = DEFAULT_CODEX_BRIDGE_PORT) -> dict[str, Any]:
    policy = load_routing_policy(root)
    base_url = _safe_base_url(host, port)
    continue_binding = _continue_codex_bridge_binding()
    return {
        "bridge": {
            "service": "ccbs-codex-bridge",
            "base_url": base_url,
            "chat_completions_url": f"{base_url}/v1/chat/completions",
            "models_url": f"{base_url}/v1/models",
            "health_url": f"{base_url}/health",
            "runtime_url": f"{base_url}/v1/codex/runtime",
            "mcp_profile_url": f"{base_url}/v1/codex/mcp-profile",
            "full_api_mount_url": f"{base_url}/ccbs",
        },
        "auth": {
            "mode": "bearer-or-loopback-owner-auto-auth",
            "api_key_env": "CCBS_API_BEARER_TOKEN",
            "loopback_owner_auto_auth_only": True,
        },
        "defaults": {
            "use_ai3": True,
            "allow_remote": True,
            "provider": "auto",
            "codex_model": str(policy.get("default_codex_model", "gpt-5")),
            "default_local_provider": str(policy.get("default_local_provider", "ollama")),
        },
        "route_policy": {
            "active_profile": str(policy.get("active_profile", "laptop")),
            "decision_engine": dict(policy.get("decision_engine", {})),
            "ask_options": list(policy.get("ask_options", [])),
        },
        "mcp_profile": codex_mcp_profile(root),
        "config_surface": {
            "adapter_template": "config/codex_adapter.template.json",
            "mcp_profile_template": "config/codex_mcp_profile.template.json",
            "continue_config": continue_binding["config_path"],
            "continue_template": continue_binding["template_path"],
        },
        "client_bindings": {
            "continue": continue_binding,
        },
        "vscode_tasks": _codex_vscode_task_bindings(),
        "docs": {
            "integration_doc": "docs/CCBS_CODEX_INTEGRATION_LAYER.md",
            "skill_builder_brief": "docs/CCBS_CODEX_SKILL_BUILDER_BRIEF.md",
            "skill_file": ".github/skills/ccbs-local-first-agent-runtime/SKILL.md",
        },
    }


def _run_codex_bridge_completion(root: Path, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    body = dict(payload)
    body.setdefault("use_ai3", True)
    body.setdefault("allow_remote", True)
    body.setdefault("provider", "auto")

    metadata = body.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata = dict(metadata)
    metadata.setdefault("integration_surface", "codex_bridge")
    metadata.setdefault("integration_runtime", "ccbs-codex-bridge")
    body["metadata"] = metadata

    if bool(body.get("use_ai3", True)):
        try:
            response = run_v1_chat_completion(root=root, payload=body, user=user)
            log_event(
                root=root,
                event_type="codex_bridge_chat_completion",
                actor=str(user.get("username", "api-user")),
                details={
                    "provider": str(response.get("model", "")),
                    "run_id": str(response.get("run_id", "")),
                    "thread_id": str(response.get("thread_id", "")),
                    "integration": "codex_bridge",
                },
            )
            return response
        except ValueError:
            raise
        except Exception:
            pass

    messages = body.get("messages", [])
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages list is required")

    question = ""
    for msg in messages[::-1]:
        if isinstance(msg, dict) and str(msg.get("role", "")) == "user":
            question = str(msg.get("content", "")).strip()
            break
    if not question:
        raise ValueError("last user message content required")

    top_k = int(body.get("top_k", 5))
    provider = str(body.get("provider", "auto")).strip().lower()
    model_id = str(body.get("model", "")).strip()
    metadata = body.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    user_id = str(metadata.get("user_id", user.get("username", "api-user"))).strip() or str(user.get("username", "api-user"))
    task_type = str(metadata.get("task_type_override", "auto")).strip().lower()
    allow_remote = bool(body.get("allow_remote", True))
    use_codex = allow_remote and provider not in {"extractive", "ollama", "local", "lmstudio"}
    force_local = provider in {"extractive", "ollama", "local", "lmstudio"}
    local_provider = provider if provider in {"extractive", "ollama", "lmstudio"} else _default_local_provider(root)

    hybrid = run_hybrid_answer(
        root=root,
        question=question,
        top_k=max(1, top_k),
        use_codex=use_codex,
        force_local=force_local,
        codex_model=model_id or str(load_routing_policy(root).get("default_codex_model", "gpt-5")),
        codex_base_url=str(body.get("base_url", "https://api.openai.com/v1")),
        timeout_s=max(1, int(body.get("timeout_s", 40))),
        local_provider=local_provider,
        local_model_id=model_id if force_local else "",
        user_id=user_id,
        metadata={**metadata, "task_type_override": task_type, "integration_surface": "codex_bridge"},
    )

    log_event(
        root=root,
        event_type="codex_bridge_chat_completion",
        actor=str(user.get("username", "api-user")),
        details={
            "provider": hybrid.provider_used,
            "model": hybrid.model_used,
            "route_chain": hybrid.route_chain,
            "integration": "codex_bridge",
        },
    )

    return {
        "id": "chatcmpl-ccbs-codex-bridge",
        "object": "chat.completion",
        "model": hybrid.model_used or model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": hybrid.answer},
                "finish_reason": "stop",
            }
        ],
        "citations": hybrid.citations,
        "route_chain": hybrid.route_chain,
        "provider_attempts": hybrid.provider_attempts,
        "dynamic_threshold": hybrid.dynamic_threshold,
        "quota_state": hybrid.quota_state,
        "resource_state": hybrid.resource_state,
        "task_features": hybrid.task_features,
        "sensitive_similarity": hybrid.sensitive_similarity,
        "user_override_applied": hybrid.user_override_applied,
    }


def create_codex_bridge_app(root: Path):
    FastAPI, Depends, Header, HTTPException, JSONResponse, _HTMLResponse, Request = _require_fastapi()
    globals()["FastAPIRequest"] = Request
    app = FastAPI(title="CCBS Codex Bridge", version="1.0.0")

    def require_user(request: FastAPIRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        token = _extract_token(authorization)
        if token:
            try:
                return verify_token(root=root, token=token, require_admin=False)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=401, detail=f"unauthorized: {exc}") from exc
        auto_user = resolve_owner_auto_auth_user(root=root, client_host=_client_host(request))
        if auto_user is not None:
            return auto_user
        raise HTTPException(status_code=401, detail="missing bearer token")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "ccbs-codex-bridge",
            "full_api_mount": "/ccbs",
        }

    @app.get("/v1/models")
    def v1_models(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        return {"object": "list", "data": list_models(root)}

    @app.get("/v1/codex/runtime")
    def v1_codex_runtime(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        return {
            **codex_bridge_status(root=root),
            "profile_scope": str(user.get("username", "default")),
        }

    @app.get("/v1/codex/mcp-profile")
    def v1_codex_mcp_profile(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        return {
            "profile_scope": str(user.get("username", "default")),
            "profile": codex_mcp_profile(root),
        }

    @app.post("/v1/chat/completions")
    def v1_chat_completions(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        try:
            return _run_codex_bridge_completion(root=root, payload=payload, user=user)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    app.mount("/ccbs", create_app(root))
    return app


def serve_codex_bridge(root: Path, host: str = DEFAULT_CODEX_BRIDGE_HOST, port: int = DEFAULT_CODEX_BRIDGE_PORT) -> None:
    try:
        import uvicorn
    except Exception as exc:  # noqa: BLE001
        raise ApiDependencyError("uvicorn is not installed. Install dependencies: pip install uvicorn") from exc

    app = create_codex_bridge_app(root)
    uvicorn.run(app, host=host, port=max(1, int(port)), log_level="info")