"""Hyper-V provisioning helpers for CCBS CLI.

This module provides a runnable MVP for:
- host preflight/status checks
- Microsoft server image catalog/list/download
- VM create/configure preview and optional execution
- one-time bootstrap planning
- sensitive wizard handoff (host key -> user key guarded script)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .repo import RepoError, repo_root


OFFICIAL_DOWNLOAD_DOMAINS = {
    "microsoft.com",
    "download.microsoft.com",
    "software-download.microsoft.com",
    "go.microsoft.com",
    "ubuntu.com",
    "releases.ubuntu.com",
    "cdimage.ubuntu.com",
    "old-releases.ubuntu.com",
    "cloud-images.ubuntu.com",
    "redhat.com",
    "access.redhat.com",
    "developers.redhat.com",
    "cdn.redhat.com",
    "debian.org",
    "cdimage.debian.org",
    "kali.download",
}

MICROSOFT_DOWNLOAD_DOMAINS = {
    "microsoft.com",
    "download.microsoft.com",
    "software-download.microsoft.com",
    "go.microsoft.com",
}

HYPERV_STORAGE_GUIDE_REL = Path("docs") / "FILE_CREATION_AND_STORAGE_BEST_PRACTICES.md"


OS_WIZARD_PRESETS: dict[str, dict[str, Any]] = {
    "windows-2025": {
        "label": "Windows Server 2025 Evaluation",
        "os_image_id": "ws2025-eval-iso",
        "allow_domains": [],
        "notes": "Catalog-driven Microsoft evaluation image flow.",
    },
    "windows-2022": {
        "label": "Windows Server 2022 Evaluation",
        "os_image_id": "ws2022-eval-iso",
        "allow_domains": [],
        "notes": "Catalog-driven Microsoft evaluation image flow.",
    },
    "windows-2019": {
        "label": "Windows Server 2019 Evaluation",
        "os_image_id": "ws2019-eval-iso",
        "allow_domains": [],
        "notes": "Catalog-driven Microsoft evaluation image flow.",
    },
    "ubuntu-2404": {
        "label": "Ubuntu Server 24.04 LTS",
        "os_url": "https://releases.ubuntu.com/24.04/ubuntu-24.04-live-server-amd64.iso",
        "allow_domains": ["ubuntu.com", "releases.ubuntu.com"],
        "notes": "Direct ISO URL can change by point release; use cache-seed fallback if needed.",
    },
    "debian-12": {
        "label": "Debian 12 Netinst",
        "os_url": "https://cdimage.debian.org/cdimage/archive/12.13.0/amd64/iso-cd/debian-12.13.0-amd64-netinst.iso",
        "allow_domains": ["debian.org", "cdimage.debian.org"],
        "notes": "Uses Debian 12 archive netinst path (12.13.0); use cache-seed if this mirror path changes.",
    },
    "rhel-9": {
        "label": "Red Hat Enterprise Linux 9",
        "os_url": "https://access.redhat.com/downloads/content/479",
        "allow_domains": ["redhat.com", "access.redhat.com", "cdn.redhat.com"],
        "notes": "Portal authentication/entitlement required; cache-seed is recommended.",
    },
    "kali": {
        "label": "Kali Linux Installer",
        "os_url": "https://cdimage.kali.org/current/kali-linux-installer-amd64.iso",
        "allow_domains": ["kali.org", "cdimage.kali.org"],
        "notes": "Official Kali hosts only; local ISO cache-seed remains supported for boot-ready Hyper-V flow.",
    },
}


def _natural_sort_key(value: str) -> list[Any]:
    parts = re.split(r"(\d+)", value)
    key: list[Any] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return key


def _resolve_kali_current_installer_url() -> tuple[str, str]:
    index_url = "https://cdimage.kali.org/current/"
    try:
        req = Request(index_url, headers={"User-Agent": "ccbs-hyperv/1.0"})
        with urlopen(req, timeout=20) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        return "", f"failed to query {index_url}: {exc}"

    matches = re.findall(
        r"""href=['"](kali-linux-[0-9][^'"]*-installer-amd64\.iso)['"]""",
        html,
        flags=re.IGNORECASE,
    )
    if not matches:
        return "", "no versioned Kali installer ISO links found in current index"

    latest = sorted(set(matches), key=_natural_sort_key, reverse=True)[0]
    return f"{index_url}{latest}", ""


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def _print_storage_best_practices_hint(root: Path) -> None:
    guide = root / HYPERV_STORAGE_GUIDE_REL
    print(f"Storage guide: {guide}")


def _powershell_available() -> tuple[bool, str]:
    if sys.platform.startswith("win"):
        pwsh = shutil.which("powershell")
        if pwsh:
            return True, pwsh
        return False, "powershell not found in PATH"

    cmd = shutil.which("cmd.exe")
    if cmd:
        return True, cmd

    fallback = Path("/mnt/c/Windows/System32/cmd.exe")
    if fallback.exists():
        return True, str(fallback)
    return False, "cmd.exe not found (this command needs Windows host access)"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _to_windows_path(path: Path) -> str:
    if sys.platform.startswith("win"):
        return str(path)

    wslpath = shutil.which("wslpath")
    if wslpath:
        proc = subprocess.run([wslpath, "-w", str(path)], text=True, capture_output=True, check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()

    raw = str(path)
    if raw.startswith("/mnt/") and len(raw) > 6 and raw[5].isalpha() and raw[6] == "/":
        drive = raw[5].upper()
        rest = raw[7:].replace("/", "\\")
        return f"{drive}:\\{rest}"
    return raw


def _run_powershell_command(command: str) -> subprocess.CompletedProcess[str]:
    available, locator = _powershell_available()
    if not available:
        return subprocess.CompletedProcess(args=[], returncode=127, stdout="", stderr=locator)

    if sys.platform.startswith("win"):
        cmd = [locator, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
        return subprocess.run(cmd, text=True, capture_output=True, check=False)

    cmd = [locator, "/c", "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _run_powershell_file(script_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    available, locator = _powershell_available()
    if not available:
        return subprocess.CompletedProcess(args=[], returncode=127, stdout="", stderr=locator)

    if sys.platform.startswith("win"):
        cmd = [locator, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path), *args]
        return subprocess.run(cmd, text=True, capture_output=True, check=False)

    win_script = _to_windows_path(script_path)
    cmd = [locator, "/c", "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", win_script, *args]
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _resolve_path(root: Path, raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    return (root / candidate).resolve()


def _catalog_path(root: Path) -> Path:
    return root / "config" / "msft_server_catalog.json"


def _load_catalog(root: Path) -> list[dict[str, Any]]:
    path = _catalog_path(root)
    if not path.exists():
        raise FileNotFoundError(f"catalog missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    images = payload.get("images", [])
    if not isinstance(images, list):
        raise ValueError("catalog format invalid: images must be a list")
    return images


def _find_image(images: list[dict[str, Any]], image_id: str) -> dict[str, Any] | None:
    for item in images:
        if str(item.get("id", "")).strip().lower() == image_id.strip().lower():
            return item
    return None


def _normalize_domain(value: str) -> str:
    cleaned = value.strip().lower().strip(".")
    if cleaned.startswith("*."):
        cleaned = cleaned[2:]
    return cleaned


def _build_allowed_domains(extra_domains: list[str]) -> set[str]:
    merged = set(OFFICIAL_DOWNLOAD_DOMAINS)
    for item in extra_domains:
        domain = _normalize_domain(item)
        if domain:
            merged.add(domain)
    return merged


def _host_allowed(host: str, allowed_domains: set[str]) -> bool:
    target = _normalize_domain(host)
    if not target:
        return False
    for domain in allowed_domains:
        if target == domain or target.endswith(f".{domain}"):
            return True
    return False


def _is_microsoft_url(url: str) -> bool:
    parsed = urlparse(url)
    host = _normalize_domain(parsed.hostname or "")
    if not host:
        return False
    return _host_allowed(host, MICROSOFT_DOWNLOAD_DOMAINS)


def _validate_download_url(url: str, allowed_domains: set[str]) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return False, "download URL must use HTTPS"
    host = _normalize_domain(parsed.hostname or "")
    if not host:
        return False, "download URL has no hostname"
    if not _host_allowed(host, allowed_domains):
        return False, f"download host '{host}' is not in authorized domain allowlist"
    return True, ""


def _safe_file_token(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value.strip())
    return cleaned or "item"


def _write_download_manifest(root: Path, payload: dict[str, Any]) -> Path:
    out_dir = root / ".ccbs" / "hyperv" / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    token = _safe_file_token(str(payload.get("image_id", "image")))
    out_path = out_dir / f"{stamp}_{token}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def _file_sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def _resolve_cache_paths(
    root: Path,
    image_id: str,
    url: str,
    cache_dirs: list[str],
) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path.resolve())
        if key in seen:
            return
        seen.add(key)
        candidates.append(path)

    default_dir = root / ".ccbs" / "hyperv" / "images"
    if image_id:
        add(default_dir / f"{image_id}.iso")
    basename = Path(urlparse(url).path).name
    if basename:
        add(default_dir / basename)

    resolved_dirs: list[Path] = [default_dir]
    for raw in cache_dirs:
        if not raw.strip():
            continue
        resolved_dirs.append(_resolve_path(root, raw))

    for cache_dir in resolved_dirs:
        if image_id:
            add(cache_dir / f"{image_id}.iso")
        if basename:
            add(cache_dir / basename)

    return candidates


def _resolve_cached_image(
    root: Path,
    image_id: str,
    url: str,
    expected_sha256: str,
    cache_dirs: list[str],
) -> tuple[bool, Path | None, str, str]:
    candidates = _resolve_cache_paths(root, image_id, url, cache_dirs)
    expected = expected_sha256.strip().lower()
    mismatches = 0

    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        digest = _file_sha256(path)
        if expected and digest.lower() != expected:
            mismatches += 1
            continue
        return True, path, digest, "sha256-verified" if expected else "exists-unverified"

    if expected and mismatches:
        return False, None, "", f"cache candidates found but sha256 mismatched ({mismatches})"
    return False, None, "", "no cache hit"


def _git_commit_manifest(root: Path, manifest_path: Path) -> tuple[bool, str]:
    rel = manifest_path.relative_to(root)
    add = subprocess.run(
        ["git", "-C", str(root), "add", "--", str(rel)],
        text=True,
        capture_output=True,
        check=False,
    )
    if add.returncode != 0:
        return False, add.stderr.strip() or "git add failed"

    diff = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--name-only", "--", str(rel)],
        text=True,
        capture_output=True,
        check=False,
    )
    if diff.returncode != 0:
        return False, diff.stderr.strip() or "git diff failed"
    if not diff.stdout.strip():
        return True, "manifest already committed"

    msg = f"Add Hyper-V media manifest {manifest_path.name}"
    commit = subprocess.run(
        ["git", "-C", str(root), "commit", "-m", msg, "--", str(rel)],
        text=True,
        capture_output=True,
        check=False,
    )
    if commit.returncode != 0:
        return False, commit.stderr.strip() or commit.stdout.strip() or "git commit failed"
    return True, commit.stdout.strip() or "manifest committed"


def _unique_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        v = value.strip()
        if not v:
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _print_os_preset_list(as_json: bool = False) -> None:
    payload = [
        {
            "id": key,
            "label": item.get("label", key),
            "os_image_id": item.get("os_image_id", ""),
            "os_url": item.get("os_url", ""),
            "notes": item.get("notes", ""),
        }
        for key, item in OS_WIZARD_PRESETS.items()
    ]
    if as_json:
        _print_json({"os_profiles": payload})
        return
    print("OS wizard presets:")
    for item in payload:
        print(f"- {item['id']}: {item['label']}")
        if item["os_image_id"]:
            print(f"  image_id: {item['os_image_id']}")
        if item["os_url"]:
            print(f"  url: {item['os_url']}")
        if item["notes"]:
            print(f"  notes: {item['notes']}")


def _collect_hyperv_status() -> tuple[int, dict[str, Any]]:
    try:
        root = repo_root()
        images = _load_catalog(root)
    except (RepoError, OSError, ValueError) as exc:
        return 2, {"ok": False, "error": str(exc), "catalog_images": 0}

    ps = r"""
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$featureState = 'Unknown'
try {
  $feature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -ErrorAction Stop
  $featureState = $feature.State
} catch {}
$vmCmd = [bool](Get-Command Get-VM -ErrorAction SilentlyContinue)
$svc = Get-Service vmms -ErrorAction SilentlyContinue
$out = [ordered]@{
  host_os = [Environment]::OSVersion.VersionString
  is_admin = $isAdmin
  hyperv_feature_state = $featureState
  hyperv_cmdlets = $vmCmd
  vmms_service = if ($svc) { $svc.Status.ToString() } else { 'NotFound' }
}
$out | ConvertTo-Json -Compress
"""
    proc = _run_powershell_command(ps)
    if proc.returncode != 0:
        return 1, {
            "ok": False,
            "error": proc.stderr.strip() or proc.stdout.strip() or "powershell call failed",
            "catalog_images": len(images),
        }

    status: dict[str, Any]
    try:
        parsed = json.loads(proc.stdout.strip())
        if isinstance(parsed, dict):
            status = parsed
        else:
            status = {"raw": proc.stdout.strip()}
    except json.JSONDecodeError:
        status = {"raw": proc.stdout.strip()}
    status["catalog_images"] = len(images)
    status["ok"] = True
    return 0, status


def cmd_hyperv_status(args: argparse.Namespace) -> int:
    rc, status = _collect_hyperv_status()
    if rc != 0:
        if args.json:
            _print_json(status)
        else:
            if rc == 2:
                print(f"ERROR: {status.get('error')}")
            else:
                print("Hyper-V status unavailable from current shell context.")
                print(status.get("error"))
                print(f"Catalog images configured: {status.get('catalog_images', 0)}")
                print("Tip: run from Windows host terminal if using WSL/Linux.")
        return rc

    if args.json:
        _print_json(status)
    else:
        print("Hyper-V status:")
        for key in ("host_os", "is_admin", "hyperv_feature_state", "hyperv_cmdlets", "vmms_service"):
            print(f"- {key}: {status.get(key)}")
        print(f"- catalog_images: {status['catalog_images']}")
    return 0


def cmd_hyperv_preflight(args: argparse.Namespace) -> int:
    rc, status = _collect_hyperv_status()
    if rc != 0:
        payload = {
            "ok": False,
            "strict": bool(args.strict),
            "error": status.get("error"),
            "status": status,
            "checks": [],
        }
        if args.json:
            _print_json(payload)
        else:
            print("Hyper-V preflight could not complete.")
            print(status.get("error"))
            print("Tip: run from Windows host terminal if using WSL/Linux.")
        return rc if args.strict else 0

    feature_state = str(status.get("hyperv_feature_state", "")).strip().lower()
    vmms_state = str(status.get("vmms_service", "")).strip().lower()
    catalog_count = int(status.get("catalog_images", 0) or 0)

    checks: list[dict[str, Any]] = [
        {"id": "is_admin", "label": "Session is elevated (Administrator)", "ok": bool(status.get("is_admin"))},
        {"id": "feature_enabled", "label": "Hyper-V optional feature is enabled", "ok": feature_state == "enabled"},
        {"id": "cmdlets", "label": "Hyper-V cmdlets are available", "ok": bool(status.get("hyperv_cmdlets"))},
        {"id": "vmms", "label": "VMMS service is running", "ok": vmms_state == "running"},
        {"id": "catalog", "label": "VM image catalog is available", "ok": catalog_count > 0},
    ]
    ok = all(bool(item.get("ok")) for item in checks)
    payload = {"ok": ok, "strict": bool(args.strict), "checks": checks, "status": status}

    if args.json:
        _print_json(payload)
    else:
        print("Hyper-V preflight checks:")
        for item in checks:
            state = "PASS" if item["ok"] else "FAIL"
            print(f"- [{state}] {item['label']}")
        print(f"Preflight result: {'PASS' if ok else 'ISSUES FOUND'}")
        if not ok:
            print("Tip: fix failed checks before running VM create/execute.")

    if args.strict and not ok:
        return 1
    return 0


def cmd_hyperv_image_list(args: argparse.Namespace) -> int:
    try:
        images = _load_catalog(repo_root())
    except (RepoError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        _print_json({"images": images})
        return 0

    print(f"Microsoft server images: {len(images)}")
    for item in images:
        print(f"- {item.get('id')}: {item.get('name')} ({item.get('channel')})")
    return 0


def cmd_hyperv_image_show(args: argparse.Namespace) -> int:
    try:
        images = _load_catalog(repo_root())
    except (RepoError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    entry = _find_image(images, args.image_id)
    if not entry:
        print(f"ERROR: image id not found: {args.image_id}")
        return 2
    if args.json:
        _print_json({"image": entry})
        return 0
    print(json.dumps(entry, indent=2))
    return 0


def _download_file(url: str, dest: Path, allowed_domains: set[str]) -> tuple[int, str, str, str, str]:
    ok, reason = _validate_download_url(url, allowed_domains)
    if not ok:
        return 1, "", "", "", reason

    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "CCBS-PRO/1.0"})
    sha = hashlib.sha256()
    total = 0
    try:
        with urlopen(req, timeout=60) as resp, dest.open("wb") as fh:
            final_url = str(getattr(resp, "geturl", lambda: url)())
            ok, reason = _validate_download_url(final_url, allowed_domains)
            if not ok:
                raise ValueError(f"redirect target rejected: {reason}")

            content_type = str(resp.headers.get("Content-Type", "")).lower()
            if content_type.startswith("text/html"):
                raise ValueError(
                    "response is HTML, not an ISO/binary payload; this source likely requires browser auth/terms."
                )

            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                sha.update(chunk)
                total += len(chunk)
    except Exception as exc:  # noqa: BLE001
        if dest.exists():
            dest.unlink(missing_ok=True)
        return 1, "", "", "", str(exc)
    return 0, sha.hexdigest(), str(total), final_url, content_type


def cmd_hyperv_image_download(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
        images = _load_catalog(root)
    except (RepoError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    _print_storage_best_practices_hint(root)

    entry: dict[str, Any] = {}
    if args.url:
        entry = {
            "id": args.image_id.strip() or "custom-url",
            "name": "Custom URL image",
            "url": args.url.strip(),
            "sha256": args.sha256.strip(),
            "channel": "custom",
        }
    else:
        if not args.image_id.strip():
            print("ERROR: provide image_id or --url")
            return 2
        found = _find_image(images, args.image_id)
        if not found:
            print(f"ERROR: image id not found: {args.image_id}")
            return 2
        entry = found

    url = str(entry.get("url", "")).strip()
    if not url:
        print("ERROR: resolved entry has no download URL")
        return 2

    extra_domains: list[str] = []
    if isinstance(entry.get("allowed_domains"), list):
        extra_domains.extend(str(item) for item in entry["allowed_domains"])
    extra_domains.extend(args.allow_domain)
    allowed_domains = _build_allowed_domains(extra_domains)
    url_ok, url_reason = _validate_download_url(url, allowed_domains)

    default_name = f"{entry.get('id', 'image')}.iso"
    if args.url:
        parsed_name = Path(urlparse(url).path).name
        if parsed_name:
            default_name = parsed_name
    default_dest = root / ".ccbs" / "hyperv" / "images" / default_name
    dest = _resolve_path(root, args.dest) if args.dest else default_dest
    expected_sha = str(args.sha256 or entry.get("sha256", "")).strip().lower()
    if args.require_sha256 and not expected_sha:
        print("ERROR: --require-sha256 set but no expected hash provided.")
        return 2

    cache_hit = False
    cache_path: Path | None = None
    cache_digest = ""
    cache_reason = "not checked"
    if args.cache_mode in {"cache-first", "cache-only"}:
        cache_hit, cache_path, cache_digest, cache_reason = _resolve_cached_image(
            root=root,
            image_id=str(entry.get("id", "")).strip(),
            url=url,
            expected_sha256=expected_sha,
            cache_dirs=args.cache_dir,
        )

    preview = {
        "image_id": entry.get("id", ""),
        "name": entry.get("name"),
        "channel": entry.get("channel", ""),
        "url": url,
        "dest": str(dest),
        "expected_sha256": expected_sha,
        "cache_mode": args.cache_mode,
        "cache_hit": cache_hit,
        "cache_path": str(cache_path) if cache_path else "",
        "cache_reason": cache_reason,
        "allowed_domains": sorted(allowed_domains),
        "url_allowed": url_ok,
        "url_validation": url_reason or "ok",
        "confirm_required": True,
    }
    if args.json:
        _print_json(preview)
    else:
        print("Image download plan:")
        for k, v in preview.items():
            print(f"- {k}: {v}")

    if args.cache_mode == "cache-only" and not cache_hit:
        print("ERROR: cache-only mode requested and no valid cached image found.")
        return 1

    if not url_ok and not cache_hit:
        print(f"ERROR: URL rejected by policy: {url_reason}")
        return 1

    if not args.confirm:
        print("Preview only. Re-run with --confirm to download.")
        return 0

    final_url = ""
    content_type = ""
    source = "download"
    digest = ""
    byte_count = 0

    if cache_hit and cache_path is not None:
        source = "cache"
        digest = cache_digest
        byte_count = cache_path.stat().st_size
        if cache_path.resolve() != dest.resolve():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache_path, dest)
        print(f"Using cached image: {cache_path}")
        print(f"Prepared image path: {dest}")
        print(f"sha256: {digest}")
        print(f"bytes: {byte_count}")
    else:
        rc, digest, detail, final_url, content_type = _download_file(url, dest, allowed_domains)
        if rc != 0:
            print(f"ERROR: download blocked/failed: {content_type}")
            return 1

        expected = expected_sha
        if expected and digest.lower() != expected:
            print(f"ERROR: sha256 mismatch. expected={expected} got={digest}")
            dest.unlink(missing_ok=True)
            return 1
        byte_count = int(detail)
        print(f"Downloaded: {dest}")
        print(f"final_url: {final_url}")
        print(f"content_type: {content_type}")
        print(f"sha256: {digest}")
        print(f"bytes: {detail}")
    manifest_payload = {
        "downloaded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "image_id": entry.get("id", ""),
        "name": entry.get("name", ""),
        "channel": entry.get("channel", ""),
        "source": source,
        "requested_url": url,
        "final_url": final_url,
        "cache_path": str(cache_path) if cache_path else "",
        "dest": str(dest),
        "sha256": digest,
        "expected_sha256": expected_sha,
        "bytes": byte_count,
        "content_type": content_type,
        "cache_mode": args.cache_mode,
        "cache_reason": cache_reason,
        "allowed_domains": sorted(allowed_domains),
        "policy": "official-domain-allowlist-v1",
    }
    try:
        manifest_path = _write_download_manifest(root, manifest_payload)
        print(f"manifest: {manifest_path}")
        if args.commit_manifest:
            ok, detail = _git_commit_manifest(root, manifest_path)
            if ok:
                print(f"manifest_commit: {detail}")
            else:
                print(f"WARNING: manifest commit failed: {detail}")
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: failed to write download manifest: {exc}")
    return 0


def cmd_hyperv_image_cache_seed(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    _print_storage_best_practices_hint(root)

    source = _resolve_path(root, args.source)
    if not source.exists() or not source.is_file():
        print(f"ERROR: source ISO not found: {source}")
        return 2

    image_id = args.image_id.strip() or _safe_file_token(source.stem)
    display_name = args.name.strip() or source.name
    suffix = source.suffix if source.suffix else ".iso"
    default_dest = root / ".ccbs" / "hyperv" / "images" / f"{image_id}{suffix}"
    dest = _resolve_path(root, args.dest) if args.dest else default_dest

    source_digest = _file_sha256(source)
    expected = args.sha256.strip().lower()
    if expected and source_digest.lower() != expected:
        print(f"ERROR: source sha256 mismatch. expected={expected} got={source_digest}")
        return 1

    preview = {
        "source": str(source),
        "dest": str(dest),
        "image_id": image_id,
        "name": display_name,
        "channel": args.channel,
        "sha256": source_digest,
        "expected_sha256": expected,
        "confirm_required": True,
    }
    if args.json:
        _print_json(preview)
    else:
        print("Cache seed plan:")
        for k, v in preview.items():
            print(f"- {k}: {v}")

    if not args.confirm:
        print("Preview only. Re-run with --confirm to seed cache.")
        return 0

    copied = False
    if source.resolve() != dest.resolve():
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source, dest)
            copied = True
        except PermissionError as exc:
            if not dest.exists():
                print(f"ERROR: destination ISO copy failed: {exc}")
                return 1
            print(f"WARNING: destination ISO is in use; reusing existing cache file: {dest}")

    try:
        digest = _file_sha256(dest)
    except PermissionError as exc:
        print(f"ERROR: cached ISO is locked and unreadable: {dest}")
        print(f"DETAIL: {exc}")
        print("Close any VM or process holding the ISO, then retry.")
        return 1

    if source.resolve() != dest.resolve() and not copied and digest.lower() != source_digest.lower():
        print("ERROR: existing cached ISO differs from provided source while destination is locked.")
        print(f"source_sha256: {source_digest}")
        print(f"cached_sha256: {digest}")
        return 1
    if expected and digest.lower() != expected:
        print(f"ERROR: destination sha256 mismatch. expected={expected} got={digest}")
        dest.unlink(missing_ok=True)
        return 1

    size_bytes = dest.stat().st_size
    print(f"Cache seeded: {dest}")
    print(f"sha256: {digest}")
    print(f"bytes: {size_bytes}")

    manifest_payload = {
        "downloaded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "image_id": image_id,
        "name": display_name,
        "channel": args.channel,
        "source": "cache-seed",
        "requested_url": args.url.strip(),
        "final_url": args.url.strip(),
        "cache_path": str(dest),
        "dest": str(dest),
        "sha256": digest,
        "expected_sha256": expected,
        "bytes": int(size_bytes),
        "content_type": "application/octet-stream",
        "cache_mode": "cache-seed",
        "cache_reason": "manual-seed",
        "allowed_domains": sorted(_build_allowed_domains(args.allow_domain)),
        "policy": "official-domain-allowlist-v1",
    }
    try:
        manifest_path = _write_download_manifest(root, manifest_payload)
        print(f"manifest: {manifest_path}")
        if args.commit_manifest:
            ok, detail = _git_commit_manifest(root, manifest_path)
            if ok:
                print(f"manifest_commit: {detail}")
            else:
                print(f"WARNING: manifest commit failed: {detail}")
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: failed to write cache-seed manifest: {exc}")
    return 0


def cmd_hyperv_vm_create(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    default_vhd = root / ".ccbs" / "hyperv" / "vms" / args.name / f"{args.name}.vhdx"
    vhd_path = _resolve_path(root, args.vhdx_path) if args.vhdx_path else default_vhd
    iso_path = _resolve_path(root, args.iso_path) if args.iso_path else None

    plan = {
        "name": args.name,
        "generation": 2,
        "memory_mb": args.memory_mb,
        "cpu": args.cpu,
        "vhdx_gb": args.vhdx_gb,
        "vhdx_path": str(vhd_path),
        "switch": args.switch,
        "iso_path": str(iso_path) if iso_path else "",
        "execute": bool(args.execute),
    }
    if args.json:
        _print_json({"vm_create": plan})
    else:
        print("VM create plan:")
        for k, v in plan.items():
            print(f"- {k}: {v}")

    if not args.execute:
        print("Preview only. Re-run with --execute to create the VM.")
        return 0

    name = _ps_quote(args.name)
    switch_name = _ps_quote(args.switch)
    vhd_win = _ps_quote(_to_windows_path(vhd_path))
    iso_attach = ""
    if iso_path:
        iso_win = _ps_quote(_to_windows_path(iso_path))
        iso_attach = f"""
