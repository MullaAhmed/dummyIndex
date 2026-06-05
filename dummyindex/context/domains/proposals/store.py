"""Read/write the on-disk ``.context/proposals/<slug>/`` artifact.

Four template files are scaffolded by ``ensure_proposal``:

- ``proposal.json``  — the structured head (``Proposal.to_dict``).
- ``spec.md``        — intent / contracts / **Acceptance** checklist.
- ``plan.md``        — ordered tasks naming file paths.
- ``checklist.md``   — flat ``- [ ]`` list derived from plan + acceptance.

All writes are atomic (tmp + ``replace``). No ``print`` here — the CLI prints.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .._io import write_text_atomic
from .errors import ProposalExistsError, ProposalSlugError
from .models import ConsistencyHits, Proposal

# Folder under `.context/` that holds every proposal.
PROPOSALS_REL = "proposals"

# Marker for the consistency block injected into spec.md. Kept as a sentinel
# so a re-scan can rewrite the block in place without duplicating it.
_CONSISTENCY_BEGIN = "<!-- dummyindex:consistency:begin -->"
_CONSISTENCY_END = "<!-- dummyindex:consistency:end -->"

_SLUG_OK_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_")

# Names of the four scaffolded files, in the order they're created.
_TEMPLATE_FILES = ("proposal.json", "spec.md", "plan.md", "checklist.md")


def validate_slug(slug: str) -> str:
    """Lowercase, charset-safe folder name. Raises ``ProposalSlugError``.

    Guards the ``.context/proposals/<slug>/`` path against traversal
    (``../``) and other unsafe folder names.
    """
    if not slug or not slug.strip():
        raise ProposalSlugError(slug, "must not be empty")
    lowered = slug.strip().lower()
    if any(ch not in _SLUG_OK_CHARS for ch in lowered):
        raise ProposalSlugError(
            slug, "must be lowercase letters, digits, '-', '_'"
        )
    if lowered.startswith("-") or lowered.endswith("-"):
        raise ProposalSlugError(slug, "must not start or end with '-'")
    return lowered


def proposals_root(context_dir: Path) -> Path:
    """``.context/proposals/`` for a given ``.context/`` directory."""
    return context_dir / PROPOSALS_REL


def proposal_dir(context_dir: Path, slug: str) -> Path:
    """``.context/proposals/<slug>/`` for a validated slug."""
    return proposals_root(context_dir) / validate_slug(slug)


def ensure_proposal(
    context_dir: Path,
    slug: str,
    title: str,
    *,
    force: bool = False,
) -> tuple[str, ...]:
    """Create ``.context/proposals/<slug>/`` plus the four template files.

    Returns the repo-relative POSIX paths of the files written. Raises
    ``ProposalExistsError`` if the directory exists and ``force`` is False,
    and ``ProposalSlugError`` for an unsafe slug.
    """
    safe_slug = validate_slug(slug)
    target = proposal_dir(context_dir, safe_slug)
    if target.exists() and not force:
        raise ProposalExistsError(safe_slug, str(target))

    target.mkdir(parents=True, exist_ok=True)
    proposal = Proposal(slug=safe_slug, title=title)

    written: list[str] = []
    write_text_atomic(
        target / "proposal.json",
        json.dumps(proposal.to_dict(), indent=2) + "\n",
    )
    written.append("proposal.json")

    write_text_atomic(target / "spec.md", _spec_template(title))
    written.append("spec.md")

    write_text_atomic(target / "plan.md", _plan_template(title))
    written.append("plan.md")

    write_text_atomic(target / "checklist.md", _checklist_template(title))
    written.append("checklist.md")

    return tuple(f"{PROPOSALS_REL}/{safe_slug}/{name}" for name in written)


def read_proposal(context_dir: Path, slug: str) -> Proposal:
    """Load ``proposal.json`` for a slug. Raises ``FileNotFoundError`` if absent."""
    path = proposal_dir(context_dir, slug) / "proposal.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Proposal.from_dict(payload)


def apply_consistency(
    context_dir: Path, slug: str, hits: ConsistencyHits
) -> Proposal:
    """Persist consistency hits into ``proposal.json`` + ``spec.md``.

    Returns the updated ``Proposal`` (a new frozen copy — the input is never
    mutated). Idempotent: re-running rewrites the ``## Consistency`` block in
    ``spec.md`` in place rather than appending a second one.
    """
    safe_slug = validate_slug(slug)
    target = proposal_dir(context_dir, safe_slug)

    current = read_proposal(context_dir, safe_slug)
    updated = dataclasses.replace(
        current,
        related_features=hits.related_features,
        conventions=hits.conventions,
    )
    write_text_atomic(
        target / "proposal.json",
        json.dumps(updated.to_dict(), indent=2) + "\n",
    )

    spec_path = target / "spec.md"
    existing = (
        spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
    )
    write_text_atomic(spec_path, _inject_consistency(existing, hits))
    return updated


# ----- templates ------------------------------------------------------------


def _spec_template(title: str) -> str:
    return (
        f"# Spec — {title}\n\n"
        "> Scaffolded by `dummyindex context propose`. Flesh out the intent\n"
        "> and contracts below, then keep the **Acceptance** checklist honest.\n\n"
        "## Intent\n\n"
        "_What problem does this solve, and for whom?_\n\n"
        "## Contracts\n\n"
        "_Inputs, outputs, invariants, and the seams this touches._\n\n"
        "## Acceptance\n\n"
        "- [ ] _First observable, testable acceptance criterion._\n\n"
        f"{_consistency_block(ConsistencyHits())}\n"
    )


def _plan_template(title: str) -> str:
    return (
        f"# Plan — {title}\n\n"
        "> Ordered, file-path-naming tasks. Cite reused symbols from\n"
        "> `.context/map/symbols.json` where you can reuse instead of writing new.\n\n"
        "## Tasks\n\n"
        "1. _First task — name the file path(s) it touches._\n"
    )


def _checklist_template(title: str) -> str:
    return (
        f"# Checklist — {title}\n\n"
        "> Flat, top-to-bottom list derived from the plan tasks + the spec's\n"
        "> Acceptance items. Tick `- [x]` only after verifying each item.\n\n"
        "- [ ] _First derived checklist item._\n"
    )


# ----- consistency block injection ------------------------------------------


def _consistency_block(hits: ConsistencyHits) -> str:
    lines = [_CONSISTENCY_BEGIN, "## Consistency", ""]
    if hits.related_features:
        lines.append("**Related features:**")
        lines.append("")
        for fid in hits.related_features:
            lines.append(f"- `{fid}`")
        lines.append("")
    else:
        lines.append("_No related features detected by the consistency scan._")
        lines.append("")
    if hits.conventions:
        lines.append("**Conventions to honor:**")
        lines.append("")
        for conv in hits.conventions:
            lines.append(f"- `{conv}`")
        lines.append("")
    else:
        lines.append("_No `.context/conventions/*.md` files found._")
        lines.append("")
    lines.append(_CONSISTENCY_END)
    return "\n".join(lines)


def _inject_consistency(spec_text: str, hits: ConsistencyHits) -> str:
    """Replace the consistency block in ``spec_text`` (or append one)."""
    block = _consistency_block(hits)
    begin = spec_text.find(_CONSISTENCY_BEGIN)
    end = spec_text.find(_CONSISTENCY_END)
    if begin != -1 and end != -1 and end > begin:
        before = spec_text[:begin]
        after = spec_text[end + len(_CONSISTENCY_END):]
        return before + block + after
    return spec_text.rstrip() + "\n\n" + block + "\n"
