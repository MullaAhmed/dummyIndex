"""Build-loop routing — item-kind matcher, dispatchable pool, GATE/via, skip.

Companion to ``test_build_loop.py`` (split for file-size discipline). Covers
the C7 build-routing fixes:

- the item→agent matcher is item-kind aware: implementation-kind items
  default to the stack implementer; a single incidental specialist token
  ("review-ready", "comment added") never outweighs it; a leading specialist
  verb ("Review …", "Test …") or a multi-token specialist match ("pytest",
  "coverage") still reaches the specialist;
- ``kind: skill``/``hook`` manifest entries and ``kind: agent`` records
  without a ``subagent_type`` are never offered as Task dispatch targets;
- a matched entry that lacks ``subagent_type`` is reported as
  ``fallback: true`` (a general-purpose downgrade, not a confident match);
- ``**GATE**`` and ``— via <tool>`` items are structural: parsed onto
  ``ChecklistItem``, marked ``dispatch: main-session`` in both output modes,
  never mapped to an agent; the via tag is surfaced as a binding directive;
- ``--skip <item> --reason "…"`` records an annotated ``- [~]`` skip instead
  of a bare tick.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.build_loop import run as run_build
from dummyindex.context.domains.buildloop import (
    BuildLoopError,
    DispatchMode,
    dispatch_mode,
    flip_item,
    map_task_to_equipment,
    parse_checklist,
    skip_item,
)

pytestmark = pytest.mark.unit

_SLUG = "gallery"

_IMPLEMENTER = {
    "name": "python-implementer",
    "subagent_type": "python-implementer",
    "kind": "agent",
    "capabilities": ["implement"],
}
_TESTER = {
    "name": "python-tester",
    "subagent_type": "python-tester",
    "kind": "agent",
    "capabilities": ["test"],
}
_REVIEWER = {
    "name": "python-reviewer",
    "subagent_type": "python-reviewer",
    "kind": "agent",
    "capabilities": ["review"],
}
_DOCS_SPECIALIST = {
    "name": "backend-docs-specialist",
    "subagent_type": "backend-docs-specialist",
    "kind": "agent",
    "capabilities": ["docs"],
}
_DB_SPECIALIST = {
    "name": "db-specialist",
    "subagent_type": "db-specialist",
    "kind": "agent",
    "capabilities": ["database"],
}


def _make_proposal(
    root: Path,
    *,
    checklist: str,
    equipment: dict | None = None,
) -> Path:
    context_dir = root / ".context"
    proposal_dir = context_dir / "proposals" / _SLUG
    proposal_dir.mkdir(parents=True)
    (proposal_dir / "checklist.md").write_text(checklist, encoding="utf-8")
    (proposal_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (proposal_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    if equipment is not None:
        (context_dir / "equipment.json").write_text(
            json.dumps(equipment, indent=2), encoding="utf-8"
        )
    return root


def _build(root: Path, *verb_args: str) -> int:
    return run_build(["--proposal", _SLUG, "--root", str(root), *verb_args])


# ----- domain: item-kind aware matcher (margin over the implementer) --------


def test_code_item_with_comment_added_routes_to_implementer() -> None:
    # THE BUG: 'comment' sat in the DOCS lexicon, so a code item mentioning
    # "comment added" routed to the docs specialist on a single incidental
    # token. Implementation-kind items must default to the stack implementer.
    choice = map_task_to_equipment(
        "Update read endpoints, comment added (app/core/resources/assets/"
        "reads.py:42-116)",
        [_IMPLEMENTER, _DOCS_SPECIALIST],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "python-implementer"


def test_incidental_review_token_loses_to_implementer() -> None:
    # "review-ready" is an adjective on an implementation item, not a review
    # task. A single incidental specialist token must not beat the implementer.
    choice = map_task_to_equipment(
        "Wire the gallery upload component and mark it review-ready",
        [_IMPLEMENTER, _REVIEWER],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "python-implementer"


def test_leading_review_verb_routes_to_reviewer() -> None:
    # The item's leading verb is its kind: "Review …" is review work even
    # when implementer tokens ("module") appear later in the text.
    choice = map_task_to_equipment(
        "Review the new auth module",
        [_IMPLEMENTER, _REVIEWER],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "python-reviewer"


def test_pytest_item_routes_to_tester_despite_impl_verb() -> None:
    # A test-kind item ("Write pytest tests …") leads with an implementer
    # verb but carries multiple test tokens — the tester must win.
    choice = map_task_to_equipment(
        "Write pytest tests for the checklist parser",
        [_IMPLEMENTER, _TESTER],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "python-tester"


def test_docs_item_still_routes_to_docs_specialist() -> None:
    # Dropping 'comment' from the DOCS lexicon must not orphan real docs
    # work — readme/changelog/docstring tokens still reach the docs
    # specialist over the implementer's incidental verb match.
    choice = map_task_to_equipment(
        "Update the README and changelog for the release",
        [_IMPLEMENTER, _DOCS_SPECIALIST],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "backend-docs-specialist"


def test_strong_specialist_match_still_beats_implementer() -> None:
    choice = map_task_to_equipment(
        "Write database migration for widgets table",
        [_IMPLEMENTER, _DB_SPECIALIST],
    )
    assert choice.fallback is False
    assert choice.equipment_name == "db-specialist"


# ----- CLI: dispatchable pool (skills/hooks/un-typed records excluded) ------

_VERIFY_ITEM_CHECKLIST = """\
# Checklist — gallery

