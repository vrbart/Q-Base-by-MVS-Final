"""Model registry and provider adapter abstractions for CCBS AI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .ai_perf import query_gpu_runtime_metrics, vram_tier_recommendation
from .ai_storage import ai2_dir
from .hardware_check import collect_hardware_snapshot

DEFAULT_REGISTRY = {
    "version": "ai-model-registry-v1",
    "default_task_models": {
        "general": "extractive-default",
        "coding": "extractive-default",
        "summarization": "extractive-default",
        "translation": "extractive-default",
    },
    "models": [
        {
            "model_id": "extractive-default",
            "provider": "extractive",
            "model": "extractive",
            "tags": ["reasoning", "summarization", "translation", "coding"],
            "installed": True,
            "notes": "Built-in fallback provider",
        },
        {
            "model_id": "ollama-llama3-2-3b",
            "provider": "ollama",
            "model": "llama3.2:3b",
            "tags": ["reasoning", "coding", "summarization"],
            "installed": False,
            "notes": "Default local Ollama recommendation",
        },
    ],
}


def _gpu_vendor_from_name(name: str) -> str:
    lower = name.lower()
    if "nvidia" in lower:
        return "nvidia"
    if "amd" in lower or "radeon" in lower:
        return "amd"
    if "intel" in lower:
        return "intel"
    if "apple" in lower:
        return "apple"
    return "unknown"


def _path_registry(root: Path) -> Path:
    out = ai2_dir(root) / "models"
    out.mkdir(parents=True, exist_ok=True)
    return out / "model_registry.json"


def load_model_registry(root: Path) -> dict[str, Any]:
    path = _path_registry(root)
    if not path.exists():
        save_model_registry(root, dict(DEFAULT_REGISTRY))

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = dict(DEFAULT_REGISTRY)

    if "models" not in payload or not isinstance(payload["models"], list):
        payload = dict(DEFAULT_REGISTRY)
        save_model_registry(root, payload)
    return payload


def save_model_registry(root: Path, payload: dict[str, Any]) -> None:
    path = _path_registry(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def list_models(root: Path) -> list[dict[str, Any]]:
    return list(load_model_registry(root).get("models", []))


def add_or_update_model(
    root: Path,
    model_id: str,
    provider: str,
    model: str,
    tags: list[str] | None = None,
    installed: bool = True,
    notes: str = "",
) -> dict[str, Any]:
    if provider not in {"extractive", "ollama"}:
        raise ValueError("provider must be 'extractive' or 'ollama'")

    reg = load_model_registry(root)
    models = list(reg.get("models", []))
    item = {
        "model_id": model_id.strip(),
        "provider": provider.strip(),
        "model": model.strip(),
        "tags": sorted({t.strip() for t in (tags or []) if t.strip()}),
        "installed": bool(installed),
        "notes": notes.strip(),
    }
    if not item["model_id"]:
        raise ValueError("model_id is required")

    replaced = False
    for idx, row in enumerate(models):
        if str(row.get("model_id", "")).strip() == item["model_id"]:
            models[idx] = item
            replaced = True
            break
    if not replaced:
        models.append(item)

    reg["models"] = sorted(models, key=lambda x: str(x.get("model_id", "")))
    save_model_registry(root, reg)
    return item


def remove_model(root: Path, model_id: str) -> dict[str, Any]:
    target = model_id.strip()
    reg = load_model_registry(root)
    models = [m for m in reg.get("models", []) if str(m.get("model_id", "")) != target]
    if len(models) == len(reg.get("models", [])):
        raise ValueError(f"model not found: {target}")
    reg["models"] = models

    defaults = dict(reg.get("default_task_models", {}))
    for task, mid in list(defaults.items()):
        if str(mid) == target:
            defaults[task] = "extractive-default"
    reg["default_task_models"] = defaults

    save_model_registry(root, reg)
    return {"removed": target}


def set_default_model(root: Path, task: str, model_id: str) -> dict[str, Any]:
    reg = load_model_registry(root)
    model_ids = {str(m.get("model_id", "")) for m in reg.get("models", [])}
    if model_id not in model_ids:
        raise ValueError(f"model not found: {model_id}")
    defaults = dict(reg.get("default_task_models", {}))
    defaults[task.strip() or "general"] = model_id
    reg["default_task_models"] = defaults
    save_model_registry(root, reg)
    return {"task": task.strip() or "general", "model_id": model_id}


def recommend_models(root: Path, path_for_disk: Path | None = None) -> dict[str, Any]:
    target = path_for_disk or root
    snap = collect_hardware_snapshot(target)

    general = "extractive-default"
    coding = "extractive-default"
    reasoning = "extractive-default"
    hints: list[str] = []

    max_vram = 0.0
    for gpu in snap.gpus:
        max_vram = max(max_vram, float(gpu.vram_gb or 0.0))
    tier = vram_tier_recommendation(max_vram if max_vram > 0 else None)

    if max_vram >= 48.0:
        general = "ollama-70b-q4"
        coding = "ollama-70b-q4"
        reasoning = "ollama-70b-q4"
        hints.append("VRAM >= 48 GB: 70B Q4 lane available.")
    elif max_vram >= 16.0:
        general = "ollama-14b-q4"
        coding = "ollama-30b-q4"
        reasoning = "ollama-30b-q4"
        hints.append("VRAM 16-24 GB: 14B-30B quantized models recommended.")
    elif max_vram >= 8.0:
        general = "ollama-8b-q4"
        coding = "ollama-8b-q4"
        reasoning = "ollama-8b-q4"
        hints.append("VRAM 8-12 GB: prefer 7-8B Q4_K_M models.")
    elif snap.ram_gb >= 16.0:
        general = "ollama-llama3-2-3b"
        hints.append("No discrete VRAM detected; fallback to 3B local model.")

    if tier.get("warning"):
        hints.append(str(tier["warning"]))

    gpu_runtime = query_gpu_runtime_metrics()
    if gpu_runtime.get("available"):
        pressure_values = [
            float(item.get("bandwidth_pressure") or 0.0)
            for item in gpu_runtime.get("gpus", [])
            if item.get("bandwidth_pressure") is not None
        ]
        if pressure_values and max(pressure_values) > 0.8:
            hints.append("Memory bandwidth pressure is high; throughput may be memory-bound.")

    return {
        "cpu": f"{snap.platform_name} {snap.machine}",
        "cpu_logical_cores": snap.cpu_logical_cores,
        "ram_gb": snap.ram_gb,
        "gpus": [
            {"name": gpu.name, "vendor": _gpu_vendor_from_name(gpu.name), "vram_gb": gpu.vram_gb}
            for gpu in snap.gpus
        ],
        "recommended": {
            "general": general,
            "coding": coding,
            "reasoning": reasoning,
            "summarization": general,
            "translation": general,
        },
        "vram_tier": tier,
        "max_vram_gb": round(max_vram, 2),
        "gpu_runtime": gpu_runtime,
        "hints": hints,
    }


def resolve_model(root: Path, task: str = "general", explicit_model_id: str = "") -> dict[str, Any]:
    reg = load_model_registry(root)
    models = {str(item.get("model_id", "")): item for item in reg.get("models", [])}
    if explicit_model_id.strip():
        item = models.get(explicit_model_id.strip())
        if item is None:
            raise ValueError(f"model not found: {explicit_model_id}")
        return dict(item)

    defaults = dict(reg.get("default_task_models", {}))
    model_id = str(defaults.get(task, defaults.get("general", "extractive-default")))
    item = models.get(model_id)
    if item is None:
        return dict(DEFAULT_REGISTRY["models"][0])
    return dict(item)


def _run_ollama(model: str, prompt: str, timeout_s: int = 120) -> str:
    proc = subprocess.run(
        ["ollama", "run", model, prompt],
        text=True,
        capture_output=True,
        check=False,
        timeout=max(1, timeout_s),
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "unknown ollama error").strip())
    return proc.stdout.strip()


def run_model_prompt(root: Path, prompt: str, task: str = "general", model_id: str = "") -> dict[str, Any]:
    item = resolve_model(root, task=task, explicit_model_id=model_id)
    provider = str(item.get("provider", "extractive"))
    model = str(item.get("model", "extractive"))

    if provider == "ollama":
        text = _run_ollama(model=model, prompt=prompt)
        return {"provider": provider, "model": model, "output": text}

    # Built-in extractive fallback mode (for offline no-model environments).
    clean = prompt.strip()
    if len(clean) > 1200:
        clean = clean[:1200]
    return {
        "provider": "extractive",
        "model": "extractive",
        "output": clean,
    }
