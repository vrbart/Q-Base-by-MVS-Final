"""Seed MCP tool server and tool definition records."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _upsert_server(conn: sqlite3.Connection, server_id: str, kind: str, name: str, endpoint: str) -> None:
    conn.execute(
        """
        INSERT INTO tool_server(server_id, kind, name, endpoint, enabled, metadata_json)
        VALUES (?, ?, ?, ?, 1, ?)
        ON CONFLICT(server_id) DO UPDATE SET
          kind = excluded.kind,
          name = excluded.name,
          endpoint = excluded.endpoint,
          enabled = 1
        """,
        (server_id, kind, name, endpoint, "{}"),
    )


def _upsert_tool(conn: sqlite3.Connection, tool_name: str, server_id: str, risk: str, schema: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO tool_definition(tool_name, server_id, schema_json, risk_level, enabled)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(tool_name) DO UPDATE SET
          server_id = excluded.server_id,
          schema_json = excluded.schema_json,
          risk_level = excluded.risk_level,
          enabled = 1
        """,
        (tool_name, server_id, json.dumps(schema, sort_keys=True), risk),
    )


def seed_mcp_registry(conn: sqlite3.Connection) -> None:
    _upsert_server(conn, "mcp_fs", "mcp", "filesystem", "stdio://filesystem")
    _upsert_server(conn, "mcp_shell", "mcp", "shell", "stdio://shell")
    _upsert_server(conn, "mcp_zip", "mcp", "zip_vault", "stdio://zip_vault")

    _upsert_tool(
        conn,
        "filesystem.read_file",
        "mcp_fs",
        "low",
        {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "max_bytes": {"type": "integer"}}},
    )
    _upsert_tool(
        conn,
        "filesystem.write_file",
        "mcp_fs",
        "high",
        {
            "type": "object",
            "required": ["path", "content"],
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "append": {"type": "boolean"}},
        },
    )
    _upsert_tool(
        conn,
        "shell.exec",
        "mcp_shell",
        "high",
        {
            "type": "object",
            "required": ["command"],
            "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}, "timeout_s": {"type": "integer"}},
        },
    )
    _upsert_tool(
        conn,
        "zip_vault.list_entries",
        "mcp_zip",
        "medium",
        {
            "type": "object",
            "required": ["zip_path"],
            "properties": {"zip_path": {"type": "string"}, "prefix": {"type": "string"}, "limit": {"type": "integer"}},
        },
    )
    _upsert_tool(
        conn,
        "zip_vault.read_entry",
        "mcp_zip",
        "medium",
        {
            "type": "object",
            "required": ["zip_path", "inner_path"],
            "properties": {
                "zip_path": {"type": "string"},
                "inner_path": {"type": "string"},
                "max_bytes": {"type": "integer"},
            },
        },
    )
    conn.commit()
