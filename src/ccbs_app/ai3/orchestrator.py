"""ai3 orchestrator: persisted run steps, approvals, retrieval, and synthesis."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .bridge_ai2 import mirror_answer_memory, mirror_run_event
from .checkpoint import create_checkpoint
from .db import new_id, transaction, utc_now
from .mcp.approvals import request_tool_approval
from .mcp.host import execute_tool_call
from .mcp.registry import seed_mcp_registry
from .question_routing import classify_question
from .retrieval.citations import persist_citations
from .retrieval.fts import search_fts
from .retrieval.reranker import merge_and_rerank
from .retrieval.vector_lancedb import search_vectors
from .taskmaster import run_taskmaster


STAGES = ["router", "planner", "retriever", "tool_executor", "synthesizer", "recorder"]


def _as_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _parse_json(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    text = str(raw).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _next_step_index(conn: sqlite3.Connection, run_id: str) -> int:
    row = conn.execute("SELECT COALESCE(MAX(step_index), -1) FROM run_step WHERE run_id = ?", (run_id,)).fetchone()
    current = row[0] if row is not None and row[0] is not None else -1
    return int(current) + 1


def _start_step(conn: sqlite3.Connection, run_id: str, step_type: str, payload: dict[str, Any]) -> str:
    step_id = new_id("step")
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO run_step(step_id, run_id, step_index, step_type, status, input_json, output_json, started_at, completed_at)
            VALUES (?, ?, ?, ?, 'running', ?, NULL, ?, NULL)
            """,
            (step_id, run_id, _next_step_index(conn, run_id), step_type, _as_json(payload), utc_now()),
        )
    return step_id


def _finish_step(
    conn: sqlite3.Connection,
    thread_id: str,
    run_id: str,
    step_id: str,
    step_type: str,
    status: str,
    output: dict[str, Any],
) -> None:
    now = utc_now()
    snapshot = {
        "stage": step_type,
        "status": status,
        "output": output,
        "run_id": run_id,
        "thread_id": thread_id,
    }
    with transaction(conn):
        conn.execute(
            "UPDATE run_step SET status = ?, output_json = ?, completed_at = ? WHERE step_id = ?",
            (status, _as_json(output), now, step_id),
        )
        create_checkpoint(conn=conn, thread_id=thread_id, run_id=run_id, step_id=step_id, state=snapshot)


def _mark_run(conn: sqlite3.Connection, run_id: str, status: str, error: str = "", set_started: bool = False) -> None:
    now = utc_now()
    with transaction(conn):
        if status in {"completed", "failed", "cancelled"}:
            conn.execute(
                "UPDATE run SET status = ?, error = ?, completed_at = ? WHERE run_id = ?",
                (status, error or None, now, run_id),
            )
            return
        if set_started:
            conn.execute(
                "UPDATE run SET status = ?, error = NULL, started_at = COALESCE(started_at, ?) WHERE run_id = ?",
                (status, now, run_id),
            )
            return
        conn.execute("UPDATE run SET status = ?, error = NULL WHERE run_id = ?", (status, run_id))


