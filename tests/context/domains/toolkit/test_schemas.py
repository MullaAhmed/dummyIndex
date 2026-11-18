"""Toolkit output validated against the dummyPlane schemas, plus the fallback validator.

The dummyPlane schemas are read from ``$DUMMYPLANE_SCHEMAS_DIR`` or the sibling
``dummyPlane/docs/schemas``. When neither exists the schema-backed tests skip. The
validator-behaviour tests always run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.toolkit import (
    ToolkitError,
    toolkit_list,
    toolkit_mutate,
    toolkit_show,
)
from tests.context.domains.toolkit.schema_check import (
    _minimal,
    load_schema,
    schemas_dir,
    validate,
)

pytestmark = pytest.mark.unit

needs_schemas = pytest.mark.skipif(
    schemas_dir() is None,
    reason="dummyPlane schemas not found; set DUMMYPLANE_SCHEMAS_DIR",
)


def _cfg(tmp_path: Path) -> Path:
    cfg = tmp_path / "srv.json"
    cfg.write_text('{"command": "node"}', encoding="utf-8")
    return cfg


@needs_schemas
def test_list_output_validates(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    toolkit_mutate(
        "add",
        "srv",
        root=root,
        home=home,
        kind="mcp",
        scope="project",
        config_file=_cfg(tmp_path),
    )
    toolkit_mutate(
        "add",
        "codex@openai-codex",
        root=root,
        home=home,
        kind="plugin",
        scope="terminal",
        terminal_id="t-1",
        out_dir=out_dir,
    )
    listing = toolkit_list(root=root, home=home, terminal_id="t-1", out_dir=out_dir)
    validate(listing, load_schema("toolkit-list.json"))


@needs_schemas
def test_fallback_list_validates(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    toolkit_mutate(
        "add",
        "srv",
        root=root,
        home=home,
        kind="mcp",
        scope="project",
        config_file=_cfg(tmp_path),
    )
    listing = toolkit_list(
        root=root, home=home, scope="terminal", terminal_id="t-2", out_dir=out_dir
    )
    validate(listing, load_schema("toolkit-list.json"))


@needs_schemas
def test_show_output_validates_for_terminal_item(
    root: Path, home: Path, out_dir: Path
) -> None:
    toolkit_mutate(
        "add",
        "codex@openai-codex",
        root=root,
        home=home,
        kind="plugin",
        scope="terminal",
        terminal_id="t-3",
        out_dir=out_dir,
    )
    shown = toolkit_show(
        "codex@openai-codex",
        root=root,
        home=home,
        scope="terminal",
        terminal_id="t-3",
        out_dir=out_dir,
    )
    validate(shown, load_schema("toolkit-show.json"))


@needs_schemas
def test_mutate_outputs_validate_for_each_action(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    schema = load_schema("toolkit-mutate.json")
    cfg = _cfg(tmp_path)
    results = [
        toolkit_mutate(
            "add",
            "srv",
            root=root,
            home=home,
            kind="mcp",
            scope="project",
            config_file=cfg,
        ),
        toolkit_mutate(
            "disable", "srv", root=root, home=home, kind="mcp", scope="project"
        ),
        toolkit_mutate(
            "enable", "srv", root=root, home=home, kind="mcp", scope="project"
        ),
        toolkit_mutate(
            "add",
            "srv",
            root=root,
            home=home,
            kind="mcp",
            scope="terminal",
            terminal_id="t-4",
            out_dir=out_dir,
            config_file=cfg,
        ),
        toolkit_mutate(
            "remove",
            "srv",
            root=root,
            home=home,
            kind="mcp",
            scope="terminal",
            terminal_id="t-4",
            out_dir=out_dir,
        ),
    ]
    for result in results:
        validate(result, schema)


@needs_schemas
def test_unchanged_mutation_validates_with_restart_false(
    root: Path, home: Path, tmp_path: Path
) -> None:
    cfg = _cfg(tmp_path)
    toolkit_mutate(
        "add", "srv", root=root, home=home, kind="mcp", scope="project", config_file=cfg
    )
    again = toolkit_mutate(
        "add", "srv", root=root, home=home, kind="mcp", scope="project", config_file=cfg
    )
    assert again["changed"] is False
    assert again["restart_required"] is False
    validate(again, load_schema("toolkit-mutate.json"))


@needs_schemas
def test_schema_check_rejects_a_bad_document() -> None:
    """Guards against a validator that passes everything."""
    bad = {"action": "add", "changed": True}  # missing item, launch_args, ...
    with pytest.raises(AssertionError):
        validate(bad, load_schema("toolkit-mutate.json"))


@needs_schemas
def test_error_envelope_validates(root: Path, home: Path) -> None:
    with pytest.raises(ToolkitError) as exc:
        toolkit_mutate(
            "enable", "ghost", root=root, home=home, kind="skill", scope="project"
        )
    validate(exc.value.to_envelope(), load_schema("error-envelope.json"))


# ----- the fallback validator itself (always runs) --------------------------

_SCHEMA = {
    "type": "object",
    "required": ["kind", "changed"],
    "properties": {
        "kind": {"enum": ["mcp", "skill"]},
        "changed": {"type": "boolean"},
        "name": {"type": "string", "minLength": 1, "pattern": "^[a-z]+$"},
        "items": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/n"}},
        "sha": {"type": ["string", "null"]},
    },
    "$defs": {"n": {"type": "integer"}},
    "if": {"properties": {"changed": {"const": True}}, "required": ["changed"]},
    "then": {"properties": {"restart": {"const": True}}},
}


def _fails(instance: object) -> bool:
    try:
        _minimal(instance, _SCHEMA, _SCHEMA, "$")
    except AssertionError:
        return True
    return False


def test_fallback_accepts_a_conforming_document() -> None:
    assert not _fails(
        {"kind": "mcp", "changed": False, "name": "abc", "items": [1], "sha": None}
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"changed": False},
        {"kind": "plugin", "changed": False},
        {"kind": "mcp", "changed": False, "name": "A1"},
        {"kind": "mcp", "changed": False, "items": []},
        {"kind": "mcp", "changed": False, "items": ["x"]},
        {"kind": "mcp", "changed": True, "restart": False},
        {"kind": "mcp", "changed": "yes"},
    ],
)
def test_fallback_rejects_each_violation(bad: dict) -> None:
    assert _fails(bad)


def test_fallback_null_and_pattern_and_then_branch() -> None:
    assert not _fails({"kind": "mcp", "changed": True, "restart": True})
    assert _fails({"kind": "mcp", "changed": True, "restart": False})
