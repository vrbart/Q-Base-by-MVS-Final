"""Repository helper functions."""

from __future__ import annotations

import subprocess
from pathlib import Path


class RepoError(RuntimeError):
    """Raised when repository assumptions are not satisfied."""


def repo_root() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RepoError("Not inside a git repository.")
    return Path(proc.stdout.strip())
