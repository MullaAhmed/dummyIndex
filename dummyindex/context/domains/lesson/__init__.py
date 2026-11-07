"""Lesson record: required cue/lesson/evidence/confidence, mapped to a rule delta.

Public surface: ``Lesson``, ``Edit``, ``LessonCheck``, ``LessonDelta``,
``Confidence``, ``DeltaOp``, ``Verdict``, ``validate_lesson``, ``lesson_to_delta``.
"""

from __future__ import annotations

from .enums import Confidence, DeltaOp, Verdict
from .models import (
    Edit,
    Lesson,
    LessonCheck,
    LessonDelta,
    lesson_to_delta,
    validate_lesson,
)

__all__ = [
    "Confidence",
    "DeltaOp",
    "Edit",
    "Lesson",
    "LessonCheck",
    "LessonDelta",
    "Verdict",
    "lesson_to_delta",
    "validate_lesson",
]
