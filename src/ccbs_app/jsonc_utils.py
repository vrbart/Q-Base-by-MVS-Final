"""Utilities for parsing JSON-with-comments input."""

from __future__ import annotations

import json
from typing import Any


def _strip_utf8_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _strip_jsonc_comments(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    in_line_comment = False
    in_block_comment = False

    i = 0
    size = len(text)
    while i < size:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < size else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                out.append(" ")
                out.append(" ")
                in_block_comment = False
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            out.append(" ")
            out.append(" ")
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            out.append(" ")
            out.append(" ")
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _remove_trailing_commas(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    i = 0
    size = len(text)

    while i < size:
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == ",":
            j = i + 1
            while j < size and text[j] in (" ", "\t", "\r", "\n"):
                j += 1
            if j < size and text[j] in ("]", "}"):
                i += 1
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def parse_jsonc(text: str) -> dict[str, Any]:
    cleaned = _strip_utf8_bom(text)
    no_comments = _strip_jsonc_comments(cleaned)
    normalized = _remove_trailing_commas(no_comments)
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSONC parse error at line {exc.lineno}, col {exc.colno}, pos {exc.pos}: {exc.msg}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSONC root must be an object")
    return parsed


def dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
