"""Load the shipped audit-persona catalog from markdown frontmatter.

Personas are ``dummyindex/skills/audit/agents/*.md`` files with a flat ``---``
frontmatter (``name``, ``role``, ``emoji``, ``subagent_type``, comma-separated
``triggers``, ``description``), hand-parsed with no YAML dependency. Panel
*selection* is the skill's judgment, so nothing here matches; this module parses
the menu and resolves each ``subagent_type`` (:func:`resolve_catalog`).
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

    Project scope only (user-scope agents are the live session's, which the skill
    consults): ``.claude/agents/*.md`` stems plus ``equipment.json`` ``kind ==
    "agent"`` items with a truthy ``subagent_type``. ``None`` when NEITHER source
    exists — an unequipped repo carries no evidence, so resolution must not
    downgrade anything. A corrupt ``equipment.json`` degrades to the agents dir.
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
                # Marketplace plugins aren't Task targets, but schema-v3 manifests
                # recorded them as kind=agent: guard on the source too.
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
