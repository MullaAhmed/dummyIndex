"""Frozen dataclasses for the audit artifact.

An audit workspace lives at ``.context/audits/<slug>/``. ``audit.json`` carries
the structured head (``AuditConfig``); ``catalog.json`` carries the persona
catalog the skill picks the panel from; the findings + report are markdown the
agents author. Python only models the structured heads — the *auditing* is the
agents, not a deterministic computation here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import CouncilMode, ModelChoice
from .enums import MAX_REBUTTAL_ROUNDS
from .errors import AuditError

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AuditConfig:
    """The structured head of an audit workspace, persisted as ``audit.json``.

    ``model`` is required at construction (no default) — the model is never
    silently defaulted; the caller resolves it explicitly before building this.
    """

    slug: str
    description: str
    mode: CouncilMode
    model: ModelChoice
    scope: tuple[str, ...] = ()
    max_rounds: int = MAX_REBUTTAL_ROUNDS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "slug": self.slug,
            "description": self.description,
            "mode": self.mode.value,
            "model": self.model.value,
            "scope": list(self.scope),
            "max_rounds": self.max_rounds,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AuditConfig":
        version = payload.get("schema_version")
        if version != SCHEMA_VERSION:
            raise AuditError(
                f"audit.json schema_version must be {SCHEMA_VERSION}, got {version!r}"
            )
        # The model is never silently defaulted — even on load. ``to_dict``
        # always emits it, so a missing key means a hand-broken file; fail loud.
        if "model" not in payload:
            raise AuditError("audit.json is missing 'model' (never silently defaulted)")
        return cls(
            slug=str(payload.get("slug", "")),
            description=str(payload.get("description", "")),
            mode=CouncilMode(payload.get("mode", CouncilMode.STANDARD.value)),
            model=ModelChoice(payload["model"]),
            scope=tuple(str(x) for x in (payload.get("scope") or ())),
            max_rounds=int(payload.get("max_rounds", MAX_REBUTTAL_ROUNDS)),
        )


@dataclass(frozen=True)
class PersonaCard:
    """One catalog entry, parsed from a persona markdown file's frontmatter.

    ``persona_id`` is the filename stem (e.g. ``security``); ``subagent_type``
    is the real Claude Code agent the skill dispatches via the Task tool;
    ``triggers`` are free-text hints the skill weighs when picking the panel.
    """

    persona_id: str
    name: str
    role: str
    emoji: str
    subagent_type: str
    triggers: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "name": self.name,
            "role": self.role,
            "emoji": self.emoji,
            "subagent_type": self.subagent_type,
            "triggers": list(self.triggers),
            "description": self.description,
        }


@dataclass(frozen=True)
class AuditStart:
    """The result of scaffolding an audit workspace — what the CLI emits."""

    slug: str
    config: AuditConfig
    catalog: tuple[PersonaCard, ...]
    written: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "dir": f"audits/{self.slug}",
            "mode": self.config.mode.value,
            "model": self.config.model.value,
            "max_rounds": self.config.max_rounds,
            "scope": list(self.config.scope),
            "written": list(self.written),
            "catalog": [card.to_dict() for card in self.catalog],
        }
