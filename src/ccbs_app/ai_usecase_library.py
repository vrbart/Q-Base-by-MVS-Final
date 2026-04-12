"""Generate derived bricks/loops/use-case library from local docs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_TIER_RE = re.compile(r"\bTier\s+(\d+)\b(?:\s*[—:-]\s*(.+))?", re.IGNORECASE)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_docx(path: Path) -> str:
    try:
        from docx import Document  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("python-docx not installed") from exc
    doc = Document(str(path))
    return "\n".join(str(p.text or "").strip() for p in doc.paragraphs if str(p.text or "").strip())


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("pypdf not installed") from exc
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(str(page.extract_text() or ""))
    return "\n".join(parts)


def _risk_from_text(text: str) -> str:
    lower = text.lower()
    high_tokens = [
        "finance",
        "payment",
        "transfer",
        "password",
        "mfa",
        "admin",
        "firewall",
        "delete",
        "install",
        "security",
    ]
    medium_tokens = ["upload", "send", "submit", "email", "web", "database"]
    if any(tok in lower for tok in high_tokens):
        return "high"
    if any(tok in lower for tok in medium_tokens):
        return "medium"
    return "low"


def _approval_from_risk(risk: str) -> str:
    if risk == "high":
        return "explicit_approval_required"
    if risk == "medium":
        return "approval_recommended"
    return "implicit_or_batch_approval"


def _loop_pattern(text: str) -> str:
    lower = text.lower()
    if "retrieve" in lower or "citation" in lower:
        return "plan -> retrieve -> synthesize -> cite -> review"
    if "tool" in lower or "shell" in lower or "filesystem" in lower:
        return "plan -> propose_tool -> approve -> execute -> log"
    if "chat" in lower or "prompt" in lower:
        return "capture_intent -> answer -> refine -> persist_memory"
    return "plan -> execute -> verify -> log"


def _entries_from_text(text: str, source_ref: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    tier_num = ""
    tier_title = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        tier_match = _TIER_RE.search(line)
        if tier_match:
            tier_num = str(tier_match.group(1))
            tier_title = str(tier_match.group(2) or "").strip() or f"Tier {tier_num}"
            continue
        if not line.startswith("-"):
            continue
        capability = line.lstrip("-").strip()
        if len(capability) < 8:
            continue
        risk = _risk_from_text(capability)
        entries.append(
            {
                "tier": f"Tier {tier_num}" if tier_num else "Unscoped",
                "capability": capability,
                "risk_level": risk,
                "approval_trigger": _approval_from_risk(risk),
                "loop_pattern": _loop_pattern(capability),
                "usecase_text": f"{tier_title}: {capability}" if tier_title else capability,
                "source_refs": [source_ref],
                "review_required": True,
            }
        )
    return entries


def _gather_sources(source_dir: Path, include_docx: bool, include_pdf: bool) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    warnings: list[str] = []
    if source_dir.is_file():
        files = [source_dir]
    else:
        files.extend(sorted(source_dir.rglob("*.md")))
        if include_docx:
            files.extend(sorted(source_dir.rglob("*.docx")))
        if include_pdf:
            files.extend(sorted(source_dir.rglob("*.pdf")))
    if not files:
        warnings.append(f"no source files found under {source_dir}")
    return files, warnings


def build_usecase_library(source_dir: Path, include_docx: bool = False, include_pdf: bool = False) -> dict[str, Any]:
    files, warnings = _gather_sources(source_dir, include_docx=include_docx, include_pdf=include_pdf)
    entries: list[dict[str, Any]] = []
    for path in files:
        suffix = path.suffix.lower()
        try:
            if suffix == ".md":
                text = _read_text(path)
            elif suffix == ".docx":
                text = _read_docx(path)
            elif suffix == ".pdf":
                text = _read_pdf(path)
            else:
                continue
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{path.name}: {exc}")
            continue
        source_ref = str(path)
        entries.extend(_entries_from_text(text=text, source_ref=source_ref))

    dedup: dict[str, dict[str, Any]] = {}
    for item in entries:
        key = f"{item['tier']}|{item['capability']}"
        if key not in dedup:
            dedup[key] = item
            continue
        merged_refs = sorted({*dedup[key].get("source_refs", []), *item.get("source_refs", [])})
        dedup[key]["source_refs"] = merged_refs
    result_entries = list(dedup.values())
    result_entries.sort(key=lambda x: (str(x.get("tier", "")), str(x.get("risk_level", "")), str(x.get("capability", ""))))
    return {
        "source_dir": str(source_dir),
        "entries": result_entries,
        "entry_count": len(result_entries),
        "warnings": warnings,
        "include_docx": bool(include_docx),
        "include_pdf": bool(include_pdf),
    }


def library_markdown(payload: dict[str, Any]) -> str:
    rows = list(payload.get("entries", []))
    lines = [
        "# AI Bricks Loops Use-Case Library",
        "",
        f"- Source: {payload.get('source_dir', '')}",
        f"- Entries: {len(rows)}",
        "",
    ]
    warnings = list(payload.get("warnings", []))
    if warnings:
        lines.extend(["## Warnings", ""])
        for row in warnings:
            lines.append(f"- {row}")
        lines.append("")
    lines.extend(
        [
            "## Catalog",
            "",
            "| Tier | Capability | Risk | Approval Trigger | Loop Pattern | Review Required |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| {tier} | {capability} | {risk_level} | {approval_trigger} | {loop_pattern} | {review_required} |".format(
                tier=str(row.get("tier", "")).replace("|", "/"),
                capability=str(row.get("capability", "")).replace("|", "/"),
                risk_level=str(row.get("risk_level", "")),
                approval_trigger=str(row.get("approval_trigger", "")),
                loop_pattern=str(row.get("loop_pattern", "")).replace("|", "/"),
                review_required="true" if bool(row.get("review_required", False)) else "false",
            )
        )
    lines.append("")
    return "\n".join(lines)


def write_library(payload: dict[str, Any], *, output_md: Path, output_json: Path) -> dict[str, Any]:
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(library_markdown(payload), encoding="utf-8")
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "output_md": str(output_md),
        "output_json": str(output_json),
        "entry_count": int(payload.get("entry_count", 0)),
        "warnings": list(payload.get("warnings", [])),
    }

