"""Build loop: checklist state + task→equipment mapping + CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.build_loop import run as run_build
from dummyindex.context.domains.buildloop import (
    BuildLoopError,
    counts,
    flip_item,
    map_task_to_equipment,
    next_wave,
    parse_checklist,
)

pytestmark = pytest.mark.unit

_SLUG = "add-widget"

_CHECKLIST = """\
# Checklist — add-widget

- [ ] Write database migration for widgets table
- [x] Scaffold the widget API endpoint
- [ ] Add security review of the widget input validation
"""

_EQUIPMENT = {
    "items": [
        {"name": "db-specialist", "capabilities": ["database", "migration", "sql"]},
        {
            "name": "security-reviewer",
            "capabilities": ["security", "validation", "audit"],
        },
    ]
}

# The shape `equip` writes: an implement-capable `{label}-implementer` plus
# specialists.
_EQUIPMENT_WITH_IMPLEMENTER = {
    "items": [
        {
            "name": "python-implementer",
            "subagent_type": "python-implementer",
            "capabilities": ["implement"],
        },
        {
            "name": "python-tester",
            "subagent_type": "python-tester",
            "capabilities": ["test"],
        },
        {
            "name": "python-reviewer",
            "subagent_type": "python-reviewer",
            "capabilities": ["review"],
        },
    ]
}


def _make_proposal(root: Path, *, with_equipment: bool = True) -> Path:
    """Build a tiny `.context/proposals/<slug>/` fixture; return repo root."""
    context_dir = root / ".context"
    proposal_dir = context_dir / "proposals" / _SLUG
    proposal_dir.mkdir(parents=True)
    (proposal_dir / "checklist.md").write_text(_CHECKLIST, encoding="utf-8")
    (proposal_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (proposal_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    if with_equipment:
        (context_dir / "equipment.json").write_text(
            json.dumps(_EQUIPMENT, indent=2), encoding="utf-8"
        )
    return root


# --- domain: parse + counts


def test_parse_checklist_reads_items_and_marks(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    assert len(items) == 3
    assert [it.index for it in items] == [0, 1, 2]
    assert items[0].text == "Write database migration for widgets table"
    assert items[0].done is False
    assert items[1].done is True  # the `- [x]` line


def test_counts_reports_done_total(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    assert counts(items) == (1, 3)


def test_parse_missing_checklist_raises(tmp_path: Path) -> None:
    with pytest.raises(BuildLoopError):
        parse_checklist(tmp_path / "nope.md")


# --- domain: flip_item (atomic + idempotent)


def test_flip_item_by_index_ticks_one_box(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    item = flip_item(path, 0)
    assert item.done is True
    items = parse_checklist(path)
    assert counts(items) == (2, 3)
    # Other items untouched.
    assert items[2].done is False


def test_flip_item_by_substring(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    flip_item(path, "security review")
    items = parse_checklist(path)
    assert items[2].done is True


def test_flip_item_idempotent_on_already_done(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    before = path.read_text(encoding="utf-8")
    item = flip_item(path, 1)  # index 1 is already `- [x]`
    assert item.done is True
    # File content unchanged — true no-op.
    assert path.read_text(encoding="utf-8") == before


def test_flip_item_ambiguous_key_raises(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    with pytest.raises(BuildLoopError):
        flip_item(path, "widget")  # appears in multiple items


# --- domain: mapping (by capability + fallback)


def test_mapping_picks_by_capability() -> None:
    manifest = _EQUIPMENT["items"]
    choice = map_task_to_equipment(
        "Write database migration for widgets table", manifest
    )
    assert choice.fallback is False
    assert choice.equipment_name == "db-specialist"


def test_mapping_picks_security_item() -> None:
    manifest = _EQUIPMENT["items"]
    choice = map_task_to_equipment(
        "Add security review of the widget input validation", manifest
    )
    assert choice.fallback is False
    assert choice.equipment_name == "security-reviewer"


def test_mapping_falls_back_when_nothing_matches() -> None:
    # `_EQUIPMENT` has no implement-capable item to default to, so this falls
    # back; the "general-purpose" literal is rendered at the CLI.
    choice = map_task_to_equipment(
        "Polish the onboarding copy tone", _EQUIPMENT["items"]
    )
    assert choice.fallback is True
    assert choice.equipment_name is None


def test_mapping_empty_manifest_falls_back() -> None:
    choice = map_task_to_equipment("anything at all", [])
    assert choice.fallback is True
    assert choice.equipment_name is None


def test_mapping_threads_grounding() -> None:
    choice = map_task_to_equipment(
        "Write database migration",
        _EQUIPMENT["items"],
        grounding=("spec.md", "plan.md"),
    )
    assert choice.grounding == ("spec.md", "plan.md")


# --- mapping: capability lexicon


def test_mapping_real_implementation_task_routes_to_implementer() -> None:
    # A real implementation task never says the word "implement". The lexicon
    # expands `implement` to trigger keywords (build, construct, …), so the
    # implementer wins on score, not via the default branch.
    task = (
        "app/core/mcp/server.py — build_mcp_server constructs "
        'FastMCP(name="BOS MCP Server", version="3.0.0", auth=…) and registers '
        "tools + resources"
    )
    choice = map_task_to_equipment(task, _EQUIPMENT_WITH_IMPLEMENTER["items"])
    assert choice.fallback is False
    assert choice.equipment_name == "python-implementer"
    assert choice.subagent_type == "python-implementer"


def test_lexicon_covers_all_capabilities() -> None:
    # Every Capability needs a non-empty keyword set, or items declaring a new
    # capability silently match on name tokens only (the score-0 misroute).
    from dummyindex.context.domains.buildloop.mapping import _CAPABILITY_LEXICON
    from dummyindex.context.domains.equip import Capability

    assert set(_CAPABILITY_LEXICON) == set(Capability)
    assert all(len(kws) > 0 for kws in _CAPABILITY_LEXICON.values())


def test_mapping_test_shaped_task_routes_to_tester() -> None:
    choice = map_task_to_equipment(
        "Add pytest coverage for the new parser fixtures",
        _EQUIPMENT_WITH_IMPLEMENTER["items"],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "python-tester"


def test_mapping_review_shaped_task_routes_to_reviewer() -> None:
    choice = map_task_to_equipment(
        "Review and audit the auth flow",
        _EQUIPMENT_WITH_IMPLEMENTER["items"],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "python-reviewer"


def test_mapping_defaults_to_implementer_when_unmatched_and_equipped() -> None:
    # An unmatched task defaults to the manifest's implementer, not a fallback.
    choice = map_task_to_equipment(
        "Polish the onboarding copy tone",
        _EQUIPMENT_WITH_IMPLEMENTER["items"],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "python-implementer"
    assert choice.subagent_type == "python-implementer"


# --- CLI: --next / --check / --status


def _build(root: Path, *verb_args: str) -> int:
    return run_build(["--proposal", _SLUG, "--root", str(root), *verb_args])


def test_cli_next_prints_item_choice_and_grounding(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path)
    rc = _build(root, "--next")
    assert rc == 0
    out = capsys.readouterr().out
    # First unchecked item is index 0 (the migration).
    assert "Write database migration" in out
    assert "db-specialist" in out
    # Grounding paths injected.
    assert "spec.md" in out
    assert "plan.md" in out


def test_cli_next_json(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["item"]["index"] == 0
    assert payload["agent"] == "db-specialist"
    # No subagent_type on the fixture: a general-purpose downgrade is fallback.
    assert payload["fallback"] is True
    assert payload["complete"] is False  # same schema contract as --next-wave
    assert any("spec.md" in g for g in payload["grounding"])


@pytest.mark.parametrize("verb", ["--next", "--next-wave"])
@pytest.mark.parametrize(
    "role_path",
    [".context/equipment/db-specialist.md", ".claude/agents/db-specialist.md"],
)
def test_dispatch_resolves_shared_or_preserved_legacy_mandate(
    tmp_path: Path, capsys, verb: str, role_path: str
) -> None:
    root = _make_proposal(tmp_path)
    body = root / role_path
    body.parent.mkdir(parents=True, exist_ok=True)
    body.write_text("Use the project's actual migration rules.\n", encoding="utf-8")
    manifest = {
        "items": [
            {
                "kind": "agent",
                "name": "db-specialist",
                "path": role_path,
                "capabilities": ["database"],
                "subagent_type": "db-specialist",
            }
        ]
    }
    (root / ".context/equipment.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    assert _build(root, verb, "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    entry = payload["items"][0] if verb == "--next-wave" else payload
    assert entry["role_path"] == role_path
    assert (root / entry["role_path"]).read_text(encoding="utf-8") == body.read_text(
        encoding="utf-8"
    )


def test_cli_next_renders_general_purpose_fallback(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, with_equipment=False)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fallback"] is True
    assert payload["agent"] == "general-purpose"
    assert payload["subagent_type"] == "general-purpose"  # fallback subagent_type


# --- equipped signal: not-equipped (warn/halt) vs per-item fallback


def test_cli_next_json_equipped_true_when_manifest_present(
    tmp_path: Path, capsys
) -> None:
    # Equipped means >=1 manifest item, whether or not this item maps to one.
    root = _make_proposal(tmp_path, with_equipment=True)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["equipped"] is True


def test_cli_next_json_equipped_false_when_manifest_absent(
    tmp_path: Path, capsys
) -> None:
    root = _make_proposal(tmp_path, with_equipment=False)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["equipped"] is False
    # Back-compat: fallback is still reported alongside `equipped`.
    assert payload["fallback"] is True


def test_cli_next_corrupt_manifest_counts_as_not_equipped(
    tmp_path: Path, capsys
) -> None:
    # An unparseable equipment.json collapses to [] in _load_manifest, so the
    # not-equipped signal fires (json + stderr) even though the file exists.
    root = _make_proposal(tmp_path, with_equipment=False)
    (root / ".context" / "equipment.json").write_text("!!! not json", encoding="utf-8")

    rc = _build(root, "--next", "--json")
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["equipped"] is False

    rc = _build(root, "--next")
    assert rc == 0
    assert "equipment.json" in capsys.readouterr().err


def test_cli_next_warns_on_stderr_when_not_equipped(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, with_equipment=False)
    rc = _build(root, "--next")
    assert rc == 0
    captured = capsys.readouterr()
    assert "equipment.json" in captured.err
    assert "equip" in captured.err


def test_cli_next_no_not_equipped_warning_when_manifest_present(
    tmp_path: Path, capsys
) -> None:
    # An EQUIPPED repo whose item falls back per-item must NOT print the
    # not-equipped warning: that is normal, not a missing toolkit.
    root = _make_proposal(tmp_path, with_equipment=True)
    # First unchecked item maps to no equipment item.
    (root / ".context" / "proposals" / _SLUG / "checklist.md").write_text(
        "# Checklist\n\n- [ ] Polish the onboarding copy tone\n",
        encoding="utf-8",
    )

    rc = _build(root, "--next")
    assert rc == 0
    captured = capsys.readouterr()
    assert "fallback" in captured.out
    assert "equipment.json" not in captured.err


# --- subagent_type passthrough

_EQUIPMENT_WITH_SUBAGENT = {
    "items": [
        {
            "name": "db-specialist",
            "subagent_type": "Data Engineer",
            "capabilities": ["database", "migration", "sql"],
        }
    ]
}


def _make_proposal_with_subagent(root: Path) -> Path:
    context_dir = root / ".context"
    proposal_dir = context_dir / "proposals" / _SLUG
    proposal_dir.mkdir(parents=True)
    (proposal_dir / "checklist.md").write_text(_CHECKLIST, encoding="utf-8")
    (proposal_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (proposal_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (context_dir / "equipment.json").write_text(
        json.dumps(_EQUIPMENT_WITH_SUBAGENT, indent=2), encoding="utf-8"
    )
    return root


def test_mapping_threads_subagent_type() -> None:
    choice = map_task_to_equipment(
        "Write database migration for widgets table",
        _EQUIPMENT_WITH_SUBAGENT["items"],
    )
    assert choice.equipment_name == "db-specialist"
    assert choice.subagent_type == "Data Engineer"


def test_mapping_fallback_has_no_subagent_type() -> None:
    choice = map_task_to_equipment("polish the copy", _EQUIPMENT_WITH_SUBAGENT["items"])
    assert choice.fallback is True
    assert choice.subagent_type is None


def test_cli_next_json_emits_subagent_type(tmp_path: Path, capsys) -> None:
    root = _make_proposal_with_subagent(tmp_path)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent"] == "db-specialist"  # equipment name
    assert payload["subagent_type"] == "Data Engineer"  # dispatch target


def test_cli_next_text_shows_subagent_type(tmp_path: Path, capsys) -> None:
    root = _make_proposal_with_subagent(tmp_path)
    rc = _build(root, "--next")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Data Engineer" in out


def test_cli_next_json_subagent_type_fallback_when_item_lacks_it(
    tmp_path: Path, capsys
) -> None:
    # Dispatch target falls back to general-purpose while agent keeps the name;
    # the downgrade is reported as fallback, never a confident match.
    root = _make_proposal(tmp_path)  # _EQUIPMENT items carry no subagent_type
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent"] == "db-specialist"
    assert payload["subagent_type"] == "general-purpose"
    assert payload["fallback"] is True


def test_cli_check_flips_exact_item(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path)
    rc = _build(root, "--check", "database migration")
    assert rc == 0
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    assert items[0].done is True
    assert items[2].done is False


def test_cli_next_then_check_roundtrip(tmp_path: Path, capsys) -> None:
    # The index --next reports must be the index --check resolves: feed it back.
    root = _make_proposal(tmp_path)
    _build(root, "--next", "--json")
    payload = json.loads(capsys.readouterr().out)
    idx = payload["item"]["index"]
    rc = _build(root, "--check", str(idx))
    assert rc == 0
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    assert items[idx].done is True


def test_cli_status_reports_counts(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path)
    rc = _build(root, "--status")
    assert rc == 0
    out = capsys.readouterr().out
    assert "1/3" in out
    assert "reconcile" not in out  # not complete yet


def test_cli_status_prints_reconcile_hint_when_complete(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path)
    _build(root, "--check", "0")
    _build(root, "--check", "2")  # index 1 already done → now 3/3
    capsys.readouterr()  # drain
    rc = _build(root, "--status")
    assert rc == 0
    out = capsys.readouterr().out
    assert "3/3" in out
    # Reconcile, not a bare rebuild (which would leave new files unassigned).
    assert "dummyindex context reconcile" in out


def test_cli_status_json_complete_has_next_step(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path)
    _build(root, "--check", "0")
    _build(root, "--check", "2")
    capsys.readouterr()
    rc = _build(root, "--status", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["complete"] is True
    assert payload["next_step"] == "dummyindex context reconcile"


def test_cli_requires_proposal(capsys) -> None:
    rc = run_build(["--status"])
    assert rc == 2
    assert "proposal" in capsys.readouterr().err


def test_cli_requires_exactly_one_verb(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path)
    rc = run_build(["--proposal", _SLUG, "--root", str(root)])
    assert rc == 2
    assert "verb" in capsys.readouterr().err


def test_cli_status_with_root_after_status_flag(tmp_path: Path, capsys) -> None:
    # `--status` is boolean here but takes a value in the shared
    # `_FLAGS_TAKING_VALUE` table (council-log), so a generic parser would
    # swallow the next token (`--root`). Flag order must not matter.
    root = _make_proposal(tmp_path)
    rc = run_build(["--proposal", _SLUG, "--status", "--root", str(root)])
    assert rc == 0
    assert "1/3" in capsys.readouterr().out


# --- waves: parallel groups in checklist.md
# `## Wave N — label` / `## Group N` headings open a PARALLEL group of mutually
# independent items. Any other heading, or none, keeps items serial (singleton
# groups), so legacy flat checklists are unchanged.

_WAVE_CHECKLIST = """\
# Checklist — add-widget

