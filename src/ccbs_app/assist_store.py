"""SQLite-backed storage for accessibility assistant phase-1."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .assist_types import AssistAction, AssistCommand, AssistProfile, AssistReceipt


def _assist_dir(root: Path) -> Path:
    out = root / ".ccbs" / "assist"
    out.mkdir(parents=True, exist_ok=True)
    return out


def assist_db_path(root: Path) -> Path:
    return _assist_dir(root) / "assist.db"


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _cursor_lastrowid(cursor: sqlite3.Cursor) -> int:
    row_id = cursor.lastrowid
    if row_id is None:
        raise RuntimeError("database insert did not return lastrowid")
    return int(row_id)


def init_store(root: Path) -> None:
    db = assist_db_path(root)
    with _connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id TEXT PRIMARY KEY,
                game_name TEXT NOT NULL,
                offline_only INTEGER NOT NULL,
                allow_multiplayer INTEGER NOT NULL,
                ack_offline_single_player INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS commands (
                command_id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT NOT NULL,
                name TEXT NOT NULL,
                cooldown_ms INTEGER NOT NULL DEFAULT 0,
                confirm_level TEXT NOT NULL DEFAULT 'none',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (profile_id) REFERENCES profiles(profile_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS phrases (
                phrase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id INTEGER NOT NULL,
                phrase_text TEXT NOT NULL,
                phrase_norm TEXT NOT NULL,
                FOREIGN KEY (command_id) REFERENCES commands(command_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                order_index INTEGER NOT NULL,
                FOREIGN KEY (command_id) REFERENCES commands(command_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                receipt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                transcript_normalized TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                command_name TEXT NOT NULL,
                action_summary TEXT NOT NULL,
                confirm_used INTEGER NOT NULL,
                metadata TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _to_profile(row: sqlite3.Row) -> AssistProfile:
    return AssistProfile(
        profile_id=str(row["profile_id"]),
        game_name=str(row["game_name"]),
        offline_only=bool(int(row["offline_only"])),
        allow_multiplayer=bool(int(row["allow_multiplayer"])),
        ack_offline_single_player=bool(int(row["ack_offline_single_player"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def create_profile(
    root: Path,
    profile_id: str,
    game_name: str,
    offline_only: bool = True,
    allow_multiplayer: bool = False,
) -> AssistProfile:
    init_store(root)
    now = _utc_now()
    pid = profile_id.strip()
    if not pid:
        raise ValueError("profile_id is required")
    if not game_name.strip():
        raise ValueError("game_name is required")

    with _connect(assist_db_path(root)) as conn:
        conn.execute(
            """
            INSERT INTO profiles(profile_id, game_name, offline_only, allow_multiplayer, ack_offline_single_player, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (pid, game_name.strip(), int(bool(offline_only)), int(bool(allow_multiplayer)), now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (pid,)).fetchone()
    if row is None:
        raise RuntimeError("failed to create profile")
    return _to_profile(row)


def ack_profile(root: Path, profile_id: str, offline_single_player: bool) -> AssistProfile:
    init_store(root)
    pid = profile_id.strip()
    with _connect(assist_db_path(root)) as conn:
        row = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (pid,)).fetchone()
        if row is None:
            raise ValueError(f"profile not found: {profile_id}")
        conn.execute(
            "UPDATE profiles SET ack_offline_single_player = ?, updated_at = ? WHERE profile_id = ?",
            (1 if offline_single_player else 0, _utc_now(), pid),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (pid,)).fetchone()
    if updated is None:
        raise RuntimeError("failed to update profile acknowledgement")
    return _to_profile(updated)


def get_profile(root: Path, profile_id: str) -> AssistProfile | None:
    init_store(root)
    with _connect(assist_db_path(root)) as conn:
        row = conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id.strip(),)).fetchone()
    return _to_profile(row) if row is not None else None


