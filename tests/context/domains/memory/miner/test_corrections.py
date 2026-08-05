"""Deterministic skill-correction grammar and aggregation."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dummyindex.context.domains.memory.miner import (
    RecurringSkillCorrection,
    SkillDirective,
    SkillDirectiveEvent,
    SkillDirectiveKind,
    aggregate_skill_corrections,
    directive_events,
    extract_skill_directives,
    normalize_skill_slug,
    stable_event_key,
)

pytestmark = pytest.mark.unit


def _event(
    skill: str,
    kind: SkillDirectiveKind,
    event_key: str,
    order: int,
    session: str = "s1",
) -> SkillDirectiveEvent:
    return SkillDirectiveEvent(
        skill=skill,
        kind=kind,
        event_key=event_key,
        session_id=session,
        occurred_at=datetime(2026, 8, order, tzinfo=timezone.utc),
        fallback_order=(order,),
    )


@pytest.mark.parametrize(
    ("prompt", "skill"),
    [
        ("Use ADHD skill for output.", "i-have-adhd"),
        ("Please invoke the dummyindex plan skill.", "dummyindex-plan"),
        ("Why are you not using the adhd skill?", "i-have-adhd"),
        ("It doesnt use the ADHD skill at all.", "i-have-adhd"),
        ("You need to follow the backend verify skill.", "backend-verify"),
    ],
)
def test_extracts_direct_and_complaint_corrections(prompt: str, skill: str) -> None:
    assert extract_skill_directives(prompt) == (
        SkillDirective(skill=skill, kind=SkillDirectiveKind.CORRECTION),
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "How do I use the ADHD skill?",
        "Create a deployment skill.",
        'The fixture says "use ADHD skill for output".',
        "Document `use ADHD skill` in the README.",
        "```\nuse ADHD skill\n```",
        "We could use the ADHD skill someday.",
    ],
)
def test_rejects_questions_quotes_code_and_non_directives(prompt: str) -> None:
    assert extract_skill_directives(prompt) == ()


@pytest.mark.parametrize(
    "prompt",
    [
        "Do not use the ADHD skill.",
        "Don't invoke the ADHD skill.",
        "Never apply the ADHD skill.",
        "Stop using the ADHD skill.",
        "Normal mode.",
        "Stop ADHD mode.",
        "Turn off ADHD mode.",
    ],
)
def test_extracts_adhd_revocations(prompt: str) -> None:
    assert extract_skill_directives(prompt) == (
        SkillDirective(
            skill="i-have-adhd",
            kind=SkillDirectiveKind.REVOCATION,
        ),
    )


def test_last_directive_for_same_skill_wins() -> None:
    assert extract_skill_directives(
        "Stop using the ADHD skill. Actually, use the ADHD skill."
    ) == (
        SkillDirective(
            skill="i-have-adhd",
            kind=SkillDirectiveKind.CORRECTION,
        ),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ADHD", "i-have-adhd"),
        ("i have adhd", "i-have-adhd"),
        ("$dummyindex_plan", "dummyindex-plan"),
        ("/Backend-Verify", "backend-verify"),
        ("---", None),
        ("x" * 65, None),
    ],
)
def test_normalize_skill_slug(raw: str, expected: str | None) -> None:
    assert normalize_skill_slug(raw) == expected


def test_stable_event_key_hashes_uuid_and_fingerprints_legacy_rows() -> None:
    from_uuid = stable_event_key(
        event_uuid=" u-1 ",
        timestamp="2026-08-03T00:00:00Z",
        session_id="s1",
        text="use adhd skill",
    )
    assert len(from_uuid) == 64
    legacy = stable_event_key(
        event_uuid=None,
        timestamp="2026-08-03T00:00:00Z",
        session_id="s1",
        text="use adhd skill",
    )
    assert legacy == stable_event_key(
        event_uuid=None,
        timestamp="2026-08-03T00:00:00Z",
        session_id="s1",
        text="use adhd skill",
    )
    assert legacy != stable_event_key(
        event_uuid=None,
        timestamp="2026-08-04T00:00:00Z",
        session_id="s1",
        text="use adhd skill",
    )


def test_directive_events_reuse_one_private_event_key() -> None:
    events = directive_events(
        "Use ADHD skill. Use dummyindex plan skill.",
        event_uuid="uuid-not-persisted",
        timestamp="2026-08-03T00:00:00Z",
        session_id="s1",
        occurred_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        fallback_order=(1, 2),
    )
    assert [event.skill for event in events] == [
        "i-have-adhd",
        "dummyindex-plan",
    ]
    assert len({event.event_key for event in events}) == 1
    assert "uuid-not-persisted" not in events[0].event_key


def test_aggregate_deduplicates_forks_and_requires_two_events() -> None:
    events = [
        _event("i-have-adhd", SkillDirectiveKind.CORRECTION, "u1", 1),
        _event("i-have-adhd", SkillDirectiveKind.CORRECTION, "u1", 1, "fork"),
        _event("i-have-adhd", SkillDirectiveKind.CORRECTION, "u2", 2, "s2"),
        _event("one-off", SkillDirectiveKind.CORRECTION, "u3", 3),
    ]
    assert aggregate_skill_corrections(events) == (
        RecurringSkillCorrection(
            skill="i-have-adhd",
            corrections=2,
            sessions=2,
        ),
    )


def test_latest_revocation_resets_older_corrections() -> None:
    events = [
        _event("i-have-adhd", SkillDirectiveKind.CORRECTION, "u1", 1),
        _event("i-have-adhd", SkillDirectiveKind.CORRECTION, "u2", 2),
        _event("i-have-adhd", SkillDirectiveKind.REVOCATION, "u3", 3),
        _event("i-have-adhd", SkillDirectiveKind.CORRECTION, "u4", 4),
    ]
    assert aggregate_skill_corrections(events) == ()
    events.append(_event("i-have-adhd", SkillDirectiveKind.CORRECTION, "u5", 5, "s2"))
    assert aggregate_skill_corrections(events) == (
        RecurringSkillCorrection(
            skill="i-have-adhd",
            corrections=2,
            sessions=2,
        ),
    )


def test_bos_shaped_adhd_and_generic_skill_aggregate() -> None:
    events = [
        _event("i-have-adhd", SkillDirectiveKind.CORRECTION, "a1", 1, "os-1"),
        _event("i-have-adhd", SkillDirectiveKind.CORRECTION, "a2", 2, "os-2"),
        _event(
            "dummyindex-plan",
            SkillDirectiveKind.CORRECTION,
            "p1",
            3,
            "std-1",
        ),
        _event(
            "dummyindex-plan",
            SkillDirectiveKind.CORRECTION,
            "p2",
            4,
            "os-3",
        ),
    ]
    assert [item.skill for item in aggregate_skill_corrections(events)] == [
        "dummyindex-plan",
        "i-have-adhd",
    ]
