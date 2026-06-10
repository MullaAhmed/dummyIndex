"""Tests for the GENERATED specialist family — templates keyed by capability.

A specialist is a first-class generated agent (db / security / performance /
docs / search), grounded in the project's ``.context/`` spine and rendered +
hash-baselined exactly like the core four. It is produced when (a) a proposal
capability has a matching template (instead of a manifest-only adoption) or
(b) the user asks explicitly. A capability with NO template still adopts
manifest-only — frontend is the canonical fallback (the registry's *Frontend
Developer* covers it, so equip never invents a speculative template for it).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import project_slug, run as run_equip
from dummyindex.context.domains.dev_pick import SubagentType
from dummyindex.context.domains.equip import (
    Capability,
    EquipmentKind,
    render_generated_set,
)
from dummyindex.context.domains.equip.generate.proposal import capabilities_from_text
from dummyindex.context.domains.equip.generate.adopt import resolve_coverage
from dummyindex.context.domains.equip.generate.catalog import build_catalog
from dummyindex.context.domains.equip.models import GENERATED_SENTINEL, StackProfile
from dummyindex.context.domains.equip.generate.specialists import (
    SPECIALIST_TEMPLATES,
    specialist_spec,
    templated_capabilities,
)
from dummyindex.context.domains.preflight.models import PreflightReport, SettingsState


def _report(*, project_agents: tuple[str, ...] = ()) -> PreflightReport:
    return PreflightReport(
        project_root="/tmp/x",
        is_git_repo=True,
        git_clean=True,
        settings=SettingsState(
            exists=False,
            parseable=True,
            user_hook_events=(),
            dummyindex_hook_present=False,
        ),
        rule_files=(),
        project_agents=project_agents,
        claude_md_exists=False,
        claude_md_has_managed_block=False,
    )


def _profile() -> StackProfile:
    return StackProfile(label="python", frameworks=("FastAPI",))


# ----- the registry ---------------------------------------------------------


@pytest.mark.unit
def test_database_and_security_have_templates() -> None:
    templated = templated_capabilities()
    assert Capability.DATABASE in templated
    assert Capability.SECURITY in templated


@pytest.mark.unit
def test_registry_is_immutable() -> None:
    # The specialist registry is a fixed constant — callers must not be able to
    # mutate the package's specialist set.
    with pytest.raises(TypeError):
        SPECIALIST_TEMPLATES["frontend"] = SPECIALIST_TEMPLATES[Capability.DATABASE]  # type: ignore[index]


@pytest.mark.unit
def test_frontend_has_no_template_so_it_stays_adoptable() -> None:
    # Frontend is the deliberate fallback: the registry's Frontend Developer
    # covers it, so equip adopts (manifest-only) rather than generating a file.
    assert Capability.FRONTEND not in templated_capabilities()


@pytest.mark.unit
def test_every_template_targets_a_claude_agent_file() -> None:
    for cap, tmpl in SPECIALIST_TEMPLATES.items():
        spec = specialist_spec(cap, label="python", proj="backend")
        assert spec.kind is EquipmentKind.AGENT
        assert spec.rel_path == f".claude/agents/{spec.name}.md"
        assert spec.name.startswith("backend-")
        assert cap in spec.capabilities
        assert spec.template == tmpl.template
        assert spec.grounding_docs  # every specialist grounds in named .context docs


@pytest.mark.unit
def test_specialist_name_is_proj_scoped_and_deterministic() -> None:
    # NAME determinism is the one invariant refresh/reset rely on.
    a = specialist_spec(Capability.DATABASE, label="python", proj="backend")
    b = specialist_spec(Capability.DATABASE, label="python", proj="backend")
    assert a.name == b.name == "backend-db-specialist"


# ----- coverage precedence: project-agent > template > registry -------------


@pytest.mark.unit
def test_proposal_database_generates_specialist_not_adopts() -> None:
    coverage = resolve_coverage(
        preflight=_report(),
        proposal_capabilities=(Capability.DATABASE,),
        templated_capabilities=templated_capabilities(),
    )
    assert Capability.DATABASE in coverage.generate_capabilities
    assert coverage.adopt == ()  # no manifest-only Data Engineer pointer anymore


@pytest.mark.unit
def test_proposal_frontend_adopts_registry_when_no_template() -> None:
    coverage = resolve_coverage(
        preflight=_report(),
        proposal_capabilities=(Capability.FRONTEND,),
        templated_capabilities=templated_capabilities(),
    )
    assert coverage.generate_capabilities == ()
    assert [a.subagent_type for a in coverage.adopt] == [SubagentType.FRONTEND.value]


@pytest.mark.unit
def test_existing_project_agent_preferred_over_generation() -> None:
    # A capability the user already covers is not a gap → adopt their agent,
    # do not generate a redundant specialist.
    coverage = resolve_coverage(
        preflight=_report(project_agents=("db-helper",)),
        proposal_capabilities=(Capability.DATABASE,),
        templated_capabilities=templated_capabilities(),
    )
    assert coverage.generate_capabilities == ()
    assert [a.subagent_type for a in coverage.adopt] == ["db-helper"]


@pytest.mark.unit
def test_forced_specialist_generates_even_with_project_agent() -> None:
    # An explicit `add-specialist` request forces a generated, editable file
    # regardless of any existing project agent.
    coverage = resolve_coverage(
        preflight=_report(project_agents=("db-helper",)),
        forced_capabilities=(Capability.DATABASE,),
        templated_capabilities=templated_capabilities(),
    )
    assert Capability.DATABASE in coverage.generate_capabilities
    assert coverage.adopt == ()


@pytest.mark.unit
def test_forced_untemplated_capability_is_dropped() -> None:
    # frontend has no template; a forced request for it generates nothing here
    # (the CLI validates explicit asks; manifest-derived forced caps are always
    # templated by construction).
    coverage = resolve_coverage(
        preflight=_report(),
        forced_capabilities=(Capability.FRONTEND,),
        templated_capabilities=templated_capabilities(),
    )
    assert coverage.generate_capabilities == ()
    assert coverage.adopt == ()


# ----- catalog integration --------------------------------------------------


@pytest.mark.unit
def test_catalog_generates_security_specialist_for_proposal() -> None:
    decision = build_catalog(
        profile=_profile(),
        conventions=(),
        preflight=_report(),
        proj="backend",
        proposal_capabilities=(Capability.SECURITY,),
    )
    names = {g.name for g in decision.generate}
    assert "backend-security-specialist" in names
    assert len(decision.generate) == 5  # the four core + one specialist
    assert decision.adopt == ()


@pytest.mark.unit
def test_catalog_forced_specialist_appends_one_agent() -> None:
    decision = build_catalog(
        profile=_profile(),
        conventions=(),
        preflight=_report(),
        proj="backend",
        forced_specialist_capabilities=(Capability.DATABASE,),
    )
    names = {g.name for g in decision.generate}
    assert "backend-db-specialist" in names
    assert len(decision.generate) == 5


@pytest.mark.unit
@pytest.mark.parametrize("capability", sorted(SPECIALIST_TEMPLATES))
def test_every_specialist_renders_frontmatter_first_and_grounded(
    capability: str,
) -> None:
    spec = specialist_spec(capability, label="python", proj="backend")
    base = (".context/HOW_TO_USE.md", ".context/conventions/naming.md")
    rendered = render_generated_set(
        profile=_profile(),
        specs=(spec,),
        conventions=(".context/conventions/naming.md",),
        grounding=base,
        proj="backend",
    )
    item, rel_path, content = rendered[0]
    # frontmatter-first (Claude Code discovers the agent only when `---` leads),
    # the never-clobber sentinel sits just after it, and no slot was left dangling.
    assert content.startswith("---")
    assert GENERATED_SENTINEL in content
    assert "{{" not in content
    # the one invariant the lifecycle relies on: name == subagent_type == stem.
    assert item.subagent_type == item.name
    assert item.version == "1.0.0"
    assert item.origin_hash and item.origin_hash.startswith("sha256:")
    # grounded_in = base ∪ the specialist's capability docs (base always present).
    assert ".context/HOW_TO_USE.md" in item.grounded_in
    for doc in SPECIALIST_TEMPLATES[capability].grounding_docs:
        assert doc in item.grounded_in


@pytest.mark.unit
def test_catalog_with_no_specialists_is_exactly_the_core_four() -> None:
    decision = build_catalog(
        profile=_profile(),
        conventions=(),
        preflight=_report(),
        proj="backend",
    )
    assert len(decision.generate) == 4
    assert decision.adopt == ()


# ----- CLI: add-specialist full lifecycle (acceptance) ----------------------


def _python_project(tmp_path: Path) -> Path:
    context_dir = tmp_path / ".context"
    (context_dir / "map").mkdir(parents=True, exist_ok=True)
    (context_dir / "map" / "files.json").write_text(
        json.dumps({"files": [{"path": "app.py", "language": "python"}]}),
        encoding="utf-8",
    )
    (context_dir / "conventions").mkdir(parents=True, exist_ok=True)
    (context_dir / "conventions" / "data-access.md").write_text(
        "# data access\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\n[project]\ndependencies = ["asyncpg", "supabase"]\n',
        encoding="utf-8",
    )
    return tmp_path


def _status(root: Path, capsys) -> dict[str, tuple[str, str]]:
    capsys.readouterr()
    assert run_equip(["status", "--root", str(root), "--json"]) == 0
    items = json.loads(capsys.readouterr().out)["items"]
    return {i["name"]: (i["state"], i["version"]) for i in items}


@pytest.mark.integration
def test_add_specialist_database_full_lifecycle(tmp_path: Path, capsys) -> None:
    root = _python_project(tmp_path)
    proj = project_slug(root)
    name = f"{proj}-db-specialist"
    agent = root / ".claude" / "agents" / f"{name}.md"

    # --- add-specialist writes a grounded, marked, hash-tracked file ---------
    assert run_equip(["add-specialist", "database", "--root", str(root)]) == 0
    assert agent.is_file()
    text = agent.read_text(encoding="utf-8")
    assert GENERATED_SENTINEL in text
    assert ".context/conventions/data-access.md" in text or "data-access.md" in text

    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    spec = next(i for i in data["items"] if i["name"] == name)
    assert spec["source"] == "generated"
    assert spec["subagent_type"] == name
    assert spec["version"] == "1.0.0"
    assert spec["origin_hash"].startswith("sha256:")
    assert ".context/HOW_TO_USE.md" in spec["grounded_in"]

    # status lists it as pristine, exactly like the core four
    assert _status(root, capsys)[name] == ("pristine", "1.0.0")

    # --- hand-edit → USER_MODIFIED -------------------------------------------
    agent.write_text(text + "\n<!-- HAND EDIT -->\n", encoding="utf-8")
    assert _status(root, capsys)[name][0] == "user-modified"

    # --- refresh skips it; uninstall would keep it; plain re-apply preserves -
    capsys.readouterr()
    assert run_equip(["refresh", "--root", str(root)]) == 0
    assert "<!-- HAND EDIT -->" in agent.read_text(encoding="utf-8")

    # a plain `equip` (no --specialist) must NOT drop the already-applied one
    capsys.readouterr()
    assert run_equip([str(root)]) == 0
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    assert name in {i["name"] for i in data["items"]}
    assert "<!-- HAND EDIT -->" in agent.read_text(encoding="utf-8")  # still preserved

    # --- reset restores the pristine render ----------------------------------
    capsys.readouterr()
    assert run_equip(["reset", name, "--root", str(root)]) == 0
    restored = agent.read_text(encoding="utf-8")
    assert "<!-- HAND EDIT -->" not in restored
    assert GENERATED_SENTINEL in restored
    assert _status(root, capsys)[name][0] == "pristine"

    # --- uninstall removes the now-pristine specialist (ours) ----------------
    capsys.readouterr()
    assert run_equip(["uninstall", "--root", str(root)]) == 0
    assert not agent.is_file()


# ----- capability-gap detection: RLS / tenant-isolation surfaces security ---


@pytest.mark.unit
def test_rls_and_tenant_isolation_surface_security_without_the_word() -> None:
    # The original gap: a plan demanding RLS / tenant isolation, never spelling
    # out "security", surfaced no security specialist.
    caps = capabilities_from_text(
        "Enforce RLS on every table. Add tenant isolation so one tenant cannot "
        "read another's rows. Apply RBAC to admin routes."
    )
    assert Capability.SECURITY in caps


@pytest.mark.unit
def test_existing_security_signals_still_match() -> None:
    # Regression guard for the signals that already worked (whole-word
    # "security", the "auth" prefix) — they must keep matching.
    assert Capability.SECURITY in capabilities_from_text("run get_advisors security")
    assert Capability.SECURITY in capabilities_from_text("add row-level security")
    assert Capability.SECURITY in capabilities_from_text("wire up authorization")


@pytest.mark.integration
def test_migration_proposal_with_rls_criticals_yields_security_specialist(
    tmp_path: Path,
) -> None:
    # The brand-centric-migration fixture: a migration plan whose criticals are
    # RLS / tenant-isolation (no literal "security") must now generate BOTH a db
    # specialist (migration/sql) and a security specialist (rls/tenant).
    root = _python_project(tmp_path)
    prop = root / ".context" / "proposals" / "brand-centric-migration"
    prop.mkdir(parents=True)
    (prop / "plan.md").write_text(
        "# Brand-centric migration\n\n"
        "Add a SQL migration introducing a `brand` table and per-brand data.\n",
        encoding="utf-8",
    )
    (prop / "checklist.md").write_text(
        "- [ ] write the migration\n"
        "- [ ] enforce RLS so each tenant only sees its own brand\n"
        "- [ ] verify tenant isolation across brands\n",
        encoding="utf-8",
    )
    assert run_equip([str(root), "--for-proposal", "brand-centric-migration"]) == 0
    proj = project_slug(root)
    agents = root / ".claude" / "agents"
    assert (agents / f"{proj}-db-specialist.md").is_file()
    assert (agents / f"{proj}-security-specialist.md").is_file()


@pytest.mark.integration
def test_patch_specialist_then_carry_forward_keeps_evolution(
    tmp_path: Path, capsys
) -> None:
    # The genuinely-new path: a specialist reaches the evolved-and-kept branch via
    # manifest carry-forward (specialist_caps_from_manifest), unlike the core
    # four which are always in the catalog. Patch → 1.0.1 (is_evolved) → a plain
    # re-apply must KEEP it (not regenerate to 1.0.0).
    root = _python_project(tmp_path)
    proj = project_slug(root)
    name = f"{proj}-db-specialist"
    agent = root / ".claude" / "agents" / f"{name}.md"
    assert run_equip(["add-specialist", "database", "--root", str(root)]) == 0

    old = "## Guardrails"
    assert old in agent.read_text(encoding="utf-8")
    patch_file = root / "patch.json"
    patch_file.write_text(
        json.dumps({"old": old, "new": old + "\n\n<!-- learned: always ship a rollback -->"}),
        encoding="utf-8",
    )
    assert (
        run_equip(
            ["patch", "--item", name, "--from-file", str(patch_file), "--root", str(root)]
        )
        == 0
    )
    assert "learned: always ship a rollback" in agent.read_text(encoding="utf-8")
    assert _status(root, capsys)[name] == ("pristine", "1.0.1")  # patch-bumped, stays ours

    # plain re-apply: the sanctioned patch survives (evolved item kept), no regress
    capsys.readouterr()
    assert run_equip([str(root)]) == 0
    assert "learned: always ship a rollback" in agent.read_text(encoding="utf-8")
    assert _status(root, capsys)[name] == ("pristine", "1.0.1")


@pytest.mark.integration
def test_specialist_never_clobbers_foreign_user_file(tmp_path: Path) -> None:
    # The other half of never-clobber: a foreign user file equip never recorded
    # at the specialist's path is skipped (no sentinel → not safe to write) and
    # never recorded in the manifest.
    root = _python_project(tmp_path)
    proj = project_slug(root)
    agent = root / ".claude" / "agents" / f"{proj}-db-specialist.md"
    agent.parent.mkdir(parents=True, exist_ok=True)
    original = "# MY hand-written db agent — do not touch\n"
    agent.write_text(original, encoding="utf-8")

    assert run_equip(["add-specialist", "database", "--root", str(root)]) == 0
    assert agent.read_text(encoding="utf-8") == original  # untouched
    data = json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))
    assert f"{proj}-db-specialist" not in {i["name"] for i in data["items"]}


@pytest.mark.integration
def test_uninstall_keeps_user_modified_specialist(tmp_path: Path, capsys) -> None:
    # Acceptance: a hand-edited (USER_MODIFIED) specialist survives uninstall,
    # exactly like a hand-edited core tool.
    root = _python_project(tmp_path)
    proj = project_slug(root)
    agent = root / ".claude" / "agents" / f"{proj}-security-specialist.md"
    assert run_equip(["add-specialist", "security", "--root", str(root)]) == 0
    agent.write_text(agent.read_text(encoding="utf-8") + "\n<!-- MINE -->\n", encoding="utf-8")
    assert _status(root, capsys)[f"{proj}-security-specialist"][0] == "user-modified"
    capsys.readouterr()
    assert run_equip(["uninstall", "--root", str(root)]) == 0
    assert agent.is_file()  # kept
    assert "<!-- MINE -->" in agent.read_text(encoding="utf-8")


@pytest.mark.integration
def test_apply_specialist_flag_generates_file(tmp_path: Path) -> None:
    # The `--specialist C` flag on `apply` is the other entry to generation
    # (distinct from the `add-specialist` verb); both go through `_run_apply`.
    root = _python_project(tmp_path)
    assert run_equip([str(root), "--specialist", "security"]) == 0
    proj = project_slug(root)
    assert (root / ".claude" / "agents" / f"{proj}-security-specialist.md").is_file()


@pytest.mark.integration
def test_apply_specialist_flag_unknown_exits_2(tmp_path: Path, capsys) -> None:
    root = _python_project(tmp_path)
    assert run_equip([str(root), "--specialist", "frontend"]) == 2
    assert "no generated-specialist template" in capsys.readouterr().err


@pytest.mark.integration
def test_add_specialist_unknown_capability_exits_2(tmp_path: Path, capsys) -> None:
    root = _python_project(tmp_path)
    assert run_equip(["add-specialist", "frontend", "--root", str(root)]) == 2
    err = capsys.readouterr().err
    assert "no generated-specialist template" in err
    assert "database" in err  # lists the available ones


@pytest.mark.integration
def test_existing_four_core_repo_unaffected_by_specialist_feature(
    tmp_path: Path, capsys
) -> None:
    # A repo equipped before specialists existed (only the core four) must not
    # gain a specialist on a plain re-apply — specialists are strictly opt-in.
    root = _python_project(tmp_path)
    assert run_equip([str(root)]) == 0
    before = set(_status(root, capsys))
    assert run_equip([str(root)]) == 0  # re-apply
    after = set(_status(root, capsys))
    assert before == after
    assert not any("specialist" in n for n in after)
