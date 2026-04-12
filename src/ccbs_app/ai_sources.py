"""Curated source catalog and raw mirror sync for offline ingestion."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .ai_storage import StorageLimitError, ai2_dir, usage_report

# Conservative default allowlist; admins can extend it explicitly.
DEFAULT_ALLOWED_DOMAINS = sorted(
    {
        "dumps.wikimedia.org",
        "open.umn.edu",
        "ocw.mit.edu",
        "openstax.org",
        "libretexts.org",
        "ourworldindata.org",
        "www.un.org",
        "plato.stanford.edu",
        "www.gutenberg.org",
        "standardebooks.org",
        "www.worldhistory.org",
        "education.cfr.org",
        "www.survivorlibrary.com",
        "www.explainthatstuff.com",
        "ollama.com",
        "lmstudio.ai",
        "localai.io",
        "jan.ai",
        "anythingllm.com",
        "github.com",
        "raw.githubusercontent.com",
    }
)

ALLOWED_LICENSE_PREFIX = (
    "public-domain",
    "cc-by",
    "cc-by-sa",
    "cc0",
    "mit",
    "apache-2.0",
    "bsd",
    "gpl",
    "proprietary-local-permitted",
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _sources_dir(root: Path) -> Path:
    out = ai2_dir(root) / "sources"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _manifest_path(root: Path) -> Path:
    return _sources_dir(root) / "source_manifest.json"


def _raw_dir(root: Path) -> Path:
    out = _sources_dir(root) / "raw"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _normalized_dir(root: Path) -> Path:
    out = _sources_dir(root) / "normalized"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _is_license_allowed(license_name: str) -> bool:
    low = license_name.strip().lower()
    return any(low.startswith(prefix) for prefix in ALLOWED_LICENSE_PREFIX)


def load_source_manifest(root: Path) -> dict[str, Any]:
    path = _manifest_path(root)
    if not path.exists():
        payload = {
            "version": "ai-source-manifest-v1",
            "allowed_domains": list(DEFAULT_ALLOWED_DOMAINS),
            "sources": [],
            "updated_at": _now(),
        }
        save_source_manifest(root, payload)
        return payload

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {
            "version": "ai-source-manifest-v1",
            "allowed_domains": list(DEFAULT_ALLOWED_DOMAINS),
            "sources": [],
            "updated_at": _now(),
        }
        save_source_manifest(root, payload)
        return payload

    if "sources" not in payload or not isinstance(payload["sources"], list):
        payload["sources"] = []
    if "allowed_domains" not in payload or not isinstance(payload["allowed_domains"], list):
        payload["allowed_domains"] = list(DEFAULT_ALLOWED_DOMAINS)
    return payload


def save_source_manifest(root: Path, payload: dict[str, Any]) -> None:
    out = dict(payload)
    out["version"] = "ai-source-manifest-v1"
    out["updated_at"] = _now()
    path = _manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")


def list_sources(root: Path) -> list[dict[str, Any]]:
    return list(load_source_manifest(root).get("sources", []))


def add_allowed_domain(root: Path, domain: str) -> dict[str, Any]:
    d = domain.strip().lower()
    if not d:
        raise ValueError("domain is required")
    payload = load_source_manifest(root)
    domains = sorted({str(x).strip().lower() for x in payload.get("allowed_domains", []) if str(x).strip()} | {d})
    payload["allowed_domains"] = domains
    save_source_manifest(root, payload)
    return {"allowed_domains": domains}


def _parse_kind(uri: str) -> str:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme in {"http", "https"}:
        return "url"
    p = Path(uri)
    if p.exists() and p.is_dir():
        return "dir"
    return "file"


def add_source(
    root: Path,
    source_id: str,
    uri: str,
    license_name: str,
    source_name: str = "",
    notes: str = "",
) -> dict[str, Any]:
    sid = source_id.strip().lower()
    if not sid:
        raise ValueError("source_id is required")
    if not uri.strip():
        raise ValueError("uri is required")
    if not _is_license_allowed(license_name):
        raise ValueError("license not allowed by curated policy")

    payload = load_source_manifest(root)
    kind = _parse_kind(uri.strip())
    allowed_domains = {str(x).strip().lower() for x in payload.get("allowed_domains", [])}

    if kind == "url":
        parsed = urllib.parse.urlparse(uri.strip())
        if parsed.scheme != "https":
            raise ValueError("only https sources are allowed")
        domain = (parsed.hostname or "").lower()
        if domain not in allowed_domains:
            raise ValueError(f"domain not allowlisted: {domain}")

    rec = {
        "source_id": sid,
        "name": source_name.strip() or sid,
        "uri": uri.strip(),
        "kind": kind,
        "license": license_name.strip(),
        "notes": notes.strip(),
        "status": "added",
        "raw_path": "",
        "synced_at": "",
        "bytes": 0,
        "sha256": "",
        "normalized_files": 0,
        "last_error": "",
    }

    sources = list(payload.get("sources", []))
    replaced = False
    for idx, item in enumerate(sources):
        if str(item.get("source_id", "")).strip().lower() == sid:
            sources[idx] = rec
            replaced = True
            break
    if not replaced:
        sources.append(rec)

    payload["sources"] = sorted(sources, key=lambda x: str(x.get("source_id", "")))
    save_source_manifest(root, payload)
    return rec


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _copy_file_with_capacity(
    src: Path,
    dst: Path,
    stage: str,
    reserve_capacity: Callable[[int, str], None],
) -> int:
    size = int(src.stat().st_size)
    reserve_capacity(size, stage)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return int(dst.stat().st_size)


def _download_with_capacity(
    uri: str,
    dst: Path,
    stage: str,
    reserve_capacity: Callable[[int, str], None],
) -> int:
    dst.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(uri, method="GET")
    written = 0
    with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
        content_len = resp.headers.get("Content-Length")
        if content_len:
            reserve_capacity(int(content_len), stage)

        with dst.open("wb") as out:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                try:
                    reserve_capacity(len(chunk), stage)
                except StorageLimitError:
                    out.close()
                    dst.unlink(missing_ok=True)
                    raise
                out.write(chunk)
                written += len(chunk)
    return written


def sync_source(root: Path, source_id: str) -> dict[str, Any]:
    sid = source_id.strip().lower()
    payload = load_source_manifest(root)
    sources = list(payload.get("sources", []))
    target_idx = -1
    for idx, item in enumerate(sources):
        if str(item.get("source_id", "")).strip().lower() == sid:
            target_idx = idx
            break
    if target_idx < 0:
        raise ValueError(f"source not found: {sid}")

    item = dict(sources[target_idx])
    kind = str(item.get("kind", ""))
    uri = str(item.get("uri", "")).strip()
    stage = f"sync:{sid}"
    storage = usage_report(root)
    max_bytes = int(storage.max_bytes)
    current_bytes = int(storage.total_bytes)

    def reserve_capacity(incoming_bytes: int, stage_name: str) -> None:
        nonlocal current_bytes
        incoming = max(0, int(incoming_bytes))
        if current_bytes + incoming > max_bytes:
            raise StorageLimitError(
                stage=stage_name,
                current_bytes=current_bytes,
                incoming_bytes=incoming,
                max_bytes=max_bytes,
            )
        current_bytes += incoming

    raw_base = _raw_dir(root) / sid
    if raw_base.exists():
        shutil.rmtree(raw_base)
    raw_base.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    if kind == "url":
        parsed = urllib.parse.urlparse(uri)
        fname = Path(parsed.path).name or "index.html"
        dst = raw_base / fname
        total_bytes = _download_with_capacity(uri=uri, dst=dst, stage=stage, reserve_capacity=reserve_capacity)
    elif kind == "file":
        src = Path(uri).expanduser()
        if not src.exists() or not src.is_file():
            raise ValueError(f"file source not found: {src}")
        total_bytes = _copy_file_with_capacity(src=src, dst=raw_base / src.name, stage=stage, reserve_capacity=reserve_capacity)
    elif kind == "dir":
        src_dir = Path(uri).expanduser()
        if not src_dir.exists() or not src_dir.is_dir():
            raise ValueError(f"directory source not found: {src_dir}")
        for p in sorted(src_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(src_dir)
            dst = raw_base / rel
            total_bytes += _copy_file_with_capacity(src=p, dst=dst, stage=stage, reserve_capacity=reserve_capacity)
    else:
        raise ValueError(f"unsupported source kind: {kind}")

    file_for_hash: Path | None = None
    for p in sorted(raw_base.rglob("*")):
        if p.is_file():
            file_for_hash = p
            break
    digest = ""
    if file_for_hash is not None:
        digest = _sha256(file_for_hash)

    item["status"] = "synced"
    item["raw_path"] = str(raw_base)
    item["synced_at"] = _now()
    item["bytes"] = int(total_bytes)
    item["sha256"] = digest
    item["last_error"] = ""

    sources[target_idx] = item
    payload["sources"] = sources
    save_source_manifest(root, payload)
    return item


def remove_source(root: Path, source_id: str, delete_files: bool = True) -> dict[str, Any]:
    sid = source_id.strip().lower()
    payload = load_source_manifest(root)
    sources = list(payload.get("sources", []))
    keep: list[dict[str, Any]] = []
    removed: dict[str, Any] | None = None

    for item in sources:
        if str(item.get("source_id", "")).strip().lower() == sid:
            removed = dict(item)
            continue
        keep.append(item)

    if removed is None:
        raise ValueError(f"source not found: {sid}")

    if delete_files:
        raw = _raw_dir(root) / sid
        norm = _normalized_dir(root) / sid
        if raw.exists():
            shutil.rmtree(raw, ignore_errors=True)
        if norm.exists():
            shutil.rmtree(norm, ignore_errors=True)

    payload["sources"] = keep
    save_source_manifest(root, payload)
    return {"removed": sid, "delete_files": bool(delete_files)}
