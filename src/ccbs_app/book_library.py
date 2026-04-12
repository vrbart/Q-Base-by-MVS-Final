"""Local book catalog + notes import helpers for user-owned study resources.

This module stores metadata only and user-provided notes/highlights.
It does not attempt to extract or bypass DRM-protected ebook content.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _books_dir(root: Path) -> Path:
    out = root / ".ccbs" / "books"
    out.mkdir(parents=True, exist_ok=True)
    return out


def library_path(root: Path) -> Path:
    return _books_dir(root) / "library.json"


def notes_dir(root: Path) -> Path:
    out = _books_dir(root) / "notes"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _default_library() -> dict[str, Any]:
    return {
        "version": 1,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "books": [],
        "imports": [],
    }


def load_library(root: Path) -> dict[str, Any]:
    target = library_path(root)
    if not target.exists():
        payload = _default_library()
        save_library(root, payload)
        return payload

    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("book library file must be a JSON object")
    if not isinstance(data.get("books", []), list):
        raise ValueError("book library 'books' must be an array")
    if not isinstance(data.get("imports", []), list):
        raise ValueError("book library 'imports' must be an array")
    data.setdefault("version", 1)
    data.setdefault("created_at", _utc_now())
    data["updated_at"] = data.get("updated_at") or _utc_now()
    return data


def save_library(root: Path, payload: dict[str, Any]) -> Path:
    payload = dict(payload)
    payload["updated_at"] = _utc_now()
    target = library_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def _slugify_book_id(raw: str) -> str:
    allowed = []
    for ch in (raw or "").strip().lower():
        if ch.isalnum():
            allowed.append(ch)
        elif ch in {" ", "-", "_", "."}:
            allowed.append("-")
    out = "".join(allowed).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "book"


def load_seed_books(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("books"), list):
        raise ValueError(f"invalid seed file: {path}")
    out: list[dict[str, Any]] = []
    for item in data["books"]:
        if not isinstance(item, dict):
            continue
        book = dict(item)
        title = str(book.get("title", "")).strip()
        if not title:
            continue
        book_id = str(book.get("book_id", "")).strip() or _slugify_book_id(title)
        book["book_id"] = book_id
        book.setdefault("tags", [])
        book.setdefault("authors", [])
        book.setdefault("source_platform", "Bookshelf")
        out.append(book)
    return out


def seed_books(root: Path, books: list[dict[str, Any]], replace: bool = False) -> dict[str, Any]:
    payload = load_library(root)
    existing: dict[str, dict[str, Any]] = {
        str(item.get("book_id")): dict(item)
        for item in payload.get("books", [])
        if isinstance(item, dict) and str(item.get("book_id", "")).strip()
    }

    inserted = 0
    updated = 0
    now = _utc_now()

    for incoming in books:
        book = dict(incoming)
        book_id = str(book.get("book_id", "")).strip()
        if not book_id:
            continue
        if book_id in existing and not replace:
            continue

        prev = existing.get(book_id)
        created_at = str(prev.get("created_at")) if isinstance(prev, dict) and prev.get("created_at") else now
        merged = {
            "book_id": book_id,
            "title": str(book.get("title", "")).strip(),
            "edition": str(book.get("edition", "")).strip(),
            "authors": [str(x).strip() for x in book.get("authors", []) if str(x).strip()],
            "publisher": str(book.get("publisher", "")).strip(),
            "source_platform": str(book.get("source_platform", "Bookshelf")).strip() or "Bookshelf",
            "status": str(book.get("status", "metadata_only")).strip() or "metadata_only",
            "drm_notice": str(
                book.get(
                    "drm_notice",
                    "Catalog entry only. Add your exported notes/highlights to use content inside CCBS.",
                )
            ).strip(),
            "tags": [str(x).strip() for x in book.get("tags", []) if str(x).strip()],
            "created_at": created_at,
            "updated_at": now,
            "notes_count": int(prev.get("notes_count", 0)) if isinstance(prev, dict) else 0,
            "note_files": list(prev.get("note_files", [])) if isinstance(prev, dict) else [],
        }
        existing[book_id] = merged
        if prev is None:
            inserted += 1
        else:
            updated += 1

    payload["books"] = sorted(existing.values(), key=lambda item: str(item.get("title", "")).lower())
    target = save_library(root, payload)
    return {
        "inserted": inserted,
        "updated": updated,
        "total_books": len(payload["books"]),
        "library_path": str(target),
    }


def list_books(root: Path, query: str = "", tag: str = "") -> list[dict[str, Any]]:
    payload = load_library(root)
    q = (query or "").strip().lower()
    tg = (tag or "").strip().lower()
    rows: list[dict[str, Any]] = []
    for item in payload.get("books", []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", ""))
        book_id = str(item.get("book_id", ""))
        tags = [str(x).lower() for x in item.get("tags", [])]
        if q:
            hay = " ".join(
                [
                    title.lower(),
                    book_id.lower(),
                    str(item.get("edition", "")).lower(),
                    " ".join(str(a).lower() for a in item.get("authors", [])),
                ]
            )
            if q not in hay:
                continue
        if tg and tg not in tags:
            continue
        rows.append(item)
    return rows


def get_book(root: Path, book_id: str) -> dict[str, Any] | None:
    needle = (book_id or "").strip().lower()
    for item in load_library(root).get("books", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("book_id", "")).strip().lower() == needle:
            return item
    return None


def _normalize_note_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for raw in lines:
        text = " ".join(str(raw).strip().split())
        if text:
            out.append(text)
    # Preserve order while deduping.
    seen: set[str] = set()
    deduped: list[str] = []
    for item in out:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _extract_notes_from_json(path: Path) -> list[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    rows: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                rows.append(item)
            elif isinstance(item, dict):
                for key in ("text", "note", "highlight", "content", "quote"):
                    if key in item and str(item[key]).strip():
                        rows.append(str(item[key]))
                        break
    elif isinstance(value, dict):
        for key in ("notes", "highlights", "items"):
            seq = value.get(key)
            if isinstance(seq, list):
                for item in seq:
                    if isinstance(item, str):
                        rows.append(item)
                    elif isinstance(item, dict):
                        for k in ("text", "note", "highlight", "content", "quote"):
                            if k in item and str(item[k]).strip():
                                rows.append(str(item[k]))
                                break
    return _normalize_note_lines(rows)


def _extract_notes_from_csv(path: Path) -> list[str]:
    rows: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames:
            candidates = [str(name).strip() for name in reader.fieldnames]
            preferred = ["text", "note", "highlight", "content", "quote"]
            selected = None
            for pick in preferred:
                for field in candidates:
                    if field.lower() == pick:
                        selected = field
                        break
                if selected:
                    break
            if selected:
                for row in reader:
                    value = str(row.get(selected, "")).strip()
                    if value:
                        rows.append(value)
            else:
                # Fallback: first non-empty cell in each row.
                for row in reader:
                    for field in candidates:
                        value = str(row.get(field, "")).strip()
                        if value:
                            rows.append(value)
                            break
    return _normalize_note_lines(rows)


def _extract_notes_from_text(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    return _normalize_note_lines(rows)


def import_notes(root: Path, book_id: str, source_path: Path, fmt: str = "auto") -> dict[str, Any]:
    if not source_path.exists():
        raise FileNotFoundError(f"path not found: {source_path}")

    book = get_book(root, book_id)
    if book is None:
        raise ValueError(f"book not found: {book_id}")

    format_hint = (fmt or "auto").strip().lower()
    if format_hint == "auto":
        suffix = source_path.suffix.lower()
        if suffix in {".md", ".txt"}:
            format_hint = "text"
        elif suffix == ".json":
            format_hint = "json"
        elif suffix == ".csv":
            format_hint = "csv"
        else:
            format_hint = "text"

    if format_hint == "json":
        notes = _extract_notes_from_json(source_path)
    elif format_hint == "csv":
        notes = _extract_notes_from_csv(source_path)
    elif format_hint in {"text", "txt", "md"}:
        notes = _extract_notes_from_text(source_path)
    else:
        raise ValueError("format must be one of: auto, text, json, csv")

    if not notes:
        raise ValueError("no notes/highlights parsed from source file")

    note_root = notes_dir(root)
    safe_id = _slugify_book_id(book_id)
    out_file = note_root / f"{safe_id}.md"

    lines = [
        f"# Notes: {book.get('title', safe_id)}",
        "",
        f"- Imported at: {_utc_now()}",
        f"- Source file: {source_path}",
        f"- Parsed entries: {len(notes)}",
        "",
    ]
    for item in notes:
        lines.append(f"- {item}")
    lines.append("")
    out_file.write_text("\n".join(lines), encoding="utf-8")

    payload = load_library(root)
    for item in payload.get("books", []):
        if isinstance(item, dict) and str(item.get("book_id", "")).strip().lower() == book_id.strip().lower():
            item["notes_count"] = len(notes)
            item["status"] = "notes_imported"
            files = [str(x) for x in item.get("note_files", []) if str(x).strip()]
            rel = str(out_file.relative_to(root))
            if rel not in files:
                files.append(rel)
            item["note_files"] = files
            item["updated_at"] = _utc_now()
            break

    imports = payload.get("imports", [])
    if not isinstance(imports, list):
        imports = []
        payload["imports"] = imports
    imports.append(
        {
            "book_id": str(book_id),
            "source_path": str(source_path),
            "format": format_hint,
            "notes_count": len(notes),
            "saved_path": str(out_file),
            "imported_at": _utc_now(),
        }
    )
    save_library(root, payload)
    return {
        "book_id": str(book_id),
        "format": format_hint,
        "notes_count": len(notes),
        "saved_path": str(out_file),
        "library_path": str(library_path(root)),
    }


def export_import_template(path: Path, fmt: str = "json") -> Path:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    flavor = fmt.strip().lower()
    if flavor == "csv":
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["text"])
            writer.writerow(["Example note or highlight line 1"])
            writer.writerow(["Example note or highlight line 2"])
        return target
    if flavor == "json":
        payload = {
            "notes": [
                {"text": "Example note or highlight line 1"},
                {"text": "Example note or highlight line 2"},
            ]
        }
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target
    raise ValueError("template format must be json or csv")
