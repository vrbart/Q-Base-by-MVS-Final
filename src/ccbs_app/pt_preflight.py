"""Packet Tracer topology preflight checks."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RE_PLACEHOLDER = re.compile(r"\{\{[^{}]+\}\}")
RE_TODO = re.compile(r"\b(?:TODO|TBD|FIXME)\b", re.IGNORECASE)
BOOTSTRAP_EXTS = {".cfg", ".txt"}
REQUIRED_FILES = ("devices.csv", "links.csv")
RECOMMENDED_FILES = (
    ("run_order", ("run_order.txt",)),
    ("proof_pack", ("proof_pack_commands.txt", "proof/proof_commands.txt")),
)
MODES = ("scaffold", "config", "deploy")


@dataclass(frozen=True)
class SimpleFinding:
    path: str
    line: int
    snippet: str


@dataclass(frozen=True)
class ModeOutcome:
    mode: str
    ok: bool
    blockers: list[str]


@dataclass(frozen=True)
class PreflightReport:
    target: str
    max_todo: int
    max_unmapped_links: int
    missing_required_items: list[str]
    missing_recommended_items: list[str]
    bootstrap_file_count: int
    placeholder_hits: list[SimpleFinding]
    todo_hits: list[SimpleFinding]
    unmapped_link_rows: list[str]
    parse_errors: list[str]
    outcomes: list[ModeOutcome]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "max_todo": self.max_todo,
            "max_unmapped_links": self.max_unmapped_links,
            "missing_required_items": self.missing_required_items,
            "missing_recommended_items": self.missing_recommended_items,
            "bootstrap_file_count": self.bootstrap_file_count,
            "placeholder_hits": [f.__dict__ for f in self.placeholder_hits],
            "todo_hits": [f.__dict__ for f in self.todo_hits],
            "unmapped_link_rows": self.unmapped_link_rows,
            "parse_errors": self.parse_errors,
            "outcomes": [o.__dict__ for o in self.outcomes],
        }


def _iter_bootstrap_files(target: Path) -> list[Path]:
    root = target / "bootstrap_cli"
    if not root.exists():
        return []
    files = [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix.lower() in BOOTSTRAP_EXTS
    ]
    return files


def _rel_posix(path: Path, target: Path) -> str:
    return path.relative_to(target).as_posix()


def _scan_text_findings(
    target: Path,
    files: list[Path],
    pattern: re.Pattern[str],
) -> tuple[list[SimpleFinding], list[str]]:
    hits: list[SimpleFinding] = []
    read_errors: list[str] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            read_errors.append(f"unable to read {_rel_posix(path, target)}: {exc}")
            continue
        for idx, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(
                    SimpleFinding(
                        path=_rel_posix(path, target),
                        line=idx,
                        snippet=line.strip(),
                    )
                )
    return hits, read_errors


def _scan_links(target: Path) -> tuple[list[str], list[str]]:
    links = target / "links.csv"
    unmapped_rows: list[str] = []
    parse_errors: list[str] = []
    if not links.exists():
        return unmapped_rows, parse_errors

    try:
        with links.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            if {"a_port", "b_port"}.issubset(header):
                left_key, right_key = "a_port", "b_port"
            elif {"left_interface", "right_interface"}.issubset(header):
                left_key, right_key = "left_interface", "right_interface"
            else:
                parse_errors.append(
                    "links.csv missing expected port columns (a_port/b_port or left_interface/right_interface)."
                )
                return unmapped_rows, parse_errors

            for row_idx, row in enumerate(reader, 2):
                left = (row.get(left_key) or "").strip()
                right = (row.get(right_key) or "").strip()
                if not left or not right:
                    unmapped_rows.append(f"links.csv:{row_idx}")
    except Exception as exc:  # noqa: BLE001
        parse_errors.append(f"links.csv parse error: {exc}")

    return unmapped_rows, parse_errors


def _evaluate_modes(
    missing_required_items: list[str],
    parse_errors: list[str],
    placeholder_hits: list[SimpleFinding],
    todo_hits: list[SimpleFinding],
    unmapped_link_rows: list[str],
    bootstrap_file_count: int,
    max_todo: int,
    max_unmapped_links: int,
) -> list[ModeOutcome]:
    has_structure_issues = bool(missing_required_items) or bool(parse_errors) or bootstrap_file_count == 0

    outcomes: list[ModeOutcome] = []
    for mode in MODES:
        blockers: list[str] = []
        if has_structure_issues:
            if missing_required_items:
                blockers.append("missing_required_files")
            if parse_errors:
                blockers.append("parse_errors")
            if bootstrap_file_count == 0:
                blockers.append("missing_bootstrap_files")

        if mode in {"config", "deploy"} and placeholder_hits:
            blockers.append("unresolved_placeholders")

        if mode == "deploy":
            if len(todo_hits) > max_todo:
                blockers.append("todo_markers_in_bootstrap")
            if len(unmapped_link_rows) > max_unmapped_links:
                blockers.append("unmapped_link_ports")

        outcomes.append(ModeOutcome(mode=mode, ok=not blockers, blockers=blockers))
    return outcomes


def run_preflight(target: Path, max_todo: int = 0, max_unmapped_links: int = 0) -> PreflightReport:
    missing_required_items: list[str] = []
    missing_recommended_items: list[str] = []
    if not target.exists():
        missing_required_items.append(f"path_missing:{target}")

    for name in REQUIRED_FILES:
        if not (target / name).exists():
            missing_required_items.append(name)
    for label, options in RECOMMENDED_FILES:
        if not any((target / option).exists() for option in options):
            if len(options) == 1:
                missing_recommended_items.append(options[0])
            else:
                missing_recommended_items.append(f"{label}: one of {', '.join(options)}")
    if not (target / "bootstrap_cli").exists():
        missing_required_items.append("bootstrap_cli/")

    bootstrap_files = _iter_bootstrap_files(target)
    placeholder_hits, placeholder_read_errors = _scan_text_findings(target, bootstrap_files, RE_PLACEHOLDER)
    todo_hits, todo_read_errors = _scan_text_findings(target, bootstrap_files, RE_TODO)
    unmapped_link_rows, parse_errors = _scan_links(target)
    parse_errors.extend(placeholder_read_errors)
    parse_errors.extend(todo_read_errors)
    parse_errors = list(dict.fromkeys(parse_errors))
    outcomes = _evaluate_modes(
        missing_required_items=missing_required_items,
        parse_errors=parse_errors,
        placeholder_hits=placeholder_hits,
        todo_hits=todo_hits,
        unmapped_link_rows=unmapped_link_rows,
        bootstrap_file_count=len(bootstrap_files),
        max_todo=max(0, max_todo),
        max_unmapped_links=max(0, max_unmapped_links),
    )

    return PreflightReport(
        target=str(target),
        max_todo=max(0, max_todo),
        max_unmapped_links=max(0, max_unmapped_links),
        missing_required_items=missing_required_items,
        missing_recommended_items=missing_recommended_items,
        bootstrap_file_count=len(bootstrap_files),
        placeholder_hits=placeholder_hits,
        todo_hits=todo_hits,
        unmapped_link_rows=unmapped_link_rows,
        parse_errors=parse_errors,
        outcomes=outcomes,
    )


def format_report(report: PreflightReport, mode: str, as_json: bool) -> str:
    if as_json:
        return json.dumps(report.to_dict(), indent=2)

    outcome_by_mode = {item.mode: item for item in report.outcomes}
    selected = outcome_by_mode[mode]
    lines: list[str] = []
    lines.append(f"Packet Tracer preflight: {report.target}")
    lines.append(f"Mode: {mode}")
    lines.append(f"Result: {'PASS' if selected.ok else 'FAIL'}")
    lines.append("")
    lines.append("Summary:")
    lines.append(f"  - tolerance max_todo: {report.max_todo}")
    lines.append(f"  - tolerance max_unmapped_links: {report.max_unmapped_links}")
    lines.append(f"  - missing required items: {len(report.missing_required_items)}")
    lines.append(f"  - missing recommended items: {len(report.missing_recommended_items)}")
    lines.append(f"  - bootstrap files: {report.bootstrap_file_count}")
    lines.append(f"  - unresolved placeholders in bootstrap: {len(report.placeholder_hits)}")
    lines.append(f"  - TODO/TBD/FIXME in bootstrap: {len(report.todo_hits)}")
    lines.append(f"  - links with unmapped ports: {len(report.unmapped_link_rows)}")
    lines.append(f"  - parse errors: {len(report.parse_errors)}")
    lines.append("")
    lines.append("Readiness matrix:")
    for outcome in report.outcomes:
        mark = "OK" if outcome.ok else "FAIL"
        detail = "" if outcome.ok else f" -> blockers: {', '.join(outcome.blockers)}"
        lines.append(f"  - {outcome.mode}: {mark}{detail}")

    sample_limit = 5
    if report.missing_required_items:
        lines.append("")
        lines.append("Missing required items:")
        for item in report.missing_required_items[:sample_limit]:
            lines.append(f"  - {item}")
    if report.missing_recommended_items:
        lines.append("")
        lines.append("Missing recommended items:")
        for item in report.missing_recommended_items[:sample_limit]:
            lines.append(f"  - {item}")
    if report.placeholder_hits:
        lines.append("")
        lines.append("Sample unresolved placeholders:")
        for hit in report.placeholder_hits[:sample_limit]:
            lines.append(f"  - {hit.path}:{hit.line} -> {hit.snippet}")
    if report.todo_hits:
        lines.append("")
        lines.append("Sample TODO markers:")
        for hit in report.todo_hits[:sample_limit]:
            lines.append(f"  - {hit.path}:{hit.line} -> {hit.snippet}")
    if report.unmapped_link_rows:
        lines.append("")
        lines.append("Sample unmapped link rows:")
        for row in report.unmapped_link_rows[:sample_limit]:
            lines.append(f"  - {row}")
    if report.parse_errors:
        lines.append("")
        lines.append("Parse errors:")
        for err in report.parse_errors[:sample_limit]:
            lines.append(f"  - {err}")

    lines.append("")
    lines.append("Mode behavior:")
    lines.append("  - scaffold: only checks package structure/files")
    lines.append("  - config: scaffold + no unresolved {{placeholders}}")
    lines.append("  - deploy: config + no TODO markers + all link ports mapped")
    return "\n".join(lines)
