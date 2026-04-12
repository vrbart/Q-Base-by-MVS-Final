"""Types for accessibility assistant phase-1 workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssistProfile:
    profile_id: str
    game_name: str
    offline_only: bool
    allow_multiplayer: bool
    ack_offline_single_player: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class AssistAction:
    action_type: str
    payload: str
    order_index: int


@dataclass(frozen=True)
class AssistCommand:
    command_id: int
    profile_id: str
    name: str
    phrases: list[str]
    actions: list[AssistAction]
    cooldown_ms: int
    confirm_level: str
    enabled: bool


@dataclass(frozen=True)
class AssistDecision:
    status: str
    reason: str
    transcript_normalized: str
    dry_run: bool
    blocked: bool
    command_id: int | None
    command_name: str
    requires_confirmation: bool
    action_plan: list[AssistAction]


@dataclass(frozen=True)
class AssistReceipt:
    ts: str
    profile_id: str
    transcript_normalized: str
    status: str
    reason: str
    command_name: str
    action_summary: str
    confirm_used: bool
    metadata: dict[str, Any]


@dataclass(frozen=True)
class AssistPackResult:
    output: str
    file_count: int
    manifest_entries: int
