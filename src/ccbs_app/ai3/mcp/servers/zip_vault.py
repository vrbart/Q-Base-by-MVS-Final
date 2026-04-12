"""ZIP vault MCP server."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any

from ...retrieval.vault_catalog import is_path_allowed, load_catalog


DEFAULT_ENTRY_BYTES_CAP = 32 * 1024 * 1024


def _is_safe_inner_path(inner_path: str) -> bool:
    text = str(inner_path or "").replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("\\"):
        return False
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        return False
    parts = [part for part in Path(text).parts if part not in {"", "."}]
    if not parts:
        return False
    return ".." not in parts


def _candidate_catalog_paths() -> list[Path]:
    env = str(os.environ.get("CCBS_VAULT_CATALOG_PATH", "")).strip()
    out: list[Path] = []
    if env:
        out.append(Path(env).expanduser())
    cwd = Path.cwd()
    out.append(cwd / "config" / "offline-vault.catalog.json")
    for parent in list(cwd.parents)[:5]:
        out.append(parent / "config" / "offline-vault.catalog.json")
    return out


def _allowlist_roots() -> list[Path]:
    env = str(os.environ.get("CCBS_VAULT_ALLOWLIST", "")).strip()
    if env:
        roots: list[Path] = []
        for item in [part.strip() for part in env.split(";")]:
            if not item:
                continue
            roots.append(Path(item).expanduser().resolve())
        if roots:
            return roots
    for candidate in _candidate_catalog_paths():
        if not candidate.exists():
            continue
        try:
            catalog = load_catalog(candidate)
            rows = [Path(str(item)).expanduser().resolve() for item in catalog.get("allowlist_roots", [])]
            if rows:
                return rows
        except Exception:
            continue
    return []


def _entry_cap_bytes() -> int:
    raw = str(os.environ.get("CCBS_VAULT_MAX_ENTRY_BYTES", str(DEFAULT_ENTRY_BYTES_CAP))).strip()
    try:
        return max(1024, int(raw))
    except Exception:
        return DEFAULT_ENTRY_BYTES_CAP


def _enforce_allowed_zip_path(target: Path) -> None:
    allowlist = _allowlist_roots()
    if not allowlist:
        return
    if not is_path_allowed(target, allowlist):
        raise PermissionError(f"zip path outside allowlist roots: {target}")


def list_entries(zip_path: str, prefix: str = "", limit: int = 200) -> dict[str, Any]:
    target = Path(zip_path).expanduser().resolve()
    _enforce_allowed_zip_path(target)
    cap = max(1, int(limit))
    safe_cap = min(cap, 10000)
    rows: list[str] = []
    skipped_unsafe = 0
    with zipfile.ZipFile(target, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = str(info.filename)
            if not _is_safe_inner_path(name):
                skipped_unsafe += 1
                continue
            if prefix and not name.startswith(prefix):
                continue
            rows.append(name)
            if len(rows) >= safe_cap:
                break
    return {"zip_path": str(target), "count": len(rows), "entries": rows, "skipped_unsafe": skipped_unsafe}


def read_entry(zip_path: str, inner_path: str, max_bytes: int = 131072) -> dict[str, Any]:
    target = Path(zip_path).expanduser().resolve()
    _enforce_allowed_zip_path(target)
    if not _is_safe_inner_path(inner_path):
        raise ValueError("inner_path is unsafe")
    entry_cap = _entry_cap_bytes()
    cap = min(max(1, int(max_bytes)), entry_cap)
    with zipfile.ZipFile(target, "r") as zf:
        info = zf.getinfo(inner_path)
        if info.is_dir():
            raise ValueError("inner_path points to a directory")
        if int(info.file_size) > entry_cap:
            raise ValueError("entry size exceeds configured cap")
        blob = zf.read(info)
    chunk = blob[:cap]
    text = chunk.decode("utf-8", errors="ignore")
    return {
        "zip_path": str(target),
        "inner_path": inner_path,
        "size_bytes": len(blob),
        "returned_bytes": len(chunk),
        "truncated": len(blob) > cap,
        "max_entry_bytes": entry_cap,
        "content": text,
    }
