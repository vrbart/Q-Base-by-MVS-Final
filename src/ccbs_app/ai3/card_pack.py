"""Card-pack manifest loading and deterministic role deck resolution."""

from __future__ import annotations

import hashlib
import json
import base64
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .evolution import (
    STAGES,
    stage_aliases,
    stage_for_index,
    stage_supports_uploaded_art,
    stage_variant_rank,
    stage_index_from_xp,
    variant_rank_from_id,
)

CORE_ROLE_ORDER = ["strategist", "core", "guardian", "ops", "retriever"]

_DEFAULT_ROLE_ICONS: dict[str, str] = {
    "strategist": "S",
    "core": "C",
    "guardian": "G",
    "ops": "O",
    "retriever": "R",
    "samurai": "S",
    "hacker": "H",
    "ranger": "R",
    "scientist": "SCI",
}

_ROLE_FALLBACK_ACCENTS: dict[str, str] = {
    "strategist": "#ff8b2c",
    "core": "#ff4cd8",
    "guardian": "#42e8ff",
    "ops": "#74ff87",
    "retriever": "#97ff54",
    "samurai": "#ff8b2c",
    "hacker": "#ca7bff",
    "ranger": "#5bffd2",
    "scientist": "#78ff66",
}

ROLE_BEHAVIORS: dict[str, dict[str, Any]] = {
    "core": {
        "ui_mode": "balanced",
        "role_hint": "Balanced assistant mode.",
        "description": "General purpose lane for everyday Q/A, coding, and planning.",
        "enforce_offline_only": None,
        "enforce_allow_remote": None,
        "top_k": 5,
        "top_k_min": 5,
        "ops_hint": "balanced",
    },
    "strategist": {
        "ui_mode": "planner",
        "role_hint": "Planner-forward mode with concise strategy.",
        "description": "Planning lane for decomposition, sequencing, and execution strategy.",
        "enforce_offline_only": None,
        "enforce_allow_remote": None,
        "top_k": 5,
        "top_k_min": 5,
        "ops_hint": "balanced",
    },
    "guardian": {
        "ui_mode": "guardrail",
        "role_hint": "Safety-first local guard mode.",
        "description": "Safety lane: enforces offline-only execution and blocks remote escalation.",
        "enforce_offline_only": True,
        "enforce_allow_remote": False,
        "top_k": 5,
        "top_k_min": 5,
        "ops_hint": "balanced",
    },
    "ops": {
        "ui_mode": "operations",
        "role_hint": "Operations mode with approvals surfaced.",
        "description": "Operations lane for approval-heavy and workflow-control tasks.",
        "enforce_offline_only": None,
        "enforce_allow_remote": None,
        "top_k": 5,
        "top_k_min": 5,
        "ops_hint": "expand",
    },
    "retriever": {
        "ui_mode": "retrieval",
        "role_hint": "Evidence-focused retrieval mode with citations.",
        "description": "Evidence-first lane with deeper retrieval and citation emphasis.",
        "enforce_offline_only": None,
        "enforce_allow_remote": None,
        "top_k": 8,
        "top_k_min": 8,
        "ops_hint": "balanced",
    },
    "samurai": {
        "ui_mode": "builder",
        "role_hint": "Samurai lane: convert verbal requests into practical implementation and code.",
        "description": "Execution lane that turns natural-language tasks into concrete code, steps, and checks.",
        "enforce_offline_only": None,
        "enforce_allow_remote": None,
        "top_k": 6,
        "top_k_min": 6,
        "ops_hint": "balanced",
    },
    "hacker": {
        "ui_mode": "terminal",
        "role_hint": "Hacker lane: code-and-command output only, optimized for execution.",
        "description": "Terminal-first code lane focused on commands, scripts, fixes, and technical runbooks.",
        "enforce_offline_only": None,
        "enforce_allow_remote": None,
        "top_k": 5,
        "top_k_min": 5,
        "ops_hint": "expand",
    },
}


def _env_enabled(name: str, default: bool = True) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _hash_to_int(value: str) -> int:
    return int(_sha256_hex(value), 16)


def _module_repo_root() -> Path:
    # src/ccbs_app/ai3/card_pack.py -> repo root is 3 parents up.
    return Path(__file__).resolve().parents[3]


