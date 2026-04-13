# FINAL QB Demo Video Script (Winning Cut)

This is the canonical, judge-facing runbook for a strong 2-5 minute submission video.

## Core Message (use this exact framing)

Q-Base is not a shortcut around work. It is a system for doing hard work with structure, evidence, and accountability.

Use this line on camera:

> Good systems do more than generate results. They reduce friction, protect dignity, and create more time for care, presence, and love.

Use this thesis during the optimization segment:

> QPU explores hard decision space; CPU verifies and executes with deterministic safety.

## Video Goal

Show five concrete things in one take:

1. Doctor/bootstrap recovery works.
2. Multi-lane UI is live and understandable.
3. Routing + optimization produce a visible decision.
4. Evidence artifacts are generated and inspectable.
5. Quantum is integrated but optional (preflight only in live cut).

## Runtime Profile For Winning Reliability

- Use the stable local path.
- Show quantum target preflight, not a long quantum solve.
- Keep the cut to 4:20 target (allowed range is 2:00-5:00).

## Preflight (before recording)

```powershell
cd C:\Users\Myles\Projects\CCBS-CLEAN-WORKSPACE\Q-Base-by-MVS-Final
$env:CCBS_AZ_SUBSCRIPTION_ID = "<SUBSCRIPTION_ID>"
$env:CCBS_AZ_RESOURCE_GROUP = "<RESOURCE_GROUP>"
$env:CCBS_AZ_WORKSPACE_NAME = "<WORKSPACE_NAME>"
$env:CCBS_AZ_LOCATION = "eastus"
$env:CCBS_CODEX_INSTANCES_CONFIG = "config\codex_instances_10.json"
```

If you want a quieter run, use default 3-lane config and skip the env var above.

## Recording Timeline (4:20 target)

### 0:00-0:15 Title Card

On-screen text:

- `Q-Base (QB) by MVS`
- `Local-first orchestration + evidence`
- `Optional Azure Quantum preflight`

Narration:

- "This demo shows structured orchestration, not a one-shot prompt."

### 0:15-0:55 Bootstrap Proof (one command)

Command:

```powershell
.\QB-doctor.bat -SubscriptionId $env:CCBS_AZ_SUBSCRIPTION_ID -ResourceGroup $env:CCBS_AZ_RESOURCE_GROUP -WorkspaceName $env:CCBS_AZ_WORKSPACE_NAME -Location $env:CCBS_AZ_LOCATION -OpenUi
```

Capture these lines clearly:

- API health `200 OK`
- workspace `Succeeded` and `usable Yes` (if quantum configured)
- lane availability `3/3` (or `10/10` if showcase mode)

Narration:

- "Doctor is idempotent and returns the stack to a healthy state."

### 0:55-1:30 UI Orientation (clear labels)

Open:

- `http://127.0.0.1:11435/v3/ui`

Point at:

- Lanes/availability
- Route Ask box (`-1 / -2 / -3` directives)
- Optimize button
- Evidence/telemetry region

Narration:

- "The control plane is explicit: route, optimize, verify, evidence."

### 1:30-2:50 Execute 3 Distinct Actions

Action A:

- Click `SYNC WORKSPACES`

Action B:

- Route ask with directive and label, for example:
- Route input: `-1 Decompose: auth, todo CRUD, docs, deploy plan`
- Label: `demo: decompose + assign`
- Click `ROUTE ASK`

Action C:

- Set max parallel (3 or 10 depending on mode)
- Click `OPTIMIZE`

Success criteria on-screen:

- Selected lane/solver/objective fields populate
- Token telemetry updates
- Last route table updates

Narration:

- "This is right-sized orchestration: not every task needs max parallelism."

### 2:50-3:35 Evidence Proof

Command window:

```powershell
Get-ChildItem .\dist\demo
Get-ChildItem .\dist\algofest\evidence
Get-Content .\dist\algofest\evidence\algofest_smoke_summary.json
```

Show:

- timestamped artifacts exist
- run summary fields are populated

Narration:

- "Claims are backed by artifacts, not just UI state."

### 3:35-4:00 Optional Quantum Preflight (fast)

```powershell
az quantum target list -o table
```

Narration:

- "Quantum is integrated as an optional optimization lane. If unavailable, QB falls back to deterministic CPU execution."

### 4:00-4:20 Closing Message

Use this close:

- "This project was built in real time through overlapping workstreams: writing, coding, proofing, validating, packaging, and orchestration."
- "QPU search plus CPU certainty is a practical team for safer, auditable automation."

## Strong Narration Blocks (drop-in)

### Opening

"Q-Base is a local-first orchestration runtime. It takes complex work, decomposes it, routes it across lanes, and returns evidence so results are inspectable and reproducible."

### QPU + CPU

"Quantum-style search helps explore competing options under constraints. CPU execution enforces policy, validation, and repeatability. Exploration plus verification is the practical pairing."

### Human Value

"This is not about replacing effort. It is about removing avoidable friction so people can focus on judgment, care, and meaningful work."

## If You Want Busy Visuals (without fake behavior)

Use this command to run the busy driver and capture many visible actions:

```powershell
.\Q-demo-busy.bat -SubscriptionId $env:CCBS_AZ_SUBSCRIPTION_ID -ResourceGroup $env:CCBS_AZ_RESOURCE_GROUP -WorkspaceName $env:CCBS_AZ_WORKSPACE_NAME -Location $env:CCBS_AZ_LOCATION -OpenUi -Use10Lanes -IncludeGitPush -CaptureSeconds 260
```

This gives you:

- UI activity
- terminal evidence checks
- optional Git push moment
- generated `dist/demo/qb_demo_steps.json`

## Video Acceptance Checklist (must all be true)

- At least 3 distinct UI actions are visible.
- A route/optimize decision is visibly populated.
- Evidence file output is shown in terminal.
- Duration is within 2:00-5:00.
- No secrets, webhook secrets, tokens, or private IDs are shown on camera.

## Post-Capture Packaging

Primary outputs to keep:

- `dist/demo/qb_demo_capture.webm`
- `dist/demo/qb_demo_steps.json`
- `dist/algofest/evidence/algofest_smoke_summary.json`

YouTube guidance:

- Upload as `Unlisted` for submission.
- Put this exact link in Devpost `Video demo link`.
- Keep repo link in `Try it out`.

## Fallback Path (if doctor fails under time pressure)

```powershell
.\Q-demo-record.bat -OpenUi -SkipQuantumChecks -CaptureSeconds 150 -Headed
```

Then show evidence and close with the same narrative.
