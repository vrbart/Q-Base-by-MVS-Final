# Recording The “Split Screen” Demo (VS Code + QB UI) With OBS

Goal: capture a clean, judge-friendly video that looks like the screenshot: **VS Code on the left**, **Q-Base UI on the right**, with visible multi-step activity and no secret leakage.

## 1) OBS Setup (Fast + Reliable)

1. Install OBS Studio.
2. Create one scene: **Display Capture** (full desktop).
3. Settings:
   - Output: `mkv` while recording (OBS can remux to `mp4` after).
   - Resolution: 1920x1080
   - FPS: 30
   - Bitrate: 6000–9000 kbps
4. Optional: add a mic track for live narration.

## 2) Arrange Windows (Like The Screenshot)

1. Open VS Code with this repo.
2. Open QB UI: `http://127.0.0.1:11435/v3/ui`
3. Tile:
   - VS Code: left half
   - Browser (QB UI): right half
4. Optional (for “GitHub 200 tasks” counter): open a GitHub issue created from:
   - `.github/ISSUE_TEMPLATE/algofest-demo-200-tasks.md`
   - or paste [`docs/DEMO_TASKLIST_200.md`](DEMO_TASKLIST_200.md) into a single issue body

## 3) Run The Demo Driver (Busy, But Real)

Start OBS recording, then run:

```powershell
$env:CCBS_CODEX_INSTANCES_CONFIG = "config\codex_instances_10.json"
.\Q-demo-record.bat -OpenUi -SkipQuantumChecks -SkipTokenValidation -CaptureSeconds 260 -Headed
```

What it does:
- Runs `QB-doctor` (bootstraps, enables owner auto-auth, opens UI)
- Opens the QB multi-instance deck page
- Runs `Q-demo-record.bat` (Playwright-driven UI actions with `tasks N/200` overlay)
- Uses the 10-lane Codex config when `CCBS_CODEX_INSTANCES_CONFIG` is set
- Writes capture output under `dist/demo/`

If you want the system to keep cycling between windows for a longer raw recording (you can cut later):

```powershell
$env:CCBS_CODEX_INSTANCES_CONFIG = "config\codex_instances_10.json"
.\Q-demo-record.bat -OpenUi -SkipQuantumChecks -SkipTokenValidation -CaptureSeconds 1200 -Headed
```

## 4) Don’t Leak Secrets

- Do **not** open any screens showing tokens, private keys, webhook secrets, or password manager entries.
- QB UI bearer token field can stay empty after running `QB-doctor.bat -OpenUi` (loopback owner auto-auth).
- If you do paste a bearer token: it is stored in the browser only, but you still should not show it on camera.
