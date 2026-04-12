# Q-Base by MVS

Q-Base (QB) is a local-first orchestration runtime for multi-agent task routing, evidence capture, and optional Azure Quantum-backed scheduling.

This repository is the minimal curated public submission surface. It keeps the root small and leaves the deeper implementation under `src/`, `scripts/`, `config/`, `automation/`, and `docs/`.

## What Is Included

- Core runtime: `src/ccbs_app`
- Demo automation: `automation/`, `Q-demo-record.bat`
- Doctor/bootstrap flow: `QB-doctor.bat`, `scripts/qb_doctor.ps1`
- Proof/validation: `Q-algofest-proof.bat`, `scripts/algofest_submission_smoke.ps1`
- Multi-instance lane manager: `scripts/codex_multi_manager.ps1`
- Minimal public docs and submission assets: `docs/`

## Quick Start

```powershell
python -m venv .venv-clean
.\.venv-clean\Scripts\Activate.ps1
pip install -U pip
pip install -e .
```

Run the local-first doctor flow:

```powershell
.\QB-doctor.bat -SkipQuantumChecks -OpenUi
```

Record the demo:

```powershell
$env:CCBS_CODEX_INSTANCES_CONFIG = "config\codex_instances_10.json"
.\Q-demo-record.bat -OpenUi -SkipQuantumChecks -CaptureSeconds 150 -Headed
```

Run the proof script:

```powershell
.\Q-algofest-proof.bat
```

## Key Docs

- Start guide: [`START_HERE.md`](START_HERE.md)
- Impact note: [`docs/IMPACT_ONE_PAGER.md`](docs/IMPACT_ONE_PAGER.md)
- OBS capture guide: [`docs/VIDEO_RECORDING_OBS.md`](docs/VIDEO_RECORDING_OBS.md)
- Submission plan: [`docs/algofest/SUBMISSION_PLAN.md`](docs/algofest/SUBMISSION_PLAN.md)
- Demo script: [`docs/algofest/FINAL_QB_DEMO_VIDEO_SCRIPT_AUTOMATION_AI.md`](docs/algofest/FINAL_QB_DEMO_VIDEO_SCRIPT_AUTOMATION_AI.md)

## Notes

- Azure Quantum is optional. Use `-SkipQuantumChecks` for the stable local demo path.
- Loopback owner auto-auth is supported for local demos.
- Strict token-provider validation can be enabled later with `scripts/set_qb_api_token.ps1`.
