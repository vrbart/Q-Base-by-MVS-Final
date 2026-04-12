"""OS-keyring-backed provider API key helpers with env fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .ai_auth import delete_provider_key_ref, get_provider_key_ref, set_provider_key_ref

KEYRING_SERVICE = "ccbs-ai"


def _load_keyring() -> Any | None:
    try:
        import keyring  # type: ignore
    except Exception:
        return None
    return keyring


def _account(user_id: str, provider_id: str) -> str:
    uid = (user_id or "default").strip().lower() or "default"
    pid = provider_id.strip().lower()
    return f"{uid}:{pid}"


def _mask(value: str) -> str:
    text = value.strip()
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def key_set(root: Path, provider_id: str, api_key: str, user_id: str = "default") -> dict[str, Any]:
    keyring = _load_keyring()
    if keyring is None:
        raise RuntimeError("keyring dependency not available; install package 'keyring'")
    key = api_key.strip()
    if not key:
        raise ValueError("api key is required")
    account = _account(user_id, provider_id)
    keyring.set_password(KEYRING_SERVICE, account, key)
    set_provider_key_ref(
        root=root,
        user_id=(user_id or "default"),
        provider_id=provider_id,
        keyring_service=KEYRING_SERVICE,
        keyring_account=account,
    )
    return {
        "provider_id": provider_id.strip().lower(),
        "user_id": (user_id or "default").strip().lower(),
        "stored": True,
        "masked": _mask(key),
        "keyring_service": KEYRING_SERVICE,
        "keyring_account": account,
    }


def key_get(root: Path, provider_id: str, user_id: str = "default") -> dict[str, Any]:
    keyring = _load_keyring()
    if keyring is None:
        raise RuntimeError("keyring dependency not available; install package 'keyring'")
    ref = get_provider_key_ref(root=root, user_id=user_id, provider_id=provider_id)
    account = ref.get("keyring_account") or _account(user_id, provider_id)
    raw = keyring.get_password(KEYRING_SERVICE, str(account)) or ""
    if not raw:
        raise ValueError("no key found for provider/user")
    return {
        "provider_id": provider_id.strip().lower(),
        "user_id": (user_id or "default").strip().lower(),
        "masked": _mask(raw),
        "keyring_service": KEYRING_SERVICE,
        "keyring_account": str(account),
    }


def key_delete(root: Path, provider_id: str, user_id: str = "default") -> dict[str, Any]:
    keyring = _load_keyring()
    if keyring is None:
        raise RuntimeError("keyring dependency not available; install package 'keyring'")
    ref = get_provider_key_ref(root=root, user_id=user_id, provider_id=provider_id)
    account = ref.get("keyring_account") or _account(user_id, provider_id)
    deleted = False
    try:
        keyring.delete_password(KEYRING_SERVICE, str(account))
        deleted = True
    except Exception:
        deleted = False
    delete_provider_key_ref(root=root, user_id=user_id, provider_id=provider_id)
    return {
        "provider_id": provider_id.strip().lower(),
        "user_id": (user_id or "default").strip().lower(),
        "deleted": bool(deleted),
        "keyring_service": KEYRING_SERVICE,
        "keyring_account": str(account),
    }


def key_status(root: Path, provider_id: str, user_id: str = "default") -> dict[str, Any]:
    ref = get_provider_key_ref(root=root, user_id=user_id, provider_id=provider_id)
    env_var = "OPENAI_API_KEY" if provider_id.strip().lower() == "codex" else "OPENAI_API_KEY_REMOTE2"
    env_present = bool(os.environ.get(env_var, "").strip())
    keyring = _load_keyring()
    keyring_available = keyring is not None

    keyring_present = False
    account = str(ref.get("keyring_account", "") or _account(user_id, provider_id))
    if keyring_available and ref:
        try:
            keyring_present = bool(keyring.get_password(KEYRING_SERVICE, account))
        except Exception:
            keyring_present = False

    return {
        "provider_id": provider_id.strip().lower(),
        "user_id": (user_id or "default").strip().lower(),
        "keyring_available": keyring_available,
        "keyring_reference_present": bool(ref),
        "keyring_key_present": keyring_present,
        "env_var": env_var,
        "env_key_present": env_present,
    }


def resolve_api_key(root: Path, provider_id: str, user_id: str = "default", explicit_key: str = "") -> str:
    key = explicit_key.strip()
    if key:
        return key

    keyring = _load_keyring()
    if keyring is not None:
        ref = get_provider_key_ref(root=root, user_id=user_id, provider_id=provider_id)
        account = str(ref.get("keyring_account", "") or _account(user_id, provider_id))
        if account:
            try:
                val = keyring.get_password(KEYRING_SERVICE, account) or ""
                if val.strip():
                    return val.strip()
            except Exception:
                pass

    env_var = "OPENAI_API_KEY" if provider_id.strip().lower() == "codex" else "OPENAI_API_KEY_REMOTE2"
    return os.environ.get(env_var, "").strip()

