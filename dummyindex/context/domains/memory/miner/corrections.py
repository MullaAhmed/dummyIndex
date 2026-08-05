"""Extract and aggregate explicit human corrections about named skills.

This is a high-precision grammar, not semantic classification. It recognizes
direct requests and complaints that name a ``... skill``, plus explicit
revocations. Raw prompt text is used only while parsing and is never retained
in the returned aggregate.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import datetime

from .enums import (
    DEFAULT_MIN_SKILL_CORRECTIONS,
    MAX_SKILL_SLUG_CHARS,
    SkillDirectiveKind,
)
from .models import (
    RecurringSkillCorrection,
    SkillDirective,
    SkillDirectiveEvent,
)

_SKILL_CAPTURE = (
    r"(?P<skill>[/\$]?[a-z0-9][a-z0-9_-]*"
    r"(?:\s+[a-z0-9][a-z0-9_-]*){0,3})"
)
_ACTION = r"(?:use|using|invoke|invoking|apply|applying|follow|following)"
_SENTENCE_START = r"(?:^|(?<=[.!?])\s+)"

_POSITIVE_PATTERNS = (
    # Direct request: "use ADHD skill", "please invoke dummyindex plan skill".
    re.compile(
        _SENTENCE_START + r"(?:(?:please|actually|now|so)\b[,\s]+|"
        r"(?:can|could|would)\s+you\s+)?"
        r"(?:use|invoke|apply|follow)\s+(?:the\s+)?" + _SKILL_CAPTURE + r"\s+skill\b",
        re.IGNORECASE,
    ),
    # Requirement: "you need/must/have to use the ADHD skill".
    re.compile(
        r"\b(?:you|it|claude(?:-os)?)\s+(?:need(?:s)?|must|ha(?:ve|s))\s+to\s+"
        + _ACTION
        + r"\s+(?:the\s+)?"
        + _SKILL_CAPTURE
        + r"\s+skill\b",
        re.IGNORECASE,
    ),
    # Complaint: "why are you not using the ADHD skill?"
    re.compile(
        r"\bwhy\b[^.!?\n]{0,80}\b(?:not|never)\s+"
        + _ACTION
        + r"\s+(?:the\s+)?"
        + _SKILL_CAPTURE
        + r"\s+skill\b",
        re.IGNORECASE,
    ),
    # Complaint: "it doesn't use...", "you never invoke...".
    re.compile(
        r"\b(?:you|it|claude(?:-os)?)\s+"
        r"(?:do(?:es)?\s+not|do(?:es)?n['’]?t|did\s+not|didn['’]?t|"
        r"is\s+not|isn['’]?t|are\s+not|aren['’]?t|won['’]?t|never|"
        r"keep(?:s)?\s+not)\s+"
        + _ACTION
        + r"\s+(?:the\s+)?"
        + _SKILL_CAPTURE
        + r"\s+skill\b",
        re.IGNORECASE,
    ),
    # Repeated-reminder complaint: "I have to tell it to use X skill".
    re.compile(
        r"\bi\s+(?:have|need)\s+to\s+(?:keep\s+)?tell\b[^.!?\n]{0,80}\bto\s+"
        + _ACTION
        + r"\s+(?:the\s+)?"
        + _SKILL_CAPTURE
        + r"\s+skill\b",
        re.IGNORECASE,
    ),
)

_REVOCATION_PATTERNS = (
    re.compile(
        _SENTENCE_START
        + r"(?:please\s+)?(?:do\s+not|don['’]?t|never|stop)\s+"
        + _ACTION
        + r"\s+(?:the\s+)?"
        + _SKILL_CAPTURE
        + r"\s+skill\b",
        re.IGNORECASE,
    ),
    re.compile(
        _SENTENCE_START + r"(?:please\s+)?stop\s+"
        r"(?!(?:using|invoking|applying|following)\b)(?:the\s+)?"
        + _SKILL_CAPTURE
        + r"\s+skill\b",
        re.IGNORECASE,
    ),
)

_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_QUOTED_EXAMPLE_RE = re.compile(
    r'"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’|(?<!\w)' r"'[^'\n]+'(?!\w)"
)
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

_ADHD_ALIASES = frozenset({"adhd", "adhd-mode", "i-have-adhd", "i-have-adhd-mode"})
_ADHD_REVOCATIONS = ("normal mode", "stop adhd mode", "turn off adhd mode")


def normalize_skill_slug(raw: str) -> str | None:
    """Normalize a captured skill name to the prompt-safe slug alphabet."""
    text = raw.strip().lower().lstrip("/$")
    slug = _NON_SLUG_RE.sub("-", text).strip("-")
    if slug in _ADHD_ALIASES:
        slug = "i-have-adhd"
    if len(slug) > MAX_SKILL_SLUG_CHARS or not _SLUG_RE.fullmatch(slug):
        return None
    return slug


def _without_quoted_examples(text: str) -> str:
    text = _FENCED_CODE_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(" ", text)
    return _QUOTED_EXAMPLE_RE.sub(" ", text)


def extract_skill_directives(text: str) -> tuple[SkillDirective, ...]:
    """Return at most one (the latest) directive for each named skill."""
    if not isinstance(text, str) or not text.strip():
        return ()
    clean = _without_quoted_examples(text)
    candidates: list[tuple[int, SkillDirective]] = []

    lowered = clean.lower()
    for phrase in _ADHD_REVOCATIONS:
        start = lowered.rfind(phrase)
        if start >= 0:
            candidates.append(
                (
                    start,
                    SkillDirective(
                        skill="i-have-adhd",
                        kind=SkillDirectiveKind.REVOCATION,
                    ),
                )
            )

    for pattern in _REVOCATION_PATTERNS:
        for match in pattern.finditer(clean):
            skill = normalize_skill_slug(match.group("skill"))
            if skill:
                candidates.append(
                    (
                        match.start(),
                        SkillDirective(
                            skill=skill,
                            kind=SkillDirectiveKind.REVOCATION,
                        ),
                    )
                )

    for pattern in _POSITIVE_PATTERNS:
        for match in pattern.finditer(clean):
            skill = normalize_skill_slug(match.group("skill"))
            if skill:
                candidates.append(
                    (
                        match.start(),
                        SkillDirective(
                            skill=skill,
                            kind=SkillDirectiveKind.CORRECTION,
                        ),
                    )
                )

    # A human event counts once per skill. If the prompt contradicts itself,
    # its last explicit directive wins.
    latest: dict[str, tuple[int, SkillDirective]] = {}
    for candidate in candidates:
        previous = latest.get(candidate[1].skill)
        if previous is None or candidate[0] >= previous[0]:
            latest[candidate[1].skill] = candidate
    return tuple(item for _pos, item in sorted(latest.values(), key=lambda x: x[0]))


def stable_event_key(
    *,
    event_uuid: str | None,
    timestamp: str,
    session_id: str,
    text: str,
) -> str:
    """Return a one-way identity stable across copied transcript rows."""
    identity: object
    if isinstance(event_uuid, str) and event_uuid.strip():
        identity = ["uuid", event_uuid.strip()]
    else:
        identity = ["legacy", timestamp, session_id, text]
    material = json.dumps(
        identity,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def directive_events(
    text: str,
    *,
    event_uuid: str | None,
    timestamp: str,
    session_id: str,
    occurred_at: datetime | None,
    fallback_order: tuple[int, ...],
) -> tuple[SkillDirectiveEvent, ...]:
    """Attach non-rendered identity/order metadata to parsed directives."""
    event_key = stable_event_key(
        event_uuid=event_uuid,
        timestamp=timestamp,
        session_id=session_id,
        text=text,
    )
    return tuple(
        SkillDirectiveEvent(
            skill=directive.skill,
            kind=directive.kind,
            event_key=event_key,
            session_id=session_id,
            occurred_at=occurred_at,
            fallback_order=fallback_order,
        )
        for directive in extract_skill_directives(text)
    )


def _event_order(event: SkillDirectiveEvent) -> tuple:
    if event.occurred_at is not None:
        try:
            timestamp = event.occurred_at.timestamp()
        except (OSError, OverflowError, ValueError):
            timestamp = 0.0
        return (1, timestamp, event.fallback_order, event.event_key)
    return (0, 0.0, event.fallback_order, event.event_key)


def aggregate_skill_corrections(
    events: Iterable[SkillDirectiveEvent],
    *,
    min_corrections: int = DEFAULT_MIN_SKILL_CORRECTIONS,
) -> tuple[RecurringSkillCorrection, ...]:
    """Deduplicate events and retain recurring positives after revocation."""
    if min_corrections < 1:
        raise ValueError("min_corrections must be >= 1")

    unique: dict[tuple[str, str], SkillDirectiveEvent] = {}
    for event in events:
        if _SLUG_RE.fullmatch(event.skill):
            unique.setdefault((event.event_key, event.skill), event)

    by_skill: dict[str, list[SkillDirectiveEvent]] = {}
    for event in unique.values():
        by_skill.setdefault(event.skill, []).append(event)

    results: list[RecurringSkillCorrection] = []
    for skill, skill_events in by_skill.items():
        ordered = sorted(skill_events, key=_event_order)
        latest_revocation = -1
        for index, event in enumerate(ordered):
            if event.kind is SkillDirectiveKind.REVOCATION:
                latest_revocation = index
        positives = [
            event
            for event in ordered[latest_revocation + 1 :]
            if event.kind is SkillDirectiveKind.CORRECTION
        ]
        if len(positives) < min_corrections:
            continue
        sessions = {event.session_id or event.event_key for event in positives}
        results.append(
            RecurringSkillCorrection(
                skill=skill,
                corrections=len(positives),
                sessions=len(sessions),
            )
        )

    results.sort(key=lambda item: (-item.corrections, item.skill))
    return tuple(results)