- [ ] Verify the upload flow end-to-end (e2e smoke check)
"""

_TOOLKIT_WITH_ADAPTERS = {
    "items": [
        _IMPLEMENTER,
        {"name": "frontend-verify", "kind": "skill", "capabilities": ["verify"]},
        {"name": "prettier-format", "kind": "hook", "capabilities": ["format"]},
    ]
}

_TOOLKIT_WITH_PLUGIN_RECORD = {
    "items": [
        _IMPLEMENTER,
        # Shape `equip discover install` records for a native plugin: kind is
        # hardcoded "agent" but there is no subagent_type to dispatch.
        {"name": "verify-bridge", "kind": "agent", "subagent_type": None,
         "capabilities": ["verify"]},
    ]
}


def test_cli_skill_and_hook_entries_never_win_the_agent_match(
    tmp_path: Path, capsys
) -> None:
    # THE BUG: "frontend-verify" (kind: skill) won on token overlap and was
    # emitted as the agent with subagent_type silently downgraded to
    # general-purpose and fallback: false. Skills/hooks are execution
    # adapters, not Task targets — they must never be the mapped agent.
    root = _make_proposal(
        tmp_path, checklist=_VERIFY_ITEM_CHECKLIST, equipment=_TOOLKIT_WITH_ADAPTERS
    )
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent"] == "python-implementer"
    assert payload["subagent_type"] == "python-implementer"
    assert payload["fallback"] is False
    assert payload["equipped"] is True


def test_cli_agent_record_without_subagent_type_is_not_dispatchable(
    tmp_path: Path, capsys
) -> None:
    root = _make_proposal(
        tmp_path,
        checklist=_VERIFY_ITEM_CHECKLIST,
        equipment=_TOOLKIT_WITH_PLUGIN_RECORD,
    )
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent"] == "python-implementer"
    assert payload["subagent_type"] == "python-implementer"


def test_cli_legacy_manifest_without_subagent_types_reports_downgrade(
    tmp_path: Path, capsys
) -> None:
    # Legacy manifests (no kind / no subagent_type) still match by capability,
    # but the general-purpose downgrade must be honest: fallback true, never a
    # confident equipped match.
    legacy = {"items": [
        {"name": "db-specialist", "capabilities": ["database", "migration", "sql"]},
    ]}
    root = _make_proposal(
        tmp_path,
        checklist="# Checklist\n\n- [ ] Write database migration for widgets table\n",
        equipment=legacy,
    )
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent"] == "db-specialist"
    assert payload["subagent_type"] == "general-purpose"
    assert payload["fallback"] is True


# ----- domain: GATE / `— via <tool>` are structural --------------------------

_ROUTED_CHECKLIST = """\
# Checklist — gallery

