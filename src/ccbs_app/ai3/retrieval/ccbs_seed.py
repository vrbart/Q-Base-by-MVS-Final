"""Deterministic CCBS seed package builder for offline vault bootstrap."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from .vault_catalog import load_catalog, resolve_runtime_vault_root


CCBS_RE = re.compile(r"ccbs", re.IGNORECASE)
DEFAULT_PACKAGE_RELPATH = "80_MISC/ccbs_repo_bootstrap/ccbs_repo_bootstrap.zip"
DEFAULT_PACKAGE_ID = "MIS-CCBS-REPO-BOOTSTRAP"
DEFAULT_SOURCE_ID = "MIS"

DEFAULT_SOURCE_NAMES = {
    "FMS": "Mathematics & Formal Sciences",
    "NAT": "Natural Sciences",
    "SOC": "Social Sciences & Civics",
    "HUM": "Humanities & Arts",
    "APT": "Applied Sciences & Technology",
    "MED": "Health & Medicine",
    "LIF": "Practical & Life Skills",
    "MIS": "Miscellaneous & Interdisciplinary",
}


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _safe_repo_relpath(raw: str) -> str:
    text = str(raw or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("../") or "/../" in text:
        raise ValueError(f"unsafe relative path: {raw}")
    return text


def _git_ls_files(root: Path, *, include_untracked: bool) -> list[str]:
    def _run(args: list[str]) -> list[str]:
        proc = subprocess.run(args, cwd=str(root), capture_output=True, check=False)
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="ignore").strip()
            raise ValueError(f"git listing failed: {stderr or proc.returncode}")
        raw = proc.stdout.decode("utf-8", errors="ignore")
        return [item for item in raw.split("\0") if item]

    tracked = _run(["git", "ls-files", "-z"])
    if not include_untracked:
        return sorted(set(tracked))
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard", "-z"])
    return sorted(set([*tracked, *untracked]))


def _decode_text(blob: bytes) -> str | None:
    head = blob[:8192]
    if b"\x00" in head:
        return None
    try:
        return blob.decode("utf-8")
    except Exception:
        try:
            return blob.decode("latin-1")
        except Exception:
            return None


def scan_ccbs_matches(
    *,
    repo_root: Path,
    include_untracked: bool = False,
    candidate_relpaths: list[str] | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    raw_paths = list(candidate_relpaths or _git_ls_files(root, include_untracked=include_untracked))
    selected: list[dict[str, Any]] = []

    for raw in sorted(set(raw_paths)):
        rel = _safe_repo_relpath(raw)
        abs_path = (root / rel).resolve()
        if not abs_path.exists() or not abs_path.is_file():
            continue

        blob = abs_path.read_bytes()
        path_match = bool(CCBS_RE.search(rel))
        decoded = _decode_text(blob)
        content_match = bool(decoded is not None and CCBS_RE.search(decoded))
        if not path_match and not content_match:
            continue

        if path_match and content_match:
            match_reason = "path+content"
        elif path_match:
            match_reason = "path"
        else:
            match_reason = "content"

        kind = "text" if decoded is not None else "binary_metadata_only"
        selected.append(
            {
                "relative_path": rel,
                "match_reason": match_reason,
                "sha256": _sha256_bytes(blob),
                "size_bytes": len(blob),
                "kind": kind,
                "_blob": blob if kind == "text" else None,
            }
        )

    selected.sort(key=lambda item: str(item["relative_path"]).lower())

    path_only = sum(1 for item in selected if item["match_reason"] == "path")
    content_only = sum(1 for item in selected if item["match_reason"] == "content")
    both = sum(1 for item in selected if item["match_reason"] == "path+content")
    text_count = sum(1 for item in selected if item["kind"] == "text")
    binary_count = sum(1 for item in selected if item["kind"] == "binary_metadata_only")

    manifest_entries = [
        {
            "relative_path": str(item["relative_path"]),
            "match_reason": str(item["match_reason"]),
            "sha256": str(item["sha256"]),
            "size_bytes": int(item["size_bytes"]),
            "kind": str(item["kind"]),
        }
        for item in selected
    ]

    return {
        "entries": selected,
        "manifest": {
            "version": 1,
            "pattern": "(?i)ccbs",
            "selection_mode": "path_or_content_union",
            "counts": {
                "selected": len(selected),
                "text": text_count,
                "binary_metadata_only": binary_count,
                "path_only": path_only,
                "content_only": content_only,
                "path_and_content": both,
            },
            "entries": manifest_entries,
        },
    }


def write_ccbs_seed_package(
    *,
    repo_root: Path,
    vault_root: Path,
    package_relpath: str = DEFAULT_PACKAGE_RELPATH,
    include_untracked: bool = False,
    candidate_relpaths: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    scan = scan_ccbs_matches(
        repo_root=root,
        include_untracked=include_untracked,
        candidate_relpaths=candidate_relpaths,
    )

    rel = _safe_repo_relpath(package_relpath)
    zip_path = (vault_root.expanduser().resolve() / rel).resolve()

    out = {
        "repo_root": str(root),
        "vault_root": str(vault_root.expanduser().resolve()),
        "zip_relpath": rel,
        "zip_path": str(zip_path),
        "dry_run": bool(dry_run),
        "manifest": dict(scan["manifest"]),
    }

    if dry_run:
        return out

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in scan["entries"]:
            if item["kind"] != "text":
                continue
            blob = item.get("_blob")
            if isinstance(blob, bytes):
                zf.writestr(str(item["relative_path"]), blob)
        zf.writestr("CCBS_MATCH_MANIFEST.json", json.dumps(scan["manifest"], indent=2, sort_keys=True).encode("utf-8"))

    out["size_bytes"] = int(zip_path.stat().st_size)
    out["zip_sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    return out


def upsert_catalog_ccbs_package(
    *,
    catalog_path: Path,
    source_id: str = DEFAULT_SOURCE_ID,
    package_id: str = DEFAULT_PACKAGE_ID,
    zip_relpath: str = DEFAULT_PACKAGE_RELPATH,
) -> dict[str, Any]:
    target = catalog_path.expanduser().resolve()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog JSON must be an object")

    payload.setdefault("version", 1)
    payload.setdefault("runtime", {})
    if not isinstance(payload.get("runtime"), dict):
        payload["runtime"] = {}
    payload["runtime"].setdefault("use_fallback_when_missing", True)
    payload["runtime"].setdefault("fallback_vault_root", ".ccbs/vault_zips")

    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        sources = []
    source_id_clean = str(source_id or DEFAULT_SOURCE_ID).strip() or DEFAULT_SOURCE_ID
    if not any(str(item.get("source_id", "")).strip() == source_id_clean for item in sources if isinstance(item, dict)):
        sources.append(
            {
                "source_id": source_id_clean,
                "name": DEFAULT_SOURCE_NAMES.get(source_id_clean, source_id_clean),
                "priority": "P0",
                "enabled": True,
                "path_globs": ["80_MISC/**/*.zip"],
            }
        )
    payload["sources"] = sources

    packages = payload.get("packages", [])
    if not isinstance(packages, list):
        packages = []
    package_id_clean = str(package_id or DEFAULT_PACKAGE_ID).strip() or DEFAULT_PACKAGE_ID
    zip_relpath_clean = _safe_repo_relpath(zip_relpath or DEFAULT_PACKAGE_RELPATH)

    updated = False
    for item in packages:
        if not isinstance(item, dict):
            continue
        if str(item.get("package_id", "")).strip() != package_id_clean:
            continue
        item["source_id"] = source_id_clean
        item["zip_relpath"] = zip_relpath_clean
        item["active"] = True
        item.setdefault("language", "en")
        item.setdefault("license", "open")
        updated = True
        break

    if not updated:
        packages.append(
            {
                "package_id": package_id_clean,
                "source_id": source_id_clean,
                "zip_relpath": zip_relpath_clean,
                "language": "en",
                "license": "open",
                "active": True,
            }
        )
    payload["packages"] = packages

    target.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    # Validate and return normalized view after update.
    catalog = load_catalog(target)
    runtime = resolve_runtime_vault_root(catalog)
    return {
        "catalog_path": str(target),
        "package_id": package_id_clean,
        "source_id": source_id_clean,
        "zip_relpath": zip_relpath_clean,
        "runtime": runtime,
        "package_count": len(catalog.get("packages", [])),
    }
