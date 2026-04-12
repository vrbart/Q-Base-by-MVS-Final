"""LM Studio OpenAI-compatible local adapter."""

from __future__ import annotations

import json
import os
import urllib.request


def _resolve_lmstudio_api_key() -> str:
    for name in ("LM_API_TOKEN", "LMSTUDIO_API_KEY", "LM_STUDIO_API_KEY"):
        value = str(os.environ.get(name, "")).strip()
        if value:
            return value
    return ""


def lmstudio_chat(
    base_url: str,
    model: str,
    prompt: str,
    timeout_s: int = 40,
    api_key: str = "",
) -> str:
    base = base_url.rstrip("/") or "http://127.0.0.1:1234/v1"
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"

    token = str(api_key or "").strip() or _resolve_lmstudio_api_key()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an offline-first assistant."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            }
        ).encode("utf-8"),
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=max(3, int(timeout_s))) as resp:  # noqa: S310
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    choices = payload.get("choices", []) if isinstance(payload, dict) else []
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message", {})
        if isinstance(msg, dict):
            out = str(msg.get("content", "")).strip()
            if out:
                return out
    raise RuntimeError("lmstudio response did not contain text")
