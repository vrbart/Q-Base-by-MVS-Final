# Q-Base by CCBS (QB) Quantum Decision Engine: Codex Reference

## Overview
This document summarizes the architecture, value model, and implementation for **Q-Base by CCBS** (short form: **QB**), the CCBS hybrid quantum-classical task orchestration engine. It is designed for direct use by Codex, agents, and developers integrating or extending the decision engine.

---

## 1. Architecture: Classical-Quantum Boundary

- **Classical (always):**
  - Dependency graph (DAG) construction
  - Ready-task (frontier) extraction
  - Feasibility, resource, and policy checks
  - Critical-path and topological ordering
  - Deterministic execution and evidence export

- **Quantum/Hybrid (only):**
  - Selecting the best bundle from the ready frontier
  - Trading off cost, time, risk, and information gain in one objective
  - Resolving conflicts among feasible candidates

**Design Rule:** Quantum/hybrid optimizer only chooses among already-feasible candidates. All legality and dependency logic remains classical.

---

## 2. Value Model: Feature Grouping

- **Static (recompute only if graph changes):**
  - `goal_impact`: Importance for project goal
  - `unlock_value`: How many downstream tasks become reachable
  - `critical_path`: Contribution to project finish time
  - `baseline duration_cost`, `baseline switch_cost`

- **Semi-static (recompute on state change):**
  - `information_gain`: Value of reducing uncertainty
  - `parallelization_gain`: Immediate concurrency enabled
  - `risk_penalty`: Anticipated risk

- **Dynamic (update every cycle):**
  - `retry_penalty`: Penalty for repeated failures
  - `observed duration deltas`, `failure history`
  - `current tool/environment context`, `resource pressure`

---

## 3. Objective Function (QUBO Formulation)

For each ready task $i$ (binary variable $x_i \in \{0,1\}$):

$$
\max \sum_i x_i (w_g \cdot goal\_impact_i + w_u \cdot unlock\_value_i + w_c \cdot critical\_path_i + w_i \cdot information\_gain_i + w_p \cdot parallelization\_gain_i - w_d \cdot duration\_cost_i - w_s \cdot switch\_cost_i - w_r \cdot risk\_penalty_i - w_t \cdot retry\_penalty_i)
$$

**Constraints:**
- Unsatisfied dependencies (classical)
- Resource caps, mutual exclusion, tool/env conflicts, approval gates, max concurrency (QUBO penalties)

---

## 4. Implementation: Python Class Skeletons and Logic

### Feature Schema, Weights, and Weighted Score
```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any

@dataclass
class TaskFeatures:
    task_id: str
    name: str
    goal_impact: float
    unlock_value: float
    critical_path: float
    information_gain: float
    parallelization_gain: float
    duration_cost: float
    switch_cost: float
    risk_penalty: float
    retry_penalty: float
    required_resources: Set[str] = field(default_factory=set)
    tool_group: Optional[str] = None
    environment_group: Optional[str] = None
    conflicts_with: Set[str] = field(default_factory=set)
    synergy_with: Dict[str, float] = field(default_factory=dict)

@dataclass
class SchedulerWeights:
    goal_impact: float = 5.0
    unlock_value: float = 3.0
    critical_path: float = 4.0
    information_gain: float = 2.0
    parallelization_gain: float = 2.0
    duration_cost: float = 2.0
    switch_cost: float = 1.0
    risk_penalty: float = 2.0
    retry_penalty: float = 1.0

def weighted_score(task: TaskFeatures, w: SchedulerWeights) -> float:
    return (
        w.goal_impact * task.goal_impact
        + w.unlock_value * task.unlock_value
        + w.critical_path * task.critical_path
        + w.information_gain * task.information_gain
        + w.parallelization_gain * task.parallelization_gain
        - w.duration_cost * task.duration_cost
        - w.switch_cost * task.switch_cost
        - w.risk_penalty * task.risk_penalty
        - w.retry_penalty * task.retry_penalty
    )
```

