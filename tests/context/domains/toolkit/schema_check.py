"""Validate toolkit output against the dummyPlane schemas in ``docs/schemas``.

Uses the ``jsonschema`` package when it is importable. Otherwise falls back to a
minimal validator that covers the keywords the toolkit schemas use: ``type``,
``enum``, ``const``, ``required``, ``properties``, ``items``, ``minItems``,
``minLength``, ``pattern``, ``$ref`` into ``$defs``, and ``if``/``then``. The
fallback raises ``AssertionError`` with a JSON path on the first mismatch.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from tests.paths import REPO_ROOT

_TYPES = {
    "string": str,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def schemas_dir() -> Path | None:
    """The dummyPlane schema folder: ``$DUMMYPLANE_SCHEMAS_DIR`` or the sibling repo."""
    override = os.environ.get("DUMMYPLANE_SCHEMAS_DIR")
    candidates = [Path(override)] if override else []
    candidates.append(REPO_ROOT.parent / "dummyPlane" / "docs" / "schemas")
    for candidate in candidates:
        if (candidate / "toolkit-list.json").is_file():
            return candidate
    return None


def load_schema(name: str) -> dict[str, Any]:
    folder = schemas_dir()
    assert folder is not None, "dummyPlane schemas not found"
    return json.loads((folder / name).read_text(encoding="utf-8"))


def jsonschema_available() -> bool:
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return False
    return True


def validate(instance: Any, schema: dict[str, Any]) -> str:
    """Validate; return which validator ran (``jsonschema`` or ``minimal``)."""
    if jsonschema_available():
        import jsonschema

        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
        if errors:
            raise AssertionError(f"{errors[0].message} at {list(errors[0].path)}")
        return "jsonschema"
    _minimal(instance, schema, schema, "$")
    return "minimal"


def _resolve(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    assert ref.startswith("#/"), f"unsupported $ref {ref}"
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _type_ok(value: Any, name: str) -> bool:
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def _minimal(
    value: Any, schema: dict[str, Any], root: dict[str, Any], path: str
) -> None:
    if "$ref" in schema:
        _minimal(value, _resolve(schema["$ref"], root), root, path)
        return
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        assert any(_type_ok(value, n) for n in names), f"{path}: expected {names}"
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: {value!r} not in enum"
    if "const" in schema:
        assert value == schema["const"], f"{path}: must equal {schema['const']!r}"
    if isinstance(value, str):
        if "minLength" in schema:
            assert len(value) >= schema["minLength"], f"{path}: too short"
        if "pattern" in schema:
            assert re.search(schema["pattern"], value), f"{path}: pattern mismatch"
    if isinstance(value, dict):
        for key in schema.get("required", []):
            assert key in value, f"{path}: missing required {key!r}"
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                _minimal(value[key], sub, root, f"{path}.{key}")
    if isinstance(value, list):
        if "minItems" in schema:
            assert len(value) >= schema["minItems"], f"{path}: too few items"
        if "items" in schema:
            for index, item in enumerate(value):
                _minimal(item, schema["items"], root, f"{path}[{index}]")
    if "if" in schema and isinstance(value, dict):
        if _matches(value, schema["if"], root) and "then" in schema:
            _minimal(value, schema["then"], root, path)


def _matches(
    value: dict[str, Any], condition: dict[str, Any], root: dict[str, Any]
) -> bool:
    try:
        _minimal(value, condition, root, "$if")
    except AssertionError:
        return False
    return True
