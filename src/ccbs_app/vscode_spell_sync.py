"""Sync CCBS cspell words into global VS Code user settings."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .jsonc_utils import dump_json, parse_jsonc


@dataclass(frozen=True)
class VSCodeSpellSyncResult:
    ok: bool
    settings_path: str
    source_words_count: int
    existing_words_count: int
    added_words_count: int
    total_words_count: int
    dry_run: bool
    warnings: tuple[str, ...]


def _default_settings_path() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        normalized = str(appdata).replace("\\", "/")
        # In WSL, APPDATA is commonly exported as /mnt/c/... for the Windows user profile.
        if normalized.startswith("/mnt/"):
            return Path(normalized) / "Code" / "User" / "settings.json"

    if sys.platform.startswith("win"):
        if appdata:
            return Path(appdata) / "Code" / "User" / "settings.json"
        return Path.home() / "AppData" / "Roaming" / "Code" / "User" / "settings.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    return Path.home() / ".config" / "Code" / "User" / "settings.json"


def _load_source_words(root: Path) -> list[str]:
    config = root / "cspell.json"
    raw = json.loads(config.read_text(encoding="utf-8"))
    words = raw.get("words", [])
    if not isinstance(words, list):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for item in words:
        if not isinstance(item, str):
            continue
        token = item.strip()
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(token)
    return sorted(values, key=lambda value: (value.casefold(), value))


def _extract_existing_words(settings: dict[str, object]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    existing_raw = settings.get("cSpell.userWords", [])
    if not isinstance(existing_raw, list):
        warnings.append("cSpell.userWords was not a list and has been replaced.")
        return [], warnings

    values: list[str] = []
    for item in existing_raw:
        if not isinstance(item, str):
            warnings.append("Ignored non-string entry in cSpell.userWords.")
            continue
        token = item.strip()
        if not token:
            continue
        values.append(token)
    return values, warnings


def _merge_words(existing_words: list[str], source_words: list[str]) -> tuple[list[str], int]:
    by_key: dict[str, str] = {}
    for item in existing_words:
        key = item.casefold()
        if key not in by_key:
            by_key[key] = item

    added = 0
    for item in source_words:
        key = item.casefold()
        if key not in by_key:
            by_key[key] = item
            added += 1

    merged = sorted(by_key.values(), key=lambda value: (value.casefold(), value))
    return merged, added


def sync_vscode_spell_words(root: Path, settings_path: Path | None = None, dry_run: bool = False) -> VSCodeSpellSyncResult:
    source_words = _load_source_words(root)
    target = (settings_path or _default_settings_path()).expanduser()
    warnings: list[str] = []

    settings: dict[str, object] = {}
    if target.exists():
        raw = target.read_text(encoding="utf-8-sig")
        try:
            settings = parse_jsonc(raw)
        except ValueError as exc:
            raise ValueError(f"Failed to parse VS Code settings at {target}: {exc}") from exc
    else:
        warnings.append("VS Code settings file did not exist and was initialized.")

    existing_words, extract_warnings = _extract_existing_words(settings)
    warnings.extend(extract_warnings)

    existing_unique = {item.casefold() for item in existing_words}
    merged_words, added = _merge_words(existing_words, source_words)
    settings["cSpell.userWords"] = merged_words

    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dump_json(settings), encoding="utf-8")

    return VSCodeSpellSyncResult(
        ok=True,
        settings_path=str(target),
        source_words_count=len(source_words),
        existing_words_count=len(existing_unique),
        added_words_count=added,
        total_words_count=len(merged_words),
        dry_run=bool(dry_run),
        warnings=tuple(warnings),
    )