### QUBO Model & Builder
```python
@dataclass
class QUBOModel:
    bias: Dict[str, float] = field(default_factory=dict)
    quadratic: Dict[Tuple[str, str], float] = field(default_factory=dict)
    offset: float = 0.0

def add_quadratic(qubo: QUBOModel, a: str, b: str, value: float) -> None:
    key = tuple(sorted((a, b)))
    qubo.quadratic[key] = qubo.quadratic.get(key, 0.0) + value

def build_qubo(
    tasks: List[TaskFeatures],
    weights: SchedulerWeights,
    *,
    choose_exactly_one: bool = True,
    max_parallel: int = 1,
    lambda_one: float = 20.0,
    lambda_conflict: float = 10.0,
    lambda_resource: float = 10.0,
) -> QUBOModel:
    qubo = QUBOModel()
    ids = [t.task_id for t in tasks]
    task_map = {t.task_id: t for t in tasks}
    # Bias terms: QUBO is usually minimized, so negate reward.
    for task in tasks:
        score = weighted_score(task, weights)
        qubo.bias[task.task_id] = qubo.bias.get(task.task_id, 0.0) - score
    # Pairwise conflicts
    for i, task_i in enumerate(tasks):
        for j in range(i + 1, len(tasks)):
            task_j = tasks[j]
            # Explicit conflict
            if task_j.task_id in task_i.conflicts_with or task_i.task_id in task_j.conflicts_with:
                add_quadratic(qubo, task_i.task_id, task_j.task_id, lambda_conflict)
            # Resource overlap conflict
            if task_i.required_resources & task_j.required_resources:
                add_quadratic(qubo, task_i.task_id, task_j.task_id, lambda_resource)
            # Optional positive synergy
            synergy = task_i.synergy_with.get(task_j.task_id, 0.0) + task_j.synergy_with.get(task_i.task_id, 0.0)
            if synergy:
                add_quadratic(qubo, task_i.task_id, task_j.task_id, -synergy)
    # Exactly-one constraint: lambda * (sum x_i - 1)^2
    if choose_exactly_one:
        qubo.offset += lambda_one
        for task_id in ids:
            # x_i^2 = x_i for binary variables
            qubo.bias[task_id] = qubo.bias.get(task_id, 0.0) - lambda_one
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                add_quadratic(qubo, ids[i], ids[j], 2.0 * lambda_one)
    return qubo
```

### Classical Fallback
```python
def brute_force_select_one(tasks: List[TaskFeatures], weights: SchedulerWeights) -> Dict:
    if not tasks:
        return {"selected": [], "score": None}
    best_task = None
    best_score = float("-inf")
    for task in tasks:
        score = weighted_score(task, weights)
        if score > best_score:
            best_score = score
            best_task = task
    return {
        "selected": [best_task.task_id] if best_task else [],
        "score": best_score,
        "solver_mode": "classical_fallback",
    }
```

### Hybrid Selector
```python
class QuantumSelector:
    def __init__(self, weights: SchedulerWeights):
        self.weights = weights
    def solve(self, tasks: List[TaskFeatures], max_parallel: int = 1) -> Dict[str, Any]:
        if not tasks:
            return {
                "selected_tasks": [],
                "solver_mode": "none",
                "reason": "empty frontier",
            }
        # For now: classical fallback. Replace with Qiskit optimizer as needed.
        result = brute_force_select_one(tasks, self.weights)
        return {
            "selected_tasks": result["selected"],
            "solver_mode": result["solver_mode"],
            "objective_score": result["score"],
        }
```

### Decision Packet
```python
def make_decision_packet(selected: List[str], tasks: List[TaskFeatures], weights: SchedulerWeights, solver_mode: str) -> dict:
    task_map = {t.task_id: t for t in tasks}
    breakdown = {}
    for task_id in selected:
        task = task_map[task_id]
        breakdown[task_id] = {
            "goal_impact": task.goal_impact,
            "unlock_value": task.unlock_value,
            "critical_path": task.critical_path,
            "information_gain": task.information_gain,
            "parallelization_gain": task.parallelization_gain,
            "duration_cost": task.duration_cost,
            "switch_cost": task.switch_cost,
            "risk_penalty": task.risk_penalty,
            "retry_penalty": task.retry_penalty,
            "weighted_score": weighted_score(task, weights),
        }
    return {
        "selected_tasks": selected,
        "solver_mode": solver_mode,
        "score_breakdown": breakdown,
        "classical_feasibility_check": "pending",
    }
```

### Example Update Rules
```python
def update_retry_penalty(attempts: int, max_retries: int) -> float:
    if max_retries <= 0:
        return 1.0
    return min(attempts / max_retries, 1.0)

def update_switch_cost(task_tool_group: str, current_tool_group: Optional[str]) -> float:
    if current_tool_group is None:
        return 0.0
    return 0.0 if task_tool_group == current_tool_group else 1.0

def decay_information_gain(base_information_gain: float, evidence_seen: bool) -> float:
    return 0.0 if evidence_seen else base_information_gain
```

---

## 5. Runtime Flow

1. **Frontier extraction:**
   - `ready_tasks = frontier_get_ready_tasks(state)`
2. **Classical presolve:**
   - `candidate_tasks = classical_presolve(ready_tasks, state)`
