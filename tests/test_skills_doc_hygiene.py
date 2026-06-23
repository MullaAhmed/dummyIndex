"""Anti-regression guard for shipped skill + generated-doc prose.

These tests grep the SHIPPED skill sources (``dummyindex/skills/**``) and the
generated-doc templates for strings the C10 docs-alignment pass removed or
added. They are deliberately string-level: their whole point is to fail loudly
if a known-bad remedy ("run ``dummyindex install --scope user``"), a phantom
CLI verb ("``dummyindex --recouncil``" presented as a command), or a stale
schema version ("(v2)") ever reappears in a skill, and to lock in the
correctness fixes (the binding ``— via`` gate, the read-only reconcile
description, the version-pinning update arg, the feature.json/INDEX.json field
contract).

Markdown-only changes are enforced by prose; that is exactly what these guards
verify. They do not touch Wave-3's ``tests/cli/test_cli_doc_sync.py``.
"""

from __future__ import annotations

import pytest

from dummyindex.context.output.bootstrap import generate_managed_block
from dummyindex.context.output.instructions import (
    PLAYBOOK_IDS,
    generate_how_to_use_md,
    generate_playbook_md,
)
from tests.paths import REPO_ROOT

_SKILLS_DIR = REPO_ROOT / "dummyindex" / "skills"


def _all_skill_markdown() -> dict[str, str]:
    """Every shipped skill markdown (SKILL.md, skill.md, council/*.md, …)."""
    out: dict[str, str] = {}
    for path in _SKILLS_DIR.rglob("*.md"):
        out[str(path.relative_to(REPO_ROOT))] = path.read_text(encoding="utf-8")
    return out


# --- Known-bad strings must never reappear in any shipped skill --------------


@pytest.mark.unit
def test_no_install_scope_user_skew_remedy() -> None:
    """The version-skew banner used to prescribe a blunt reinstall as the fix.
    `install` is non-destructive now, but the banner must point at the
    diagnosis verb + /dummyindex-update, never `install --scope user`."""
    offenders = [
        rel
        for rel, text in _all_skill_markdown().items()
        if "install --scope user" in text
    ]
    assert not offenders, (
        "shipped skill(s) still prescribe `dummyindex install --scope user` as "
        f"the version-skew remedy: {offenders}"
    )


@pytest.mark.unit
def test_recouncil_never_presented_as_bare_cli_command() -> None:
    """`/dummyindex --recouncil` is a Claude skill invocation, never a runnable
    `dummyindex` CLI verb. A line that writes the literal `dummyindex
    --recouncil` (CLI binary directly followed by the flag) is the phantom-verb
    bug; `/dummyindex --recouncil` (the skill) is fine, and so is a line that
    explicitly disclaims it ("there is no `dummyindex --recouncil` command")."""
    # Phrases that prove the line is DISCLAIMING the phantom verb, not
    # prescribing it.
    disclaimers = ("not a", "not** a", "there is no", "no `dummyindex --recouncil`")
    offenders: list[str] = []
    for rel, text in _all_skill_markdown().items():
        for line in text.splitlines():
            if "dummyindex --recouncil" not in line:
                continue
            if "/dummyindex --recouncil" in line:
                continue  # the skill invocation form — correct
            if any(d in line for d in disclaimers):
                continue  # an explicit "this is NOT a CLI verb" disclaimer
            offenders.append(f"{rel}: {line.strip()}")
    assert not offenders, (
        "`dummyindex --recouncil` is presented as a CLI command (it is a skill "
        f"invocation `/dummyindex --recouncil`): {offenders}"
    )


@pytest.mark.unit
def test_no_stale_equipment_schema_version_in_skills() -> None:
    """equipment.json is schema v4. No skill may claim (v2)/(v3) or
    `schema_version 2`/`schema_version 3` as the live version."""
    bad = (
        "(v2)",
        "(v3)",
        "schema_version 2",
        "schema_version 3",
        "manifest v2",
        "manifest v3",
    )
    offenders: list[str] = []
    for rel, text in _all_skill_markdown().items():
        for token in bad:
            if token in text:
                offenders.append(f"{rel}: {token!r}")
    assert not offenders, f"stale equipment schema version in skill(s): {offenders}"


# --- Version-skew banner points at the safe diagnose-then-fix path -----------


@pytest.mark.unit
def test_skew_banners_point_at_diagnosis_verb() -> None:
    """Every skill that carries the `__VERSION__` skew banner must route to
    `dummyindex context check --versions` (diagnose) + /dummyindex-update."""
    for rel, text in _all_skill_markdown().items():
        if "If they diverge" not in text:
            continue
        assert "context check --versions" in text, (
            f"{rel}: skew banner does not point at `context check --versions`"
        )
        assert "/dummyindex-update" in text, (
            f"{rel}: skew banner does not route to /dummyindex-update"
        )


# --- build skill: binding `— via` gate + non-dispatchable main-session items -


