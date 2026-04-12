"""Shared role-evolution thresholds and helpers for Smiles cards."""

from __future__ import annotations

from typing import Any

# Ordered from earliest to latest stage.
STAGES: list[dict[str, Any]] = [
    {
        "index": 0,
        "name": "scribble_1",
        "label": "Scribble I",
        "min_xp": 0,
        "variant_rank": 0,
        "aliases": ["l0", "s0", "scribble_1", "scribble1", "sketch", "sketch_1", "stage0"],
    },
    {
        "index": 1,
        "name": "scribble_2",
        "label": "Scribble II",
        "min_xp": 2,
        "variant_rank": 0,
        "aliases": ["l1", "s1", "scribble_2", "scribble2", "sketch_2", "stage1"],
    },
    {
        "index": 2,
        "name": "base",
        "label": "Base",
        "min_xp": 5,
        "variant_rank": 1,
        "aliases": ["l2", "s2", "a", "base", "stage2"],
    },
    {
        "index": 3,
        "name": "evolved",
        "label": "Evolved",
        "min_xp": 12,
        "variant_rank": 2,
        "aliases": ["l3", "s3", "b", "evolved", "stage3"],
    },
    {
        "index": 4,
        "name": "elite",
        "label": "Elite",
        "min_xp": 24,
        "variant_rank": 3,
        "aliases": ["l4", "s4", "c", "elite", "stage4"],
    },
    {
        "index": 5,
        "name": "rare",
        "label": "Rare",
        "min_xp": 40,
        "variant_rank": 4,
        "aliases": ["l5", "s5", "d", "rare", "stage5"],
    },
    {
        "index": 6,
        "name": "mythic",
        "label": "Mythic",
        "min_xp": 65,
        "variant_rank": 5,
        "aliases": ["l6", "s6", "e", "mythic", "legend", "stage6"],
    },
]


def stage_for_index(index: int) -> dict[str, Any]:
    if not STAGES:
        return {"index": 0, "name": "base", "label": "Base", "min_xp": 0, "variant_rank": 1, "aliases": ["a"]}
    idx = max(0, min(int(index), len(STAGES) - 1))
    return dict(STAGES[idx])


def stage_index_from_xp(xp: int) -> int:
    value = max(0, int(xp))
    selected = 0
    for stage in STAGES:
        if value >= int(stage["min_xp"]):
            selected = int(stage["index"])
        else:
            break
    return selected


def stage_name_from_xp(xp: int) -> str:
    return str(stage_for_index(stage_index_from_xp(xp)).get("name", "base"))


def next_stage_target(xp: int) -> int:
    value = max(0, int(xp))
    idx = stage_index_from_xp(value)
    next_idx = min(idx + 1, len(STAGES) - 1)
    target = int(stage_for_index(next_idx).get("min_xp", value))
    if next_idx == idx:
        return value
    return target


def stage_aliases(index: int) -> list[str]:
    return [str(item).strip().lower() for item in stage_for_index(index).get("aliases", []) if str(item).strip()]


def stage_index_from_token(token: str) -> int:
    raw = str(token or "").strip().lower()
    if not raw:
        return 2
    for stage in STAGES:
        aliases = {str(stage.get("name", "")).strip().lower(), *stage_aliases(int(stage.get("index", 0)))}
        if raw in aliases:
            return int(stage.get("index", 0))
    return 2


def stage_variant_rank(index: int) -> int:
    return int(stage_for_index(index).get("variant_rank", 1))


def variant_rank_from_id(variant_id: str) -> int:
    raw = str(variant_id or "").strip().lower().replace("-", "_")
    if not raw:
        return 1
    checks = [
        (5, {"e", "mythic", "legend", "l6", "s6", "stage6"}),
        (4, {"d", "rare", "l5", "s5", "stage5"}),
        (3, {"c", "elite", "l4", "s4", "stage4"}),
        (2, {"b", "evolved", "l3", "s3", "stage3"}),
        (1, {"a", "base", "l2", "s2", "stage2"}),
    ]
    parts = {raw}
    parts.update(p for p in raw.split("_") if p)
    for rank, tags in checks:
        if parts & tags:
            return rank
    return 1


def stage_supports_uploaded_art(index: int) -> bool:
    return int(index) >= 2
