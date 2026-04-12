# Start Here

## 1. Create A Local Environment

```powershell
python -m venv .venv-clean
.\.venv-clean\Scripts\Activate.ps1
pip install -U pip
pip install -e .
```

## 2. Bring QB Up

Stable local path:

```powershell
.\QB-doctor.bat -SkipQuantumChecks -OpenUi
```

If you want strict secure-token validation later:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\set_qb_api_token.ps1
```

## 3. Record The Demo

```powershell
$env:CCBS_CODEX_INSTANCES_CONFIG = "config\codex_instances_10.json"
.\Q-demo-record.bat -OpenUi -SkipQuantumChecks -CaptureSeconds 150 -Headed
```

## 4. Run Submission Proof

```powershell
.\Q-algofest-proof.bat
```

## 5. Read The Submission Docs

- [`docs/algofest/SUBMISSION_PLAN.md`](docs/algofest/SUBMISSION_PLAN.md)
- [`docs/algofest/DEVPOST_WRITEUP_DRAFT.md`](docs/algofest/DEVPOST_WRITEUP_DRAFT.md)
- [`docs/algofest/VIDEO_SCRIPT_4M20S.md`](docs/algofest/VIDEO_SCRIPT_4M20S.md)
- [`docs/algofest/FINAL_QB_DEMO_VIDEO_SCRIPT_AUTOMATION_AI.md`](docs/algofest/FINAL_QB_DEMO_VIDEO_SCRIPT_AUTOMATION_AI.md)
