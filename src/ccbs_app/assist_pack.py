"""Offline pack builder for accessibility assistant assets."""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from .assist_store import export_profile, list_profiles
from .assist_types import AssistPackResult

DOC_FILES = [
    "docs/ACCESSIBLE_GAMING_ASSISTANT_SPEC.md",
    "docs/OFFLINE_AI_FEATURES_BACKLOG.md",
    "docs/ACCESSIBLE_GAMING_PHASE1_ROADMAP.md",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _collect_repo_files(root: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for rel in DOC_FILES:
        path = root / rel
        if path.exists() and path.is_file():
            files.append((path, rel))

    schema = root / "tools" / "brick_schema.json"
    if schema.exists() and schema.is_file():
        files.append((schema, "tools/brick_schema.json"))

    bricks_dir = root / "bricks"
    if bricks_dir.exists():
        for brick in sorted(bricks_dir.glob("BR-ACC-GAME-*")):
            if not brick.is_dir():
                continue
            for rel in [
                "metadata.yaml",
                "config/README.txt",
                "proof-pack/README.txt",
                "rollback/README.txt",
            ]:
                path = brick / rel
                if path.exists() and path.is_file():
                    arcname = str(path.relative_to(root)).replace("\\", "/")
                    files.append((path, arcname))

    files.sort(key=lambda item: item[1])
    return files


def build_assist_pack(root: Path, output: Path, include_local_profiles: bool = False) -> AssistPackResult:
    files = _collect_repo_files(root)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        profile_entries: list[tuple[Path, str]] = []

        if include_local_profiles:
            export_root = tmp / "profiles"
            export_root.mkdir(parents=True, exist_ok=True)
            for profile in list_profiles(root):
                export_path = export_root / f"{profile.profile_id}.json"
                export_profile(root=root, profile_id=profile.profile_id, out_path=export_path)
                arcname = f"profiles/{profile.profile_id}.json"
                profile_entries.append((export_path, arcname))

        all_entries = files + sorted(profile_entries, key=lambda item: item[1])

        manifest_entries = []
        for source, arcname in all_entries:
            manifest_entries.append(
                {
                    "path": arcname,
                    "sha256": _sha256(source),
                    "bytes": int(source.stat().st_size),
                }
            )

        manifest_payload = {
            "format": "ccbs-assist-pack-v1",
            "entry_count": len(manifest_entries),
            "entries": manifest_entries,
        }
        manifest_path = tmp / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for source, arcname in all_entries:
                zf.write(source, arcname)
            zf.write(manifest_path, "manifest.json")

    return AssistPackResult(
        output=str(output),
        file_count=len(all_entries) + 1,
        manifest_entries=len(manifest_entries),
    )
