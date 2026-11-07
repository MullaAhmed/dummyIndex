"""The lesson record: one validated cue/lesson/evidence/confidence per event."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ..evolve_gate import EvolveError
from ..living_rules import rules_in
from .enums import Confidence, DeltaOp, Verdict

REQUIRED_FIELDS = ("cue", "lesson", "evidence", "confidence")
LEGACY_FIELDS = frozenset(
    {"target", "rule_id", "body", "expected_sha256", "sources", "verified", "tests"}
)
LESSON_FIELDS = frozenset(REQUIRED_FIELDS) | {"edits"}


@dataclass(frozen=True)
class Edit:
    """One component change and its observed verdict."""

    component: str
    change: str
    verdict: Verdict

    def to_dict(self) -> dict[str, str]:
        return {
            "component": self.component,
            "change": self.change,
            "verdict": self.verdict.value,
        }


@dataclass(frozen=True)
class Lesson:
    """A required cue/lesson/evidence/confidence record with optional edit verdicts."""

    cue: str
    lesson: str
    evidence: str
    confidence: Confidence
    edits: tuple[Edit, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cue": self.cue,
            "lesson": self.lesson,
            "evidence": self.evidence,
            "confidence": self.confidence.value,
            "edits": [e.to_dict() for e in self.edits],
        }


@dataclass(frozen=True)
class LessonCheck:
    """``lesson`` is set for the new shape; ``legacy_shape`` marks an old reflection."""

    lesson: Lesson | None = None
    legacy_shape: bool = False


@dataclass(frozen=True)
class LessonDelta:
    """``living_rules.plan_rule`` keyword arguments plus the op they amount to."""

    op: DeltaOp
    plan_kwargs: Mapping[str, Any]


def _text(raw: dict, name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise EvolveError(f"lesson needs a non-empty {name}")
    return value.strip()


def _edit(row: object) -> Edit:
    if not isinstance(row, dict):
        raise EvolveError("lesson edits must be objects")
    try:
        verdict = Verdict(row.get("verdict"))
    except ValueError:
        allowed = "|".join(v.value for v in Verdict)
        raise EvolveError(f"lesson verdict must be one of {allowed}") from None
    return Edit(_text(row, "component"), _text(row, "change"), verdict)


def validate_lesson(raw: object) -> LessonCheck:
    """The only lesson shape check: one object, or a flagged pre-change reflection."""
    if not isinstance(raw, dict):
        raise EvolveError("a closeout carries exactly one lesson object, not a list")
    if not LESSON_FIELDS & raw.keys() and LEGACY_FIELDS & raw.keys():
        return LessonCheck(legacy_shape=True)
    cue, lesson, evidence = (_text(raw, name) for name in REQUIRED_FIELDS[:3])
    try:
        confidence = Confidence(raw.get("confidence"))
    except ValueError:
        allowed = "|".join(c.value for c in Confidence)
        raise EvolveError(f"lesson confidence must be one of {allowed}") from None
    edits = raw.get("edits", [])
    if not isinstance(edits, list):
        raise EvolveError("lesson edits must be a list")
    return LessonCheck(
        Lesson(cue, lesson, evidence, confidence, tuple(_edit(row) for row in edits))
    )


def lesson_to_delta(
    lesson: Lesson,
    rule_id: str,
    *,
    target: str,
    current_text: str,
    expected_sha256: str,
    sources: tuple[str, ...],
    evidence: tuple[str, ...],
    supersedes: tuple[str, ...] = (),
) -> LessonDelta:
    """Map a lesson to ``plan_rule`` arguments; pure, merging stays in living_rules.

    ``current_text`` is the target text the caller hashed into ``expected_sha256``.
    """
    exists = rule_id in {r["id"] for r in rules_in(current_text)}
    op = DeltaOp.SUPERSEDE if supersedes else DeltaOp.REVISE if exists else DeltaOp.ADD
    return LessonDelta(
        op,
        MappingProxyType(
            {
                "target": target,
                "rule_id": rule_id,
                "body": f"When {lesson.cue}: {lesson.lesson}",
                "expected_sha256": expected_sha256,
                "sources": sources,
                "evidence": evidence,
                "supersedes": supersedes,
            }
        ),
    )