3. **Hybrid selection:**
   - `selection = selector.solve(candidate_tasks, max_parallel=1)`
4. **Decision packet:**
   - `decision = make_decision_packet(...)`
5. **Feasibility check:**
   - `validated = classical_feasibility_check(decision, state)`
6. **Dispatch:**
   - `dispatch(validated)`

---

## 6. Decision Packet Example
```json
{
  "selected_tasks": ["task_7", "task_11"],
  "solver_mode": "hybrid_qaoa",
  "frontier_size": 9,
  "objective_score": 12.48,
  "score_breakdown": {
    "goal_impact": 4.2,
    "unlock_value": 2.1,
    "critical_path": 3.4,
    "information_gain": 1.3,
    "parallelization_gain": 2.0,
    "duration_cost": -0.8,
    "switch_cost": -0.3,
    "risk_penalty": -0.9,
    "retry_penalty": -0.5
  },
  "rejected_due_to_constraints": ["task_3", "task_8"],
  "classical_feasibility_check": "passed",
  "next_actions": ["dispatch", "capture_evidence"]
}
```

---

## 7. Key Design Rule

> **Quantum chooses among feasible candidates. It does not replace feasibility logic.**

This boundary is essential for speed, explainability, and technical credibility.

---

## 8. File Location
- Main implementation: `src/ccbs_app/planner/quantum_select.py`
- Integrate with orchestrator via frontier, presolver, and feasibility modules.

---

## 9. References
- Qiskit Optimization: https://qiskit.org/documentation/optimization/
- QAOA: https://qiskit.org/documentation/optimization/tutorials/06_examples_max_cut_and_tsp.html
- CCBS Clean-Core: See repo and README for product boundaries.

---

**For further integration, see quantum_select.py and orchestrator entry points.**

---

## 10. CCBS-Only Buildathon Proof Plan

### Summary
- Remove third-party planning and design connectors from scope entirely, now and going forward.
- Keep `CCBS` as the sole planning and execution authority.
- Preserve the current classical DAG/frontier/feasibility flow with bounded ready-set optimization.
- Generate repeatable proof-of-development artifacts for submission and review.

### Key Implementation Changes
- Remove connector references from config, feature flags, task catalogs, and documentation.
- Standardize internal entities only:
  - `WorkItem`
  - `DecisionPacket`
  - `ExecutionCheckpoint`
  - `EvidenceRecord`
- Keep execution pipeline:
  - intake -> DAG build -> ready frontier -> classical presolve -> bounded selector -> feasibility check -> dispatch -> evidence capture
- Add an evidence export pipeline that emits:
  - decision logs
  - transition timeline
  - execution results
  - validation output
  - artifact manifest
- Keep external publishing optional and one-way only, never authoritative.

### Canonical Public Interfaces
- `POST /work-items`
- `GET /work-items`
- `POST /scheduler/select-next`
- `POST /checkpoints/record`
- `GET /evidence/export`

### Canonical Buildathon Deliverables
- architecture summary
- run trace timeline
- decision packet bundle
- test and validation report
- final evidence manifest

---

## 11. VM Modal Rebuild (Step-by-Step)

This section defines the VM accommodation path for the orchestrator while preserving the classical/quantum boundary.

1. Define the active VM modal profile per run.
2. Apply policy gating before selection:
   - allowed VM lanes
   - per-task VM memory ceiling
   - host-inference preference for tasks that otherwise require guest-side inference
3. Build the ready frontier classically from dependency-complete tasks only.
4. Run classical presolve to shrink candidate set (`top_k` and conflict pruning).
5. Run bounded selection on the reduced ready set.
6. Re-check feasibility classically on selected output.
7. Dispatch deterministically and capture evidence artifacts.
8. Record `ExecutionCheckpoint` entries for each transition.
9. Export evidence bundle for review and submission.

### VM Modal Data Contract Additions
- `vm_lane`
- `estimated_vm_memory_mb`
- `requires_guest_model`
- `vm_profile` on `DecisionConstraints`

### VM Modal Objective Guardrails
- Keep dependency validity and readiness outside the optimizer.
- Use the selector only for already-feasible candidates.
- Penalize cross-lane conflict and over-capacity combinations.
- Enforce deterministic post-selection feasibility checks.

---

## 12. Test and Validation Plan

1. Confirm no runtime dependency on removed third-party planning/design connectors.
2. Regression test orchestration flow:
   - dependency validity
   - ready-frontier selection
   - post-selection feasibility enforcement
3. Validate evidence exports are complete and deterministic across repeated runs.
4. Validate end-to-end run from intake to final evidence manifest.
5. Validate VM modal profile gates:
   - disallowed lane filtering
   - memory cap filtering
   - host-inference preference filtering

