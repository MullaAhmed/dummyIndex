"""CJK-versus-Latin share of authored prose, ignoring code, URLs and paths."""

from __future__ import annotations

import re

MIN_CHARS = 200
WARN_BELOW = 0.5

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_URL = re.compile(r"https?://\S+")
# ASCII-only classes: Chinese prose has no spaces, so whitespace tokens would drop CJK.
_PATH = re.compile(r"[A-Za-z0-9_.~:-]*[/\\][A-Za-z0-9_./\\~:-]*")
_FILENAME = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9]{1,5}(?![A-Za-z0-9])")
_CJK = re.compile(r"[㐀-䶿一-鿿]")
_LATIN_WORD = re.compile(r"[A-Za-z]+")


def _strip(text: str) -> str:
    for pattern in (_FENCE, _INLINE_CODE, _URL, _PATH, _FILENAME):
        text = pattern.sub(" ", text)
    return text


def cjk_share(text: str) -> float | None:
    """Return CJK / (CJK + Latin words) after stripping code, URLs and paths.

    Returns ``None`` when fewer than ``MIN_CHARS`` non-whitespace characters
    remain or when the text has no countable CJK or Latin tokens.
    """
    stripped = _strip(text)
    if len(re.sub(r"\s", "", stripped)) < MIN_CHARS:
        return None
    cjk = len(_CJK.findall(stripped))
    latin = len(_LATIN_WORD.findall(stripped))
    denominator = cjk + latin
    if denominator == 0:
        return None
    return cjk / denominator


def needs_warning(share: float | None) -> bool:
    return share is not None and share < WARN_BELOW
