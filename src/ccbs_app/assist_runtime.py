"""Runtime orchestration for accessibility assistant phase-1 dry-run."""

from __future__ import annotations

import datetime as dt

from .assist_policy import confirmation_allowed, cooldown_allowed, is_emergency_phrase, profile_allowed
from .assist_router import normalize_transcript, route_transcript
from .assist_store import get_profile, last_command_receipt, list_commands, record_receipt
from .assist_types import AssistAction, AssistDecision, AssistReceipt


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _action_summary(actions: list[AssistAction]) -> str:
    if not actions:
        return "none"
    parts = [f"{item.action_type}:{item.payload}" for item in actions[:8]]
    return ", ".join(parts)


def run_assist_dry(
    root,
    profile_id: str,
    transcript: str,
    confirm: bool = False,
) -> tuple[AssistDecision, AssistReceipt]:
    transcript_norm = normalize_transcript(transcript)

    profile = get_profile(root, profile_id)
    if profile is None:
        decision = AssistDecision(
            status="blocked",
            reason="profile_not_found",
            transcript_normalized=transcript_norm,
            dry_run=True,
            blocked=True,
            command_id=None,
            command_name="",
            requires_confirmation=False,
            action_plan=[],
        )
        receipt = AssistReceipt(
            ts=_utc_now(),
            profile_id=profile_id,
            transcript_normalized=transcript_norm,
            status=decision.status,
            reason=decision.reason,
            command_name="",
            action_summary="none",
            confirm_used=bool(confirm),
            metadata={"dry_run": True, "blocked": True},
        )
        record_receipt(root, receipt)
        return decision, receipt

    if is_emergency_phrase(transcript_norm):
        decision = AssistDecision(
            status="halt",
            reason="emergency_stop_phrase",
            transcript_normalized=transcript_norm,
            dry_run=True,
            blocked=False,
            command_id=None,
            command_name="EMERGENCY_STOP",
            requires_confirmation=False,
            action_plan=[],
        )
        receipt = AssistReceipt(
            ts=_utc_now(),
            profile_id=profile.profile_id,
            transcript_normalized=transcript_norm,
            status=decision.status,
            reason=decision.reason,
            command_name=decision.command_name,
            action_summary="none",
            confirm_used=bool(confirm),
            metadata={"dry_run": True, "blocked": False},
        )
        record_receipt(root, receipt)
        return decision, receipt

    profile_ok, profile_reason = profile_allowed(profile)
    if not profile_ok:
        decision = AssistDecision(
            status="blocked",
            reason=profile_reason,
            transcript_normalized=transcript_norm,
            dry_run=True,
            blocked=True,
            command_id=None,
            command_name="",
            requires_confirmation=False,
            action_plan=[],
        )
        receipt = AssistReceipt(
            ts=_utc_now(),
            profile_id=profile.profile_id,
            transcript_normalized=transcript_norm,
            status=decision.status,
            reason=decision.reason,
            command_name="",
            action_summary="none",
            confirm_used=bool(confirm),
            metadata={"dry_run": True, "blocked": True},
        )
        record_receipt(root, receipt)
        return decision, receipt

    commands = list_commands(root, profile.profile_id)
    routed = route_transcript(transcript=transcript, commands=commands)

    if routed.status == "no_match":
        decision = AssistDecision(
            status="no_match",
            reason=routed.reason,
            transcript_normalized=routed.transcript_normalized,
            dry_run=True,
            blocked=False,
            command_id=None,
            command_name="",
            requires_confirmation=False,
            action_plan=[],
        )
        receipt = AssistReceipt(
            ts=_utc_now(),
            profile_id=profile.profile_id,
            transcript_normalized=decision.transcript_normalized,
            status=decision.status,
            reason=decision.reason,
            command_name="",
            action_summary="none",
            confirm_used=bool(confirm),
            metadata={"dry_run": True, "blocked": False},
        )
        record_receipt(root, receipt)
        return decision, receipt

    if routed.status == "ambiguous":
        decision = AssistDecision(
            status="ambiguous",
            reason=routed.reason,
            transcript_normalized=routed.transcript_normalized,
            dry_run=True,
            blocked=True,
            command_id=None,
            command_name="",
            requires_confirmation=False,
            action_plan=[],
        )
        receipt = AssistReceipt(
            ts=_utc_now(),
            profile_id=profile.profile_id,
            transcript_normalized=decision.transcript_normalized,
            status=decision.status,
            reason=decision.reason,
            command_name="",
            action_summary="none",
            confirm_used=bool(confirm),
            metadata={"dry_run": True, "blocked": True, "alternatives": routed.alternatives},
        )
        record_receipt(root, receipt)
        return decision, receipt

    command = routed.command
    if command is None:
        decision = AssistDecision(
            status="blocked",
            reason="router_internal_error",
            transcript_normalized=routed.transcript_normalized,
            dry_run=True,
            blocked=True,
            command_id=None,
            command_name="",
            requires_confirmation=False,
            action_plan=[],
        )
        receipt = AssistReceipt(
            ts=_utc_now(),
            profile_id=profile.profile_id,
            transcript_normalized=decision.transcript_normalized,
            status=decision.status,
            reason=decision.reason,
            command_name="",
            action_summary="none",
            confirm_used=bool(confirm),
            metadata={"dry_run": True, "blocked": True},
        )
        record_receipt(root, receipt)
        return decision, receipt

    now = dt.datetime.now(dt.timezone.utc)
    last = last_command_receipt(root, profile.profile_id, command.name)
    cooldown_ok, cooldown_reason = cooldown_allowed(last_receipt=last, cooldown_ms=command.cooldown_ms, now_utc=now)
    if not cooldown_ok:
        decision = AssistDecision(
            status="blocked",
            reason=cooldown_reason,
            transcript_normalized=routed.transcript_normalized,
            dry_run=True,
            blocked=True,
            command_id=command.command_id,
            command_name=command.name,
            requires_confirmation=command.confirm_level == "require",
            action_plan=[],
        )
        receipt = AssistReceipt(
            ts=_utc_now(),
            profile_id=profile.profile_id,
            transcript_normalized=decision.transcript_normalized,
            status=decision.status,
            reason=decision.reason,
            command_name=decision.command_name,
            action_summary="none",
            confirm_used=bool(confirm),
            metadata={"dry_run": True, "blocked": True},
        )
        record_receipt(root, receipt)
        return decision, receipt

    confirm_ok, confirm_reason = confirmation_allowed(command.confirm_level, bool(confirm))
    if not confirm_ok:
        decision = AssistDecision(
            status="blocked",
            reason=confirm_reason,
            transcript_normalized=routed.transcript_normalized,
            dry_run=True,
            blocked=True,
            command_id=command.command_id,
            command_name=command.name,
            requires_confirmation=True,
            action_plan=[],
        )
        receipt = AssistReceipt(
            ts=_utc_now(),
            profile_id=profile.profile_id,
            transcript_normalized=decision.transcript_normalized,
            status=decision.status,
            reason=decision.reason,
            command_name=decision.command_name,
            action_summary="none",
            confirm_used=bool(confirm),
            metadata={"dry_run": True, "blocked": True},
        )
        record_receipt(root, receipt)
        return decision, receipt

    decision = AssistDecision(
        status="dry_run_ready",
        reason="dry_run_plan_generated",
        transcript_normalized=routed.transcript_normalized,
        dry_run=True,
        blocked=False,
        command_id=command.command_id,
        command_name=command.name,
        requires_confirmation=command.confirm_level == "require",
        action_plan=command.actions,
    )
    receipt = AssistReceipt(
        ts=_utc_now(),
        profile_id=profile.profile_id,
        transcript_normalized=decision.transcript_normalized,
        status=decision.status,
        reason=decision.reason,
        command_name=decision.command_name,
        action_summary=_action_summary(command.actions),
        confirm_used=bool(confirm),
        metadata={"dry_run": True, "blocked": False, "action_count": len(command.actions)},
    )
    record_receipt(root, receipt)
    return decision, receipt