def _candidate_assets_dirs(root: Path) -> list[Path]:
    out: list[Path] = []
    for candidate in (
        root / "assets",
        _module_repo_root() / "assets",
        Path.cwd() / "assets",
    ):
        if candidate not in out:
            out.append(candidate)
    env_assets = str(os.environ.get("CCBS_ASSETS_DIR", "")).strip()
    if env_assets:
        env_path = Path(env_assets).expanduser()
        if env_path not in out:
            out.insert(0, env_path)
    return out


def discover_assets_dir(root: Path) -> Path | None:
    for assets_dir in _candidate_assets_dirs(root):
        if assets_dir.exists() and assets_dir.is_dir():
            return assets_dir
    return None


def _candidate_manifest_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for assets_dir in _candidate_assets_dirs(root):
        path = assets_dir / "ai3" / "cards" / "manifest.json"
        if path not in paths:
            paths.append(path)
    return paths


def _default_icon(role_id: str) -> str:
    rid = role_id.strip().lower()
    return _DEFAULT_ROLE_ICONS.get(rid, rid[:2].upper() if rid else "AI")


def _rough_avatar_data_url(*, role_id: str, label: str, accent: str, stage_index: int, seed_tag: str = "") -> str:
    rid = role_id.strip().lower() or "core"
    acc = accent.strip() or _ROLE_FALLBACK_ACCENTS.get(rid, "#3df0ff")
    bg = "#10142a"
    seed = _hash_to_int(f"rough:{rid}:{label}:{stage_index}:{seed_tag}")
    tilt = -5 + (seed % 11)
    eye = 12 + (seed % 9)
    mouth_wave = 4 + (seed % 4)
    wobble = 2 + (seed % 3)
    hand_jitter = -6 + (seed % 13)
    body_color = ["#8aa0bb", "#9ab2c8", "#a0b6d0", "#90a8bf"][seed % 4]
    stick = "#1c2136"
    paper = "#d9e0ef"
    stage_note = "L0 SCRIBBLE" if stage_index <= 0 else "L1 SCRIBBLE"
    extra = ""
    if stage_index >= 1:
        # Keep this intentionally rough and hand-drawn looking.
        extra = f"""
    <path d='M70 150 q18 {12 + wobble} 35 0 q18 {10 + wobble} 34 0' fill='none' stroke='{stick}' stroke-width='4' stroke-linecap='round'/>
    <line x1='98' y1='202' x2='{120 + hand_jitter}' y2='{220 + wobble}' stroke='{stick}' stroke-width='5' stroke-linecap='round'/>
    <line x1='{120 + hand_jitter}' y1='{220 + wobble}' x2='{143 + hand_jitter}' y2='{198 + wobble}' stroke='{stick}' stroke-width='4' stroke-linecap='round'/>
"""
    svg = f"""
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 320 460' width='320' height='460'>
  <defs>
    <linearGradient id='paper' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='{paper}' stop-opacity='0.95'/>
      <stop offset='100%' stop-color='#b8c4dc' stop-opacity='0.88'/>
    </linearGradient>
  </defs>
  <rect x='7' y='7' width='306' height='446' rx='24' fill='{bg}' stroke='{acc}' stroke-width='7'/>
  <rect x='20' y='20' width='280' height='420' rx='19' fill='url(#paper)' opacity='0.12'/>
  <g transform='translate(58,88) rotate({tilt},100,120)'>
    <path d='M42 24 L192 24 L194 300 L40 300 Z' fill='none' stroke='{acc}' stroke-width='3' stroke-dasharray='5 7'/>
    <circle cx='100' cy='86' r='44' fill='{body_color}' stroke='{stick}' stroke-width='5'/>
    <path d='M{100-eye} 78 l{eye/2:.1f} {eye/2:.1f} M{100-eye/2:.1f} 78 l{-eye/2:.1f} {eye/2:.1f}' stroke='{stick}' stroke-width='4' stroke-linecap='round'/>
    <path d='M{100+eye/4:.1f} 78 l{eye/2:.1f} {eye/2:.1f} M{100+eye/1.8:.1f} 78 l{-eye/2:.1f} {eye/2:.1f}' stroke='{stick}' stroke-width='4' stroke-linecap='round'/>
    <path d='M70 112 q15 {mouth_wave} 30 0 q15 {mouth_wave} 30 0' fill='none' stroke='{stick}' stroke-width='4' stroke-linecap='round'/>
    <line x1='100' y1='132' x2='100' y2='212' stroke='{stick}' stroke-width='6' stroke-linecap='round'/>
    <line x1='100' y1='158' x2='62' y2='186' stroke='{stick}' stroke-width='5' stroke-linecap='round'/>
    <line x1='100' y1='158' x2='140' y2='190' stroke='{stick}' stroke-width='5' stroke-linecap='round'/>
    <line x1='100' y1='212' x2='70' y2='260' stroke='{stick}' stroke-width='5' stroke-linecap='round'/>
    <line x1='100' y1='212' x2='134' y2='260' stroke='{stick}' stroke-width='5' stroke-linecap='round'/>
{extra}
    <path d='M20 318 q80 -14 160 0' fill='none' stroke='{acc}' stroke-width='3' stroke-dasharray='6 8'/>
  </g>
  <rect x='44' y='352' width='232' height='70' rx='13' fill='rgba(8,14,32,0.80)' stroke='{acc}' stroke-width='3'/>
  <text x='160' y='377' text-anchor='middle' font-size='14' font-family='monospace' font-weight='700' fill='#dff2ff'>{stage_note}</text>
  <text x='160' y='401' text-anchor='middle' font-size='19' font-family='monospace' font-weight='700' fill='#e8f7ff'>{label.upper()[:13]}</text>
</svg>
""".strip()
    return "data:image/svg+xml;utf8," + quote(svg, safe="")


