"""Personalized chat-only profile persistence over ai3 memory_item."""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import new_id, transaction, utc_now
from .evolution import next_stage_target as evolution_next_stage_target
from .evolution import stage_name_from_xp

PROFILE_KEYS = [
    "chat_ui.display_name",
    "chat_ui.avatar_style",
    "chat_ui.theme",
    "chat_ui.preferred_model",
    "chat_ui.language_mode",
    "chat_ui.manual_language",
    "chat_ui.language_storage_mode",
    "chat_ui.language_external_enrichment",
    "chat_ui.tone_preset",
    "chat_ui.active_role",
    "chat_ui.card_pack",
    "chat_ui.ops_collapsed",
    "chat_ui.offline_mode",
    "chat_ui.scope_prompt_mode",
    "chat_ui.default_answer_scope",
    "chat_ui.live_output_mode",
]

DEFAULT_CHAT_PROFILE = {
    "display_name": "Owner",
    "avatar_style": "nft-core",
    "theme": "neon-deck",
    "preferred_model": "",
    "language_mode": "auto",
    "manual_language": "",
    "language_storage_mode": "auto",
    "language_external_enrichment": "false",
    "tone_preset": "balanced",
    "active_role": "core",
    "card_pack": "",
    "ops_collapsed": "true",
    "offline_mode": "guided",
    "scope_prompt_mode": "always",
    "default_answer_scope": "repo_grounded",
    "live_output_mode": "collapsed",
}

ROLE_XP_PREFIX = "chat_ui.role_xp."
ROLE_XP_KEYS = [
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


def _memory_row(conn: sqlite3.Connection, key: str, user_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT memory_id, value
        FROM memory_item
        WHERE scope = 'global' AND scope_id = ? AND key = ?
        ORDER BY updated_at DESC, created_at DESC
        LIMIT 1
        """,
        (user_id.strip() or "default", key),
    ).fetchone()


def get_chat_profile(conn: sqlite3.Connection, user_id: str = "default") -> dict[str, Any]:
    out = dict(DEFAULT_CHAT_PROFILE)
    scope_id = user_id.strip() or "default"
    for key in PROFILE_KEYS:
        row = _memory_row(conn, key=key, user_id=scope_id)
        if row is None:
            continue
        logical = key.split(".", 1)[-1]
        out[logical] = str(row["value"] or "").strip()
    return out


def set_chat_profile(conn: sqlite3.Connection, values: dict[str, Any], user_id: str = "default") -> dict[str, Any]:
    scope_id = user_id.strip() or "default"
    allowed = {key.split(".", 1)[-1]: key for key in PROFILE_KEYS}
    updates: dict[str, str] = {}
    for logical_key, full_key in allowed.items():
        if logical_key not in values:
            continue
        updates[full_key] = str(values.get(logical_key, "")).strip()

    if not updates:
        return get_chat_profile(conn, user_id=scope_id)

    now = utc_now()
    with transaction(conn):
        for full_key, value in updates.items():
            row = _memory_row(conn, key=full_key, user_id=scope_id)
            if row is None:
                conn.execute(
                    """
                    INSERT INTO memory_item(memory_id, scope, scope_id, key, value, importance, created_at, updated_at)
                    VALUES (?, 'global', ?, ?, ?, 0.8, ?, ?)
                    """,
                    (new_id("memory"), scope_id, full_key, value, now, now),
                )
            else:
                conn.execute(
                    "UPDATE memory_item SET value = ?, updated_at = ? WHERE memory_id = ?",
                    (value, now, str(row["memory_id"])),
                )
    return get_chat_profile(conn, user_id=scope_id)


def get_role_xp(conn: sqlite3.Connection, user_id: str = "default") -> dict[str, int]:
    scope_id = user_id.strip() or "default"
    rows = conn.execute(
        """
        SELECT key, value
        FROM memory_item
        WHERE scope = 'global' AND scope_id = ? AND key LIKE ?
        """,
        (scope_id, f"{ROLE_XP_PREFIX}%"),
    ).fetchall()
    out: dict[str, int] = {key: 0 for key in ROLE_XP_KEYS}
    for row in rows:
        key = str(row["key"] or "").strip()
        rid = key.removeprefix(ROLE_XP_PREFIX).strip().lower()
        if not rid:
            continue
        try:
            value = max(0, int(str(row["value"] or "0").strip() or "0"))
        except ValueError:
            value = 0
        out[rid] = value
    return out


def add_role_xp(conn: sqlite3.Connection, *, user_id: str, role_id: str, delta: int) -> int:
    scope_id = user_id.strip() or "default"
    rid = role_id.strip().lower()
    if not rid:
        return 0
    gain = max(0, int(delta))
    if gain <= 0:
        current = get_role_xp(conn, user_id=scope_id)
        return int(current.get(rid, 0))
    key = f"{ROLE_XP_PREFIX}{rid}"
    row = _memory_row(conn, key=key, user_id=scope_id)
    now = utc_now()
    current = 0
    if row is not None:
        try:
            current = max(0, int(str(row["value"] or "0").strip() or "0"))
        except ValueError:
            current = 0
    new_total = current + gain
    with transaction(conn):
        if row is None:
            conn.execute(
                """
                INSERT INTO memory_item(memory_id, scope, scope_id, key, value, importance, created_at, updated_at)
                VALUES (?, 'global', ?, ?, ?, 0.65, ?, ?)
                """,
                (new_id("memory"), scope_id, key, str(new_total), now, now),
            )
        else:
            conn.execute(
                "UPDATE memory_item SET value = ?, updated_at = ? WHERE memory_id = ?",
                (str(new_total), now, str(row["memory_id"])),
            )
    return new_total


def role_stage_from_xp(xp: int) -> str:
    return stage_name_from_xp(xp)


def next_stage_target(xp: int) -> int:
    return evolution_next_stage_target(xp)
