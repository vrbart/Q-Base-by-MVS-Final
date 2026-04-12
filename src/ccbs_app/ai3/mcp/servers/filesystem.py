"""Filesystem MCP server."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_file(path: str, max_bytes: int = 65536) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    blob = target.read_bytes()
    cap = max(1, int(max_bytes))
    chunk = blob[:cap]
    text = chunk.decode("utf-8", errors="ignore")
    return {
        "path": str(target),
        "size_bytes": len(blob),
        "returned_bytes": len(chunk),
        "truncated": len(blob) > cap,
        "content": text,
    }


def write_file(path: str, content: str, append: bool = False) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8") as fh:
        fh.write(content)
    return {
        "path": str(target),
        "written_chars": len(content),
        "append": bool(append),
    }