## Wave 1 — schema + validation
- [ ] Write database migration for widgets table
- [ ] Add security review of the widget input validation

## Wave 2 — wiring
- [ ] Scaffold the widget API endpoint
"""


def _make_wave_proposal(root: Path, *, checklist: str = _WAVE_CHECKLIST) -> Path:
    root = _make_proposal(root)
    (root / ".context" / "proposals" / _SLUG / "checklist.md").write_text(
        checklist, encoding="utf-8"
    )
    return root


# --- domain: group assignment


def test_parse_legacy_flat_checklist_is_serial(tmp_path: Path) -> None:
    # No wave headings (a plain title doesn't count): strictly serial.
    root = _make_proposal(tmp_path)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    groups = [it.group for it in items]
    assert len(set(groups)) == len(items)
    assert groups == sorted(groups)


def test_parse_wave_headings_group_items(tmp_path: Path) -> None:
    root = _make_wave_proposal(tmp_path)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    assert len(items) == 3
    # Wave 1 items share a group; Wave 2 starts a later one.
    assert items[0].group == items[1].group
    assert items[2].group > items[0].group


def test_parse_group_heading_spelling_and_reset(tmp_path: Path) -> None:
    # `## Group N` works like `## Wave N`; a non-wave heading in between
    # closes the open group so following items are serial again.
    checklist = """\
