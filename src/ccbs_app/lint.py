"""YAML lint wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path


class LintToolMissing(RuntimeError):
    """Raised when yamllint cannot be executed."""


def lint_one(path: Path) -> tuple[bool, int, str, str]:
    proc = subprocess.run(["yamllint", str(path)], text=True, capture_output=True, check=False)
    if proc.returncode == 127:
        raise LintToolMissing("yamllint is not installed or not found in PATH")
    return proc.returncode == 0, proc.returncode, proc.stdout, proc.stderr
