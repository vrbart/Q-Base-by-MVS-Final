"""STT adapter surface for phase-1 transcript-driven assistant runs.

Phase-1 does not capture live audio. This module defines a stable interface so
future local engines (for example Vosk/Whisper) can be added without CLI churn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class STTResult:
    transcript: str
    confidence: float


class STTAdapter(Protocol):
    def transcribe(self, source: str) -> STTResult:
        """Return transcript text from a source token.

        For phase-1, `source` is already user-provided text.
        """
        ...


class TranscriptAdapter:
    """Simple adapter that treats source text as already transcribed."""

    def transcribe(self, source: str) -> STTResult:
        text = source.strip()
        return STTResult(transcript=text, confidence=1.0 if text else 0.0)
