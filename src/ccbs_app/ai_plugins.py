"""Plugin registry/install/verification with publisher allowlist policy."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .ai_storage import ai2_dir, ensure_capacity


REQUIRED_FIELDS = {"plugin_id", "version", "publisher", "capabilities", "files", "signature_sha256"}


def _plugins_dir(root: Path) -> Path:
    out = ai2_dir(root) / "plugins"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _allowlist_path(root: Path) -> Path:
    return _plugins_dir(root) / "publisher_allowlist.json"


def _registry_path(root: Path) -> Path:
    return _plugins_dir(root) / "plugin_registry.json"


def _load_allowlist(root: Path) -> dict[str, Any]:
    path = _allowlist_path(root)
    if not path.exists():
        payload = {"version": "plugin-allowlist-v1", "publishers": ["ccbs-internal"]}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {"version": "plugin-allowlist-v1", "publishers": ["ccbs-internal"]}
    if "publishers" not in payload or not isinstance(payload["publishers"], list):
        payload["publishers"] = ["ccbs-internal"]
    return payload


def _load_registry(root: Path) -> dict[str, Any]:
    path = _registry_path(root)
    if not path.exists():
        payload = {"version": "plugin-registry-v1", "plugins": []}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return payload
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = {"version": "plugin-registry-v1", "plugins": []}
    if "plugins" not in payload or not isinstance(payload["plugins"], list):
        payload["plugins"] = []
    return payload


def _save_registry(root: Path, payload: dict[str, Any]) -> None:
    path = _registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _canonical_signature_payload(manifest: dict[str, Any], file_hashes: dict[str, str]) -> str:
    core = {
        "plugin_id": str(manifest.get("plugin_id", "")),
        "version": str(manifest.get("version", "")),
        "publisher": str(manifest.get("publisher", "")),
        "capabilities": sorted(str(x) for x in manifest.get("capabilities", [])),
        "file_hashes": dict(sorted(file_hashes.items())),
    }
    return json.dumps(core, sort_keys=True, separators=(",", ":"))


def _verify_manifest_signature(manifest: dict[str, Any], file_hashes: dict[str, str]) -> tuple[bool, str]:
    payload = _canonical_signature_payload(manifest, file_hashes)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    provided = str(manifest.get("signature_sha256", "")).strip().lower()
    return digest == provided, digest


def list_plugins(root: Path) -> list[dict[str, Any]]:
    return list(_load_registry(root).get("plugins", []))


def install_plugin(root: Path, zip_path: Path) -> dict[str, Any]:
    if not zip_path.exists() or not zip_path.is_file():
        raise ValueError(f"plugin zip not found: {zip_path}")

    allowlist = {str(x).strip().lower() for x in _load_allowlist(root).get("publishers", [])}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        manifest_path = tmp_dir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("plugin manifest.json missing")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        missing = sorted(REQUIRED_FIELDS - set(manifest.keys()))
        if missing:
            raise ValueError(f"manifest missing fields: {', '.join(missing)}")

        publisher = str(manifest.get("publisher", "")).strip().lower()
        if publisher not in allowlist:
            raise ValueError(f"publisher not allowlisted: {publisher}")

        file_hashes: dict[str, str] = {}
        for rel in manifest.get("files", []):
            rel_s = str(rel).strip()
            if not rel_s:
                continue
            p = (tmp_dir / rel_s).resolve()
            if not p.exists() or not p.is_file() or tmp_dir not in p.parents:
                raise ValueError(f"manifest file missing or invalid path: {rel_s}")
            file_hashes[rel_s.replace("\\", "/")] = _sha256_file(p)

        ok, computed = _verify_manifest_signature(manifest, file_hashes)
        if not ok:
            raise ValueError(f"invalid plugin signature (computed={computed})")

        plugin_id = str(manifest["plugin_id"]).strip().lower()
        version = str(manifest["version"]).strip()
        if not plugin_id or not version:
            raise ValueError("plugin_id and version are required")

        install_dir = _plugins_dir(root) / "packages" / plugin_id / version
        if install_dir.exists():
            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)

        total_bytes = sum((tmp_dir / rel).stat().st_size for rel in manifest.get("files", []))
        ensure_capacity(root, incoming_bytes=int(total_bytes), stage=f"plugin-install:{plugin_id}")

        for rel in manifest.get("files", []):
            src = tmp_dir / str(rel)
            dst = install_dir / str(rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        shutil.copy2(manifest_path, install_dir / "manifest.json")

    reg = _load_registry(root)
    plugins = list(reg.get("plugins", []))
    rec = {
        "plugin_id": plugin_id,
        "version": version,
        "publisher": publisher,
        "capabilities": sorted(str(x) for x in manifest.get("capabilities", [])),
        "enabled": False,
        "install_path": str(install_dir),
        "signature_sha256": str(manifest.get("signature_sha256", "")),
    }

    replaced = False
    for idx, item in enumerate(plugins):
        if str(item.get("plugin_id", "")) == plugin_id:
            plugins[idx] = rec
            replaced = True
            break
    if not replaced:
        plugins.append(rec)

    reg["plugins"] = sorted(plugins, key=lambda x: str(x.get("plugin_id", "")))
    _save_registry(root, reg)
    return rec


def _toggle(root: Path, plugin_id: str, enabled: bool) -> dict[str, Any]:
    pid = plugin_id.strip().lower()
    reg = _load_registry(root)
    plugins = list(reg.get("plugins", []))
    found = False
    for item in plugins:
        if str(item.get("plugin_id", "")) == pid:
            item["enabled"] = bool(enabled)
            found = True
            break
    if not found:
        raise ValueError(f"plugin not found: {pid}")
    reg["plugins"] = plugins
    _save_registry(root, reg)
    return {"plugin_id": pid, "enabled": bool(enabled)}


def enable_plugin(root: Path, plugin_id: str) -> dict[str, Any]:
    return _toggle(root, plugin_id=plugin_id, enabled=True)


def disable_plugin(root: Path, plugin_id: str) -> dict[str, Any]:
    return _toggle(root, plugin_id=plugin_id, enabled=False)


def verify_plugin(root: Path, plugin_id: str) -> dict[str, Any]:
    pid = plugin_id.strip().lower()
    reg = _load_registry(root)
    rec = None
    for item in reg.get("plugins", []):
        if str(item.get("plugin_id", "")) == pid:
            rec = dict(item)
            break
    if rec is None:
        raise ValueError(f"plugin not found: {pid}")

    manifest_path = Path(str(rec.get("install_path", ""))) / "manifest.json"
    if not manifest_path.exists():
        return {"ok": False, "plugin_id": pid, "reason": "manifest_missing"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    file_hashes: dict[str, str] = {}
    for rel in manifest.get("files", []):
        p = Path(str(rec["install_path"])) / str(rel)
        if not p.exists() or not p.is_file():
            return {"ok": False, "plugin_id": pid, "reason": f"missing_file:{rel}"}
        file_hashes[str(rel)] = _sha256_file(p)

    ok, digest = _verify_manifest_signature(manifest, file_hashes)
    return {
        "ok": bool(ok),
        "plugin_id": pid,
        "computed_signature": digest,
        "expected_signature": str(manifest.get("signature_sha256", "")),
    }
