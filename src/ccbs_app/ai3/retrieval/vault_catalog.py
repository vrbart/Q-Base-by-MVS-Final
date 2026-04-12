"""Catalog-driven offline ZIP vault configuration and orchestration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .zip_ingest import index_zip_archive
from .zip_manifest import sync_zip_manifest


DEFAULT_TEXT_EXTENSIONS = [
    ".txt",
    ".md",
    ".rst",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".py",
    ".ps1",
    ".sh",
    ".html",
    ".htm",
]


DEFAULT_SOURCES: list[dict[str, Any]] = [
    {"source_id": "FMS", "name": "Mathematics & Formal Sciences", "priority": "P0", "enabled": True, "path_globs": ["10_FORMAL/**/*.zip"]},
    {"source_id": "NAT", "name": "Natural Sciences", "priority": "P0", "enabled": True, "path_globs": ["20_NATURAL/**/*.zip"]},
    {"source_id": "SOC", "name": "Social Sciences & Civics", "priority": "P0", "enabled": True, "path_globs": ["30_SOCIAL/**/*.zip"]},
    {"source_id": "HUM", "name": "Humanities & Arts", "priority": "P0", "enabled": True, "path_globs": ["40_HUMANITIES/**/*.zip"]},
    {"source_id": "APT", "name": "Applied Sciences & Technology", "priority": "P0", "enabled": True, "path_globs": ["50_APPLIED/**/*.zip"]},
    {"source_id": "MED", "name": "Health & Medicine", "priority": "P0", "enabled": True, "path_globs": ["60_HEALTH/**/*.zip"]},
    {"source_id": "LIF", "name": "Practical & Life Skills", "priority": "P0", "enabled": True, "path_globs": ["70_LIFESKILLS/**/*.zip"]},
    {"source_id": "MIS", "name": "Miscellaneous & Interdisciplinary", "priority": "P0", "enabled": True, "path_globs": ["80_MISC/**/*.zip"]},
]


def _looks_windows_drive(raw: str) -> bool:
    return len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha()


def _catalog_project_base(catalog_path: Path) -> Path:
    target = catalog_path.expanduser().resolve()
    if target.parent.name.lower() == "config" and target.parent.parent.exists():
        return target.parent.parent
    return target.parent


def _normalize_path(raw: str, *, base_dir: Path) -> Path:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("path is required")
    text = text.replace("\\", "/")
    if _looks_windows_drive(text):
        if os.name == "nt":
            return Path(text).expanduser().resolve()
        drive = text[0].lower()
        suffix = text[2:].lstrip("/")
        return (Path("/mnt") / drive / suffix).resolve()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _is_safe_relpath(raw: str) -> bool:
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return False
    if text.startswith("/") or text.startswith("\\") or _looks_windows_drive(text):
        return False
    parts = [part for part in Path(text).parts if part not in {"", "."}]
    if not parts:
        return False
    return ".." not in parts


def _is_within(path: Path, root: Path) -> bool:
    target = path.resolve()
    base = root.resolve()
    try:
        target.relative_to(base)
        return True
    except Exception:
        return False


def _normalize_sources(raw_sources: Any) -> list[dict[str, Any]]:
    values = raw_sources if isinstance(raw_sources, list) and raw_sources else list(DEFAULT_SOURCES)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in values:
        if not isinstance(row, dict):
            raise ValueError("catalog sources entries must be objects")
        source_id = str(row.get("source_id", "")).strip()
        if not source_id:
            raise ValueError("catalog source requires source_id")
        if source_id in seen:
            raise ValueError(f"duplicate source_id: {source_id}")
        seen.add(source_id)
        name = str(row.get("name", "")).strip()
        if not name:
            raise ValueError(f"source {source_id} requires name")
        priority = str(row.get("priority", "P0")).strip() or "P0"
        enabled = bool(row.get("enabled", True))
        globs = row.get("path_globs", [])
        if not isinstance(globs, list):
            raise ValueError(f"source {source_id} path_globs must be an array")
        out.append(
            {
                "source_id": source_id,
                "name": name,
                "priority": priority,
                "enabled": enabled,
                "path_globs": [str(item).strip() for item in globs if str(item).strip()],
            }
        )
    return out


def _normalize_packages(raw_packages: Any, source_ids: set[str]) -> list[dict[str, Any]]:
    if raw_packages is None:
        return []
    if not isinstance(raw_packages, list):
        raise ValueError("catalog packages must be an array")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw_packages:
        if not isinstance(row, dict):
            raise ValueError("catalog package entries must be objects")
        package_id = str(row.get("package_id", "")).strip()
        if not package_id:
            raise ValueError("catalog package requires package_id")
        if package_id in seen:
            raise ValueError(f"duplicate package_id: {package_id}")
        seen.add(package_id)
        source_id = str(row.get("source_id", "")).strip()
        if source_id not in source_ids:
            raise ValueError(f"package {package_id} references unknown source_id: {source_id}")
        zip_relpath = str(row.get("zip_relpath", "")).strip()
        if not _is_safe_relpath(zip_relpath):
            raise ValueError(f"package {package_id} has unsafe zip_relpath")
        out.append(
            {
                "package_id": package_id,
                "source_id": source_id,
                "zip_relpath": zip_relpath.replace("\\", "/"),
                "language": str(row.get("language", "")).strip(),
                "license": str(row.get("license", "")).strip(),
                "active": bool(row.get("active", True)),
                "metadata": {k: v for k, v in row.items() if k not in {"package_id", "source_id", "zip_relpath", "language", "license", "active"}},
            }
        )
    return out


def _normalize_ingest_defaults(raw: Any) -> dict[str, Any]:
    defaults = raw if isinstance(raw, dict) else {}
    text_extensions = defaults.get("text_extensions", DEFAULT_TEXT_EXTENSIONS)
    if not isinstance(text_extensions, list):
        raise ValueError("ingest_defaults.text_extensions must be an array")
    exts = []
    for item in text_extensions:
        ext = str(item).strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = f".{ext}"
        exts.append(ext)
    if not exts:
        exts = list(DEFAULT_TEXT_EXTENSIONS)
    return {
        "max_entries_per_zip": max(1, int(defaults.get("max_entries_per_zip", 50000))),
        "max_entry_bytes": max(1024, int(defaults.get("max_entry_bytes", 32 * 1024 * 1024))),
        "max_total_extract_bytes_per_run": max(1024, int(defaults.get("max_total_extract_bytes_per_run", 2 * 1024 * 1024 * 1024))),
        "text_extensions": exts,
    }


def _normalize_embedding(raw: Any) -> dict[str, Any]:
    values = raw if isinstance(raw, dict) else {}
    provider = str(values.get("provider", "auto")).strip().lower() or "auto"
    fallback = str(values.get("fallback_provider", "hash96")).strip().lower() or "hash96"
    return {
        "provider": provider,
        "ollama_base_url": str(values.get("ollama_base_url", "http://127.0.0.1:11434")).strip() or "http://127.0.0.1:11434",
        "ollama_model": str(values.get("ollama_model", "nomic-embed-text")).strip() or "nomic-embed-text",
        "fallback_provider": fallback,
    }


def _normalize_runtime(raw: Any, *, base_dir: Path) -> dict[str, Any]:
    values = raw if isinstance(raw, dict) else {}
    use_fallback = bool(values.get("use_fallback_when_missing", True))
    fallback_root = _normalize_path(str(values.get("fallback_vault_root", ".ccbs/vault_zips")), base_dir=base_dir)
    return {
        "use_fallback_when_missing": use_fallback,
        "fallback_vault_root": fallback_root,
    }


def load_catalog(catalog_path: Path) -> dict[str, Any]:
    target = catalog_path.expanduser().resolve()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("vault catalog JSON must be an object")

    version = int(payload.get("version", 0))
    if version != 1:
        raise ValueError(f"unsupported vault catalog version: {version}")

    project_base = _catalog_project_base(target)
    vault_root = _normalize_path(str(payload.get("vault_root", "")), base_dir=project_base)
    allowlist_raw = payload.get("allowlist_roots", [])
    if not isinstance(allowlist_raw, list) or not allowlist_raw:
        raise ValueError("allowlist_roots must be a non-empty array")
    allowlist_roots = [_normalize_path(str(item), base_dir=project_base) for item in allowlist_raw]
    runtime = _normalize_runtime(payload.get("runtime"), base_dir=project_base)
    fallback_root = Path(str(runtime["fallback_vault_root"])).expanduser().resolve()
    if bool(runtime.get("use_fallback_when_missing", True)) and not any(_is_within(fallback_root, root) for root in allowlist_roots):
        allowlist_roots.append(fallback_root)
    if not any(_is_within(vault_root, root) for root in allowlist_roots):
        raise ValueError("vault_root is outside allowlist_roots")

    sources = _normalize_sources(payload.get("sources"))
    source_ids = {str(row["source_id"]) for row in sources}
    packages = _normalize_packages(payload.get("packages", []), source_ids=source_ids)
    ingest_defaults = _normalize_ingest_defaults(payload.get("ingest_defaults"))
    embedding = _normalize_embedding(payload.get("embedding"))

    return {
        "version": 1,
        "catalog_path": target,
        "vault_root": vault_root,
        "allowlist_roots": allowlist_roots,
        "sources": sources,
        "packages": packages,
        "ingest_defaults": ingest_defaults,
        "embedding": embedding,
        "runtime": runtime,
    }


def catalog_summary(catalog: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": int(catalog.get("version", 0)),
        "catalog_path": str(catalog.get("catalog_path", "")),
        "vault_root": str(catalog.get("vault_root", "")),
        "allowlist_roots": [str(item) for item in catalog.get("allowlist_roots", [])],
        "source_count": len(catalog.get("sources", [])),
        "package_count": len(catalog.get("packages", [])),
        "active_package_count": sum(1 for row in catalog.get("packages", []) if bool(row.get("active", True))),
        "embedding": dict(catalog.get("embedding", {})),
        "ingest_defaults": dict(catalog.get("ingest_defaults", {})),
        "runtime": {
            "use_fallback_when_missing": bool(dict(catalog.get("runtime", {})).get("use_fallback_when_missing", True)),
            "fallback_vault_root": str(dict(catalog.get("runtime", {})).get("fallback_vault_root", "")),
        },
    }


def selected_packages(
    catalog: dict[str, Any],
    source_id: str = "",
    package_id: str = "",
    active_only: bool = True,
) -> list[dict[str, Any]]:
    sid = str(source_id or "").strip()
    pid = str(package_id or "").strip()
    rows = list(catalog.get("packages", []))
    out: list[dict[str, Any]] = []
    for row in rows:
        if sid and str(row.get("source_id", "")) != sid:
            continue
        if pid and str(row.get("package_id", "")) != pid:
            continue
        if active_only and not bool(row.get("active", True)):
            continue
        out.append(dict(row))
    out.sort(key=lambda item: (str(item.get("source_id", "")), str(item.get("package_id", ""))))
    return out


def is_path_allowed(path: Path, allowlist_roots: list[Path]) -> bool:
    target = path.expanduser().resolve()
    return any(_is_within(target, root) for root in allowlist_roots)


def resolve_runtime_vault_root(catalog: dict[str, Any]) -> dict[str, Any]:
    configured_root = Path(str(catalog.get("vault_root", ""))).expanduser().resolve()
    runtime = dict(catalog.get("runtime", {}))
    fallback_root = Path(str(runtime.get("fallback_vault_root", ".ccbs/vault_zips"))).expanduser().resolve()
    use_fallback = bool(runtime.get("use_fallback_when_missing", True))
    configured_exists = configured_root.exists() and configured_root.is_dir()
    resolved_root = configured_root
    fallback_used = False
    reason = "configured_exists"
    if not configured_exists and use_fallback:
        resolved_root = fallback_root
        fallback_used = True
        reason = "configured_missing_fallback"
    elif not configured_exists and not use_fallback:
        reason = "configured_missing_no_fallback"

    allowlist = [Path(str(item)).expanduser().resolve() for item in catalog.get("allowlist_roots", [])]
    if allowlist and not is_path_allowed(resolved_root, allowlist):
        raise ValueError(f"runtime vault root outside allowlist_roots: {resolved_root}")

    return {
        "configured_vault_root": str(configured_root),
        "resolved_vault_root": str(resolved_root),
        "fallback_vault_root": str(fallback_root),
        "configured_exists": configured_exists,
        "fallback_used": fallback_used,
        "use_fallback_when_missing": use_fallback,
        "reason": reason,
    }


def resolve_package_zip_path(catalog: dict[str, Any], package: dict[str, Any], vault_root: Path | None = None) -> Path:
    rel = str(package.get("zip_relpath", "")).strip().replace("\\", "/")
    if not _is_safe_relpath(rel):
        raise ValueError("unsafe zip_relpath")
    base = vault_root or Path(str(catalog["vault_root"]))
    target = (base / rel).resolve()
    if not is_path_allowed(target, [Path(str(root)) for root in catalog.get("allowlist_roots", [])]):
        raise ValueError("package zip path is outside allowlist roots")
    return target


def _upsert_sources(conn, catalog: dict[str, Any]) -> None:
    for row in catalog.get("sources", []):
        source_id = str(row.get("source_id", "")).strip()
        if not source_id:
            continue
        metadata = {"path_globs": list(row.get("path_globs", []))}
        conn.execute(
            """
            INSERT INTO vault_source(source_id, name, priority, enabled, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(source_id) DO UPDATE SET
              name = excluded.name,
              priority = excluded.priority,
              enabled = excluded.enabled,
              metadata_json = excluded.metadata_json,
              updated_at = excluded.updated_at
            """,
            (
                source_id,
                str(row.get("name", "")),
                str(row.get("priority", "P0")),
                1 if bool(row.get("enabled", True)) else 0,
                json.dumps(metadata, sort_keys=True),
            ),
        )


def _upsert_packages(conn, catalog: dict[str, Any]) -> None:
    for row in catalog.get("packages", []):
        package_id = str(row.get("package_id", "")).strip()
        if not package_id:
            continue
        metadata = dict(row.get("metadata", {}))
        conn.execute(
            """
            INSERT INTO vault_package(package_id, source_id, zip_relpath, active, language, license, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(package_id) DO UPDATE SET
              source_id = excluded.source_id,
              zip_relpath = excluded.zip_relpath,
              active = excluded.active,
              language = excluded.language,
              license = excluded.license,
              metadata_json = excluded.metadata_json,
              updated_at = excluded.updated_at
            """,
            (
                package_id,
                str(row.get("source_id", "")),
                str(row.get("zip_relpath", "")),
                1 if bool(row.get("active", True)) else 0,
                str(row.get("language", "")),
                str(row.get("license", "")),
                json.dumps(metadata, sort_keys=True),
            ),
        )


def sync_catalog(
    conn,
    catalog_path: Path,
    source_id: str = "",
    package_id: str = "",
    full_hash: bool = False,
) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    runtime = resolve_runtime_vault_root(catalog)
    runtime_root = Path(str(runtime["resolved_vault_root"])).expanduser().resolve()
    _upsert_sources(conn, catalog)
    _upsert_packages(conn, catalog)
    conn.commit()

    items = selected_packages(catalog, source_id=source_id, package_id=package_id, active_only=True)
    synced: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in items:
        package_id_value = str(item.get("package_id", ""))
        source_id_value = str(item.get("source_id", ""))
        try:
            zip_path = resolve_package_zip_path(catalog, item, vault_root=runtime_root)
            if not zip_path.exists():
                errors.append(
                    {
                        "package_id": package_id_value,
                        "source_id": source_id_value,
                        "status": "missing_zip",
                        "zip_path": str(zip_path),
                    }
                )
                continue
            if not zip_path.is_file():
                errors.append(
                    {
                        "package_id": package_id_value,
                        "source_id": source_id_value,
                        "status": "not_a_file",
                        "zip_path": str(zip_path),
                    }
                )
                continue

            out = sync_zip_manifest(
                conn,
                zip_path=zip_path,
                source_id=source_id_value,
                package_id=package_id_value,
                vault_root=str(runtime_root),
                active=bool(item.get("active", True)),
                full_hash=bool(full_hash),
            )
            synced.append(out)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "package_id": package_id_value,
                    "source_id": source_id_value,
                    "status": "sync_error",
                    "error": str(exc),
                }
            )

    if not items:
        skipped.append({"status": "no_matching_active_packages"})

    return {
        "catalog": catalog_summary(catalog),
        "runtime": runtime,
        "filters": {"source_id": str(source_id or ""), "package_id": str(package_id or "")},
        "selected_packages": len(items),
        "synced": synced,
        "errors": errors,
        "skipped": skipped,
    }


def index_catalog(
    conn,
    catalog_path: Path,
    source_id: str = "",
    package_id: str = "",
    full: bool = False,
    full_hash: bool = False,
) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    defaults = dict(catalog.get("ingest_defaults", {}))
    sync_out = sync_catalog(
        conn,
        catalog_path=catalog_path,
        source_id=source_id,
        package_id=package_id,
        full_hash=full_hash,
    )

    indexed: list[dict[str, Any]] = []
    errors = list(sync_out.get("errors", []))
    for item in sync_out.get("synced", []):
        try:
            zip_id = str(item.get("zip_id", "")).strip()
            zip_path = Path(str(item.get("path", ""))).expanduser().resolve()
            if not zip_id:
                raise ValueError("sync result missing zip_id")
            out = index_zip_archive(
                conn,
                zip_id=zip_id,
                zip_path=zip_path,
                max_entries=max(1, int(defaults.get("max_entries_per_zip", 50000))),
                only_pending=not bool(full),
                max_entry_bytes=max(1024, int(defaults.get("max_entry_bytes", 32 * 1024 * 1024))),
                max_total_extract_bytes=max(1024, int(defaults.get("max_total_extract_bytes_per_run", 2 * 1024 * 1024 * 1024))),
                text_extensions=set(str(x).strip().lower() for x in defaults.get("text_extensions", DEFAULT_TEXT_EXTENSIONS)),
                embedding_config=dict(catalog.get("embedding", {})),
            )
            indexed.append(out)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "zip_id": str(item.get("zip_id", "")),
                    "path": str(item.get("path", "")),
                    "status": "index_error",
                    "error": str(exc),
                }
            )

    return {
        "catalog": catalog_summary(catalog),
        "runtime": dict(sync_out.get("runtime", {})),
        "filters": {"source_id": str(source_id or ""), "package_id": str(package_id or "")},
        "sync": sync_out,
        "indexed": indexed,
        "errors": errors,
        "full_reindex": bool(full),
    }


def catalog_doctor(
    catalog: dict[str, Any],
    source_id: str = "",
    package_id: str = "",
) -> dict[str, Any]:
    runtime = resolve_runtime_vault_root(catalog)
    runtime_root = Path(str(runtime.get("resolved_vault_root", ""))).expanduser().resolve()
    selected = selected_packages(
        catalog,
        source_id=str(source_id or ""),
        package_id=str(package_id or ""),
        active_only=True,
    )
    package_checks: list[dict[str, Any]] = []
    for item in selected:
        package_id_value = str(item.get("package_id", ""))
        source_id_value = str(item.get("source_id", ""))
        zip_path = resolve_package_zip_path(catalog, item, vault_root=runtime_root)
        package_checks.append(
            {
                "package_id": package_id_value,
                "source_id": source_id_value,
                "zip_relpath": str(item.get("zip_relpath", "")),
                "zip_path": str(zip_path),
                "exists": zip_path.exists(),
                "is_file": zip_path.is_file(),
            }
        )
    missing = [item for item in package_checks if not bool(item.get("exists"))]
    not_files = [item for item in package_checks if bool(item.get("exists")) and not bool(item.get("is_file"))]
    return {
        "catalog": catalog_summary(catalog),
        "runtime": runtime,
        "filters": {"source_id": str(source_id or ""), "package_id": str(package_id or "")},
        "active_selected": len(selected),
        "package_checks": package_checks,
        "missing_packages": missing,
        "not_file_packages": not_files,
        "ok": len(missing) == 0 and len(not_files) == 0,
    }
