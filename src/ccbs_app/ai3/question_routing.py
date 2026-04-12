"""Question classification helpers for ai3 routing decisions."""

from __future__ import annotations

import re
from typing import Any

_SIMPLE_OPENERS = (
    "what is",
    "what's",
    "whats",
    "who is",
    "where is",
    "when is",
    "which is",
    "which are",
    "name the",
    "define ",
    "capital of ",
)

_QUESTION_WORD_PREFIX = re.compile(r"^(what|who|where|when|which|is|are|can|could|would|should)\b", re.IGNORECASE)

_COMPLEX_HINTS = (
    "how to",
    "step by step",
    "compare",
    "tradeoff",
    "architecture",
    "design",
    "migrate",
    "implementation",
    "strategy",
    "policy",
)

_CODE_HINTS = (
    "code",
    "repo",
    "file",
    "python",
    "javascript",
    "typescript",
    "sql",
    "yaml",
    "json",
    "debug",
    "refactor",
    "stack trace",
    "exception",
    "unit test",
)

_COUNTRY_CAPITALS: dict[str, tuple[str, str]] = {
    "china": ("China", "Beijing"),
    "canada": ("Canada", "Ottawa"),
    "united states": ("the United States", "Washington, D.C."),
    "usa": ("the United States", "Washington, D.C."),
    "us": ("the United States", "Washington, D.C."),
    "mexico": ("Mexico", "Mexico City"),
    "japan": ("Japan", "Tokyo"),
    "india": ("India", "New Delhi"),
    "france": ("France", "Paris"),
    "germany": ("Germany", "Berlin"),
    "italy": ("Italy", "Rome"),
    "spain": ("Spain", "Madrid"),
    "united kingdom": ("the United Kingdom", "London"),
    "uk": ("the United Kingdom", "London"),
    "australia": ("Australia", "Canberra"),
    "brazil": ("Brazil", "Brasilia"),
}


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().split()).lower()


def classify_question(question: str) -> dict[str, Any]:
    raw = " ".join(str(question or "").strip().split())
    normalized = raw.lower()
    token_count = len([tok for tok in re.split(r"\s+", normalized) if tok])
    char_count = len(raw)

    starts_like_question = bool(_QUESTION_WORD_PREFIX.match(normalized))
    simple_opener = any(normalized.startswith(prefix) for prefix in _SIMPLE_OPENERS)
    complex_hint = any(phrase in normalized for phrase in _COMPLEX_HINTS)
    code_hint = any(phrase in normalized for phrase in _CODE_HINTS)
    too_long = token_count > 16 or char_count > 120
    multi_clause = normalized.count("?") > 1 or ("\n" in raw)

    simple_qa = bool(raw) and (starts_like_question or simple_opener) and not complex_hint and not code_hint and not too_long and not multi_clause
    reason = "simple_short_question" if simple_qa else "complex_or_contextual"

    return {
        "simple_qa": simple_qa,
        "reason": reason,
        "token_count": token_count,
        "char_count": char_count,
        "starts_like_question": starts_like_question or simple_opener,
        "complex_hint": complex_hint,
        "code_hint": code_hint,
    }


def simple_fact_answer(question: str) -> str:
    normalized = _normalize(question)
    if not normalized:
        return ""

    match = re.search(r"\bcapital of ([a-z .'-]+)\b", normalized)
    if not match:
        return ""

    country = re.sub(r"\s+", " ", match.group(1)).strip(" .?!")
    country = re.sub(r"^the\s+", "", country)
    country = country.strip()
    if not country:
        return ""

    entry = _COUNTRY_CAPITALS.get(country)
    if entry is None:
        return ""
    display_name, capital = entry
    return f"The capital of {display_name} is {capital}."
