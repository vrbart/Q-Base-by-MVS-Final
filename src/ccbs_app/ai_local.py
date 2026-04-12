"""Offline-first AI helpers for CCBS CLI."""

from __future__ import annotations

import datetime as dt
import difflib
import json
import re
import sqlite3
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


TEXT_EXTENSIONS = {
    ".cfg",
    ".csv",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

IGNORE_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ccbs"}
LOCAL_PROVIDERS = {"extractive", "ollama"}
TOKEN_RE = re.compile(r"[a-z0-9_./-]+", re.IGNORECASE)


@dataclass(frozen=True)
class SearchHit:
    path: str
    chunk_id: int
    score: float
    content: str


@dataclass(frozen=True)
class IndexSummary:
    target: str
    indexed_files: int
    indexed_chunks: int
    skipped_files: int


@dataclass(frozen=True)
class AnswerResult:
    question: str
    answer: str
    provider: str
    model: str
    confidence: float
    hits: list[SearchHit]


@dataclass(frozen=True)
class RoutePlan:
    action: str
    confidence: float
    reason: str
    suggested_command: str
    args: dict[str, Any]


@dataclass(frozen=True)
class DiagnosisItem:
    manifest: str
    status: str
    detail: str


@dataclass(frozen=True)
class DiagnosisReport:
    target: str
    scanned_manifests: int
    items: list[DiagnosisItem]
    recommendations: list[str]


@dataclass(frozen=True)
class DiffExplainReport:
    old_path: str
    new_path: str
    added_count: int
    removed_count: int
    categories: dict[str, int]
    highlights: list[str]


def _ai_dir(root: Path) -> Path:
    d = root / ".ccbs" / "ai"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_db(root: Path) -> Path:
    return _ai_dir(root) / "index.db"


def _memory_db(root: Path) -> Path:
    return _ai_dir(root) / "memory.db"


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    try:
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


def _tokenize(text: str) -> list[str]:
    return [tok.lower() for tok in TOKEN_RE.findall(text) if len(tok) > 1]


def _token_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tok in _tokenize(text):
        counts[tok] = counts.get(tok, 0) + 1
    return counts


def _chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    clean = text.replace("\r\n", "\n")
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(clean):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _iter_text_files(target: Path, max_files: int) -> tuple[list[Path], int]:
    files: list[Path] = []
    skipped = 0
    if target.is_file():
        if target.suffix.lower() in TEXT_EXTENSIONS:
            return [target], 0
        return [], 1

    for path in sorted(target.rglob("*")):
        if len(files) >= max_files:
            skipped += 1
            continue
        if not path.is_file():
            continue
        parts = set(path.parts)
        if parts & IGNORE_DIRS:
            skipped += 1
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            skipped += 1
            continue
        files.append(path)
    return files, skipped


def ensure_offline_policy(provider: str, offline: bool) -> None:
    if provider not in LOCAL_PROVIDERS:
        raise RuntimeError(f"Unsupported provider: {provider}")
    if offline and provider not in LOCAL_PROVIDERS:
        raise RuntimeError(f"Provider '{provider}' blocked by offline policy")


def index_repository(root: Path, target: Path, max_files: int = 5000) -> IndexSummary:
    db = _index_db(root)
    files, skipped = _iter_text_files(target, max_files=max(1, max_files))

    with _connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                path TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                mtime REAL NOT NULL,
                content TEXT NOT NULL,
                token_counts TEXT NOT NULL,
                PRIMARY KEY (path, chunk_id)
            )
            """
        )
        indexed_chunks = 0
        indexed_files = 0

        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                skipped += 1
                continue

            rel = str(path.resolve().relative_to(root.resolve())) if path.is_absolute() else str(path)
            mtime = path.stat().st_mtime
            conn.execute("DELETE FROM chunks WHERE path = ?", (rel,))
            chunks = _chunk_text(text)
            for idx, chunk in enumerate(chunks, 1):
                counts = json.dumps(_token_counts(chunk), separators=(",", ":"), sort_keys=True)
                conn.execute(
                    "INSERT INTO chunks(path, chunk_id, mtime, content, token_counts) VALUES (?, ?, ?, ?, ?)",
                    (rel, idx, mtime, chunk, counts),
                )
                indexed_chunks += 1
            indexed_files += 1
        conn.commit()

    return IndexSummary(
        target=str(target),
        indexed_files=indexed_files,
        indexed_chunks=indexed_chunks,
        skipped_files=skipped,
    )


def _score_chunk(query_terms: set[str], token_counts: dict[str, int], content: str) -> float:
    score = 0.0
    for term in query_terms:
        score += float(token_counts.get(term, 0))
    content_lower = content.lower()
    for term in query_terms:
        if term in content_lower:
            score += 0.25
    return score


def search_index(root: Path, question: str, top_k: int = 5) -> list[SearchHit]:
    db = _index_db(root)
    if not db.exists():
        return []

    query_terms = set(_tokenize(question))
    if not query_terms:
        return []

    hits: list[SearchHit] = []
    with _connect(db) as conn:
        rows = conn.execute("SELECT path, chunk_id, content, token_counts FROM chunks").fetchall()
        for path, chunk_id, content, token_counts in rows:
            counts = json.loads(token_counts)
            score = _score_chunk(query_terms, counts, content)
            if score <= 0:
                continue
            hits.append(SearchHit(path=path, chunk_id=int(chunk_id), score=score, content=str(content)))
    hits.sort(key=lambda item: item.score, reverse=True)
    return hits[: max(1, top_k)]


def _build_context(hits: list[SearchHit]) -> str:
    lines: list[str] = []
    for idx, hit in enumerate(hits, 1):
        lines.append(f"[{idx}] {hit.path}#chunk{hit.chunk_id}")
        lines.append(hit.content)
        lines.append("")
    return "\n".join(lines).strip()


def _extractive_answer(question: str, hits: list[SearchHit]) -> str:
    if not hits:
        return "No indexed context matched your question. Run `ccbs ai index` and ask again."
    query_terms = set(_tokenize(question))
    selected: list[str] = []
    for idx, hit in enumerate(hits, 1):
        lines = [line.strip() for line in hit.content.splitlines() if line.strip()]
        best = ""
        best_score = -1
        for line in lines:
            score = sum(1 for term in query_terms if term in line.lower())
            if score > best_score:
                best = line
                best_score = score
        if not best and lines:
            best = lines[0]
        if best:
            selected.append(f"[{idx}] {best}")
    return "\n".join(selected[:5]) if selected else "No relevant text found."


def _run_ollama(model: str, prompt: str, timeout_s: int = 90) -> str:
    proc = subprocess.run(
        ["ollama", "run", model, prompt],
        text=True,
        capture_output=True,
        check=False,
        timeout=max(1, timeout_s),
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "unknown ollama error").strip())
    return proc.stdout.strip()


def answer_question(
    root: Path,
    question: str,
    provider: str = "extractive",
    model: str = "llama3.2:3b",
    top_k: int = 5,
    offline: bool = True,
) -> AnswerResult:
    ensure_offline_policy(provider, offline=offline)
    hits = search_index(root, question, top_k=max(1, top_k))
    context = _build_context(hits)
    confidence = 0.0 if not hits else min(0.99, hits[0].score / 8.0)

    if provider == "ollama":
        prompt = (
            "You are an offline repo assistant. Answer using only supplied context. "
            "If uncertain, say uncertain and cite relevant snippets.\n\n"
            f"Question:\n{question}\n\nContext:\n{context}\n"
        )
        try:
            answer = _run_ollama(model=model, prompt=prompt)
            used_provider = "ollama"
        except Exception as exc:  # noqa: BLE001
            fallback = _extractive_answer(question, hits)
            answer = f"Ollama unavailable ({exc}). Fallback extractive answer:\n{fallback}"
            used_provider = "extractive"
    else:
        answer = _extractive_answer(question, hits)
        used_provider = "extractive"

    return AnswerResult(
        question=question,
        answer=answer,
        provider=used_provider,
        model=model,
        confidence=confidence,
        hits=hits,
    )


def init_memory(root: Path) -> None:
    db = _memory_db(root)
    with _connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                metadata TEXT NOT NULL
            )
            """
        )
        conn.commit()


