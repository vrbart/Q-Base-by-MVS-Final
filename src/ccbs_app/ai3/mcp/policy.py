"""Policy evaluation wrappers for MCP tool calls."""

from __future__ import annotations

from typing import Any

from ..policy import evaluate_policy


def _rule_type(tool_name: str) -> str:
    if tool_name.startswith("filesystem.read"):
        return "fs_read"
    if tool_name.startswith("filesystem.write"):
        return "fs_write"
    if tool_name.startswith("shell."):
        return "shell"
    if tool_name.startswith("zip_vault."):
        return "zip_extract"
    return "tool"


def target_string(tool_name: str, arguments: dict[str, Any]) -> str:
    if "path" in arguments:
        return str(arguments.get("path", ""))
    if "zip_path" in arguments and "inner_path" not in arguments:
        return str(arguments.get("zip_path", ""))
    if "zip_path" in arguments and "inner_path" in arguments:
        return f"{arguments.get('zip_path')}::{arguments.get('inner_path')}"
    if "command" in arguments:
        return str(arguments.get("command", ""))
    return tool_name


def evaluate_tool_policy(conn, tool_name: str, arguments: dict[str, Any], thread_id: str = "", project_id: str = "") -> dict[str, Any]:
    return evaluate_policy(
        conn=conn,
        rule_type=_rule_type(tool_name),
        target=target_string(tool_name, arguments),
        thread_id=thread_id,
        project_id=project_id,
    )
