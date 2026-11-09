"""Extract the capabilities a proposal demands (spec §6).

``equip --for-proposal S`` harvests the *specialist* capabilities named in
``proposals/S/plan.md`` + ``checklist.md`` via :data:`_PROPOSAL_CAPABILITY_TOKENS`.
They feed ``build_catalog`` as ``proposal_capabilities``. The CLI validates the slug.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..constants import _PROPOSAL_CAPABILITY_TOKENS

_PROPOSAL_TEXT_FILES: tuple[str, ...] = ("plan.md", "checklist.md")

# Alphanumeric runs, lowercased. Whole-word matching (rather than bare substring)
# so a short token like ``ui`` does not false-match inside ``build`` / ``guide``.
_WORD_RE = re.compile(r"[a-z0-9]+")


def extract_proposal_capabilities(proposal_dir: Path) -> tuple[str, ...]:
    """Read a proposal's plan + checklist and return the capabilities it implies.

    Both files are optional. Returns each matching capability once, in table
    order, or ``()`` when neither file exists or no specialist token matches.
    """
    text = _read_proposal_text(proposal_dir)
    return capabilities_from_text(text)


def capabilities_from_text(text: str) -> tuple[str, ...]:
    """Capabilities implied by ``text`` via the narrow proposal token table."""
    words = _WORD_RE.findall(text.lower())
    out: list[str] = []
    for capability, tokens in _PROPOSAL_CAPABILITY_TOKENS:
        if _any_token_hits(tokens, words) and capability not in out:
            out.append(capability)
    return tuple(out)


def _any_token_hits(tokens: tuple[str, ...], words: list[str]) -> bool:
    """True when any ``token`` matches a whole word or is a prefix of one.

    Whole-word/prefix matching (never bare substring) keeps a short token like
    ``ui`` from firing inside ``build``, while a deliberate prefix token like
    ``optimi`` still catches ``optimize`` / ``optimization``.
    """
    return any(
        word == token or word.startswith(token) for token in tokens for word in words
    )


def _read_proposal_text(proposal_dir: Path) -> str:
    parts: list[str] = []
    for name in _PROPOSAL_TEXT_FILES:
        path = proposal_dir / name
        if not path.is_file():
            continue
        try:
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(parts)
