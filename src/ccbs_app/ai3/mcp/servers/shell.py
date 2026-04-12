"""Shell MCP server."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_MAX_COMMAND_CHARS = 800
_BLOCKED_COMMAND_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:invoke-expression|iex)\b", re.IGNORECASE),
        "PowerShell expression re-invocation is blocked",
    ),
    (
        re.compile(r"\b(?:certutil|bitsadmin|mshta|regsvr32|rundll32)\b", re.IGNORECASE),
        "download or inline execution helpers are blocked",
    ),
    (
        re.compile(r"\b(?:invoke-webrequest|iwr|curl(?:\.exe)?|wget(?:\.exe)?|start-bitstransfer)\b", re.IGNORECASE),
        "network download helpers are blocked",
    ),
    (
        re.compile(r"(?:downloadstring\s*\(|downloadfile\s*\(|new-object\s+net\.webclient|system\.net\.webclient)", re.IGNORECASE),
        "inline download cradles are blocked",
    ),
    (
        re.compile(r"\b(?:add-mppreference|set-mppreference)\b", re.IGNORECASE),
        "antivirus preference changes are blocked",
    ),
    (
        re.compile(r"\b(?:register-scheduledtask|schtasks(?:\.exe)?)\b", re.IGNORECASE),
        "scheduled task changes are blocked",
    ),
    (
        re.compile(r"currentversion\\run|start menu\\programs\\startup", re.IGNORECASE),
        "autostart persistence changes are blocked",
    ),
    (
        re.compile(r"\b(?:new-service|sc(?:\.exe)?\s+create)\b", re.IGNORECASE),
        "service creation is blocked",
    ),
    (
        re.compile(r"\b(?:powershell|pwsh)(?:\.exe)?\b[^\r\n]{0,120}\s-(?:enc|encodedcommand)\b", re.IGNORECASE),
        "encoded PowerShell payloads are blocked",
    ),
)


def _assert_command_allowed(command: str) -> str:
    cleaned = str(command or "").strip()
    if not cleaned:
        raise ValueError("command is required")
    if "\x00" in cleaned:
        raise ValueError("command contains an invalid NUL byte")
    if "\r" in cleaned or "\n" in cleaned:
        raise ValueError("shell.exec only accepts single-line commands")
    if len(cleaned) > _MAX_COMMAND_CHARS:
        raise ValueError(f"shell.exec is limited to {_MAX_COMMAND_CHARS} characters")
    for pattern, reason in _BLOCKED_COMMAND_RULES:
        if pattern.search(cleaned):
            raise ValueError(f"shell.exec blocked: {reason}")
    return cleaned


def _build_shell_command(command: str) -> list[str]:
    if os.name == "nt":
        powershell = (
            shutil.which("pwsh.exe")
            or shutil.which("powershell.exe")
            or shutil.which("pwsh")
            or shutil.which("powershell")
        )
        if powershell:
            return [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command]
        cmd_exe = shutil.which("cmd.exe") or shutil.which("cmd")
        if cmd_exe:
            return [str(cmd_exe), "/d", "/s", "/c", command]
        return ["cmd.exe", "/d", "/s", "/c", command]

    shell_bin = shutil.which("bash") or shutil.which("sh")
    if shell_bin:
        return [str(shell_bin), "-lc", command]
    return ["/bin/sh", "-lc", command]


def exec_shell(command: str, cwd: str = "", timeout_s: int = 30) -> dict[str, Any]:
    cleaned = _assert_command_allowed(command)
    workdir = Path(cwd).expanduser().resolve() if cwd.strip() else None
    proc = subprocess.run(
        _build_shell_command(cleaned),
        cwd=str(workdir) if workdir else None,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
        check=False,
        timeout=max(1, int(timeout_s)),
    )
    return {
        "command": cleaned,
        "cwd": str(workdir) if workdir else "",
        "return_code": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