def _hero_avatar_data_url(*, role_id: str, label: str, accent: str, variant_tag: str = "") -> str:
    rid = role_id.strip().lower() or "core"
    acc = accent.strip() or _ROLE_FALLBACK_ACCENTS.get(rid, "#3df0ff")
    bg = "#09112e"
    sprite = {
        "strategist": {"skin": "#ffd6b1", "hair": "#2a3f80", "body": "#c63b2f", "prop": "map"},
        "core": {"skin": "#ff6ac6", "hair": "#7a22d9", "body": "#3b2b62", "prop": "blades"},
        "guardian": {"skin": "#8cc5ff", "hair": "#1d3f6e", "body": "#132945", "prop": "guard"},
        "ops": {"skin": "#f6d3b8", "hair": "#6a4125", "body": "#222f40", "prop": "case"},
        "retriever": {"skin": "#b8ff73", "hair": "#4d8c28", "body": "#2f512e", "prop": "staff"},
        "samurai": {"skin": "#ffb67f", "hair": "#5a3520", "body": "#5d2830", "prop": "blade"},
        "hacker": {"skin": "#8cc3ff", "hair": "#1f2f47", "body": "#1f1f3d", "prop": "screen"},
        "ranger": {"skin": "#6be6cb", "hair": "#2e7f71", "body": "#1e4b49", "prop": "leaf"},
        "scientist": {"skin": "#b7ff8d", "hair": "#59842b", "body": "#35584b", "prop": "flask"},
    }.get(rid, {"skin": "#b0d9ff", "hair": "#315d92", "body": "#2d3d60", "prop": "none"})
    tilt = -4 if (_hash_to_int(f"{rid}:{variant_tag}") % 2 == 0) else 4
    prop_label = {
        "map": "MAP",
        "blades": "X",
        "guard": "II",
        "case": "OPS",
        "staff": "R",
        "blade": "S",
        "screen": "CLI",
        "leaf": "K",
        "flask": "LAB",
        "none": "AI",
    }.get(sprite["prop"], "AI")
    svg = f"""
<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 320 460' width='320' height='460'>
  <defs>
    <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='{acc}' stop-opacity='0.30'/>
      <stop offset='100%' stop-color='{bg}' stop-opacity='1'/>
    </linearGradient>
    <radialGradient id='halo' cx='50%' cy='34%' r='60%'>
      <stop offset='0%' stop-color='{acc}' stop-opacity='0.68'/>
      <stop offset='100%' stop-color='{acc}' stop-opacity='0.02'/>
    </radialGradient>
  </defs>
  <rect x='7' y='7' width='306' height='446' rx='25' fill='{bg}' stroke='{acc}' stroke-width='7'/>
  <rect x='20' y='20' width='280' height='420' rx='19' fill='url(#bg)'/>
  <rect x='20' y='20' width='280' height='420' rx='19' fill='url(#halo)'/>
  <g transform='translate(63,90) rotate({tilt},97,80)'>
    <ellipse cx='97' cy='44' rx='45' ry='14' fill='{sprite["hair"]}' opacity='0.92'/>
    <circle cx='97' cy='62' r='42' fill='{sprite["skin"]}' stroke='{acc}' stroke-width='4'/>
    <path d='M76 53 l10 10 M86 53 l-10 10' stroke='#0b1228' stroke-width='4' stroke-linecap='round'/>
    <path d='M108 53 l10 10 M118 53 l-10 10' stroke='#0b1228' stroke-width='4' stroke-linecap='round'/>
    <path d='M74 82 q23 15 46 0 q23 15 46 0' fill='none' stroke='#0b1228' stroke-width='4' stroke-linecap='round'/>
    <rect x='59' y='103' width='76' height='100' rx='16' fill='{sprite["body"]}' stroke='{acc}' stroke-width='3'/>
    <rect x='38' y='112' width='20' height='62' rx='8' fill='{sprite["body"]}' stroke='{acc}' stroke-width='2'/>
    <rect x='136' y='112' width='20' height='62' rx='8' fill='{sprite["body"]}' stroke='{acc}' stroke-width='2'/>
    <rect x='66' y='203' width='24' height='54' rx='9' fill='#1b2749' stroke='{acc}' stroke-width='2'/>
    <rect x='104' y='203' width='24' height='54' rx='9' fill='#1b2749' stroke='{acc}' stroke-width='2'/>
    <rect x='143' y='127' width='38' height='25' rx='6' fill='#101d3d' stroke='{acc}' stroke-width='2'/>
    <text x='162' y='143' text-anchor='middle' font-family='monospace' font-size='11' font-weight='700' fill='#ebfbff'>{prop_label}</text>
  </g>
  <rect x='52' y='360' width='216' height='58' rx='14' fill='rgba(7,14,35,0.85)' stroke='{acc}' stroke-width='3'/>
  <text x='160' y='395' text-anchor='middle' font-size='22' font-family='monospace' font-weight='700' fill='#e8f7ff'>{label.upper()[:12]}</text>
</svg>
""".strip()
    return "data:image/svg+xml;utf8," + quote(svg, safe="")


