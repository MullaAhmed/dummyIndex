"""Unit + integration tests for the ``context.audit`` domain."""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from dummyindex.context.domains.audit import (
    MAX_REBUTTAL_ROUNDS,
    AuditConfig,
    AuditExistsError,
    AuditLogError,
    AuditNotFoundError,
    AuditSlugError,
    ModelRequiredError,
    append_log,
    audit_dir,
    completed_rounds,
    ensure_audit,
    is_round_complete,
    latest_status,
    load_catalog,
    parse_persona,
    read_audit,
    read_log,
    resolve_mode,
    resolve_model,
    slugify,
    validate_slug,
)
from dummyindex.context.domains.config import (
    Config,
    CouncilMode,
    ModelChoice,
    ScopeKind,
    write_config,
)

_FIXED_NOW = _dt.datetime(2026, 6, 9, 12, 0, 0, tzinfo=_dt.timezone.utc)


# ----- slug helpers ---------------------------------------------------------


@pytest.mark.unit
def test_validate_slug_rejects_traversal() -> None:
    for bad in ("", "  ", "../evil", "a/b", "has space", "-lead", "trail-"):
        with pytest.raises(AuditSlugError):
            validate_slug(bad)


@pytest.mark.unit
def test_validate_slug_normalizes_case() -> None:
    assert validate_slug("Audit_01-X".lower()) == "audit_01-x"


@pytest.mark.unit
def test_slugify_is_deterministic_and_safe() -> None:
    assert slugify("Audit the AUTH flow!! for holes") == "audit-the-auth-flow-for-holes"
    assert slugify("   ") == "audit"
    assert slugify("***") == "audit"
    # never produces an invalid slug
    validate_slug(slugify("A very long description " * 20))


# ----- model / mode resolution ----------------------------------------------


@pytest.mark.unit
def test_resolve_model_prefers_flag(tmp_path: Path) -> None:
    assert resolve_model(tmp_path, "opus-4.7") == ModelChoice.OPUS_4_7


@pytest.mark.unit
def test_resolve_model_invalid_flag_errors(tmp_path: Path) -> None:
    with pytest.raises(Exception) as exc:
        resolve_model(tmp_path, "gpt-5")
    assert "not one of" in str(exc.value)


