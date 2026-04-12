"""Vector backend with LanceDB-first intent and SQLite fallback storage."""

from __future__ import annotations

import hashlib
import json
import math
import os
import urllib.request
from typing import Any

from ..db import utc_now


def _tokenize(text: str) -> list[str]:
    return [tok for tok in str(text).lower().replace("\n", " ").split(" ") if tok]


def embed_hash96(text: str, dims: int = 96) -> list[float]:
    vec = [0.0] * max(8, int(dims))
    for tok in _tokenize(text):
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % len(vec)
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        mag = 1.0 + (digest[3] / 255.0)
        vec[idx] += sign * mag
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


def _http_post_json(url: str, payload: dict[str, Any], timeout_s: int = 10) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=max(1, int(timeout_s))) as resp:
        raw = resp.read()
    parsed = json.loads(raw.decode("utf-8", errors="replace"))
    if not isinstance(parsed, dict):
        raise RuntimeError("embedding endpoint returned non-object")
    return parsed


def embed_ollama(text: str, base_url: str = "http://127.0.0.1:11434", model: str = "nomic-embed-text") -> list[float]:
    endpoint = str(base_url).rstrip("/") + "/api/embed"
    payload = {"model": model, "input": text}
    body = _http_post_json(endpoint, payload, timeout_s=12)
    values = body.get("embeddings")
    if isinstance(values, list) and values and isinstance(values[0], list):
        return [float(x) for x in values[0]]
    value = body.get("embedding")
    if isinstance(value, list):
        return [float(x) for x in value]
    raise RuntimeError("ollama embed response missing embedding vector")


def _provider_from_config(config: dict[str, Any] | None = None) -> dict[str, str]:
    values = dict(config or {})
    provider = str(values.get("provider", os.environ.get("CCBS_AI3_EMBED_PROVIDER", "auto"))).strip().lower() or "auto"
    base_url = str(values.get("ollama_base_url", os.environ.get("CCBS_AI3_EMBED_OLLAMA_BASE_URL", "http://127.0.0.1:11434"))).strip()
    model = str(values.get("ollama_model", os.environ.get("CCBS_AI3_EMBED_OLLAMA_MODEL", "nomic-embed-text"))).strip()
    fallback = str(values.get("fallback_provider", "hash96")).strip().lower() or "hash96"
    return {
        "provider": provider,
        "ollama_base_url": base_url,
        "ollama_model": model,
        "fallback_provider": fallback,
    }


def embed_text(text: str, config: dict[str, Any] | None = None, dims: int = 96) -> tuple[str, list[float]]:
    resolved = _provider_from_config(config)
    provider = resolved["provider"]
    if provider in {"hash", "hash96"}:
        return "hash96", embed_hash96(text, dims=dims)
    if provider in {"ollama", "ollama_embed"}:
        vector = embed_ollama(text, base_url=resolved["ollama_base_url"], model=resolved["ollama_model"])
        return f"ollama:{resolved['ollama_model']}", vector
    if provider == "auto":
        try:
            vector = embed_ollama(text, base_url=resolved["ollama_base_url"], model=resolved["ollama_model"])
            return f"ollama:{resolved['ollama_model']}", vector
        except Exception:
            fallback = resolved.get("fallback_provider", "hash96")
            if fallback in {"hash", "hash96"}:
                return "hash96", embed_hash96(text, dims=dims)
            return "hash96", embed_hash96(text, dims=dims)
    return "hash96", embed_hash96(text, dims=dims)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def upsert_vector(conn, chunk_id: str, text: str, backend: str = "", config: dict[str, Any] | None = None) -> None:
    chosen_backend, vec = embed_text(text, config=config)
    final_backend = str(backend or chosen_backend).strip() or "hash96"
    conn.execute(
        """
        INSERT INTO chunk_vector(chunk_id, vector_json, backend, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(chunk_id) DO UPDATE SET
          vector_json = excluded.vector_json,
          backend = excluded.backend,
          created_at = excluded.created_at
        """,
        (chunk_id, json.dumps(vec), final_backend, utc_now()),
    )


def _embed_query_for_backend(query: str, backend: str, dims: int, config: dict[str, Any]) -> list[float]:
    b = str(backend or "").strip().lower()
    if b.startswith("ollama:"):
        try:
            return embed_ollama(query, base_url=str(config.get("ollama_base_url", "http://127.0.0.1:11434")), model=str(config.get("ollama_model", "nomic-embed-text")))
        except Exception:
            return embed_hash96(query, dims=max(8, int(dims)))
    if b in {"hash", "hash96"}:
        return embed_hash96(query, dims=max(8, int(dims)))
    return embed_hash96(query, dims=max(8, int(dims)))


def search_vectors(conn, query: str, top_k: int = 10, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    resolved = _provider_from_config(config)
    rows = conn.execute("SELECT chunk_id, vector_json, backend FROM chunk_vector").fetchall()
    qv_cache: dict[str, list[float]] = {}
    out: list[dict[str, Any]] = []
    for row in rows:
        vec = [float(x) for x in json.loads(str(row["vector_json"]) or "[]")]
        backend = str(row["backend"] or "hash96")
        if backend not in qv_cache:
            qv_cache[backend] = _embed_query_for_backend(query, backend=backend, dims=len(vec), config=resolved)
        out.append(
            {
                "chunk_id": str(row["chunk_id"]),
                "vector_score": _cosine(qv_cache.get(backend, []), vec),
                "backend": backend,
            }
        )
    out.sort(key=lambda item: float(item["vector_score"]), reverse=True)
    return out[: max(1, int(top_k))]
