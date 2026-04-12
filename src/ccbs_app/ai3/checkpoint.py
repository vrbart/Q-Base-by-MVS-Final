"""Checkpoint persistence helpers for ai3 runs."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import new_id, utc_now


def create_checkpoint(
    conn: sqlite3.Connection,
    thread_id: str,
    run_id: str,
    step_id: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    row = {
        "checkpoint_id": new_id("chk"),
        "thread_id": thread_id,
        "run_id": run_id,
        "step_id": step_id,
        "state_json": json.dumps(state, sort_keys=True),
        "created_at": utc_now(),
    }
    conn.execute(
        """
        INSERT INTO checkpoint(checkpoint_id, thread_id, run_id, step_id, state_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            row["checkpoint_id"],
            row["thread_id"],
            row["run_id"],
            row["step_id"],
            row["state_json"],
            row["created_at"],
        ),
    )
    return row


def list_checkpoints(conn: sqlite3.Connection, run_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    cap = max(1, int(limit))
    if run_id.strip():
        rows = conn.execute(
            """
            SELECT checkpoint_id, thread_id, run_id, step_id, state_json, created_at
            FROM checkpoint
            WHERE run_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (run_id.strip(), cap),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT checkpoint_id, thread_id, run_id, step_id, state_json, created_at
            FROM checkpoint
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (cap,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "checkpoint_id": str(row["checkpoint_id"]),
                "thread_id": str(row["thread_id"]),
                "run_id": str(row["run_id"]),
                "step_id": str(row["step_id"]),
                "state": json.loads(str(row["state_json"]) or "{}"),
                "created_at": str(row["created_at"]),
            }
        )
    return out


def get_checkpoint(conn: sqlite3.Connection, checkpoint_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT checkpoint_id, thread_id, run_id, step_id, state_json, created_at
        FROM checkpoint
        WHERE checkpoint_id = ?
        """,
        (checkpoint_id.strip(),),
    ).fetchone()
    if row is None:
        return None
    return {
        "checkpoint_id": str(row["checkpoint_id"]),
        "thread_id": str(row["thread_id"]),
        "run_id": str(row["run_id"]),
        "step_id": str(row["step_id"]),
        "state": json.loads(str(row["state_json"]) or "{}"),
        "created_at": str(row["created_at"]),
    }