def list_profiles(root: Path) -> list[AssistProfile]:
    init_store(root)
    with _connect(assist_db_path(root)) as conn:
        rows = conn.execute("SELECT * FROM profiles ORDER BY profile_id").fetchall()
    return [_to_profile(row) for row in rows]


def _to_actions(rows: list[sqlite3.Row]) -> list[AssistAction]:
    return [
        AssistAction(
            action_type=str(row["action_type"]),
            payload=str(row["payload"]),
            order_index=int(row["order_index"]),
        )
        for row in rows
    ]


def _to_command(root_conn: sqlite3.Connection, row: sqlite3.Row) -> AssistCommand:
    cid = int(row["command_id"])
    phrase_rows = root_conn.execute(
        "SELECT phrase_text FROM phrases WHERE command_id = ? ORDER BY phrase_id",
        (cid,),
    ).fetchall()
    action_rows = root_conn.execute(
        "SELECT action_type, payload, order_index FROM actions WHERE command_id = ? ORDER BY order_index, action_id",
        (cid,),
    ).fetchall()
    return AssistCommand(
        command_id=cid,
        profile_id=str(row["profile_id"]),
        name=str(row["name"]),
        phrases=[str(item["phrase_text"]) for item in phrase_rows],
        actions=_to_actions(action_rows),
        cooldown_ms=max(0, int(row["cooldown_ms"])),
        confirm_level=str(row["confirm_level"]),
        enabled=bool(int(row["enabled"])),
    )


def add_command(
    root: Path,
    profile_id: str,
    name: str,
    phrase: str,
    phrase_norm: str,
    actions: list[tuple[str, str]],
    cooldown_ms: int,
    confirm_level: str,
) -> AssistCommand:
    init_store(root)
    pid = profile_id.strip()
    if not pid:
        raise ValueError("profile_id is required")
    if not name.strip():
        raise ValueError("command name is required")
    if not phrase.strip():
        raise ValueError("phrase is required")
    if not actions:
        raise ValueError("at least one action is required")
    if confirm_level not in {"none", "require"}:
        raise ValueError("confirm_level must be 'none' or 'require'")

    with _connect(assist_db_path(root)) as conn:
        profile = conn.execute("SELECT profile_id FROM profiles WHERE profile_id = ?", (pid,)).fetchone()
        if profile is None:
            raise ValueError(f"profile not found: {profile_id}")

        now = _utc_now()
        cur = conn.execute(
            """
            INSERT INTO commands(profile_id, name, cooldown_ms, confirm_level, enabled, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (pid, name.strip(), max(0, int(cooldown_ms)), confirm_level, now),
        )
        command_id = _cursor_lastrowid(cur)
        conn.execute(
            "INSERT INTO phrases(command_id, phrase_text, phrase_norm) VALUES (?, ?, ?)",
            (command_id, phrase.strip(), phrase_norm.strip()),
        )
        for idx, (action_type, payload) in enumerate(actions, 1):
            conn.execute(
                "INSERT INTO actions(command_id, action_type, payload, order_index) VALUES (?, ?, ?, ?)",
                (command_id, action_type, payload, idx),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM commands WHERE command_id = ?", (command_id,)).fetchone()
    if row is None:
        raise RuntimeError("failed to create command")
    with _connect(assist_db_path(root)) as conn:
        return _to_command(conn, row)


def list_commands(root: Path, profile_id: str) -> list[AssistCommand]:
    init_store(root)
    pid = profile_id.strip()
    with _connect(assist_db_path(root)) as conn:
        rows = conn.execute(
            "SELECT * FROM commands WHERE profile_id = ? ORDER BY command_id",
            (pid,),
        ).fetchall()
        return [_to_command(conn, row) for row in rows]


def record_receipt(root: Path, receipt: AssistReceipt) -> None:
    init_store(root)
    with _connect(assist_db_path(root)) as conn:
        conn.execute(
            """
            INSERT INTO receipts(ts, profile_id, transcript_normalized, status, reason, command_name, action_summary, confirm_used, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt.ts,
                receipt.profile_id,
                receipt.transcript_normalized,
                receipt.status,
                receipt.reason,
                receipt.command_name,
                receipt.action_summary,
                int(bool(receipt.confirm_used)),
                json.dumps(receipt.metadata, separators=(",", ":"), sort_keys=True),
            ),
        )
        conn.commit()


