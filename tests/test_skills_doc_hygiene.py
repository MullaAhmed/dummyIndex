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

import re
from pathlib import Path

import pytest

from dummyindex.context.output.bootstrap import generate_managed_block
from dummyindex.context.output.instructions import (
    PLAYBOOK_IDS,
    generate_how_to_use_md,
    generate_playbook_md,
)
from dummyindex.installer.common import _SIBLING_SKILLS
from tests.paths import REPO_ROOT

_SKILLS_DIR = REPO_ROOT / "dummyindex" / "skills"


def _all_skill_markdown() -> dict[str, str]:
    """Every shipped skill markdown (SKILL.md, skill.md, council/*.md, …)."""
    out: dict[str, str] = {}
    for path in _SKILLS_DIR.rglob("*.md"):
        out[str(path.relative_to(REPO_ROOT))] = path.read_text(encoding="utf-8")
    return out


def _installed_skill_sources() -> tuple[tuple[str, str], ...]:
    """The family's markdown entry points copied as installed ``SKILL.md`` files."""
    paths = (_SKILLS_DIR / "skill.md", *_SKILLS_DIR.glob("*/SKILL.md"))
    return tuple(
        (str(path.relative_to(REPO_ROOT)), path.read_text(encoding="utf-8"))
        for path in sorted(paths)
    )


@pytest.mark.unit
def test_installed_skill_frontmatter_is_agent_skills_portable() -> None:
    """Keep shipped entry points on the interoperable Agent Skills surface.

    ``allowed-tools: Read, Write, Bash, Task`` is Claude-specific metadata and
    its comma-separated value is not part of the open Agent Skills contract.
    Tool availability is owned by the active host, so each shared entry point
    carries only the required discovery metadata.

    Frontmatter ``name`` must also match the skill's **installed directory
    label** — the same label ``_SIBLING_SKILLS`` maps each source dir to
    (``skills/plan/`` -> ``dummyindex-plan``, etc.); the top-level ``skill.md``
    is the primary skill and installs as bare ``dummyindex``.
    """
    sibling_labels = dict(_SIBLING_SKILLS)
    for rel, text in _installed_skill_sources():
        assert text.startswith("---\n"), f"{rel}: frontmatter is not first"
        _, frontmatter, _ = text.split("---", 2)
        values = {
            key.strip(): value.strip()
            for line in frontmatter.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
            for key, value in (line.split(":", 1),)
        }
        fields = {
            line.split(":", 1)[0].strip()
            for line in frontmatter.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        assert fields == {"name", "description"}, (
            f"{rel}: shared Agent Skill frontmatter must contain only name + "
            f"description, got {sorted(fields)}"
        )
        assert "allowed-tools" not in frontmatter
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", values["name"]), (
            f"{rel}: name is not a valid Agent Skills identifier"
        )
        assert len(values["name"]) <= 64, f"{rel}: name exceeds 64 characters"
        assert values["description"], f"{rel}: description is empty"
        assert len(values["description"]) <= 1024, (
            f"{rel}: description exceeds 1024 characters"
        )

        source_dir = Path(rel).parent.name
        expected_name = (
            "dummyindex" if source_dir == "skills" else sibling_labels[source_dir]
        )
        assert values["name"] == expected_name, (
            f"{rel}: frontmatter name {values['name']!r} does not match its "
            f"installed directory label {expected_name!r}"
        )


