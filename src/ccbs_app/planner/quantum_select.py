from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class TaskFeatures:
    task_id: str
    name: str
    # Static / semi-static normalized features: 0.0 -> 1.0
    goal_impact: float
    unlock_value: float
    critical_path: float
    information_gain: float
    parallelization_gain: float
    # Costs / penalties normalized: 0.0 -> 1.0
    duration_cost: float
    switch_cost: float
    risk_penalty: float
    retry_penalty: float
    # Optional metadata
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


@dataclass
class QUBOModel:
    linear: Dict[str, float] = field(default_factory=dict)
    quadratic: Dict[Tuple[str, str], float] = field(default_factory=dict)
    offset: float = 0.0


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
    lambda_cap: float = 8.0,
) -> QUBOModel:
    qubo = QUBOModel()
    ids = [t.task_id for t in tasks]

    # Linear terms: QUBO minimization uses negated reward.
    for task in tasks:
        qubo.linear[task.task_id] = qubo.linear.get(task.task_id, 0.0) - linear_score(task, weights)

    # Pairwise conflicts / synergy.
    for i, task_i in enumerate(tasks):
        for j in range(i + 1, len(tasks)):
            task_j = tasks[j]
            if task_j.task_id in task_i.conflicts_with or task_i.task_id in task_j.conflicts_with:
                add_quadratic(qubo, task_i.task_id, task_j.task_id, lambda_conflict)
            if task_i.required_resources & task_j.required_resources:
                add_quadratic(qubo, task_i.task_id, task_j.task_id, lambda_resource)
            synergy = task_i.synergy_with.get(task_j.task_id, 0.0) + task_j.synergy_with.get(task_i.task_id, 0.0)
            if synergy:
                add_quadratic(qubo, task_i.task_id, task_j.task_id, -synergy)

    # Cardinality constraints via penalties.
    if choose_exactly_one:
        qubo.offset += lambda_one
        for task_id in ids:
            qubo.linear[task_id] = qubo.linear.get(task_id, 0.0) - lambda_one
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                add_quadratic(qubo, ids[i], ids[j], 2.0 * lambda_one)
    elif max_parallel > 0:
        # Soft cap penalty encouraging <= max_parallel.
        for task_id in ids:
            qubo.linear[task_id] = qubo.linear.get(task_id, 0.0) - lambda_cap * (2.0 * max_parallel - 1.0)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                add_quadratic(qubo, ids[i], ids[j], 2.0 * lambda_cap)

    return qubo


def _pair_penalty(a: TaskFeatures, b: TaskFeatures) -> float:
    penalty = 0.0
    if b.task_id in a.conflicts_with or a.task_id in b.conflicts_with:
        penalty += 1000.0
    if a.required_resources & b.required_resources:
        penalty += 1000.0
    synergy = a.synergy_with.get(b.task_id, 0.0) + b.synergy_with.get(a.task_id, 0.0)
    penalty -= synergy
    return penalty


def _subset_feasible(subset: List[TaskFeatures], *, choose_exactly_one: bool, max_parallel: int) -> bool:
    size = len(subset)
    if choose_exactly_one and size != 1:
        return False
    if not choose_exactly_one and size > max_parallel:
        return False
    for i in range(size):
        for j in range(i + 1, size):
            if _pair_penalty(subset[i], subset[j]) >= 1000.0:
                return False
    return True


def _subset_objective(subset: List[TaskFeatures], weights: SchedulerWeights) -> float:
    total = sum(linear_score(task, weights) for task in subset)
    for i in range(len(subset)):
        for j in range(i + 1, len(subset)):
            total -= _pair_penalty(subset[i], subset[j])
    return total


def brute_force_select(
    tasks: List[TaskFeatures],
    weights: SchedulerWeights,
    *,
    choose_exactly_one: bool = True,
    max_parallel: int = 1,
) -> Dict[str, Any]:
    if not tasks:
        return {"selected": [], "score": None, "solver_mode": "classical_empty"}

    safe_parallel = max(1, int(max_parallel))
    best_subset: List[TaskFeatures] = []
    best_score = float("-inf")

    if choose_exactly_one:
        sizes = [1]
    else:
        sizes = list(range(1, min(safe_parallel, len(tasks)) + 1))

    for size in sizes:
        for combo in combinations(tasks, size):
            subset = list(combo)
            if not _subset_feasible(subset, choose_exactly_one=choose_exactly_one, max_parallel=safe_parallel):
                continue
            score = _subset_objective(subset, weights)
            if score > best_score:
                best_score = score
                best_subset = subset

    return {
        "selected": [task.task_id for task in best_subset],
        "score": best_score if best_subset else None,
        "solver_mode": "classical_bruteforce_bundle",
    }


def brute_force_select_one(tasks: List[TaskFeatures], weights: SchedulerWeights) -> Dict[str, Any]:
    return brute_force_select(tasks, weights, choose_exactly_one=True, max_parallel=1)


class QuantumSelector:
    def __init__(self, weights: SchedulerWeights):
        self.weights = weights

    def solve(self, tasks: List[TaskFeatures], max_parallel: int = 1) -> Dict[str, Any]:
        if not tasks:
            return {
                "selected_tasks": [],
                "solver_mode": "none",
                "objective_score": None,
                "reason": "empty frontier",
            }

        safe_parallel = max(1, int(max_parallel))
        choose_exactly_one = safe_parallel <= 1
        result = brute_force_select(
            tasks,
            self.weights,
            choose_exactly_one=choose_exactly_one,
            max_parallel=safe_parallel,
        )
        return {
            "selected_tasks": list(result.get("selected", [])),
            "solver_mode": str(result.get("solver_mode", "classical_bruteforce_bundle")),
            "objective_score": result.get("score"),
        }


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
            "linear_score": linear_score(task, weights),
        }
    return {
        "selected_tasks": selected,
        "solver_mode": solver_mode,
        "score_breakdown": breakdown,
        "classical_feasibility_check": "pending",
    }


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

