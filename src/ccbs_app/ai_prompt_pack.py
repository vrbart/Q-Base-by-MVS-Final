"""Prompt-pack helpers for curated safe agent prompts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _pack_dir(root: Path) -> Path:
    return root / "config" / "prompt_packs"


def list_prompt_packs(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pack_dir = _pack_dir(root)
    if not pack_dir.exists():
        return out
    for path in sorted(pack_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        prompts = payload.get("prompts", [])
        out.append(
            {
                "pack_id": str(payload.get("pack_id", path.stem)),
                "name": str(payload.get("name", path.stem)),
                "description": str(payload.get("description", "")).strip(),
                "prompt_count": len(prompts) if isinstance(prompts, list) else 0,
                "path": str(path),
            }
        )
    return out


def load_prompt_pack(root: Path, pack_id: str) -> dict[str, Any]:
    clean = pack_id.strip()
    if not clean:
        raise ValueError("pack_id is required")
    path = _pack_dir(root) / f"{clean}.json"
    if not path.exists():
        raise ValueError(f"prompt pack not found: {clean}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"prompt pack invalid: {clean}")
    payload.setdefault("pack_id", clean)
    payload.setdefault("prompts", [])
    return payload


def find_prompt(pack: dict[str, Any], prompt_id: str) -> dict[str, Any]:
    clean = prompt_id.strip()
    rows = pack.get("prompts", [])
    if not isinstance(rows, list):
        raise ValueError("prompt pack malformed: prompts must be a list")
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("prompt_id", "")).strip() == clean:
            return row
    raise ValueError(f"prompt not found: {clean}")


def _markdown_export(pack: dict[str, Any], single_prompt: dict[str, Any] | None = None) -> str:
    lines = [
        f"# {pack.get('name', pack.get('pack_id', 'Prompt Pack'))}",
        "",
        str(pack.get("description", "")).strip(),
        "",
    ]
    prompts = [single_prompt] if single_prompt is not None else list(pack.get("prompts", []))
    for row in prompts:
        if not isinstance(row, dict):
            continue
        lines.extend(
            [
                f"## {row.get('prompt_id', 'prompt')}",
                "",
                f"- Title: {row.get('title', '')}",
                f"- Risk: {row.get('risk_level', '')}",
                "",
                "```text",
                str(row.get("content", "")).rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def export_prompt_pack(
    *,
    root: Path,
    pack_id: str,
    output: Path,
    fmt: str,
    prompt_id: str = "",
) -> dict[str, Any]:
    pack = load_prompt_pack(root, pack_id=pack_id)
    selected = find_prompt(pack, prompt_id) if prompt_id.strip() else None
    output.parent.mkdir(parents=True, exist_ok=True)
    clean_fmt = fmt.strip().lower()
    if clean_fmt == "json":
        payload = dict(pack)
        if selected is not None:
            payload["prompts"] = [selected]
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    elif clean_fmt == "markdown":
        output.write_text(_markdown_export(pack, selected), encoding="utf-8")
    else:
        raise ValueError("format must be markdown|json")
    return {
        "pack_id": str(pack.get("pack_id", pack_id)),
        "output": str(output),
        "format": clean_fmt,
        "prompt_id": prompt_id.strip(),
    }

