"""Citation verification for vault-backed retrieval results."""

from __future__ import annotations

import json
import re
from typing import Any

from ..db import new_id, utc_now


_CANONICAL_RE = re.compile(r"^vault://zip/([0-9a-fA-F]{64})#/([^?]+)(?:\?.*)?$")
_LEGACY_RE = re.compile(r"^vault://([^/]+)/(.+)$")


def _parse_uri(source_uri: str) -> dict[str, str]:
    text = str(source_uri or "").strip()
    m = _CANONICAL_RE.match(text)
    if m:
        return {"kind": "canonical", "zip_sha256": str(m.group(1)).lower(), "inner_path": str(m.group(2))}
    m = _LEGACY_RE.match(text)
    if m:
        return {"kind": "legacy", "zip_id": str(m.group(1)), "inner_path": str(m.group(2))}
    return {}


def _record(conn, run_id: str, citation_id: str, status: str, reason: str, details: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "verification_id": new_id("citv"),
        "run_id": str(run_id),
        "citation_id": str(citation_id),
        "status": str(status),
        "reason": str(reason),
        "verified_at": utc_now(),
        "details": dict(details),
    }
    conn.execute(
        """
        INSERT INTO citation_verification(verification_id, run_id, citation_id, status, reason, verified_at, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload["verification_id"],
            payload["run_id"],
            payload["citation_id"],
            payload["status"],
            payload["reason"],
            payload["verified_at"],
            json.dumps(payload["details"], sort_keys=True),
        ),
    )
    return payload


def verify_run_citations(conn, run_id: str, strict: bool = False) -> dict[str, Any]:
    run_id_clean = str(run_id or "").strip()
    if not run_id_clean:
        raise ValueError("run_id is required")

    rows = conn.execute(
        """
        SELECT citation_id, source_uri, chunk_id, page, start_offset, end_offset, snippet
        FROM citation
        WHERE run_id = ?
        ORDER BY rowid ASC
        """,
        (run_id_clean,),
    ).fetchall()

    conn.execute("DELETE FROM citation_verification WHERE run_id = ?", (run_id_clean,))
    checks: list[dict[str, Any]] = []
    failures = 0

    for row in rows:
        citation_id = str(row["citation_id"] or "")
        source_uri = str(row["source_uri"] or "")
        chunk_id = str(row["chunk_id"] or "")
        parsed = _parse_uri(source_uri)
        if not parsed:
            failures += 1
            checks.append(_record(conn, run_id_clean, citation_id, "failed", "invalid_source_uri", {"source_uri": source_uri}))
            continue

        resolved = None
        if parsed.get("kind") == "canonical":
            resolved = conn.execute(
                """
                SELECT za.zip_id, za.sha256, ze.entry_id
                FROM zip_archive za
                JOIN zip_entry ze ON ze.zip_id = za.zip_id
                WHERE lower(za.sha256) = ? AND ze.inner_path = ?
                LIMIT 1
                """,
                (str(parsed.get("zip_sha256", "")).lower(), str(parsed.get("inner_path", ""))),
            ).fetchone()
            if resolved is None:
                failures += 1
                checks.append(
                    _record(
                        conn,
                        run_id_clean,
                        citation_id,
                        "failed",
                        "zip_entry_not_found",
                        {"source_uri": source_uri, "kind": "canonical"},
                    )
                )
                continue
            resolved_sha = str(resolved["sha256"] or "").lower()
            if resolved_sha != str(parsed.get("zip_sha256", "")).lower():
                failures += 1
                checks.append(
                    _record(
                        conn,
                        run_id_clean,
                        citation_id,
                        "failed",
                        "zip_hash_mismatch",
                        {"source_uri": source_uri, "expected": parsed.get("zip_sha256", ""), "actual": resolved_sha},
                    )
                )
                continue
        else:
            resolved = conn.execute(
                """
                SELECT za.zip_id, za.sha256, ze.entry_id
                FROM zip_archive za
                JOIN zip_entry ze ON ze.zip_id = za.zip_id
                WHERE za.zip_id = ? AND ze.inner_path = ?
                LIMIT 1
                """,
                (str(parsed.get("zip_id", "")), str(parsed.get("inner_path", ""))),
            ).fetchone()
            if resolved is None:
                failures += 1
                checks.append(
                    _record(
                        conn,
                        run_id_clean,
                        citation_id,
                        "failed",
                        "zip_entry_not_found",
                        {"source_uri": source_uri, "kind": "legacy"},
                    )
                )
                continue

        chunk_text = ""
        if chunk_id:
            chunk_row = conn.execute("SELECT text FROM chunk WHERE chunk_id = ?", (chunk_id,)).fetchone()
            if chunk_row is not None:
                chunk_text = str(chunk_row["text"] or "")

        start_offset = row["start_offset"]
        end_offset = row["end_offset"]
        if isinstance(start_offset, int) and isinstance(end_offset, int):
            if start_offset < 0 or end_offset < start_offset:
                failures += 1
                checks.append(
                    _record(
                        conn,
                        run_id_clean,
                        citation_id,
                        "failed",
                        "invalid_offsets",
                        {"start_offset": start_offset, "end_offset": end_offset},
                    )
                )
                continue

        snippet = str(row["snippet"] or "").strip()
        if snippet and chunk_text and snippet not in chunk_text:
            failures += 1
            checks.append(
                _record(
                    conn,
                    run_id_clean,
                    citation_id,
                    "failed",
                    "snippet_mismatch",
                    {"snippet_preview": snippet[:160], "chunk_preview": chunk_text[:160]},
                )
            )
            continue

        checks.append(
            _record(
                conn,
                run_id_clean,
                citation_id,
                "verified",
                "ok",
                {
                    "source_uri": source_uri,
                    "chunk_id": chunk_id,
                    "page": row["page"],
                },
            )
        )

    conn.commit()
    verified = sum(1 for item in checks if item["status"] == "verified")
    failed = sum(1 for item in checks if item["status"] != "verified")
    return {
        "run_id": run_id_clean,
        "strict": bool(strict),
        "total": len(checks),
        "verified": verified,
        "failed": failed,
        "checks": checks,
        "ok": failed == 0,
    }