def _fallback_avatar_data_url(
    *,
    role_id: str,
    label: str,
    accent: str,
    stage_index: int,
    variant_tag: str = "",
) -> str:
    if int(stage_index) <= 1:
        return _rough_avatar_data_url(
            role_id=role_id,
            label=label,
            accent=accent,
            stage_index=stage_index,
            seed_tag=variant_tag,
        )
    return _hero_avatar_data_url(
        role_id=role_id,
        label=label,
        accent=accent,
        variant_tag=variant_tag,
    )

def _builtin_manifest() -> dict[str, Any]:
    return {
        "pack_id": "builtin_neon",
        "version": "1.0.0",
        "label": "CCBS Built-in Neon Deck",
        "roles": [
            {
                "role_id": "strategist",
                "label": "Strategist",
                "utility_mode": "strategist",
                "is_core": True,
                "icon": "⚔",
                "variants": [{"variant_id": "builtin", "image_path": "", "frame_style": "orange", "accent_palette": {}, "rarity_weight": 1}],
            },
            {
                "role_id": "core",
                "label": "Core Agent",
                "utility_mode": "core",
                "is_core": True,
                "icon": "◎",
                "variants": [{"variant_id": "builtin", "image_path": "", "frame_style": "pink", "accent_palette": {}, "rarity_weight": 1}],
            },
            {
                "role_id": "guardian",
                "label": "Guardian",
                "utility_mode": "guardian",
                "is_core": True,
                "icon": "⛩",
                "variants": [{"variant_id": "builtin", "image_path": "", "frame_style": "cyan", "accent_palette": {}, "rarity_weight": 1}],
            },
            {
                "role_id": "ops",
                "label": "Ops",
                "utility_mode": "ops",
                "is_core": True,
                "icon": "💼",
                "variants": [{"variant_id": "builtin", "image_path": "", "frame_style": "green", "accent_palette": {}, "rarity_weight": 1}],
            },
            {
                "role_id": "retriever",
                "label": "Retriever",
                "utility_mode": "retriever",
                "is_core": True,
                "icon": "🌿",
                "variants": [{"variant_id": "builtin", "image_path": "", "frame_style": "lime", "accent_palette": {}, "rarity_weight": 1}],
            },
        ],
    }


