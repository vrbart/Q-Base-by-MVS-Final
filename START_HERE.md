# Start Here

## 0. What You Need

Required:

- Windows with PowerShell
- Git
- Python 3.10+
- Node.js 18+ and `npm`

Optional:

- Azure CLI + Azure Quantum extension for live quantum checks
- Codex CLI for Codex-backed lane launches

Stable public demo path:

- no Azure Quantum setup required
- no bearer token setup required if you use local owner auto-auth

## 1. Clone The Repo

```powershell
git clone https://github.com/vrbart/Q-Base-by-MVS-Final.git
cd Q-Base-by-MVS-Final
```

## 2. Create A Local Environment

```powershell
python -m venv .venv-clean
.\.venv-clean\Scripts\Activate.ps1
pip install -U pip
pip install -e .
```

## 3. Bring QB Up

Stable local path:

```powershell
.\QB-doctor.bat -SkipQuantumChecks -SkipTokenValidation -OpenUi
```

If you want strict secure-token validation later:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\set_qb_api_token.ps1
```

## 4. Record The Demo

```powershell
$env:CCBS_CODEX_INSTANCES_CONFIG = "config\codex_instances_10.json"
.\Q-demo-record.bat -SkipDoctor -CaptureSeconds 150 -Headed
```

## 5. Run Submission Proof

```powershell
.\Q-algofest-proof.bat
```

## 6. Read The Submission Docs

- [`docs/algofest/SUBMISSION_PLAN.md`](docs/algofest/SUBMISSION_PLAN.md)
- [`docs/algofest/DEVPOST_WRITEUP_DRAFT.md`](docs/algofest/DEVPOST_WRITEUP_DRAFT.md)
- [`docs/algofest/VIDEO_SCRIPT_4M20S.md`](docs/algofest/VIDEO_SCRIPT_4M20S.md)
- [`docs/algofest/FINAL_QB_DEMO_VIDEO_SCRIPT_AUTOMATION_AI.md`](docs/algofest/FINAL_QB_DEMO_VIDEO_SCRIPT_AUTOMATION_AI.md)
