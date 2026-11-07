from __future__ import annotations

import re

_INVISIBLE = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]"
)
_INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) instructions|</?(system|instructions?)>|<\|im_(start|end)\|>|<!-- dummyindex:",
    re.I,
)


def scan_text(text: str) -> tuple[str, ...]:
    """Return quarantine reasons for hostile text, empty when clean."""
    reasons: list[str] = []
    if _INVISIBLE.search(text):
        reasons.append("invisible-unicode")
    if _INJECTION.search(text):
        reasons.append("injection-marker")
    return tuple(reasons)