def _validate_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("card-pack manifest must be an object")
    out = {
        "pack_id": str(payload.get("pack_id", "")).strip() or "nft_pack",
        "version": str(payload.get("version", "")).strip() or "1.0.0",
        "label": str(payload.get("label", "")).strip() or "CCBS Card Pack",
        "roles": [],
    }
    roles = payload.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ValueError("card-pack manifest roles[] is required")
    for raw_role in roles:
        if not isinstance(raw_role, dict):
            continue
        role_id = str(raw_role.get("role_id", "")).strip().lower()
        if not role_id:
            continue
        variants = raw_role.get("variants")
        if not isinstance(variants, list) or not variants:
            continue
        role = {
            "role_id": role_id,
            "label": str(raw_role.get("label", role_id.title())).strip() or role_id.title(),
            "utility_mode": str(raw_role.get("utility_mode", role_id)).strip().lower() or role_id,
            "is_core": bool(raw_role.get("is_core", False)),
            "icon": str(raw_role.get("icon", "◎")).strip() or "◎",
            "variants": [],
        }
        for raw_variant in variants:
            if not isinstance(raw_variant, dict):
                continue
            rarity = int(raw_variant.get("rarity_weight", 1) or 1)
            role["variants"].append(
                {
                    "variant_id": str(raw_variant.get("variant_id", "v1")).strip() or "v1",
                    "image_path": str(raw_variant.get("image_path", "")).strip(),
                    "frame_style": str(raw_variant.get("frame_style", "neon")).strip() or "neon",
                    "accent_palette": dict(raw_variant.get("accent_palette", {}) or {}),
                    "rarity_weight": rarity if rarity > 0 else 1,
                }
            )
        if role["variants"]:
            out["roles"].append(role)
    if not out["roles"]:
        raise ValueError("card-pack manifest has no usable roles")
    return out


def load_card_pack(root: Path, pack_id: str = "") -> dict[str, Any]:
    if not _env_enabled("CCBS_CARD_PACK_ENABLE", True):
        return _builtin_manifest()

    manifest_path: Path | None = None
    for candidate in _candidate_manifest_paths(root):
        if candidate.exists():
            manifest_path = candidate
            break
    if manifest_path is None:
        return _builtin_manifest()

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = _validate_manifest(payload)
        manifest["_cards_dir"] = str(manifest_path.parent)
    except Exception:
        return _builtin_manifest()

    desired = pack_id.strip()
    if desired and manifest.get("pack_id") != desired:
        return _builtin_manifest()
    return manifest


def _asset_url(image_path: str, cards_dir: Path | None = None) -> str:
    raw = image_path.strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("/"):
        raw = raw[1:]
    if ".." in raw:
        return ""
    fingerprint = ""
    if cards_dir is not None:
        path = cards_dir / raw
        if not path.exists():
            return ""
        try:
            stat = path.stat()
            fingerprint = f"?v={int(stat.st_mtime_ns)}-{int(stat.st_size)}"
        except Exception:
            fingerprint = ""
    return f"/assets/ai3/cards/{raw}{fingerprint}"


def _asset_inline_data_url(image_path: str, cards_dir: Path | None = None) -> str:
    raw = image_path.strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("/"):
        raw = raw[1:]
    if ".." in raw:
        return ""
    if cards_dir is None:
        return ""
    path = cards_dir / raw
    if not path.exists() or not path.is_file():
        return ""
    try:
        data = path.read_bytes()
    except Exception:
        return ""
    if not data:
        return ""
    mime = mimetypes.guess_type(str(path))[0] or ("image/svg+xml" if path.suffix.lower() == ".svg" else "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _resolve_user_variant_image_path(
    *,
    cards_dir: Path | None,
    role_id: str,
    variant_id: str,
    stage_index: int,
) -> str:
    if cards_dir is None:
        return ""
    user_dir = cards_dir / "user"
    if not user_dir.exists() or not user_dir.is_dir():
        return ""
    rid = role_id.strip().lower()
    vid = variant_id.strip().lower()
    vtag = ""
    if "-" in vid:
        vtag = vid.rsplit("-", 1)[-1].strip()
    elif "_" in vid:
        vtag = vid.rsplit("_", 1)[-1].strip()
    ext_order = (".png", ".webp", ".jpg", ".jpeg", ".svg")
    name_keys = []
    for alias in stage_aliases(stage_index):
        name_keys.extend([f"{rid}_{alias}", f"{rid}-{alias}"])
    name_keys.extend(
        [
        f"{rid}_{vid}",
        f"{rid}-{vid}",
        vid,
        ]
    )
    if vtag and vtag != vid:
        name_keys.extend([f"{rid}_{vtag}", f"{rid}-{vtag}"])
    name_keys.extend(
        [
            f"{rid}_l0",
            f"{rid}-l0",
            f"{rid}_l1",
            f"{rid}-l1",
            f"{rid}_a",
            f"{rid}-a",
            f"{rid}_b",
            f"{rid}-b",
            f"{rid}_c",
            f"{rid}-c",
            f"{rid}_d",
            f"{rid}-d",
            f"{rid}_e",
            f"{rid}-e",
        rid,
        ]
    )
    seen: set[str] = set()
    for key in name_keys:
        key = key.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        for ext in ext_order:
            path = user_dir / f"{key}{ext}"
            if path.exists() and path.is_file():
                return f"user/{path.name}"
    return ""


