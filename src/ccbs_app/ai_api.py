"""Local API server (OpenAI-compatible + admin endpoints) for ai2."""

from __future__ import annotations

import base64
import binascii
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request as FastAPIRequest
else:
    FastAPIRequest = Any

from .ai_audit import list_events, log_event
from .ai3.api_v3 import register_v3_routes
from .ai3.card_pack import discover_assets_dir
from .ai3.chat_ui import render_chat_ui_html
from .ai3.foundry_pane import render_foundry_pane_html
from .ai3.multi_instance_ui import render_multi_instance_ui_html
from .ai3.compat_v1 import run_v1_chat_completion
from .ai3.gui import render_ai3_gui_html
from .ai_auth import resolve_owner_auto_auth_user, verify_token
from .ai_hybrid import run_hybrid_answer
from .ai_index2 import answer_query, embedding_for_text, index_stats
from .ai_models import list_models
from .ai_perf import runtime_resource_state, summarize_perf_metrics
from .ai_plugins import list_plugins
from .ai_quota import quota_summary, set_quota_budgets
from .ai_router_state import load_router_state
from .ai_routing_policy import load_routing_policy
from .ai_sources import list_sources
from .ai_storage import usage_report, verify_storage
from .ai_workspaces import list_workspaces


class ApiDependencyError(RuntimeError):
    """Raised when FastAPI/uvicorn dependencies are unavailable."""


def _require_fastapi() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException, Request
        from fastapi.responses import HTMLResponse, JSONResponse
    except Exception as exc:  # noqa: BLE001
        raise ApiDependencyError(
            "FastAPI is not installed. Install dependencies: pip install fastapi uvicorn"
        ) from exc
    return FastAPI, Depends, Header, HTTPException, JSONResponse, HTMLResponse, Request