def _latest_user_message(conn: sqlite3.Connection, thread_id: str) -> str:
    row = conn.execute(
        """
        SELECT content
        FROM message
        WHERE thread_id = ? AND role = 'user'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (thread_id,),
    ).fetchone()
    if row is None:
        return ""
    return str(row["content"] or "").strip()


def _now_ts() -> str:
    return utc_now()


def _default_endpoint_values(provider: str) -> tuple[str, str]:
    p = provider.strip().lower() or "ollama"
    if p == "lmstudio":
        return "http://127.0.0.1:1234/v1", "local-model"
    if p == "codex":
        return "https://api.openai.com/v1", "gpt-5"
    return "http://127.0.0.1:11434", "llama3.1:8b"


def ensure_endpoint(
    conn: sqlite3.Connection,
    provider: str = "ollama",
    base_url: str = "",
    chat_model: str = "",
    embed_model: str = "",
    endpoint_id: str = "",
) -> str:
    pid = endpoint_id.strip() or new_id("endpoint")
    existing = conn.execute("SELECT endpoint_id FROM model_endpoint WHERE endpoint_id = ?", (pid,)).fetchone()
    if existing is not None:
        return str(existing["endpoint_id"])

    default_base, default_chat = _default_endpoint_values(provider)
    row = {
        "endpoint_id": pid,
        "provider": provider.strip().lower() or "ollama",
        "base_url": (base_url or default_base).strip(),
        "auth_ref": "",
        "chat_model": (chat_model or default_chat).strip(),
        "embed_model": embed_model.strip(),
        "created_at": _now_ts(),
        "metadata_json": "{}",
    }
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO model_endpoint(endpoint_id, provider, base_url, auth_ref, chat_model, embed_model, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["endpoint_id"],
                row["provider"],
                row["base_url"],
                row["auth_ref"],
                row["chat_model"],
                row["embed_model"] or None,
                row["created_at"],
                row["metadata_json"],
            ),
        )
    return row["endpoint_id"]


def ensure_default_endpoint(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT endpoint_id
        FROM model_endpoint
        ORDER BY created_at ASC
        LIMIT 1
        """
    ).fetchone()
    if row is not None:
        return str(row["endpoint_id"])
    return ensure_endpoint(conn=conn, provider="ollama")


