"""Text chunking helpers with offset metadata."""

from __future__ import annotations

import re

TOKEN_RE = re.compile(r"[a-z0-9_./-]+", re.IGNORECASE)


def token_count(text: str) -> int:
    return len(TOKEN_RE.findall(text or ""))


def chunk_text(text: str, size: int = 1000, overlap: int = 150) -> list[dict[str, int | str]]:
    clean = (text or "").replace("\r\n", "\n")
    if not clean.strip():
        return []
    out: list[dict[str, int | str]] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + max(64, int(size)))
        payload = clean[start:end].strip()
        if payload:
            out.append(
                {
                    "text": payload,
                    "start_offset": start,
                    "end_offset": end,
                    "token_count": token_count(payload),
                }
            )
        if end >= len(clean):
            break
        start = max(start + 1, end - max(0, int(overlap)))
    return out
