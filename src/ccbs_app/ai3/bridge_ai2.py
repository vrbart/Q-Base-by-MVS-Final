"""Dual-write bridge from ai3 runtime events into ai2 stores."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..ai_audit import log_event as ai2_log_event
from ..ai_local import store_memory as ai2_store_memory


def mirror_run_event(root: Path, event_type: str, payload: dict[str, Any]) -> None:
    ai2_log_event(root=root, event_type=f"ai3_{event_type}", actor="ai3", details=payload)


def mirror_answer_memory(root: Path, question: str, answer: str, metadata: dict[str, Any] | None = None) -> None:
    ai2_store_memory(
        root=root,
        kind="ai3-hybrid",
        question=question,
        answer=answer,
        metadata=metadata or {},
    )
