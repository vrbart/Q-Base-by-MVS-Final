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

## 4. Implementation: Python Class Skeleton

### Feature Schema
```python
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
```

### Weights Schema
```python
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
```

### Linear Score Function
```python
def linear_score(task: TaskFeatures, w: SchedulerWeights) -> float:
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
    linear: Dict[str, float] = field(default_factory=dict)
    quadratic: Dict[Tuple[str, str], float] = field(default_factory=dict)
    offset: float = 0.0

def build_qubo(tasks, weights, choose_exactly_one=True, max_parallel=1, lambda_one=20.0, lambda_conflict=10.0, lambda_resource=10.0):
    # ...see quantum_select.py for full logic...
    pass
```

### Classical Fallback
```python
def brute_force_select_one(tasks, weights):
    # Returns best task by linear score
    pass
```

### Hybrid Selector
```python
class QuantumSelector:
    def __init__(self, weights: SchedulerWeights):
        self.weights = weights
    def solve(self, tasks: List[TaskFeatures], max_parallel: int = 1) -> Dict[str, Any]:
        # Classical fallback or Qiskit optimizer
        pass
```

### Decision Packet
```python
def make_decision_packet(selected, tasks, weights, solver_mode):
    # Returns explainable, auditable decision dict
    pass
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

## 10. VM Modal Rebuild (Step-by-Step)

This section defines the VM-aware modal strategy to run the orchestrator safely on multi-VM hosts.

### Step 1: Pick the VM modal

- `host_shared_model` (recommended): VMs run controllers/executors, host runs model inference.
- `guest_local_model`: each VM may run local inference (higher RAM/VRAM pressure).
- `api_only_remote`: VMs call remote model APIs; local inference disabled.

### Step 2: Set profile constraints

Use `VMModalProfile` in `DecisionConstraints`:

- `allowed_vm_lanes`: permitted VM lanes for this run.
- `max_vm_memory_mb_per_task`: hard cap to block oversized VM tasks.
- `prefer_host_inference`: when true, tasks marked `requires_guest_model=True` are filtered out.

### Step 3: Annotate tasks with VM metadata

Each `TaskDecisionInput` can carry:

- `vm_lane`
- `estimated_vm_memory_mb`
- `requires_guest_model`

### Step 4: Apply classical VM presolve gate

`policy_filter_tasks(...)` enforces modal constraints before optimization:

- blocks disallowed lanes
- blocks memory-over-cap tasks
- blocks guest-model-required tasks when host inference is preferred

### Step 5: Run bounded selection

After VM gate filtering:

1. build QUBO from feasible candidates
2. run `classical` / `qaoa` / `exact` / `auto`
3. run feasibility check again
4. export evidence manifest

### Step 6: Validate and iterate

- run `tests/test_quantum_decision_kernel.py`
- confirm VM modal filtering behavior
- review manifest `selected_task_set`, `rejected_tasks`, and `constraint_report`

---

## 11. Multi-Instance Optimized Lane Selection

`quantum_select.py` now supports bounded bundle selection (not just single-task picks):

- `QuantumSelector.solve(tasks, max_parallel=N)` selects up to `N` candidates.
- Classical feasibility remains enforced through pairwise conflict/resource checks.
- Objective remains weighted utility minus penalties, with optional synergy bonuses.

CCBS multi-instance integration uses this for tool-bundle selection:

- Capability frontier: discovered app candidates that support multi-instance operation.
- Presolve boundary: keep only feasible tool candidates.
- Bounded selector: choose best bundle for configured lane parallelism.
- Evidence packet: include selected bundle, solver mode, and score breakdown.
- Runtime lane routing supports directive prefixes (`-1`, `-2`, `-3`) and tracks active task ownership per lane.
- Token telemetry snapshots (daily/weekly/paid) are exposed for operator awareness on each routed ask.
