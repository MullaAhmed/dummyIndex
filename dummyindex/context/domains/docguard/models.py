"""Frozen dataclasses for the docguard (managed-doc-home) domain — data only.

``DocClassification`` is the verdict for one path; ``StrayGroup`` pairs classified
paths under one collision-resolved slug. The ``Move*`` records describe migrating
those groups into ``.context/``: one relocation (``MoveItem``), a group's moves
(``PlannedGroup``), the whole plan (``MovePlan``), a reported non-move
(``MoveSkip``) and the applied outcome (``MoveResult``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .enums import DocKind, DocRole


@dataclass(frozen=True)
class DocClassification:
    """The classifier's verdict for one repo-relative ``.md`` path.

    ``in_managed_location`` is ``True`` only under ``.context/``. ``suggested_slug``
    / ``suggested_home`` are repo-relative POSIX strings, or ``None`` when the path
    is not a placeable stray (not a planning doc, or an *unslug-able* one the
    caller must skip + report). ``role`` + ``pairing_stem`` let the grouper merge
    ``<stem>-design.md`` with ``<stem>.md``.
    """

    is_planning_doc: bool
    kind: DocKind
    in_managed_location: bool
    suggested_slug: str | None = None
    suggested_home: str | None = None
    role: DocRole = DocRole.NONE
    pairing_stem: str | None = None
    rel_path: str | None = None


@dataclass(frozen=True)
class StrayGroup:
    """One managed-home slug grouping the spec/plan members in a directory.

    ``spec_path`` / ``plan_path`` (``<stem>-design.md`` / ``<stem>.md``) may be
    ``None`` for a lone member. ``base_slug`` is the slug before disambiguation;
    ``collision`` is ``True`` when ``slug`` was suffixed (``<base>-2``).
    """

    slug: str
    base_slug: str
    kind: DocKind
    directory: str
    pairing_stem: str
    suggested_home: str
    spec_path: str | None = None
    plan_path: str | None = None
    collision: bool = False


@dataclass(frozen=True)
class MoveItem:
    """One file relocation from a stray ``docs/`` path into a managed home.

    ``method`` is empty while only planned; once applied it is ``"git-mv"``
    (tracked source), ``"replace"`` (non-git tree) or ``"replace+add"`` (untracked
    source or refused ``git mv``, staged at the target).
    """

    slug: str
    kind: DocKind
    source_rel: str
    target_rel: str
    method: str = ""


@dataclass(frozen=True)
class PlannedGroup:
    """A stray group resolved to its managed home plus the file moves it needs.

    ``title`` is derived from the primary source's H1, else the base slug.
    """

    slug: str
    kind: DocKind
    home_rel: str
    title: str
    moves: tuple[MoveItem, ...]


@dataclass(frozen=True)
class MoveSkip:
    """A reported non-move: ``target_rel`` is a group's home or the skipped file."""

    slug: str
    kind: DocKind
    target_rel: str
    reason: str


@dataclass(frozen=True)
class MovePlan:
    """The whole transactional migration plan — validated, nothing moved yet.

    ``skipped`` holds groups already reported as non-moves (an existing managed
    home without ``--force``).
    """

    repo_root: Path
    context_dir: Path
    groups: tuple[PlannedGroup, ...]
    skipped: tuple[MoveSkip, ...]


@dataclass(frozen=True)
class MoveResult:
    """The outcome of applying a :class:`MovePlan` (``dry_run``: nothing moved).

    ``moved`` items have ``method`` filled; ``skipped`` holds every non-move,
    plan-level and per-file.
    """

    moved: tuple[MoveItem, ...]
    skipped: tuple[MoveSkip, ...]
    dry_run: bool
