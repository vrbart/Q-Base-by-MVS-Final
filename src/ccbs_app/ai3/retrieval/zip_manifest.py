"""ZIP manifest sync into ai3 runtime tables."""

from __future__ import annotations

import hashlib
import mimetypes
import re
import zipfile
from pathlib import Path
from typing import Any

from ..db import new_id, utc_now


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _canonical_zip_path_key(raw: str | Path) -> str:
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return ""
    text = re.sub(r"/+", "/", text)
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", text)
    if m:
        drive = str(m.group(1)).lower()
        suffix = str(m.group(2)).lstrip("/")
        text = f"{drive}:/{suffix}"
    m2 = re.match(r"^([a-zA-Z]):/(.*)$", text)
    if m2:
        drive = str(m2.group(1)).lower()
        suffix = str(m2.group(2)).lstrip("/")
        text = f"{drive}:/{suffix}"
    return text.lower()


def _find_existing_zip(conn, target_key: str) -> dict[str, str] | None:
    rows = conn.execute("SELECT zip_id, path, sha256 FROM zip_archive ORDER BY rowid ASC").fetchall()
    for row in rows:
        path_value = str(row["path"] or "")
        if _canonical_zip_path_key(path_value) == target_key:
            return {
                "zip_id": str(row["zip_id"]),
                "path": path_value,
                "sha256": str(row["sha256"] or "").lower(),
            }
    return None


def _dedupe_zip_aliases(conn, target_key: str, preferred_zip_id: str) -> None:
    rows = conn.execute("SELECT rowid, zip_id, path FROM zip_archive ORDER BY rowid ASC").fetchall()
    duplicates: list[tuple[int, str]] = []
    for row in rows:
        if _canonical_zip_path_key(str(row["path"] or "")) != target_key:
            continue
        duplicates.append((int(row["rowid"]), str(row["zip_id"])))
    if len(duplicates) <= 1:
        return

    keep_zip_id = str(preferred_zip_id)
    if not any(item[1] == keep_zip_id for item in duplicates):
        keep_zip_id = sorted(duplicates, key=lambda item: item[0])[0][1]

    for _rowid, zip_id in duplicates:
        if zip_id == keep_zip_id:
            continue
        conn.execute("UPDATE zip_entry SET zip_id = ? WHERE zip_id = ?", (keep_zip_id, zip_id))
        conn.execute("DELETE FROM zip_archive WHERE zip_id = ?", (zip_id,))


def sync_zip_manifest(
    conn,
    zip_path: Path,
    source_id: str = "",
    package_id: str = "",
    vault_root: str = "",
    active: bool = True,
    full_hash: bool = False,
) -> dict[str, Any]:
    target = zip_path.expanduser().resolve()
    if not target.exists() or not target.is_file():
        raise ValueError(f"zip file not found: {target}")
    target_key = _canonical_zip_path_key(target)

    now = utc_now()
    size = int(target.stat().st_size)
    digest = _sha256(target)
    source_id_clean = str(source_id or "").strip()
    package_id_clean = str(package_id or "").strip()
    existing = _find_existing_zip(conn, target_key)
    zip_sha_changed = False
    if existing is None:
        zip_id = new_id("zip")
        conn.execute(
            """
            INSERT INTO zip_archive(zip_id, path, size_bytes, sha256, source_id, package_id, vault_root, active, added_at, last_scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (zip_id, str(target), size, digest, source_id_clean, package_id_clean, str(vault_root or ""), 1 if active else 0, now, now),
        )
    else:
        zip_id = str(existing["zip_id"])
        old_sha = str(existing.get("sha256", "")).lower()
        zip_sha_changed = bool(old_sha) and old_sha != digest.lower()
        conn.execute(
            """
            UPDATE zip_archive
            SET size_bytes = ?, sha256 = ?, source_id = ?, package_id = ?, vault_root = ?, active = ?, last_scanned_at = ?
            WHERE zip_id = ?
            """,
            (size, digest, source_id_clean, package_id_clean, str(vault_root or ""), 1 if active else 0, now, zip_id),
        )
    conn.execute("UPDATE zip_archive SET path = ? WHERE zip_id = ?", (str(target), zip_id))
    _dedupe_zip_aliases(conn, target_key=target_key, preferred_zip_id=zip_id)

    existing = {
        str(r["inner_path"]): {
            "entry_id": str(r["entry_id"]),
            "size_bytes": int(r["size_bytes"] or 0),
            "crc32": str(r["crc32"] or ""),
            "text_extracted": int(r["text_extracted"] or 0),
            "parse_status": str(r["parse_status"] or "pending"),
        }
        for r in conn.execute(
            "SELECT entry_id, inner_path, size_bytes, crc32, text_extracted, parse_status FROM zip_entry WHERE zip_id = ?",
            (zip_id,),
        ).fetchall()
    }

    seen: set[str] = set()
    with zipfile.ZipFile(target, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            inner = str(info.filename)
            seen.add(inner)
            existing_row = existing.get(inner)
            entry_id = existing_row["entry_id"] if existing_row else new_id("entry")
            mime, _ = mimetypes.guess_type(inner)
            crc32 = format(int(info.CRC) & 0xFFFFFFFF, "08x")
            size_bytes = int(info.file_size)
            unchanged = (
                bool(existing_row)
                and not zip_sha_changed
                and int(existing_row["size_bytes"]) == size_bytes
                and str(existing_row["crc32"]) == crc32
            )
            text_extracted = int(existing_row["text_extracted"]) if unchanged and existing_row else 0
            parse_status = str(existing_row["parse_status"]) if unchanged and existing_row else "pending"
            parse_error = ""
            entry_sha256 = None
            if full_hash:
                entry_sha256 = _sha256_bytes(zf.read(info))
            conn.execute(
                """
                INSERT INTO zip_entry(entry_id, zip_id, package_id, inner_path, size_bytes, modified_at, crc32, mime, entry_sha256, parse_status, parse_error, text_extracted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET
                  package_id = excluded.package_id,
                  size_bytes = excluded.size_bytes,
                  modified_at = excluded.modified_at,
                  crc32 = excluded.crc32,
                  mime = excluded.mime,
                  entry_sha256 = COALESCE(excluded.entry_sha256, zip_entry.entry_sha256),
                  parse_status = excluded.parse_status,
                  parse_error = excluded.parse_error,
                  text_extracted = excluded.text_extracted
                """,
                (
                    entry_id,
                    zip_id,
                    package_id_clean,
                    inner,
                    size_bytes,
                    f"{info.date_time[0]:04d}-{info.date_time[1]:02d}-{info.date_time[2]:02d}T{info.date_time[3]:02d}:{info.date_time[4]:02d}:{info.date_time[5]:02d}Z",
                    crc32,
                    mime or "",
                    entry_sha256,
                    parse_status,
                    parse_error,
                    text_extracted,
                ),
            )

    for inner, details in existing.items():
        if inner in seen:
            continue
        entry_id = str(details["entry_id"])
        conn.execute("DELETE FROM zip_entry WHERE entry_id = ?", (entry_id,))

    conn.commit()
    return {
        "zip_id": zip_id,
        "path": str(target),
        "size_bytes": size,
        "sha256": digest,
        "source_id": source_id_clean,
        "package_id": package_id_clean,
        "active": bool(active),
        "entries": len(seen),
        "scanned_at": now,
        "full_hash": bool(full_hash),
    }