def _resolve_pool_image_path(*, cards_dir: Path | None, role_id: str, stage_index: int, seed_key: str) -> str:
    if cards_dir is None or not stage_supports_uploaded_art(stage_index):
        return ""
    pool_dir = cards_dir / "user" / "pool"
    if not pool_dir.exists() or not pool_dir.is_dir():
        return ""
    exts = {".png", ".webp", ".jpg", ".jpeg", ".svg"}
    files = sorted([p for p in pool_dir.iterdir() if p.is_file() and p.suffix.lower() in exts], key=lambda p: p.name.lower())
    if not files:
        return ""
    rid = role_id.strip().lower()
    aliases = set(stage_aliases(stage_index))

    def _has_token(name: str, token: str) -> bool:
        raw = name.lower()
        return (
            raw.startswith(f"{token}_")
            or raw.startswith(f"{token}-")
            or f"_{token}_" in raw
            or f"-{token}-" in raw
            or raw.endswith(f"_{token}")
            or raw.endswith(f"-{token}")
        )

    role_stage = [p for p in files if _has_token(p.stem, rid) and any(_has_token(p.stem, tag) for tag in aliases)]
    if role_stage:
        return f"user/pool/{role_stage[_hash_to_int(seed_key + ':role_stage') % len(role_stage)].name}"
    stage_only = [p for p in files if any(_has_token(p.stem, tag) for tag in aliases)]
    if stage_only:
        return f"user/pool/{stage_only[_hash_to_int(seed_key + ':stage') % len(stage_only)].name}"
    role_only = [p for p in files if _has_token(p.stem, rid)]
    if role_only:
        return f"user/pool/{role_only[_hash_to_int(seed_key + ':role') % len(role_only)].name}"
    return f"user/pool/{files[_hash_to_int(seed_key + ':any') % len(files)].name}"


def _pick_weighted_variant(variants: list[dict[str, Any]], seed_key: str) -> dict[str, Any]:
    if not variants:
        return {"variant_id": "fallback", "image_path": "", "frame_style": "neon", "accent_palette": {}, "rarity_weight": 1}
    total = sum(max(1, int(item.get("rarity_weight", 1))) for item in variants)
    roll = (_hash_to_int(seed_key) % total) + 1
    upto = 0
    for item in variants:
        upto += max(1, int(item.get("rarity_weight", 1)))
        if roll <= upto:
            return item
    return variants[-1]


def _stage_for_xp(xp: int) -> int:
    return stage_index_from_xp(xp)


def _stage_name(stage: int) -> str:
    return str(stage_for_index(stage).get("name", "base"))


def _next_target_for_stage(stage: int) -> int:
    idx = max(0, int(stage))
    if idx >= len(STAGES) - 1:
        return int(stage_for_index(idx).get("min_xp", 0))
    return int(stage_for_index(idx + 1).get("min_xp", 0))


def _pick_variant_for_stage(variants: list[dict[str, Any]], stage: int, seed_key: str) -> dict[str, Any]:
    if not variants:
        return {"variant_id": "fallback", "image_path": "", "frame_style": "neon", "accent_palette": {}, "rarity_weight": 1}
    min_rank = max(1, int(stage_variant_rank(stage)))
    pool = [item for item in variants if variant_rank_from_id(str(item.get("variant_id", ""))) >= min_rank]
    if not pool and min_rank > 1:
        pool = [item for item in variants if variant_rank_from_id(str(item.get("variant_id", ""))) >= (min_rank - 1)]
    if not pool:
        pool = [item for item in variants if variant_rank_from_id(str(item.get("variant_id", ""))) >= 1]
    return _pick_weighted_variant(pool or variants, seed_key)


