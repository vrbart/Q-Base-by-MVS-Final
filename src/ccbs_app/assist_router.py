"""Deterministic transcript routing for accessibility assistant."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .assist_types import AssistCommand

_NON_WORD = re.compile(r"[^a-z0-9 ]+")


@dataclass(frozen=True)
class RouteResult:
    status: str
    reason: str
    transcript_normalized: str
    command: AssistCommand | None
    alternatives: list[str]


def normalize_transcript(text: str) -> str:
    lowered = text.lower().strip()
    lowered = _NON_WORD.sub(" ", lowered)
    return " ".join(lowered.split())


def _score_phrase(transcript_norm: str, phrase_norm: str) -> int:
    if not transcript_norm or not phrase_norm:
        return 0
    if transcript_norm == phrase_norm:
        return 100
    if transcript_norm.startswith(phrase_norm):
        return 80
    if phrase_norm.startswith(transcript_norm):
        return 70
    if phrase_norm in transcript_norm:
        return 60
    tokens_t = set(transcript_norm.split())
    tokens_p = set(phrase_norm.split())
    overlap = len(tokens_t & tokens_p)
    if overlap:
        return 10 + overlap
    return 0


def route_transcript(transcript: str, commands: list[AssistCommand]) -> RouteResult:
    transcript_norm = normalize_transcript(transcript)
    if not transcript_norm:
        return RouteResult(
            status="empty",
            reason="empty_transcript",
            transcript_normalized=transcript_norm,
            command=None,
            alternatives=[],
        )

    best_score = 0
    best_command: AssistCommand | None = None
    top_commands: list[AssistCommand] = []

    for cmd in commands:
        if not cmd.enabled:
            continue
        command_score = 0
        for phrase in cmd.phrases:
            score = _score_phrase(transcript_norm, normalize_transcript(phrase))
            if score > command_score:
                command_score = score
        if command_score <= 0:
            continue

        if command_score > best_score:
            best_score = command_score
            best_command = cmd
            top_commands = [cmd]
        elif command_score == best_score:
            top_commands.append(cmd)

    if best_command is None:
        return RouteResult(
            status="no_match",
            reason="no_command_match",
            transcript_normalized=transcript_norm,
            command=None,
            alternatives=[],
        )

    unique_top = []
    seen = set()
    for item in top_commands:
        if item.command_id in seen:
            continue
        seen.add(item.command_id)
        unique_top.append(item)

    if len(unique_top) > 1:
        names = [item.name for item in unique_top]
        return RouteResult(
            status="ambiguous",
            reason="ambiguous_command_match",
            transcript_normalized=transcript_norm,
            command=None,
            alternatives=names,
        )

    return RouteResult(
        status="matched",
        reason="matched_command",
        transcript_normalized=transcript_norm,
        command=best_command,
        alternatives=[],
    )
