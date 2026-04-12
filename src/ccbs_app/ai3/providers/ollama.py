"""Ollama local adapter."""

from __future__ import annotations

import json
import urllib.request


def ollama_chat(base_url: str, model: str, prompt: str, timeout_s: int = 40) -> str:
    base = base_url.rstrip("/") or "http://127.0.0.1:11434"
    url = f"{base}/api/generate"
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=max(3, int(timeout_s))) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    out = str(payload.get("response", "") if isinstance(payload, dict) else "").strip()
    if not out:
        raise RuntimeError("ollama response did not contain text")
    return out
