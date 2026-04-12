"""OpenAI-compatible remote provider adapter (Codex path)."""

from __future__ import annotations

import json
import urllib.request


def _chat_completion(api_key: str, base_url: str, model: str, prompt: str, timeout_s: int) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a practical software assistant."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            }
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
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
    text = str(payload.get("output_text", "") if isinstance(payload, dict) else "").strip()
    if text:
        return text
    raise RuntimeError("codex response did not contain text")


def codex_chat(api_key: str, base_url: str, model: str, prompt: str, timeout_s: int = 40) -> str:
    return _chat_completion(api_key=api_key, base_url=base_url, model=model, prompt=prompt, timeout_s=timeout_s)