def list_receipts(root: Path, profile_id: str | None = None, limit: int = 20) -> list[AssistReceipt]:
    init_store(root)
    cap = max(1, int(limit))
    with _connect(assist_db_path(root)) as conn:
        if profile_id:
            rows = conn.execute(
                """
                SELECT ts, profile_id, transcript_normalized, status, reason, command_name, action_summary, confirm_used, metadata
                FROM receipts
                WHERE profile_id = ?
                ORDER BY receipt_id DESC
                LIMIT ?
                """,
                (profile_id, cap),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT ts, profile_id, transcript_normalized, status, reason, command_name, action_summary, confirm_used, metadata
                FROM receipts
                ORDER BY receipt_id DESC
                LIMIT ?
                """,
                (cap,),
            ).fetchall()

    out: list[AssistReceipt] = []
    for row in rows:
        out.append(
            AssistReceipt(
                ts=str(row["ts"]),
                profile_id=str(row["profile_id"]),
                transcript_normalized=str(row["transcript_normalized"]),
                status=str(row["status"]),
                reason=str(row["reason"]),
                command_name=str(row["command_name"]),
                action_summary=str(row["action_summary"]),
                confirm_used=bool(int(row["confirm_used"])),
                metadata=json.loads(str(row["metadata"]) or "{}"),
            )
        )
    return out


def last_command_receipt(root: Path, profile_id: str, command_name: str) -> AssistReceipt | None:
    init_store(root)
    with _connect(assist_db_path(root)) as conn:
        row = conn.execute(
            """
            SELECT ts, profile_id, transcript_normalized, status, reason, command_name, action_summary, confirm_used, metadata
            FROM receipts
            WHERE profile_id = ? AND command_name = ?
            ORDER BY receipt_id DESC
            LIMIT 1
            """,
            (profile_id, command_name),
        ).fetchone()
    if row is None:
        return None
    return AssistReceipt(
        ts=str(row["ts"]),
        profile_id=str(row["profile_id"]),
        transcript_normalized=str(row["transcript_normalized"]),
        status=str(row["status"]),
        reason=str(row["reason"]),
        command_name=str(row["command_name"]),
        action_summary=str(row["action_summary"]),
        confirm_used=bool(int(row["confirm_used"])),
        metadata=json.loads(str(row["metadata"]) or "{}"),
    )


def export_profile(root: Path, profile_id: str, out_path: Path) -> Path:
    profile = get_profile(root, profile_id)
    if profile is None:
        raise ValueError(f"profile not found: {profile_id}")
    commands = list_commands(root, profile_id)
    payload = {
        "version": "assist-profile-v1",
        "profile": {
            "profile_id": profile.profile_id,
            "game_name": profile.game_name,
            "offline_only": profile.offline_only,
            "allow_multiplayer": profile.allow_multiplayer,
            "ack_offline_single_player": profile.ack_offline_single_player,
        },
        "commands": [
            {
                "name": cmd.name,
                "phrases": cmd.phrases,
                "cooldown_ms": cmd.cooldown_ms,
                "confirm_level": cmd.confirm_level,
                "enabled": cmd.enabled,
                "actions": [
                    {
                        "type": action.action_type,
                        "payload": action.payload,
                        "order_index": action.order_index,
                    }
                    for action in cmd.actions
                ],
            }
            for cmd in commands
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def import_profile(root: Path, in_path: Path, profile_id_override: str = "") -> AssistProfile:
    init_store(root)
    payload = json.loads(in_path.read_text(encoding="utf-8"))
    profile_payload = payload.get("profile", {})
    if not isinstance(profile_payload, dict):
        raise ValueError("invalid profile payload")

    profile_id = profile_id_override.strip() or str(profile_payload.get("profile_id", "")).strip()
    if not profile_id:
        raise ValueError("profile_id is required")

    game_name = str(profile_payload.get("game_name", "")).strip()
    if not game_name:
        raise ValueError("game_name is required")

    offline_only = bool(profile_payload.get("offline_only", True))
    allow_multiplayer = bool(profile_payload.get("allow_multiplayer", False))
    ack = bool(profile_payload.get("ack_offline_single_player", False))

    with _connect(assist_db_path(root)) as conn:
        existing = conn.execute("SELECT profile_id FROM profiles WHERE profile_id = ?", (profile_id,)).fetchone()
        now = _utc_now()
        if existing is None:
            conn.execute(
                """
                INSERT INTO profiles(profile_id, game_name, offline_only, allow_multiplayer, ack_offline_single_player, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (profile_id, game_name, int(offline_only), int(allow_multiplayer), int(ack), now, now),
            )
        else:
            conn.execute(
                """
                UPDATE profiles
                SET game_name = ?, offline_only = ?, allow_multiplayer = ?, ack_offline_single_player = ?, updated_at = ?
                WHERE profile_id = ?
                """,
                (game_name, int(offline_only), int(allow_multiplayer), int(ack), now, profile_id),
            )
            # Replace commands/phrases/actions for deterministic imports.
            command_rows = conn.execute(
                "SELECT command_id FROM commands WHERE profile_id = ?",
                (profile_id,),
            ).fetchall()
            for command_row in command_rows:
                cid = int(command_row["command_id"])
                conn.execute("DELETE FROM phrases WHERE command_id = ?", (cid,))
                conn.execute("DELETE FROM actions WHERE command_id = ?", (cid,))
            conn.execute("DELETE FROM commands WHERE profile_id = ?", (profile_id,))

        command_payloads = payload.get("commands", [])
        if not isinstance(command_payloads, list):
            raise ValueError("commands must be a list")

        for item in command_payloads:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            confirm_level = str(item.get("confirm_level", "none")).strip() or "none"
            if confirm_level not in {"none", "require"}:
                confirm_level = "none"
            cooldown_ms = max(0, int(item.get("cooldown_ms", 0)))
            enabled = 1 if bool(item.get("enabled", True)) else 0
            created_at = _utc_now()
            cur = conn.execute(
                """
                INSERT INTO commands(profile_id, name, cooldown_ms, confirm_level, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (profile_id, name, cooldown_ms, confirm_level, enabled, created_at),
            )
            command_id = _cursor_lastrowid(cur)

            phrases = item.get("phrases", [])
            if isinstance(phrases, list):
                for phrase in phrases:
                    text = str(phrase).strip()
                    if not text:
                        continue
                    norm = " ".join(text.lower().split())
                    conn.execute(
                        "INSERT INTO phrases(command_id, phrase_text, phrase_norm) VALUES (?, ?, ?)",
                        (command_id, text, norm),
                    )

            actions = item.get("actions", [])
            if isinstance(actions, list):
                for idx, action in enumerate(actions, 1):
                    if not isinstance(action, dict):
                        continue
                    action_type = str(action.get("type", "")).strip()
                    payload_text = str(action.get("payload", "")).strip()
                    if not action_type or not payload_text:
                        continue
                    order_index = int(action.get("order_index", idx))
                    conn.execute(
                        "INSERT INTO actions(command_id, action_type, payload, order_index) VALUES (?, ?, ?, ?)",
                        (command_id, action_type, payload_text, order_index),
                    )

        conn.commit()

    profile = get_profile(root, profile_id)
    if profile is None:
        raise RuntimeError("failed to import profile")
    return profile