def normalize_utility_mode(value: str, fallback: str = "core") -> str:
    raw = str(value or "").strip().lower()
    if raw:
        return raw
    fb = str(fallback or "").strip().lower()
    return fb or "core"


def role_behavior(role_id: str, utility_mode: str = "") -> dict[str, Any]:
    rid = role_id.strip().lower()
    mode = normalize_utility_mode(utility_mode, fallback=rid or "core")
    if rid in {"ranger", "scientist"} and mode in ROLE_BEHAVIORS:
        effective = mode
    elif rid in ROLE_BEHAVIORS:
        effective = rid
    elif mode in ROLE_BEHAVIORS:
        effective = mode
    else:
        effective = "core"
    out = dict(ROLE_BEHAVIORS.get(effective, ROLE_BEHAVIORS["core"]))
    out["effective_role"] = effective
    out["utility_mode"] = mode
    out["role_id"] = rid or "core"
    return out


def resolve_role_utility_mode(*, root: Path, role_id: str, pack_id: str = "") -> str:
    rid = str(role_id or "").strip().lower()
    if not rid:
        return "core"
    manifest = load_card_pack(root=root, pack_id=pack_id)
    for role in list(manifest.get("roles", [])):
        if not isinstance(role, dict):
            continue
        if str(role.get("role_id", "")).strip().lower() == rid:
            return normalize_utility_mode(str(role.get("utility_mode", rid)), fallback=rid)
    return rid


