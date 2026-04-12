"""Hybrid score merge and lightweight reranking."""

from __future__ import annotations

from typing import Any


def merge_and_rerank(
    lexical_hits: list[dict[str, Any]],
    vector_hits: list[dict[str, Any]],
    top_k: int = 8,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in lexical_hits:
        cid = str(row["chunk_id"])
        merged.setdefault(cid, {"chunk_id": cid, "lexical_score": 0.0, "vector_score": 0.0})
        merged[cid]["lexical_score"] = float(row.get("lexical_score", 0.0))
    for row in vector_hits:
        cid = str(row["chunk_id"])
        merged.setdefault(cid, {"chunk_id": cid, "lexical_score": 0.0, "vector_score": 0.0})
        merged[cid]["vector_score"] = float(row.get("vector_score", 0.0))

    out: list[dict[str, Any]] = []
    for cid, row in merged.items():
        lexical = float(row.get("lexical_score", 0.0))
        vector = float(row.get("vector_score", 0.0))
        score = (0.45 * lexical) + (0.55 * max(0.0, vector))
        out.append(
            {
                "chunk_id": cid,
                "score": score,
                "lexical_score": lexical,
                "vector_score": vector,
            }
        )
    out.sort(key=lambda item: float(item["score"]), reverse=True)
    return out[: max(1, int(top_k))]