def _build_skill() -> str:
    return (_SKILLS_DIR / "build" / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_build_skill_via_substitution_is_a_failure() -> None:
    text = _build_skill()
    assert "Substitution is a build failure" in text
    assert "BINDING routing" in text


@pytest.mark.unit
def test_build_skill_verify_demands_tool_provenance() -> None:
    text = _build_skill()
    # The verify step must require evidence the tagged tool actually ran.
    assert "the tool actually ran" in text


@pytest.mark.unit
def test_build_skill_excludes_consumer_specific_canvas_gate() -> None:
    """The hand-edit in the consumer repo embedded a project-specific
    canvas-to-code provenance gate; the GENERIC rule was folded upstream but
    the project-specific paths must NOT ship in the package skill."""
    text = _build_skill()
    assert "canvas-to-code" not in text
    assert ".canvas-to-code/state" not in text


@pytest.mark.unit
def test_build_skill_marks_gate_and_main_session_undispatchable() -> None:
    text = _build_skill()
    assert "main-session" in text
    # GATE / via items are handled in-session, never dispatched.
    assert "GATE" in text
    assert "never" in text.lower()


# --- plan skill: agent-availability resolution + open-decisions rule ---------


def _plan_skill() -> str:
    return (_SKILLS_DIR / "plan" / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_plan_skill_resolves_agent_availability_before_dispatch() -> None:
    text = _plan_skill()
    assert "Resolve agent availability first" in text
    # The hardcoded types must be reframed as preferred-only, with a
    # general-purpose fallback spelled out per critic.
    assert "general-purpose" in text
    assert "have not confirmed exists" in text


@pytest.mark.unit
def test_plan_skill_keeps_open_decisions_out_of_checklist() -> None:
    text = _plan_skill()
    assert "Open decisions never become" in text
    assert "**GATE**" in text


@pytest.mark.unit
def test_plan_skill_says_read_before_overwrite() -> None:
    text = _plan_skill()
    assert "before you overwrite it" in text


# --- update skill: version pinning -------------------------------------------


@pytest.mark.unit
def test_update_skill_documents_version_pinning() -> None:
    text = (_SKILLS_DIR / "update" / "SKILL.md").read_text(encoding="utf-8")
    assert "If the user passed a version/tag" in text
    assert "verbatim" in text
    # The frontmatter/title should advertise the optional positional arg.
    assert "/dummyindex-update <version" in text or "<version|tag>" in text


# --- trivial-filter doc: where the count fields live -------------------------


@pytest.mark.unit
def test_trivial_filter_doc_locates_count_fields_in_index_json() -> None:
    text = (_SKILLS_DIR / "council" / "18-filter-trivial.md").read_text(
        encoding="utf-8"
    )
    assert "features/INDEX.json" in text
    # It must say feature.json does NOT carry the count fields.
    assert "not** in `features/<id>/feature.json`" in text
    assert "len()" in text


# --- generated-doc templates: correct update-path contract -------------------


@pytest.mark.unit
def test_how_to_use_describes_reconcile_as_read_only() -> None:
    h = generate_how_to_use_md()
    assert "writes nothing" in h
    assert "reconcile-stamp" in h
    # rebuild --changed must be qualified as preserving curated docs.
    assert "rebuild --changed" in h
    assert "preserve" in h.lower()


@pytest.mark.unit
def test_how_to_use_drops_blanket_no_handedit_rule() -> None:
    h = generate_how_to_use_md()
    # The old absolute claim must be gone; in-session feature-doc edits are
    # now sanctioned.
    assert "All files are regenerated on rebuild" not in h


@pytest.mark.unit
def test_how_to_use_documents_index_json_field_names() -> None:
    h = generate_how_to_use_md()
    assert "feature_id" in h
    # And warns `id` is wrong / `features` is the wrapper key.
    assert "not** `id`" in h or "not `id`" in h or "*not* `id`" in h


@pytest.mark.unit
def test_how_to_use_user_overrides_index() -> None:
    h = generate_how_to_use_md()
    assert "win" in h.lower()


@pytest.mark.unit
def test_managed_block_describes_reconcile_correctly() -> None:
    m = generate_managed_block()
    # reconcile is read-only; the procedure folds it in.
    assert "writes nothing" in m or "read-only" in m
    assert "reconcile-stamp" in m
    assert "user wins" in m.lower()
    # The old false claim ("folds new/changed code into the curated taxonomy"
    # as a property of `reconcile` itself) must be gone.
    assert "reconcile` folds" not in m


@pytest.mark.unit
def test_playbooks_pair_rebuild_with_reconcile_for_new_files() -> None:
    """A playbook closer must not present bare `rebuild --changed` as the whole
    re-index story when the task adds files — it must point at the reconcile
    procedure too."""
    for pid in PLAYBOOK_IDS:
        body = generate_playbook_md(pid)
        if "rebuild --changed" not in body:
            continue
        assert "reconcile" in body, (
            f"playbook {pid!r} closes on `rebuild --changed` without mentioning "
            "the reconcile procedure for new files"
        )