@pytest.mark.unit
def test_resolve_model_falls_back_to_config(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    write_config(
        context_dir,
        Config(
            schema_version=1,
            scope=ScopeKind.REPO,
            scope_path=None,
            mode=CouncilMode.DEEP,
            model=ModelChoice.OPUS_4_7,
            auto_refresh_hook=True,
        ),
    )
    assert resolve_model(context_dir, None) == ModelChoice.OPUS_4_7
    # mode also falls back to config
    assert resolve_mode(context_dir, None) == CouncilMode.DEEP


@pytest.mark.unit
def test_resolve_model_required_when_no_flag_no_config(tmp_path: Path) -> None:
    with pytest.raises(ModelRequiredError):
        resolve_model(tmp_path / ".context", None)


@pytest.mark.unit
def test_resolve_mode_defaults_to_standard(tmp_path: Path) -> None:
    assert resolve_mode(tmp_path / ".context", None) == CouncilMode.STANDARD


# ----- config model round-trip ----------------------------------------------


@pytest.mark.unit
def test_audit_config_round_trip() -> None:
    cfg = AuditConfig(
        slug="x",
        description="audit x",
        mode=CouncilMode.STANDARD,
        model=ModelChoice.OPUS_4_7,
        scope=("dummyindex/cli",),
    )
    again = AuditConfig.from_dict(json.loads(json.dumps(cfg.to_dict())))
    assert again == cfg
    assert again.max_rounds == MAX_REBUTTAL_ROUNDS


@pytest.mark.unit
def test_audit_config_from_dict_rejects_missing_model() -> None:
    # model is never silently defaulted — even on load.
    from dummyindex.context.domains.audit import AuditError

    with pytest.raises(AuditError):
        AuditConfig.from_dict({"schema_version": 1, "slug": "x", "mode": "standard"})


@pytest.mark.unit
def test_audit_config_from_dict_rejects_bad_schema_version() -> None:
    from dummyindex.context.domains.audit import AuditError

    with pytest.raises(AuditError):
        AuditConfig.from_dict({"schema_version": 99, "model": "opus-4.7"})


# ----- persona catalog ------------------------------------------------------


@pytest.mark.unit
def test_parse_persona_reads_frontmatter() -> None:
    text = (
        "---\n"
        "name: Security Auditor\n"
        "role: Security auditor\n"
        "emoji: shield\n"
        "subagent_type: Security Engineer\n"
        "triggers: auth, jwt , , secret\n"
        "description: Trust boundaries and secrets.\n"
        "---\n\n# body\n"
    )
    card = parse_persona(text, "security")
    assert card.persona_id == "security"
    assert card.name == "Security Auditor"
    assert card.subagent_type == "Security Engineer"
    assert card.triggers == ("auth", "jwt", "secret")  # blanks dropped


@pytest.mark.unit
def test_parse_persona_defaults_without_frontmatter() -> None:
    card = parse_persona("no frontmatter here", "mystery")
    assert card.persona_id == "mystery"
    assert card.subagent_type == "general-purpose"
    assert card.triggers == ()


@pytest.mark.unit
def test_load_catalog_missing_dir_is_empty(tmp_path: Path) -> None:
    assert load_catalog(tmp_path / "nope") == ()


@pytest.mark.unit
def test_load_catalog_reads_dir(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("---\nname: A\n---\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("---\nname: B\n---\n", encoding="utf-8")
    cards = load_catalog(tmp_path)
    assert tuple(c.persona_id for c in cards) == ("a", "b")


# ----- shipped catalog (integration with the real personas) -----------------


@pytest.mark.integration
def test_shipped_catalog_is_valid() -> None:
    from dummyindex.context.domains.audit import default_personas_dir

    cards = load_catalog(default_personas_dir())
    assert cards, "no audit personas shipped under skills/audit/agents/"
    for card in cards:
        assert card.subagent_type, f"{card.persona_id} has no subagent_type"
        assert card.description, f"{card.persona_id} has no description"


# ----- workspace scaffold ---------------------------------------------------


@pytest.mark.integration
def test_ensure_audit_scaffolds_workspace(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    personas = tmp_path / "personas"
    personas.mkdir()
    (personas / "security.md").write_text(
        "---\nname: Sec\nsubagent_type: Security Engineer\n"
        "description: sec\n---\n",
        encoding="utf-8",
    )

    start = ensure_audit(
        context_dir,
        description="Audit error handling in the CLI dispatcher",
        mode=CouncilMode.STANDARD,
        model=ModelChoice.OPUS_4_7,
        scope=("dummyindex/cli",),
        personas_dir=personas,
    )

    assert start.slug == "audit-error-handling-in-the-cli-dispatcher"
    target = audit_dir(context_dir, start.slug)
    assert (target / "audit.json").is_file()
    assert (target / "description.md").is_file()
    assert (target / "catalog.json").is_file()
    assert (target / "findings").is_dir()
    # catalog.json mirrors the persona dir
    catalog = json.loads((target / "catalog.json").read_text())
    assert catalog[0]["persona_id"] == "security"
    # round-trips through read_audit
    cfg = read_audit(context_dir, start.slug)
    assert cfg.model == ModelChoice.OPUS_4_7
    assert cfg.scope == ("dummyindex/cli",)
    assert cfg.max_rounds == MAX_REBUTTAL_ROUNDS


@pytest.mark.integration
def test_ensure_audit_does_not_require_existing_context(tmp_path: Path) -> None:
    # .context/ absent — audit creates it on demand.
    context_dir = tmp_path / ".context"
    assert not context_dir.exists()
    ensure_audit(
        context_dir,
        description="standalone audit",
        mode=CouncilMode.LIGHT,
        model=ModelChoice.SONNET_4_6,
        personas_dir=tmp_path / "none",
    )
    assert context_dir.is_dir()


@pytest.mark.integration
def test_ensure_audit_refuses_overwrite_without_force(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    kwargs = dict(
        description="dup",
        mode=CouncilMode.STANDARD,
        model=ModelChoice.SONNET_4_6,
        slug="dup",
        personas_dir=tmp_path / "none",
    )
    ensure_audit(context_dir, **kwargs)
    with pytest.raises(AuditExistsError):
        ensure_audit(context_dir, **kwargs)
    # force overwrites
    ensure_audit(context_dir, force=True, **kwargs)


@pytest.mark.unit
def test_read_audit_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(AuditNotFoundError):
        read_audit(tmp_path / ".context", "ghost")


# ----- debate log -----------------------------------------------------------


@pytest.mark.integration
def test_debate_log_append_and_convergence(tmp_path: Path) -> None:
    ws = tmp_path / "audits" / "x"
    ws.mkdir(parents=True)

    append_log(ws, round_num=0, persona="security", status="started", now=_FIXED_NOW)
    assert not is_round_complete(ws, 0)
    append_log(ws, round_num=0, persona="security", status="complete", now=_FIXED_NOW)
    append_log(ws, round_num=0, persona="correctness", status="complete", now=_FIXED_NOW)
    assert is_round_complete(ws, 0)
    assert latest_status(ws, 0, "security") == "complete"

    # round 1 started but not done
    append_log(ws, round_num=1, persona="security", status="started", now=_FIXED_NOW)
    assert not is_round_complete(ws, 1)
    assert completed_rounds(ws) == (0,)

    entries = read_log(ws)
    assert entries[0].round == 0 and entries[0].persona == "security"


@pytest.mark.unit
def test_debate_log_validates_inputs(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(AuditLogError):
        append_log(ws, round_num=0, persona="x", status="bogus")
    with pytest.raises(AuditLogError):
        append_log(ws, round_num=-1, persona="x", status="complete")
    with pytest.raises(AuditLogError):
        append_log(ws, round_num=0, persona="a/b", status="complete")
    with pytest.raises(AuditLogError):
        append_log(tmp_path / "missing", round_num=0, persona="x", status="complete")


@pytest.mark.unit
def test_read_log_absent_is_empty(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    assert read_log(ws) == ()
    assert completed_rounds(ws) == ()


# ----- persona roster resolution ---------------------------------------------


def _security_card():
    from dummyindex.context.domains.audit import parse_persona

    return parse_persona(
        "---\nname: Security Auditor\nsubagent_type: Security Engineer\n"
        "description: sec\n---\n",
        "security",
    )


def test_resolve_catalog_none_roster_is_identity() -> None:
    from dummyindex.context.domains.audit import resolve_catalog

    cards = (_security_card(),)
    assert resolve_catalog(cards, None) == cards


def test_resolve_catalog_keeps_installed_subagent() -> None:
    from dummyindex.context.domains.audit import RosterAgent, resolve_catalog

    roster = (RosterAgent(subagent_type="Security Engineer"),)
    (card,) = resolve_catalog((_security_card(),), roster)
    assert card.subagent_type == "Security Engineer"
    assert card.requested_subagent_type is None


def test_resolve_catalog_rewrites_absent_persona_to_equipped_match() -> None:
    from dummyindex.context.domains.audit import RosterAgent, resolve_catalog

    roster = (
        RosterAgent(subagent_type="python-implementer", capabilities=("implement",)),
        RosterAgent(subagent_type="security-specialist", capabilities=("security",)),
    )
    (card,) = resolve_catalog((_security_card(),), roster)
    assert card.subagent_type == "security-specialist"
    assert card.requested_subagent_type == "Security Engineer"


def test_resolve_catalog_falls_back_to_general_purpose() -> None:
    from dummyindex.context.domains.audit import RosterAgent, resolve_catalog

    roster = (RosterAgent(subagent_type="python-implementer", capabilities=("implement",)),)
    (card,) = resolve_catalog((_security_card(),), roster)
    assert card.subagent_type == "general-purpose"
    assert card.requested_subagent_type == "Security Engineer"


def test_persona_card_to_dict_carries_requested_subagent_type() -> None:
    from dummyindex.context.domains.audit import RosterAgent, resolve_catalog

    (card,) = resolve_catalog((_security_card(),), (RosterAgent(subagent_type="x"),))
    payload = card.to_dict()
    assert payload["subagent_type"] == "general-purpose"
    assert payload["requested_subagent_type"] == "Security Engineer"


def test_collect_roster_none_when_no_sources(tmp_path: Path) -> None:
    from dummyindex.context.domains.audit import collect_roster

    assert collect_roster(tmp_path, tmp_path / ".context") is None


def test_collect_roster_reads_agents_and_equipment(tmp_path: Path) -> None:
    from dummyindex.context.domains.audit import collect_roster

    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "python-reviewer.md").write_text("# reviewer\n", encoding="utf-8")

    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    (context_dir / "equipment.json").write_text(
        json.dumps({
            "schema_version": 3,
            "items": [
                {
                    "kind": "agent",
                    "name": "security-specialist",
                    "path": ".claude/agents/security-specialist.md",
                    "source": "generated",
                    "capabilities": ["security"],
                    "subagent_type": "security-specialist",
                },
                {
                    "kind": "skill",
                    "name": "verify",
                    "path": ".claude/skills/verify/SKILL.md",
                    "source": "generated",
                    "capabilities": ["verify"],
                },
            ],
        }),
        encoding="utf-8",
    )

    roster = collect_roster(tmp_path, context_dir)
    assert roster is not None
    names = {agent.subagent_type for agent in roster}
    assert "security-specialist" in names
    assert "python-reviewer" in names
    assert "verify" not in names  # skills are not Task dispatch targets


def test_collect_roster_excludes_legacy_marketplace_plugin(tmp_path: Path) -> None:
    """Legacy (schema v3) manifests recorded marketplace plugins with
    kind=agent; such an item must not leak into the dispatch roster — a plugin
    name like ``pg-tuner@claude-plugins-official`` is not Task-dispatchable."""
    from dummyindex.context.domains.audit import collect_roster

    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    (context_dir / "equipment.json").write_text(
        json.dumps({
            "schema_version": 3,
            "items": [
                {
                    "kind": "agent",
                    "name": "pg-tuner@claude-plugins-official",
                    "path": "",
                    "source": "marketplace",
                    "capabilities": ["database"],
                    "subagent_type": "pg-tuner@claude-plugins-official",
                },
                {
                    "kind": "agent",
                    "name": "security-specialist",
                    "path": ".claude/agents/security-specialist.md",
                    "source": "generated",
                    "capabilities": ["security"],
                    "subagent_type": "security-specialist",
                },
            ],
        }),
        encoding="utf-8",
    )

    roster = collect_roster(tmp_path, context_dir)
    assert roster is not None
    names = {agent.subagent_type for agent in roster}
    assert "security-specialist" in names
    assert "pg-tuner@claude-plugins-official" not in names


def test_collect_roster_tolerates_corrupt_equipment(tmp_path: Path) -> None:
    from dummyindex.context.domains.audit import collect_roster

    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    (context_dir / "equipment.json").write_text("{not json", encoding="utf-8")
    roster = collect_roster(tmp_path, context_dir)
    assert roster == ()  # source exists but unreadable → strict empty roster


@pytest.mark.integration
def test_ensure_audit_resolves_catalog_against_equipped_repo(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    (context_dir / "equipment.json").write_text(
        json.dumps({
            "schema_version": 3,
            "items": [{
                "kind": "agent",
                "name": "security-specialist",
                "path": ".claude/agents/security-specialist.md",
                "source": "generated",
                "capabilities": ["security"],
                "subagent_type": "security-specialist",
            }],
        }),
        encoding="utf-8",
    )
    personas = tmp_path / "personas"
    personas.mkdir()
    (personas / "security.md").write_text(
        "---\nname: Sec\nsubagent_type: Security Engineer\ndescription: sec\n---\n",
        encoding="utf-8",
    )

    start = ensure_audit(
        context_dir,
        description="resolved roster audit",
        mode=CouncilMode.STANDARD,
        model=ModelChoice.SONNET_4_6,
        personas_dir=personas,
    )
    catalog = json.loads(
        (audit_dir(context_dir, start.slug) / "catalog.json").read_text(encoding="utf-8")
    )
    assert catalog[0]["subagent_type"] == "security-specialist"
    assert catalog[0]["requested_subagent_type"] == "Security Engineer"


@pytest.mark.integration
def test_ensure_audit_unequipped_repo_keeps_shipped_names(tmp_path: Path) -> None:
    """No .claude/agents and no equipment.json — no evidence either way, so
    the shipped subagent_type survives untouched (documented fallback)."""
    context_dir = tmp_path / ".context"
    personas = tmp_path / "personas"
    personas.mkdir()
    (personas / "security.md").write_text(
        "---\nname: Sec\nsubagent_type: Security Engineer\ndescription: sec\n---\n",
        encoding="utf-8",
    )
    start = ensure_audit(
        context_dir,
        description="bare repo audit",
        mode=CouncilMode.LIGHT,
        model=ModelChoice.SONNET_4_6,
        personas_dir=personas,
    )
    catalog = json.loads(
        (audit_dir(context_dir, start.slug) / "catalog.json").read_text(encoding="utf-8")
    )
    assert catalog[0]["subagent_type"] == "Security Engineer"
    assert catalog[0]["requested_subagent_type"] is None


# ----- over-engineering persona (capability pref + card + resolution) --------


def _over_engineering_card():
    """The shipped over-engineering card, loaded from the real personas dir."""
    from dummyindex.context.domains.audit import default_personas_dir

    cards = load_catalog(default_personas_dir())
    matches = [c for c in cards if c.persona_id == "over-engineering"]
    assert matches, "over-engineering persona not auto-discovered by the *.md glob"
    return matches[0]


@pytest.mark.unit
def test_over_engineering_capability_pref_registered() -> None:
    # (a) the pref maps the persona onto the ``review`` capability.
    from dummyindex.context.domains.audit.catalog import _PERSONA_CAPABILITY_PREFS

    assert _PERSONA_CAPABILITY_PREFS["over-engineering"] == ("review",)


@pytest.mark.integration
def test_over_engineering_card_in_shipped_catalog() -> None:
    # (b) the Wave-1 card is auto-discovered with the right dispatch target.
    card = _over_engineering_card()
    assert card.subagent_type == "Code Reviewer"
    assert card.role
    assert card.triggers
    assert card.description


@pytest.mark.integration
def test_over_engineering_body_contract() -> None:
    # (c) body contract (Acceptance §3): read the file text directly — the five
    # tag tokens, the literal footer, and the complexity-only carve-out.
    from dummyindex.context.domains.audit import default_personas_dir

    body = (default_personas_dir() / "over-engineering.md").read_text(encoding="utf-8")
    for tag in ("delete:", "stdlib:", "native:", "yagni:", "shrink:"):
        assert tag in body, f"missing tag token {tag!r}"
    assert "net: -N lines, -M deps possible." in body
    # complexity-only carve-out: names the three lanes that belong to others.
    lowered = body.lower()
    assert "correctness" in lowered
    assert "security" in lowered
    assert "performance" in lowered


def test_over_engineering_resolves_to_code_reviewer_when_present() -> None:
    # (d.1) shipped name installed → kept as-is.
    from dummyindex.context.domains.audit import RosterAgent, resolve_catalog

    roster = (RosterAgent(subagent_type="Code Reviewer"),)
    (card,) = resolve_catalog((_over_engineering_card(),), roster)
    assert card.subagent_type == "Code Reviewer"
    assert card.requested_subagent_type is None


def test_over_engineering_resolves_to_review_capable_agent() -> None:
    # (d.2) absent → the ``review``-capable agent via the new pref; original
    # subagent_type preserved as requested_subagent_type.
    from dummyindex.context.domains.audit import RosterAgent, resolve_catalog

    roster = (RosterAgent(subagent_type="dummyindex-reviewer", capabilities=("review",)),)
    (card,) = resolve_catalog((_over_engineering_card(),), roster)
    assert card.subagent_type == "dummyindex-reviewer"
    assert card.requested_subagent_type == "Code Reviewer"


def test_over_engineering_falls_back_to_general_purpose() -> None:
    # (d.3) neither the shipped name nor a ``review``-capable agent → general-purpose.
    from dummyindex.context.domains.audit import RosterAgent, resolve_catalog

    roster = (RosterAgent(subagent_type="python-implementer", capabilities=("implement",)),)
    (card,) = resolve_catalog((_over_engineering_card(),), roster)
    assert card.subagent_type == "general-purpose"
    assert card.requested_subagent_type == "Code Reviewer"