@pytest.mark.unit
def test_skill_bodies_name_the_portable_host_path() -> None:
    """The host-language sweep generalized the old binary "Codex path" /
    "Codex branch" labels to a named **portable host path** (covering the
    skill-native-hosts and generic-fallback behavior classes) so the split
    reads past one product. Pin the sentinel wording so a future edit can't
    silently regress a skill body back to Codex-only phrasing."""
    sentinel = "portable host path"
    targets = (
        "skill.md",
        "plan/SKILL.md",
        "build/SKILL.md",
        "equip/SKILL.md",
        "audit/SKILL.md",
        "gc/SKILL.md",
        "fleet/SKILL.md",
    )
    offenders = [
        rel
        for rel in targets
        if sentinel not in (_SKILLS_DIR / rel).read_text(encoding="utf-8").lower()
    ]
    assert not offenders, (
        f"skill file(s) no longer name the portable host path: {offenders}"
    )


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
    """Host skill invocations are valid; the bare CLI phantom verb is not."""
    # Phrases that prove the line is DISCLAIMING the phantom verb, not
    # prescribing it.
    disclaimers = ("not a", "not** a", "there is no", "no `dummyindex --recouncil`")
    offenders: list[str] = []
    for rel, text in _all_skill_markdown().items():
        for line in text.splitlines():
            if "dummyindex --recouncil" not in line:
                continue
            if "/dummyindex --recouncil" in line or "$dummyindex --recouncil" in line:
                continue  # the skill invocation form — correct
            if any(d in line for d in disclaimers):
                continue  # an explicit "this is NOT a CLI verb" disclaimer
            offenders.append(f"{rel}: {line.strip()}")
    assert not offenders, (
        "`dummyindex --recouncil` is presented as a CLI command (it is a skill "
        "invocation `/dummyindex --recouncil` or `$dummyindex --recouncil`): "
        f"{offenders}"
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


# --- build-dispatch-fanout-fix: two-class via rule + models disclosure -------


def _plan_skill() -> str:
    return (_SKILLS_DIR / "plan" / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_plan_skill_teaches_the_two_class_via_rule() -> None:
    """Plan step 6 must separate agent tags from binding tool tags — the old
    guidance taught bare generated-agent names, which serialized dispatch."""
    text = _plan_skill()
    assert "two tag" in text.lower()
    assert "— via agent:<name>" in text
    assert "Never write\n     a bare generated-agent name after a plain `— via`" in (
        text
    )


@pytest.mark.unit
def test_plan_skill_step8_assertion_is_two_class() -> None:
    """The checklist-derivation step may not claim every `— via` item is
    main-session: only GATE + binding tool tags are; agent tags fan out."""
    text = _plan_skill()
    assert "`**GATE**` items and *binding* via-tagged items" in text
    assert "dispatches as a subagent unit" in text
    # The blanket pre-fanout claim is gone.
    assert "classifies both `**GATE**` and `— via` items" not in text


@pytest.mark.unit
def test_build_skill_documents_models_disclosure_and_route() -> None:
    """The build skill's opening step prints the effective-model line, and
    --route / proposal routing / upgrade_note are documented for conductors."""
    text = _build_skill()
    assert "models: implementer=<x> auditor=<y> decisions=<z>" in text
    assert "--route k=v" in text
    assert '"routing"' in text  # the proposal.json block
    assert "upgrade_note" in text
    # Precedence is spelled out once, in the disclosure step.
    assert "invocation >\n     proposal > unset" in text


# --- gc skill: non-dispatchable gates, ordered contract, no bare delete ------


def _gc_skill() -> str:
    return (_SKILLS_DIR / "gc" / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_gc_skill_marks_confirm_and_gate_non_dispatchable() -> None:
    """The user-confirm step (step 4) and the dogfood GATE must both be pinned
    as human decisions, never handed to a subagent. Mirrors
    `test_build_skill_marks_gate_and_main_session_undispatchable`."""
    text = _gc_skill()
    # The non-dispatchable / human-decision markers must be present.
    assert "non-dispatchable" in text
    assert "human-decision" in text
    # Step 4 is explicitly the user-confirm gate, marked non-dispatchable.
    assert "CONFIRM WITH THE USER" in text
    assert "NOT dispatchable to a subagent" in text
    # The dogfood GATE section is likewise a non-dispatchable human decision.
    assert "GATE" in text
    assert "not dispatchable to a subagent" in text.lower()
    # And the discipline section pins step 4 + the GATE together.
    assert "user-confirm" in text
    assert "NOT dispatchable" in text


@pytest.mark.unit
def test_gc_skill_documents_ordered_contract() -> None:
    """The skill must document the ordered pipeline so a future edit that
    reorders or drops the confirm gate fails. Assert the key ordered tokens
    appear AND in the correct relative order."""
    text = _gc_skill()
    ordered_tokens = (
        "gc status",
        "PageIndex walk",
        "user-confirm",
        "gc delete",
        "gc stamp",
        "reconcile",
    )
    # Each token must be present.
    for token in ordered_tokens:
        assert token in text, f"ordered-contract token missing: {token!r}"
    # And the one-line contract must carry them in order. Find the contract
    # line (the `→`-joined pipeline summary) and assert the tokens are ordered
    # within it — a reorder of the pipeline must fail this test.
    contract_lines = [
        line
        for line in text.splitlines()
        if "gc status" in line and "gc stamp" in line and "→" in line
    ]
    assert contract_lines, "no single-line ordered contract found in gc SKILL.md"
    contract = contract_lines[0]
    positions = [contract.index(tok) for tok in ordered_tokens]
    assert positions == sorted(positions), (
        f"ordered-contract tokens are out of order in the pipeline summary: "
        f"{dict(zip(ordered_tokens, positions, strict=True))}"
    )


@pytest.mark.unit
def test_gc_skill_states_never_a_bare_delete_sentinel() -> None:
    """The skill explicitly forbids ever showing a bare `gc delete`. Pin the
    sentinel sentence so the contract can't be silently dropped."""
    text = _gc_skill()
    assert "Never show a bare `gc delete`" in text


@pytest.mark.unit
def test_gc_skill_no_runnable_gc_delete_without_yes() -> None:
    """Every *runnable* `gc delete` invocation in the skill must carry `--yes`
    or be explicitly described as a dry-run. This is the real guard behind the
    "Never show a bare `gc delete`" sentinel: it checks each occurrence rather
    than trusting the prose.

    A line is treated as a runnable invocation when `gc delete` is immediately
    followed by a flag-like token (`--…`) or a backslash line-continuation —
    i.e. an actual command synopsis or shell line. Prose/pipeline references
    (e.g. the `→`-joined contract summary, or "`gc delete` already updated …")
    do not pretype a command and are exempt; a line that itself marks the
    invocation a dry-run is also fine.
    """
    # `gc delete` followed (allowing a quoted-word or arg) by a `--flag` or a
    # trailing backslash continuation == a runnable command synopsis.
    invocation = re.compile(r"gc delete\b[^\n`]*?(--\w|\\\s*$)")
    offenders: list[str] = []
    for line in _gc_skill().splitlines():
        if "gc delete" not in line:
            continue
        if not invocation.search(line):
            continue  # a prose / pipeline reference, not a runnable command
        if "--yes" in line:
            continue  # carries the explicit confirm flag
        if "dry-run" in line.lower():
            continue  # explicitly a dry-run, removes nothing
        offenders.append(line.strip())
    assert not offenders, (
        "runnable `gc delete` invocation(s) lack `--yes` and are not marked a "
        f"dry-run: {offenders}"
    )


# --- plan skill: agent-availability resolution + open-decisions rule ---------


def _plan_skill() -> str:
    return (_SKILLS_DIR / "plan" / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_plan_skill_uses_host_native_critics() -> None:
    text = _plan_skill()
    assert "active host's native delegation mechanism" in text
    assert "built-in `explorer` subagents" in text
    assert "Do not inspect or create `.claude/agents/`" in text


@pytest.mark.unit
def test_codex_plan_never_runs_claude_equipment() -> None:
    text = _plan_skill()
    flat = " ".join(text.split())
    assert "Do not run `dummyindex context equip discover`, `install`, `apply`" in flat
    assert "Do not create `.context/equipment.json` or write `.claude/**`" in flat
    assert "do not run `equip apply`" in flat
    assert "build-ready without" in flat
    routing_branch = text.split(
        "   **Portable host path** (skill-native hosts — Codex, Cursor, and similar):",
        1,
    )[1].split("\n7.", 1)[0]
    finish_branch = text.split("   **Portable host path:** do not run", 1)[1].split(
        "\n## Checklist", 1
    )[0]
    for branch in (routing_branch, finish_branch):
        assert "```bash" not in branch
        assert not re.search(r"(?m)^\s*dummyindex context equip\b", branch)


@pytest.mark.unit
def test_codex_build_proceeds_without_equipment_manifest() -> None:
    text = _build_skill()
    flat = " ".join(text.split())
    assert "an `equipped: false` result" in flat
    assert "must not stop the" in flat
    assert "Do not offer `equip apply`" in flat
    for agent in ("`worker`", "`explorer`", "`default`"):
        assert agent in text
    manifest_branch = text.split("   - **Portable host path:** an `equipped", 1)[
        1
    ].split("\n\n1.", 1)[0]
    assert "```bash" not in manifest_branch
    assert not re.search(r"(?m)^\s*dummyindex context equip\b", manifest_branch)


@pytest.mark.unit
def test_codex_equip_is_read_only_native_routing() -> None:
    text = _equip_skill()
    codex = text.split(
        "### Portable host path — native routing, read-only, then stop", 1
    )[1]
    codex = codex.split("### Claude Code — rendered equipment and lifecycle", 1)[0]
    assert "```bash" not in codex
    flat = " ".join(codex.split())
    assert "Native routing needs no equipment manifest" in flat
    assert "do not invoke any `dummyindex context equip` verb" in flat
    assert "do not write `.claude/**`" in flat
    assert "stop this skill" in flat
    assert not re.search(r"(?m)^\s*(?:dummyindex context equip|npx skills)\b", codex)


@pytest.mark.unit
def test_codex_onboarding_and_audit_use_current_without_claude_hooks() -> None:
    onboarding = (_SKILLS_DIR / "council" / "05-onboarding.md").read_text(
        encoding="utf-8"
    )
    audit = (_SKILLS_DIR / "audit" / "SKILL.md").read_text(encoding="utf-8")
    onboarding_flat = " ".join(onboarding.split())
    audit_flat = " ".join(audit.split())
    assert "--model current --no-hook" in onboarding_flat
    assert "Do **not** offer Claude model labels" in onboarding_flat
    assert "Codex has a native hook system" in onboarding_flat
    assert "On Codex, always pass `--model current`" in audit_flat
    assert "Do not offer Claude labels" in audit_flat


@pytest.mark.unit
def test_plan_skill_keeps_open_decisions_out_of_checklist() -> None:
    text = _plan_skill()
    assert "Open decisions never become" in text
    assert "**GATE**" in text


@pytest.mark.unit
def test_plan_skill_says_read_before_editing() -> None:
    text = _plan_skill()
    assert "before editing it" in text
    assert "never replace unread content blindly" in text


# --- equip skill: eval/benchmark loop is documented --------------------------


def _equip_skill() -> str:
    return (_SKILLS_DIR / "equip" / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_equip_skill_documents_eval_benchmark_loop() -> None:
    """The equip skill must document the trigger-eval loop so a future edit that
    drops it fails. Assert all three CLI touchpoints are named, the judgment is
    made BLIND to the expected label, and the suite-authoring warning to use
    SYNTHETIC (non-secret) prompts is present. Mirrors `_gc_skill` /
    `_build_skill` per-skill grep tests — substring checks against the markdown."""
    text = _equip_skill()

    # All three CLI touchpoints of the dispatch → observe → eval → benchmark →
    # patch loop must be named.
    for touchpoint in ("equip eval", "equip benchmark", "equip patch"):
        assert touchpoint in text, (
            f"equip SKILL.md no longer names the `{touchpoint}` CLI touchpoint of "
            "the eval loop"
        )

    # The firing judgment must be made BLIND to each case's expected label.
    assert "blind" in text.lower(), (
        "equip SKILL.md must document that each case is judged BLIND to its "
        "expected trigger label"
    )

    # Suites are committed under .context/, so the synthetic-prompt warning is
    # non-negotiable.
    assert "synthetic" in text.lower(), (
        "equip SKILL.md must warn that suite prompts MUST be synthetic "
        "(non-secret) — suites are committed under `.context/`"
    )


@pytest.mark.unit
def test_equip_skill_documents_proxy_vs_prize_framing() -> None:
    """Meta-Harness alignment: trigger-description accuracy measures ROUTING
    quality (a proxy), never toolkit/task-outcome quality (the prize a paper's
    benchmark number measures) — conflating the two is exactly the wrong move
    a 5-advisor council + two falsification experiments ruled out. The
    improve-loop step must separately warn that tuning `description` against
    the suite tends to OVERFIT it, and that `equip eval` stays a REPORTER —
    never a search-optimization target or gate. Mirrors
    `test_equip_skill_documents_eval_benchmark_loop`: substring checks against
    the shipped markdown."""
    text = _equip_skill().lower()

    for token in ("proxy", "prize", "overfit", "reporter"):
        assert token in text, (
            "equip SKILL.md no longer documents the proxy-vs-prize framing "
            f"token {token!r}"
        )


@pytest.mark.unit
def test_equip_skill_no_runnable_evolve_loop_command() -> None:
    """The proxy-vs-prize caution warns that `equip eval` is a reporter, not a
    search-optimization loop — but the SKILL must never itself document a
    RUNNABLE `equip evolve-loop` command synopsis (that CLI verb does not
    exist; a propose->eval->keep-best loop is explicitly out of scope). A bare
    `"evolve-loop" not in text` check would false-positive on this very
    caution's own prose (it names "evolve-loop" to disclaim it), so — mirroring
    `test_gc_skill_no_runnable_gc_delete_without_yes` — this guard is
    regex-scoped to command-shaped lines only: `evolve-loop` immediately
    followed by a flag-like token or a shell line-continuation."""
    invocation = re.compile(r"evolve-loop\b[^\n`]*?(--\w|\\\s*$)")
    offenders: list[str] = []
    for line in _equip_skill().splitlines():
        if "evolve-loop" not in line:
            continue
        if not invocation.search(line):
            continue  # prose mention (e.g. the caution's disclaimer), not a command
        offenders.append(line.strip())
    assert not offenders, (
        "SKILL.md documents a runnable `equip evolve-loop` command; that verb "
        f"is explicitly out of scope (contraindicated search loop): {offenders}"
    )


# --- update skill: version pinning -------------------------------------------


@pytest.mark.unit
def test_update_skill_documents_version_pinning() -> None:
    text = (_SKILLS_DIR / "update" / "SKILL.md").read_text(encoding="utf-8")
    assert "If the user passed a version/tag" in text
    assert "verbatim" in text
    # The frontmatter/title should advertise the optional positional arg.
    assert "/dummyindex-update <version" in text or "<version|tag>" in text


@pytest.mark.unit
def test_update_skill_documents_generated_tool_refresh() -> None:
    """The update skill must document that `install` also refreshes the repo's
    equip-generated tools (agents/skills/specialists) — so a future edit that drops
    the behaviour fails. Names `equip refresh`, the never-clobber / USER_MODIFIED
    guarantee, and the equipped-only guard."""
    text = (_SKILLS_DIR / "update" / "SKILL.md").read_text(encoding="utf-8")
    assert "equip refresh" in text
    assert "generated" in text
    assert "USER_MODIFIED" in text or "hand-edited" in text
    assert "equipment.json" in text
    # It is a VERIFIED layer with an explicit fallback when install's best-effort
    # refresh is skipped — not a silent hope.
    assert "dummyindex context equip refresh" in text
    assert "skipped" in text


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


# --- codebase-scan council doc: ranked-seed editing contract ------------------


def _scan_council_doc() -> str:
    return (_SKILLS_DIR / "council" / "58-codebase-scan.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_codebase_scan_doc_edits_the_ranked_seed() -> None:
    """The authoring procedure is EDIT-the-ranked-shortlist, not invent-from-
    scratch: the seed is PageRank-ranked (proposal A2) and the old "keep maybe
    a third of its nodes" framing must never come back."""
    text = _scan_council_doc()
    assert "ranked shortlist" in text
    assert "edit the ranked shortlist" in text.lower()
    assert "keep maybe a third" not in text


@pytest.mark.unit
def test_codebase_scan_doc_requires_symbol_ref_and_evidence() -> None:
    """Every repo-owned node needs a resolvable `symbolRef`; every node needs
    `evidence` with the EXTRACTED-verbatim / INFERRED-reshaped semantics
    (proposal A3). Groups are grounded in `graph-communities.json`."""
    text = _scan_council_doc()
    assert "`symbolRef`" in text
    assert "`evidence`" in text
    assert "EXTRACTED" in text
    assert "INFERRED" in text
    assert "verbatim" in text
    # Named at least twice: once as an input, once as the group scaffold.
    assert text.count("graph-communities.json") >= 2


@pytest.mark.unit
def test_codebase_scan_doc_carries_current_caps() -> None:
    """Caps doubled to 120/240 with an explicit 40–80 aim; the pre-upgrade
    60/120 caps and 20–40 aim must be gone."""
    text = _scan_council_doc()
    assert "`graph.nodes` ≤ 120" in text
    assert "`graph.edges` ≤ 240" in text
    assert "40–80" in text
    assert "≤ 60" not in text
    assert "20–40" not in text


@pytest.mark.unit
def test_codebase_scan_doc_keeps_strong_sections() -> None:
    """The rewrite is a revision, not a restart: AI-surface hunting, the
    scan-check loop, the load-bearing INFERRED warning, and the skip logic
    all survive."""
    text = _scan_council_doc()
    assert "## Finding the AI surface" in text
    assert "## Skip logic" in text
    assert "load-bearing, not decoration" in text
    assert "dummyindex context scan-check" in text


@pytest.mark.unit
def test_skill_md_scan_phase_matches_current_caps() -> None:
    """skill.md's scan-phase summary must not still claim the 60-node cap."""
    text = (_SKILLS_DIR / "skill.md").read_text(encoding="utf-8")
    assert "≤ 60-node" not in text
    assert "40–80" in text


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


# --- fleet skill: red-flag rules + zero hardcoded identifiers ----------------


def _fleet_skill() -> str:
    return (_SKILLS_DIR / "fleet" / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.unit
def test_fleet_skill_carries_resume_from_state_and_foreground_rules() -> None:
    """The two scar-tissue red flags the fleet skill exists to prevent: an
    uncommitted/lost run state (resume MUST come from committed artifacts,
    never transcripts) and agents reporting unverified success (foreground
    verification is mandatory). Mirrors the per-skill grep guards above."""
    text = _fleet_skill()
    # Resume-from-state-only rule.
    assert "Resume-from-state only" in text or "resume from" in text.lower()
    assert "transcript" in text.lower()
    assert "RUN-MANIFEST.md" in text and "state.json" in text
    assert "fleet status" in text and "fleet next" in text
    # Foreground verification rule (the orchestrator ground-rules block).
    assert "Verify in the FOREGROUND" in text or "FOREGROUND" in text
    # The magic-word report vocabulary matches the manifest's commit policy.
    for word in ("DONE", "BLOCKED", "GATED"):
        assert word in text
    # Stage-only-owned-files discipline.
    assert "ONLY files" in text
    # Merge phase is opt-in.
    assert "opt-in" in text.lower()


@pytest.mark.unit
def test_fleet_skill_has_no_hardcoded_project_identifiers() -> None:
    """Every repo/team/tracker name must come from the run manifest or flags.
    The tool's own name is fine; any real-world project, person, or product
    reference in the shipped skill is not."""
    text = _fleet_skill()
    for banned in (
        "BOS-Mono",
        "Ahmed",
        "Linear",  # tracker stays host-side — named generically instead
        "Jira",
        "GitHub Projects",
        "dummyindex/fleet-runner",  # a specific proposal slug
    ):
        assert banned not in text, f"fleet SKILL.md hardcodes {banned!r}"
