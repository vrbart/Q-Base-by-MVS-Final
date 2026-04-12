"""Spell-check integration helpers."""

from __future__ import annotations

import sys
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TARGETS = [
    "README.md",
    "USAGE.md",
    "docs",
    "src",
    "tests",
    "bricks",
]


@dataclass(frozen=True)
class SpellcheckResult:
    ok: bool
    return_code: int
    command: list[str]
    stdout: str
    stderr: str
    tool_found: bool


def _resolve_targets(root: Path, raw_paths: list[str]) -> list[str]:
    targets = raw_paths if raw_paths else DEFAULT_TARGETS
    resolved: list[str] = []
    seen: set[str] = set()

    for raw in targets:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (root / candidate).resolve()
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            resolved.append(str(candidate))
    return resolved


def _local_cspell_candidate(root: Path) -> str:
    bin_name = "cspell.cmd" if sys.platform.startswith("win") else "cspell"
    return str((root / "node_modules" / ".bin" / bin_name).resolve())


def _resolve_cspell_runner(root: Path) -> list[str]:
    cspell = shutil.which("cspell")
    if cspell:
        return [cspell]

    local_cspell = _local_cspell_candidate(root)
    if Path(local_cspell).exists():
        return [local_cspell]

    npx = shutil.which("npx")
    if npx:
        return [npx, "--yes", "cspell"]

    return []


def _is_windows_runner(runner: list[str]) -> bool:
    if not runner or sys.platform.startswith("win"):
        return False
    entry = runner[0].strip().lower()
    if not entry:
        return False
    if entry.endswith((".exe", ".cmd", ".bat")):
        return True
    if entry.startswith("/mnt/"):
        return True
    return False


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


def run_spellcheck(root: Path, paths: list[str], config_path: str = "cspell.json") -> SpellcheckResult:
    runner = _resolve_cspell_runner(root)
    config = Path(config_path).expanduser()
    if not config.is_absolute():
        config = (root / config).resolve()

    raw_targets = _resolve_targets(root, paths)

    if not runner:
        return SpellcheckResult(
            ok=False,
            return_code=127,
            command=[],
            stdout="",
            stderr="cspell not found (checked PATH, local node_modules, and npx)",
            tool_found=False,
        )

    use_windows_paths = _is_windows_runner(runner)
    cfg_arg = _to_windows_path(config) if use_windows_paths else str(config)
    targets = [_to_windows_path(Path(p)) for p in raw_targets] if use_windows_paths else raw_targets

    cmd = [
        *runner,
        "--no-progress",
        "--config",
        cfg_arg,
        *targets,
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return SpellcheckResult(
        ok=proc.returncode == 0,
        return_code=int(proc.returncode),
        command=cmd,
        stdout=proc.stdout,
        stderr=proc.stderr,
        tool_found=True,
    )
