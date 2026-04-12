"""Hardware capability checks for offline roadmap phases."""

from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GpuDevice:
    name: str
    vram_gb: float | None = None


@dataclass(frozen=True)
class HardwareSnapshot:
    platform_name: str
    platform_release: str
    machine: str
    cpu_logical_cores: int
    ram_gb: float
    disk_target: str
    disk_free_gb: float
    gpus: tuple[GpuDevice, ...]
    ai_pc_hint: bool
    ai_pc_reason: str = ""


@dataclass(frozen=True)
class PhaseSupport:
    phase: int
    title: str
    supported: bool
    blockers: tuple[str, ...]


def _round_gb(value: float) -> float:
    return round(value, 2)


def _linux_total_ram_gb() -> float:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return 0.0
    try:
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                fields = line.split()
                if len(fields) >= 2:
                    return float(fields[1]) / (1024.0 * 1024.0)
    except Exception:  # noqa: BLE001
        return 0.0
    return 0.0


def _windows_total_ram_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        ok = bool(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)))  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return 0.0
    if not ok:
        return 0.0
    return float(status.ullTotalPhys) / (1024.0 * 1024.0 * 1024.0)


def _macos_total_ram_gb() -> float:
    try:
        proc = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return 0.0
    if proc.returncode != 0:
        return 0.0
    try:
        return float(proc.stdout.strip()) / (1024.0 * 1024.0 * 1024.0)
    except ValueError:
        return 0.0


def _detect_total_ram_gb() -> float:
    if sys.platform.startswith("linux"):
        return _linux_total_ram_gb()
    if sys.platform.startswith("win"):
        return _windows_total_ram_gb()
    if sys.platform == "darwin":
        return _macos_total_ram_gb()
    return 0.0


