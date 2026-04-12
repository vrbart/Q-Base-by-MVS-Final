"""Audit log utilities for CCBS offline AI admin actions."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .ai_storage import ai2_dir


def _db_path(root: Path) -> Path:
    out_dir = ai2_dir(root) / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "audit.db"


@contextmanager
def _connect(path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path)
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


def init_audit_db(root: Path) -> None:
    with _connect(_db_path(root)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                details_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def log_event(root: Path, event_type: str, actor: str, details: dict[str, Any] | None = None) -> None:
    init_audit_db(root)
    payload = json.dumps(details or {}, sort_keys=True, separators=(",", ":"))
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with _connect(_db_path(root)) as conn:
        conn.execute(
            "INSERT INTO events(ts, event_type, actor, details_json) VALUES (?, ?, ?, ?)",
            (now, event_type.strip() or "unknown", actor.strip() or "system", payload),
        )
        conn.commit()


def list_events(root: Path, limit: int = 100, event_type: str = "") -> list[dict[str, Any]]:
    init_audit_db(root)
    query = "SELECT ts, event_type, actor, details_json FROM events"
    params: tuple[Any, ...]
    if event_type.strip():
        query += " WHERE event_type = ?"
        query += " ORDER BY event_id DESC LIMIT ?"
        params = (event_type.strip(), max(1, int(limit)))
    else:
        query += " ORDER BY event_id DESC LIMIT ?"
        params = (max(1, int(limit)),)

    out: list[dict[str, Any]] = []
    with _connect(_db_path(root)) as conn:
        rows = conn.execute(query, params).fetchall()
    for row in rows:
        out.append(
            {
                "ts": str(row["ts"]),
                "event_type": str(row["event_type"]),
                "actor": str(row["actor"]),
                "details": json.loads(str(row["details_json"]) or "{}"),
            }
        )
    return out
