"""Normalization and ingestion pipeline for mirrored offline sources."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from .ai_sources import load_source_manifest, save_source_manifest
from .ai_storage import StorageLimitError, usage_report

TEXT_EXT = {
    ".txt",
    ".md",
    ".rst",
    ".py",
    ".ps1",
    ".sh",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
}


TAG_RE = re.compile(r"<[^>]+>")


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _read_text_file(path: Path) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return ""


def _normalize_html(text: str) -> str:
    clean = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", html.unescape(clean)).strip()


def _normalize_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            data = zf.read("word/document.xml")
    except Exception:
        return ""
    txt = data.decode("utf-8", errors="ignore")
    txt = txt.replace("</w:p>", "\n")
    txt = TAG_RE.sub(" ", txt)
    return re.sub(r"\s+", " ", html.unescape(txt)).strip()


def _normalize_json(path: Path) -> str:
    try:
        payload = json.loads(_read_text_file(path))
    except Exception:
        return _read_text_file(path)
    return json.dumps(payload, indent=2, sort_keys=True)


def _normalize_csv(path: Path) -> str:
    try:
        rows: list[str] = []
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            for row in reader:
                rows.append(" | ".join(row))
        return "\n".join(rows)
    except Exception:
        return _read_text_file(path)


def normalize_file(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXT:
        return _read_text_file(path), "text"
    if suffix == ".json":
        return _normalize_json(path), "json"
    if suffix == ".csv":
        return _normalize_csv(path), "csv"
    if suffix in {".html", ".htm"}:
        return _normalize_html(_read_text_file(path)), "html"
    if suffix == ".docx":
        return _normalize_docx(path), "docx"
    if suffix == ".pdf":
        # Keep deterministic fallback text until a local PDF parser pack is installed.
        return f"PDF placeholder: {path.name} (install optional PDF parser plugin for full text extraction)", "pdf_placeholder"
    return "", "unsupported"


def _iter_raw_files(raw_path: Path) -> list[Path]:
    if raw_path.is_file():
        return [raw_path]
    out: list[Path] = []
    for p in sorted(raw_path.rglob("*")):
        if p.is_file():
            out.append(p)
    return out


def ingest_sources(root: Path, source_id: str = "", max_files: int = 50000) -> dict[str, Any]:
    payload = load_source_manifest(root)
    sources = list(payload.get("sources", []))
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

    selected: list[dict[str, Any]] = []
    for item in sources:
        sid = str(item.get("source_id", "")).strip().lower()
        if source_id.strip() and sid != source_id.strip().lower():
            continue
        status = str(item.get("status", ""))
        if status not in {"synced", "normalized"}:
            continue
        selected.append(item)

    normalized_total = 0
    skipped = 0
    written_bytes = 0

    for item in selected:
        sid = str(item.get("source_id", "")).strip().lower()
        raw_path = Path(str(item.get("raw_path", "")))
        if not raw_path.exists():
            item["status"] = "sync_missing"
            item["last_error"] = f"raw path missing: {raw_path}"
            continue

        out_base = root / ".ccbs" / "ai2" / "sources" / "normalized" / sid
        out_base.mkdir(parents=True, exist_ok=True)

        files = _iter_raw_files(raw_path)
        count = 0
        for src in files:
            if count >= max(1, int(max_files)):
                skipped += 1
                continue

            text, norm_kind = normalize_file(src)
            if not text.strip():
                skipped += 1
                continue

            rel = src.relative_to(raw_path)
            out_text = out_base / rel.with_suffix(rel.suffix + ".txt")
            out_meta = out_base / rel.with_suffix(rel.suffix + ".meta.json")
            out_text.parent.mkdir(parents=True, exist_ok=True)

            blob = text.encode("utf-8", errors="ignore")
            reserve_capacity(incoming_bytes=len(blob), stage=f"normalize:{sid}")
            out_text.write_text(text, encoding="utf-8")
            written_bytes += len(blob)

            meta = {
                "source_id": sid,
                "license": str(item.get("license", "")),
                "raw_path": str(src),
                "normalized_path": str(out_text),
                "normalized_kind": norm_kind,
                "sha256": _sha256_bytes(blob),
                "bytes": len(blob),
            }
            out_meta.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

            normalized_total += 1
            count += 1

        item["normalized_files"] = count
        item["status"] = "normalized"
        item["last_error"] = ""

    payload["sources"] = sources
    save_source_manifest(root, payload)
    return {
        "source_id": source_id.strip().lower(),
        "normalized_files": normalized_total,
        "skipped_files": skipped,
        "written_bytes": written_bytes,
        "sources_processed": len(selected),
    }


def ingest_status(root: Path) -> dict[str, Any]:
    payload = load_source_manifest(root)
    sources = payload.get("sources", [])
    total_norm = 0
    status_counts: dict[str, int] = {}
    for item in sources:
        total_norm += int(item.get("normalized_files", 0) or 0)
        status = str(item.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "source_count": len(sources),
        "normalized_files": total_norm,
        "status_counts": status_counts,
    }
