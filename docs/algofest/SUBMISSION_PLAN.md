# Q-Base (QB) by CCBS - AlgoFest Submission Plan

This plan is implementation-grounded to this repository and should be used as the final internal submission playbook.

## 1. Thesis

QB addresses the orchestration gap in AI-assisted engineering by providing:

1. Local-first execution and control.
2. Deterministic multi-lane task routing.
3. Policy-aware gating and evidence capture.
4. Optional Azure Quantum optimisation extension.

The system prioritizes reproducibility and auditability, not only feature output.

## 2. Architecture Summary

Core components in this repo:

1. Orchestration + routing logic:
   - `src/ccbs_app/multi_instance_agent.py`
   - `src/ccbs_app/ai3/api_v3.py`
2. Multi-instance lane control:
   - `scripts/codex_multi_manager.ps1`
3. Idempotent health/recovery bootstrap:
   - `scripts/qb_doctor.ps1`
   - `QB-doctor.bat`
4. Quantum workspace integration:
   - `scripts/qb_quantum_multi_instance.ps1`
5. Runtime profile/config contracts:
   - `config/codex_instances.json`
   - `config/multi_instance_profile.json`

Execution model:

1. Job enters via UI/API.
2. Request is normalized and lane/routing metadata inferred.
3. Lane manager executes in mapped lane(s), with duplicate-shell prevention and reuse.
4. Output and runtime telemetry are persisted.
5. Optional quantum checks/selection run if enabled.

## 3. Innovation -> Evidence Mapping

1. Idempotent lane orchestration
   - Evidence: lane status (`availability_counter`, `LaneShells`, `HealthyShells`)
   - Source: `scripts/codex_multi_manager.ps1`
2. Parser-assisted lane inference (`-1`, `#R2`, `lane 3`)
   - Evidence: parser metadata in route output and chat response payload
   - Source: `src/ccbs_app/multi_instance_agent.py`, `src/ccbs_app/ai3/api_v3.py`
3. Local-first with cloud-optional quantum extension
   - Evidence: successful local health path independent of quantum; optional workspace/target checks
   - Source: `scripts/qb_doctor.ps1`, `scripts/qb_quantum_multi_instance.ps1`
4. Evidence-first verification workflow
   - Evidence: generated JSON summaries and test output
   - Source: `scripts/algofest_submission_smoke.ps1`, `tests/test_multi_instance_agent.py`, `tests/test_multi_instance_api_surface.py`, `tests/test_ai3_foundry_pane.py`

## 4. Demo Plan (4:20 Target)

1. Problem + value framing (0:00-0:30).
2. Architecture and lane model (0:30-1:25).
3. One-command proof run (1:25-2:45).
4. Execution/evidence view (2:45-3:45).
5. Optional quantum extension mention (3:45-4:10).
6. Close + reproducibility CTA (4:10-4:20).

Detailed script:

- `docs/algofest/VIDEO_SCRIPT_4M20S.md`
- `docs/algofest/SHOTLIST.md`

## 5. Evidence Checklist

1. Doctor/health output.
2. Multi-instance lane status output.
3. API health and runtime snapshots.
4. Targeted test run output.
5. Evidence summary JSON (`dist/algofest/evidence/`).
6. UI screenshots of intake, lane state, and output panels.
7. Optional Azure Quantum status output when enabled.

## 6. Judging Criteria Mapping

1. Innovation & Creativity (25%)
   - Multi-lane deterministic orchestration + parser-driven routing.
2. Technical Complexity (25%)
   - Runtime coordination, policy checks, idempotent recovery, optional quantum.
3. Practical Impact (20%)
   - Repeatable, local, auditable engineering workflows.
4. Design & UX (15%)
   - Unified UI flow with explicit lane status and controls.
5. Presentation & Demo (15%)
   - Tight 4:20 runbook with reproducible proof path.

## 7. Risk Register (Top)

1. Quantum endpoint instability
   - Mitigation: classical/local path is default and complete.
2. Runtime drift across machines
   - Mitigation: one-command doctor + smoke script + documented expected outputs.
3. Over-claiming
   - Mitigation: explicit "do not claim" boundaries in submission docs.
4. Demo timing overrun
   - Mitigation: strict shot list and backup clips.

## 8. Packaging Checklist

1. Public polished repo mirror exported.
2. Submission docs complete and aligned.
3. Video script and shot list finalized.
4. Smoke evidence generated.
5. All Devpost fields pre-filled from canonical docs.
6. No sensitive files or tokens in submission mirror.

## 9. 48-Hour Execution Sequence

1. Freeze commit/tag for submission.
2. Generate public mirror + manifest.
3. Run smoke/evidence script.
4. Record demo (live + backup clips).
5. Final consistency pass across repo/readme/devpost fields.
6. Submit with links verified.

## 10. Do-Not-Claim Guardrails

1. Do not claim full production readiness.
2. Do not claim quantum is mandatory for core flow.
3. Do not claim guaranteed optimization superiority on every workload.
4. Do not claim unlimited lane scalability on all hardware.
5. Do not claim all cataloged agents/surfaces are fully implemented.
