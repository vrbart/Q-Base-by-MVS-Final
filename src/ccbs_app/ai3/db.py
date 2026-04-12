"""ai3 runtime database helpers."""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Iterator

from .migrations import migrate_runtime


def runtime_dir(root: Path) -> Path:
    out = root / ".ccbs" / "ai3"
    out.mkdir(parents=True, exist_ok=True)
    return out


def runtime_db_path(root: Path) -> Path:
    return runtime_dir(root) / "runtime.db"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    clean = "".join(ch for ch in prefix.lower().strip() if ch.isalnum() or ch in {"_", "-"})
    clean = clean or "id"
    return f"{clean}_{uuid.uuid4().hex}"


def connect_runtime(root: Path) -> sqlite3.Connection:
    def _configure(conn: sqlite3.Connection, *, prefer_wal: bool) -> None:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=4000;")
        if prefer_wal:
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
            except sqlite3.OperationalError:
                conn.execute("PRAGMA journal_mode=DELETE;")
        else:
            conn.execute("PRAGMA journal_mode=DELETE;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

    def _connect(*, prefer_wal: bool) -> sqlite3.Connection:
        conn = sqlite3.connect(runtime_db_path(root), timeout=8.0)
        _configure(conn, prefer_wal=prefer_wal)
        return conn

    def _looks_recoverable(exc: Exception) -> bool:
        raw = str(exc).strip().lower()
        return any(
            needle in raw
            for needle in (
                "disk i/o error",
                "database is malformed",
                "malformed",
                "unable to open database file",
                "database disk image is malformed",
            )
        )

    def _rotate_corrupt_runtime() -> None:
        path = runtime_db_path(root)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
        for suffix in ("", "-wal", "-shm"):
            src = Path(f"{path}{suffix}") if suffix else path
            if not src.exists():
                continue
            dst = runtime_dir(root) / f"runtime.corrupt.{stamp}{suffix or '.db'}"
            try:
                os.replace(src, dst)
            except OSError:
                # If the file is currently locked or inaccessible, keep original and let caller fail.
                return

    try:
        migrate_runtime(root)
        return _connect(prefer_wal=True)
    except sqlite3.OperationalError as exc:
        if not _looks_recoverable(exc):
            raise
        _rotate_corrupt_runtime()
        migrate_runtime(root)
        return _connect(prefer_wal=False)


@contextlib.contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
