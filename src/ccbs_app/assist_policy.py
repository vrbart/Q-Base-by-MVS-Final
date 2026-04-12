"""Policy checks for accessibility assistant phase-1."""

from __future__ import annotations

import datetime as dt

from .assist_types import AssistProfile, AssistReceipt

EMERGENCY_PHRASES = {"stop all", "emergency stop"}


def profile_allowed(profile: AssistProfile) -> tuple[bool, str]:
    if not profile.ack_offline_single_player:
        return False, "profile_ack_required"
    if not profile.offline_only:
        return False, "offline_only_required"
    if profile.allow_multiplayer:
        return False, "multiplayer_not_allowed"
    return True, "ok"


def is_emergency_phrase(transcript_normalized: str) -> bool:
    return transcript_normalized.strip() in EMERGENCY_PHRASES


def requires_confirmation(confirm_level: str) -> bool:
    return confirm_level == "require"


def confirmation_allowed(confirm_level: str, confirm_flag: bool) -> tuple[bool, str]:
    if requires_confirmation(confirm_level) and not confirm_flag:
        return False, "confirmation_required"
    return True, "ok"


def cooldown_allowed(last_receipt: AssistReceipt | None, cooldown_ms: int, now_utc: dt.datetime) -> tuple[bool, str]:
    if cooldown_ms <= 0 or last_receipt is None:
        return True, "ok"
    try:
        last_dt = dt.datetime.fromisoformat(last_receipt.ts)
    except Exception:  # noqa: BLE001
        return True, "ok"
    delta_ms = int((now_utc - last_dt).total_seconds() * 1000)
    if delta_ms < max(0, cooldown_ms):
        return False, f"cooldown_active:{max(0, cooldown_ms - delta_ms)}ms_remaining"
    return True, "ok"
