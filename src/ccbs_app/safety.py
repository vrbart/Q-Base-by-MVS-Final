"""Permission advice and safety scanning helpers."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

IGNORE_DIRS = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".ccbs"}
EXECUTABLE_EXTENSIONS = {".exe", ".dll", ".msi", ".bat", ".cmd", ".ps1", ".sh"}
SENSITIVE_RE = re.compile(
    r"\b(password|passwd|secret|token|api[_-]?key|private[_-]?key|client[_-]?secret)\b",
    re.IGNORECASE,
)

PERMISSION_LEVELS: dict[str, dict[str, str]] = {
    "read_only": {
        "label": "Read-only",
        "capabilities": "Reads files, runs validation/analysis, no writes.",
        "risk": "Lowest risk; safest for first run.",
    },
    "workspace_write": {
        "label": "Workspace write",
        "capabilities": "Can modify files in the project/workspace.",
        "risk": "Medium risk; changes are local and reviewable.",
    },
    "full_access": {
        "label": "Full access",
        "capabilities": "Can access broader filesystem/network and run wider automation.",
        "risk": "Highest risk; use only after trust review.",
    },
}

TASK_REQUIREMENTS: dict[str, dict[str, str]] = {
    "general": {
        "level": "read_only",
        "reason": "General Q&A and diagnostics do not require writes.",
    },
    "ai_qa": {
        "level": "read_only",
        "reason": "Index/search/answer tasks only read content by default.",
    },
    "pt_preflight": {
        "level": "read_only",
        "reason": "Preflight is a read-only readiness check.",
    },
    "pt_apply_write": {
        "level": "workspace_write",
        "reason": "Applying link ports with --write edits bootstrap files.",
    },
    "pt_autopilot": {
        "level": "workspace_write",
        "reason": "Autopilot performs write operations and validation sequence.",
    },
    "admin_ops": {
        "level": "full_access",
        "reason": "Administrative git/system actions may need elevated trust.",
    },
}

_LEVEL_ORDER = {"read_only": 0, "workspace_write": 1, "full_access": 2}


@dataclass(frozen=True)
class SafetyFinding:
    path: str
    category: str
    detail: str


@dataclass(frozen=True)
class SafetyScanReport:
    target: str
    scanned_files: int
    skipped_files: int
    symlink_count: int
    executable_like_count: int
    binary_file_count: int
    sensitive_hit_count: int
    scanned_paths: list[str]
    findings: list[SafetyFinding]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "scanned_files": self.scanned_files,
            "skipped_files": self.skipped_files,
            "symlink_count": self.symlink_count,
            "executable_like_count": self.executable_like_count,
            "binary_file_count": self.binary_file_count,
            "sensitive_hit_count": self.sensitive_hit_count,
            "scanned_paths": self.scanned_paths,
            "findings": [item.__dict__ for item in self.findings],
        }


def recommend_permission(task: str) -> tuple[str, str]:
    cfg = TASK_REQUIREMENTS.get(task, TASK_REQUIREMENTS["general"])
    return cfg["level"], cfg["reason"]


def permission_sufficient(chosen_level: str, required_level: str) -> bool:
    return _LEVEL_ORDER.get(chosen_level, -1) >= _LEVEL_ORDER.get(required_level, 999)


def _iter_files(target: Path, max_files: int) -> tuple[list[Path], int]:
    if target.is_file():
        return [target], 0

    files: list[Path] = []
    skipped = 0
    for path in sorted(target.rglob("*")):
        if len(files) >= max_files:
            skipped += 1
            continue
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            skipped += 1
            continue
        files.append(path)
    return files, skipped


def scan_path(target: Path, max_files: int = 2000, max_findings: int = 80) -> SafetyScanReport:
    files, skipped = _iter_files(target, max_files=max(1, max_files))

    symlink_count = 0
    executable_like_count = 0
    binary_file_count = 0
    sensitive_hit_count = 0
    findings: list[SafetyFinding] = []
    scanned_paths: list[str] = []

    for path in files:
        scanned_paths.append(str(path))

        if path.is_symlink():
            symlink_count += 1
            if len(findings) < max_findings:
                findings.append(SafetyFinding(path=str(path), category="symlink", detail="symbolic link"))

        if path.suffix.lower() in EXECUTABLE_EXTENSIONS:
            executable_like_count += 1
            if len(findings) < max_findings:
                findings.append(SafetyFinding(path=str(path), category="executable_like", detail=path.suffix.lower()))

        try:
            blob = path.read_bytes()
        except Exception:  # noqa: BLE001
            skipped += 1
            continue

        if b"\x00" in blob[:8192]:
            binary_file_count += 1
            if len(findings) < max_findings:
                findings.append(SafetyFinding(path=str(path), category="binary", detail="null bytes detected"))
            continue

        text = blob.decode("utf-8", errors="ignore")
        for line_num, line in enumerate(text.splitlines(), 1):
            match = SENSITIVE_RE.search(line)
            if not match:
                continue
            sensitive_hit_count += 1
            if len(findings) < max_findings:
                findings.append(
                    SafetyFinding(
                        path=str(path),
                        category="sensitive_hint",
                        detail=f"line {line_num}: keyword '{match.group(1)}'",
                    )
                )

    return SafetyScanReport(
        target=str(target),
        scanned_files=len(files),
        skipped_files=skipped,
        symlink_count=symlink_count,
        executable_like_count=executable_like_count,
        binary_file_count=binary_file_count,
        sensitive_hit_count=sensitive_hit_count,
        scanned_paths=scanned_paths,
        findings=findings,
    )


def write_scan_manifest(
    root: Path,
    report: SafetyScanReport,
    task: str,
    chosen_level: str,
    required_level: str,
    include_hashes: bool = False,
    hash_limit: int = 200,
) -> Path:
    out_dir = root / ".ccbs" / "security"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "scan_manifest.json"

    payload: dict[str, Any] = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "task": task,
        "chosen_level": chosen_level,
        "required_level": required_level,
        "report": report.to_dict(),
    }
    if include_hashes:
        hashes: list[dict[str, str]] = []
        for raw_path in report.scanned_paths[: max(1, hash_limit)]:
            path = Path(raw_path)
            if not path.exists() or not path.is_file():
                continue
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except Exception:  # noqa: BLE001
                continue
            hashes.append({"path": str(path), "sha256": digest})
        payload["hashes"] = hashes

    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path
