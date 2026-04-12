"""Hybrid lexical/vector indexing and retrieval for ai2 pipeline."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .ai_models import run_model_prompt
from .ai_storage import StorageLimitError, usage_report

TOKEN_RE = re.compile(r"[a-z0-9_./-]+", re.IGNORECASE)


@dataclass(frozen=True)
class HybridHit:
    chunk_ref: int
    doc_id: str
    source_id: str
    path: str
    chunk_id: int
    score: float
    lexical_score: float
    vector_score: float
    content: str


@dataclass(frozen=True)
class IndexBuildSummary:
    docs_indexed: int
    chunks_indexed: int
    skipped_files: int
    db_path: str
    indexed_at: str


def _index_dir(root: Path) -> Path:
    out = root / ".ccbs" / "ai2" / "index"
    out.mkdir(parents=True, exist_ok=True)
    return out


def index_db_path(root: Path) -> Path:
    return _index_dir(root) / "index.db"


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


def _cursor_lastrowid(cursor: sqlite3.Cursor) -> int:
    row_id = cursor.lastrowid
    if row_id is None:
        raise RuntimeError("database insert did not return lastrowid")
    return int(row_id)


def _tokenize(text: str) -> list[str]:
    return [tok.lower() for tok in TOKEN_RE.findall(text or "") if len(tok) > 1]


def _token_counts(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for tok in _tokenize(text):
        out[tok] = out.get(tok, 0) + 1
    return out


def _chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    clean = text.replace("\r\n", "\n")
    if not clean.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(clean):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _embedding(text: str, dims: int = 64) -> list[float]:
    vec = [0.0] * dims
    for tok in _tokenize(text):
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % dims
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        mag = 1.0 + (digest[3] / 255.0)
        vec[idx] += sign * mag

    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def init_index_db(root: Path) -> None:
    db = index_db_path(root)
    with _connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS docs (
                doc_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                mtime REAL NOT NULL,
                bytes INTEGER NOT NULL,
                indexed_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_ref INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                token_counts_json TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                FOREIGN KEY(doc_id) REFERENCES docs(doc_id)
            )
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                content,
                chunk_ref UNINDEXED
            )
            """
        )
        conn.commit()


def _iter_normalized(root: Path, source_id: str = "") -> list[Path]:
    base = root / ".ccbs" / "ai2" / "sources" / "normalized"
    if source_id.strip():
        base = base / source_id.strip().lower()
    if not base.exists():
        return []
    out: list[Path] = []
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix.lower() == ".txt" and not path.name.endswith(".meta.json"):
            out.append(path)
    return out