- [ ] solo before any heading

## Wave 1
- [ ] a
- [ ] b

### Notes
- [ ] serial after notes
- [ ] serial too

## Group 2
- [ ] c
- [ ] d
"""
    root = _make_wave_proposal(tmp_path, checklist=checklist)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    g = [it.group for it in items]
    assert g[0] != g[1]  # solo item is its own group
    assert g[1] == g[2]  # Wave 1 pair shares
    assert g[3] != g[2] and g[3] != g[4]  # serial after a non-wave heading
    assert g[5] == g[6]  # Group 2 pair shares
    assert g == sorted(g)  # groups are monotonic in document order


def test_parse_empty_wave_heading_keeps_groups_contiguous(tmp_path: Path) -> None:
    # Ids are assigned lazily at the first item, so an empty wave burns none.
    checklist = """\
## Wave 1 — accidentally empty

## Wave 2 — real work
- [ ] a
- [ ] b

## Wave 3
- [ ] c
"""
    root = _make_wave_proposal(tmp_path, checklist=checklist)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    assert [it.group for it in items] == [0, 0, 1]


def test_flip_item_preserves_group(tmp_path: Path) -> None:
    root = _make_wave_proposal(tmp_path)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    parsed = parse_checklist(path)
    # A wave-2 item's group is nonzero, so dropping it to the default 0 shows.
    flipped = flip_item(path, 2)
    assert parsed[2].group > 0
    assert flipped.group == parsed[2].group


# --- domain: next_wave


def test_next_wave_returns_all_unchecked_in_first_incomplete_group(
    tmp_path: Path,
) -> None:
    root = _make_wave_proposal(tmp_path)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    wave = next_wave(items)
    assert [it.index for it in wave] == [0, 1]


def test_next_wave_advances_after_wave_completes(tmp_path: Path) -> None:
    root = _make_wave_proposal(tmp_path)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    flip_item(path, 0)
    flip_item(path, 1)
    wave = next_wave(parse_checklist(path))
    assert [it.index for it in wave] == [2]


def test_next_wave_holds_at_earlier_incomplete_wave(tmp_path: Path) -> None:
    # One leftover in Wave 1 gates Wave 2: only the leftover is returned.
    root = _make_wave_proposal(tmp_path)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    flip_item(path, 0)
    wave = next_wave(parse_checklist(path))
    assert [it.index for it in wave] == [1]


def test_next_wave_serial_checklist_yields_single_item(tmp_path: Path) -> None:
    # Back-compat: a flat checklist's wave is the one item `--next` reports.
    root = _make_proposal(tmp_path)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    wave = next_wave(items)
    assert [it.index for it in wave] == [0]


def test_next_wave_empty_when_all_done(tmp_path: Path) -> None:
    root = _make_wave_proposal(tmp_path)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    for idx in (0, 1, 2):
        flip_item(path, idx)
    assert next_wave(parse_checklist(path)) == ()


# --- CLI: --next-wave


def test_cli_next_wave_json_emits_all_wave_items_with_agents(
    tmp_path: Path, capsys
) -> None:
    root = _make_wave_proposal(tmp_path)
    rc = _build(root, "--next-wave", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["proposal"] == _SLUG
    assert payload["equipped"] is True
    # Opaque 0-based group id (NOT the `N` from `## Wave N`).
    assert payload["group"] == 0
    items = payload["items"]
    assert [it["index"] for it in items] == [0, 1]
    # Each item carries its own mapping.
    assert items[0]["agent"] == "db-specialist"
    assert items[1]["agent"] == "security-reviewer"
    assert all("subagent_type" in it and "fallback" in it for it in items)
    # Grounding is shared wave-wide.
    assert any("spec.md" in g for g in payload["grounding"])


def test_cli_next_wave_human_lists_every_item(tmp_path: Path, capsys) -> None:
    root = _make_wave_proposal(tmp_path)
    rc = _build(root, "--next-wave")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Write database migration" in out
    assert "security review" in out
    assert "db-specialist" in out
    assert "security-reviewer" in out
    # Wave 2's item is NOT offered yet.
    assert "Scaffold the widget API endpoint" not in out


def test_large_wave_dispatch_is_bounded_and_resumable(tmp_path, capsys):
    root = _make_wave_proposal(tmp_path)
    path = root / ".context/proposals" / _SLUG / "checklist.md"
    path.write_text(
        "## Wave 1\n" + "".join(f"- [ ] Task {i} repair source\n" for i in range(500)),
        encoding="utf-8",
    )
    assert _build(root, "--next-wave", "--json") == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert len(output.encode("utf-8")) <= 65_536
    assert len(payload["items"]) <= 8
    assert payload["group_total"] == 500 and payload["truncated"]
    first_ids = {item["task_id"] for item in payload["items"]}
    for item in payload["items"]:
        flip_item(path, item["task_id"])
    assert _build(root, "--next-wave", "--json") == 0
    assert first_ids.isdisjoint(
        item["task_id"] for item in json.loads(capsys.readouterr().out)["items"]
    )


def test_cli_next_wave_serial_checklist_matches_next(tmp_path: Path, capsys) -> None:
    # On a legacy flat checklist the wave is exactly the single `--next` item.
    root = _make_proposal(tmp_path)
    rc = _build(root, "--next-wave", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [it["index"] for it in payload["items"]] == [0]


def test_cli_next_wave_all_done_prints_reconcile(tmp_path: Path, capsys) -> None:
    root = _make_wave_proposal(tmp_path)
    for idx in ("0", "1", "2"):
        _build(root, "--check", idx)
    capsys.readouterr()  # drain
    rc = _build(root, "--next-wave", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["complete"] is True
    assert payload["items"] == []
    assert payload["next_step"] == "dummyindex context reconcile"


def test_cli_next_wave_warns_on_stderr_when_not_equipped(
    tmp_path: Path, capsys
) -> None:
    root = _make_proposal(tmp_path, with_equipment=False)
    rc = _build(root, "--next-wave")
    assert rc == 0
    captured = capsys.readouterr()
    assert "equipment.json" in captured.err
    assert "equip" in captured.err


def test_cli_next_wave_json_reports_equipped_false(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, with_equipment=False)
    rc = _build(root, "--next-wave", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["equipped"] is False
    # Every item renders the general-purpose fallback.
    assert all(it["subagent_type"] == "general-purpose" for it in payload["items"])


def test_cli_next_wave_is_exclusive_with_next(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path)
    rc = _build(root, "--next", "--next-wave")
    assert rc == 2
    assert "verb" in capsys.readouterr().err


def test_cli_next_json_missing_capability_signal_on_specialist_fallback(
    tmp_path: Path, capsys
) -> None:
    # Unequipped, the db-migration item falls back; its text implies a
    # specialist capability, so build emits a signal for `equip discover`.
    root = _make_proposal(tmp_path, with_equipment=False)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fallback"] is True
    assert payload["missing_capability"] == ["database"]


def test_cli_next_json_no_missing_capability_when_specialist_equipped(
    tmp_path: Path, capsys
) -> None:
    # The db-specialist covers the capability, so no signal, even though the
    # dispatch downgrades to general-purpose (no subagent_type on the fixture).
    root = _make_proposal(tmp_path, with_equipment=True)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "missing_capability" not in payload


def test_cli_status_json_carries_auto_recouncil_end_to_end(
    tmp_path: Path, capsys
) -> None:
    """Config `build.auto_recouncil` reaches the --status payload: default
    true with no config, explicit false honoured."""
    from dataclasses import replace

    from dummyindex.context.domains.config import (
        BuildPolicy,
        default_config,
        write_config,
    )

    root = _make_proposal(tmp_path)
    context_dir = root / ".context"

    _build(root, "--check", "0")
    capsys.readouterr()
    rc = _build(root, "--status", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_recouncil"] is True  # default: recouncil after the wave

    write_config(
        context_dir, replace(default_config(), build=BuildPolicy(auto_recouncil=False))
    )
    capsys.readouterr()
    rc = _build(root, "--status", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["auto_recouncil"] is False  # the durable opt-out is honoured


def test_ambiguous_checklist_key_lists_candidates(tmp_path: Path) -> None:
    """The ambiguity error names the matching items (index + text), so the
    caller can retry with an index without a second lookup command."""
    root = _make_proposal(tmp_path)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    items = parse_checklist(path)
    # Find a substring shared by at least two items, then flip by it.
    shared = None
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            for word in a.text.lower().split():
                if len(word) >= 3 and word in b.text.lower():
                    shared = word
                    break
            if shared:
                break
        if shared:
            break
    assert shared, "fixture checklist must contain two items sharing a word"

    with pytest.raises(BuildLoopError) as excinfo:
        flip_item(path, shared)

    message = str(excinfo.value)
    assert "ambiguous checklist key" in message
    assert "retry with an index" in message
    hits = [it for it in items if shared in it.text.lower()]
    for hit in hits[:5]:
        assert f"{hit.index}: {hit.text}" in message


# ----- live-item refusal ------------------------------------------------------

_LIVE_CHECKLIST = (
    "## Wave 1\n- [ ] Add parser\n- [ ] Run a live test against production\n"
)


def test_next_wave_refuses_live_items(tmp_path: Path, capsys) -> None:
    root = _make_wave_proposal(tmp_path, checklist=_LIVE_CHECKLIST)
    assert _build(root, "--next-wave", "--json") != 0
    err = capsys.readouterr().err
    assert "live test against production" in err
    assert "Add parser" not in err


def test_next_wave_allows_live_ok_and_clean(tmp_path: Path) -> None:
    ok = "## Wave 1\n- [ ] Live test <!-- live-ok: fixture name -->\n"
    assert _build(_make_wave_proposal(tmp_path, checklist=ok), "--next-wave") == 0
    clean = tmp_path / "c"
    clean.mkdir()
    assert _build(_make_wave_proposal(clean), "--next-wave") == 0


def test_scaffold_checklist_states_live_rule() -> None:
    from dummyindex.context.domains.proposals.store import _checklist_template

    text = _checklist_template("x")
    assert "No live-testing/production steps" in text
    assert "live-ok" in text


def test_closeout_moves_flagged_live_item_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    from dummyindex.context.domains.buildloop.checklist_lint import live_items
    from dummyindex.context.domains.proposals import closeout_workspace
    from dummyindex.context.domains.proposals.retirement import (
        ADMIN_FILES,
        workspace_inventory,
    )

    monkeypatch.setattr(
        "dummyindex.context.domains.proposals.closeout.head_commit",
        lambda _root: "rev",
    )
    context = tmp_path / ".context"
    ws = context / "proposals" / "work"
    ws.mkdir(parents=True)
    (ws / "proposal.json").write_text(
        json.dumps({"slug": "work", "status": "in_progress"}), encoding="utf-8"
    )
    cl = ws / "checklist.md"
    cl.write_text(
        "- [x] Implement\n- [ ] Live test against production\n", encoding="utf-8"
    )
    inventory = workspace_inventory(ws)
    item = parse_checklist(cl)[1]
    assert live_items(parse_checklist(cl)) == (item,)
    receipt = closeout_workspace(
        context,
        "proposal",
        "work",
        {
            "state": "implemented",
            "source_commit": "rev",
            "reviewed_files": inventory,
            "discarded": {
                n: "nothing durable left" for n in inventory if n not in ADMIN_FILES
            },
            "pending_verification": [
                {"item_id": item.item_id, "description": "Live test"}
            ],
        },
    )
    assert len(receipt["pending_verification"]) == 1
    assert all(i.done for i in parse_checklist(cl))
    assert "Live test" not in cl.read_text()


def test_next_refuses_live_items(tmp_path: Path, capsys) -> None:
    # The serial --next verb applies the same live-item refusal as --next-wave.
    root = _make_wave_proposal(tmp_path, checklist=_LIVE_CHECKLIST)
    assert _build(root, "--next", "--json") == 2
    captured = capsys.readouterr()
    assert "live test against production" in captured.err
    assert captured.out == ""


def test_domain_dimension_agents_are_not_dispatched(tmp_path: Path, capsys) -> None:
    # Domain agents are read-only knowledge holders: never a dispatch target,
    # even when they are the best capability match for the item.
    root = _make_wave_proposal(tmp_path)
    manifest = {
        "items": [
            {
                "kind": "agent",
                "name": "p-migration-domain",
                "subagent_type": "p-migration-domain",
                "capabilities": ["database", "migration", "sql"],
                "dimension": "domain",
            },
            {
                "kind": "agent",
                "name": "p-migration-procedure",
                "subagent_type": "p-migration-procedure",
                "capabilities": ["database", "migration", "sql"],
                "dimension": "procedure",
            },
        ]
    }
    (root / ".context" / "equipment.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    assert _build(root, "--next-wave", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    used = {e["subagent_type"] for e in payload["items"]}
    assert "p-migration-domain" not in used
