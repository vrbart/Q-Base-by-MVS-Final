# AlgoFest Demo Script (Target 4:20)

Canonical consolidated demo guide: [`../../DEMO_ONEFILE.md`](../../DEMO_ONEFILE.md)

Target duration: **4:20**  
Allowed range: **2:00-5:00**

## 0:00-0:30 Problem + Value
Narration:
"Engineering teams struggle when multi-step work is routed manually across tools. QB solves that with local-first orchestration, deterministic lane routing, and reproducible evidence output."

Show:
- Project title splash.
- One architecture visual with lanes + control plane.

## 0:30-1:25 Architecture + Optimization Flow
Narration:
"QB runs a three-lane execution model. Requests are normalized, routed, and assigned with policy-aware logic. Runtime health is continuously verifiable."

Show:
- QB UI and lane panel.
- Brief code glimpse of routing/orchestration files.

## 1:25-2:45 Live System Proof
Narration:
"Now we run the one-command proof path to verify the system is healthy and ready."

Run:

```powershell
.\Q-algofest-proof.bat
```

Show:
- Doctor pass success.
- API healthy result.
- Lane availability `3/3`.

## 2:45-3:45 Orchestration Evidence
Narration:
"This is not just a static UI. We can show assignment and runtime evidence from the same run."

Show:
- Multi-instance status output.
- Evidence JSON path and key fields.
- One task-routing example in UI.

## 3:45-4:10 Quantum Extension Lane
Narration:
"QB is local-first by design. Azure Quantum is integrated as an optional extension lane for advanced selection workflows."

Show:
- Workspace status `Succeeded` / `usable Yes`.
- Target list snapshot.

## 4:10-4:20 Close
Narration:
"QB demonstrates algorithmic orchestration with practical, reproducible execution. Judges can clone, run, and verify in minutes."

Show:
- Final callout: repo link + quickstart path.
