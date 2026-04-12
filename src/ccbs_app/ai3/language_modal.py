"""Unified language + model decision helpers for AI3 modal workflows."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sqlite3
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..ai_routing_policy import classify_task, load_routing_policy

DEFAULT_LANGUAGE_SEED = """
Python
JavaScript
TypeScript
C
C++
C#
Java
Go
Rust
Kotlin
Swift
Objective-C
PHP
Ruby
Perl
Lua
R
Julia
Scala
Haskell
OCaml
F#
Dart
Elixir
Erlang
Clojure
Groovy
PowerShell
Bash
SQL
PL/SQL
Transact-SQL
Assembly
x86 assembly language
ARM NEON
Fortran
COBOL
Pascal
Ada
Lisp
Scheme
Prolog
MATLAB
Wolfram Language
SAS Language
GDScript
Haxe
Nim
Zig
Solidity
Move
V
Verilog
SystemVerilog
VHDL
OpenCL
OpenGL Shading Language
WebAssembly
HTML
CSS
XML
YAML
JSON
TOML
Make
Dockerfile
Terraform
Ansible
Jinja
Jupyter Notebook
A#
lambda Prolog
"""

BUNDLED_LANGUAGE_REGISTRY_FILES: tuple[str, ...] = (
    "config/ai3_language_universe.txt",
    "config/language_universe.txt",
)

LANGUAGE_ALIAS_MAP: dict[str, str] = {
    "py": "Python",
    "python3": "Python",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "node": "JavaScript",
    "nodejs": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "csharp": "C#",
    "c#": "C#",
    "dotnet": "C#",
    "cpp": "C++",
    "cxx": "C++",
    "cc": "C++",
    "c++": "C++",
    "golang": "Go",
    "shell": "Bash",
    "sh": "Bash",
    "zsh": "Bash",
    "ps1": "PowerShell",
    "powershell": "PowerShell",
    "postgresql": "SQL",
    "sqlite": "SQL",
    "mysql": "SQL",
    "tsx": "TypeScript",
    "jsx": "JavaScript",
    "yml": "YAML",
    "a#": "A#",
    "a sharp": "A#",
    "a♯": "A#",
    "lambdaprolog": "lambda Prolog",
    "lambda prolog": "lambda Prolog",
    "λprolog": "lambda Prolog",
}

EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".pyw": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".c": "C",
    ".h": "C",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".cs": "C#",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".swift": "Swift",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".rb": "Ruby",
    ".pl": "Perl",
    ".pm": "Perl",
    ".lua": "Lua",
    ".r": "R",
    ".jl": "Julia",
    ".scala": "Scala",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".mli": "OCaml",
    ".fs": "F#",
    ".fsx": "F#",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".clj": "Clojure",
    ".groovy": "Groovy",
    ".ps1": "PowerShell",
    ".bat": "Batch file",
    ".cmd": "Batch file",
    ".sh": "Bash",
    ".sql": "SQL",
    ".s": "Assembly",
    ".asm": "Assembly",
    ".f": "Fortran",
    ".f90": "Fortran",
    ".f95": "Fortran",
    ".cob": "COBOL",
    ".cbl": "COBOL",
    ".pas": "Pascal",
    ".adb": "Ada",
    ".ads": "Ada",
    ".lisp": "Lisp",
    ".lsp": "Lisp",
    ".scm": "Scheme",
    ".pro": "Prolog",
    ".m": "MATLAB",
    ".wl": "Wolfram Language",
    ".gd": "GDScript",
    ".hx": "Haxe",
    ".nim": "Nim",
    ".zig": "Zig",
    ".sol": "Solidity",
    ".move": "Move",
    ".v": "V",
    ".sv": "SystemVerilog",
    ".vhd": "VHDL",
    ".cl": "OpenCL",
    ".wgsl": "WebGPU Shading Language",
    ".wasm": "WebAssembly",
    ".html": "HTML",
    ".css": "CSS",
    ".xml": "XML",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".dockerfile": "Dockerfile",
    ".tf": "Terraform",
    ".j2": "Jinja",
    ".ipynb": "Jupyter Notebook",
}

_CODE_FENCE_RE = re.compile(r"```([^\n`]*)")
_LANG_HINT_RE = re.compile(
    r"\b(?:in|using|with|for)\s+([A-Za-z0-9#+.\-_/ ]{1,48})\b",
    re.IGNORECASE,
)
_FILE_REF_RE = re.compile(r"\b[\w./\\-]+\.[A-Za-z0-9]{1,12}\b")
_BULLET_PREFIX_RE = re.compile(r"^(?:[-*•]\s+|\d+[.)]\s+)")
_LANG_TAG_FALLBACK_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9#+._-]{0,47}$")

_SCOPE_OFFLINE_TERMS = (
    "offline",
    "local only",
    "strict local",
    "air gap",
    "air-gapped",
    "no internet",
    "without internet",
    "disconnected",
    "on-prem",
)

_SCOPE_REMOTE_TERMS = (
    "cloud",
    "online",
    "internet",
    "github",
    "remote",
    "download",
    "api",
    "web",
    "external",
)

_SCOPE_HYBRID_TERMS = (
    "hybrid",
    "local and cloud",
    "edge and cloud",
    "sync",
    "fallback",
    "split-brain",
    "store-and-forward",
)

_SCOPE_REPO_TERMS = (
    "repo",
    "repository",
    "codebase",
    "this project",
    "this code",
    "local files",
)

_WORKLOAD_PROFILES: dict[str, dict[str, Any]] = {
    "bugfix": {
        "hints": ("bug", "fix", "error", "exception", "stack trace", "failing test", "regression"),
        "languages": ("Python", "TypeScript", "JavaScript", "C#", "Java", "Go", "Rust", "C++"),
    },
    "architecture": {
        "hints": ("architecture", "design", "system", "tradeoff", "migration", "scalability", "distributed"),
        "languages": ("TypeScript", "Python", "Go", "Java", "C#", "Rust", "SQL"),
    },
    "scripting": {
        "hints": ("script", "automation", "cli", "batch", "powershell", "bash", "shell", "cron"),
        "languages": ("PowerShell", "Bash", "Python", "Batch file", "AWK", "Perl"),
    },
    "data": {
        "hints": ("data", "dataset", "analytics", "notebook", "pandas", "etl", "ml", "model training"),
        "languages": ("Python", "SQL", "R", "Julia", "Scala", "MATLAB"),
    },
    "systems": {
        "hints": ("kernel", "driver", "embedded", "firmware", "low level", "memory", "toolchain"),
        "languages": ("C", "C++", "Rust", "Zig", "Assembly", "Go"),
    },
    "web": {
        "hints": ("frontend", "backend", "api server", "react", "vue", "web app", "http"),
        "languages": ("TypeScript", "JavaScript", "HTML", "CSS", "Go", "Python", "PHP"),
    },
    "database": {
        "hints": ("sql", "query", "database", "postgres", "mysql", "schema", "index"),
        "languages": ("SQL", "PL/SQL", "Transact-SQL", "Python"),
    },
    "security": {
        "hints": ("security", "exploit", "reverse", "forensics", "malware", "pentest"),
        "languages": ("Python", "Bash", "PowerShell", "C", "C++", "Assembly", "Rust"),
    },
}

_ROLE_LANGUAGE_BOOSTS: dict[str, tuple[str, ...]] = {
    "hacker": (
        "Bash",
        "PowerShell",
        "Python",
        "C",
        "C++",
        "Rust",
        "Assembly",
        "SQL",
    ),
    "samurai": (
        "TypeScript",
        "Python",
        "Java",
        "C#",
        "Go",
        "Rust",
        "SQL",
        "Bash",
        "PowerShell",
    ),
}


def language_modal_dir(root: Path) -> Path:
    out = root / ".ccbs" / "ai3" / "language_modal"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _json_registry_path(root: Path) -> Path:
    return language_modal_dir(root) / "language_registry.json"


def _sqlite_registry_path(root: Path) -> Path:
    return language_modal_dir(root) / "language_registry.sqlite"


def _parquet_registry_path(root: Path) -> Path:
    return language_modal_dir(root) / "language_registry.parquet"


def _feather_registry_path(root: Path) -> Path:
    return language_modal_dir(root) / "language_registry.feather"


def _seed_input_path(root: Path) -> Path:
    return language_modal_dir(root) / "language_seed.txt"


def _bundled_seed_paths(root: Path) -> list[Path]:
    out: list[Path] = []
    for rel in BUNDLED_LANGUAGE_REGISTRY_FILES:
        path = root / rel
        if path.exists():
            out.append(path)
    return out


def _normalize_language_token(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.casefold()
    lowered = lowered.replace("♯", "#")
    lowered = lowered.replace("λ", "lambda")
    lowered = re.sub(r"[^a-z0-9#+.\- ]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def normalize_language_name(value: str) -> str:
    token = _normalize_language_token(value)
    if not token:
        return ""
    alias = LANGUAGE_ALIAS_MAP.get(token, "")
    if alias:
        return alias
    # Keep operator-heavy names readable while preserving expected casing.
    canonical = re.sub(r"\s+", " ", str(value or "").strip())
    canonical = canonical.replace("♯", "#")
    canonical = canonical.replace("λ", "lambda ")
    canonical = re.sub(r"\s+", " ", canonical).strip()
    if canonical.lower() in {"c++", "c#", "a#"}:
        return canonical.upper().replace("++", "++")
    if canonical.lower() == "lambda prolog":
        return "lambda Prolog"
    if canonical.lower() == "batch file":
        return "Batch file"
    if len(canonical) <= 4 and canonical.isupper():
        return canonical
    return " ".join(part if any(ch.isdigit() for ch in part) else part.capitalize() for part in canonical.split(" "))


def _parse_language_lines(raw: str) -> list[str]:
    if not raw:
        return []
    # Support pasted lists that are newline or CSV based.
    raw_text = str(raw)
    candidate_rows = list(raw_text.splitlines())
    if len(candidate_rows) <= 2 and "," in raw_text:
        try:
            candidate_rows = []
            for csv_row in csv.reader(str(raw).splitlines()):
                candidate_rows.extend(csv_row)
        except Exception:
            pass

    out: list[str] = []
    for line in candidate_rows:
        row = line.strip()
        if not row:
            continue
        if row.startswith("#"):
            continue
        if row.startswith("[@github]"):
            continue
        cleaned = _BULLET_PREFIX_RE.sub("", row).strip()
        if not cleaned:
            continue
        normalized = normalize_language_name(cleaned)
        if normalized:
            out.append(normalized)
    return out


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _git_ls_files(root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    rows: list[str] = []
    for line in str(proc.stdout or "").splitlines():
        item = line.strip()
        if item:
            rows.append(item)
    return rows


def _infer_language_from_path(path: str) -> str:
    lower = str(path or "").strip().lower()
    if not lower:
        return ""
    if lower.endswith("dockerfile"):
        return "Dockerfile"
    ext = Path(lower).suffix
    return EXTENSION_LANGUAGE_MAP.get(ext, "")


def _collect_ccbs_scan_languages(root: Path) -> tuple[list[str], dict[str, Any]]:
    files = _git_ls_files(root)
    if not files:
        files = []
        for item in root.rglob("*"):
            if item.is_file():
                files.append(str(item.relative_to(root)))
            if len(files) > 20000:
                break

    langs: list[str] = []
    for rel in files:
        if "ccbs" not in rel.casefold():
            continue
        inferred = _infer_language_from_path(rel)
        if inferred:
            langs.append(inferred)
    return langs, {"files_scanned": len(files), "ccbs_hits": len(langs)}


def _parse_github_owner_repo(remote_url: str) -> tuple[str, str]:
    raw = str(remote_url or "").strip()
    if not raw:
        return "", ""
    cleaned = raw
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if cleaned.startswith("git@github.com:"):
        tail = cleaned.split(":", 1)[1]
        parts = tail.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return "", ""
    try:
        parsed = urllib.parse.urlparse(cleaned)
    except Exception:
        return "", ""
    host = str(parsed.netloc or "").lower()
    if host not in {"github.com", "www.github.com"}:
        return "", ""
    path = str(parsed.path or "").strip("/")
    pieces = path.split("/")
    if len(pieces) < 2:
        return "", ""
    return pieces[0], pieces[1]


def _git_remote_origin(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return str(proc.stdout or "").strip()


def _repo_scoped_github_languages(root: Path) -> tuple[list[str], dict[str, Any]]:
    files = _git_ls_files(root)
    if not files:
        return [], {"enabled": False, "reason": "git_ls_files_unavailable"}
    langs: list[str] = []
    for rel in files:
        inferred = _infer_language_from_path(rel)
        if inferred:
            langs.append(inferred)
    return langs, {"enabled": True, "source": "repo_scoped", "files_scanned": len(files), "language_hits": len(langs)}


def _external_github_languages(root: Path, enable_external: bool) -> tuple[list[str], dict[str, Any]]:
    if not enable_external:
        return [], {"enabled": False, "reason": "disabled"}

    remote = _git_remote_origin(root)
    owner, repo = _parse_github_owner_repo(remote)
    if not owner or not repo:
        return [], {"enabled": False, "reason": "no_github_origin", "remote": remote}

    token = str(os.environ.get("GITHUB_TOKEN", "")).strip()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{owner}/{repo}/languages"
    req = urllib.request.Request(url=url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return [], {"enabled": True, "source": "github_api", "error": f"http_{exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return [], {"enabled": True, "source": "github_api", "error": str(exc)}

    try:
        payload = json.loads(body)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return [], {"enabled": True, "source": "github_api", "error": "invalid_payload"}
    langs = [normalize_language_name(str(key)) for key in payload.keys()]
    langs = [x for x in langs if x]
    return langs, {"enabled": True, "source": "github_api", "owner": owner, "repo": repo, "language_hits": len(langs)}


def _collect_seed_languages(root: Path, raw_language_text: str = "") -> dict[str, Any]:
    seed = list(_parse_language_lines(DEFAULT_LANGUAGE_SEED))
    from_input = list(_parse_language_lines(raw_language_text))
    seed_file_text = _safe_read_text(_seed_input_path(root))
    from_file = list(_parse_language_lines(seed_file_text))
    bundled_rows: list[str] = []
    bundled_files = _bundled_seed_paths(root)
    for path in bundled_files:
        bundled_rows.extend(_parse_language_lines(_safe_read_text(path)))
    total = seed + bundled_rows + from_input + from_file
    return {
        "languages": total,
        "health": {
            "default_seed": len(seed),
            "bundled_seed": len(bundled_rows),
            "bundled_files": [str(path) for path in bundled_files],
            "payload_seed": len(from_input),
            "file_seed": len(from_file),
        },
    }


def _dedupe_languages(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = normalize_language_name(item)
        if not normalized:
            continue
        key = _normalize_language_token(normalized)
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    out.sort(key=lambda x: x.casefold())
    return out


def _aliases_for_language(language: str) -> list[str]:
    token = _normalize_language_token(language)
    aliases = {language}
    for raw_alias, canonical in LANGUAGE_ALIAS_MAP.items():
        if _normalize_language_token(canonical) == token:
            aliases.add(raw_alias)
    ext_aliases = [ext for ext, lang in EXTENSION_LANGUAGE_MAP.items() if _normalize_language_token(lang) == token]
    aliases.update(ext_aliases)
    out = sorted({str(item).strip() for item in aliases if str(item).strip()}, key=lambda x: x.casefold())
    return out


def _build_registry_payload(
    root: Path,
    *,
    raw_language_text: str = "",
    include_external_github: bool = False,
) -> dict[str, Any]:
    seed_data = _collect_seed_languages(root, raw_language_text=raw_language_text)
    seed_languages = list(seed_data.get("languages", []))
    seed_health = dict(seed_data.get("health", {}))
    ccbs_languages, ccbs_health = _collect_ccbs_scan_languages(root)
    repo_languages, repo_health = _repo_scoped_github_languages(root)
    ext_languages, ext_health = _external_github_languages(root, enable_external=include_external_github)

    merged = seed_languages + ccbs_languages + repo_languages + ext_languages
    unique_languages = _dedupe_languages(merged)

    rows: list[dict[str, Any]] = []
    alias_index: dict[str, str] = {}
    for language in unique_languages:
        aliases = _aliases_for_language(language)
        rows.append(
            {
                "name": language,
                "normalized": _normalize_language_token(language),
                "aliases": aliases,
            }
        )
        for alias in aliases:
            alias_index[_normalize_language_token(alias)] = language
        alias_index[_normalize_language_token(language)] = language

    payload = {
        "version": "ai3-language-modal-v1",
        "generated_at": _safe_now(),
        "root": str(root),
        "languages": rows,
        "alias_index": alias_index,
        "counts": {
            "languages": len(rows),
            "aliases": len(alias_index),
        },
        "source_health": {
            "seed": seed_health,
            "ccbs_scan": ccbs_health,
            "github_repo": repo_health,
            "github_external": ext_health,
        },
    }
    return payload


def _safe_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _write_json_registry(root: Path, payload: dict[str, Any]) -> Path:
    path = _json_registry_path(root)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_sqlite_registry(root: Path, payload: dict[str, Any]) -> Path:
    path = _sqlite_registry_path(root)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS language_entry (
              normalized TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              aliases_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM language_entry")
        now = _safe_now()
        for row in list(payload.get("languages", [])):
            normalized = str(row.get("normalized", "")).strip()
            name = str(row.get("name", "")).strip()
            aliases_json = json.dumps(list(row.get("aliases", [])))
            if not normalized or not name:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO language_entry(normalized, name, aliases_json, updated_at) VALUES (?, ?, ?, ?)",
                (normalized, name, aliases_json, now),
            )
        conn.commit()
    finally:
        conn.close()
    return path


def _write_optional_columnar(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    health: dict[str, Any] = {"parquet": {"written": False}, "feather": {"written": False}}
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # noqa: BLE001
        health["parquet"]["error"] = f"pandas_unavailable:{exc}"
        health["feather"]["error"] = f"pandas_unavailable:{exc}"
        return health

    rows = []
    for row in list(payload.get("languages", [])):
        rows.append(
            {
                "name": str(row.get("name", "")),
                "normalized": str(row.get("normalized", "")),
                "aliases_json": json.dumps(list(row.get("aliases", []))),
            }
        )
    frame = pd.DataFrame(rows)

    parquet_path = _parquet_registry_path(root)
    feather_path = _feather_registry_path(root)

    try:
        frame.to_parquet(parquet_path, index=False)
        health["parquet"]["written"] = True
        health["parquet"]["path"] = str(parquet_path)
    except Exception as exc:  # noqa: BLE001
        health["parquet"]["error"] = str(exc)

    try:
        frame.to_feather(feather_path)
        health["feather"]["written"] = True
        health["feather"]["path"] = str(feather_path)
    except Exception as exc:  # noqa: BLE001
        health["feather"]["error"] = str(exc)
    return health


def rebuild_language_registry(
    root: Path,
    *,
    raw_language_text: str = "",
    include_external_github: bool = False,
) -> dict[str, Any]:
    payload = _build_registry_payload(
        root,
        raw_language_text=raw_language_text,
        include_external_github=include_external_github,
    )
    json_path = _write_json_registry(root, payload)
    sqlite_path = _write_sqlite_registry(root, payload)
    columnar = _write_optional_columnar(root, payload)
    payload["storage"] = {
        "json": {"path": str(json_path), "written": True},
        "sqlite": {"path": str(sqlite_path), "written": True},
        "columnar": columnar,
    }
    return payload


def _load_from_json(root: Path) -> dict[str, Any]:
    path = _json_registry_path(root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_from_sqlite(root: Path) -> dict[str, Any]:
    path = _sqlite_registry_path(root)
    if not path.exists():
        return {}
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT normalized, name, aliases_json FROM language_entry ORDER BY name ASC").fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    if not rows:
        return {}

    languages: list[dict[str, Any]] = []
    alias_index: dict[str, str] = {}
    for row in rows:
        normalized = str(row["normalized"] or "").strip()
        name = str(row["name"] or "").strip()
        try:
            aliases = json.loads(str(row["aliases_json"] or "[]"))
        except Exception:
            aliases = []
        if not isinstance(aliases, list):
            aliases = []
        aliases = [str(item).strip() for item in aliases if str(item).strip()]
        languages.append({"name": name, "normalized": normalized, "aliases": aliases})
        for alias in aliases:
            alias_index[_normalize_language_token(alias)] = name
        alias_index[normalized] = name
    return {
        "version": "ai3-language-modal-v1",
        "generated_at": _safe_now(),
        "languages": languages,
        "alias_index": alias_index,
        "counts": {"languages": len(languages), "aliases": len(alias_index)},
    }


def _load_from_columnar(root: Path, mode: str) -> dict[str, Any]:
    path = _parquet_registry_path(root) if mode == "parquet" else _feather_registry_path(root)
    if not path.exists():
        return {}
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return {}
    try:
        frame = pd.read_parquet(path) if mode == "parquet" else pd.read_feather(path)
    except Exception:
        return {}
    languages: list[dict[str, Any]] = []
    alias_index: dict[str, str] = {}
    for _, row in frame.iterrows():
        name = str(row.get("name", "")).strip()
        normalized = str(row.get("normalized", "")).strip()
        try:
            aliases = json.loads(str(row.get("aliases_json", "[]")))
        except Exception:
            aliases = []
        if not isinstance(aliases, list):
            aliases = []
        aliases = [str(item).strip() for item in aliases if str(item).strip()]
        if not name or not normalized:
            continue
        languages.append({"name": name, "normalized": normalized, "aliases": aliases})
        for alias in aliases:
            alias_index[_normalize_language_token(alias)] = name
        alias_index[normalized] = name
    if not languages:
        return {}
    return {
        "version": "ai3-language-modal-v1",
        "generated_at": _safe_now(),
        "languages": languages,
        "alias_index": alias_index,
        "counts": {"languages": len(languages), "aliases": len(alias_index)},
    }


def load_language_registry(
    root: Path,
    *,
    preferred_storage_mode: str = "auto",
    refresh: bool = False,
    include_external_github: bool = False,
    raw_language_text: str = "",
) -> dict[str, Any]:
    if refresh or not _json_registry_path(root).exists():
        rebuild_language_registry(
            root,
            raw_language_text=raw_language_text,
            include_external_github=include_external_github,
        )

    pref = str(preferred_storage_mode or "auto").strip().lower()
    if pref not in {"auto", "json", "sqlite", "parquet", "feather"}:
        pref = "auto"
    chain = [pref] if pref != "auto" else ["sqlite", "json"]
    if pref == "auto":
        chain = ["sqlite", "parquet", "feather", "json"]
    else:
        chain.extend([mode for mode in ["sqlite", "parquet", "feather", "json"] if mode != pref])

    attempts: list[dict[str, Any]] = []
    payload: dict[str, Any] = {}
    active = ""
    for mode in chain:
        if mode == "json":
            payload = _load_from_json(root)
        elif mode == "sqlite":
            payload = _load_from_sqlite(root)
        elif mode in {"parquet", "feather"}:
            payload = _load_from_columnar(root, mode=mode)
        else:
            payload = {}
        ok = bool(payload.get("languages"))
        attempts.append({"mode": mode, "ok": ok})
        if ok:
            active = mode
            break

    if not payload.get("languages"):
        payload = rebuild_language_registry(
            root,
            raw_language_text=raw_language_text,
            include_external_github=include_external_github,
        )
        active = "json"
        attempts.append({"mode": "rebuild_json", "ok": True})

    payload = dict(payload)
    payload["active_storage_mode"] = active or "json"
    payload["storage_attempts"] = attempts
    payload["preferred_storage_mode"] = pref
    return payload


def ensure_ui_backup(root: Path) -> dict[str, Any]:
    src = Path(__file__).resolve().with_name("ui_shared.py")
    backup_dir = root / ".ccbs" / "ai3" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / "ui_shared.pre_unified_language_modal.py"
    if out.exists():
        return {"created": False, "path": str(out), "source": str(src)}
    try:
        shutil.copy2(src, out)
        return {"created": True, "path": str(out), "source": str(src)}
    except Exception as exc:  # noqa: BLE001
        return {"created": False, "path": str(out), "source": str(src), "error": str(exc)}


def _language_candidates_from_text(message: str, alias_index: dict[str, str]) -> list[str]:
    out: list[str] = []
    text = str(message or "")

    for match in _CODE_FENCE_RE.finditer(text):
        token = str(match.group(1) or "").strip().split(" ")[0].strip()
        normalized = alias_index.get(_normalize_language_token(token), "")
        if normalized:
            out.append(normalized)
            continue
        if _LANG_TAG_FALLBACK_RE.match(token):
            fallback = normalize_language_name(token)
            if fallback:
                out.append(fallback)

    for match in _LANG_HINT_RE.finditer(text):
        token = str(match.group(1) or "").strip()
        normalized = alias_index.get(_normalize_language_token(token), "")
        if normalized:
            out.append(normalized)

    for match in _FILE_REF_RE.finditer(text):
        inferred = _infer_language_from_path(str(match.group(0) or ""))
        if inferred:
            out.append(inferred)

    dedup: list[str] = []
    seen: set[str] = set()
    for item in out:
        key = _normalize_language_token(item)
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return dedup


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = str(text or "").casefold()
    return any(term in lowered for term in terms)


def _classify_workload(message: str) -> dict[str, Any]:
    text = " ".join(str(message or "").strip().split()).casefold()
    if not text:
        return {"class_id": "general", "confidence": 0.45, "signals": []}

    best_class = "general"
    best_score = 0.0
    best_signals: list[str] = []
    for class_id, profile in _WORKLOAD_PROFILES.items():
        hints = tuple(str(item).casefold() for item in profile.get("hints", ()))
        matched = [hint for hint in hints if hint and hint in text]
        if not matched:
            continue
        score = float(len(matched))
        if class_id == "architecture":
            score += 0.4
        if class_id == "systems":
            score += 0.25
        if score > best_score:
            best_class = class_id
            best_score = score
            best_signals = matched[:4]

    if best_class == "general":
        if "test" in text or "refactor" in text:
            return {"class_id": "bugfix", "confidence": 0.58, "signals": ["test/refactor"]}
        if "script" in text or "terminal" in text:
            return {"class_id": "scripting", "confidence": 0.58, "signals": ["script/terminal"]}
        return {"class_id": "general", "confidence": 0.5, "signals": []}

    confidence = min(0.9, 0.56 + (best_score * 0.08))
    return {"class_id": best_class, "confidence": round(confidence, 3), "signals": best_signals}


def _rank_language_candidates(
    *,
    message: str,
    candidates: list[str],
    registry: dict[str, Any],
    active_role: str,
    use_case_class: str,
    workload_class: str,
) -> tuple[str, list[dict[str, Any]], list[str], float]:
    alias_index = dict(registry.get("alias_index", {}))
    registry_rows = list(registry.get("languages", []))
    registry_names = {
        _normalize_language_token(str(row.get("name", "")))
        for row in registry_rows
        if str(row.get("name", "")).strip()
    }
    scores: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    def boost(language: str, delta: float, reason: str) -> None:
        normalized_name = normalize_language_name(language)
        if not normalized_name:
            return
        token = _normalize_language_token(normalized_name)
        canonical = alias_index.get(token, normalized_name)
        if token not in registry_names and _normalize_language_token(canonical) not in registry_names:
            canonical = normalized_name
        scores[canonical] = float(scores.get(canonical, 0.0)) + float(delta)
        reason_rows = reasons.setdefault(canonical, [])
        if reason not in reason_rows:
            reason_rows.append(reason)

    for idx, item in enumerate(candidates):
        rank_boost = max(0.6, 1.35 - (idx * 0.1))
        boost(item, rank_boost, "explicit language signal")

    workload_profile = _WORKLOAD_PROFILES.get(workload_class, {})
    workload_langs = tuple(str(item) for item in workload_profile.get("languages", ()))
    for idx, item in enumerate(workload_langs):
        rank_boost = max(0.16, 0.74 - (idx * 0.07))
        boost(item, rank_boost, f"{workload_class} workload fit")

    role_langs = _ROLE_LANGUAGE_BOOSTS.get(str(active_role).strip().lower(), ())
    for idx, item in enumerate(role_langs):
        role_boost = max(0.08, 0.32 - (idx * 0.03))
        boost(item, role_boost, f"{active_role} role preference")

    if use_case_class == "complex":
        for idx, item in enumerate(("TypeScript", "Python", "Go", "Rust", "Java")):
            boost(item, max(0.07, 0.22 - (idx * 0.03)), "complex task suitability")
    elif use_case_class == "sensitive":
        for idx, item in enumerate(("Python", "SQL", "Bash", "PowerShell")):
            boost(item, max(0.06, 0.18 - (idx * 0.03)), "sensitive task local safety")

    if not scores:
        return "Plain text", [], ["No language ranking signals found; using generic fallback lane."], 0.45

    ranked = sorted(scores.items(), key=lambda item: (-item[1], _normalize_language_token(item[0])))
    top_score = float(ranked[0][1])
    next_score = float(ranked[1][1]) if len(ranked) > 1 else 0.0
    margin = max(0.0, top_score - next_score)
    confidence = max(0.4, min(0.98, 0.55 + min(0.25, top_score / 3.6) + min(0.12, margin / 1.6)))
    ranking_rows: list[dict[str, Any]] = []
    for name, score in ranked[:8]:
        ranking_rows.append(
            {
                "language": name,
                "score": round(float(score), 4),
                "reasons": list(reasons.get(name, []))[:3],
            }
        )
    trace = [
        f"Ranked {len(ranked)} language candidates against {len(registry_rows)} catalog entries.",
        f"Selected language '{ranking_rows[0]['language']}' (score={ranking_rows[0]['score']:.3f}, margin={margin:.3f}).",
    ]
    return str(ranking_rows[0]["language"]), ranking_rows, trace, confidence


def _infer_scope_strategy(
    *,
    message: str,
    offline_mode: str,
    answer_scope: str,
    active_role: str,
    scope_confirmed: bool,
) -> dict[str, Any]:
    text = " ".join(str(message or "").strip().split()).casefold()
    signals = {
        "offline": _contains_any(text, _SCOPE_OFFLINE_TERMS),
        "remote": _contains_any(text, _SCOPE_REMOTE_TERMS),
        "hybrid": _contains_any(text, _SCOPE_HYBRID_TERMS),
        "repo": _contains_any(text, _SCOPE_REPO_TERMS),
    }
    recommended_scope = str(answer_scope or "repo_grounded").strip().lower() or "repo_grounded"
    hybrid_mode = "local_only"
    reason = "scope inherits current selection"
    confidence = 0.56
    prompt_required = False

    if str(offline_mode).strip().lower() == "strict":
        if str(answer_scope).strip().lower() in {"repo_grounded", "general_local"}:
            recommended_scope = str(answer_scope).strip().lower()
        else:
            recommended_scope = "repo_grounded" if signals["repo"] else "general_local"
        hybrid_mode = "local_only"
        reason = "strict offline mode forces local scope"
        confidence = 0.92
    elif signals["offline"] and not signals["remote"]:
        recommended_scope = "repo_grounded" if signals["repo"] else "general_local"
        hybrid_mode = "local_only"
        reason = "prompt requests local/offline execution"
        confidence = 0.8
    elif signals["hybrid"] or (signals["offline"] and signals["remote"]):
        recommended_scope = "remote_allowed"
        hybrid_mode = "local_first_hybrid"
        reason = "prompt indicates hybrid local+cloud workflow"
        confidence = 0.83
    elif signals["remote"]:
        recommended_scope = "remote_allowed"
        hybrid_mode = "balanced_hybrid"
        reason = "prompt requests cloud/online capabilities"
        confidence = 0.76
    elif signals["repo"]:
        recommended_scope = "repo_grounded"
        hybrid_mode = "local_only"
        reason = "prompt is repository-grounded"
        confidence = 0.7

    if recommended_scope != str(answer_scope).strip().lower():
        prompt_required = True
    if not scope_confirmed and (signals["hybrid"] or (signals["offline"] and signals["remote"])):
        prompt_required = True
    if str(active_role).strip().lower() in {"hacker", "samurai"} and not scope_confirmed and signals["remote"]:
        prompt_required = True

    return {
        "recommended_scope": recommended_scope,
        "scope_prompt_required": bool(prompt_required),
        "hybrid_mode": hybrid_mode,
        "scope_reason": reason,
        "scope_confidence": round(float(confidence), 4),
        "signals": signals,
    }


def _rank_model_candidates(
    catalog_rows: list[dict[str, Any]],
    *,
    use_case_class: str,
    offline_mode: str,
    answer_scope: str,
    active_role: str,
    hybrid_mode: str,
) -> tuple[dict[str, Any], list[str], float]:
    traces: list[str] = []
    remote_allowed = offline_mode != "strict" and answer_scope == "remote_allowed"
    ranked: list[tuple[float, dict[str, Any]]] = []
    role_id = str(active_role or "").strip().lower()
    mode_id = str(hybrid_mode or "").strip().lower()

    for row in list(catalog_rows):
        provider = str(row.get("provider", "")).strip().lower()
        model = str(row.get("model", "")).strip()
        base_url = str(row.get("base_url", "")).strip()
        key = str(row.get("key", f"{provider}|{model}|{base_url}")).strip()
        reachable = bool(row.get("reachable", False))
        if not provider or not model:
            continue

        if offline_mode == "strict" and provider in {"codex", "openai"}:
            continue
        if answer_scope != "remote_allowed" and provider in {"codex", "openai"}:
            continue
        if provider in {"codex", "openai"} and not remote_allowed:
            continue

        score = 0.0
        if reachable:
            score += 0.4
        if provider in {"lmstudio", "ollama"}:
            score += 0.35
        elif provider in {"codex", "openai"}:
            score += 0.3
        elif provider == "extractive":
            score += 0.2

        if mode_id == "local_only":
            if provider in {"lmstudio", "ollama"}:
                score += 0.12
            if provider in {"codex", "openai"}:
                score -= 0.3
        elif mode_id == "local_first_hybrid":
            if provider in {"lmstudio", "ollama"}:
                score += 0.12
            if provider in {"codex", "openai"}:
                score += 0.05
        elif mode_id == "balanced_hybrid":
            if provider in {"codex", "openai"}:
                score += 0.12
            if provider in {"lmstudio", "ollama"}:
                score += 0.08

        if use_case_class == "complex":
            if provider in {"codex", "openai", "lmstudio", "ollama"}:
                score += 0.25
        elif use_case_class == "sensitive":
            if provider in {"lmstudio", "ollama"}:
                score += 0.25
            if provider in {"codex", "openai"}:
                score -= 0.2
        else:
            if provider in {"lmstudio", "ollama", "extractive"}:
                score += 0.12

        if provider == "extractive":
            score -= 0.08

        if role_id == "hacker":
            if provider in {"lmstudio", "ollama"}:
                score += 0.08
            if provider == "extractive":
                score -= 0.06
        elif role_id == "samurai":
            model_lower = model.casefold()
            if "coder" in model_lower or "code" in model_lower:
                score += 0.08
            if provider in {"lmstudio", "ollama", "codex", "openai"}:
                score += 0.04

        ranked.append(
            (
                score,
                {
                    "provider": provider,
                    "model": model,
                    "base_url": base_url,
                    "model_key": key,
                    "reachable": reachable,
                    "source": row.get("source", ""),
                },
            )
        )

    if not ranked:
        traces.append("No candidate model from catalog satisfied constraints; using extractive fallback.")
        return (
            {
                "provider": "extractive",
                "model": "extractive",
                "base_url": "",
                "model_key": "extractive|extractive|",
                "reachable": True,
                "source": "fallback",
            },
            traces,
            0.42,
        )

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score, best = ranked[0]
    traces.append(
        f"Ranked {len(ranked)} model candidates ({mode_id or 'hybrid'}); selected {best['provider']}:{best['model']} (score={best_score:.2f})."
    )
    confidence = max(0.35, min(0.98, 0.6 + best_score / 2.0))
    return best, traces, confidence


def build_language_model_decision(
    root: Path,
    *,
    message: str,
    catalog_rows: list[dict[str, Any]],
    offline_mode: str,
    answer_scope: str,
    profile: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_obj = dict(profile or {})
    payload_obj = dict(payload or {})
    metadata = _dict_metadata(payload_obj)
    language_mode = str(payload_obj.get("language_mode", profile_obj.get("language_mode", "auto"))).strip().lower() or "auto"
    manual_language = str(payload_obj.get("manual_language", profile_obj.get("manual_language", ""))).strip()
    storage_mode = str(payload_obj.get("language_storage_mode", profile_obj.get("language_storage_mode", "auto"))).strip().lower() or "auto"
    include_external = str(payload_obj.get("language_external_enrichment", profile_obj.get("language_external_enrichment", "false"))).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    raw_seed = str(payload_obj.get("language_seed_text", "") or "")
    registry = load_language_registry(
        root,
        preferred_storage_mode=storage_mode,
        include_external_github=include_external,
        raw_language_text=raw_seed,
    )
    alias_index = dict(registry.get("alias_index", {}))
    active_role = (
        str(payload_obj.get("active_role", "")).strip().lower()
        or str(metadata.get("active_role", "")).strip().lower()
        or str(profile_obj.get("active_role", "core")).strip().lower()
        or "core"
    )
    scope_confirmed = _to_bool(
        payload_obj.get("scope_confirmed", metadata.get("scope_confirmed", False)),
        default=False,
    )

    policy = load_routing_policy(root)
    task = classify_task(
        message,
        requested_task_type=str(payload_obj.get("task_type_override", "auto")),
        policy=policy,
        metadata=metadata,
        root=root,
    )
    use_case_class = str(task.get("task_type", "simple"))
    workload = _classify_workload(message)
    workload_class = str(workload.get("class_id", "general"))
    candidates = _language_candidates_from_text(message, alias_index)
    selected_language, language_rankings, language_trace, language_conf = _rank_language_candidates(
        message=message,
        candidates=candidates,
        registry=registry,
        active_role=active_role,
        use_case_class=use_case_class,
        workload_class=workload_class,
    )
    scope_strategy = _infer_scope_strategy(
        message=message,
        offline_mode=str(offline_mode),
        answer_scope=str(answer_scope),
        active_role=active_role,
        scope_confirmed=scope_confirmed,
    )

    override_applied = False
    trace: list[str] = []
    if language_mode == "manual" and manual_language:
        normalized_manual = normalize_language_name(manual_language)
        if normalized_manual:
            selected_language = normalized_manual
            override_applied = True
            trace.append(f"Manual language override applied: {selected_language}.")

    if not override_applied:
        if candidates:
            trace.append(f"Detected language candidates from prompt/context: {', '.join(candidates[:4])}.")
        else:
            trace.append("No explicit language detected; using generic fallback lane.")
    trace.extend(language_trace)
    trace.append(
        "Scope strategy: "
        f"{scope_strategy.get('hybrid_mode', 'local_only')} "
        f"(recommended={scope_strategy.get('recommended_scope', answer_scope)}, "
        f"reason={scope_strategy.get('scope_reason', 'n/a')})."
    )

    model_route, route_trace, route_conf = _rank_model_candidates(
        catalog_rows,
        use_case_class=use_case_class,
        offline_mode=offline_mode,
        answer_scope=answer_scope,
        active_role=active_role,
        hybrid_mode=str(scope_strategy.get("hybrid_mode", "local_only")),
    )
    trace.extend(route_trace)
    trace.append(f"Use-case classified as '{use_case_class}' (confidence={task.get('confidence', 'n/a')}).")
    trace.append(
        f"Workload profile classified as '{workload_class}' "
        f"(confidence={workload.get('confidence', 'n/a')})."
    )
    trace.append(f"Storage mode active: {registry.get('active_storage_mode', 'json')}.")

    overall_conf = float(task.get("confidence", 0.6) or 0.6)
    overall_conf = max(0.2, min(0.99, (overall_conf + route_conf + language_conf) / 3.0))
    return {
        "decision_version": "ai3-language-modal-v1",
        "selected_language": selected_language,
        "language_mode": language_mode,
        "manual_language": manual_language,
        "language_candidates": candidates,
        "language_rankings": language_rankings,
        "use_case_class": use_case_class,
        "workload_class": workload_class,
        "provider_route": model_route,
        "confidence": round(overall_conf, 4),
        "explanation_trace": trace,
        "override_applied": override_applied,
        "active_storage_mode": str(registry.get("active_storage_mode", "json")),
        "storage_attempts": list(registry.get("storage_attempts", [])),
        "source_health": dict(registry.get("source_health", {})),
        "scope_recommendation": str(scope_strategy.get("recommended_scope", answer_scope)),
        "scope_prompt_required": bool(scope_strategy.get("scope_prompt_required", False)),
        "hybrid_mode": str(scope_strategy.get("hybrid_mode", "local_only")),
        "scope_reason": str(scope_strategy.get("scope_reason", "")),
        "scope_confidence": float(scope_strategy.get("scope_confidence", 0.0) or 0.0),
        "scope_signals": dict(scope_strategy.get("signals", {})),
        "active_role": active_role,
    }


def _dict_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        out.update(dict(meta))
    for key in ("active_role", "effective_role", "answer_scope", "scope_confirmed", "ui_surface"):
        if key in payload and key not in out:
            out[key] = payload.get(key)
    return out
