"""Tests for `dummyindex context equip` — templates-first toolkit rendering."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import _cmd_equip, _project_slug
from dummyindex.context.domains.equip import (
    SCHEMA_VERSION,
    GENERATED_SENTINEL,
    EquipmentItem,
    EquipmentManifest,
    content_hash,
    detect_formatter,
    detect_stack,
    is_safe_to_write,
    render_template,
)
from dummyindex.context.domains.equip import IMPLEMENTER_TEMPLATE


def _write_files_map(context_dir: Path, languages: list[str | None]) -> None:
    files = [
        {"path": f"src/f{i}.x", "language": lang, "size_bytes": 10}
        for i, lang in enumerate(languages)
    ]
    (context_dir / "map").mkdir(parents=True, exist_ok=True)
    (context_dir / "map" / "files.json").write_text(
        json.dumps({"schema_version": 1, "files": files}) + "\n", encoding="utf-8"
    )


# ----- stack detection ------------------------------------------------------


@pytest.mark.unit
def test_detect_stack_picks_dominant_language(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, ["python", "python", "python", "javascript"])
    profile = detect_stack(context_dir)
    assert profile.label == "python"


@pytest.mark.unit
def test_detect_stack_ties_break_alphabetically(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, ["python", "go"])
    profile = detect_stack(context_dir)
    assert profile.label == "go"  # tie -> alphabetical


@pytest.mark.unit
def test_detect_stack_missing_map_is_generic(tmp_path: Path) -> None:
    profile = detect_stack(tmp_path / ".context")
    assert profile.label == "generic"
    assert profile.frameworks == ()


@pytest.mark.unit
def test_detect_stack_ignores_null_languages(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, [None, None, "rust"])
    assert detect_stack(context_dir).label == "rust"


@pytest.mark.unit
def test_detect_stack_surfaces_frameworks_from_manifest(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, ["python"])
    (tmp_path / "pyproject.toml").write_text(
        'dependencies = ["fastapi", "uvicorn"]\n', encoding="utf-8"
    )
    profile = detect_stack(context_dir)
    assert "FastAPI" in profile.frameworks


# ----- formatter detection --------------------------------------------------


@pytest.mark.unit
def test_detect_formatter_ruff(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    assert detect_formatter(tmp_path) == "ruff"


@pytest.mark.unit
def test_detect_formatter_none(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert detect_formatter(tmp_path) is None


# ----- render ---------------------------------------------------------------


@pytest.mark.unit
def test_render_fills_slots_and_grounds(tmp_path: Path) -> None:
    body = render_template(
        IMPLEMENTER_TEMPLATE,
        stack="python",
        conventions=(".context/conventions/naming.md",),
    )
    assert "{{stack}}" not in body
    assert "{{conventions}}" not in body
    assert "{{context_root}}" not in body
    assert "python" in body
    assert ".context/conventions/naming.md" in body
    assert ".context" in body  # grounding present
    assert GENERATED_SENTINEL in body  # sentinel stamped for never-clobber
    # frontmatter MUST lead the file (byte 0) or Claude Code won't discover the
    # agent/skill — the sentinel lives in the body, not before `---`.
    assert body.startswith("---")
    assert body.index("name:") < body.index(GENERATED_SENTINEL)


@pytest.mark.unit
def test_render_empty_conventions_still_grounds(tmp_path: Path) -> None:
    body = render_template(IMPLEMENTER_TEMPLATE, stack="generic", conventions=())
    assert "{{conventions}}" not in body
    assert ".context" in body


# ----- manifest schema ------------------------------------------------------


@pytest.mark.unit
def test_manifest_roundtrip_matches_schema() -> None:
    item = EquipmentItem(
        kind="agent",
        name="python-implementer",
        path=".claude/agents/python-implementer.md",
        source="generated",
        capabilities=("implement",),
        grounded_in=(".context/HOW_TO_USE.md",),
    )
    manifest = EquipmentManifest(schema_version=1, items=(item,))
    data = manifest.to_dict()
    assert data["schema_version"] == 1
    assert data["items"][0]["capabilities"] == ["implement"]
    assert data["items"][0]["grounded_in"] == [".context/HOW_TO_USE.md"]
    # round-trips back into frozen tuples
    back = EquipmentManifest.from_dict(data)
    assert back == manifest
    assert isinstance(back.items[0].capabilities, tuple)


# ----- manifest schema v2 ---------------------------------------------------


@pytest.mark.unit
def test_schema_version_is_2() -> None:
    assert SCHEMA_VERSION == 2


@pytest.mark.unit
def test_item_roundtrips_v2_fields() -> None:
    item = EquipmentItem(
        kind="agent",
        name="python-implementer",
        path=".claude/agents/python-implementer.md",
        source="generated",
        capabilities=("implement",),
        grounded_in=(".context/HOW_TO_USE.md",),
        subagent_type="python-implementer",
        version="1.0.0",
        origin_hash="sha256:deadbeef",
    )
    data = item.to_dict()
    assert data["subagent_type"] == "python-implementer"
    assert data["version"] == "1.0.0"
    assert data["origin_hash"] == "sha256:deadbeef"
    assert EquipmentItem.from_dict(data) == item


@pytest.mark.unit
def test_v1_item_loads_with_none_defaults() -> None:
    """A v1 manifest entry (no new keys) loads with the new fields as None."""
    v1 = {
        "kind": "agent",
        "name": "python-implementer",
        "path": ".claude/agents/python-implementer.md",
        "source": "generated",
        "capabilities": ["implement"],
        "grounded_in": [".context/HOW_TO_USE.md"],
    }
    item = EquipmentItem.from_dict(v1)
    assert item.subagent_type is None
    assert item.version is None
    assert item.origin_hash is None


@pytest.mark.unit
def test_v1_manifest_loads_tolerantly() -> None:
    v1 = {
        "schema_version": 1,
        "items": [
            {
                "kind": "skill",
                "name": "proj-verify",
                "path": ".claude/skills/proj-verify/SKILL.md",
                "source": "generated",
                "capabilities": ["test", "verify"],
                "grounded_in": [".context/HOW_TO_USE.md"],
            }
        ],
    }
    manifest = EquipmentManifest.from_dict(v1)
    assert manifest.schema_version == 1  # preserved as-read
    assert manifest.items[0].version is None


# ----- content hashing ------------------------------------------------------


@pytest.mark.unit
def test_content_hash_stable_and_prefixed() -> None:
    h1 = content_hash("x")
    h2 = content_hash("x")
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert content_hash("y") != h1


# ----- safety: never clobber ------------------------------------------------


@pytest.mark.unit
def test_is_safe_to_write_absent(tmp_path: Path) -> None:
    assert is_safe_to_write(tmp_path / "nope.md") is True


@pytest.mark.unit
def test_is_safe_to_write_ours(tmp_path: Path) -> None:
    p = tmp_path / "ours.md"
    p.write_text(f"{GENERATED_SENTINEL}\nbody\n", encoding="utf-8")
    assert is_safe_to_write(p) is True


@pytest.mark.unit
def test_is_safe_to_write_user_file(tmp_path: Path) -> None:
    p = tmp_path / "theirs.md"
    p.write_text("# my hand-written agent\n", encoding="utf-8")
    assert is_safe_to_write(p) is False


# ----- CLI: equip end to end ------------------------------------------------


def _project(tmp_path: Path, languages: list[str | None]) -> Path:
    context_dir = tmp_path / ".context"
    _write_files_map(context_dir, languages)
    (context_dir / "conventions").mkdir(parents=True, exist_ok=True)
    (context_dir / "conventions" / "naming.md").write_text("# naming\n", encoding="utf-8")
    return tmp_path


@pytest.mark.integration
def test_equip_writes_agent_and_skill(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python", "python"])
    rc = _cmd_equip([str(root)])
    assert rc == 0

    agent = root / ".claude" / "agents" / "python-implementer.md"
    skill = root / ".claude" / "skills" / f"{_project_slug(root)}-verify" / "SKILL.md"
    assert agent.is_file()
    assert skill.is_file()
    # generated files carry the sentinel + reference .context/
    agent_text = agent.read_text(encoding="utf-8")
    assert GENERATED_SENTINEL in agent_text
    assert ".context/conventions/naming.md" in agent_text
    # frontmatter-first: written files must be discoverable by Claude Code.
    assert agent_text.startswith("---")
    assert skill.read_text(encoding="utf-8").startswith("---")


@pytest.mark.integration
def test_equip_writes_manifest_with_schema(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    rc = _cmd_equip([str(root)])
    assert rc == 0

    manifest_path = root / ".context" / "equipment.json"
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2  # equip writes the current SCHEMA_VERSION
    assert len(data["items"]) >= 2
    for item in data["items"]:
        assert item["capabilities"]  # non-empty
        assert item["grounded_in"]   # grounded
        assert ".context/HOW_TO_USE.md" in item["grounded_in"]


@pytest.mark.integration
def test_equip_records_format_hook_when_formatter_present(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    (root / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    rc = _cmd_equip([str(root)])
    assert rc == 0

    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    hooks = [i for i in data["items"] if i["kind"] == "hook"]
    assert hooks and hooks[0]["name"] == "ruff-format"
    assert hooks[0]["capabilities"] == ["format"]
    # the hook is record-only — settings.json is NOT touched
    assert not (root / ".claude" / "settings.json").exists()


@pytest.mark.integration
def test_equip_never_clobbers_user_file(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    agent = root / ".claude" / "agents" / "python-implementer.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    original = "# MY hand-written agent — do not touch\n"
    agent.write_text(original, encoding="utf-8")

    rc = _cmd_equip([str(root)])
    assert rc == 0
    # untouched
    assert agent.read_text(encoding="utf-8") == original
    # and not recorded as written in the manifest
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    names = {i["name"] for i in data["items"]}
    assert "python-implementer" not in names


@pytest.mark.integration
def test_equip_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    rc = _cmd_equip([str(root), "--dry-run"])
    assert rc == 0
    assert not (root / ".claude").exists()
    assert not (root / ".context" / "equipment.json").exists()


@pytest.mark.integration
def test_equip_rejects_unknown_args(tmp_path: Path) -> None:
    root = _project(tmp_path, ["python"])
    rc = _cmd_equip([str(root), "--bogus"])
    assert rc == 2
