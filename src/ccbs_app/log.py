"""Logging helpers for CCBS CLI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_log(payload: dict[str, Any], log_dir: Path) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = log_dir / f"ccbs-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