def create_app(root: Path):
    FastAPI, Depends, Header, HTTPException, JSONResponse, HTMLResponse, Request = _require_fastapi()
    # FastAPI resolves forward-referenced annotations from module globals.
    globals()["FastAPIRequest"] = Request

    app = FastAPI(title="CCBS Offline AI API", version="1.0.0")
    role_id_pattern = re.compile(r"^[a-z0-9_]{2,40}$")
    variant_pattern = re.compile(r"^[a-z0-9_]{1,12}$")

    try:
        from fastapi.staticfiles import StaticFiles

        assets_dir = discover_assets_dir(root) or (root / "assets")
        if assets_dir.exists() and assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    except Exception:
        pass

    def _assets_dir() -> Path:
        base = discover_assets_dir(root) or (root / "assets")
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _smiles_user_dir() -> Path:
        out = _assets_dir() / "ai3" / "cards" / "user"
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _smiles_sheet_dir() -> Path:
        out = _smiles_user_dir() / "sheets"
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _decode_image_data_url(raw: str) -> tuple[str, bytes]:
        value = str(raw or "").strip()
        if not value.startswith("data:image/") or "," not in value:
            raise HTTPException(status_code=400, detail="invalid image_data_url")
        header, encoded = value.split(",", 1)
        mime = header.split(";")[0].removeprefix("data:")
        try:
            blob = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid base64 image payload: {exc}") from exc
        if not blob:
            raise HTTPException(status_code=400, detail="empty image payload")
        if len(blob) > 16 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="image payload too large")
        return mime, blob

    def _safe_slug(value: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("._-")
        return clean[:80] or "sheet"

    _level_aliases: dict[str, str] = {
        "l0": "l0",
        "s0": "l0",
        "sketch": "l0",
        "sketch_1": "l0",
        "scribble1": "l0",
        "scribble_1": "l0",
        "stage0": "l0",
        "l1": "l1",
        "s1": "l1",
        "sketch_2": "l1",
        "scribble2": "l1",
        "scribble_2": "l1",
        "stage1": "l1",
        "l2": "a",
        "s2": "a",
        "a": "a",
        "base": "a",
        "stage2": "a",
        "l3": "b",
        "s3": "b",
        "b": "b",
        "evolved": "b",
        "stage3": "b",
        "l4": "c",
        "s4": "c",
        "c": "c",
        "elite": "c",
        "stage4": "c",
        "l5": "d",
        "s5": "d",
        "d": "d",
        "rare": "d",
        "stage5": "d",
        "l6": "e",
        "s6": "e",
        "e": "e",
        "mythic": "e",
        "legend": "e",
        "stage6": "e",
    }

    def _normalize_level_token(raw: str) -> str:
        token = str(raw or "").strip().lower()
        return _level_aliases.get(token, "")

    def _all_level_tokens() -> list[str]:
        return ["l0", "l1", "a", "b", "c", "d", "e"]

    def _pool_dir() -> Path:
        out = _smiles_user_dir() / "pool"
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _git_head_short() -> str:
        try:
            git_dir = root / ".git"
            head_path = git_dir / "HEAD"
            head = head_path.read_text(encoding="utf-8").strip()
            if head.startswith("ref: "):
                ref = head.split(" ", 1)[1].strip()
                ref_path = git_dir / ref
                if ref_path.exists():
                    return ref_path.read_text(encoding="utf-8").strip()[:8]
            return head[:8]
        except Exception:
            return "unknown"

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

    def require_admin(request: FastAPIRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        token = _extract_token(authorization)
        if token:
            try:
                return verify_token(root=root, token=token, require_admin=True)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=403, detail=f"forbidden: {exc}") from exc
        auto_user = resolve_owner_auto_auth_user(root=root, client_host=_client_host(request))
        if auto_user is None:
            raise HTTPException(status_code=401, detail="missing bearer token")
        if str(auto_user.get("role", "")) != "admin":
            raise HTTPException(status_code=403, detail="forbidden: admin role required")
        return auto_user

    register_v3_routes(app=app, root=root, Depends=Depends, HTTPException=HTTPException, require_user=require_user)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "ccbs-offline-ai-api"}

    @app.get("/v3/runtime-info")
    def v3_runtime_info() -> dict[str, Any]:
        return {
            "repo_root": str(root.resolve()),
            "git_head": _git_head_short(),
            "features": {
                "smiles_refresh": True,
                "browser_reset": True,
                "smile_editor": True,
                "role_xp_evolution": True,
                "smiles_pool_randomizer": True,
                "multi_level_evolution": True,
            },
        }

    @app.get("/v1/models")
    def v1_models(_user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        rows = list_models(root)
        return {"object": "list", "data": rows}

    @app.post("/v1/embeddings")
    def v1_embeddings(payload: dict[str, Any], _user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        del _user
        raw_input = payload.get("input", "")
        if isinstance(raw_input, str):
            values = [raw_input]
        elif isinstance(raw_input, list):
            values = [str(x) for x in raw_input]
        else:
            raise HTTPException(status_code=400, detail="input must be string or list")

        data = []
        for idx, text in enumerate(values):
            data.append({"object": "embedding", "index": idx, "embedding": embedding_for_text(text)})
        return {"object": "list", "data": data}

    @app.post("/v1/chat/completions")
    def v1_chat_completions(payload: dict[str, Any], user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        if bool(payload.get("use_ai3", True)):
            try:
                response = run_v1_chat_completion(root=root, payload=payload, user=user)
                log_event(
                    root=root,
                    event_type="api_chat_completion",
                    actor=str(user.get("username", "api-user")),
                    details={
                        "provider": str(response.get("model", "")),
                        "run_id": str(response.get("run_id", "")),
                        "thread_id": str(response.get("thread_id", "")),
                        "compat": "ai3",
                    },
                )
                return response
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except Exception:
                # Safety fallback for rollout: keep ai2 path available if ai3 fails unexpectedly.
                pass

        messages = payload.get("messages", [])
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail="messages list is required")

        question = ""
        for msg in messages[::-1]:
            if isinstance(msg, dict) and str(msg.get("role", "")) == "user":
                question = str(msg.get("content", "")).strip()
                break
        if not question:
            raise HTTPException(status_code=400, detail="last user message content required")

        top_k = int(payload.get("top_k", 5))
        provider = str(payload.get("provider", "auto")).strip().lower()
        model_id = str(payload.get("model", "")).strip()
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        user_id = str(metadata.get("user_id", user.get("username", "api-user"))).strip() or str(user.get("username", "api-user"))
        task_type = str(metadata.get("task_type_override", "auto")).strip().lower()

        use_codex = provider not in {"extractive", "ollama", "local"}
        force_local = provider in {"extractive", "ollama", "local"}
        local_provider = "ollama" if provider == "ollama" else "extractive"

        hybrid = run_hybrid_answer(
            root=root,
            question=question,
            top_k=max(1, top_k),
            use_codex=use_codex,
            force_local=force_local,
            codex_model=model_id or "gpt-5",
            codex_base_url=str(payload.get("base_url", "https://api.openai.com/v1")),
            timeout_s=max(1, int(payload.get("timeout_s", 40))),
            local_provider=local_provider,
            local_model_id=model_id if force_local else "",
            user_id=user_id,
            metadata={**metadata, "task_type_override": task_type},
        )

        log_event(
            root=root,
            event_type="api_chat_completion",
            actor=str(user.get("username", "api-user")),
            details={"provider": hybrid.provider_used, "model": hybrid.model_used, "route_chain": hybrid.route_chain},
        )

        return {
            "id": "chatcmpl-local",
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

    @app.get("/v3/ui", response_class=HTMLResponse)
    def v3_ui():
        # QB-first default surface.
        return HTMLResponse(
            render_multi_instance_ui_html(),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/v3/ai3/ui", response_class=HTMLResponse)
    def v3_ai3_ui():
        # Legacy standalone deck preserved as a reference surface.
        return HTMLResponse(
            render_ai3_gui_html(),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/v3/chat-ui", response_class=HTMLResponse)
    def v3_chat_ui():
        flag = str(os.environ.get("CCBS_CHAT_UI_ENABLE", "1")).strip().lower()
        if flag not in {"1", "true", "yes", "on"}:
            raise HTTPException(status_code=404, detail="chat-ui disabled")
        return HTMLResponse(
            render_chat_ui_html(),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/v3/foundry-ui", response_class=HTMLResponse)
    def v3_foundry_ui():
        flag = str(os.environ.get("CCBS_FOUNDRY_UI_ENABLE", "1")).strip().lower()
        if flag not in {"1", "true", "yes", "on"}:
            raise HTTPException(status_code=404, detail="foundry-ui disabled")
        return HTMLResponse(
            render_foundry_pane_html(),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/v3/multi-instance/ui", response_class=HTMLResponse)
    def v3_multi_instance_ui(_user: dict[str, Any] = Depends(require_user)):
        del _user
        return HTMLResponse(
            render_multi_instance_ui_html(),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/admin/storage")
    def admin_storage(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return verify_storage(root)

    @app.get("/admin/models")
    def admin_models(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return {"models": list_models(root)}

    @app.get("/admin/sources")
    def admin_sources(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return {"sources": list_sources(root)}

    @app.get("/admin/index")
    def admin_index(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return index_stats(root)

    @app.get("/admin/plugins")
    def admin_plugins(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return {"plugins": list_plugins(root)}

    @app.get("/admin/users")
    def admin_users(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return {"message": "use CLI `ccbs ai user list` for local user enumeration"}

    @app.get("/admin/audit")
    def admin_audit(limit: int = 100, _user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return {"events": list_events(root=root, limit=max(1, int(limit)))}

    @app.get("/admin/perf")
    def admin_perf(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return {
            "runtime_resource_state": runtime_resource_state(),
            "perf_metrics": summarize_perf_metrics(root),
        }

    @app.get("/admin/quota")
    def admin_quota(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return quota_summary(root)

    @app.post("/admin/quota")
    def admin_quota_set(payload: dict[str, Any], _user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        token_budget = int(payload.get("monthly_token_budget", 2_000_000))
        cost_budget = float(payload.get("monthly_cost_budget_usd", 50.0))
        return set_quota_budgets(root, monthly_token_budget=token_budget, monthly_cost_budget_usd=cost_budget)

    @app.get("/admin/router-state")
    def admin_router_state(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return load_router_state(root)

    @app.get("/admin/workspaces")
    def admin_workspaces(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return list_workspaces(root)

    @app.get("/admin/status")
    def admin_status(_user: dict[str, Any] = Depends(require_admin)) -> Any:
        report = usage_report(root)
        quota = quota_summary(root)
        router = load_router_state(root)
        policy = load_routing_policy(root)
        return JSONResponse(
            {
                "storage": {
                    "total_bytes": report.total_bytes,
                    "max_bytes": report.max_bytes,
                    "remaining_bytes": report.remaining_bytes,
                    "sections": report.sections,
                },
                "index": index_stats(root),
                "models": len(list_models(root)),
                "sources": len(list_sources(root)),
                "plugins": len(list_plugins(root)),
                "quota": quota,
                "router_state": router,
                "policy_version": policy.get("version", "unknown"),
            }
        )

    @app.get("/admin/smiles")
    def admin_smiles_status(_user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        user_dir = _smiles_user_dir()
        sheet_dir = _smiles_sheet_dir()
        pool_dir = _pool_dir()
        card_files = sorted(
            [
                item.name
                for item in user_dir.iterdir()
                if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}
            ]
        )
        pool_files = sorted(
            [
                item.name
                for item in pool_dir.iterdir()
                if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}
            ]
        )
        sheet_files = sorted(
            [
                item.name
                for item in sheet_dir.iterdir()
                if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ]
        )
        return {
            "user_cards_dir": str(user_dir.resolve()),
            "pool_cards_dir": str(pool_dir.resolve()),
            "sheet_input_dir": str(sheet_dir.resolve()),
            "card_files": card_files,
            "pool_files": pool_files,
            "sheet_files": sheet_files,
            "restart_required_after_save": True,
        }

    @app.post("/admin/smiles/save-batch")
    def admin_smiles_save_batch(payload: dict[str, Any], _user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        cards = payload.get("cards")
        if not isinstance(cards, list) or not cards:
            raise HTTPException(status_code=400, detail="cards[] is required")
        user_dir = _smiles_user_dir()
        pool_dir = _pool_dir()
        save_mode = str(payload.get("mode", "individual")).strip().lower() or "individual"
        if save_mode not in {"individual", "pool", "both"}:
            raise HTTPException(status_code=400, detail="mode must be individual|pool|both")
        requested_level = _normalize_level_token(str(payload.get("level", "")).strip())
        saved: list[dict[str, Any]] = []
        pool_saved: list[dict[str, Any]] = []
        ext_by_mime = {
            "image/png": ".png",
            "image/webp": ".webp",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/svg+xml": ".svg",
        }
        now_stamp = int(time.time())
        default_level = requested_level or "a"
        for item in cards:
            if not isinstance(item, dict):
                continue
            role_id = str(item.get("role_id", "")).strip().lower()
            variant = str(item.get("variant", "a")).strip().lower() or "a"
            level = _normalize_level_token(str(item.get("level", "")).strip()) or default_level
            if not role_id_pattern.fullmatch(role_id):
                raise HTTPException(status_code=400, detail=f"invalid role_id: {role_id}")
            if not variant_pattern.fullmatch(variant):
                raise HTTPException(status_code=400, detail=f"invalid variant: {variant}")
            mime, data = _decode_image_data_url(str(item.get("image_data_url", "")))
            ext = ext_by_mime.get(mime.lower(), ".png")
            slot = str(item.get("slot", "")).strip() or "slot"

            if save_mode in {"individual", "both"}:
                stems: list[str] = []
                for token in (variant, level):
                    token = str(token or "").strip().lower()
                    if token and token not in stems:
                        stems.append(token)
                for token in stems:
                    stem = f"{role_id}_{token}"
                    for stale in user_dir.glob(f"{stem}.*"):
                        try:
                            stale.unlink()
                        except Exception:
                            pass
                    out_path = user_dir / f"{stem}{ext}"
                    out_path.write_bytes(data)
                    saved.append(
                        {
                            "role_id": role_id,
                            "variant": token,
                            "file": out_path.name,
                            "bytes": len(data),
                            "slot": slot,
                        }
                    )

            if save_mode in {"pool", "both"}:
                pool_name = f"{now_stamp}_{level}_{role_id}_{slot}_{len(pool_saved):02d}{ext}"
                pool_path = pool_dir / pool_name
                pool_path.write_bytes(data)
                pool_saved.append(
                    {
                        "role_id": role_id,
                        "level": level,
                        "file": pool_path.name,
                        "bytes": len(data),
                        "slot": slot,
                    }
                )

        if not saved and not pool_saved:
            raise HTTPException(status_code=400, detail="no valid cards were saved")
        return {
            "saved": saved,
            "saved_count": len(saved),
            "pool_saved": pool_saved,
            "pool_saved_count": len(pool_saved),
            "mode": save_mode,
            "level": requested_level or default_level,
            "user_cards_dir": str(user_dir.resolve()),
            "pool_cards_dir": str(pool_dir.resolve()),
            "restart_required": True,
        }

    @app.post("/admin/smiles/upload-sheet")
    def admin_smiles_upload_sheet(payload: dict[str, Any], _user: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        label = _safe_slug(str(payload.get("label", "sheet")).strip())
        mime, data = _decode_image_data_url(str(payload.get("image_data_url", "")))
        ext = {
            "image/png": ".png",
            "image/webp": ".webp",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
        }.get(mime.lower(), ".png")
        out_dir = _smiles_sheet_dir()
        stamp = int(time.time())
        out_path = out_dir / f"{stamp}_{label}{ext}"
        out_path.write_bytes(data)
        return {"sheet_file": out_path.name, "sheet_dir": str(out_dir.resolve()), "bytes": len(data)}

    @app.get("/admin/smiles/ui", response_class=HTMLResponse)
    def admin_smiles_ui(_user: dict[str, Any] = Depends(require_admin)):
        user_dir = _smiles_user_dir().resolve()
        sheet_dir = _smiles_sheet_dir().resolve()
        pool_dir = _pool_dir().resolve()
        roles = [
            "strategist",
            "core",
            "guardian",
            "ops",
            "retriever",
            "samurai",
            "hacker",
            "ranger",
            "scientist",
        ]
        variants = _all_level_tokens()
        targets = [f"{role}_{variant}" for role in roles for variant in variants]
        options = "\n".join([f'<option value="{name}">{name}</option>' for name in targets])
        return HTMLResponse(
            f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CCBS Smile Editor</title>
  <style>
    :root {{ --bg:#08112b; --panel:#0d1a40; --ink:#e7f6ff; --muted:#8cb8d6; --line:#2ce7ff66; --ok:#83ff9a; --warn:#ff8ea0; }}
    body {{ margin:0; color:var(--ink); font-family:Segoe UI, Arial, sans-serif; background:linear-gradient(140deg,#071029,#0a1a42 45%, #0a142e); }}
    .wrap {{ max-width:1180px; margin:16px auto; padding:0 14px 30px; display:grid; gap:12px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px; }}
    h1 {{ margin:0 0 8px; font-size:20px; }}
    .small {{ color:var(--muted); font-size:12px; }}
    .paths code {{ display:block; margin:4px 0; padding:6px 8px; border-radius:8px; background:#071431; color:#a8edff; }}
    .controls {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; }}
    button {{ border:0; border-radius:10px; padding:8px 12px; font-weight:700; cursor:pointer; }}
    .btn-main {{ background:linear-gradient(120deg,#2ce7ff,#9df7ff); color:#041629; }}
    .btn-alt {{ background:linear-gradient(120deg,#90ff68,#bfffa2); color:#07220b; }}
    .btn-warn {{ background:linear-gradient(120deg,#ff96aa,#ff7e93); color:#2e0711; }}
    .grid {{ display:grid; grid-template-columns: repeat(5, minmax(160px, 1fr)); gap:8px; }}
    .slot {{ border:1px solid #2ce7ff55; border-radius:10px; padding:8px; background:#071531; }}
    .slot label {{ display:block; font-size:12px; color:var(--muted); margin-bottom:4px; text-transform:uppercase; letter-spacing:.07em; }}
    .slot select {{ width:100%; border-radius:8px; background:#08102a; color:var(--ink); border:1px solid #2ce7ff4a; padding:6px; }}
    .previews {{ display:grid; grid-template-columns: repeat(5, minmax(140px, 1fr)); gap:8px; }}
    .preview-card {{ background:#071431; border:1px solid #2ce7ff50; border-radius:10px; padding:6px; }}
    .preview-card canvas {{ width:100%; height:auto; display:block; border-radius:8px; background:#050d20; }}
    .msg {{ min-height:20px; font-size:13px; color:var(--muted); }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <h1>Smile Editor (5-Slot Import)</h1>
      <div class="small">Use one collage image with five Smiles (top-left, top-right, center, bottom-left, bottom-right). Import writes role files that the card deck can evolve into.</div>
      <div class="paths">
        <code>Cards output folder: {user_dir}</code>
        <code>Pool output folder: {pool_dir}</code>
        <code>Sheet input folder: {sheet_dir}</code>
      </div>
      <div class="small">Individual naming: <code>role_level.png</code> (levels: <code>l0 l1 a b c d e</code>). Pool naming is automatic and deterministic-random at runtime.</div>
    </div>

    <div class="panel">
      <div class="controls">
        <input id="sheetFile" type="file" accept="image/*" />
        <label class="small">X Offset <input id="xOffset" type="number" value="0" style="width:80px;" /></label>
        <label class="small">Y Offset <input id="yOffset" type="number" value="0" style="width:80px;" /></label>
        <label class="small">Scale <input id="scale" type="number" step="0.05" value="1.00" style="width:90px;" /></label>
        <label class="small">Save Mode
          <select id="saveMode" style="width:160px;">
            <option value="individual">Individual slots</option>
            <option value="pool">One pooled random set</option>
            <option value="both">Individual + pool</option>
          </select>
        </label>
        <label class="small">Level
          <select id="levelTag" style="width:140px;">
            <option value="l0">l0 (scribble 1)</option>
            <option value="l1">l1 (scribble 2)</option>
            <option value="a">a (base)</option>
            <option value="b">b (evolved)</option>
            <option value="c">c (elite)</option>
            <option value="d">d (rare)</option>
            <option value="e">e (mythic)</option>
          </select>
        </label>
        <button id="previewBtn" class="btn-main" type="button">Preview 5 Smiles</button>
        <button id="saveBtn" class="btn-alt" type="button">Save Cards</button>
        <button id="saveSheetBtn" class="btn-warn" type="button">Save Source Sheet</button>
      </div>
      <div class="small">Pool mode puts all crops in one random image pool. Individual mode writes role files for level-based evolution. After saving: use Smiles Refresh / Browser Reset in the UI.</div>
    </div>

    <div class="panel">
      <div class="grid">
        <div class="slot"><label>Top Left</label><select id="slot_top_left">{options}</select></div>
        <div class="slot"><label>Top Right</label><select id="slot_top_right">{options}</select></div>
        <div class="slot"><label>Center</label><select id="slot_center">{options}</select></div>
        <div class="slot"><label>Bottom Left</label><select id="slot_bottom_left">{options}</select></div>
        <div class="slot"><label>Bottom Right</label><select id="slot_bottom_right">{options}</select></div>
      </div>
    </div>

    <div class="panel">
      <div class="previews">
        <div class="preview-card"><div class="small">Top Left</div><canvas id="cv_top_left" width="320" height="460"></canvas></div>
        <div class="preview-card"><div class="small">Top Right</div><canvas id="cv_top_right" width="320" height="460"></canvas></div>
        <div class="preview-card"><div class="small">Center</div><canvas id="cv_center" width="320" height="460"></canvas></div>
        <div class="preview-card"><div class="small">Bottom Left</div><canvas id="cv_bottom_left" width="320" height="460"></canvas></div>
        <div class="preview-card"><div class="small">Bottom Right</div><canvas id="cv_bottom_right" width="320" height="460"></canvas></div>
      </div>
    </div>

    <div class="panel">
      <div id="msg" class="msg">Ready.</div>
      <a class="small" href="/admin/ui">Back to admin dashboard</a>
    </div>
  </div>
<script>
const slots = [
  {{ id: 'top_left', x: 0.06, y: 0.04, w: 0.29, h: 0.43 }},
  {{ id: 'top_right', x: 0.65, y: 0.04, w: 0.29, h: 0.43 }},
  {{ id: 'center', x: 0.35, y: 0.24, w: 0.31, h: 0.44 }},
  {{ id: 'bottom_left', x: 0.06, y: 0.52, w: 0.29, h: 0.43 }},
  {{ id: 'bottom_right', x: 0.65, y: 0.52, w: 0.29, h: 0.43 }},
];
let lastImage = null;
let cropData = {{}};

function msg(t, isErr = false) {{
  const el = document.getElementById('msg');
  el.textContent = t;
  el.style.color = isErr ? '#ff9fad' : '#8cb8d6';
}}

function readFileAsDataURL(file) {{
  return new Promise((resolve, reject) => {{
    const r = new FileReader();
    r.onload = () => resolve(String(r.result || ''));
    r.onerror = reject;
    r.readAsDataURL(file);
  }});
}}

function loadImage(dataUrl) {{
  return new Promise((resolve, reject) => {{
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = dataUrl;
  }});
}}

function slotRect(slot, w, h, xOff, yOff, scale) {{
  const bw = w * slot.w;
  const bh = h * slot.h;
  const sw = bw * scale;
  const sh = bh * scale;
  const sx = (w * slot.x) + xOff - ((sw - bw) / 2);
  const sy = (h * slot.y) + yOff - ((sh - bh) / 2);
  return {{ sx, sy, sw, sh }};
}}

async function preview() {{
  const file = document.getElementById('sheetFile').files[0];
  if (!file) {{
    msg('Choose a sheet image first.', true);
    return;
  }}
  const xOff = Number(document.getElementById('xOffset').value || 0);
  const yOff = Number(document.getElementById('yOffset').value || 0);
  const scale = Math.max(0.5, Number(document.getElementById('scale').value || 1));
  const dataUrl = await readFileAsDataURL(file);
  const img = await loadImage(dataUrl);
  lastImage = dataUrl;
  cropData = {{}};
  for (const slot of slots) {{
    const rect = slotRect(slot, img.width, img.height, xOff, yOff, scale);
    const cv = document.getElementById(`cv_${{slot.id}}`);
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.drawImage(img, rect.sx, rect.sy, rect.sw, rect.sh, 0, 0, cv.width, cv.height);
    cropData[slot.id] = cv.toDataURL('image/png');
  }}
  msg('Preview ready. Check crops, then Save Cards.');
}}

async function postJson(path, body) {{
  const res = await fetch(path, {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(body),
  }});
  const text = await res.text();
  let data = {{}};
  try {{ data = text ? JSON.parse(text) : {{}}; }} catch (_err) {{ data = {{ raw: text }}; }}
  if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
  return data;
}}

async function saveCards() {{
  if (!Object.keys(cropData).length) {{
    await preview();
  }}
  const saveMode = String(document.getElementById('saveMode').value || 'individual');
  const levelTag = String(document.getElementById('levelTag').value || 'a');
  const cards = [];
  for (const slot of slots) {{
    const select = document.getElementById(`slot_${{slot.id}}`);
    const raw = String(select.value || '');
    const bits = raw.split('_');
    if (bits.length < 2) continue;
    const variant = bits.pop();
    const role = bits.join('_');
    cards.push({{
      slot: slot.id,
      role_id: role,
      variant: variant,
      level: levelTag,
      image_data_url: cropData[slot.id] || '',
    }});
  }}
  const out = await postJson('/admin/smiles/save-batch', {{ cards, mode: saveMode, level: levelTag }});
  msg(`Saved individual=${{out.saved_count || 0}}, pool=${{out.pool_saved_count || 0}} (mode=${{out.mode}} level=${{out.level}}).`);
}}

async function saveSheet() {{
  const file = document.getElementById('sheetFile').files[0];
  if (!file) {{
    msg('Choose a sheet image first.', true);
    return;
  }}
  if (!lastImage) {{
    lastImage = await readFileAsDataURL(file);
  }}
  const out = await postJson('/admin/smiles/upload-sheet', {{
    label: file.name,
    image_data_url: lastImage,
  }});
  msg(`Saved source sheet: ${{out.sheet_file}}`);
}}

document.getElementById('previewBtn').addEventListener('click', () => preview().catch((e) => msg(String(e.message || e), true)));
document.getElementById('saveBtn').addEventListener('click', () => saveCards().catch((e) => msg(String(e.message || e), true)));
document.getElementById('saveSheetBtn').addEventListener('click', () => saveSheet().catch((e) => msg(String(e.message || e), true)));
</script>
</body>
</html>
""",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/admin/ui", response_class=HTMLResponse)
    def admin_ui(_user: dict[str, Any] = Depends(require_admin)) -> str:
        report = usage_report(root)
        idx = index_stats(root)
        models = list_models(root)
        sources = list_sources(root)
        plugins = list_plugins(root)
        return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CCBS Offline Admin</title>
  <style>
    :root {{ --bg:#f5f2ea; --ink:#21201d; --card:#fffdf7; --line:#d9d2c3; --accent:#8a3d00; }}
    body {{ margin:0; font-family: Georgia, "Times New Roman", serif; background:linear-gradient(145deg,#f7f4ec,#ece6da); color:var(--ink); }}
    .wrap {{ max-width: 980px; margin: 24px auto; padding: 0 16px; }}
    h1 {{ letter-spacing: .03em; }}
    .grid {{ display:grid; gap:14px; grid-template-columns: repeat(auto-fit, minmax(220px,1fr)); }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; box-shadow:0 4px 14px rgba(0,0,0,.06); }}
    .label {{ color:#5d564a; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }}
    .value {{ font-size:24px; color:var(--accent); margin-top:4px; }}
    .small {{ font-size:12px; color:#4e483f; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>CCBS Offline Admin Dashboard</h1>
    <div class="grid">
      <div class="card"><div class="label">Storage Used</div><div class="value">{report.total_bytes}</div><div class="small">Max {report.max_bytes}</div></div>
      <div class="card"><div class="label">Storage Remaining</div><div class="value">{report.remaining_bytes}</div><div class="small">Hard cap enforced</div></div>
      <div class="card"><div class="label">Indexed Docs</div><div class="value">{idx.get('docs',0)}</div><div class="small">Chunks {idx.get('chunks',0)}</div></div>
      <div class="card"><div class="label">Models</div><div class="value">{len(models)}</div><div class="small">Registry entries</div></div>
      <div class="card"><div class="label">Sources</div><div class="value">{len(sources)}</div><div class="small">Curated mirror entries</div></div>
      <div class="card"><div class="label">Plugins</div><div class="value">{len(plugins)}</div><div class="small">Signed + allowlisted only</div></div>
      <div class="card"><div class="label">Smiles</div><div class="value"><a href="/admin/smiles/ui">Open Smile Editor</a></div><div class="small">5-slot importer + role mapping</div></div>
    </div>
  </div>
</body>
</html>
"""

    return app


def api_status(root: Path) -> dict[str, Any]:
    try:
        _require_fastapi()
        installed = True
    except ApiDependencyError as exc:
        return {"dependencies_ok": False, "detail": str(exc)}

    report = usage_report(root)
    return {
        "dependencies_ok": installed,
        "storage_total_bytes": report.total_bytes,
        "storage_remaining_bytes": report.remaining_bytes,
    }


def serve_api(root: Path, host: str = "127.0.0.1", port: int = 11435) -> None:
    try:
        import uvicorn
    except Exception as exc:  # noqa: BLE001
        raise ApiDependencyError("uvicorn is not installed. Install dependencies: pip install uvicorn") from exc

    app = create_app(root)
    uvicorn.run(app, host=host, port=max(1, int(port)), log_level="info")
