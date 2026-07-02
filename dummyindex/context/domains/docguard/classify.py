"""Path-based classifier: is a ``.md`` path a stray planning doc, and where does
it belong?

The single source of truth for "this markdown is an internal planning artifact
that leaked outside ``.context/``." Pure and filesystem-free — it reasons only
over the repo-relative *path shape*, so it is cheap enough for the PreToolUse
write-guard hot path and exhaustively unit-testable from constructed paths.

Two public entry points:

- ``classify_doc_path(repo_root, path) -> DocClassification`` — verdict for one
  path (location-gated heuristics + slug derivation + spec/plan role).
- ``group_strays(repo_root, paths) -> tuple[StrayGroup, ...]`` — pairs
  ``<stem>-design.md`` with ``<stem>.md`` under one slug, disambiguates
  same-slug collisions across directories, and reports them.

Classification is *conservative* and *location-gated*: a planning-shaped
filename (``*-design.md`` / ``YYYY-MM-DD-<name>.md``) is a stray only when it
lives under ``docs/`` — ``src/widget-design.md`` is never a stray.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from ..audit.workspace import slugify
from ..proposals.errors import ProposalSlugError
from ..proposals.store import validate_slug
from .constants import (
    AUDIT_SEGMENT,
    AUDITS_REL,
    CONTEXT_DIR_NAME,
    DESIGN_SUFFIX,
    DOCS_DIR_NAME,
    EXCLUDED_DOCS_SUBTREES,
    MARKDOWN_SUFFIX,
    PLANNING_SEGMENTS,
    PROPOSALS_REL,
    ROOT_DOC_STEMS,
)
from .enums import DocKind, DocRole
from .errors import DocPathError
from .models import DocClassification, StrayGroup

# At least one alphanumeric char ⇒ the stem has slug-able content.
_ALNUM = re.compile(r"[a-z0-9]")
# ``YYYY-MM-DD-<name>`` planning-doc filename convention (name must be non-empty).
_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-.+")


def classify_doc_path(repo_root: Path | str, path: Path | str) -> DocClassification:
    """Classify a single path. Raises ``DocPathError`` if it escapes ``repo_root``.

    See the module docstring for the gate order. The function performs **no**
    I/O — it operates lexically on the repo-relative path components, so callers
    can classify a path that does not exist on disk.
    """
    rel_posix = _rel_posix(repo_root, path)
    rel = Path(rel_posix)
    parts = rel.parts

    # Managed location: anything under .context/ is never a stray.
    if parts and parts[0] == CONTEXT_DIR_NAME:
        return DocClassification(
            is_planning_doc=False,
            kind=DocKind.NONE,
            in_managed_location=True,
            rel_path=rel_posix,
        )

    not_planning = DocClassification(
        is_planning_doc=False,
        kind=DocKind.NONE,
        in_managed_location=False,
        rel_path=rel_posix,
    )

    # Only markdown is ever a planning doc.
    if rel.suffix.lower() != MARKDOWN_SUFFIX:
        return not_planning

    # Root-level project chrome (README/CHANGELOG/ARCHITECTURE/SECURITY).
    if len(parts) == 1 and rel.stem.lower() in ROOT_DOC_STEMS:
        return not_planning

    # Location gate: a stray only ever lives under docs/.
    if not parts or parts[0] != DOCS_DIR_NAME:
        return not_planning

    interior = parts[1:-1]  # dir segments between docs/ and the filename
    # Published docs subtrees (guide/reference/sources) are never strays.
    if interior and interior[0] in EXCLUDED_DOCS_SUBTREES:
        return not_planning

    segments = set(interior)
    in_planning_segment = bool(segments & PLANNING_SEGMENTS)
    role, pairing_stem = _role_and_stem(rel.stem)
    filename_is_planning = role is DocRole.SPEC or _is_dated(rel.stem)

    if not (in_planning_segment or filename_is_planning):
        return not_planning

    kind = DocKind.AUDIT if AUDIT_SEGMENT in segments else DocKind.PROPOSAL
    slug = _derive_slug(pairing_stem)
    home = _home_for(kind, slug) if slug is not None else None
    return DocClassification(
        is_planning_doc=True,
        kind=kind,
        in_managed_location=False,
        suggested_slug=slug,
        suggested_home=home,
        role=role,
        pairing_stem=pairing_stem,
        rel_path=rel_posix,
    )


def group_strays(
    repo_root: Path | str, paths: Iterable[Path | str]
) -> tuple[StrayGroup, ...]:
    """Pair + group placeable strays under collision-disambiguated slugs.

    Classifies each path, keeps only *placeable* planning docs (planning + a
    non-``None`` slug — unslug-able strays are dropped here for the caller to
    surface separately), buckets them by ``(directory, pairing_stem)`` so a spec
    and its plan merge, then walks the buckets in deterministic sorted order
    disambiguating same-base-slug collisions across directories (``<slug>`` then
    ``<slug>-2`` …) and flagging each suffixed group.
    """
    buckets: dict[tuple[str, str], list[DocClassification]] = {}
    for raw in paths:
        dc = classify_doc_path(repo_root, raw)
        if not dc.is_planning_doc or dc.suggested_slug is None:
            continue
        directory = _parent_posix(dc.rel_path or "")
        buckets.setdefault((directory, dc.pairing_stem or ""), []).append(dc)

    groups: list[StrayGroup] = []
    used: set[str] = set()
    for directory, pairing_stem in sorted(buckets):
        members = buckets[(directory, pairing_stem)]
        kind = (
            DocKind.AUDIT
            if any(m.kind is DocKind.AUDIT for m in members)
            else DocKind.PROPOSAL
        )
        # All members share a pairing_stem, hence the same base slug.
        base_slug = next(m.suggested_slug for m in members if m.suggested_slug)
        spec_path = next((m.rel_path for m in members if m.role is DocRole.SPEC), None)
        plan_path = next((m.rel_path for m in members if m.role is DocRole.PLAN), None)
        slug, collision = _disambiguate(base_slug, used)
        used.add(slug)
        groups.append(
            StrayGroup(
                slug=slug,
                base_slug=base_slug,
                kind=kind,
                directory=directory,
                pairing_stem=pairing_stem,
                suggested_home=_home_for(kind, slug),
                spec_path=spec_path,
                plan_path=plan_path,
                collision=collision,
            )
        )
    return tuple(groups)


# ----- helpers --------------------------------------------------------------


def _rel_posix(repo_root: Path | str, path: Path | str) -> str:
    """Repo-relative POSIX path. Raises ``DocPathError`` if outside the root.

    Lexical only (``Path.relative_to``) — no ``resolve()``, so classification
    never touches the filesystem.
    """
    root = Path(repo_root)
    target = Path(path)
    try:
        return target.relative_to(root).as_posix()
    except ValueError as exc:
        raise DocPathError(str(target), str(root)) from exc


def _role_and_stem(stem: str) -> tuple[DocRole, str]:
    """Spec-vs-plan role + the pairing stem for a filename stem.

    ``<x>-design`` is the SPEC member whose pairing stem is ``<x>``; everything
    else is the PLAN member whose pairing stem is the full stem. A bare
    ``-design`` (no prefix) is treated as a plan so the pairing key never empties
    from the suffix alone.
    """
    if stem.endswith(DESIGN_SUFFIX) and len(stem) > len(DESIGN_SUFFIX):
        return DocRole.SPEC, stem[: -len(DESIGN_SUFFIX)]
    return DocRole.PLAN, stem


def _is_dated(stem: str) -> bool:
    """Whether the stem matches the ``YYYY-MM-DD-<name>`` planning convention."""
    return bool(_DATE_PREFIX.match(stem))


def _derive_slug(pairing_stem: str) -> str | None:
    """``slugify(stem)`` then ``validate_slug``; ``None`` when unslug-able.

    ``slugify`` always returns a charset-safe value, falling back to the generic
    ``"audit"`` sentinel for content-free input — which would silently collapse
    every symbol-only filename onto one slug. We treat a stem with no
    alphanumeric content as *unslug-able* (return ``None``) so the caller can
    skip + report it instead of minting a meaningless home. ``validate_slug`` is
    still applied defensively; a raise (it never propagates) also yields ``None``.
    """
    if not _ALNUM.search(pairing_stem.lower()):
        return None
    try:
        return validate_slug(slugify(pairing_stem))
    except ProposalSlugError:
        return None


def _home_for(kind: DocKind, slug: str) -> str:
    """Repo-relative POSIX managed home for a kind + final slug."""
    rel = AUDITS_REL if kind is DocKind.AUDIT else PROPOSALS_REL
    return f"{CONTEXT_DIR_NAME}/{rel}/{slug}"


def _parent_posix(rel_path: str) -> str:
    """POSIX parent directory of a repo-relative path ("" for a top-level file)."""
    parent = Path(rel_path).parent.as_posix()
    return "" if parent == "." else parent


def _disambiguate(base_slug: str, used: set[str]) -> tuple[str, bool]:
    """Return a slug unused in ``used`` and whether it had to be suffixed."""
    if base_slug not in used:
        return base_slug, False
    n = 2
    while f"{base_slug}-{n}" in used:
        n += 1
    return f"{base_slug}-{n}", True
