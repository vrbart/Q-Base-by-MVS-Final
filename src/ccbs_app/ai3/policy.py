"""Policy rule evaluation for ai3 tool execution."""

from __future__ import annotations

import fnmatch
import sqlite3
from typing import Any

from .db import new_id, utc_now


def add_policy_rule(
    conn: sqlite3.Connection,
    scope: str,
    scope_id: str,
    rule_type: str,
    effect: str,
    pattern: str,
) -> dict[str, Any]:
    payload = {
        "rule_id": new_id("rule"),
        "scope": scope,
        "scope_id": scope_id or "",
        "rule_type": rule_type.strip().lower(),
        "effect": effect.strip().lower(),
        "pattern": pattern.strip() or "*",
        "created_at": utc_now(),
    }
    conn.execute(
        """
        INSERT INTO policy_rule(rule_id, scope, scope_id, rule_type, effect, pattern, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["rule_id"],
            payload["scope"],
            payload["scope_id"] or None,
            payload["rule_type"],
            payload["effect"],
            payload["pattern"],
            payload["created_at"],
        ),
    )
    conn.commit()
    return payload


def _ordered_rules(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT rule_id, scope, scope_id, rule_type, effect, pattern, created_at
        FROM policy_rule
        ORDER BY
          CASE scope WHEN 'thread' THEN 0 WHEN 'project' THEN 1 ELSE 2 END,
          created_at DESC
        """
    ).fetchall()


def evaluate_policy(
    conn: sqlite3.Connection,
    rule_type: str,
    target: str,
    thread_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    rtype = rule_type.strip().lower()
    text = target.strip()

    for row in _ordered_rules(conn):
        row_type = str(row["rule_type"]).strip().lower()
        if row_type != rtype:
            continue
        scope = str(row["scope"])
        scope_id = str(row["scope_id"] or "")
        if scope == "thread" and scope_id and scope_id != thread_id:
            continue
        if scope == "project" and scope_id and scope_id != project_id:
            continue
        pattern = str(row["pattern"] or "*")
        if fnmatch.fnmatch(text, pattern):
            effect = str(row["effect"]).strip().lower()
            return {
                "allowed": effect == "allow",
                "effect": effect,
                "rule_id": str(row["rule_id"]),
                "scope": scope,
                "pattern": pattern,
                "reason": f"matched {rtype} rule",
            }

    # Default permit; explicit approvals still required at tool-call level.
    return {
        "allowed": True,
        "effect": "allow",
        "rule_id": "",
        "scope": "default",
        "pattern": "*",
        "reason": "default_allow",
    }