---

## 13. Assumptions

- `CCBS` remains the single source of truth.
- Proof artifacts are generated entirely from internal system state and execution evidence.
- External systems are publish-only outputs when used.

---

## 14. Implementation Step Log

1. Updated canonical orchestrator reference document with CCBS-only scope and artifact contract.
2. Added VM modal rebuild steps aligned to current policy + bounded selector flow.
3. Added explicit API surface, test plan, and assumptions for buildathon proof submission.
4. Regenerated `.docx` from this markdown to keep presentation output synchronized.
5. Removed the deprecated tool names from this full orchestrator reference document.
6. Regenerated `.docx` again after the naming compliance pass.
7. Re-ran quantum decision kernel tests to confirm behavior remains stable.

### Packaging Milestones (A-D)

- A. Packaging scope and exclusion filters finalized. (complete)
- B. Single-source packaging script implemented. (complete)
- C. Packaging dry run and validation. (complete)
- D. Final canonical artifact generation. (complete)

### Packaging Execution Notes

1. Added `scripts/buildathon_package.py` as the single packaging authority.
2. Added one command entrypoint in VS Code tasks:
   - `Ops Core: Buildathon Migration One-File`
3. Migration one-file mode is now canonical:
   - `python3 scripts/buildathon_package.py --migration-onefile`
4. Generated root artifact:
   - `CCBS_MIGRATION_ONEFILE.zip`
5. Embedded migration payload inside the zip:
   - `migration/manifest.json`
   - `migration/restore_instructions.md`
   - `migration/backend_policy_snapshot.json`
6. Azure-first sprint backend policy preserved with IBM fallback:
   - backend priority: `azure -> ibm -> classical`
   - `primary_backend`, `executed_backend`, `fallback_used`, `fallback_reason` captured in quantum evidence
7. Validation checks completed:
   - required anchor paths present in zip
   - excluded runtime/bulk paths absent from zip
   - deterministic membership hash stable across two consecutive runs
8. Added provider-aware quantum execution CLI surface:
   - `quantum run --provider azure|ibm --batch <file> --mode auto|qaoa|exact --json`
   - `quantum monitor --run-id <id> --json`
   - `quantum collect --run-id <id> --output <path> --json`
9. Added batch schema support (`tasks`, `constraints`, `weights`, `provider_options`) and retry policy knobs:
   - `max_retries`
   - `timeout_budget_seconds`
   - `failover_enabled`
10. Added local run-store contract under `.ccbs/quantum/runs/<run_id>/` with deterministic artifacts:
   - `run_record.json`
   - `decision_manifest.json`
   - `decision_manifest.md`
11. Added hybrid GitHub workflow model:
   - offline-safe regression CI (`.github/workflows/ccbs-quantum-regression.yml`)
   - manual cloud-prep dispatch (`.github/workflows/ccbs-quantum-manual-cloud-prep.yml`)
12. Added baseline batch fixture for manual operator flows:
   - `quantum/batches/sample_batch.json`
13. Re-ran contract tests for routing + quantum kernel + quantum CLI execution.
14. Added explicit fallback-chain tests:
   - forced Azure failure -> IBM recovery
   - forced IBM failure -> classical recovery

### Azure Sprint Events (April 10-15, 2026)

1. Event 1 (Apr 10): Azure preflight baseline + IBM regression baseline.
2. Event 2 (Apr 11): Azure solve integration with classical feasibility boundary.
3. Event 3 (Apr 12): Azure policy default in sprint mode + fallback checks.
4. Event 4 (Apr 13): Evidence schema hardening and deterministic run checks.
5. Event 5 (Apr 14): One-file migration packaging finalized and validated.
6. Event 6 (Apr 15): Release candidate migration package + handoff proof set.

---

## 15. Multi-Instance Optimized Lane Selection

The quantum-ready selector now supports bounded bundle selection for CCBS lane tooling:

- `QuantumSelector.solve(tasks, max_parallel=N)` can pick up to `N` feasible candidates.
- Conflict/resource constraints remain classical and deterministic.
- Utility/penalty scoring still follows the same weighted objective with pairwise synergy support.

Multi-instance control integration uses this path:

1. Discover app capability frontier from internal catalog.
2. Keep only feasible multi-instance candidates.
3. Run bounded selector for desired lane count.
4. Emit decision packet with `selected_tasks`, `solver_mode`, `objective_score`, and feature breakdown.
5. Route asks using lane directives (`-1`, `-2`, `-3`) or profile fallback strategy.
6. Capture lane ownership + active task runtime view and token telemetry snapshots (daily/weekly/paid).