## Wave 1 — decision + bridge + code
- [ ] **GATE** — Decide the RLS/tenant-isolation model for widgets (blocks all DDL)
- [ ] Export BCO-0 illustrations into the gallery — via canvas-to-code:start
- [ ] Write database migration for widgets table
"""

_TOOLKIT = {"items": [_IMPLEMENTER, _DB_SPECIALIST]}


def test_parse_checklist_extracts_gate_and_via(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_ROUTED_CHECKLIST, equipment=_TOOLKIT)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    assert items[0].gate is True
    assert items[0].via is None
    # Text retained verbatim — `--check` substring keys keep working.
    assert items[0].text.startswith("**GATE**")
    assert items[1].gate is False
    assert items[1].via == "canvas-to-code:start"
    assert items[1].text.endswith("— via canvas-to-code:start")
    # Plain items default to no gate / no via.
    assert items[2].gate is False
    assert items[2].via is None


def test_parse_checklist_gate_requires_exact_uppercase_prefix(tmp_path: Path) -> None:
    checklist = """\
- [ ] GATE — decide the model (bare marker)
- [ ] Integrate GATEWAY routing for uploads
- [ ] gate the rollout behind a flag
"""
    root = _make_proposal(tmp_path, checklist=checklist, equipment=_TOOLKIT)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    assert items[0].gate is True       # bare `GATE —` form
    assert items[1].gate is False      # GATEWAY is not a gate (word boundary)
    assert items[2].gate is False      # case-sensitive: lowercase prose stays normal


def test_dispatch_mode_classifies_items(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_ROUTED_CHECKLIST, equipment=_TOOLKIT)
    items = parse_checklist(root / ".context" / "proposals" / _SLUG / "checklist.md")
    assert dispatch_mode(items[0]) is DispatchMode.MAIN_SESSION  # gate
    assert dispatch_mode(items[1]) is DispatchMode.MAIN_SESSION  # via
    assert dispatch_mode(items[2]) is DispatchMode.SUBAGENT      # plain


def test_flip_item_still_matches_tagged_items_by_substring(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_ROUTED_CHECKLIST, equipment=_TOOLKIT)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    flipped = flip_item(path, "Export BCO-0")
    assert flipped.done is True
    assert parse_checklist(path)[1].done is True


# ----- CLI: GATE / via items are main-session, never dispatch units ---------


def test_cli_next_wave_json_marks_gate_and_via_as_main_session(
    tmp_path: Path, capsys
) -> None:
    root = _make_proposal(tmp_path, checklist=_ROUTED_CHECKLIST, equipment=_TOOLKIT)
    rc = _build(root, "--next-wave", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    gate, via, code = payload["items"]

    assert gate["dispatch"] == "main-session"
    assert gate["gate"] is True
    assert gate["agent"] is None
    assert gate["subagent_type"] is None
    assert "GATE" in gate["instruction"]
    assert "never dispatch" in gate["instruction"]

    assert via["dispatch"] == "main-session"
    assert via["via"] == "canvas-to-code:start"
    assert via["agent"] is None
    assert via["subagent_type"] is None
    # The via tag is a binding directive, not a hint — and substitution is
    # forbidden.
    assert "canvas-to-code:start" in via["instruction"]
    assert "binding" in via["instruction"]
    assert "not a hint" in via["instruction"]

    assert code["dispatch"] == "subagent"
    assert code["agent"] == "db-specialist"
    assert code["subagent_type"] == "db-specialist"
    assert code["instruction"] is None


def test_cli_next_wave_human_marks_main_session_items(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, checklist=_ROUTED_CHECKLIST, equipment=_TOOLKIT)
    rc = _build(root, "--next-wave")
    assert rc == 0
    out = capsys.readouterr().out
    assert "main-session" in out
    assert "GATE" in out
    assert "canvas-to-code:start" in out
    assert "binding" in out
    # The header must not claim the whole wave is concurrently dispatchable.
    assert "1 subagent" in out
    assert "2 main-session" in out


def test_cli_next_json_gate_item_is_main_session(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, checklist=_ROUTED_CHECKLIST, equipment=_TOOLKIT)
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dispatch"] == "main-session"
    assert payload["gate"] is True
    assert payload["agent"] is None
    assert payload["subagent_type"] is None
    assert "GATE" in payload["instruction"]


def test_cli_next_json_plain_item_is_subagent(tmp_path: Path, capsys) -> None:
    root = _make_proposal(
        tmp_path,
        checklist="# Checklist\n\n- [ ] Write database migration for widgets table\n",
        equipment=_TOOLKIT,
    )
    rc = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dispatch"] == "subagent"
    assert payload["gate"] is False
    assert payload["via"] is None


# ----- domain + CLI: --skip <item> --reason "…" ------------------------------

_SKIP_CHECKLIST = """\
# Checklist — gallery

