"""Ordered SQL migrations for ai3 runtime database."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


MIGRATION_PREFIX = "000"


def _runtime_dir(root: Path) -> Path:
    out = root / ".ccbs" / "ai3"
    out.mkdir(parents=True, exist_ok=True)
    return out


def runtime_db_path(root: Path) -> Path:
    return _runtime_dir(root) / "runtime.db"


def _migration_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def _schema_sql() -> str:
    return (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")


def _normalize_sql(raw: str) -> str:
    text = raw
    if "@@SCHEMA@@" in text:
        text = text.replace("@@SCHEMA@@", _schema_sql())
    return text


@contextmanager
def _connect(path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    out: set[str] = set()
    for row in rows:
        try:
            out.add(str(row[1]))
        except Exception:
            continue
    return out


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_ddl: str) -> None:
    column_name = str(column_ddl.split(" ", 1)[0]).strip()
    if not column_name:
        return
    if column_name in _table_columns(conn, table_name):
        return
    try:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}")
    except sqlite3.OperationalError as exc:
        # Concurrent startup can race on ALTER TABLE; treat duplicate-column as idempotent.
        if "duplicate column name" in str(exc).lower():
            return
        raise


def _ensure_wave_a_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vault_source (
          source_id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          priority TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          metadata_json TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vault_package (
          package_id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL,
          zip_relpath TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1,
          language TEXT,
          license TEXT,
          metadata_json TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY(source_id) REFERENCES vault_source(source_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS citation_verification (
          verification_id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          citation_id TEXT NOT NULL,
          status TEXT NOT NULL,
          reason TEXT NOT NULL,
          verified_at TEXT NOT NULL,
          details_json TEXT,
          FOREIGN KEY(run_id) REFERENCES run(run_id),
          FOREIGN KEY(citation_id) REFERENCES citation(citation_id)
        )
        """
    )

    _ensure_column(conn, "zip_archive", "source_id TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "zip_archive", "package_id TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "zip_archive", "vault_root TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "zip_archive", "active INTEGER NOT NULL DEFAULT 1")

    _ensure_column(conn, "zip_entry", "package_id TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "zip_entry", "entry_sha256 TEXT")
    _ensure_column(conn, "zip_entry", "parse_status TEXT NOT NULL DEFAULT 'pending'")
    _ensure_column(conn, "zip_entry", "parse_error TEXT NOT NULL DEFAULT ''")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_zip_archive_source_active ON zip_archive(source_id, active)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_zip_entry_package_inner ON zip_entry(package_id, inner_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_citation_verification_run_status ON citation_verification(run_id, status)")


def current_version(root: Path) -> int:
    db = runtime_db_path(root)
    if not db.exists():
        return 0
    with _connect(db) as conn:
        row = conn.execute("PRAGMA user_version").fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def migration_files() -> list[tuple[int, Path]]:
    rows: list[tuple[int, Path]] = []
    for path in sorted(_migration_dir().glob("*.sql")):
        stem = path.stem
        parts = stem.split("_", 1)
        if not parts or not parts[0].isdigit():
            continue
        rows.append((int(parts[0]), path))
    return rows


def migrate_runtime(root: Path) -> dict[str, object]:
    db = runtime_db_path(root)
    db.parent.mkdir(parents=True, exist_ok=True)

    applied: list[int] = []
    with _connect(db) as conn:
        row = conn.execute("PRAGMA user_version").fetchone()
        version = int(row[0] if row else 0)

        for number, path in migration_files():
            if number <= version:
                continue
            sql = _normalize_sql(path.read_text(encoding="utf-8"))
            try:
                conn.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + sql
                    + f"\nPRAGMA user_version = {int(number)};\n"
                    + "COMMIT;\n"
                )
            except Exception:
                conn.execute("ROLLBACK;")
                raise
            version = number
            applied.append(number)

        _ensure_wave_a_schema(conn)

    return {"db_path": str(db), "version": version, "applied": applied}
