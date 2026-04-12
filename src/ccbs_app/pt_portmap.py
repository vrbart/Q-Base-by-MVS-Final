"""Packet Tracer link-to-bootstrap interface mapping."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

RE_TRUNK = re.compile(r"\btrunk\b", re.IGNORECASE)
RE_ACCESS_VLAN = re.compile(r"access\s+vlan\s+(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class LinkRow:
    row_num: int
    a_role: str
    a_port: str
    b_role: str
    b_port: str
    link_type: str


@dataclass(frozen=True)
class PortmapReport:
    target: str
    write: bool
    changed_files: list[str]
    skipped_files: list[str]
    unresolved_rows: list[str]
    issues: list[str]


def _normalize(text: str) -> str:
    return text.strip()


def _normalize_port(text: str) -> str:
    return _normalize(text).lower()


def _read_links(links_path: Path) -> tuple[list[LinkRow], list[str], list[str]]:
    rows: list[LinkRow] = []
    unresolved_rows: list[str] = []
    issues: list[str] = []
    if not links_path.exists():
        return rows, unresolved_rows, [f"missing links file: {links_path}"]

    try:
        with links_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            header = set(reader.fieldnames or [])
            uses_new = {"a_role", "a_port", "b_role", "b_port", "link_type"}.issubset(header)
            uses_old = {"left_device", "left_interface", "right_device", "right_interface", "purpose"}.issubset(
                header
            )
            if not uses_new and not uses_old:
                issues.append(
                    "links.csv missing expected columns (a_role/a_port/b_role/b_port/link_type or "
                    "left_device/left_interface/right_device/right_interface/purpose)."
                )
                return rows, unresolved_rows, issues

            for row_num, row in enumerate(reader, 2):
                if uses_new:
                    a_role = _normalize(row.get("a_role", ""))
                    a_port = _normalize(row.get("a_port", ""))
                    b_role = _normalize(row.get("b_role", ""))
                    b_port = _normalize(row.get("b_port", ""))
                    link_type = _normalize(row.get("link_type", ""))
                else:
                    a_role = _normalize(row.get("left_device", ""))
                    a_port = _normalize(row.get("left_interface", ""))
                    b_role = _normalize(row.get("right_device", ""))
                    b_port = _normalize(row.get("right_interface", ""))
                    link_type = _normalize(row.get("purpose", ""))

                if not a_role or not b_role:
                    issues.append(f"links.csv:{row_num} missing role/device names")
                    continue
                if not a_port or not b_port:
                    unresolved_rows.append(f"links.csv:{row_num}")
                rows.append(LinkRow(row_num=row_num, a_role=a_role, a_port=a_port, b_role=b_role, b_port=b_port, link_type=link_type))
    except Exception as exc:  # noqa: BLE001
        issues.append(f"failed reading links.csv: {exc}")

    return rows, unresolved_rows, issues


def _ports_for_role(role: str, rows: list[LinkRow]) -> tuple[list[str], dict[str, str]]:
    trunk_ports: set[str] = set()
    access_ports: dict[str, str] = {}
    for row in rows:
        own_port = ""
        if row.a_role == role:
            own_port = row.a_port
        elif row.b_role == role:
            own_port = row.b_port
        if not own_port:
            continue

        if RE_TRUNK.search(row.link_type):
            trunk_ports.add(_normalize_port(own_port))
            continue
        match = RE_ACCESS_VLAN.search(row.link_type)
        if match:
            access_ports[_normalize_port(own_port)] = match.group(1)

    return sorted(trunk_ports), dict(sorted(access_ports.items(), key=lambda item: item[0]))


def _render_interface_sections(trunk_ports: list[str], access_ports: dict[str, str]) -> list[str]:
    lines: list[str] = []
    lines.append("! ---- Uplink trunk ----")
    lines.append("! Auto-generated from links.csv")
    if trunk_ports:
        for port in trunk_ports:
            lines.append(f"interface {port}")
            lines.append(" switchport mode trunk")
            lines.append(" switchport trunk native vlan 99")
            lines.append(" switchport trunk allowed vlan 10,20,99")
            lines.append(" spanning-tree portfast trunk")
            lines.append("")
    else:
        lines.append("! No mapped trunk ports found for this device.")
        lines.append("")

    lines.append("! ---- Endpoint ports ----")
    lines.append("! Auto-generated from links.csv")
    if access_ports:
        for port, vlan in access_ports.items():
            lines.append(f"interface {port}")
            lines.append(" switchport mode access")
            lines.append(f" switchport access vlan {vlan}")
            lines.append(" spanning-tree portfast")
            lines.append(" spanning-tree bpduguard enable")
            lines.append("")
    else:
        lines.append("! No mapped access ports found for this device.")
        lines.append("")
    return lines


def _replace_interface_sections(text: str, replacement_lines: list[str]) -> tuple[str, bool, str | None]:
    lines = text.splitlines()
    trunk_idx = -1
    end_idx = -1
    for idx, line in enumerate(lines):
        lowered = line.strip().lower()
        if trunk_idx == -1 and lowered.startswith("! ---- uplink trunk"):
            trunk_idx = idx
        if lowered == "end":
            end_idx = idx
            break

    if trunk_idx == -1:
        return text, False, "missing '! ---- Uplink trunk ----' marker"
    if end_idx == -1 or trunk_idx >= end_idx:
        return text, False, "missing 'end' marker after trunk section"

    rebuilt = lines[:trunk_idx] + replacement_lines + lines[end_idx:]
    updated = "\n".join(rebuilt)
    if text.endswith("\n"):
        updated += "\n"
    return updated, updated != text, None


def _role_config_path(bootstrap_dir: Path, role: str) -> Path | None:
    for ext in (".cfg", ".txt"):
        candidate = bootstrap_dir / f"{role}{ext}"
        if candidate.exists():
            return candidate
    return None


def _rel_posix(path: Path, target: Path) -> str:
    return path.relative_to(target).as_posix()


def apply_link_ports(target: Path, write: bool = False) -> PortmapReport:
    changed_files: list[str] = []
    skipped_files: list[str] = []
    issues: list[str] = []
    unresolved_rows: list[str] = []

    bootstrap_dir = target / "bootstrap_cli"
    if not bootstrap_dir.exists():
        issues.append(f"missing bootstrap directory: {bootstrap_dir}")
        return PortmapReport(
            target=str(target),
            write=write,
            changed_files=changed_files,
            skipped_files=skipped_files,
            unresolved_rows=unresolved_rows,
            issues=issues,
        )

    rows, unresolved_rows, link_issues = _read_links(target / "links.csv")
    issues.extend(link_issues)
    if not rows:
        issues.append("no usable link rows found")
        return PortmapReport(
            target=str(target),
            write=write,
            changed_files=changed_files,
            skipped_files=skipped_files,
            unresolved_rows=unresolved_rows,
            issues=issues,
        )

    roles = sorted({row.a_role for row in rows} | {row.b_role for row in rows})
    role_has_trunk: dict[str, bool] = {role: False for role in roles}
    for row in rows:
        if RE_TRUNK.search(row.link_type):
            role_has_trunk[row.a_role] = True
            role_has_trunk[row.b_role] = True

    for role in roles:
        cfg_path = _role_config_path(bootstrap_dir, role)
        if cfg_path is None:
            if role_has_trunk.get(role, False):
                skipped_files.append(f"{role}: missing bootstrap file")
            continue

        trunk_ports, access_ports = _ports_for_role(role, rows)
        if not trunk_ports and not access_ports:
            skipped_files.append(f"{_rel_posix(cfg_path, target)}: no mapped ports")
            continue

        try:
            original = cfg_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            issues.append(f"unable to read {_rel_posix(cfg_path, target)}: {exc}")
            continue

        replacement = _render_interface_sections(trunk_ports, access_ports)
        updated, changed, replace_issue = _replace_interface_sections(original, replacement)
        if replace_issue:
            issues.append(f"{_rel_posix(cfg_path, target)}: {replace_issue}")
            continue
        if changed:
            changed_files.append(_rel_posix(cfg_path, target))
            if write:
                cfg_path.write_text(updated, encoding="utf-8")

    return PortmapReport(
        target=str(target),
        write=write,
        changed_files=changed_files,
        skipped_files=skipped_files,
        unresolved_rows=unresolved_rows,
        issues=issues,
    )


def format_portmap_report(report: PortmapReport) -> str:
    mode = "write" if report.write else "dry-run"
    lines: list[str] = []
    lines.append(f"Packet Tracer link-port apply: {report.target}")
    lines.append(f"Mode: {mode}")
    lines.append(f"Changed files: {len(report.changed_files)}")
    lines.append(f"Skipped files: {len(report.skipped_files)}")
    lines.append(f"Unresolved link rows: {len(report.unresolved_rows)}")
    lines.append(f"Issues: {len(report.issues)}")

    if report.changed_files:
        lines.append("")
        lines.append("Changed file list:")
        for item in report.changed_files[:20]:
            lines.append(f"  - {item}")
    if report.skipped_files:
        lines.append("")
        lines.append("Skipped file list:")
        for item in report.skipped_files[:20]:
            lines.append(f"  - {item}")
    if report.unresolved_rows:
        lines.append("")
        lines.append("Sample unresolved rows:")
        for item in report.unresolved_rows[:20]:
            lines.append(f"  - {item}")
    if report.issues:
        lines.append("")
        lines.append("Issues:")
        for item in report.issues[:20]:
            lines.append(f"  - {item}")
    return "\n".join(lines)
