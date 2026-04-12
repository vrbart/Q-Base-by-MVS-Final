"""ZIP entry extraction and indexing into ai3 document/chunk tables."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

from ..db import new_id, utc_now
from .chunker import chunk_text
from .vector_lancedb import upsert_vector


TEXT_EXT = {".txt", ".md", ".rst", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".csv", ".py", ".ps1", ".sh", ".html", ".htm"}


def _decode_bytes(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return ""


def _legacy_source_uri(zip_id: str, inner_path: str) -> str:
    return f"vault://{zip_id}/{inner_path}"


def _canonical_source_uri(zip_sha256: str, inner_path: str, zip_id: str) -> str:
    clean_hash = str(zip_sha256 or "").strip()
    if clean_hash:
        return f"vault://zip/{clean_hash}#/{inner_path}"
    return _legacy_source_uri(zip_id=zip_id, inner_path=inner_path)


def _doc_id(zip_id: str, inner_path: str) -> str:
    return hashlib.sha256(f"{zip_id}:{inner_path}".encode("utf-8")).hexdigest()


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _is_safe_inner_path(inner_path: str) -> bool:
    text = str(inner_path or "").replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("\\"):
        return False
    parts = [p for p in Path(text).parts if p not in {"", "."}]
    if not parts:
        return False
    if ".." in parts:
        return False
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        return False
    return True


def index_zip_archive(
    conn,
    zip_id: str,
    zip_path: Path,
    max_entries: int = 20000,
    only_pending: bool = True,
    max_entry_bytes: int = 32 * 1024 * 1024,
    max_total_extract_bytes: int = 2 * 1024 * 1024 * 1024,
    text_extensions: set[str] | None = None,
    embedding_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = zip_path.expanduser().resolve()
    if not target.exists():
        raise ValueError(f"zip file not found: {target}")
    max_entries_i = max(1, int(max_entries))
    max_entry_bytes_i = max(1024, int(max_entry_bytes))
    max_total_extract_i = max(1024, int(max_total_extract_bytes))
    allowed_ext = {str(x).lower().strip() for x in (text_extensions or TEXT_EXT)}
    if not allowed_ext:
        allowed_ext = set(TEXT_EXT)

    zip_row = conn.execute(
        "SELECT sha256, package_id FROM zip_archive WHERE zip_id = ?",
        (zip_id,),
    ).fetchone()
    zip_sha256 = str(zip_row["sha256"] or "") if zip_row else ""
    package_id = str(zip_row["package_id"] or "") if zip_row else ""

    entry_rows = conn.execute(
        "SELECT entry_id, inner_path, text_extracted FROM zip_entry WHERE zip_id = ? ORDER BY inner_path LIMIT ?",
        (zip_id, max_entries_i),
    ).fetchall()
    entry_map = {
        str(r["inner_path"]): {
            "entry_id": str(r["entry_id"]),
            "text_extracted": int(r["text_extracted"] or 0),
        }
        for r in entry_rows
    }

    docs = 0
    chunks = 0
    skipped_unsupported = 0
    skipped_too_large = 0
    failed_parse = 0
    extracted_bytes = 0
    now = utc_now()
    with zipfile.ZipFile(target, "r") as zf:
        for idx, info in enumerate(zf.infolist(), 1):
            if idx > max_entries_i:
                break
            if info.is_dir():
                continue
            inner = str(info.filename)
            entry = entry_map.get(inner)
            if not entry:
                continue
            entry_id = str(entry["entry_id"])
            if only_pending and int(entry["text_extracted"]) == 1:
                continue
            if not _is_safe_inner_path(inner):
                conn.execute(
                    "UPDATE zip_entry SET parse_status = ?, parse_error = ?, text_extracted = 0 WHERE entry_id = ?",
                    ("failed_parse", "unsafe_inner_path", entry_id),
                )
                failed_parse += 1
                continue
            suffix = Path(inner).suffix.lower()
            if suffix not in allowed_ext:
                conn.execute(
                    "UPDATE zip_entry SET parse_status = ?, parse_error = ?, text_extracted = 0 WHERE entry_id = ?",
                    ("skipped_unsupported", f"unsupported_extension:{suffix or '<none>'}", entry_id),
                )
                skipped_unsupported += 1
                continue
            file_size = int(info.file_size or 0)
            if file_size > max_entry_bytes_i or extracted_bytes + file_size > max_total_extract_i:
                conn.execute(
                    "UPDATE zip_entry SET parse_status = ?, parse_error = ?, text_extracted = 0 WHERE entry_id = ?",
                    ("skipped_too_large", "extract_limit_exceeded", entry_id),
                )
                skipped_too_large += 1
                continue

            try:
                raw = zf.read(info)
            except Exception as exc:  # noqa: BLE001
                conn.execute(
                    "UPDATE zip_entry SET parse_status = ?, parse_error = ?, text_extracted = 0 WHERE entry_id = ?",
                    ("failed_parse", f"zip_read_error:{exc}", entry_id),
                )
                failed_parse += 1
                continue
            extracted_bytes += len(raw)
            entry_sha256 = _sha256_bytes(raw)
            text = _decode_bytes(raw)
            if not text.strip():
                conn.execute(
                    "UPDATE zip_entry SET entry_sha256 = ?, parse_status = ?, parse_error = ?, text_extracted = 0 WHERE entry_id = ?",
                    (entry_sha256, "skipped_unsupported", "empty_or_binary_content", entry_id),
                )
                skipped_unsupported += 1
                continue

            doc_id = _doc_id(zip_id, inner)
            uri = _canonical_source_uri(zip_sha256=zip_sha256, inner_path=inner, zip_id=zip_id)
            legacy_uri = _legacy_source_uri(zip_id=zip_id, inner_path=inner)
            old_chunk_rows = conn.execute("SELECT chunk_id FROM chunk WHERE doc_id = ?", (doc_id,)).fetchall()
            for old in old_chunk_rows:
                old_chunk_id = str(old["chunk_id"])
                conn.execute("DELETE FROM chunk_vector WHERE chunk_id = ?", (old_chunk_id,))
                conn.execute("DELETE FROM chunk_fts WHERE chunk_id = ?", (old_chunk_id,))
            conn.execute("DELETE FROM chunk WHERE doc_id = ?", (doc_id,))
            conn.execute("DELETE FROM document WHERE doc_id = ?", (doc_id,))
            conn.execute(
                """
                INSERT INTO document(doc_id, source_uri, title, language, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    uri,
                    Path(inner).name,
                    "",
                    now,
                    json.dumps(
                        {
                            "zip_id": zip_id,
                            "zip_sha256": zip_sha256,
                            "package_id": package_id,
                            "inner_path": inner,
                            "legacy_source_uri": legacy_uri,
                        }
                    ),
                ),
            )
            docs += 1

            doc_chunks = chunk_text(text)
            for cidx, row in enumerate(doc_chunks, 1):
                cid = new_id("chunk")
                payload = str(row.get("text", ""))
                conn.execute(
                    """
                    INSERT INTO chunk(chunk_id, doc_id, chunk_index, text, token_count, page, start_offset, end_offset, created_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid,
                        doc_id,
                        cidx,
                        payload,
                        int(row.get("token_count", 0)),
                        None,
                        int(row.get("start_offset", 0)),
                        int(row.get("end_offset", 0)),
                        now,
                        json.dumps({"zip_id": zip_id, "package_id": package_id, "inner_path": inner}),
                    ),
                )
                conn.execute("INSERT INTO chunk_fts(text, chunk_id) VALUES (?, ?)", (payload, cid))
                upsert_vector(conn, chunk_id=cid, text=payload, config=dict(embedding_config or {}))
                chunks += 1

            conn.execute(
                """
                UPDATE zip_entry
                SET entry_sha256 = ?, parse_status = 'indexed', parse_error = '', text_extracted = 1
                WHERE entry_id = ?
                """,
                (entry_sha256, entry_id),
            )

    conn.execute(
        """
        INSERT INTO index_snapshot(snapshot_id, kind, backend, created_at, details_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            new_id("snap"),
            "vector",
            str((embedding_config or {}).get("provider", "auto")),
            now,
            json.dumps({"zip_id": zip_id, "docs": docs, "chunks": chunks, "path": str(target)}),
        ),
    )
    conn.execute(
        """
        INSERT INTO index_snapshot(snapshot_id, kind, backend, created_at, details_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            new_id("snap"),
            "keyword",
            "sqlite_fts5",
            now,
            json.dumps({"zip_id": zip_id, "docs": docs, "chunks": chunks, "path": str(target)}),
        ),
    )
    conn.execute(
        """
        INSERT INTO index_snapshot(snapshot_id, kind, backend, created_at, details_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            new_id("snap"),
            "rerank",
            "local_weighted_merge",
            now,
            json.dumps({"zip_id": zip_id, "docs": docs, "chunks": chunks}),
        ),
    )
    conn.commit()
    return {
        "zip_id": zip_id,
        "docs_indexed": docs,
        "chunks_indexed": chunks,
        "skipped_unsupported": skipped_unsupported,
        "skipped_too_large": skipped_too_large,
        "failed_parse": failed_parse,
        "extracted_bytes": extracted_bytes,
        "max_entry_bytes": max_entry_bytes_i,
        "max_total_extract_bytes": max_total_extract_i,
        "indexed_at": now,
        "only_pending": bool(only_pending),
    }
