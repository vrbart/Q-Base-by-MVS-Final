"""Approval workflow for tool calls."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..db import new_id, utc_now


def request_tool_approval(conn: sqlite3.Connection, run_id: str, tool_call_id: str, rationale: str = "") -> dict[str, Any]:
    now = utc_now()
    approval_id = new_id("approval")
    conn.execute(
        """
        INSERT INTO approval(approval_id, run_id, tool_call_id, requested_at, approved_at, approved_by, decision, rationale)
        VALUES (?, ?, ?, ?, NULL, NULL, 'pending', ?)
        """,
        (approval_id, run_id, tool_call_id, now, rationale.strip()),
    )
    conn.execute("UPDATE tool_call SET approval_id = ?, status = 'blocked' WHERE tool_call_id = ?", (approval_id, tool_call_id))
    conn.commit()
    return {
        "approval_id": approval_id,
        "run_id": run_id,
        "tool_call_id": tool_call_id,
        "decision": "pending",
        "requested_at": now,
    }


def _set_decision(conn: sqlite3.Connection, tool_call_id: str, decision: str, approved_by: str, rationale: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT approval_id, run_id
        FROM approval
        WHERE tool_call_id = ?
        ORDER BY requested_at DESC
        LIMIT 1
        """,
        (tool_call_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"approval not found for tool_call_id={tool_call_id}")
    approval_id = str(row["approval_id"])
    now = utc_now()
    conn.execute(
        """
        UPDATE approval
        SET decision = ?, approved_at = ?, approved_by = ?, rationale = ?
        WHERE approval_id = ?
        """,
        (decision, now, approved_by, rationale, approval_id),
    )
    next_status = "planned" if decision == "approved" else "cancelled"
    conn.execute("UPDATE tool_call SET status = ? WHERE tool_call_id = ?", (next_status, tool_call_id))
    conn.commit()
    return {
        "approval_id": approval_id,
        "tool_call_id": tool_call_id,
        "decision": decision,
        "approved_by": approved_by,
        "approved_at": now,
    }


def approve_tool_call(conn: sqlite3.Connection, tool_call_id: str, approved_by: str = "user", rationale: str = "") -> dict[str, Any]:
    return _set_decision(conn, tool_call_id=tool_call_id, decision="approved", approved_by=approved_by, rationale=rationale)


def reject_tool_call(conn: sqlite3.Connection, tool_call_id: str, approved_by: str = "user", rationale: str = "") -> dict[str, Any]:
    return _set_decision(conn, tool_call_id=tool_call_id, decision="rejected", approved_by=approved_by, rationale=rationale)
