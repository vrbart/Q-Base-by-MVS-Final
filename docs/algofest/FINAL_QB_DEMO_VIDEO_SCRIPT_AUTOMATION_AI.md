# FINAL QB Demo Video Script (Canonical)

This is the single authoritative demo script for public use.

All other demo docs remain in the repo and point back to this file.

## 0) Public-Safe Inputs

Set these once in your shell (or pass them as command args):

```powershell
$env:CCBS_AZ_SUBSCRIPTION_ID = "<SUBSCRIPTION_ID>"
$env:CCBS_AZ_RESOURCE_GROUP = "<RESOURCE_GROUP>"
$env:CCBS_AZ_WORKSPACE_NAME = "<WORKSPACE_NAME>"
$env:CCBS_AZ_LOCATION = "eastus"
```

Never hardcode real tenant IDs, subscription IDs, emails, or bearer tokens in docs.

## 1) Scene Plan (Say / Do / Execute)

### Scene 1 - Clone + Setup

Say:
"This is a fresh clone and standard setup."

Do:
Open terminal and show clean repo checkout.

Execute:

```bash
git clone https://github.com/vrbart/Q-Base-by-MVS.git qb-demo
cd qb-demo
python -m venv .venv-clean
# Windows
.venv-clean\Scripts\activate
# macOS/Linux
# source .venv-clean/bin/activate
pip install -U pip
pip install -e .
```

### Scene 2 - Doctor + Bootstrap (Multi-Step Proof)

Say:
"Doctor returns the system to a working state and enables loopback owner auto-auth so the UI can run without pasting a bearer token."

Do:
Run the doctor wrapper with env-backed parameters.

Execute:

```powershell
# Optional (for a “10 lanes” shot without popping windows):
# $env:CCBS_CODEX_INSTANCES_CONFIG = "config\\codex_instances_10.json"

.\QB-doctor.bat -SubscriptionId $env:CCBS_AZ_SUBSCRIPTION_ID -ResourceGroup $env:CCBS_AZ_RESOURCE_GROUP -WorkspaceName $env:CCBS_AZ_WORKSPACE_NAME -Location $env:CCBS_AZ_LOCATION -OpenUi
```

Success criteria on screen:
- workspace state `Succeeded`
- workspace usable `Yes`
- lane availability `3/3`
- API health `200`
- UI loads without token paste (owner auto-auth enabled)

### Scene 3 - Automated UI Run + Capture (Refresh + Sync + Route + Optimize)

Say:
"Now we record a single take that performs multiple visible actions: Refresh, Sync Workspaces, Route Ask, Optimize, Evidence, and a live Git push. The overlay shows a running counter so you can see we complete **200** route/optimize actions."

Do:
Run prep, then the automation wrapper.

Execute:

```powershell
.\Q-demo-prep.bat -SkipTests
.\Q-demo-busy.bat -SubscriptionId $env:CCBS_AZ_SUBSCRIPTION_ID -ResourceGroup $env:CCBS_AZ_RESOURCE_GROUP -WorkspaceName $env:CCBS_AZ_WORKSPACE_NAME -Location $env:CCBS_AZ_LOCATION -OpenUi -Use10Lanes -IncludeGitPush -CaptureSeconds 260
```

What the recording will show (on-screen overlay):
- STEP 1/6 Refresh
- STEP 2/6 Sync Workspaces
- STEP 3/6 Route Ask (runs multiple cycles across -1/-2/-3 lanes)
- STEP 4/6 Optimize (runs multiple cycles with varying parallelism)
- STEP 5/6 Evidence (expands capability scan)
- STEP 6/6 Done (hold for readability while the busy driver also shows GitHub, VS Code, and terminals)

On-screen proof:
- overlay includes `tasks <N>/200` (route + optimize actions)
- `dist/demo/qb_demo_steps.json` records every action with timestamps

### Scene 4 - Evidence Check (Artifacts are real)

Say:
"This run is evidence-backed, not just a UI click-through."

Do:
Show generated artifacts.

Execute:

```powershell
Get-ChildItem .\dist\demo
Get-ChildItem .\dist\algofest\evidence
Get-ChildItem .\.ccbs\quantum\runs -ErrorAction SilentlyContinue
Get-Content .\dist\algofest\evidence\algofest_smoke_summary.json
```

Expected artifacts:
- `dist/demo/qb_demo_capture.webm`
- `dist/demo/qb_demo_start.png`
- `dist/demo/qb_demo_end.png`
- `dist/algofest/evidence/algofest_smoke_summary.json`

Optional GitHub “200 tasks” prop (single issue, not spam):
- Use the issue template `.github/ISSUE_TEMPLATE/algofest-demo-200-tasks.md`, or copy [`docs/DEMO_TASKLIST_200.md`](docs/DEMO_TASKLIST_200.md) into a single GitHub issue body to get a visible `0/200` counter.
- The busy demo driver can also create a small video-linked publish commit on camera with `-IncludeGitPush`.

### Scene 5 - Optional Quantum Preflight (fast only)

Say:
"Quantum is optional. For the demo we only show target availability; QB can fall back to classical planning."

Do:
Run a quick target list (no long jobs).

Execute:

```powershell
az quantum target list -o table
```

### Optional GitHub App Segment (30-45s, only if already created)

Say:
"QB is designed to surface-adapt into external systems. Here is the GitHub App we use for future webhook/OAuth integrations."

Do:
Open the GitHub App settings page, but do not show secrets.

Execute (opens browser to the app list, or direct slug if provided):

```powershell
.\Q-demo-github.bat
# or
.\Q-demo-github.bat -AppSlug "<your-app-slug>"
```

### Scene 6 - Close

Say:
"What you watched was executed and recorded by QB with reproducible evidence."

Do:
Hold final state for 3-5 seconds, then fade out.

## 2) Timing (Target 4:20)

- `0:00-0:30` Problem and value
- `0:30-1:20` Architecture and lane model
- `1:20-2:30` Doctor/bootstrap proof
- `2:30-3:40` Automated UI run
- `3:40-4:20` Evidence review and close

## 3) No-Overclaim Rules

- Quantum is optional and may fall back to classical.
- This is a polished prototype, not a production SLA claim.
- Do not claim real hardware quantum execution unless shown.

## 4) Troubleshooting (Non-Destructive)

- Missing token provider:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\set_qb_api_token.ps1 -Mode command -TokenCommand "<cmd>"
```

- Re-run doctor:

```powershell
.\QB-doctor.bat -SubscriptionId $env:CCBS_AZ_SUBSCRIPTION_ID -ResourceGroup $env:CCBS_AZ_RESOURCE_GROUP -WorkspaceName $env:CCBS_AZ_WORKSPACE_NAME -Location $env:CCBS_AZ_LOCATION -OpenUi
```

- Skip lane relaunch (prevent extra windows):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\qb_quantum_multi_instance.ps1 -SubscriptionId $env:CCBS_AZ_SUBSCRIPTION_ID -ResourceGroup $env:CCBS_AZ_RESOURCE_GROUP -WorkspaceName $env:CCBS_AZ_WORKSPACE_NAME -Location $env:CCBS_AZ_LOCATION -SkipLaneLaunch -OpenUi
```
