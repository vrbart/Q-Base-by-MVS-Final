"""Storage policy and quota enforcement for CCBS offline AI (ai2)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_STORAGE_BYTES = 214748364800  # 200 GiB hard ceiling
DEFAULT_POLICY = {
    "version": "ai-storage-policy-v1",
    "max_bytes": MAX_STORAGE_BYTES,
    "on_limit": "block_new_ingest",
}


class StorageLimitError(RuntimeError):
    """Raised when write operations would exceed the hard storage cap."""

    def __init__(self, stage: str, current_bytes: int, incoming_bytes: int, max_bytes: int) -> None:
        needed = current_bytes + incoming_bytes
        remaining = max(0, max_bytes - current_bytes)
        super().__init__(
            "storage_limit_reached: "
            f"stage={stage} current_bytes={current_bytes} incoming_bytes={incoming_bytes} "
            f"needed_bytes={needed} max_bytes={max_bytes} remaining_bytes={remaining}"
        )
        self.stage = stage
        self.current_bytes = int(current_bytes)
        self.incoming_bytes = int(incoming_bytes)
        self.max_bytes = int(max_bytes)


@dataclass(frozen=True)
class StorageUsage:
    total_bytes: int
    max_bytes: int
    remaining_bytes: int
    sections: dict[str, int]


def ai2_dir(root: Path) -> Path:
    out = root / ".ccbs" / "ai2"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _path_policy(root: Path) -> Path:
    return ai2_dir(root) / "storage_policy.json"


def _tracked_paths(root: Path) -> dict[str, Path]:
    base = ai2_dir(root)
    return {
        "sources_raw": base / "sources" / "raw",
        "sources_normalized": base / "sources" / "normalized",
        "index": base / "index",
        "models": base / "models",
        "plugins": base / "plugins",
        "workspaces": base / "workspaces",
        "packs": base / "packs",
        "auth": base / "auth",
        "audit": base / "audit",
    }


def _safe_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return int(path.stat().st_size)
        except OSError:
            return 0

    total = 0
    for root_dir, _, files in os.walk(path):
        for name in files:
            p = Path(root_dir) / name
            try:
                total += int(p.stat().st_size)
            except OSError:
                continue
    return total


def load_storage_policy(root: Path) -> dict[str, Any]:
    path = _path_policy(root)
    if not path.exists():
        save_storage_policy(root, dict(DEFAULT_POLICY))

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = dict(DEFAULT_POLICY)

    max_bytes = int(payload.get("max_bytes", MAX_STORAGE_BYTES))
    if max_bytes > MAX_STORAGE_BYTES:
        max_bytes = MAX_STORAGE_BYTES
    if max_bytes <= 0:
        max_bytes = MAX_STORAGE_BYTES

    out = {
        "version": str(payload.get("version", DEFAULT_POLICY["version"])),
        "max_bytes": max_bytes,
        "on_limit": "block_new_ingest",
    }

    if out != payload:
        save_storage_policy(root, out)
    return out


def save_storage_policy(root: Path, policy: dict[str, Any]) -> None:
    max_bytes = int(policy.get("max_bytes", MAX_STORAGE_BYTES))
    if max_bytes > MAX_STORAGE_BYTES:
        max_bytes = MAX_STORAGE_BYTES
    if max_bytes <= 0:
        max_bytes = MAX_STORAGE_BYTES

    sanitized = {
        "version": str(policy.get("version", DEFAULT_POLICY["version"])),
        "max_bytes": max_bytes,
        "on_limit": "block_new_ingest",
    }

    path = _path_policy(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")


def usage_report(root: Path) -> StorageUsage:
    policy = load_storage_policy(root)
    sections = {name: _safe_size(path) for name, path in _tracked_paths(root).items()}
    total = int(sum(sections.values()))
    max_bytes = int(policy["max_bytes"])
    remaining = max(0, max_bytes - total)
    return StorageUsage(total_bytes=total, max_bytes=max_bytes, remaining_bytes=remaining, sections=sections)


def ensure_capacity(root: Path, incoming_bytes: int = 0, stage: str = "write") -> StorageUsage:
    incoming = max(0, int(incoming_bytes))
    report = usage_report(root)
    if report.total_bytes + incoming > report.max_bytes:
        raise StorageLimitError(stage=stage, current_bytes=report.total_bytes, incoming_bytes=incoming, max_bytes=report.max_bytes)
    return report


def verify_storage(root: Path) -> dict[str, Any]:
    policy = load_storage_policy(root)
    report = usage_report(root)
    within_cap = report.total_bytes <= report.max_bytes and int(policy["max_bytes"]) <= MAX_STORAGE_BYTES
    return {
        "ok": bool(within_cap),
        "max_bytes": report.max_bytes,
        "hard_limit_bytes": MAX_STORAGE_BYTES,
        "total_bytes": report.total_bytes,
        "remaining_bytes": report.remaining_bytes,
        "sections": report.sections,
        "on_limit": policy["on_limit"],
    }


def gc_storage(root: Path, target_bytes: int, dry_run: bool = False) -> dict[str, Any]:
    target = max(0, int(target_bytes))
    report = usage_report(root)
    if target >= report.total_bytes:
        return {
            "deleted_files": 0,
            "freed_bytes": 0,
            "before_bytes": report.total_bytes,
            "after_bytes": report.total_bytes,
            "target_bytes": target,
            "dry_run": bool(dry_run),
        }

    # Prefer removing normalized content first, then raw mirrors, then index artifacts.
    order = ["sources_normalized", "sources_raw", "index", "packs", "plugins", "models"]
    tracked = _tracked_paths(root)
    candidates: list[tuple[float, int, Path]] = []

    for section in order:
        base = tracked[section]
        if not base.exists():
            continue
        for dir_root, _, files in os.walk(base):
            for name in files:
                p = Path(dir_root) / name
                try:
                    stat = p.stat()
                except OSError:
                    continue
                candidates.append((float(stat.st_mtime), int(stat.st_size), p))

    candidates.sort(key=lambda row: row[0])

    freed = 0
    deleted = 0
    current = report.total_bytes
    for _, size, path in candidates:
        if current - freed <= target:
            break
        freed += size
        deleted += 1
        if not dry_run:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # If deletion failed, discount it from reclaimed bytes.
                freed -= size
                deleted -= 1

    after = usage_report(root).total_bytes if not dry_run else max(0, current - freed)
    return {
        "deleted_files": deleted,
        "freed_bytes": max(0, current - after),
        "before_bytes": current,
        "after_bytes": after,
        "target_bytes": target,
        "dry_run": bool(dry_run),
    }
