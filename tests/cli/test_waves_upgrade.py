"""`build --next`/`--next-wave` — the defensive bare-name pool upgrade.

The CLI-side half of build-dispatch-fanout-fix: via tags naming generated
agents must fan out as pinned subagent units instead of serializing, while
unknown names and untyped legacy matches fail safe. Companion to
``tests/context/domains/test_build_loop_routing.py`` (the classifier
matrix) — this file exercises the mapper/payload layer through
``dummyindex.cli.build_loop.run``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.build_loop import run as run_build

pytestmark = pytest.mark.unit

_SLUG = "fanout"

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


def _make_proposal(
    root: Path,
    *,
    checklist: str,
    equipment: dict | None = None,
    routing: dict | None = None,
) -> Path:
    context_dir = root / ".context"
    proposal_dir = context_dir / "proposals" / _SLUG
    proposal_dir.mkdir(parents=True)
    (proposal_dir / "checklist.md").write_text(checklist, encoding="utf-8")
    proposal_payload: dict = {"slug": _SLUG, "title": "t"}
    if routing is not None:
        proposal_payload["routing"] = routing
    (proposal_dir / "proposal.json").write_text(
        json.dumps(proposal_payload), encoding="utf-8"
    )
    if equipment is not None:
        (context_dir / "equipment.json").write_text(
            json.dumps(equipment), encoding="utf-8"
        )
    return root


def _build(root: Path, *verb_args: str) -> tuple[int, str]:
    """Run one build verb, returning ``(rc, captured stdout)``."""
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_build(["--proposal", _SLUG, "--root", str(root), *verb_args])
    return rc, buf.getvalue()


# The wave carries one item of each tag class so every payload assertion
# lands in a single --next-wave call.
_WAVE_CHECKLIST = """\
# Checklist — fanout

## Wave 1 — tag classes
- [ ] Implement the widget parser module — via agent:python-implementer
- [ ] Implement the router module — via python-implementer
- [ ] Implement the auth provider — via agent:ghost-agent
- [ ] Verify the upload flow end to end — via /dummyindex-verify
"""

_TOOLKIT = {"items": [_IMPLEMENTER, _TESTER]}


def test_bare_generated_agent_name_upgrades_and_pins(tmp_path: Path) -> None:
    """THE defect: '— via python-implementer' serialized a dispatchable unit."""
    root = _make_proposal(tmp_path, checklist=_WAVE_CHECKLIST, equipment=_TOOLKIT)
    rc, out = _build(root, "--next-wave", "--json")
    assert rc == 0
    items = {e["via"]: e for e in json.loads(out)["items"]}
    bare = items["python-implementer"]
    assert bare["dispatch"] == "subagent"
    # Pinned to the named entry — capability scoring bypassed even though the
    # text ("module" tokens) would route plain items to the implementer anyway;
    # pinning is exact-name, not scored.
    assert bare["agent"] == "python-implementer"
    assert bare["subagent_type"] == "python-implementer"
    assert bare["fallback"] is False
    assert bare["instruction"] is None
    assert bare["upgrade_note"] is not None
    assert "upgraded" in bare["upgrade_note"]


def test_agent_prefixed_tag_pins_to_pool_entry(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_WAVE_CHECKLIST, equipment=_TOOLKIT)
    rc, out = _build(root, "--next-wave", "--json")
    assert rc == 0
    explicit = {e["via"]: e for e in json.loads(out)["items"]}[
        "agent:python-implementer"
    ]
    assert explicit["dispatch"] == "subagent"
    assert explicit["agent"] == "python-implementer"
    assert explicit["subagent_type"] == "python-implementer"
    assert explicit["upgrade_note"].startswith("explicit")


def test_unknown_agent_tag_fails_safe(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_WAVE_CHECKLIST, equipment=_TOOLKIT)
    rc, out = _build(root, "--next-wave", "--json")
    assert rc == 0
    ghost = {e["via"]: e for e in json.loads(out)["items"]}["agent:ghost-agent"]
    assert ghost["dispatch"] == "main-session"
    assert ghost["agent"] is None
    assert ghost["subagent_type"] is None
    assert "warning" in ghost["upgrade_note"]
    assert "ghost-agent" in ghost["upgrade_note"]
    assert "never launch the Task tool" in ghost["instruction"]


def test_skill_kind_via_tag_stays_main_session_without_note(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_WAVE_CHECKLIST, equipment=_TOOLKIT)
    rc, out = _build(root, "--next-wave", "--json")
    assert rc == 0
    skill = {e["via"]: e for e in json.loads(out)["items"]}["/dummyindex-verify"]
    assert skill["dispatch"] == "main-session"
    assert skill["upgrade_note"] is None
    assert "binding" in skill["instruction"]


_UNTYPED_LEGACY = {
    "items": [{"name": "py-impl", "kind": "agent", "capabilities": ["implement"]}]
}


def test_untyped_legacy_match_stays_main_session_with_explanation(
    tmp_path: Path,
) -> None:
    root = _make_proposal(
        tmp_path,
        checklist="# Checklist\n\n- [ ] Implement the widget parser — via py-impl\n",
        equipment=_UNTYPED_LEGACY,
    )
    rc, out = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(out)
    assert payload["dispatch"] == "main-session"
    assert payload["subagent_type"] is None
    assert "no subagent_type" in payload["upgrade_note"]


def test_pin_bypasses_capability_scoring(tmp_path: Path) -> None:
    # A review-flavoured text would score the tester/reviewer on a plain item;
    # an exact agent-tag pin must ignore scoring entirely.
    root = _make_proposal(
        tmp_path,
        checklist=(
            "# Checklist\n\n"
            "- [ ] Test coverage review for the parser — via python-implementer\n"
        ),
        equipment=_TOOLKIT,
    )
    rc, out = _build(root, "--next", "--json")
    assert rc == 0
    payload = json.loads(out)
    assert payload["dispatch"] == "subagent"
    assert payload["agent"] == "python-implementer"


def test_wave_payload_carries_routing_and_override_wins(tmp_path: Path) -> None:
    root = _make_proposal(
        tmp_path,
        checklist=_WAVE_CHECKLIST,
        equipment=_TOOLKIT,
        routing={"implementer": "sonnet"},
    )
    rc, out = _build(root, "--next-wave", "--json")
    assert rc == 0
    assert json.loads(out)["routing"] == {"implementer": "sonnet"}

    rc, out = _build(
        root,
        "--next-wave",
        "--json",
        "--route",
        "implementer=fable",
        "--route",
        "decisions=current",
    )
    assert rc == 0
    assert json.loads(out)["routing"] == {
        "implementer": "fable",
        "decisions": "current",
    }


def test_invalid_proposal_routing_fails_the_wave_loudly(tmp_path: Path) -> None:
    root = _make_proposal(
        tmp_path,
        checklist="# Checklist\n\n- [ ] Implement the widget parser\n",
        equipment=_TOOLKIT,
        routing={"implementer": "gpt-9"},
    )
    rc, out = _build(root, "--next-wave", "--json")
    assert rc == 2
    assert not out  # the error goes to stderr; stdout stays empty


def test_text_mode_prints_upgrade_notes(tmp_path: Path) -> None:
    root = _make_proposal(tmp_path, checklist=_WAVE_CHECKLIST, equipment=_TOOLKIT)
    rc, out = _build(root, "--next-wave")
    assert rc == 0
    assert "upgraded: bare '— via python-implementer'" in out
    assert "no kind-agent equipment entry named 'ghost-agent'" in out
