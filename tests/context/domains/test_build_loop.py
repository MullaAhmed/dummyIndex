"""Slice C — build loop: checklist state + task→equipment mapping + CLI."""
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
        {"name": "security-reviewer", "capabilities": ["security", "validation", "audit"]},
    ]
}

# A standard tuned toolkit: one implement-capable agent plus specialists. This
# is the realistic shape `equip` writes (`{label}-implementer` carries
# `["implement"]`). Used by the lexicon-scoring + default-to-implementer tests.
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


# ----- domain: parse + counts ----------------------------------------------

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


# ----- domain: flip_item (atomic + idempotent) -----------------------------

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


# ----- domain: mapping (by capability + fallback) --------------------------

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
    # `_EQUIPMENT` has items but NONE implement-capable (only db + security
    # specialists), so an unmatched task has no implementer to default to →
    # honest fallback: equipment_name is None, fallback True. The
    # "general-purpose" literal is rendered at the CLI.
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
        "Write database migration", _EQUIPMENT["items"], grounding=("spec.md", "plan.md")
    )
    assert choice.grounding == ("spec.md", "plan.md")


# ----- mapping: capability lexicon (the reported bug) -----------------------


def test_mapping_real_implementation_task_routes_to_implementer() -> None:
    # THE BUG: a real implementation task describes WHAT to build and never says
    # the abstract word "implement". Under the old literal capability-token
    # overlap this scored 0 against `python-implementer` (cap `["implement"]`)
    # and fell back to general-purpose. The lexicon expands `implement` to its
    # trigger keywords (build, construct, register, module, server, …), so the
    # implementer wins on score — not on the default branch (a tester/reviewer
    # are present and score 0). This is the proof the bug is fixed.
    task = (
        'app/core/mcp/server.py — build_mcp_server constructs '
        'FastMCP(name="BOS MCP Server", version="3.0.0", auth=…) and registers '
        "tools + resources"
    )
    choice = map_task_to_equipment(task, _EQUIPMENT_WITH_IMPLEMENTER["items"])
    assert choice.fallback is False
    assert choice.equipment_name == "python-implementer"
    assert choice.subagent_type == "python-implementer"