def create_thread(
    conn: sqlite3.Connection,
    title: str = "",
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now_ts()
    row = {
        "thread_id": new_id("thread"),
        "created_at": now,
        "updated_at": now,
        "title": title.strip(),
        "tags_json": _as_json(tags or []),
        "metadata_json": _as_json(metadata or {}),
    }
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO thread(thread_id, created_at, updated_at, title, tags_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                row["thread_id"],
                row["created_at"],
                row["updated_at"],
                row["title"] or None,
                row["tags_json"],
                row["metadata_json"],
            ),
        )
    return {
        "thread_id": row["thread_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "title": row["title"],
        "tags": tags or [],
        "metadata": metadata or {},
    }


def create_message(
    conn: sqlite3.Connection,
    thread_id: str,
    role: str,
    content: str,
    content_json: dict[str, Any] | None = None,
    parent_message_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tid = thread_id.strip()
    if not tid:
        raise ValueError("thread_id is required")
    if role not in {"user", "assistant", "tool", "system"}:
        raise ValueError("role must be one of: user, assistant, tool, system")
    body = content.strip()
    if not body:
        raise ValueError("content is required")

    row = {
        "message_id": new_id("msg"),
        "thread_id": tid,
        "role": role,
        "content": body,
        "content_json": _as_json(content_json or {}),
        "created_at": _now_ts(),
        "parent_message_id": parent_message_id.strip() or None,
        "metadata_json": _as_json(metadata or {}),
    }
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO message(message_id, thread_id, role, content, content_json, created_at, parent_message_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["message_id"],
                row["thread_id"],
                row["role"],
                row["content"],
                row["content_json"],
                row["created_at"],
                row["parent_message_id"],
                row["metadata_json"],
            ),
        )
        conn.execute("UPDATE thread SET updated_at = ? WHERE thread_id = ?", (_now_ts(), tid))

    return {
        "message_id": row["message_id"],
        "thread_id": row["thread_id"],
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
        "parent_message_id": row["parent_message_id"],
        "metadata": metadata or {},
        "content_json": content_json or {},
    }


def create_run(
    conn: sqlite3.Connection,
    thread_id: str,
    endpoint_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tid = thread_id.strip()
    if not tid:
        raise ValueError("thread_id is required")
    thread = conn.execute("SELECT thread_id FROM thread WHERE thread_id = ?", (tid,)).fetchone()
    if thread is None:
        raise ValueError(f"thread not found: {tid}")

    endpoint = endpoint_id.strip() or ensure_default_endpoint(conn)
    endpoint_row = conn.execute("SELECT endpoint_id FROM model_endpoint WHERE endpoint_id = ?", (endpoint,)).fetchone()
    if endpoint_row is None:
        raise ValueError(f"endpoint not found: {endpoint}")

    now = _now_ts()
    payload = {
        "run_id": new_id("run"),
        "thread_id": tid,
        "endpoint_id": endpoint,
        "status": "queued",
        "started_at": None,
        "completed_at": None,
        "error": None,
        "trace_id": new_id("trace"),
        "metadata_json": _as_json(metadata or {}),
    }
    with transaction(conn):
        conn.execute(
            """
            INSERT INTO run(run_id, thread_id, endpoint_id, status, started_at, completed_at, error, trace_id, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["run_id"],
                payload["thread_id"],
                payload["endpoint_id"],
                payload["status"],
                payload["started_at"],
                payload["completed_at"],
                payload["error"],
                payload["trace_id"],
                payload["metadata_json"],
            ),
        )
        conn.execute("UPDATE thread SET updated_at = ? WHERE thread_id = ?", (now, tid))

    return get_run(conn, payload["run_id"])


def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "thread_id": str(row["thread_id"]),
        "endpoint_id": str(row["endpoint_id"]),
        "status": str(row["status"]),
        "started_at": str(row["started_at"] or ""),
        "completed_at": str(row["completed_at"] or ""),
        "error": str(row["error"] or ""),
        "trace_id": str(row["trace_id"] or ""),
        "metadata": _parse_json(row["metadata_json"], {}),
    }


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT run_id, thread_id, endpoint_id, status, started_at, completed_at, error, trace_id, metadata_json
        FROM run
        WHERE run_id = ?
        """,
        (run_id.strip(),),
    ).fetchone()
    if row is None:
        raise ValueError(f"run not found: {run_id}")
    return _row_to_run(row)


def list_run_steps(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT step_id, run_id, step_index, step_type, status, input_json, output_json, started_at, completed_at
        FROM run_step
        WHERE run_id = ?
        ORDER BY step_index ASC
        """,
        (run_id.strip(),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "step_id": str(row["step_id"]),
                "run_id": str(row["run_id"]),
                "step_index": int(row["step_index"]),
                "step_type": str(row["step_type"]),
                "status": str(row["status"]),
                "input": _parse_json(row["input_json"], {}),
                "output": _parse_json(row["output_json"], {}),
                "started_at": str(row["started_at"] or ""),
                "completed_at": str(row["completed_at"] or ""),
            }
        )
    return out


def list_run_artifacts(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT artifact_id, thread_id, run_id, kind, uri, mime, sha256, bytes, created_at, metadata_json
        FROM artifact
        WHERE run_id = ?
        ORDER BY created_at ASC
        """,
        (run_id.strip(),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "artifact_id": str(row["artifact_id"]),
                "thread_id": str(row["thread_id"]),
                "run_id": str(row["run_id"]),
                "kind": str(row["kind"]),
                "uri": str(row["uri"]),
                "mime": str(row["mime"] or ""),
                "sha256": str(row["sha256"] or ""),
                "bytes": int(row["bytes"] or 0),
                "created_at": str(row["created_at"]),
                "metadata": _parse_json(row["metadata_json"], {}),
            }
        )
    return out


def list_run_citations(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT citation_id, source_uri, doc_id, chunk_id, page, start_offset, end_offset, snippet
        FROM citation
        WHERE run_id = ?
        ORDER BY rowid ASC
        """,
        (run_id.strip(),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "citation_id": str(row["citation_id"]),
                "source_uri": str(row["source_uri"]),
                "doc_id": str(row["doc_id"] or ""),
                "chunk_id": str(row["chunk_id"] or ""),
                "page": row["page"],
                "start_offset": row["start_offset"],
                "end_offset": row["end_offset"],
                "snippet": str(row["snippet"] or ""),
            }
        )
    return out


def retrieve_chunks(conn: sqlite3.Connection, query: str, top_k: int = 5) -> dict[str, Any]:
    question = query.strip()
    if not question:
        return {"query": "", "ranked": [], "hits": [], "context": "", "citations": []}

    recall = max(8, int(top_k) * 4)
    lexical = search_fts(conn, query=question, top_k=recall)
    vector = search_vectors(conn, query=question, top_k=recall)
    ranked = merge_and_rerank(lexical_hits=lexical, vector_hits=vector, top_k=max(1, int(top_k)))

    ordered_ids = [str(item.get("chunk_id", "")) for item in ranked if str(item.get("chunk_id", ""))]
    if not ordered_ids:
        return {
            "query": question,
            "ranked": ranked,
            "hits": [],
            "context": "",
            "citations": [],
            "lexical_count": len(lexical),
            "vector_count": len(vector),
        }

    placeholders = ",".join("?" for _ in ordered_ids)
    rows = conn.execute(
        f"""
        SELECT c.chunk_id, c.doc_id, c.text, c.page, c.start_offset, c.end_offset, d.source_uri
        FROM chunk c
        LEFT JOIN document d ON d.doc_id = c.doc_id
        WHERE c.chunk_id IN ({placeholders})
        """,
        tuple(ordered_ids),
    ).fetchall()
    by_id = {str(row["chunk_id"]): row for row in rows}

    hits: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    context_lines: list[str] = []
    for rank, item in enumerate(ranked, 1):
        chunk_id = str(item.get("chunk_id", ""))
        row = by_id.get(chunk_id)
        if row is None:
            continue
        text = str(row["text"] or "")
        snippet = text[:700].strip()
        source_uri = str(row["source_uri"] or "")
        hit = {
            "rank": rank,
            "chunk_id": chunk_id,
            "doc_id": str(row["doc_id"] or ""),
            "source_uri": source_uri,
            "snippet": snippet,
            "page": row["page"],
            "start_offset": row["start_offset"],
            "end_offset": row["end_offset"],
            "score": float(item.get("score", 0.0)),
            "lexical_score": float(item.get("lexical_score", 0.0)),
            "vector_score": float(item.get("vector_score", 0.0)),
        }
        hits.append(hit)
        citations.append(
            {
                "source_uri": source_uri,
                "doc_id": hit["doc_id"],
                "chunk_id": chunk_id,
                "page": row["page"],
                "start_offset": row["start_offset"],
                "end_offset": row["end_offset"],
                "snippet": snippet,
            }
        )
        context_lines.append(f"[{rank}] {source_uri}\n{snippet}")

    return {
        "query": question,
        "ranked": ranked,
        "hits": hits,
        "citations": citations,
        "context": "\n\n".join(context_lines),
        "lexical_count": len(lexical),
        "vector_count": len(vector),
    }


def _memory_context(conn: sqlite3.Connection, limit: int = 8) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT key, value, importance
        FROM memory_item
        ORDER BY importance DESC, rowid DESC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        key = str(row["key"] or "").strip()
        value = str(row["value"] or "").strip()
        if not value:
            continue
        items.append({"key": key, "value": value, "importance": float(row["importance"] or 0.0)})
    if not items:
        return {"items": [], "context": ""}
    lines = ["Memory Hints:"]
    for idx, item in enumerate(items, 1):
        label = item["key"] or f"fact_{idx}"
        lines.append(f"- {label}: {item['value']}")
    return {"items": items, "context": "\n".join(lines)}


def _tool_requests(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    raw = metadata.get("tool_calls", [])
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name", "")).strip()
        if not tool_name:
            continue
        args = item.get("arguments", {})
        if not isinstance(args, dict):
            args = {}
        out.append({"tool_name": tool_name, "arguments": args})
    return out


def _approval_is_approved(conn: sqlite3.Connection, approval_id: str) -> bool:
    if not approval_id.strip():
        return False
    row = conn.execute("SELECT decision FROM approval WHERE approval_id = ?", (approval_id,)).fetchone()
    if row is None:
        return False
    return str(row["decision"] or "") == "approved"


def _upsert_run_metadata(conn: sqlite3.Connection, run_id: str, metadata: dict[str, Any]) -> None:
    with transaction(conn):
        conn.execute("UPDATE run SET metadata_json = ? WHERE run_id = ?", (_as_json(metadata), run_id))


def execute_run(
    root: Path,
    conn: sqlite3.Connection,
    run_id: str,
    actor: str = "ai3",
    allow_remote: bool = True,
) -> dict[str, Any]:
    run = get_run(conn, run_id)
    if run["status"] in {"completed", "failed", "cancelled"}:
        return {
            "run": run,
            "steps": list_run_steps(conn, run_id),
            "citations": list_run_citations(conn, run_id),
            "artifacts": list_run_artifacts(conn, run_id),
        }

    seed_mcp_registry(conn)
    _mark_run(conn, run_id, status="running", set_started=True)

    run = get_run(conn, run_id)
    metadata = dict(run.get("metadata", {}))
    thread_id = str(run["thread_id"])
    endpoint_id = str(run["endpoint_id"])

    endpoint_row = conn.execute(
        "SELECT provider, base_url, chat_model FROM model_endpoint WHERE endpoint_id = ?",
        (endpoint_id,),
    ).fetchone()
    if endpoint_row is None:
        _mark_run(conn, run_id, status="failed", error=f"endpoint missing: {endpoint_id}")
        raise ValueError(f"endpoint missing: {endpoint_id}")

    question = str(metadata.get("question", "")).strip() or _latest_user_message(conn, thread_id)
    if not question:
        _mark_run(conn, run_id, status="failed", error="no user question available")
        raise ValueError("run has no question; add a user message or metadata.question")

    question_profile = classify_question(question)
    simple_qa = bool(question_profile.get("simple_qa", False))

    metadata.setdefault("question", question)
    metadata.setdefault("question_profile", question_profile)
    metadata.setdefault("simple_qa", simple_qa)
    metadata.setdefault("local_attempts_max", 3)
    metadata.setdefault("top_k", 5)
    metadata.setdefault("offline_only", False)
    metadata.setdefault("strict_local_models", not simple_qa)
    metadata.setdefault("allow_extractive_fallback", simple_qa)
    metadata.setdefault("dual_write", _to_bool(os.environ.get("CCBS_AI3_DUAL_WRITE", "1")))
    metadata.setdefault("allow_remote", bool(allow_remote))

    local_base_urls = dict(metadata.get("local_base_urls", {})) if isinstance(metadata.get("local_base_urls", {}), dict) else {}
    local_models = dict(metadata.get("local_models", {})) if isinstance(metadata.get("local_models", {}), dict) else {}

    provider = str(endpoint_row["provider"] or "").strip().lower()
    base_url = str(endpoint_row["base_url"] or "").strip()
    chat_model = str(endpoint_row["chat_model"] or "").strip()
    metadata.setdefault("preferred_provider", provider or "ollama")

    if provider in {"ollama", "lmstudio"}:
        local_base_urls.setdefault(provider, base_url)
        local_models.setdefault(provider, chat_model)

    metadata["local_base_urls"] = local_base_urls
    metadata["local_models"] = local_models
    _upsert_run_metadata(conn, run_id, metadata)

    route_output: dict[str, Any] = {}
    retrieval_output: dict[str, Any] = {"context": "", "hits": [], "citations": []}
    tool_output: dict[str, Any] = {"requires_action": False, "results": []}
    synth_output: dict[str, Any] = {}

    try:
        router_step = _start_step(conn, run_id, "router", {"question": question})
        needs_retrieval = int(metadata.get("top_k", 5)) > 0 and not _to_bool(metadata.get("simple_qa", False))
        route_policy = "simple_qa_fast_path" if _to_bool(metadata.get("simple_qa", False)) else "offline_3_then_online_1"
        route_output = {
            "stage": "router",
            "needs_retrieval": needs_retrieval,
            "needs_tools": bool(_tool_requests(metadata)),
            "question_chars": len(question),
            "simple_qa": _to_bool(metadata.get("simple_qa", False)),
            "question_profile": dict(metadata.get("question_profile", {})),
            "route_policy": route_policy,
        }
        _finish_step(conn, thread_id, run_id, router_step, "router", "completed", route_output)

        planner_step = _start_step(conn, run_id, "planner", {"question": question})
        pipeline = ["router", "planner"]
        if route_output.get("needs_retrieval"):
            pipeline.append("retriever")
        if route_output.get("needs_tools"):
            pipeline.append("tool_executor")
        pipeline.extend(["synthesizer", "recorder"])
        planner_output = {
            "stage": "planner",
            "pipeline": pipeline,
            "local_attempts_max": max(1, int(metadata.get("local_attempts_max", 3))),
            "offline_only": _to_bool(metadata.get("offline_only", False)),
            "allow_remote": _to_bool(metadata.get("allow_remote", allow_remote)),
            "simple_qa": _to_bool(metadata.get("simple_qa", False)),
            "route_policy": route_policy,
        }
        _finish_step(conn, thread_id, run_id, planner_step, "planner", "completed", planner_output)

        if route_output.get("needs_retrieval"):
            retrieval_step = _start_step(
                conn,
                run_id,
                "retriever",
                {"query": question, "top_k": max(1, int(metadata.get("top_k", 5)))},
            )
            retrieval_output = retrieve_chunks(conn, query=question, top_k=max(1, int(metadata.get("top_k", 5))))
            with transaction(conn):
                conn.execute("DELETE FROM citation WHERE run_id = ?", (run_id,))
                persist_citations(conn, run_id=run_id, rows=list(retrieval_output.get("citations", [])))
            _finish_step(
                conn,
                thread_id,
                run_id,
                retrieval_step,
                "retriever",
                "completed",
                {
                    "hits": retrieval_output.get("hits", []),
                    "lexical_count": retrieval_output.get("lexical_count", 0),
                    "vector_count": retrieval_output.get("vector_count", 0),
                },
            )

        tool_requests = _tool_requests(metadata)
        existing_tool_count = conn.execute(
            "SELECT COUNT(1) FROM tool_call WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        has_existing_tools = bool(existing_tool_count and int(existing_tool_count[0] or 0) > 0)

        if route_output.get("needs_tools") or has_existing_tools:
            tool_step = _start_step(
                conn,
                run_id,
                "tool_executor",
                {"tool_requests": tool_requests},
            )

            if not has_existing_tools and tool_requests:
                with transaction(conn):
                    for item in tool_requests:
                        tool_call_id = new_id("toolcall")
                        conn.execute(
                            """
                            INSERT INTO tool_call(tool_call_id, run_id, step_id, tool_name, arguments_json, result_json, status, approval_id, started_at, completed_at)
                            VALUES (?, ?, ?, ?, ?, NULL, 'planned', NULL, NULL, NULL)
                            """,
                            (
                                tool_call_id,
                                run_id,
                                tool_step,
                                str(item["tool_name"]),
                                _as_json(item.get("arguments", {})),
                            ),
                        )

            planned_rows = conn.execute(
                """
                SELECT tool_call_id, tool_name, approval_id, status
                FROM tool_call
                WHERE run_id = ?
                ORDER BY rowid ASC
                """,
                (run_id,),
            ).fetchall()

            pending_approvals: list[dict[str, Any]] = []
            for row in planned_rows:
                status = str(row["status"])
                if status not in {"planned", "blocked"}:
                    continue
                approval_id = str(row["approval_id"] or "")
                if status == "blocked":
                    continue
                if approval_id and _approval_is_approved(conn, approval_id):
                    continue
                if approval_id:
                    # An approval record already exists; do not fan out duplicates on resume.
                    continue
                result = request_tool_approval(
                    conn,
                    run_id=run_id,
                    tool_call_id=str(row["tool_call_id"]),
                    rationale=f"approval required for {row['tool_name']}",
                )
                pending_approvals.append(result)

            blocked_rows = conn.execute(
                """
                SELECT tool_call_id, tool_name, approval_id, status
                FROM tool_call
                WHERE run_id = ? AND status = 'blocked'
                ORDER BY rowid ASC
                """,
                (run_id,),
            ).fetchall()

            if blocked_rows:
                pending = [
                    {
                        "tool_call_id": str(row["tool_call_id"]),
                        "tool_name": str(row["tool_name"]),
                        "approval_id": str(row["approval_id"] or ""),
                    }
                    for row in blocked_rows
                ]
                tool_output = {
                    "requires_action": True,
                    "pending_approvals": pending,
                    "created_approvals": pending_approvals,
                }
                _finish_step(conn, thread_id, run_id, tool_step, "tool_executor", "requires_action", tool_output)
                _mark_run(conn, run_id, status="requires_action")

                if _to_bool(metadata.get("dual_write", False)):
                    try:
                        mirror_run_event(
                            root,
                            "requires_action",
                            {"run_id": run_id, "pending_approvals": pending, "actor": actor},
                        )
                    except Exception:
                        pass

                return {
                    "run": get_run(conn, run_id),
                    "steps": list_run_steps(conn, run_id),
                    "citations": list_run_citations(conn, run_id),
                    "artifacts": list_run_artifacts(conn, run_id),
                    "requires_action": pending,
                }

            executable = conn.execute(
                """
                SELECT tool_call_id
                FROM tool_call
                WHERE run_id = ? AND status = 'planned'
                ORDER BY rowid ASC
                """,
                (run_id,),
            ).fetchall()

            tool_results: list[dict[str, Any]] = []
            for row in executable:
                payload = execute_tool_call(
                    conn,
                    tool_call_id=str(row["tool_call_id"]),
                    project_root=root,
                    thread_id=thread_id,
                    project_id=str(metadata.get("project_id", "")),
                )
                tool_results.append(payload)

            tool_output = {"requires_action": False, "results": tool_results}
            _finish_step(conn, thread_id, run_id, tool_step, "tool_executor", "completed", tool_output)

        synthesizer_step = _start_step(
            conn,
            run_id,
            "synthesizer",
            {
                "question": question,
                "context_chars": len(str(retrieval_output.get("context", ""))),
                "tool_results": len(tool_output.get("results", [])),
            },
        )

        tool_context = ""
        if tool_output.get("results"):
            tool_context = "\n\nTool Results:\n" + "\n".join(
                _as_json(item.get("result", item))[:1800] for item in tool_output.get("results", [])
            )
        memory_ctx = _memory_context(conn, limit=max(1, int(metadata.get("memory_context_limit", 8))))
        metadata["memory_context_items"] = len(memory_ctx.get("items", []))
        _upsert_run_metadata(conn, run_id, metadata)
        memory_context = ""
        if str(memory_ctx.get("context", "")).strip():
            memory_context = "\n\n" + str(memory_ctx.get("context", ""))

        effective_offline_only = _to_bool(metadata.get("offline_only", False)) or not _to_bool(
            metadata.get("allow_remote", allow_remote)
        )
        taskmaster = run_taskmaster(
            root=root,
            question=question,
            context=str(retrieval_output.get("context", "")) + tool_context + memory_context,
            offline_only=effective_offline_only,
            simple_qa=_to_bool(metadata.get("simple_qa", False)),
            strict_local_models=_to_bool(metadata.get("strict_local_models", True)),
            allow_extractive_fallback=_to_bool(metadata.get("allow_extractive_fallback", False)),
            local_attempts_max=max(1, int(metadata.get("local_attempts_max", 3))),
            preferred_provider=str(metadata.get("preferred_provider", provider)),
            local_base_urls=dict(metadata.get("local_base_urls", {})),
            local_models=dict(metadata.get("local_models", {})),
            codex_base_url=str(metadata.get("codex_base_url", "https://api.openai.com/v1")),
            codex_model=str(metadata.get("codex_model", "gpt-5")),
            user_id=str(metadata.get("user_id", "default")),
            timeout_s=max(3, int(metadata.get("timeout_s", 40))),
        )

        synth_output = {
            "ok": _to_bool(taskmaster.get("ok", True)),
            "failure_code": str(taskmaster.get("failure_code", "")),
            "next_steps": list(taskmaster.get("next_steps", [])),
            "answer": str(taskmaster.get("answer", "")).strip(),
            "provider_used": str(taskmaster.get("provider_used", "")),
            "attempts": list(taskmaster.get("attempts", [])),
            "online_prompt_required": _to_bool(taskmaster.get("online_prompt_required", False)),
            "route_policy": str(taskmaster.get("route_policy", "offline_3_then_online_1")),
        }
        _finish_step(
            conn,
            thread_id,
            run_id,
            synthesizer_step,
            "synthesizer",
            "completed" if bool(synth_output.get("ok", True)) else "failed",
            synth_output,
        )

        recorder_step = _start_step(
            conn,
            run_id,
            "recorder",
            {"answer_chars": len(str(synth_output.get("answer", "")))},
        )

        assistant_message = create_message(
            conn,
            thread_id=thread_id,
            role="assistant",
            content=str(synth_output.get("answer", "")).strip() or "No answer generated.",
            metadata={
                "provider_used": synth_output.get("provider_used", ""),
                "run_id": run_id,
                "failure_code": synth_output.get("failure_code", ""),
                "taskmaster_ok": bool(synth_output.get("ok", True)),
            },
        )

        artifact = {
            "artifact_id": new_id("artifact"),
            "thread_id": thread_id,
            "run_id": run_id,
            "kind": "answer",
            "uri": f"db://run/{run_id}/assistant_message/{assistant_message['message_id']}",
            "mime": "text/plain",
            "sha256": None,
            "bytes": len(str(assistant_message["content"]).encode("utf-8")),
            "created_at": _now_ts(),
            "metadata_json": _as_json(
                {
                    "message_id": assistant_message["message_id"],
                    "provider_used": synth_output.get("provider_used", ""),
                }
            ),
        }
        with transaction(conn):
            conn.execute(
                """
                INSERT INTO artifact(artifact_id, thread_id, run_id, kind, uri, mime, sha256, bytes, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact["artifact_id"],
                    artifact["thread_id"],
                    artifact["run_id"],
                    artifact["kind"],
                    artifact["uri"],
                    artifact["mime"],
                    artifact["sha256"],
                    artifact["bytes"],
                    artifact["created_at"],
                    artifact["metadata_json"],
                ),
            )

        _finish_step(
            conn,
            thread_id,
            run_id,
            recorder_step,
            "recorder",
            "completed",
            {
                "message_id": assistant_message["message_id"],
                "artifact_id": artifact["artifact_id"],
                "citations": len(list_run_citations(conn, run_id)),
            },
        )

        if bool(synth_output.get("ok", True)):
            _mark_run(conn, run_id, status="completed")
        else:
            _mark_run(
                conn,
                run_id,
                status="failed",
                error=str(synth_output.get("failure_code", "taskmaster_failed")) or "taskmaster_failed",
            )

        if _to_bool(metadata.get("dual_write", False)):
            try:
                if bool(synth_output.get("ok", True)):
                    mirror_run_event(
                        root,
                        "completed",
                        {
                            "run_id": run_id,
                            "thread_id": thread_id,
                            "provider_used": synth_output.get("provider_used", ""),
                            "actor": actor,
                        },
                    )
                    mirror_answer_memory(
                        root,
                        question=question,
                        answer=str(assistant_message["content"]),
                        metadata={
                            "run_id": run_id,
                            "thread_id": thread_id,
                            "provider_used": synth_output.get("provider_used", ""),
                        },
                    )
                else:
                    mirror_run_event(
                        root,
                        "failed",
                        {
                            "run_id": run_id,
                            "thread_id": thread_id,
                            "failure_code": synth_output.get("failure_code", ""),
                            "provider_used": synth_output.get("provider_used", ""),
                            "actor": actor,
                        },
                    )
            except Exception:
                pass

        return {
            "run": get_run(conn, run_id),
            "steps": list_run_steps(conn, run_id),
            "citations": list_run_citations(conn, run_id),
            "artifacts": list_run_artifacts(conn, run_id),
            "assistant_message": assistant_message,
            "taskmaster": synth_output,
        }
    except Exception as exc:
        _mark_run(conn, run_id, status="failed", error=str(exc))
        if _to_bool(metadata.get("dual_write", False)):
            try:
                mirror_run_event(root, "failed", {"run_id": run_id, "error": str(exc), "actor": actor})
            except Exception:
                pass
        raise


def resume_run(
    root: Path,
    conn: sqlite3.Connection,
    run_id: str,
    actor: str = "ai3",
    allow_remote: bool = True,
) -> dict[str, Any]:
    run = get_run(conn, run_id)
    if run["status"] not in {"requires_action", "queued", "running"}:
        return {
            "run": run,
            "steps": list_run_steps(conn, run_id),
            "citations": list_run_citations(conn, run_id),
            "artifacts": list_run_artifacts(conn, run_id),
            "message": f"run status {run['status']} does not require resume",
        }

    return execute_run(root=root, conn=conn, run_id=run_id, actor=actor, allow_remote=allow_remote)