def _doc_id(source_id: str, path: Path) -> str:
    key = f"{source_id}:{path.resolve()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def build_index(root: Path, source_id: str = "", max_files: int = 50000) -> IndexBuildSummary:
    init_index_db(root)
    db = index_db_path(root)
    storage = usage_report(root)
    max_bytes = int(storage.max_bytes)
    current_bytes = int(storage.total_bytes)

    def reserve_capacity(incoming_bytes: int, stage: str) -> None:
        nonlocal current_bytes
        incoming = max(0, int(incoming_bytes))
        if current_bytes + incoming > max_bytes:
            raise StorageLimitError(
                stage=stage,
                current_bytes=current_bytes,
                incoming_bytes=incoming,
                max_bytes=max_bytes,
            )
        current_bytes += incoming

    files = _iter_normalized(root, source_id=source_id)
    docs = 0
    chunks = 0
    skipped = 0
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    with _connect(db) as conn:
        for idx, path in enumerate(files, 1):
            if idx > max(1, int(max_files)):
                skipped += 1
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                skipped += 1
                continue

            sid = "unknown"
            parts = list(path.parts)
            if "normalized" in parts:
                pos = parts.index("normalized")
                if pos + 1 < len(parts):
                    sid = parts[pos + 1]

            stat = path.stat()
            content_bytes = text.encode("utf-8", errors="ignore")
            reserve_capacity(incoming_bytes=0, stage="index-preflight")
            did = _doc_id(sid, path)
            sha = hashlib.sha256(content_bytes).hexdigest()

            old_refs = conn.execute("SELECT chunk_ref FROM chunks WHERE doc_id = ?", (did,)).fetchall()
            for row in old_refs:
                conn.execute("DELETE FROM chunks_fts WHERE chunk_ref = ?", (str(int(row["chunk_ref"])),))
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (did,))
            conn.execute("DELETE FROM docs WHERE doc_id = ?", (did,))

            conn.execute(
                "INSERT INTO docs(doc_id, source_id, path, sha256, mtime, bytes, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (did, sid, str(path), sha, float(stat.st_mtime), len(content_bytes), now),
            )

            doc_chunks = _chunk_text(text)
            for cidx, chunk in enumerate(doc_chunks, 1):
                emb = _embedding(chunk)
                token_counts = _token_counts(chunk)
                entry_bytes = len(chunk.encode("utf-8")) + len(json.dumps(emb))
                reserve_capacity(incoming_bytes=entry_bytes, stage="index-write")
                cur = conn.execute(
                    "INSERT INTO chunks(doc_id, chunk_id, content, token_counts_json, embedding_json) VALUES (?, ?, ?, ?, ?)",
                    (did, cidx, chunk, json.dumps(token_counts, sort_keys=True, separators=(",", ":")), json.dumps(emb)),
                )
                chunk_ref = _cursor_lastrowid(cur)
                conn.execute("INSERT INTO chunks_fts(content, chunk_ref) VALUES (?, ?)", (chunk, str(chunk_ref)))
                chunks += 1

            docs += 1
        conn.commit()

    return IndexBuildSummary(
        docs_indexed=docs,
        chunks_indexed=chunks,
        skipped_files=skipped,
        db_path=str(db),
        indexed_at=now,
    )


def _fetch_chunks(conn: sqlite3.Connection, refs: list[int]) -> list[sqlite3.Row]:
    if not refs:
        return []
    marks = ",".join("?" for _ in refs)
    sql = f"""
        SELECT c.chunk_ref, c.doc_id, d.source_id, d.path, c.chunk_id, c.content, c.embedding_json
        FROM chunks c
        JOIN docs d ON d.doc_id = c.doc_id
        WHERE c.chunk_ref IN ({marks})
    """
    return conn.execute(sql, tuple(refs)).fetchall()


