"""Scaffold + read the on-disk ``.context/audits/<slug>/`` workspace.

``ensure_audit`` creates the workspace and its three scaffolded artifacts:

- ``audit.json``      — the structured head (``AuditConfig.to_dict``).
- ``description.md``  — the human-readable brief (the request + scope).
- ``catalog.json``    — the persona menu the skill picks the panel from.
- ``findings/``       — empty dir the per-persona finding files land in.

Unlike ``propose``, audit does **not** require a pre-existing ``.context/`` —
an on-demand audit can run on any repo; the workspace is created on demand.
All writes are atomic (tmp + ``replace``). No ``print`` here — the CLI prints.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import EllipsisType
from typing import Optional, Sequence, Union

from ..atomic_io import write_text_atomic
from ..config import ConfigError, CouncilMode, ModelChoice, read_config
from .catalog import (
    RosterAgent,
    collect_roster,
    default_personas_dir,
    load_catalog,
    resolve_catalog,
)
from .enums import MAX_REBUTTAL_ROUNDS
from .errors import (
    AuditError,
    AuditExistsError,
    AuditNotFoundError,
    AuditSlugError,
    ModelRequiredError,
)
from .models import AuditConfig, AuditStart

# Folder under `.context/` that holds every audit.
AUDITS_REL = "audits"

_SLUG_OK_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_")
_SLUG_MAX_LEN = 60


def validate_slug(slug: str) -> str:
    """Lowercase, charset-safe folder name. Raises ``AuditSlugError``.

    Guards the ``.context/audits/<slug>/`` path against traversal (``../``)
    and other unsafe folder names.
    """
    if not slug or not slug.strip():
        raise AuditSlugError(slug, "must not be empty")
    lowered = slug.strip().lower()
    if any(ch not in _SLUG_OK_CHARS for ch in lowered):
        raise AuditSlugError(slug, "must be lowercase letters, digits, '-', '_'")
    if lowered.startswith("-") or lowered.endswith("-"):
        raise AuditSlugError(slug, "must not start or end with '-'")
    return lowered


def slugify(description: str) -> str:
    """Derive a safe slug from a free-text description (deterministic).

    Lowercases, collapses every run of non-alphanumerics to a single ``-``,
    trims, and caps the length. Falls back to ``"audit"`` for an empty result.
    """
    collapsed = re.sub(r"[^a-z0-9]+", "-", description.strip().lower()).strip("-")
    capped = collapsed[:_SLUG_MAX_LEN].strip("-")
    return capped or "audit"


def audits_root(context_dir: Path) -> Path:
    """``.context/audits/`` for a given ``.context/`` directory."""
    return context_dir / AUDITS_REL


def audit_dir(context_dir: Path, slug: str) -> Path:
    """``.context/audits/<slug>/`` for a validated slug."""
    return audits_root(context_dir) / validate_slug(slug)


def resolve_model(context_dir: Path, model_flag: Optional[str]) -> ModelChoice:
    """Resolve the model to run the audit on — never silently defaulted.

    Precedence: explicit ``--model`` flag → persisted ``.context/config.json``
    → ``ModelRequiredError``. An invalid ``--model`` value raises ``AuditError``.
    """
    if model_flag:
        try:
            return ModelChoice(model_flag)
        except ValueError as exc:
            allowed = ", ".join(m.value for m in ModelChoice)
            raise AuditError(
                f"--model {model_flag!r} is not one of: {allowed}"
            ) from exc
    try:
        cfg = read_config(context_dir)
    except ConfigError:
        cfg = None
    if cfg is not None:
        return cfg.model
    raise ModelRequiredError()


def resolve_mode(context_dir: Path, mode_flag: Optional[str]) -> CouncilMode:
    """Resolve the effort mode: ``--mode`` → config → ``standard`` default.

    Unlike the model, the mode *may* be defaulted (standard) — only the model
    is the never-silent-default field.
    """
    if mode_flag:
        try:
            return CouncilMode(mode_flag)
        except ValueError as exc:
            allowed = ", ".join(m.value for m in CouncilMode)
            raise AuditError(
                f"--mode {mode_flag!r} is not one of: {allowed}"
            ) from exc
    try:
        cfg = read_config(context_dir)
    except ConfigError:
        cfg = None
    if cfg is not None:
        return cfg.mode
    return CouncilMode.STANDARD


def ensure_audit(
    context_dir: Path,
    *,
    description: str,
    mode: CouncilMode,
    model: ModelChoice,
    scope: Sequence[str] = (),
    slug: Optional[str] = None,
    force: bool = False,
    personas_dir: Optional[Path] = None,
    roster: Union[Optional[tuple[RosterAgent, ...]], EllipsisType] = ...,
) -> AuditStart:
    """Create ``.context/audits/<slug>/`` plus its scaffolded artifacts.

    ``slug`` defaults to ``slugify(description)``. Raises ``AuditExistsError``
    when the directory exists and ``force`` is False, and ``AuditSlugError``
    for an unsafe explicit slug.

    The emitted catalog's ``subagent_type`` values are resolved against the
    repo's installed roster (see ``catalog.resolve_catalog``). ``roster``
    defaults to ``collect_roster(context_dir.parent, context_dir)``; pass an
    explicit tuple (or ``None`` for the no-sources identity) to override.
    """
    if not description or not description.strip():
        raise AuditError("an audit description is required (--describe)")

    safe_slug = validate_slug(slug) if slug else slugify(description)
    target = audit_dir(context_dir, safe_slug)
    if target.exists() and not force:
        raise AuditExistsError(safe_slug, str(target))

    target.mkdir(parents=True, exist_ok=True)
    (target / "findings").mkdir(exist_ok=True)

    config = AuditConfig(
        slug=safe_slug,
        description=description.strip(),
        mode=mode,
        model=model,
        scope=tuple(scope),
        max_rounds=MAX_REBUTTAL_ROUNDS,
    )

    written: list[str] = []
    write_text_atomic(
        target / "audit.json",
        json.dumps(config.to_dict(), indent=2) + "\n",
    )
    written.append("audit.json")

    write_text_atomic(target / "description.md", _description_template(config))
    written.append("description.md")

    if roster is ...:
        roster = collect_roster(context_dir.parent, context_dir)
    catalog = resolve_catalog(
        load_catalog(personas_dir or default_personas_dir()), roster
    )
    write_text_atomic(
        target / "catalog.json",
        json.dumps([card.to_dict() for card in catalog], indent=2) + "\n",
    )
    written.append("catalog.json")

    rel = tuple(f"{AUDITS_REL}/{safe_slug}/{name}" for name in written)
    return AuditStart(
        slug=safe_slug,
        config=config,
        catalog=catalog,
        written=rel,
    )


def read_audit(context_dir: Path, slug: str) -> AuditConfig:
    """Load ``audit.json`` for a slug. Raises ``AuditNotFoundError`` if absent."""
    path = audit_dir(context_dir, slug) / "audit.json"
    if not path.exists():
        raise AuditNotFoundError(slug, str(path))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return AuditConfig.from_dict(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        # ValueError covers a bad enum value (mode/model) from from_dict;
        # from_dict's own AuditError (bad schema/missing model) propagates as-is.
        raise AuditError(f"could not read {path}: {exc}") from exc


# ----- templates ------------------------------------------------------------


def _description_template(config: AuditConfig) -> str:
    scope_block = (
        "\n".join(f"- `{path}`" for path in config.scope)
        if config.scope
        else "_Whole repository (no --scope given)._"
    )
    return (
        f"# Audit — {config.slug}\n\n"
        "> Scaffolded by `dummyindex context audit start`. The "
        "`/dummyindex-audit` skill drives the argue-and-audit panel from here.\n\n"
        "## Request\n\n"
        f"{config.description}\n\n"
        "## Scope\n\n"
        f"{scope_block}\n\n"
        f"## Settings\n\n"
        f"- mode: `{config.mode.value}`\n"
        f"- model: `{config.model.value}`\n"
        f"- max rebuttal rounds: {config.max_rounds}\n"
    )