if (Test-Path {iso_win}) {{
  Add-VMDvdDrive -VMName {name} -Path {iso_win}
}}
"""

    ps = f"""
$ErrorActionPreference = 'Stop'
if (-not (Get-Command New-VM -ErrorAction SilentlyContinue)) {{ throw 'Hyper-V cmdlets unavailable' }}
if (Get-VM -Name {name} -ErrorAction SilentlyContinue) {{
  Write-Host 'VM already exists. Skipping create.'
  exit 0
}}
New-Item -ItemType Directory -Force -Path (Split-Path {vhd_win}) | Out-Null
New-VM -Name {name} -Generation 2 -MemoryStartupBytes {int(args.memory_mb)}MB -SwitchName {switch_name} -NewVHDPath {vhd_win} -NewVHDSizeBytes {int(args.vhdx_gb)}GB | Out-Null
Set-VMProcessor -VMName {name} -Count {int(args.cpu)}
Set-VM -Name {name} -AutomaticCheckpointsEnabled $false
{iso_attach}
Write-Host 'VM create complete.'
"""
    proc = _run_powershell_command(ps)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip())
    return 0 if proc.returncode == 0 else 1


def _resolve_wizard_vm_args(args: argparse.Namespace, iso_path: str = "") -> argparse.Namespace:
    return argparse.Namespace(
        name=args.vm_name,
        switch=args.switch,
        memory_mb=args.memory_mb,
        cpu=args.cpu,
        vhdx_gb=args.vhdx_gb,
        vhdx_path=args.vhdx_path,
        iso_path=iso_path,
        execute=bool(args.execute),
        json=False,
    )


def _default_wizard_vm_name(args: argparse.Namespace) -> str:
    return "KaliVM" if str(args.os_profile).strip() == "kali" else "CCBS-VM"


def _resolve_downloaded_iso_path(
    root: Path,
    *,
    image_id: str,
    url: str,
    dest: str,
    cache_mode: str,
    cache_dirs: list[str],
    expected_sha256: str,
) -> Path | None:
    explicit_dest = str(dest).strip()
    if explicit_dest:
        resolved_dest = _resolve_path(root, explicit_dest)
        if resolved_dest.exists():
            return resolved_dest

    cache_ok, cache_path, _digest, _reason = _resolve_cached_image(
        root,
        image_id=str(image_id).strip(),
        url=str(url).strip(),
        cache_dirs=cache_dirs,
        expected_sha256=expected_sha256.strip().lower(),
    )
    if cache_ok and cache_path:
        return cache_path

    if cache_mode == "download-only":
        media_root = root / ".ccbs" / "hyperv" / "images"
        if str(image_id).strip():
            candidate = media_root / f"{image_id.strip()}.iso"
            if candidate.exists():
                return candidate
        if str(url).strip():
            candidate = media_root / Path(urlparse(str(url).strip()).path).name
            if candidate.name and candidate.exists():
                return candidate
    return None


def cmd_hyperv_vm_configure(args: argparse.Namespace) -> int:
    plan = {
        "name": args.name,
        "memory_mb": args.memory_mb,
        "cpu": args.cpu,
        "switch": args.switch or "",
        "execute": bool(args.execute),
    }
    if args.json:
        _print_json({"vm_configure": plan})
    else:
        print("VM configure plan:")
        for k, v in plan.items():
            print(f"- {k}: {v}")

    if not args.execute:
        print("Preview only. Re-run with --execute to configure the VM.")
        return 0

    name = _ps_quote(args.name)
    cmd_parts = [
        "$ErrorActionPreference = 'Stop'",
        f"if (-not (Get-VM -Name {name} -ErrorAction SilentlyContinue)) {{ throw 'VM not found' }}",
    ]
    if args.memory_mb:
        cmd_parts.append(f"Set-VMMemory -VMName {name} -StartupBytes {int(args.memory_mb)}MB")
    if args.cpu:
        cmd_parts.append(f"Set-VMProcessor -VMName {name} -Count {int(args.cpu)}")
    if args.switch:
        cmd_parts.append(f"Connect-VMNetworkAdapter -VMName {name} -SwitchName {_ps_quote(args.switch)}")
    cmd_parts.append("Write-Host 'VM configure complete.'")
    proc = _run_powershell_command("\n".join(cmd_parts))
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip())
    return 0 if proc.returncode == 0 else 1


def cmd_hyperv_bootstrap_plan(args: argparse.Namespace) -> int:
    profiles = {
        "standalone": {
            "required_secret_types": ["admin_password"],
            "optional_secret_types": ["product_key", "api_token", "recovery_phrase"],
            "notes": "Standalone server bootstrap.",
        },
        "adds_new_forest": {
            "required_secret_types": ["admin_password", "dsrm_password"],
            "optional_secret_types": ["product_key", "api_token"],
            "notes": "AD DS domain controller bootstrap (new forest).",
        },
        "join_domain": {
            "required_secret_types": ["admin_password"],
            "optional_secret_types": ["domain_join_credential", "product_key"],
            "notes": "Member server join-domain bootstrap.",
        },
        "adlds": {
            "required_secret_types": ["admin_password"],
            "optional_secret_types": ["recovery_phrase", "api_token"],
            "notes": "AD LDS (ADAM) bootstrap profile.",
        },
    }
    profile = profiles[args.profile]
    payload = {
        "vm_name": args.vm_name,
        "profile": args.profile,
        "required_secret_types": profile["required_secret_types"],
        "optional_secret_types": profile["optional_secret_types"],
        "notes": profile["notes"],
        "next_steps": [
            "Run: ccbs hyperv wizard --profile <profile> --execute",
            "Collect handle metadata only (no plaintext secret logging).",
            "Apply bootstrap scripts over PowerShell Direct on first boot.",
        ],
    }
    if args.json:
        _print_json(payload)
    else:
        print("Bootstrap plan:")
        for k, v in payload.items():
            if isinstance(v, list):
                print(f"- {k}:")
                for item in v:
                    print(f"  - {item}")
            else:
                print(f"- {k}: {v}")
    return 0


def cmd_hyperv_wizard(args: argparse.Namespace) -> int:
    try:
        root = repo_root()
    except RepoError as exc:
        print(f"ERROR: {exc}")
        return 2

    # Some unit tests call this handler with a minimal argparse.Namespace.
    # Normalize optional flags/fields so preview mode stays robust.
    if not hasattr(args, "list_os_profiles"):
        args.list_os_profiles = False
    if not hasattr(args, "os_profile"):
        args.os_profile = "custom"
    if not hasattr(args, "download_os"):
        args.download_os = False
    if not hasattr(args, "os_image_id"):
        args.os_image_id = ""
    if not hasattr(args, "os_url"):
        args.os_url = ""
    if not hasattr(args, "allow_domain"):
        args.allow_domain = []
    if not hasattr(args, "os_sha256"):
        args.os_sha256 = ""
    if not hasattr(args, "os_dest"):
        args.os_dest = ""
    if not hasattr(args, "os_cache_mode"):
        args.os_cache_mode = "cache-first"
    if not hasattr(args, "os_cache_dir"):
        args.os_cache_dir = []
    if not hasattr(args, "os_require_sha256"):
        args.os_require_sha256 = False
    if not hasattr(args, "commit_manifest"):
        args.commit_manifest = False
    if not hasattr(args, "os_local_iso"):
        args.os_local_iso = ""
    if not hasattr(args, "os_prompt_local_media"):
        args.os_prompt_local_media = True
    if not hasattr(args, "vm_name"):
        args.vm_name = ""
    if not hasattr(args, "switch"):
        args.switch = "Default Switch"
    if not hasattr(args, "memory_mb"):
        args.memory_mb = 4096
    if not hasattr(args, "cpu"):
        args.cpu = 2
    if not hasattr(args, "vhdx_gb"):
        args.vhdx_gb = 80
    if not hasattr(args, "vhdx_path"):
        args.vhdx_path = ""

    if not str(args.vm_name).strip():
        args.vm_name = _default_wizard_vm_name(args)

    if args.list_os_profiles:
        _print_os_preset_list()
        return 0

    if args.os_profile != "custom":
        preset = OS_WIZARD_PRESETS.get(args.os_profile, {})
        if preset:
            if not args.download_os:
                args.download_os = True
                print(f"Enabled --download-os due to --os-profile {args.os_profile}")
            if not args.os_image_id.strip() and not args.os_url.strip():
                args.os_image_id = str(preset.get("os_image_id", "")).strip()
                args.os_url = str(preset.get("os_url", "")).strip()

            merged_domains = list(args.allow_domain)
            merged_domains.extend(str(x) for x in preset.get("allow_domains", []))
            args.allow_domain = _unique_keep_order(merged_domains)
            notes = str(preset.get("notes", "")).strip()
            if notes:
                print(f"OS profile note: {notes}")

    microsoft_os_flow = False
    if args.download_os:
        profile_is_windows = str(args.os_profile).startswith("windows-")
        image_is_windows = str(args.os_image_id).strip().lower().startswith("ws")
        url_is_windows = bool(args.os_url.strip()) and _is_microsoft_url(str(args.os_url).strip())
        microsoft_os_flow = profile_is_windows or image_is_windows or url_is_windows

        if microsoft_os_flow:
            if args.allow_domain:
                print("Ignoring --allow-domain for Microsoft OS flow (trusted policy: official Microsoft domains only).")
                args.allow_domain = []
            if args.os_url.strip() and not _is_microsoft_url(args.os_url.strip()):
                print("ERROR: --os-url for Microsoft OS flow must be an official Microsoft domain.")
                print(f"Provided url: {args.os_url.strip()}")
                return 2

    resolved_iso_path: Path | None = None
    if args.download_os:
        _print_storage_best_practices_hint(root)
        if not args.os_image_id.strip() and not args.os_url.strip():
            args.os_image_id = "ws2022-eval-iso"
            print("No OS source provided; defaulting --os-image-id ws2022-eval-iso")

        local_iso = str(args.os_local_iso or "").strip()
        
        # DEV MODE: Check if running in auto-confirm environment
        dev_auto_confirm = os.environ.get("CCBS_HYPERV_AUTO_CONFIRM", "").lower() in ("1", "true", "yes")
        
        if (
            not local_iso
            and microsoft_os_flow
            and bool(args.execute)
            and bool(args.os_prompt_local_media)
            and sys.stdin.isatty()
        ):
            print("Trusted source policy: Microsoft official domains only.")
            print("If you already downloaded/ported an official Microsoft ISO, you can use it now.")
            
            # DEV MODE: Auto-skip ISO prompt in dev/auto-confirm mode
            if dev_auto_confirm:
                print("[DEV MODE] Auto-confirming: Using direct download (not local ISO)")
                choice = "n"
            else:
                try:
                    choice = input("Use local/portable ISO instead of direct download? [y/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    choice = "n"
            
            if choice in {"y", "yes"}:
                if dev_auto_confirm:
                    print("[DEV MODE] Local ISO requested but not provided in dev mode; skipping local ISO input")
                    entered = ""
                else:
                    try:
                        entered = input("Enter local ISO path: ").strip()
                    except (EOFError, KeyboardInterrupt):
                        entered = ""
                if entered:
                    local_iso = entered
                else:
                    print("No local ISO path entered; continuing with official download flow.")

        if local_iso and args.execute:
            seed_image_id = args.os_image_id.strip() or "ws-local-portable-iso"
            source_hint = args.os_url.strip()
            if not source_hint:
                try:
                    images = _load_catalog(root)
                    entry = _find_image(images, seed_image_id)
                    if entry:
                        source_hint = str(entry.get("url", "")).strip()
                except (OSError, ValueError):
                    source_hint = ""

            print("Seeding local/portable ISO into Hyper-V cache before wizard download step.")
            seed_args = argparse.Namespace(
                source=local_iso,
                image_id=seed_image_id,
                name=f"Local seeded ISO ({seed_image_id})",
                channel="manual-cache-seed",
                url=source_hint,
                sha256=args.os_sha256,
                dest="",
                allow_domain=[],
                commit_manifest=bool(args.commit_manifest and args.execute),
                confirm=True,
                json=False,
            )
            rc = cmd_hyperv_image_cache_seed(seed_args)
            if rc != 0:
                return rc
            args.os_cache_mode = "cache-only"

        if local_iso and not args.execute:
            print(f"Local ISO provided (preview): {local_iso}")
            print("On --execute, this ISO will be cache-seeded first, then resolved with --os-cache-mode cache-only.")

        print("OS image step (before VM create):")
        download_args = argparse.Namespace(
            image_id=args.os_image_id,
            url=args.os_url,
            sha256=args.os_sha256,
            dest=args.os_dest,
            confirm=bool(args.execute),
            json=False,
            allow_domain=args.allow_domain,
            cache_mode=args.os_cache_mode,
            cache_dir=args.os_cache_dir,
            require_sha256=bool(args.os_require_sha256),
            commit_manifest=bool(args.commit_manifest and args.execute),
        )
        rc = cmd_hyperv_image_download(download_args)
        if rc != 0:
            return rc
        resolved_iso_path = _resolve_downloaded_iso_path(
            root,
            image_id=args.os_image_id,
            url=args.os_url,
            dest=args.os_dest,
            cache_mode=args.os_cache_mode,
            cache_dirs=args.os_cache_dir,
            expected_sha256=args.os_sha256,
        )
    elif str(args.os_local_iso).strip():
        resolved_iso_path = _resolve_path(root, str(args.os_local_iso).strip())

    if resolved_iso_path:
        print(f"Resolved ISO path for VM create: {resolved_iso_path}")
    elif args.download_os or str(args.os_local_iso).strip():
        print("WARNING: Unable to resolve a local ISO path after OS media step; VM create will continue without attached ISO.")

    print("VM create step:")
    vm_args = _resolve_wizard_vm_args(args, str(resolved_iso_path) if resolved_iso_path else "")
    rc = cmd_hyperv_vm_create(vm_args)
    if rc != 0:
        return rc

    script = root / "scripts" / "sensitive_data_wizard.ps1"
    skip_sensitive_env = os.environ.get("CCBS_SKIP_SENSITIVE_WIZARD", "").lower() in {"1", "true", "yes"}
    if skip_sensitive_env:
        print("Sensitive wizard launch disabled (CCBS_SKIP_SENSITIVE_WIZARD=1).")
        if not args.execute:
            print("Preview only. Re-run with --execute to create the VM.")
        return 0

    should_offer_sensitive = str(args.os_profile).startswith("windows-") or args.profile != "custom"
    if not script.exists():
        if should_offer_sensitive:
            print(f"WARNING: sensitive wizard script missing: {script}")
        if not args.execute:
            print("Preview only. Re-run with --execute to create the VM.")
        return 0

    cmd_preview = (
        f"powershell -NoProfile -ExecutionPolicy Bypass -File \"{script}\" "
        f"-Action WizardRun -Profile {args.profile}"
    )
    print(f"Sensitive wizard command: {cmd_preview}")
    if not args.execute:
        print("Preview only. Re-run with --execute to create the VM.")
        return 0

    if not should_offer_sensitive:
        print("Skipping sensitive wizard launch for this flow.")
        return 0

    proc = _run_powershell_file(script, ["-Action", "WizardRun", "-Profile", args.profile])
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip())
    return 0 if proc.returncode == 0 else 1


def add_hyperv_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    hyperv = sub.add_parser("hyperv", help="Hyper-V provisioning helpers")
    hyperv_sub = hyperv.add_subparsers(dest="hyperv_cmd", required=True)

    status = hyperv_sub.add_parser("status", help="Show Hyper-V host status and catalog availability")
    status.add_argument("--json", action="store_true", help="Emit JSON output")
    status.set_defaults(func=cmd_hyperv_status)

    preflight = hyperv_sub.add_parser("preflight", help="Run host preflight checks")
    preflight.add_argument("--strict", action="store_true", help="Return non-zero if checks fail")
    preflight.add_argument("--json", action="store_true", help="Emit JSON output")
    preflight.set_defaults(func=cmd_hyperv_preflight)

    image = hyperv_sub.add_parser("image", help="Microsoft server image catalog")
    image_sub = image.add_subparsers(dest="image_cmd", required=True)

    image_list = image_sub.add_parser("list", help="List available Microsoft server images")
    image_list.add_argument("--json", action="store_true", help="Emit JSON output")
    image_list.set_defaults(func=cmd_hyperv_image_list)

    image_show = image_sub.add_parser("show", help="Show one image catalog entry")
    image_show.add_argument("image_id", help="Catalog image id")
    image_show.add_argument("--json", action="store_true", help="Emit JSON output")
    image_show.set_defaults(func=cmd_hyperv_image_show)

    image_download = image_sub.add_parser("download", help="Download image from official catalog URL")
    image_download.add_argument("image_id", nargs="?", default="", help="Catalog image id")
    image_download.add_argument(
        "--url",
        default="",
        help="Direct HTTPS URL (allowed only if host is in official/authorized domain list)",
    )
    image_download.add_argument(
        "--sha256",
        default="",
        help="Expected SHA256 hash (recommended for direct URLs)",
    )
    image_download.add_argument("--dest", default="", help="Destination file path")
    image_download.add_argument(
        "--allow-domain",
        action="append",
        default=[],
        help="Additional authorized download domain (repeatable)",
    )
    image_download.add_argument(
        "--cache-mode",
        choices=("cache-first", "download-only", "cache-only"),
        default="cache-first",
        help="OS media resolution strategy",
    )
    image_download.add_argument(
        "--cache-dir",
        action="append",
        default=[],
        help="Additional cache directory to search before download (repeatable)",
    )
    image_download.add_argument(
        "--require-sha256",
        action="store_true",
        help="Fail if expected SHA256 is missing",
    )
    image_download.add_argument(
        "--commit-manifest",
        action="store_true",
        help="Auto-commit generated manifest into git after successful media resolution",
    )
    image_download.add_argument(
        "--confirm",
        action="store_true",
        help="Required flag to execute actual download (otherwise preview only)",
    )
    image_download.add_argument("--json", action="store_true", help="Emit JSON output")
    image_download.set_defaults(func=cmd_hyperv_image_download)

    image_cache_seed = image_sub.add_parser("cache-seed", help="Seed local cache from manually downloaded ISO")
    image_cache_seed.add_argument("source", help="Path to existing ISO file")
    image_cache_seed.add_argument("--image-id", default="", help="Image id/alias for cache naming")
    image_cache_seed.add_argument("--name", default="", help="Display name for manifest")
    image_cache_seed.add_argument("--channel", default="manual-cache-seed", help="Manifest channel label")
    image_cache_seed.add_argument(
        "--url",
        default="",
        help="Official source URL used to obtain this file (provenance metadata only)",
    )
    image_cache_seed.add_argument("--sha256", default="", help="Expected SHA256 to verify source file")
    image_cache_seed.add_argument("--dest", default="", help="Destination cache path")
    image_cache_seed.add_argument(
        "--allow-domain",
        action="append",
        default=[],
        help="Authorized domains associated with source provenance (repeatable)",
    )
    image_cache_seed.add_argument(
        "--commit-manifest",
        action="store_true",
        help="Auto-commit generated manifest into git",
    )
    image_cache_seed.add_argument(
        "--confirm",
        action="store_true",
        help="Required flag to execute cache seeding (otherwise preview only)",
    )
    image_cache_seed.add_argument("--json", action="store_true", help="Emit JSON output")
    image_cache_seed.set_defaults(func=cmd_hyperv_image_cache_seed)

    vm = hyperv_sub.add_parser("vm", help="Create/configure Hyper-V VMs")
    vm_sub = vm.add_subparsers(dest="vm_cmd", required=True)

    vm_create = vm_sub.add_parser("create", help="Create a new Hyper-V VM")
    vm_create.add_argument("name", help="VM name")
    vm_create.add_argument("--switch", default="Default Switch", help="Hyper-V switch name")
    vm_create.add_argument("--memory-mb", type=int, default=4096, help="Startup memory (MB)")
    vm_create.add_argument("--cpu", type=int, default=2, help="vCPU count")
    vm_create.add_argument("--vhdx-gb", type=int, default=80, help="OS disk size (GB)")
    vm_create.add_argument("--vhdx-path", default="", help="Optional VHDX path")
    vm_create.add_argument("--iso-path", default="", help="Optional ISO path to attach")
    vm_create.add_argument("--execute", action="store_true", help="Execute create operation")
    vm_create.add_argument("--json", action="store_true", help="Emit JSON output")
    vm_create.set_defaults(func=cmd_hyperv_vm_create)

    vm_config = vm_sub.add_parser("configure", help="Configure an existing Hyper-V VM")
    vm_config.add_argument("name", help="VM name")
    vm_config.add_argument("--memory-mb", type=int, default=0, help="Startup memory (MB)")
    vm_config.add_argument("--cpu", type=int, default=0, help="vCPU count")
    vm_config.add_argument("--switch", default="", help="Switch name to connect")
    vm_config.add_argument("--execute", action="store_true", help="Execute configure operation")
    vm_config.add_argument("--json", action="store_true", help="Emit JSON output")
    vm_config.set_defaults(func=cmd_hyperv_vm_configure)

    bootstrap = hyperv_sub.add_parser("bootstrap", help="Plan one-time server/domain bootstrap")
    bootstrap_sub = bootstrap.add_subparsers(dest="bootstrap_cmd", required=True)

    bootstrap_plan = bootstrap_sub.add_parser("plan", help="Show required secrets and next steps")
    bootstrap_plan.add_argument("vm_name", help="VM name")
    bootstrap_plan.add_argument(
        "--profile",
        choices=("standalone", "adds_new_forest", "join_domain", "adlds"),
        default="standalone",
        help="Bootstrap profile",
    )
    bootstrap_plan.add_argument("--json", action="store_true", help="Emit JSON output")
    bootstrap_plan.set_defaults(func=cmd_hyperv_bootstrap_plan)

    wizard = hyperv_sub.add_parser(
        "wizard",
        help="Resolve OS media, create a boot-ready Hyper-V VM, and optionally hand off to the sensitive wizard",
    )
    wizard.add_argument(
        "--profile",
        choices=("standalone", "adds_new_forest", "join_domain", "adlds", "custom"),
        default="standalone",
        help="Sensitive wizard profile",
    )
    wizard.add_argument(
        "--os-profile",
        choices=tuple(sorted(OS_WIZARD_PRESETS.keys())) + ("custom",),
        default="custom",
        help="OS-specific wizard preset; enables --download-os automatically",
    )
    wizard.add_argument(
        "--list-os-profiles",
        action="store_true",
        help="Show available OS wizard presets and exit",
    )
    wizard.add_argument(
        "--download-os",
        action="store_true",
        help="Run OS download step before VM creation",
    )
    wizard.add_argument("--vm-name", default="", help="VM name for the boot-ready Hyper-V create step")
    wizard.add_argument("--switch", default="Default Switch", help="Hyper-V switch name for VM creation")
    wizard.add_argument("--memory-mb", type=int, default=4096, help="Startup memory (MB) for VM creation")
    wizard.add_argument("--cpu", type=int, default=2, help="vCPU count for VM creation")
    wizard.add_argument("--vhdx-gb", type=int, default=80, help="OS disk size (GB) for VM creation")
    wizard.add_argument("--vhdx-path", default="", help="Optional VHDX path for VM creation")
    wizard.add_argument(
        "--os-local-iso",
        default="",
        help="Local/portable ISO path to cache-seed before --download-os execution",
    )
    wizard.add_argument(
        "--no-os-local-prompt",
        dest="os_prompt_local_media",
        action="store_false",
        help="Disable interactive prompt for local/portable ISO in execute flow",
    )
    wizard.add_argument(
        "--os-image-id",
        default="",
        help="Catalog image id for --download-os",
    )
    wizard.add_argument(
        "--os-url",
        default="",
        help="Direct HTTPS URL for --download-os",
    )
    wizard.add_argument(
        "--os-sha256",
        default="",
        help="Expected SHA256 for --download-os",
    )
    wizard.add_argument(
        "--os-dest",
        default="",
        help="Destination path for --download-os",
    )
    wizard.add_argument(
        "--allow-domain",
        action="append",
        default=[],
        help="Additional authorized domain for --download-os (repeatable)",
    )
    wizard.add_argument(
        "--os-cache-mode",
        choices=("cache-first", "download-only", "cache-only"),
        default="cache-first",
        help="OS media resolution strategy for --download-os",
    )
    wizard.add_argument(
        "--os-cache-dir",
        action="append",
        default=[],
        help="Additional OS cache directory for --download-os (repeatable)",
    )
    wizard.add_argument(
        "--os-require-sha256",
        action="store_true",
        help="Require expected SHA256 for --download-os",
    )
    wizard.add_argument(
        "--commit-manifest",
        action="store_true",
        help="Auto-commit generated OS media manifests when --execute is used",
    )
    wizard.add_argument(
        "--execute",
        action="store_true",
        help="Execute OS media resolution, VM creation, and optional sensitive handoff",
    )
    wizard.set_defaults(os_prompt_local_media=True, func=cmd_hyperv_wizard)
