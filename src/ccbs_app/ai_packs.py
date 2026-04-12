"""Offline pack build/install/list/verify helpers for ai2 assets."""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .ai_storage import ai2_dir


def _packs_dir(root: Path) -> Path:
    out = ai2_dir(root) / "packs"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _registry_path(root: Path) -> Path:
    return _packs_dir(root) / "pack_registry.json"


def _load_registry(root: Path) -> dict[str, Any]:
    path = _registry_path(root)
    if not path.exists():
        payload = {"version": "ai-pack-registry-v1", "packs": []}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {"version": "ai-pack-registry-v1", "packs": []}
    if "packs" not in payload or not isinstance(payload["packs"], list):
        payload["packs"] = []
    return payload


def _save_registry(root: Path, payload: dict[str, Any]) -> None:
    path = _registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_pack(root: Path, output: Path, include_data: bool = False) -> dict[str, Any]:
    ai2 = ai2_dir(root)
    selected: list[tuple[Path, str]] = []

    for rel in [
        "storage_policy.json",
        "models/model_registry.json",
        "sources/source_manifest.json",
        "plugins/plugin_registry.json",
        "plugins/publisher_allowlist.json",
        "workspaces/workspace_registry.json",
    ]:
        p = ai2 / rel
        if p.exists() and p.is_file():
            selected.append((p, rel))

    if include_data:
        for rel_dir in ["sources/normalized", "index"]:
            base = ai2 / rel_dir
            if not base.exists():
                continue
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    selected.append((p, str(p.relative_to(ai2)).replace("\\", "/")))

    manifest_entries: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for src, arc in selected:
            manifest_entries.append({"path": arc, "sha256": _sha256(src), "bytes": int(src.stat().st_size)})

        manifest = {
            "format": "ccbs-ai2-pack-v1",
            "entry_count": len(manifest_entries),
            "entries": manifest_entries,
        }
        manifest_file = tmp_path / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src, arc in selected:
                zf.write(src, arc)
            zf.write(manifest_file, "manifest.json")

    return {
        "output": str(output),
        "entries": len(manifest_entries),
        "include_data": bool(include_data),
    }


def install_pack(root: Path, pack_path: Path) -> dict[str, Any]:
    if not pack_path.exists() or not pack_path.is_file():
        raise ValueError(f"pack not found: {pack_path}")

    with zipfile.ZipFile(pack_path, "r") as zf:
        if "manifest.json" not in zf.namelist():
            raise ValueError("pack manifest.json missing")
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        for item in manifest.get("entries", []):
            path = str(item.get("path", ""))
            expected = str(item.get("sha256", ""))
            payload = zf.read(path)
            digest = hashlib.sha256(payload).hexdigest()
            if digest != expected:
                raise ValueError(f"checksum mismatch: {path}")

        install_dir = _packs_dir(root) / "installed" / pack_path.stem
        if install_dir.exists():
            for p in sorted(install_dir.rglob("*"), reverse=True):
                if p.is_file():
                    p.unlink(missing_ok=True)
            for p in sorted(install_dir.rglob("*"), reverse=True):
                if p.is_dir():
                    p.rmdir()
        install_dir.mkdir(parents=True, exist_ok=True)
        zf.extractall(install_dir)

    reg = _load_registry(root)
    packs = list(reg.get("packs", []))
    rec = {
        "pack_name": pack_path.stem,
        "path": str(install_dir),
        "source_zip": str(pack_path),
        "entry_count": int(manifest.get("entry_count", 0)),
    }

    replaced = False
    for idx, item in enumerate(packs):
        if str(item.get("pack_name", "")) == rec["pack_name"]:
            packs[idx] = rec
            replaced = True
            break
    if not replaced:
        packs.append(rec)
    reg["packs"] = sorted(packs, key=lambda x: str(x.get("pack_name", "")))
    _save_registry(root, reg)
    return rec


def list_packs(root: Path) -> list[dict[str, Any]]:
    return list(_load_registry(root).get("packs", []))


def verify_pack(root: Path, pack_name: str) -> dict[str, Any]:
    name = pack_name.strip()
    reg = _load_registry(root)
    rec = None
    for item in reg.get("packs", []):
        if str(item.get("pack_name", "")) == name:
            rec = dict(item)
            break
    if rec is None:
        raise ValueError(f"pack not found: {name}")

    base = Path(str(rec["path"]))
    manifest_path = base / "manifest.json"
    if not manifest_path.exists():
        return {"ok": False, "pack_name": name, "reason": "manifest_missing"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest.get("entries", []):
        p = base / str(item.get("path", ""))
        if not p.exists() or not p.is_file():
            return {"ok": False, "pack_name": name, "reason": f"missing:{p}"}
        digest = _sha256(p)
        if digest != str(item.get("sha256", "")):
            return {"ok": False, "pack_name": name, "reason": f"checksum:{p}"}

    return {"ok": True, "pack_name": name, "entry_count": int(manifest.get("entry_count", 0))}