def store_memory(root: Path, kind: str, question: str, answer: str, metadata: dict[str, Any] | None = None) -> None:
    init_memory(root)
    db = _memory_db(root)
    payload = json.dumps(metadata or {}, separators=(",", ":"), sort_keys=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    with _connect(db) as conn:
        conn.execute(
            "INSERT INTO memory(ts, kind, question, answer, metadata) VALUES (?, ?, ?, ?, ?)",
            (now, kind, question, answer, payload),
        )
        conn.commit()


def load_memory(root: Path, limit: int = 20) -> list[dict[str, Any]]:
    db = _memory_db(root)
    if not db.exists():
        return []
    with _connect(db) as conn:
        rows = conn.execute(
            "SELECT ts, kind, question, answer, metadata FROM memory ORDER BY id DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
    output: list[dict[str, Any]] = []
    for ts, kind, question, answer, metadata in rows:
        output.append(
            {
                "ts": str(ts),
                "kind": str(kind),
                "question": str(question),
                "answer": str(answer),
                "metadata": json.loads(str(metadata) or "{}"),
            }
        )
    return output


def diagnose_target(target: Path) -> DiagnosisReport:
    manifests: list[Path] = []
    if target.is_file() and target.name == "manifest.json":
        manifests = [target]
    elif target.is_dir():
        manifests = sorted(target.rglob("manifest.json"))

    items: list[DiagnosisItem] = []
    recommendations: list[str] = []

    for path in manifests:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            items.append(DiagnosisItem(manifest=str(path), status="parse_error", detail=str(exc)))
            continue

        status = str(payload.get("status", "unknown"))
        detail = ""
        if status == "failed_step":
            steps = payload.get("steps", [])
            last = steps[-1] if isinstance(steps, list) and steps else {}
            detail = f"failed step={last.get('name')} rc={last.get('return_code')}"
            recommendations.append("Inspect step command stderr and rerun after fix.")
        elif status == "failed_proof":
            proof = payload.get("proof", [])
            failed = [p.get("name") for p in proof if isinstance(p, dict) and not p.get("ok", False)]
            detail = f"failed proof checks={', '.join(str(x) for x in failed)}"
            recommendations.append("Run proof commands manually and compare expected outputs.")
        elif status == "precondition_failed":
            detail = str(payload.get("error", "missing precondition"))
            recommendations.append("Check required CLI flags (for example --confirm).")
        elif status == "ok":
            detail = "run completed successfully"
        else:
            detail = f"status={status}"

        items.append(DiagnosisItem(manifest=str(path), status=status, detail=detail))

    if not manifests:
        recommendations.append("No manifest.json found under target path.")
    elif not recommendations:
        recommendations.append("No failure patterns detected in scanned manifests.")

    deduped = list(dict.fromkeys(recommendations))
    return DiagnosisReport(
        target=str(target),
        scanned_manifests=len(manifests),
        items=items,
        recommendations=deduped,
    )


def _command_category(command: str) -> str:
    c = command.strip().lower()
    if c.startswith("interface "):
        return "interface"
    if c.startswith("switchport"):
        return "switchport"
    if c.startswith("spanning-tree"):
        return "stp"
    if c.startswith("vlan ") or c.startswith("name "):
        return "vlan"
    if c.startswith("router ospf") or c.startswith("network "):
        return "ospf"
    if c.startswith("ip "):
        return "ip"
    if c.startswith("access-list") or c.startswith("ip access-list"):
        return "acl"
    if c.startswith("no "):
        return "negation"
    return "other"


def diff_explain(old_path: Path, new_path: Path) -> DiffExplainReport:
    old_lines = old_path.read_text(encoding="utf-8").splitlines()
    new_lines = new_path.read_text(encoding="utf-8").splitlines()

    diff = list(difflib.ndiff(old_lines, new_lines))
    added = [line[2:].strip() for line in diff if line.startswith("+ ") and line[2:].strip()]
    removed = [line[2:].strip() for line in diff if line.startswith("- ") and line[2:].strip()]

    categories: dict[str, int] = {}
    for cmd in added + removed:
        cat = _command_category(cmd)
        categories[cat] = categories.get(cat, 0) + 1

    highlights: list[str] = []
    for item in added[:5]:
        highlights.append(f"ADD: {item}")
    for item in removed[:5]:
        highlights.append(f"REMOVE: {item}")

    return DiffExplainReport(
        old_path=str(old_path),
        new_path=str(new_path),
        added_count=len(added),
        removed_count=len(removed),
        categories=dict(sorted(categories.items(), key=lambda item: item[0])),
        highlights=highlights,
    )


def route_request(request: str) -> RoutePlan:
    text = request.strip().lower()
    if not text:
        return RoutePlan(
            action="none",
            confidence=0.0,
            reason="empty request",
            suggested_command="",
            args={},
        )

    if "apply-link-ports" in text or "link ports" in text or "autofill" in text:
        return RoutePlan(
            action="pt_apply_link_ports",
            confidence=0.9,
            reason="request mentions link-port autofill",
            suggested_command="ccbs pt apply-link-ports <path> --write",
            args={"write": True},
        )
    if "preflight" in text or "unresolved" in text:
        return RoutePlan(
            action="pt_preflight",
            confidence=0.92,
            reason="request matches preflight/tolerance checks",
            suggested_command="ccbs pt preflight <path> --mode deploy",
            args={"mode": "deploy"},
        )
    if "validate all" in text:
        return RoutePlan(
            action="validate_all",
            confidence=0.95,
            reason="request explicitly asks to validate all",
            suggested_command="ccbs validate all",
            args={},
        )
    if "doctor" in text:
        return RoutePlan(
            action="doctor",
            confidence=0.85,
            reason="request mentions doctor diagnostics",
            suggested_command="ccbs doctor",
            args={},
        )
    if "repo root" in text:
        return RoutePlan(
            action="repo_root",
            confidence=0.9,
            reason="request asks for repository root",
            suggested_command="ccbs repo-root",
            args={},
        )
    return RoutePlan(
        action="ai_answer",
        confidence=0.55,
        reason="no direct tool mapping; route to local Q&A",
        suggested_command="ccbs ai answer \"<question>\"",
        args={},
    )
