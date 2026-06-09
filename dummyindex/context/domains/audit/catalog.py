"""Load the shipped audit-persona catalog from markdown frontmatter.

Each persona is a markdown file under ``dummyindex/skills/audit/agents/`` with a
small ``---`` frontmatter block (``name``, ``role``, ``emoji``,
``subagent_type``, ``triggers``, ``description``). The catalog is the menu the
``/dummyindex-audit`` skill picks a task-relevant panel from — the *selection*
is the skill's (the LLM's) judgment, so there is deliberately no matching logic
here. This module only parses and emits the menu.

Frontmatter is hand-parsed (no YAML dependency, matching the rest of the
package). ``triggers`` is a comma-separated string so a list never needs YAML.
"""
from __future__ import annotations

from pathlib import Path

from .models import PersonaCard


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
        token.strip()
        for token in fm.get("triggers", "").split(",")
        if token.strip()
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
