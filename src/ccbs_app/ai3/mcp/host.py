"""MCP host execution runtime."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from ..db import utc_now
from .policy import evaluate_tool_policy
from .servers.filesystem import read_file, write_file
from .servers.shell import exec_shell
from .servers.zip_vault import list_entries, read_entry


def _canonical_args(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"))


def _cache_key(tool_name: str, arguments: dict[str, Any]) -> str:
    payload = f"{tool_name}|{_canonical_args(arguments)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_cache(conn, key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT result_json, created_at, ttl_seconds
        FROM tool_cache
        WHERE cache_key = ?
        """,
        (key,),
    ).fetchone()
    if row is None:
        return None
    ttl = row["ttl_seconds"]
    if ttl is not None:
        try:
            created = dt.datetime.fromisoformat(str(row["created_at"]))
            if created + dt.timedelta(seconds=int(ttl)) < dt.datetime.now(dt.timezone.utc):
                return None
        except Exception:
            return None
    return json.loads(str(row["result_json"]) or "{}")


def _set_cache(conn, key: str, tool_name: str, arguments: dict[str, Any], result: dict[str, Any], ttl_seconds: int | None = None) -> None:
    conn.execute(
        """
        INSERT INTO tool_cache(cache_key, tool_name, arguments_json, result_json, created_at, ttl_seconds)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
          result_json = excluded.result_json,
          created_at = excluded.created_at,
          ttl_seconds = excluded.ttl_seconds
        """,
        (key, tool_name, _canonical_args(arguments), json.dumps(result, sort_keys=True), utc_now(), ttl_seconds),
    )


def _dispatch(tool_name: str, arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    args = dict(arguments)
    if tool_name == "filesystem.read_file":
        return read_file(path=str(args.get("path", "")), max_bytes=int(args.get("max_bytes", 65536)))
    if tool_name == "filesystem.write_file":
        return write_file(path=str(args.get("path", "")), content=str(args.get("content", "")), append=bool(args.get("append", False)))
    if tool_name == "shell.exec":
        cwd = str(args.get("cwd", "")).strip()
        if cwd and not Path(cwd).is_absolute():
            cwd = str((project_root / cwd).resolve())
        return exec_shell(command=str(args.get("command", "")), cwd=cwd, timeout_s=int(args.get("timeout_s", 30)))
    if tool_name == "zip_vault.list_entries":
        return list_entries(zip_path=str(args.get("zip_path", "")), prefix=str(args.get("prefix", "")), limit=int(args.get("limit", 200)))
    if tool_name == "zip_vault.read_entry":
        return read_entry(
            zip_path=str(args.get("zip_path", "")),
            inner_path=str(args.get("inner_path", "")),
            max_bytes=int(args.get("max_bytes", 131072)),
        )
    raise ValueError(f"unsupported tool: {tool_name}")


def execute_tool_call(conn, tool_call_id: str, project_root: Path, thread_id: str = "", project_id: str = "") -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT tool_call_id, tool_name, arguments_json, status
        FROM tool_call
        WHERE tool_call_id = ?
        """,
        (tool_call_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"tool call not found: {tool_call_id}")
    tool_name = str(row["tool_name"])
    arguments = json.loads(str(row["arguments_json"]) or "{}")

    policy = evaluate_tool_policy(conn, tool_name=tool_name, arguments=arguments, thread_id=thread_id, project_id=project_id)
    if not bool(policy.get("allowed", True)):
        payload = {
            "ok": False,
            "error": "policy_denied",
            "policy": policy,
            "policy_reason": str(policy.get("reason", "policy_denied")),
        }
        conn.execute(
            "UPDATE tool_call SET status = 'failed', result_json = ?, completed_at = ? WHERE tool_call_id = ?",
            (json.dumps(payload, sort_keys=True), utc_now(), tool_call_id),
        )
        conn.commit()
        return payload

    key = _cache_key(tool_name, arguments)
    cached = _get_cache(conn, key)
    if cached is not None:
        payload = {"ok": True, "cached": True, "result": cached}
        conn.execute(
            "UPDATE tool_call SET status = 'succeeded', result_json = ?, completed_at = ? WHERE tool_call_id = ?",
            (json.dumps(payload, sort_keys=True), utc_now(), tool_call_id),
        )
        conn.commit()
        return payload

    conn.execute("UPDATE tool_call SET status = 'running', started_at = ? WHERE tool_call_id = ?", (utc_now(), tool_call_id))
    conn.commit()
    try:
        result = _dispatch(tool_name=tool_name, arguments=arguments, project_root=project_root)
        _set_cache(conn, key=key, tool_name=tool_name, arguments=arguments, result=result)
        payload = {"ok": True, "cached": False, "result": result}
        conn.execute(
            "UPDATE tool_call SET status = 'succeeded', result_json = ?, completed_at = ? WHERE tool_call_id = ?",
            (json.dumps(payload, sort_keys=True), utc_now(), tool_call_id),
        )
        conn.commit()
        return payload
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "error": str(exc)}
        conn.execute(
            "UPDATE tool_call SET status = 'failed', result_json = ?, completed_at = ? WHERE tool_call_id = ?",
            (json.dumps(payload, sort_keys=True), utc_now(), tool_call_id),
        )
        conn.commit()
        return payload