def search_index(root: Path, question: str, top_k: int = 5) -> list[HybridHit]:
    db = index_db_path(root)
    if not db.exists() or not question.strip():
        return []

    q_embed = _embedding(question)
    lex_scores: dict[int, float] = {}

    with _connect(db) as conn:
        try:
            rows = conn.execute(
                "SELECT chunk_ref, bm25(chunks_fts) AS rank FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT ?",
                (" ".join(_tokenize(question)) or question.strip(), max(20, top_k * 8)),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

        for row in rows:
            ref = int(row["chunk_ref"])
            rank = float(row["rank"])
            lex_scores[ref] = 1.0 / (1.0 + max(0.0, rank))

        if not lex_scores:
            fallback = conn.execute(
                "SELECT chunk_ref FROM chunks ORDER BY chunk_ref DESC LIMIT ?",
                (max(50, top_k * 10),),
            ).fetchall()
            for row in fallback:
                lex_scores[int(row["chunk_ref"])] = 0.0

        refs = list(lex_scores.keys())
        chunk_rows = _fetch_chunks(conn, refs)

    hits: list[HybridHit] = []
    for row in chunk_rows:
        ref = int(row["chunk_ref"])
        emb = json.loads(str(row["embedding_json"]) or "[]")
        vscore = _cosine(q_embed, [float(x) for x in emb])
        lscore = float(lex_scores.get(ref, 0.0))
        score = (0.65 * max(0.0, vscore)) + (0.35 * max(0.0, lscore))
        hits.append(
            HybridHit(
                chunk_ref=ref,
                doc_id=str(row["doc_id"]),
                source_id=str(row["source_id"]),
                path=str(row["path"]),
                chunk_id=int(row["chunk_id"]),
                score=score,
                lexical_score=lscore,
                vector_score=vscore,
                content=str(row["content"]),
            )
        )

    hits.sort(key=lambda x: x.score, reverse=True)
    return hits[: max(1, int(top_k))]


def answer_query(
    root: Path,
    question: str,
    top_k: int = 5,
    task: str = "general",
    model_id: str = "",
    provider: str = "extractive",
) -> dict[str, Any]:
    hits = search_index(root, question=question, top_k=max(1, int(top_k)))
    if not hits:
        return {
            "question": question,
            "answer": "No indexed content matched. Run `ccbs ai ingest run` and `ccbs ai index build`.",
            "provider": provider,
            "model": model_id or "extractive-default",
            "citations": [],
        }

    context_lines: list[str] = []
    for idx, hit in enumerate(hits, 1):
        context_lines.append(f"[{idx}] {hit.path}#chunk{hit.chunk_id}")
        context_lines.append(hit.content)
        context_lines.append("")
    context = "\n".join(context_lines).strip()

    prompt = (
        "You are a local offline assistant. Answer from supplied context only. "
        "If uncertain, say uncertain. Include citations using [n] notation.\n\n"
        f"Question:\n{question}\n\n"
        f"Context:\n{context}\n"
    )

    if provider == "ollama" or model_id:
        try:
            run = run_model_prompt(root=root, prompt=prompt, task=task, model_id=model_id)
            answer = str(run.get("output", "")).strip() or "No response."
            used_provider = str(run.get("provider", provider))
            used_model = str(run.get("model", model_id or ""))
        except Exception as exc:  # noqa: BLE001
            answer = f"Model unavailable ({exc}). Fallback extractive answer:\n" + "\n".join(
                f"[{i}] {h.content.splitlines()[0][:220]}" for i, h in enumerate(hits, 1)
            )
            used_provider = "extractive"
            used_model = "extractive"
    else:
        answer = "\n".join(f"[{i}] {h.content.splitlines()[0][:220]}" for i, h in enumerate(hits, 1))
        used_provider = "extractive"
        used_model = "extractive"

    return {
        "question": question,
        "answer": answer,
        "provider": used_provider,
        "model": used_model,
        "citations": [
            {
                "path": h.path,
                "source_id": h.source_id,
                "chunk_id": h.chunk_id,
                "score": h.score,
                "lexical_score": h.lexical_score,
                "vector_score": h.vector_score,
            }
            for h in hits
        ],
    }


def index_stats(root: Path) -> dict[str, Any]:
    db = index_db_path(root)
    if not db.exists():
        return {
            "db_path": str(db),
            "exists": False,
            "docs": 0,
            "chunks": 0,
            "bytes": 0,
        }

    with _connect(db) as conn:
        docs = int(conn.execute("SELECT COUNT(*) AS c FROM docs").fetchone()["c"])
        chunks = int(conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()["c"])

    return {
        "db_path": str(db),
        "exists": True,
        "docs": docs,
        "chunks": chunks,
        "bytes": int(db.stat().st_size),
    }


def doctor_index(root: Path) -> dict[str, Any]:
    stats = index_stats(root)
    issues: list[str] = []
    if not stats["exists"]:
        issues.append("index_missing")
    if stats["exists"] and stats["chunks"] == 0:
        issues.append("index_empty")
    if stats["exists"] and stats["docs"] == 0:
        issues.append("docs_missing")
    return {
        "ok": not issues,
        "issues": issues,
        "stats": stats,
    }


def embedding_for_text(text: str) -> list[float]:
    return _embedding(text)
