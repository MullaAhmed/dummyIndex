"""Frozen dataclasses for the docguard (managed-doc-home) domain.

Data only — no behaviour. ``DocClassification`` is the classifier's verdict for
a single repo-relative path; ``StrayGroup`` is the result of pairing/grouping
several classified paths under one collision-resolved managed-home slug. The
``Move*`` records describe the migration of those stray groups into their
managed ``.context/`` homes: ``MoveItem`` is one planned/executed file
relocation, ``PlannedGroup`` bundles a group's relocations under its resolved
home, ``MovePlan`` is the whole transactional plan, ``MoveSkip`` is a reported
non-move, and ``MoveResult`` is the outcome of applying a plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .enums import DocKind, DocRole


@dataclass(frozen=True)
class DocClassification:
    """The classifier's verdict for one repo-relative ``.md`` path.

    ``is_planning_doc`` is the headline signal. ``kind`` names the managed-home
    family the stray would relocate into. ``in_managed_location`` is ``True``
    only for a path already under ``.context/``. ``suggested_slug`` /
    ``suggested_home`` are repo-relative POSIX strings, or ``None`` when the path
    is not a placeable stray — either because it is not a planning doc at all, or
    because its filename carries no slug-able content (an *unslug-able* stray the
    caller must skip + report rather than mint a meaningless home). ``role`` and
    ``pairing_stem`` expose the spec-vs-plan pairing key so the grouping helper
    can merge ``<stem>-design.md`` with its ``<stem>.md``. ``rel_path`` is the
    repo-relative POSIX path that was classified.
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

    ``spec_path`` / ``plan_path`` are the repo-relative POSIX paths of the
    ``<stem>-design.md`` and ``<stem>.md`` members; either may be ``None`` for a
    lone spec or lone plan. ``slug`` is the final, collision-disambiguated slug
    and ``suggested_home`` is built from it; ``base_slug`` is what the
    directory's stem slugified to *before* disambiguation, and ``collision`` is
    ``True`` when ``slug`` was suffixed (``<base>-2``) to avoid clashing with an
    earlier group's slug.
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

    ``source_rel`` / ``target_rel`` are repo-relative POSIX paths: the source
    under ``docs/`` and the target under ``.context/<home>/`` (``spec.md`` /
    ``plan.md`` for a proposal, ``report.md`` for an audit). ``method`` is empty
    while the item is only *planned*; once applied it records how the move was
    executed — ``"git-mv"`` (tracked source, history preserved), ``"replace"``
    (non-git tree), or ``"replace+add"`` (untracked source staged at the target).
    """

    slug: str
    kind: DocKind
    source_rel: str
    target_rel: str
    method: str = ""


@dataclass(frozen=True)
class PlannedGroup:
    """A stray group resolved to its managed home plus the file moves it needs.

    ``home_rel`` is the repo-relative POSIX managed home directory and ``title``
    is the proposal/audit title derived from the primary source's H1 (or the
    fallback). ``moves`` are the relocations that materialise the group.
    """

    slug: str
    kind: DocKind
    home_rel: str
    title: str
    moves: tuple[MoveItem, ...]


@dataclass(frozen=True)
class MoveSkip:
    """A reported non-move — a whole group or a single file left in place.

    ``target_rel`` names what was skipped (the managed home for a group-level
    skip, or the specific target file for a per-file clobber-protection skip)
    and ``reason`` is the human-readable explanation the CLI surfaces.
    """

    slug: str
    kind: DocKind
    target_rel: str
    reason: str


@dataclass(frozen=True)
class MovePlan:
    """The whole transactional migration plan — validated, nothing moved yet.

    ``repo_root`` / ``context_dir`` anchor the absolute paths the apply step
    rebuilds from the relative move records. ``groups`` are the relocations to
    perform; ``skipped`` are the groups already reported as non-moves (an
    existing managed home without ``--force``).
    """

    repo_root: Path
    context_dir: Path
    groups: tuple[PlannedGroup, ...]
    skipped: tuple[MoveSkip, ...]


@dataclass(frozen=True)
class MoveResult:
    """The outcome of applying a :class:`MovePlan`.

    ``moved`` are the executed :class:`MoveItem` records (``method`` filled);
    ``skipped`` carries every reported non-move (plan-level plus per-file
    clobber-protection skips). ``dry_run`` is ``True`` when the plan was only
    previewed (``yes=False``) and nothing was moved.
    """

    moved: tuple[MoveItem, ...]
    skipped: tuple[MoveSkip, ...]
    dry_run: bool
