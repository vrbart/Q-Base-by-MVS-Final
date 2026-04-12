"""Citation persistence for ai3 runs."""

from __future__ import annotations

from typing import Any

from ..db import new_id


def persist_citations(conn, run_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = {
            "citation_id": new_id("cit"),
            "run_id": run_id,
            "source_uri": str(row.get("source_uri", "")),
            "doc_id": str(row.get("doc_id", "")) or None,
            "chunk_id": str(row.get("chunk_id", "")) or None,
            "page": row.get("page"),
            "start_offset": row.get("start_offset"),
            "end_offset": row.get("end_offset"),
            "snippet": str(row.get("snippet", "")),
        }
        conn.execute(
            """
            INSERT INTO citation(citation_id, run_id, source_uri, doc_id, chunk_id, page, start_offset, end_offset, snippet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["citation_id"],
                payload["run_id"],
                payload["source_uri"],
                payload["doc_id"],
                payload["chunk_id"],
                payload["page"],
                payload["start_offset"],
                payload["end_offset"],
                payload["snippet"],
            ),
        )
        out.append(payload)
    return out