def resolve_card_deck(
    *,
    root: Path,
    thread_id: str,
    user_id: str,
    surface: str,
    active_role: str = "",
    pack_id: str = "",
    extras_count: int = 4,
    role_xp: dict[str, int] | None = None,
) -> dict[str, Any]:
    manifest = load_card_pack(root=root, pack_id=pack_id)
    roles = [dict(item) for item in manifest.get("roles", []) if isinstance(item, dict)]
    role_map = {str(item.get("role_id", "")).strip().lower(): item for item in roles}
    cards_dir = Path(str(manifest.get("_cards_dir", "")).strip()) if str(manifest.get("_cards_dir", "")).strip() else None

    seed_source = f"{thread_id.strip() or 'thread-auto'}:{user_id.strip() or 'default'}:{manifest.get('pack_id','')}:{manifest.get('version','')}"
    thread_seed = _sha256_hex(seed_source)

    cards: list[dict[str, Any]] = []
    xp_map = {str(k).strip().lower(): max(0, int(v)) for k, v in (role_xp or {}).items()}

    def build_card(role: dict[str, Any]) -> dict[str, Any]:
        role_id = str(role.get("role_id", "")).strip().lower() or "core"
        utility_mode = normalize_utility_mode(str(role.get("utility_mode", role_id)), fallback=role_id)
        role_points = int(xp_map.get(role_id, 0))
        evolution_stage = _stage_for_xp(role_points)
        variant = _pick_variant_for_stage(list(role.get("variants", [])), evolution_stage, f"{thread_seed}:{role_id}:{evolution_stage}")
        behavior = role_behavior(role_id, utility_mode)
        description = str(role.get("description", "")).strip() or str(behavior.get("description", "")).strip()
        role_label = str(role.get("label", role_id.title()))
        constraints: list[str] = []
        if behavior.get("enforce_offline_only") is True:
            constraints.append("offline-only")
        if behavior.get("enforce_allow_remote") is False:
            constraints.append("remote disabled")
        top_k_min = int(behavior.get("top_k_min", 0) or 0)
        if top_k_min > 0:
            constraints.append(f"top-k >= {top_k_min}")
        accent_palette = dict(variant.get("accent_palette", {}) or {})
        accent = str(accent_palette.get("border", "")).strip() or _ROLE_FALLBACK_ACCENTS.get(role_id, "#3df0ff")
        variant_id = str(variant.get("variant_id", "v1"))
        use_uploaded_art = stage_supports_uploaded_art(evolution_stage)
        resolved_variant_path = _resolve_user_variant_image_path(
            cards_dir=cards_dir,
            role_id=role_id,
            variant_id=variant_id,
            stage_index=evolution_stage,
        )
        pool_variant_path = _resolve_pool_image_path(
            cards_dir=cards_dir,
            role_id=role_id,
            stage_index=evolution_stage,
            seed_key=f"{thread_seed}:{role_id}:{evolution_stage}:{variant_id}",
        )
        resolved_variant_path = resolved_variant_path or pool_variant_path or str(variant.get("image_path", ""))
        primary_image = _asset_url(resolved_variant_path, cards_dir=cards_dir) if use_uploaded_art else ""
        primary_inline = _asset_inline_data_url(resolved_variant_path, cards_dir=cards_dir) if use_uploaded_art else ""
        fallback_image = _fallback_avatar_data_url(
            role_id=role_id,
            label=role_label,
            accent=accent,
            stage_index=evolution_stage,
            variant_tag=variant_id,
        )
        variant_options: list[dict[str, Any]] = []
        for raw_variant in list(role.get("variants", [])):
            option_accent_palette = dict(raw_variant.get("accent_palette", {}) or {})
            option_accent = str(option_accent_palette.get("border", "")).strip() or accent
            option_variant_id = str(raw_variant.get("variant_id", "v1"))
            resolved_option_path = _resolve_user_variant_image_path(
                cards_dir=cards_dir,
                role_id=role_id,
                variant_id=option_variant_id,
                stage_index=evolution_stage,
            ) or str(raw_variant.get("image_path", ""))
            option_primary = _asset_url(resolved_option_path, cards_dir=cards_dir) if use_uploaded_art else ""
            option_inline = _asset_inline_data_url(resolved_option_path, cards_dir=cards_dir) if use_uploaded_art else ""
            option_fallback = _fallback_avatar_data_url(
                role_id=role_id,
                label=role_label,
                accent=option_accent,
                stage_index=evolution_stage,
                variant_tag=option_variant_id,
            )
            variant_options.append(
                {
                    "variant_id": option_variant_id,
                    "image_url": option_primary,
                    "image_inline_url": option_inline,
                    "image_fallback_url": option_fallback,
                    "frame_style": str(raw_variant.get("frame_style", "neon")),
                    "accent_palette": option_accent_palette,
                }
            )
        return {
            "role_id": role_id,
            "label": role_label,
            "utility_mode": utility_mode,
            "is_core": bool(role.get("is_core", False)),
            "icon": str(role.get("icon", _default_icon(role_id))) or _default_icon(role_id),
            "description": description,
            "constraint_summary": ", ".join(constraints),
            "variant_id": variant_id,
            "image_url": primary_image,
            "image_inline_url": primary_inline,
            "image_fallback_url": fallback_image,
            "variant_options": variant_options,
            "frame_style": str(variant.get("frame_style", "neon")),
            "accent_palette": accent_palette,
            "behavior": behavior,
            "effective_behavior_role": str(behavior.get("effective_role", role_id)),
            "evolution": {
                "xp": role_points,
                "level": evolution_stage,
                "max_level": max(0, len(STAGES) - 1),
                "stage": _stage_name(evolution_stage),
                "stage_label": str(stage_for_index(evolution_stage).get("label", _stage_name(evolution_stage).title())),
                "next_target": _next_target_for_stage(evolution_stage),
                "remaining_to_next": max(0, _next_target_for_stage(evolution_stage) - role_points),
            },
        }

    # Always include core role buttons in fixed order where available.
    for role_id in CORE_ROLE_ORDER:
        role = role_map.get(role_id)
        if role is None:
            continue
        cards.append(build_card(role))

    # Deterministic extras from non-core roles.
    non_core = [item for item in roles if not bool(item.get("is_core", False))]
    non_core.sort(key=lambda item: _hash_to_int(f"{thread_seed}:{str(item.get('role_id',''))}"))
    for item in non_core[: max(0, int(extras_count))]:
        cards.append(build_card(item))

    active = active_role.strip().lower()
    known = {str(item.get("role_id", "")).strip().lower() for item in cards}
    if active not in known:
        active = "core" if "core" in known else (next(iter(known)) if known else "core")

    return {
        "pack": {
            "pack_id": str(manifest.get("pack_id", "")),
            "version": str(manifest.get("version", "")),
            "label": str(manifest.get("label", "")),
        },
        "surface": surface.strip().lower() or "ui",
        "thread_seed": thread_seed,
        "cards": cards,
        "active_role": active,
        "card_pack_enabled": _env_enabled("CCBS_CARD_PACK_ENABLE", True),
    }