def test_lexicon_covers_all_capabilities() -> None:
    # Guard the single-source alphabet: every Capability member must carry a
    # non-empty keyword set. If the enum grows and the lexicon isn't updated,
    # items declaring the new capability would silently match on name tokens
    # only — reintroducing the score-0 misroute this commit fixes.
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
    # An unmatched task on a manifest that HAS an implement-capable item routes
    # to that implementer (not general-purpose). fallback stays False because a
    # real specialist owns the work.
    choice = map_task_to_equipment(
        "Polish the onboarding copy tone",
        _EQUIPMENT_WITH_IMPLEMENTER["items"],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "python-implementer"
    assert choice.subagent_type == "python-implementer"


# ----- CLI: --next / --check / --status ------------------------------------

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
    # The fixture's db-specialist names no subagent_type, so the dispatch
    # target is a general-purpose downgrade — reported honestly as fallback.
    assert payload["fallback"] is True
    assert payload["complete"] is False  # same schema contract as --next-wave
    assert any("spec.md" in g for g in payload["grounding"])


def test_cli_next_renders_general_purpose_fallback(tmp_path: Path, capsys) -> None:
    # No equipment.json → everything falls back; CLI must render the literal
    # "general-purpose" agent name.
    root = _make_proposal(tmp_path, with_equipment=False)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fallback"] is True
    assert payload["agent"] == "general-purpose"
    assert payload["subagent_type"] == "general-purpose"  # fallback subagent_type


# ----- equipped signal: not-equipped (warn/halt) vs per-item fallback -------


def test_cli_next_json_equipped_true_when_manifest_present(
    tmp_path: Path, capsys
) -> None:
    # A manifest with >=1 item → the repo IS equipped, regardless of whether
    # the current item maps to a specialist.
    root = _make_proposal(tmp_path, with_equipment=True)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["equipped"] is True


def test_cli_next_json_equipped_false_when_manifest_absent(
    tmp_path: Path, capsys
) -> None:
    # No equipment.json at all → the repo is NOT equipped; build should warn.
    root = _make_proposal(tmp_path, with_equipment=False)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["equipped"] is False
    # Back-compat: fallback still reported alongside the new signal.
    assert payload["fallback"] is True


def test_cli_next_corrupt_manifest_counts_as_not_equipped(
    tmp_path: Path, capsys
) -> None:
    # A present-but-unparseable equipment.json collapses to [] in _load_manifest
    # → not equipped. The signal must still fire (json + stderr) — the toolkit is
    # not usable even though the file exists.
    root = _make_proposal(tmp_path, with_equipment=False)
    (root / ".context" / "equipment.json").write_text("!!! not json", encoding="utf-8")

    rc = _build(root, "--next", "--json")
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["equipped"] is False

    rc = _build(root, "--next")
    assert rc == 0
    assert "equipment.json" in capsys.readouterr().err


def test_cli_next_warns_on_stderr_when_not_equipped(tmp_path: Path, capsys) -> None:
    # Human (non-json) --next on an UNEQUIPPED repo must surface a prominent
    # not-equipped warning on stderr pointing at `equip`.
    root = _make_proposal(tmp_path, with_equipment=False)
    rc = _build(root, "--next")
    assert rc == 0
    captured = capsys.readouterr()
    assert "equipment.json" in captured.err
    assert "equip" in captured.err


def test_cli_next_no_not_equipped_warning_when_manifest_present(
    tmp_path: Path, capsys
) -> None:
    # The load-bearing distinction: an EQUIPPED repo whose current item still
    # per-item-falls-back (no specialist matched) must NOT print the
    # not-equipped warning — that's normal, not a missing-toolkit signal.
    root = _make_proposal(tmp_path, with_equipment=True)
    # Override the checklist so the first unchecked item maps to no equipment
    # item → per-item fallback (equipment.json is still present).
    (root / ".context" / "proposals" / _SLUG / "checklist.md").write_text(
        "# Checklist\n\n- [ ] Polish the onboarding copy tone\n",
        encoding="utf-8",
    )

    rc = _build(root, "--next")
    assert rc == 0
    captured = capsys.readouterr()
    # Per-item fallback IS reported (normal), but the not-equipped warning isn't.
    assert "fallback" in captured.out
    assert "equipment.json" not in captured.err


# ----- Task 11: subagent_type passthrough -----------------------------------

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
    assert payload["agent"] == "db-specialist"          # unchanged: equipment name
    assert payload["subagent_type"] == "Data Engineer"  # new: dispatch target


def test_cli_next_text_shows_subagent_type(tmp_path: Path, capsys) -> None:
    root = _make_proposal_with_subagent(tmp_path)
    rc = _build(root, "--next")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Data Engineer" in out


def test_cli_next_json_subagent_type_fallback_when_item_lacks_it(
    tmp_path: Path, capsys
) -> None:
    # The fixture's db-specialist has no subagent_type → CLI falls back to
    # general-purpose for the dispatch target while keeping agent=name — and
    # reports the downgrade as fallback, never a confident equipped match.
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
    # A completed build closes the loop by reconciling new code into .context/,
    # not a bare deterministic rebuild (which would leave the files unassigned).
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
    # Regression: `--status` is a boolean verb here but is also in the shared
    # `_FLAGS_TAKING_VALUE` table (council-log's `--status STATE`). An earlier
    # version routed through `parse_path_and_root`, which swallowed the token
    # after `--status` (e.g. `--root`). Flag order must not matter.
    root = _make_proposal(tmp_path)
    rc = run_build(["--proposal", _SLUG, "--status", "--root", str(root)])
    assert rc == 0
    assert "1/3" in capsys.readouterr().out


# ----- waves: parallel groups in checklist.md --------------------------------
#
# `## Wave N — label` (or `## Group N`) headings open a PARALLEL group: every
# item under one heading is mutually independent and may be dispatched
# concurrently. Any other heading (e.g. the `# Checklist` title) — or no
# heading at all — keeps items serial (each item is its own singleton group),
# so legacy flat checklists behave exactly as before.

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


# ----- domain: group assignment ----------------------------------------------


def test_parse_legacy_flat_checklist_is_serial(tmp_path: Path) -> None:
    # No wave headings (a plain title doesn't count): every item is its own
    # group → strictly serial, identical to pre-wave behaviour.
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
    assert g[0] != g[1]            # solo item is its own group
    assert g[1] == g[2]            # Wave 1 pair shares
    assert g[3] != g[2] and g[3] != g[4]  # serial after a non-wave heading
    assert g[5] == g[6]            # Group 2 pair shares
    assert g == sorted(g)          # groups are monotonic in document order


def test_parse_empty_wave_heading_keeps_groups_contiguous(tmp_path: Path) -> None:
    # A wave heading with no items under it must not burn a group id — ids
    # are assigned lazily at the first item, so they stay contiguous from 0.
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
    # Use a wave-2 item: its group is nonzero, so a flip_item that drops the
    # group (falling back to the dataclass default 0) is caught.
    flipped = flip_item(path, 2)
    assert parsed[2].group > 0
    assert flipped.group == parsed[2].group


# ----- domain: next_wave ------------------------------------------------------


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
    # Back-compat: a flat checklist's wave is always exactly one item — the
    # same item `--next` would report.
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


# ----- CLI: --next-wave -------------------------------------------------------


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
    # Each item carries its own mapping — the two Wave 1 items route to
    # different specialists.
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
