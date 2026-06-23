"""Load the shipped audit-persona catalog from markdown frontmatter.

Each persona is a markdown file under ``dummyindex/skills/audit/agents/`` with a
small ``---`` frontmatter block (``name``, ``role``, ``emoji``,
``subagent_type``, ``triggers``, ``description``). The catalog is the menu the
``/dummyindex-audit`` skill picks a task-relevant panel from — the *selection*
is the skill's (the LLM's) judgment, so there is deliberately no matching logic
here. This module parses the menu and RESOLVES each card's ``subagent_type``
against the repo's installed roster (project ``.claude/agents/`` stems +
``equipment.json`` agent entries):

- shipped name installed → kept as-is;
- absent → rewritten to the equipped agent covering the persona's capability
  (``security`` → the security specialist, …), else ``general-purpose``,
  with the original preserved as ``requested_subagent_type``;
- NO roster sources at all (bare repo: no ``.claude/agents``, no
  ``equipment.json``) → cards pass through untouched — there is no evidence
  the global personas are absent, and audit never requires an equipped repo.

Frontmatter is hand-parsed (no YAML dependency, matching the rest of the
package). ``triggers`` is a comma-separated string so a list never needs YAML.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .models import PersonaCard

# The universal built-in Task target — always dispatchable.
_GENERAL_PURPOSE = "general-purpose"

# persona_id (file stem) → equipment capability tokens, in preference order.
# Mirrors the equip Capability vocabulary (domains/equip/enums.py).
_PERSONA_CAPABILITY_PREFS: dict[str, tuple[str, ...]] = {
    "architecture": ("review", "implement"),
    "correctness": ("review", "implement"),
    "maintainability": ("review",),
    "over-engineering": ("review",),
    "performance": ("performance",),
    "security": ("security",),
    "tests": ("test", "verify"),
    "data-integrity": ("database", "data"),
}


@dataclass(frozen=True)
class RosterAgent:
    """One installed, dispatchable agent the resolver may map a persona onto."""

    subagent_type: str
    capabilities: tuple[str, ...] = ()


def default_personas_dir() -> Path:
    """The bundled ``dummyindex/skills/audit/agents/`` directory.

    Resolved relative to this package so the CLI reads the *shipped* personas,
    not whatever a target repo happens to have under ``.claude/``.
    """
    return Path(__file__).resolve().parents[3] / "skills" / "audit" / "agents"


def load_catalog(personas_dir: Path) -> tuple[PersonaCard, ...]:
    """Parse every ``*.md`` persona in ``personas_dir`` into a ``PersonaCard``.

    Returns an empty tuple if the directory is missing (an install without the
    companion personas) — the caller surfaces that, rather than crashing.
    """
    if not personas_dir.is_dir():
        return ()
    cards: list[PersonaCard] = []
    for md in sorted(personas_dir.glob("*.md")):
        cards.append(parse_persona(md.read_text(encoding="utf-8"), md.stem))
    return tuple(cards)


def parse_persona(text: str, persona_id: str) -> PersonaCard:
    """Build a ``PersonaCard`` from a persona file's text + its filename stem."""
    fm = _parse_frontmatter(text)
    triggers = tuple(
        token.strip() for token in fm.get("triggers", "").split(",") if token.strip()
    )
    return PersonaCard(
        persona_id=persona_id,
        name=fm.get("name", persona_id),
        role=fm.get("role", ""),
        emoji=fm.get("emoji", ""),
        subagent_type=fm.get("subagent_type", "general-purpose"),
        triggers=triggers,
        description=fm.get("description", ""),
    )


def collect_roster(
    project_root: Path, context_dir: Path
) -> tuple[RosterAgent, ...] | None:
    """The repo's installed dispatchable agents, or None when unknowable.

    Sources (project scope only — user-scope ``~/.claude/agents`` belongs to
    the live session's agent list, which the skill consults):

    - ``<project_root>/.claude/agents/*.md`` file stems (capabilities unknown);
    - ``<context_dir>/equipment.json`` items with ``kind == "agent"`` and a
      truthy ``subagent_type`` (skills/hooks/plugins are never Task targets).

    Returns ``None`` when NEITHER source exists — an unequipped repo carries
    no evidence about which global personas are installed, so resolution must
    not downgrade anything. A corrupt ``equipment.json`` degrades to whatever
    the agents dir yields (the source exists, so resolution stays strict).
    """
    agents_dir = project_root / ".claude" / "agents"
    equipment_path = context_dir / "equipment.json"
    if not agents_dir.is_dir() and not equipment_path.is_file():
        return None

    roster: list[RosterAgent] = []
    seen: set[str] = set()

    if equipment_path.is_file():
        from ..equip import EquipError, EquipmentKind, EquipmentSource, read_manifest

        try:
            manifest = read_manifest(context_dir)
        except EquipError:
            manifest = None
        if manifest is not None:
            for item in manifest.items:
                if item.kind != EquipmentKind.AGENT or not item.subagent_type:
                    continue
                # Marketplace plugins are not Task-dispatchable agents. Legacy
                # (schema v3) manifests recorded them with kind=agent, so guard
                # on the source too or a plugin name would leak into the roster.
                if item.source == EquipmentSource.MARKETPLACE:
                    continue
                if item.subagent_type in seen:
                    continue
                seen.add(item.subagent_type)
                roster.append(
                    RosterAgent(
                        subagent_type=item.subagent_type,
                        capabilities=item.capabilities,
                    )
                )

    if agents_dir.is_dir():
        for stem in sorted(p.stem for p in agents_dir.glob("*.md") if p.is_file()):
            if stem in seen:
                continue
            seen.add(stem)
            roster.append(RosterAgent(subagent_type=stem))

    return tuple(roster)


def resolve_catalog(
    cards: tuple[PersonaCard, ...],
    roster: tuple[RosterAgent, ...] | None,
) -> tuple[PersonaCard, ...]:
    """Resolve each card's ``subagent_type`` against the installed roster.

    Pure: returns new ``PersonaCard`` copies (``dataclasses.replace``), never
    mutates. ``roster=None`` (no roster sources) is the identity. Fallback
    order per card: shipped name if installed → equipped agent covering the
    persona's capability → ``general-purpose``; rewrites preserve the shipped
    name in ``requested_subagent_type``.
    """
    if roster is None:
        return cards
    installed = {agent.subagent_type for agent in roster}
    resolved: list[PersonaCard] = []
    for card in cards:
        if card.subagent_type in installed or card.subagent_type == _GENERAL_PURPOSE:
            resolved.append(card)
            continue
        resolved.append(
            replace(
                card,
                subagent_type=_capability_match(card.persona_id, roster)
                or _GENERAL_PURPOSE,
                requested_subagent_type=card.subagent_type,
            )
        )
    return tuple(resolved)


def _capability_match(persona_id: str, roster: tuple[RosterAgent, ...]) -> str | None:
    """The first roster agent covering the persona's capability, if any."""
    for capability in _PERSONA_CAPABILITY_PREFS.get(persona_id, ()):
        for agent in roster:
            if capability in agent.capabilities:
                return agent.subagent_type
    return None


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Read the ``key: value`` pairs from a leading ``---`` frontmatter block.

    Returns an empty dict when the text has no frontmatter. Values keep their
    inline form (no list/nesting support — by design the persona schema is flat).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fm[key.strip()] = value.strip()
    return fm
