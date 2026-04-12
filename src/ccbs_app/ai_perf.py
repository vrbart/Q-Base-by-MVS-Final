"""Performance telemetry helpers for hybrid routing."""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

from .ai_storage import ai2_dir


def _metrics_path(root: Path) -> Path:
    out = ai2_dir(root)
    out.mkdir(parents=True, exist_ok=True)
    return out / "perf_metrics.jsonl"


def append_perf_metric(root: Path, metric: dict[str, Any]) -> None:
    path = _metrics_path(root)
    payload = dict(metric)
    payload.setdefault("ts", time.time())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def recent_perf_metrics(root: Path, limit: int = 100) -> list[dict[str, Any]]:
    path = _metrics_path(root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in lines[-max(1, int(limit)):]:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def summarize_perf_metrics(root: Path, limit: int = 200) -> dict[str, Any]:
    rows = recent_perf_metrics(root, limit=limit)
    if not rows:
        return {"count": 0, "ttft_s_avg": None, "tokens_per_s_avg": None, "latency_s_avg": None}

    ttft = [float(r.get("ttft_s", 0.0)) for r in rows if isinstance(r.get("ttft_s"), (int, float))]
    tps = [float(r.get("tokens_per_s", 0.0)) for r in rows if isinstance(r.get("tokens_per_s"), (int, float))]
    lat = [float(r.get("latency_s", 0.0)) for r in rows if isinstance(r.get("latency_s"), (int, float))]

    def _avg(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    return {
        "count": len(rows),
        "ttft_s_avg": _avg(ttft),
        "tokens_per_s_avg": _avg(tps),
        "latency_s_avg": _avg(lat),
        "latest": rows[-1],
    }


def query_gpu_runtime_metrics() -> dict[str, Any]:
    nvidia_smi = "nvidia-smi"
    try:
        proc = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total,memory.used,utilization.gpu,utilization.memory,clocks.mem,clocks.max.mem",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=3,
        )
    except Exception:
        return {"available": False, "reason": "nvidia_smi_unavailable"}

    if proc.returncode != 0:
        return {"available": False, "reason": "nvidia_smi_failed"}

    gpus: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        item = line.strip()
        if not item:
            continue
        parts = [x.strip() for x in item.split(",")]
        if len(parts) < 7:
            continue
        name = parts[0]
        def _f(v: str) -> float | None:
            try:
                return float(v)
            except Exception:
                return None
        total = _f(parts[1])
        used = _f(parts[2])
        util_gpu = _f(parts[3])
        util_mem = _f(parts[4])
        clock_mem = _f(parts[5])
        clock_max = _f(parts[6])
        bandwidth_pressure = None
        if util_mem is not None and clock_mem is not None and clock_max and clock_max > 0:
            # Heuristic: memory utilization weighted by clock ratio.
            bandwidth_pressure = min(1.0, max(0.0, (util_mem / 100.0) * (clock_mem / clock_max)))
        gpus.append(
            {
                "name": name,
                "memory_total_mb": total,
                "memory_used_mb": used,
                "utilization_gpu_pct": util_gpu,
                "utilization_memory_pct": util_mem,
                "memory_clock_mhz": clock_mem,
                "memory_clock_max_mhz": clock_max,
                "bandwidth_pressure": None if bandwidth_pressure is None else round(bandwidth_pressure, 4),
            }
        )

    return {"available": bool(gpus), "gpus": gpus, "reason": "" if gpus else "no_gpu_rows"}


def _cpu_load_pct() -> float | None:
    getloadavg = getattr(os, "getloadavg", None)
    if not callable(getloadavg):
        return None
    try:
        loadavg = cast(Any, getloadavg)()
        if not isinstance(loadavg, tuple) or len(loadavg) < 1:
            return None
        l1 = float(loadavg[0])
        cores = max(1, int(os.cpu_count() or 1))
        return min(100.0, max(0.0, (l1 / cores) * 100.0))
    except Exception:
        return None


def runtime_resource_state() -> dict[str, Any]:
    gpu = query_gpu_runtime_metrics()
    cpu_load_pct = _cpu_load_pct()
    max_gpu_util = None
    max_bw_pressure = None
    if gpu.get("available"):
        utils = [float(g.get("utilization_gpu_pct") or 0.0) for g in gpu.get("gpus", [])]
        bw = [float(g.get("bandwidth_pressure") or 0.0) for g in gpu.get("gpus", []) if g.get("bandwidth_pressure") is not None]
        if utils:
            max_gpu_util = max(utils)
        if bw:
            max_bw_pressure = max(bw)
    return {
        "cpu_load_pct": None if cpu_load_pct is None else round(cpu_load_pct, 2),
        "gpu": gpu,
        "max_gpu_utilization_pct": None if max_gpu_util is None else round(max_gpu_util, 2),
        "max_bandwidth_pressure": None if max_bw_pressure is None else round(max_bw_pressure, 4),
    }


def vram_tier_recommendation(max_vram_gb: float | None) -> dict[str, Any]:
    if max_vram_gb is None or max_vram_gb <= 0:
        return {
            "tier": "unknown",
            "recommended_models": ["7-8B Q4_K_M (safe default)"],
            "warning": "VRAM not detected; start with 7-8B quantized model.",
        }
    vram = float(max_vram_gb)
    if vram >= 48.0:
        return {
            "tier": "48gb_plus",
            "recommended_models": ["70B Q4", "30B Q4/Q5", "14-30B full context"],
            "warning": "",
        }
    if vram >= 16.0:
        return {
            "tier": "16_to_24gb",
            "recommended_models": ["14-30B Q4", "7-8B high-context"],
            "warning": "",
        }
    if vram >= 8.0:
        return {
            "tier": "8_to_12gb",
            "recommended_models": ["7-8B Q4_K_M"],
            "warning": "Larger than ~14B will likely need heavy offloading.",
        }
    return {
        "tier": "under_8gb",
        "recommended_models": ["3-7B quantized"],
        "warning": "7-8B may require reduced context or CPU offload.",
    }


def _estimate_tokens(text: str) -> int:
    words = max(1, len(text.split()))
    return max(1, int(words * 0.75 + len(text) / 22.0))


def _stream_openai_compatible(base_url: str, api_key: str, model: str, prompt: str, timeout_s: int) -> tuple[float, float, int]:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        url = f"{base}/chat/completions"
    elif base.endswith("/chat/completions"):
        url = base
    else:
        url = f"{base}/v1/chat/completions"
    body = {
        "model": model,
        "stream": True,
        "messages": [
            {"role": "system", "content": "You are a concise benchmark assistant."},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )

    t0 = time.perf_counter()
    first_token_at: float | None = None
    generated = ""
    with urllib.request.urlopen(req, timeout=max(3, int(timeout_s))) as resp:  # noqa: S310
        for raw in resp:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith("data:"):
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except Exception:
                    continue
                choices = payload.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = str(delta.get("content", ""))
                if content:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    generated += content

    t1 = time.perf_counter()
    latency = max(0.0001, t1 - t0)
    ttft = latency if first_token_at is None else max(0.0001, first_token_at - t0)
    tokens = _estimate_tokens(generated)
    return ttft, latency, tokens


def _stream_ollama(base_url: str, model: str, prompt: str, timeout_s: int) -> tuple[float, float, int]:
    base = base_url.rstrip("/")
    url = f"{base}/api/generate"
    body = {"model": model, "prompt": prompt, "stream": True}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    first_token_at: float | None = None
    generated = ""
    with urllib.request.urlopen(req, timeout=max(3, int(timeout_s))) as resp:  # noqa: S310
        for raw in resp:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            chunk = str(payload.get("response", ""))
            if chunk:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                generated += chunk
            if bool(payload.get("done", False)):
                break
    t1 = time.perf_counter()
    latency = max(0.0001, t1 - t0)
    ttft = latency if first_token_at is None else max(0.0001, first_token_at - t0)
    tokens = _estimate_tokens(generated)
    return ttft, latency, tokens


def run_benchmark(
    root: Path,
    provider: str,
    model: str,
    prompt: str,
    runs: int = 3,
    timeout_s: int = 40,
    base_url: str = "",
    api_key: str = "",
) -> dict[str, Any]:
    provider_id = provider.strip().lower()
    run_count = max(1, int(runs))
    ttft_values: list[float] = []
    latency_values: list[float] = []
    tps_values: list[float] = []
    errors: list[str] = []

    for _ in range(run_count):
        try:
            if provider_id == "local":
                url = base_url or "http://127.0.0.1:11434"
                ttft, latency, tokens = _stream_ollama(url, model, prompt, timeout_s=timeout_s)
            else:
                url = base_url or "https://api.openai.com/v1"
                if not api_key:
                    raise RuntimeError("missing_api_key")
                ttft, latency, tokens = _stream_openai_compatible(url, api_key, model, prompt, timeout_s=timeout_s)
            tps = max(0.01, tokens / max(0.001, latency))
            ttft_values.append(ttft)
            latency_values.append(latency)
            tps_values.append(tps)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    if not latency_values:
        return {
            "ok": False,
            "provider": provider_id,
            "model": model,
            "runs": run_count,
            "errors": errors or ["benchmark_failed"],
        }

    out = {
        "ok": True,
        "provider": provider_id,
        "model": model,
        "runs": run_count,
        "successful_runs": len(latency_values),
        "ttft_s_avg": round(sum(ttft_values) / len(ttft_values), 4),
        "latency_s_avg": round(sum(latency_values) / len(latency_values), 4),
        "tokens_per_s_avg": round(sum(tps_values) / len(tps_values), 4),
        "errors": errors,
    }
    append_perf_metric(
        root,
        {
            "metric_type": "benchmark",
            "provider": provider_id,
            "model": model,
            "ttft_s": out["ttft_s_avg"],
            "latency_s": out["latency_s_avg"],
            "tokens_per_s": out["tokens_per_s_avg"],
            "runs": out["successful_runs"],
        },
    )
    return out
