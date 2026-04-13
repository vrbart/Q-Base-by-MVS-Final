# One Clear Run For Reviewers

This file is the shortest path to a real QB result with visible proof in terminal and files.

## 1) Start QB

```powershell
.\QB-doctor.bat -SkipQuantumChecks -SkipTokenValidation -OpenUi
```

Expected terminal proof:

- API health shows `200 OK`
- multi-instance endpoints (`runtime/apps/state/profile`) show `200 OK`
- lane health table appears

## 2) Do one obvious task in the UI

Open `http://127.0.0.1:11435/v3/ui` and run these three clicks in order:

1. `SYNC WORKSPACES`
2. `ROUTE ASK` with:
   - message: `-1 Build a login page and one to-do list feature`
   - task label: `login-todo-proof`
3. `OPTIMIZE` (keep max parallel = `3`)

Expected UI proof:

- `LAST ROUTE` is populated
- `OPTIMIZER DECISION` is populated
- token telemetry values change

## 3) Show proof outside the UI

Run:

```powershell
.\Q-algofest-proof.bat -SkipQuantumChecks -SkipTokenValidation -SkipTests
```

Then show the evidence file:

```powershell
Get-ChildItem .\dist\algofest\evidence\algofest_smoke_summary.json
Get-Content .\dist\algofest\evidence\algofest_smoke_summary.json
```

Expected terminal/file proof:

- `overall_ok: true`
- lane availability summary
- API health summary
- timestamped JSON artifact under `dist\algofest\evidence`

## What this proves

With one short run, reviewers can verify:

- QB starts cleanly
- QB routes a real task
- QB optimizes lane selection
- QB produces reproducible evidence artifacts

