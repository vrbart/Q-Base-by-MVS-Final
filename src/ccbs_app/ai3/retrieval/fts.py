"""FTS candidate recall for ai3 chunk corpus."""

from __future__ import annotations

from typing import Any


def search_fts(conn, query: str, top_k: int = 20) -> list[dict[str, Any]]:
    text = query.strip()
    if not text:
        return []
    try:
        rows = conn.execute(
            """
            SELECT chunk_id, bm25(chunk_fts) AS rank
            FROM chunk_fts
            WHERE chunk_fts MATCH ?
            LIMIT ?
            """,
            (text, max(1, int(top_k))),
        ).fetchall()
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        rank = float(row["rank"])
        lexical_score = 1.0 / (1.0 + max(0.0, rank))
        out.append(
            {
                "chunk_id": str(row["chunk_id"]),
                "lexical_score": lexical_score,
            }
        )
    return out
