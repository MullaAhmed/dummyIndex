"""Protected tokens of a doc and the loss check that guards a restyle rewrite."""

from __future__ import annotations

import re
from collections import Counter

from .constants import CONTRACTION_SPECIALS, NEGATION_WORDS
from .errors import TokenLossError
from .models import TokenDiff

_APOS = "['’]"
# Backtick or tilde fence (CommonMark); group 2 is the body.
_FENCE = re.compile(r"(`{3}|~{3})(.*?)\1", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_HEADING = re.compile(r"^(#{1,6})\s", re.MULTILINE)
_LINK_TARGET = re.compile(r"\]\(([^)\s]+)\)")
# Needs a file extension so clock times such as 12:30 are not citations.
_PATH_LINE = re.compile(r"[\w\-./\\]+\.\w+:\d+(?:-\d+)?")
_NUMERAL = re.compile(r"\d+(?:[.,]\d+)*")
_NEGATION = re.compile(
    r"\b(?:" + "|".join(NEGATION_WORDS) + r")\b", re.IGNORECASE
)
_NT_CONTRACTION = re.compile(rf"\b(\w+)n{_APOS}t\b", re.IGNORECASE)


def _expand_contractions(text: str) -> str:
    for short, full in CONTRACTION_SPECIALS:
        pattern = re.escape(short).replace("'", _APOS)
        text = re.sub(rf"\b{pattern}\b", full, text, flags=re.IGNORECASE)
    return _NT_CONTRACTION.sub(r"\1 not", text)


def protected_tokens(text: str) -> Counter[str]:
    """Count each protected token in ``text``.

    Keys: fenced block and inline code (inner text), heading level (`#`..`######`),
    link target, `path:line` citation, numeral, and negation word (lower-cased).
    """
    tokens: Counter[str] = Counter()
    tokens.update(m.group(2).strip() for m in _FENCE.finditer(text))
    outside_fences = _FENCE.sub("\n", text)
    tokens.update(code.strip() for code in _INLINE_CODE.findall(outside_fences))
    tokens.update(m.group(1) for m in _HEADING.finditer(outside_fences))

    prose = _INLINE_CODE.sub(" ", outside_fences)
    tokens.update(_LINK_TARGET.findall(prose))
    prose = _LINK_TARGET.sub(" ", prose)
    tokens.update(_PATH_LINE.findall(prose))
    prose = _PATH_LINE.sub(" ", prose)

    tokens.update(_NUMERAL.findall(prose))
    tokens.update(w.lower() for w in _NEGATION.findall(_expand_contractions(prose)))
    return tokens


def diff_tokens(old: str, new: str) -> TokenDiff:
    """Tokens whose count dropped from ``old`` to ``new`` (lost) or rose (added)."""
    before, after = protected_tokens(old), protected_tokens(new)
    lost = tuple(sorted(k for k in before if before[k] > after[k]))
    added = tuple(sorted(k for k in after if after[k] > before[k]))
    return TokenDiff(lost=lost, added=added)


def assert_tokens_kept(old: str, new: str) -> tuple[str, ...]:
    """Raise ``TokenLossError`` naming each lost token; return the added (warning) tokens."""
    diff = diff_tokens(old, new)
    if diff.lost:
        raise TokenLossError(diff.lost)
    return diff.added
