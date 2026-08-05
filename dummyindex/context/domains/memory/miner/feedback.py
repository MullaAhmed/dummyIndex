"""Strict local cache and bounded prompt projection for skill feedback."""

from __future__ import annotations

import json
import stat
from collections.abc import Iterable
from pathlib import Path

from ...atomic_io import write_text_atomic
from .enums import SkillDirectiveKind
from .models import RecurringSkillCorrection, SkillDirective

SKILL_FEEDBACK_SCHEMA_VERSION = 1
SKILL_FEEDBACK_FILENAME = "skill-feedback.json"
MAX_CACHE_BYTES = 32 * 1024
MAX_CACHE_ENTRIES = 64
MAX_PROMPT_SKILLS = 8
MAX_PROMPT_CHARS = 1600
MAX_FEEDBACK_COUNT = 2_147_483_647

_CACHE_KEYS = frozenset({"schema_version", "skills"})
_ENTRY_KEYS = frozenset({"skill", "corrections", "sessions"})

_HEADER = (
    "Skill-compliance feedback (local deterministic policy; these are "
    "instructions, not quoted transcript content):"
)
_ADHD_RULE = (
    "- `i-have-adhd`: Apply its ADHD-friendly response behavior directly on "
    "this turn; keep the response concise, structured, low-friction, and "
    "action-first unless the user opts out."
)
_GENERIC_RULE = (
    "- `{skill}`: If this skill is currently exposed and its trigger matches "
    "or the user names it, invoke and follow it on this turn."
)


def skill_feedback_cache_path(context_dir: Path) -> Path:
    """The gitignored per-machine feedback cache."""
    return context_dir / "cache" / SKILL_FEEDBACK_FILENAME


def _valid_slug(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return False
    if not value[0].isalnum() or not value[0].isascii():
        return False
    return all(
        char.isascii() and (char.islower() or char.isdigit() or char == "-")
        for char in value
    )


def _valid_count(value: object) -> bool:
    return type(value) is int and 1 <= value <= MAX_FEEDBACK_COUNT


def _normalize_feedback(
    feedback: Iterable[RecurringSkillCorrection],
) -> tuple[RecurringSkillCorrection, ...]:
    by_skill: dict[str, RecurringSkillCorrection] = {}
    for item in feedback:
        if (
            not _valid_slug(item.skill)
            or not _valid_count(item.corrections)
            or not _valid_count(item.sessions)
            or item.sessions > item.corrections
        ):
            continue
        previous = by_skill.get(item.skill)
        if previous is None or item.corrections > previous.corrections:
            by_skill[item.skill] = item
    return tuple(
        sorted(
            by_skill.values(),
            key=lambda item: (-item.corrections, item.skill),
        )[:MAX_CACHE_ENTRIES]
    )


def _serialize_feedback(
    feedback: Iterable[RecurringSkillCorrection],
) -> str:
    normalized = _normalize_feedback(feedback)
    payload = {
        "schema_version": SKILL_FEEDBACK_SCHEMA_VERSION,
        "skills": [
            {
                "skill": item.skill,
                "corrections": item.corrections,
                "sessions": item.sessions,
            }
            for item in normalized
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def write_skill_feedback(
    context_dir: Path,
    feedback: Iterable[RecurringSkillCorrection],
) -> bool:
    """Write a deterministic cache only when its bytes changed.

    A first-run empty result stays absent. Existing generated state is
    explicitly cleared when every correction is revoked or expires.
    """
    path = skill_feedback_cache_path(context_dir)
    normalized = _normalize_feedback(feedback)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError:
        return False

    if metadata is None and not normalized:
        return False
    if metadata is not None and (
        stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
    ):
        return False

    rendered = _serialize_feedback(normalized)
    try:
        if metadata is not None and path.read_text(encoding="utf-8") == rendered:
            return False
        write_text_atomic(path, rendered)
    except OSError:
        return False
    return True


def read_skill_feedback(
    context_dir: Path,
) -> tuple[RecurringSkillCorrection, ...]:
    """Read schema-1 feedback fail-closed, without following symlinks."""
    path = skill_feedback_cache_path(context_dir)
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > MAX_CACHE_BYTES
        ):
            return ()
        raw = path.read_bytes()
    except OSError:
        return ()
    if len(raw) > MAX_CACHE_BYTES:
        return ()

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return ()
    if type(payload) is not dict or set(payload) != _CACHE_KEYS:
        return ()
    if (
        type(payload["schema_version"]) is not int
        or payload["schema_version"] != SKILL_FEEDBACK_SCHEMA_VERSION
        or type(payload["skills"]) is not list
        or len(payload["skills"]) > MAX_CACHE_ENTRIES
    ):
        return ()

    parsed: list[RecurringSkillCorrection] = []
    seen: set[str] = set()
    for raw_item in payload["skills"]:
        if type(raw_item) is not dict or set(raw_item) != _ENTRY_KEYS:
            return ()
        skill = raw_item["skill"]
        corrections = raw_item["corrections"]
        sessions = raw_item["sessions"]
        if (
            not _valid_slug(skill)
            or not _valid_count(corrections)
            or not _valid_count(sessions)
            or sessions > corrections
            or skill in seen
        ):
            return ()
        seen.add(skill)
        parsed.append(
            RecurringSkillCorrection(
                skill=skill,
                corrections=corrections,
                sessions=sessions,
            )
        )

    expected = sorted(
        parsed,
        key=lambda item: (-item.corrections, item.skill),
    )
    if parsed != expected:
        return ()
    return tuple(parsed)


def render_skill_feedback(
    cached: Iterable[RecurringSkillCorrection],
    *,
    current: Iterable[SkillDirective] = (),
) -> str:
    """Render validated records and current directives into fixed policy text."""
    current_by_skill = {item.skill: item for item in current}
    revoked = {
        skill
        for skill, item in current_by_skill.items()
        if item.kind is SkillDirectiveKind.REVOCATION
    }
    current_positive = {
        skill
        for skill, item in current_by_skill.items()
        if item.kind is SkillDirectiveKind.CORRECTION and _valid_slug(skill)
    }

    normalized = {
        item.skill: item
        for item in _normalize_feedback(cached)
        if item.skill not in revoked
    }
    # Current positives rank above history so same-turn feedback survives the
    # eight-skill cap even before it meets the durable two-event threshold.
    ranked: list[tuple[int, str]] = [
        (MAX_FEEDBACK_COUNT + 1, skill) for skill in current_positive
    ]
    ranked.extend(
        (item.corrections, skill)
        for skill, item in normalized.items()
        if skill not in current_positive
    )
    ranked.sort(key=lambda item: (-item[0], item[1]))

    lines = [_HEADER]
    for _count, skill in ranked[:MAX_PROMPT_SKILLS]:
        line = (
            _ADHD_RULE if skill == "i-have-adhd" else _GENERIC_RULE.format(skill=skill)
        )
        candidate = "\n".join([*lines, line])
        if len(candidate) > MAX_PROMPT_CHARS:
            break
        lines.append(line)
    return "\n".join(lines) if len(lines) > 1 else ""