- [ ] Write database migration for widgets table
- [ ] Export BCO-0 illustrations — via canvas-to-code:start
"""


def test_skip_item_records_annotated_skip(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_SKIP_CHECKLIST, equipment=_TOOLKIT)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    item = skip_item(path, 1, "renegotiated: bridge source unavailable")
    assert item.done is True
    assert "skipped: renegotiated: bridge source unavailable" in item.text
    text = path.read_text(encoding="utf-8")
    # An annotated `- [~]`, never a bare `- [x]` tick.
    assert (
        "- [~] Export BCO-0 illustrations — via canvas-to-code:start "
        "— skipped: renegotiated: bridge source unavailable" in text
    )
    # The skip closes the box so the wave frontier advances.
    items = parse_checklist(path)
    assert items[1].done is True


def test_skip_item_requires_reason(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_SKIP_CHECKLIST, equipment=_TOOLKIT)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    with pytest.raises(BuildLoopError):
        skip_item(path, 0, "   ")


def test_skip_item_refuses_already_closed_box(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_SKIP_CHECKLIST, equipment=_TOOLKIT)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    flip_item(path, 0)
    with pytest.raises(BuildLoopError):
        skip_item(path, 0, "too late")


def test_skip_item_collapses_newlines_in_reason(tmp_path: Path) -> None:
    # A reason must never break the single-line checkbox format.
    root = _make_proposal(tmp_path, checklist=_SKIP_CHECKLIST, equipment=_TOOLKIT)
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    skip_item(path, 0, "out of\nscope")
    assert "skipped: out of scope" in path.read_text(encoding="utf-8")
    assert len(parse_checklist(path)) == 2


def test_cli_skip_with_reason_annotates_checklist(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, checklist=_SKIP_CHECKLIST, equipment=_TOOLKIT)
    rc = _build(root, "--skip", "database migration", "--reason", "moved to follow-up")
    assert rc == 0
    out = capsys.readouterr().out
    assert "skip" in out
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    assert "- [~] Write database migration for widgets table — skipped: " \
        "moved to follow-up" in path.read_text(encoding="utf-8")


def test_cli_skip_without_reason_is_an_error(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, checklist=_SKIP_CHECKLIST, equipment=_TOOLKIT)
    rc = _build(root, "--skip", "database migration")
    assert rc == 2
    assert "--reason" in capsys.readouterr().err
    # Untouched file: no annotation, no tick.
    path = root / ".context" / "proposals" / _SLUG / "checklist.md"
    assert "[~]" not in path.read_text(encoding="utf-8")


def test_cli_reason_without_skip_is_an_error(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, checklist=_SKIP_CHECKLIST, equipment=_TOOLKIT)
    rc = _build(root, "--next", "--reason", "dangling")
    assert rc == 2
    assert "--skip" in capsys.readouterr().err


def test_cli_skip_is_exclusive_with_other_verbs(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, checklist=_SKIP_CHECKLIST, equipment=_TOOLKIT)
    rc = _build(root, "--skip", "0", "--reason", "x", "--next")
    assert rc == 2
    assert "verb" in capsys.readouterr().err


def test_cli_skip_already_closed_box_is_an_error(tmp_path: Path, capsys) -> None:
    root = _make_proposal(tmp_path, checklist=_SKIP_CHECKLIST, equipment=_TOOLKIT)
    _build(root, "--check", "0")
    capsys.readouterr()  # drain
    rc = _build(root, "--skip", "0", "--reason", "renegotiated")
    assert rc == 2
    assert "already" in capsys.readouterr().err
