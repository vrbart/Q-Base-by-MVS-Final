"""Local auth/user/token primitives for CCBS offline AI."""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .ai_storage import ai2_dir

ROLES = {"admin", "user"}


def _db_path(root: Path) -> Path:
    out = ai2_dir(root) / "auth"
    out.mkdir(parents=True, exist_ok=True)
    return out / "auth.db"


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


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _hash_password(password: str, salt_hex: str) -> str:
    data = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200_000)
    return data.hex()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_loopback_host(client_host: str) -> bool:
    host = (client_host or "").strip().lower()
    return host in {"127.0.0.1", "::1", "localhost"}


def init_auth_db(root: Path) -> None:
    with _connect(_db_path(root)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt_hex TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(username) REFERENCES users(username)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_routing_prefs (
                username TEXT NOT NULL,
                task_type TEXT NOT NULL,
                preferred_provider TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(username, task_type),
                FOREIGN KEY(username) REFERENCES users(username)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS provider_key_refs (
                user_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                keyring_service TEXT NOT NULL,
                keyring_account TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(user_id, provider_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS owner_auto_auth (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                username TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(username) REFERENCES users(username)
            )
            """
        )
        conn.commit()


def create_user(root: Path, username: str, password: str, role: str = "user") -> dict[str, Any]:
    init_auth_db(root)
    uname = username.strip().lower()
    if not uname:
        raise ValueError("username is required")
    if role not in ROLES:
        raise ValueError(f"invalid role: {role}")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")

    now = _now()
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)
    with _connect(_db_path(root)) as conn:
        conn.execute(
            """
            INSERT INTO users(username, role, password_hash, salt_hex, disabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                role = excluded.role,
                password_hash = excluded.password_hash,
                salt_hex = excluded.salt_hex,
                disabled = 0,
                updated_at = excluded.updated_at
            """,
            (uname, role, pw_hash, salt, now, now),
        )
        conn.commit()
    return {"username": uname, "role": role, "disabled": False}


def list_users(root: Path) -> list[dict[str, Any]]:
    init_auth_db(root)
    with _connect(_db_path(root)) as conn:
        rows = conn.execute(
            "SELECT username, role, disabled, created_at, updated_at FROM users ORDER BY username"
        ).fetchall()
    return [
        {
            "username": str(row["username"]),
            "role": str(row["role"]),
            "disabled": bool(int(row["disabled"])),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]


def set_user_role(root: Path, username: str, role: str) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f"invalid role: {role}")
    init_auth_db(root)
    now = _now()
    uname = username.strip().lower()
    with _connect(_db_path(root)) as conn:
        row = conn.execute("SELECT username FROM users WHERE username = ?", (uname,)).fetchone()
        if row is None:
            raise ValueError(f"user not found: {uname}")
        conn.execute("UPDATE users SET role = ?, updated_at = ? WHERE username = ?", (role, now, uname))
        conn.commit()
    return {"username": uname, "role": role}


def set_user_disabled(root: Path, username: str, disabled: bool = True) -> dict[str, Any]:
    init_auth_db(root)
    now = _now()
    uname = username.strip().lower()
    with _connect(_db_path(root)) as conn:
        row = conn.execute("SELECT username FROM users WHERE username = ?", (uname,)).fetchone()
        if row is None:
            raise ValueError(f"user not found: {uname}")
        conn.execute(
            "UPDATE users SET disabled = ?, updated_at = ? WHERE username = ?",
            (1 if disabled else 0, now, uname),
        )
        conn.commit()
    return {"username": uname, "disabled": bool(disabled)}


def set_user_password(root: Path, username: str, password: str) -> dict[str, Any]:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    init_auth_db(root)
    now = _now()
    uname = username.strip().lower()
    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)
    with _connect(_db_path(root)) as conn:
        row = conn.execute("SELECT username FROM users WHERE username = ?", (uname,)).fetchone()
        if row is None:
            raise ValueError(f"user not found: {uname}")
        conn.execute(
            "UPDATE users SET password_hash = ?, salt_hex = ?, updated_at = ? WHERE username = ?",
            (pw_hash, salt, now, uname),
        )
        conn.commit()
    return {"username": uname, "password_updated": True}


def _authenticate(root: Path, username: str, password: str) -> dict[str, Any] | None:
    init_auth_db(root)
    uname = username.strip().lower()
    with _connect(_db_path(root)) as conn:
        row = conn.execute(
            "SELECT username, role, password_hash, salt_hex, disabled FROM users WHERE username = ?",
            (uname,),
        ).fetchone()
    if row is None:
        return None
    if bool(int(row["disabled"])):
        return None
    expected = str(row["password_hash"])
    actual = _hash_password(password, str(row["salt_hex"]))
    if not secrets.compare_digest(expected, actual):
        return None
    return {
        "username": str(row["username"]),
        "role": str(row["role"]),
        "disabled": bool(int(row["disabled"])),
    }


def issue_token(root: Path, username: str, password: str, ttl_hours: int = 24) -> dict[str, Any]:
    user = _authenticate(root, username=username, password=password)
    if user is None:
        raise ValueError("invalid username/password")

    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    issued = dt.datetime.now(dt.timezone.utc)
    expires = issued + dt.timedelta(hours=max(1, int(ttl_hours)))

    with _connect(_db_path(root)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tokens(token_hash, username, role, issued_at, expires_at, revoked) VALUES (?, ?, ?, ?, ?, 0)",
            (token_hash, user["username"], user["role"], issued.isoformat(), expires.isoformat()),
        )
        conn.commit()

    return {
        "token": token,
        "username": user["username"],
        "role": user["role"],
        "issued_at": issued.isoformat(),
        "expires_at": expires.isoformat(),
    }


def verify_token(root: Path, token: str, require_admin: bool = False) -> dict[str, Any]:
    init_auth_db(root)
    digest = _hash_token(token.strip())
    now = dt.datetime.now(dt.timezone.utc)

    with _connect(_db_path(root)) as conn:
        row = conn.execute(
            """
            SELECT t.username, t.role, t.expires_at, t.revoked, u.disabled
            FROM tokens t
            JOIN users u ON u.username = t.username
            WHERE t.token_hash = ?
            """,
            (digest,),
        ).fetchone()

    if row is None:
        raise ValueError("invalid token")
    if bool(int(row["revoked"])):
        raise ValueError("token revoked")
    if bool(int(row["disabled"])):
        raise ValueError("user disabled")

    expires = dt.datetime.fromisoformat(str(row["expires_at"]))
    if expires <= now:
        raise ValueError("token expired")

    role = str(row["role"])
    if require_admin and role != "admin":
        raise ValueError("admin role required")

    return {
        "username": str(row["username"]),
        "role": role,
        "expires_at": expires.isoformat(),
    }


def set_owner_auto_auth(root: Path, username: str, enabled: bool = True) -> dict[str, Any]:
    init_auth_db(root)
    uname = username.strip().lower()
    if not uname:
        raise ValueError("username is required")
    now = _now()

    with _connect(_db_path(root)) as conn:
        user = conn.execute(
            "SELECT username, role, disabled FROM users WHERE username = ?",
            (uname,),
        ).fetchone()
        if user is None:
            raise ValueError(f"user not found: {uname}")
        if bool(int(user["disabled"])):
            raise ValueError("user disabled")
        if str(user["role"]) != "admin":
            raise ValueError("owner auto-auth requires admin role")

        conn.execute(
            """
            INSERT INTO owner_auto_auth(id, username, enabled, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (uname, 1 if enabled else 0, now),
        )
        conn.commit()
    return {
        "configured": True,
        "enabled": bool(enabled),
        "username": uname,
        "role": "admin",
        "updated_at": now,
    }


def disable_owner_auto_auth(root: Path) -> dict[str, Any]:
    init_auth_db(root)
    now = _now()
    with _connect(_db_path(root)) as conn:
        row = conn.execute(
            """
            SELECT o.username, u.role
            FROM owner_auto_auth o
            LEFT JOIN users u ON u.username = o.username
            WHERE o.id = 1
            """
        ).fetchone()
        if row is None:
            return {
                "configured": False,
                "enabled": False,
                "username": "",
                "role": "",
                "updated_at": now,
            }
        conn.execute("UPDATE owner_auto_auth SET enabled = 0, updated_at = ? WHERE id = 1", (now,))
        conn.commit()
    return {
        "configured": True,
        "enabled": False,
        "username": str(row["username"]),
        "role": str(row["role"] or ""),
        "updated_at": now,
    }


def get_owner_auto_auth(root: Path) -> dict[str, Any]:
    init_auth_db(root)
    with _connect(_db_path(root)) as conn:
        row = conn.execute(
            """
            SELECT o.username, o.enabled, o.updated_at, u.role, u.disabled
            FROM owner_auto_auth o
            LEFT JOIN users u ON u.username = o.username
            WHERE o.id = 1
            """
        ).fetchone()

    if row is None:
        return {
            "configured": False,
            "enabled": False,
            "username": "",
            "role": "",
            "updated_at": "",
        }

    return {
        "configured": True,
        "enabled": bool(int(row["enabled"])) and not bool(int(row["disabled"] or 0)),
        "username": str(row["username"]),
        "role": str(row["role"] or ""),
        "updated_at": str(row["updated_at"]),
        "user_disabled": bool(int(row["disabled"] or 0)),
    }


def resolve_owner_auto_auth_user(root: Path, client_host: str) -> dict[str, Any] | None:
    if not _is_loopback_host(client_host):
        return None
    out = get_owner_auto_auth(root)
    if not bool(out.get("configured")):
        return None
    if not bool(out.get("enabled")):
        return None
    role = str(out.get("role", ""))
    if role not in ROLES:
        return None
    return {
        "username": str(out.get("username", "")),
        "role": role,
        "auth_mode": "owner_auto",
    }


def set_user_routing_pref(root: Path, username: str, task_type: str, preferred_provider: str) -> dict[str, Any]:
    init_auth_db(root)
    uname = username.strip().lower()
    ttype = task_type.strip().lower()
    provider = preferred_provider.strip().lower()
    if not uname:
        raise ValueError("username is required")
    if ttype not in {"simple", "complex", "sensitive", "auto"}:
        raise ValueError("invalid task_type")
    if provider not in {"local", "codex", "remote2", "both"}:
        raise ValueError("invalid preferred_provider")
    now = _now()
    with _connect(_db_path(root)) as conn:
        user = conn.execute("SELECT username FROM users WHERE username = ?", (uname,)).fetchone()
        if user is None:
            raise ValueError(f"user not found: {uname}")
        conn.execute(
            """
            INSERT INTO user_routing_prefs(username, task_type, preferred_provider, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username, task_type) DO UPDATE SET
                preferred_provider = excluded.preferred_provider,
                updated_at = excluded.updated_at
            """,
            (uname, ttype, provider, now),
        )
        conn.commit()
    return {
        "username": uname,
        "task_type": ttype,
        "preferred_provider": provider,
        "updated_at": now,
    }


def list_user_routing_prefs(root: Path, username: str = "") -> list[dict[str, Any]]:
    init_auth_db(root)
    uname = username.strip().lower()
    out: list[dict[str, Any]] = []
    with _connect(_db_path(root)) as conn:
        if uname:
            rows = conn.execute(
                "SELECT username, task_type, preferred_provider, updated_at FROM user_routing_prefs WHERE username = ? ORDER BY task_type",
                (uname,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT username, task_type, preferred_provider, updated_at FROM user_routing_prefs ORDER BY username, task_type"
            ).fetchall()
    for row in rows:
        out.append(
            {
                "username": str(row["username"]),
                "task_type": str(row["task_type"]),
                "preferred_provider": str(row["preferred_provider"]),
                "updated_at": str(row["updated_at"]),
            }
        )
    return out


def get_user_routing_pref(root: Path, username: str, task_type: str) -> str:
    init_auth_db(root)
    uname = username.strip().lower()
    ttype = task_type.strip().lower()
    with _connect(_db_path(root)) as conn:
        row = conn.execute(
            "SELECT preferred_provider FROM user_routing_prefs WHERE username = ? AND task_type = ?",
            (uname, ttype),
        ).fetchone()
        if row is None and ttype != "auto":
            row = conn.execute(
                "SELECT preferred_provider FROM user_routing_prefs WHERE username = ? AND task_type = ?",
                (uname, "auto"),
            ).fetchone()
    return "" if row is None else str(row["preferred_provider"])


def set_provider_key_ref(
    root: Path,
    user_id: str,
    provider_id: str,
    keyring_service: str,
    keyring_account: str,
) -> dict[str, Any]:
    init_auth_db(root)
    uid = (user_id or "default").strip().lower() or "default"
    pid = provider_id.strip().lower()
    now = _now()
    with _connect(_db_path(root)) as conn:
        conn.execute(
            """
            INSERT INTO provider_key_refs(user_id, provider_id, keyring_service, keyring_account, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, provider_id) DO UPDATE SET
                keyring_service = excluded.keyring_service,
                keyring_account = excluded.keyring_account,
                updated_at = excluded.updated_at
            """,
            (uid, pid, keyring_service.strip(), keyring_account.strip(), now),
        )
        conn.commit()
    return {
        "user_id": uid,
        "provider_id": pid,
        "keyring_service": keyring_service.strip(),
        "keyring_account": keyring_account.strip(),
        "updated_at": now,
    }


def get_provider_key_ref(root: Path, user_id: str, provider_id: str) -> dict[str, Any]:
    init_auth_db(root)
    uid = (user_id or "default").strip().lower() or "default"
    pid = provider_id.strip().lower()
    with _connect(_db_path(root)) as conn:
        row = conn.execute(
            "SELECT user_id, provider_id, keyring_service, keyring_account, updated_at FROM provider_key_refs WHERE user_id = ? AND provider_id = ?",
            (uid, pid),
        ).fetchone()
    if row is None:
        return {}
    return {
        "user_id": str(row["user_id"]),
        "provider_id": str(row["provider_id"]),
        "keyring_service": str(row["keyring_service"]),
        "keyring_account": str(row["keyring_account"]),
        "updated_at": str(row["updated_at"]),
    }


def delete_provider_key_ref(root: Path, user_id: str, provider_id: str) -> dict[str, Any]:
    init_auth_db(root)
    uid = (user_id or "default").strip().lower() or "default"
    pid = provider_id.strip().lower()
    with _connect(_db_path(root)) as conn:
        conn.execute(
            "DELETE FROM provider_key_refs WHERE user_id = ? AND provider_id = ?",
            (uid, pid),
        )
        conn.commit()
    return {"user_id": uid, "provider_id": pid, "deleted": True}