def _detect_nvidia_gpus() -> list[GpuDevice]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return []
    try:
        proc = subprocess.run(
            [nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return []
    if proc.returncode != 0:
        return []

    devices: list[GpuDevice] = []
    for line in proc.stdout.splitlines():
        item = line.strip()
        if not item:
            continue
        name = item
        vram_gb: float | None = None
        if "," in item:
            name, mem_token = item.rsplit(",", 1)
            try:
                vram_gb = _round_gb(float(mem_token.strip()) / 1024.0)
            except ValueError:
                vram_gb = None
        devices.append(GpuDevice(name=name.strip(), vram_gb=vram_gb))
    return devices


def _detect_windows_gpus() -> list[GpuDevice]:
    if not sys.platform.startswith("win"):
        return []
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return []
    script = "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"
    try:
        proc = subprocess.run(
            [powershell, "-NoProfile", "-Command", script],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []

    rows = parsed if isinstance(parsed, list) else [parsed]
    devices: list[GpuDevice] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name", "")).strip()
        if not name:
            continue
        vram = row.get("AdapterRAM")
        vram_gb: float | None = None
        if isinstance(vram, (int, float)) and float(vram) > 0:
            vram_gb = _round_gb(float(vram) / (1024.0 * 1024.0 * 1024.0))
        devices.append(GpuDevice(name=name, vram_gb=vram_gb))
    return devices


def _detect_linux_gpus() -> list[GpuDevice]:
    if not sys.platform.startswith("linux"):
        return []
    lspci = shutil.which("lspci")
    if not lspci:
        return []
    try:
        proc = subprocess.run([lspci], text=True, capture_output=True, check=False)
    except Exception:  # noqa: BLE001
        return []
    if proc.returncode != 0:
        return []

    devices: list[GpuDevice] = []
    for line in proc.stdout.splitlines():
        lower = line.lower()
        if "vga compatible controller" in lower or "3d controller" in lower or "display controller" in lower:
            name = line.split(": ", 1)[-1].strip()
            devices.append(GpuDevice(name=name))
    return devices


def _detect_macos_gpus() -> list[GpuDevice]:
    if sys.platform != "darwin":
        return []
    try:
        proc = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            text=True,
            capture_output=True,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []

    rows = parsed.get("SPDisplaysDataType", [])
    devices: list[GpuDevice] = []
    if not isinstance(rows, list):
        return devices
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("sppci_model", "")).strip() or str(row.get("_name", "")).strip()
        if not name:
            continue
        vram_gb: float | None = None
        raw_vram = str(row.get("spdisplays_vram", "")).strip().lower()
        if raw_vram.endswith("gb"):
            try:
                vram_gb = _round_gb(float(raw_vram.replace("gb", "").strip()))
            except ValueError:
                vram_gb = None
        devices.append(GpuDevice(name=name, vram_gb=vram_gb))
    return devices


def _detect_gpus() -> tuple[GpuDevice, ...]:
    nvidia = _detect_nvidia_gpus()
    if nvidia:
        return tuple(nvidia)
    if sys.platform.startswith("win"):
        return tuple(_detect_windows_gpus())
    if sys.platform.startswith("linux"):
        return tuple(_detect_linux_gpus())
    if sys.platform == "darwin":
        return tuple(_detect_macos_gpus())
    return ()


def _cpu_descriptor() -> str:
    descriptor = (platform.processor() or "").strip()
    if descriptor:
        return descriptor
    if sys.platform.startswith("linux"):
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            try:
                for line in cpuinfo.read_text(encoding="utf-8").splitlines():
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[-1].strip()
            except Exception:  # noqa: BLE001
                return ""
    return ""


def _detect_ai_pc_hint() -> tuple[bool, str]:
    machine = platform.machine().lower()
    cpu_text = _cpu_descriptor().lower()
    if sys.platform == "darwin" and machine in {"arm64", "aarch64"}:
        return True, "Apple Silicon machine detected"
    if sys.platform.startswith("win") and machine in {"arm64", "aarch64"}:
        return True, "Windows ARM64 machine detected"
    if "core ultra" in cpu_text:
        return True, "Intel Core Ultra CPU hint detected"
    if "ryzen ai" in cpu_text:
        return True, "AMD Ryzen AI CPU hint detected"
    if "snapdragon x" in cpu_text:
        return True, "Snapdragon X CPU hint detected"
    return False, ""


def collect_hardware_snapshot(disk_target: Path) -> HardwareSnapshot:
    target = disk_target.expanduser().resolve()
    usage = shutil.disk_usage(target)
    gpus = _detect_gpus()
    ai_hint, ai_reason = _detect_ai_pc_hint()
    return HardwareSnapshot(
        platform_name=platform.system() or "Unknown",
        platform_release=platform.release() or "Unknown",
        machine=platform.machine() or "Unknown",
        cpu_logical_cores=max(1, int(os.cpu_count() or 1)),
        ram_gb=_round_gb(_detect_total_ram_gb()),
        disk_target=str(target),
        disk_free_gb=_round_gb(float(usage.free) / (1024.0 * 1024.0 * 1024.0)),
        gpus=gpus,
        ai_pc_hint=ai_hint,
        ai_pc_reason=ai_reason,
    )


def _max_gpu_vram_gb(snapshot: HardwareSnapshot) -> float:
    values = [float(item.vram_gb) for item in snapshot.gpus if item.vram_gb is not None]
    return max(values) if values else 0.0


def assess_phase_support(snapshot: HardwareSnapshot) -> list[PhaseSupport]:
    max_vram = _max_gpu_vram_gb(snapshot)
    has_vram_measurement = any(item.vram_gb is not None for item in snapshot.gpus)

    results: list[PhaseSupport] = []

    phase1_blockers: list[str] = []
    if snapshot.ram_gb < 32.0:
        phase1_blockers.append(f"Needs >=32 GB RAM (detected {snapshot.ram_gb:.2f} GB).")
    if snapshot.disk_free_gb < 1000.0:
        phase1_blockers.append(
            "Needs >=1000 GB free storage for documents/models "
            f"(detected {snapshot.disk_free_gb:.2f} GB at {snapshot.disk_target})."
        )
    results.append(
        PhaseSupport(
            phase=1,
            title="Local knowledge index and translation",
            supported=not phase1_blockers,
            blockers=tuple(phase1_blockers),
        )
    )

    phase2_blockers: list[str] = []
    if snapshot.ram_gb < 64.0:
        phase2_blockers.append(f"Needs >=64 GB RAM for smoother local LLM workflows (detected {snapshot.ram_gb:.2f} GB).")
    if not (max_vram >= 24.0 or snapshot.ai_pc_hint):
        if snapshot.gpus and not has_vram_measurement:
            phase2_blockers.append("GPU detected but VRAM is unknown; target is >=24 GB VRAM or an AI-PC class system.")
        else:
            phase2_blockers.append("Needs discrete GPU with >=24 GB VRAM or an AI-PC class system.")
    results.append(
        PhaseSupport(
            phase=2,
            title="Code assistance and retrieval-augmented local LLM",
            supported=not phase2_blockers,
            blockers=tuple(phase2_blockers),
        )
    )

    phase3_blockers: list[str] = []
    if snapshot.ram_gb < 16.0:
        phase3_blockers.append(f"Needs >=16 GB RAM for offline speech and math tools (detected {snapshot.ram_gb:.2f} GB).")
    results.append(
        PhaseSupport(
            phase=3,
            title="Optional voice and math tooling",
            supported=not phase3_blockers,
            blockers=tuple(phase3_blockers),
        )
    )

    phase4_blockers: list[str] = []
    if snapshot.ram_gb < 8.0:
        phase4_blockers.append(f"Needs >=8 GB RAM for local productivity features (detected {snapshot.ram_gb:.2f} GB).")
    results.append(
        PhaseSupport(
            phase=4,
            title="Productivity, validation, and priority engine",
            supported=not phase4_blockers,
            blockers=tuple(phase4_blockers),
        )
    )

    return results


def hardware_report_payload(snapshot: HardwareSnapshot, phase_results: list[PhaseSupport]) -> dict[str, Any]:
    supported_phases = [item.phase for item in phase_results if item.supported]
    unsupported_phases = [item.phase for item in phase_results if not item.supported]
    return {
        "ok": True,
        "snapshot": {
            "platform": snapshot.platform_name,
            "platform_release": snapshot.platform_release,
            "machine": snapshot.machine,
            "cpu_logical_cores": snapshot.cpu_logical_cores,
            "ram_gb": snapshot.ram_gb,
            "disk_target": snapshot.disk_target,
            "disk_free_gb": snapshot.disk_free_gb,
            "gpus": [{"name": item.name, "vram_gb": item.vram_gb} for item in snapshot.gpus],
            "ai_pc_hint": snapshot.ai_pc_hint,
            "ai_pc_reason": snapshot.ai_pc_reason,
        },
        "phases": [
            {
                "phase": item.phase,
                "title": item.title,
                "supported": item.supported,
                "blockers": list(item.blockers),
            }
            for item in phase_results
        ],
        "supported_phases": supported_phases,
        "unsupported_phases": unsupported_phases,
    }


def format_hardware_report(snapshot: HardwareSnapshot, phase_results: list[PhaseSupport]) -> str:
    lines = [
        "Hardware check:",
        f"  - platform: {snapshot.platform_name} {snapshot.platform_release} ({snapshot.machine})",
        f"  - cpu logical cores: {snapshot.cpu_logical_cores}",
        f"  - ram: {snapshot.ram_gb:.2f} GB",
        f"  - disk free ({snapshot.disk_target}): {snapshot.disk_free_gb:.2f} GB",
    ]
    if snapshot.gpus:
        for item in snapshot.gpus:
            vram_suffix = f" ({item.vram_gb:.2f} GB VRAM)" if item.vram_gb is not None else " (VRAM unknown)"
            lines.append(f"  - gpu: {item.name}{vram_suffix}")
    else:
        lines.append("  - gpu: none detected")

    ai_line = "yes"
    if not snapshot.ai_pc_hint:
        ai_line = "no"
    if snapshot.ai_pc_reason:
        ai_line = f"{ai_line} ({snapshot.ai_pc_reason})"
    lines.append(f"  - ai-pc hint: {ai_line}")
    lines.append("")
    lines.append("Phase support:")

    for result in phase_results:
        status = "PASS" if result.supported else "FAIL"
        lines.append(f"  - phase {result.phase}: {status} | {result.title}")
        for blocker in result.blockers:
            lines.append(f"    * {blocker}")

    supported = [str(item.phase) for item in phase_results if item.supported]
    unsupported = [str(item.phase) for item in phase_results if not item.supported]
    lines.append("")
    lines.append(f"Supported phases: {', '.join(supported) if supported else 'none'}")
    lines.append(f"Unsupported phases: {', '.join(unsupported) if unsupported else 'none'}")
    return "\n".join(lines)
