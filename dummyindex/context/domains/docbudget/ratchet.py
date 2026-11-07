"""Doc word-budget ratchet: measure, read, check, update. Pure, root-injectable."""

from __future__ import annotations

from pathlib import Path

from .constants import CONTEXT_CEILING, RATCHET_SEPARATOR, SKILLS_CEILING
from .enums import BudgetGroup
from .models import BudgetViolation, UpdateResult

__all__ = [
    "check",
    "format_ratchet",
    "measure",
    "read_ratchet",
    "scan",
    "update_ratchet",
]

_CONTEXT_GLOBS = (
    ".context/features/*/spec.md",
    ".context/features/*/plan.md",
    ".context/features/*/concerns.md",
    ".context/PROJECT.md",
    ".context/architecture/overview.md",
    ".context/conventions/*.md",
)
_SKILLS_DIR = "dummyindex/skills"
_SKILL_NAME = "SKILL.md"


def measure(path: Path) -> int:
    """Whitespace-separated word count of a UTF-8 file."""
    return len(path.read_text(encoding="utf-8", errors="replace").split())


def is_skill_file(path: Path) -> bool:
    """True only for a file named exactly ``SKILL.md`` (case-sensitive)."""
    return path.name == _SKILL_NAME


def _ceiling(group: BudgetGroup) -> int:
    return SKILLS_CEILING if group is BudgetGroup.SKILLS else CONTEXT_CEILING


def scan(root: Path, group: BudgetGroup) -> dict[str, int]:
    """Word counts for every in-scope doc under ``root``, keyed by POSIX rel path."""
    found: dict[str, int] = {}
    if group is BudgetGroup.SKILLS:
        # Exact-name filter: glob is case-insensitive on Windows (skill.md).
        paths = [p for p in (root / _SKILLS_DIR).rglob("*.md") if is_skill_file(p)]
    else:
        paths = [p for pattern in _CONTEXT_GLOBS for p in root.glob(pattern)]
    for path in paths:
        if path.is_file():
            found[path.relative_to(root).as_posix()] = measure(path)
    return dict(sorted(found.items()))


def read_ratchet(path: Path) -> dict[str, int]:
    """Parse a ratchet file; a missing file is an empty ratchet."""
    if not path.is_file():
        return {}
    entries: dict[str, int] = {}
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        name, sep, words = line.rpartition(RATCHET_SEPARATOR)
        try:
            if not sep or not name:
                raise ValueError("missing tab separator")
            entries[name] = int(words)
        except ValueError as exc:
            raise ValueError(
                f"{path}:{lineno}: malformed ratchet line {line!r}: {exc}"
            ) from exc
    return dict(sorted(entries.items()))


def format_ratchet(ratchet: dict[str, int]) -> str:
    """Sorted `path<TAB>words` lines, LF newlines, trailing newline."""
    lines = [f"{p}{RATCHET_SEPARATOR}{w}" for p, w in sorted(ratchet.items())]
    return "\n".join(lines) + "\n" if lines else ""


def check(
    root: Path,
    ratchet: dict[str, int],
    group: BudgetGroup = BudgetGroup.CONTEXT,
) -> tuple[BudgetViolation, ...]:
    """Violations: growth over recorded size, or unrecorded docs over ceiling."""
    ceiling = _ceiling(group)
    out: list[BudgetViolation] = []
    for rel, words in scan(root, group).items():
        recorded = ratchet.get(rel)
        if recorded is None:
            if words > ceiling:
                out.append(BudgetViolation(rel, words, ceiling, None))
        elif words > recorded:
            out.append(BudgetViolation(rel, words, recorded, recorded))
    return tuple(out)


def update_ratchet(
    root: Path,
    ratchet: dict[str, int],
    group: BudgetGroup = BudgetGroup.CONTEXT,
) -> UpdateResult:
    """Lower entries to current size; never raise one.

    Grown docs keep their old entry and are returned in ``refused``. Every
    unrecorded doc is seeded at its current size (the ceiling applies only in
    ``check`` to unrecorded docs). Entries for docs that no longer exist are
    dropped.
    """
    new: dict[str, int] = {}
    lowered: list[str] = []
    refused: list[BudgetViolation] = []
    for rel, words in scan(root, group).items():
        recorded = ratchet.get(rel)
        if recorded is None:
            new[rel] = words
        elif words > recorded:
            new[rel] = recorded
            refused.append(BudgetViolation(rel, words, recorded, recorded))
        else:
            new[rel] = words
            if words < recorded:
                lowered.append(rel)
    return UpdateResult(dict(sorted(new.items())), tuple(lowered), tuple(refused))
