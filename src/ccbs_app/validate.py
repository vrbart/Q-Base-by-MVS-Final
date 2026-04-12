"""Brick validation wrappers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _simple_yaml_load(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue

        if stripped.startswith("- ") and current_list_key:
            data.setdefault(current_list_key, []).append(stripped[2:].strip())
            continue

        if ":" not in stripped:
            raise ValueError(f"Invalid YAML line: {raw_line}")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value == "":
            data[key] = []
            current_list_key = key
        else:
            data[key] = value
            current_list_key = None

    return data


def _read_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = _simple_yaml_load(text)
    if not isinstance(data, dict):
        raise ValueError("metadata.yaml must contain a YAML object")
    return data


def load_schema(schema_path: Path) -> dict[str, Any]:
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _validate_required(parsed: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    properties = schema.get("properties", {})

    def _declared_types(field: str) -> list[str]:
        if not isinstance(properties, dict):
            return []
        prop = properties.get(field, {})
        if not isinstance(prop, dict):
            return []
        raw_type = prop.get("type")
        if isinstance(raw_type, str):
            return [raw_type]
        if isinstance(raw_type, list):
            return [t for t in raw_type if isinstance(t, str)]
        return []

    for field in schema.get("required", []):
        if field not in parsed:
            errors.append(f"'{field}' is required")
            continue

        value = parsed.get(field)
        expected = _declared_types(field)

        if "string" in expected:
            if not isinstance(value, str) or not value.strip():
                errors.append(f"'{field}' must be a non-empty string")
            continue

        if "array" in expected:
            if not isinstance(value, list):
                errors.append(f"'{field}' must be an array")
                continue
            min_items = 0
            if isinstance(properties, dict):
                prop = properties.get(field, {})
                if isinstance(prop, dict):
                    raw_min = prop.get("minItems", 0)
                    if isinstance(raw_min, int):
                        min_items = raw_min
            if len(value) < min_items:
                errors.append(f"'{field}' must contain at least {min_items} item(s)")
            continue

        if value is None:
            errors.append(f"'{field}' is required")
    return errors


def validate_one(metadata_path: Path, schema_path: Path) -> tuple[bool, list[str], dict[str, Any]]:
    errors: list[str] = []
    parsed = _read_yaml(metadata_path)
    schema = load_schema(schema_path)
    errors.extend(_validate_required(parsed, schema))
    return len(errors) == 0, errors, parsed


def find_metadata_files(bricks_dir: Path) -> list[Path]:
    return sorted(bricks_dir.glob("*/metadata.yaml"))


def validate_all(bricks_dir: Path, schema_path: Path) -> tuple[bool, list[str], int]:
    failures: list[str] = []
    files = find_metadata_files(bricks_dir)
    for path in files:
        ok, errors, _ = validate_one(path, schema_path)
        if not ok:
            failures.append(f"{path}: {'; '.join(errors)}")
    return len(failures) == 0, failures, len(files)
