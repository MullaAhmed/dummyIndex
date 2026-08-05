"""Safe skill-feedback cache projection and prompt rendering."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dummyindex.context.domains.memory.miner import (
    MAX_CACHE_BYTES,
    MAX_CACHE_ENTRIES,
    MAX_PROMPT_CHARS,
    MAX_PROMPT_SKILLS,
    RecurringSkillCorrection,
    SkillDirective,
    SkillDirectiveKind,
    read_skill_feedback,
    render_skill_feedback,
    skill_feedback_cache_path,
    write_skill_feedback,
)

pytestmark = pytest.mark.unit


def _item(
    skill: str = "i-have-adhd",
    corrections: int = 2,
    sessions: int = 2,
) -> RecurringSkillCorrection:
    return RecurringSkillCorrection(
        skill=skill,
        corrections=corrections,
        sessions=sessions,
    )


def _write_payload(context_dir: Path, payload: object) -> Path:
    path = skill_feedback_cache_path(context_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path


def _payload(skills: list[dict[str, object]]) -> dict[str, object]:
    return {"schema_version": 1, "skills": skills}


def test_cache_round_trip_is_sorted_bounded_and_contains_no_event_data(
    tmp_path: Path,
) -> None:
    context_dir = tmp_path / ".context"
    raw_secret = "repeat use adhd skill token=SECRET"
    feedback = [
        _item("zeta", 2, 1),
        _item("alpha", 4, 2),
        *[_item(f"skill-{index:02}", 3, 1) for index in range(70)],
    ]
    assert write_skill_feedback(context_dir, feedback) is True
    parsed = read_skill_feedback(context_dir)
    assert len(parsed) == MAX_CACHE_ENTRIES
    assert parsed == tuple(
        sorted(parsed, key=lambda item: (-item.corrections, item.skill))
    )
    text = skill_feedback_cache_path(context_dir).read_text(encoding="utf-8")
    assert raw_secret not in text
    for forbidden in ("prompt", "uuid", "timestamp", "profile", "cwd", "path"):
        assert forbidden not in text


def test_first_empty_write_stays_absent_but_existing_cache_is_cleared(
    tmp_path: Path,
) -> None:
    context_dir = tmp_path / ".context"
    path = skill_feedback_cache_path(context_dir)
    assert write_skill_feedback(context_dir, ()) is False
    assert not path.exists()
    assert write_skill_feedback(context_dir, (_item(),)) is True
    assert write_skill_feedback(context_dir, ()) is True
    assert read_skill_feedback(context_dir) == ()
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "skills": [],
    }


def test_byte_identical_cache_is_not_rewritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    context_dir = tmp_path / ".context"
    feedback = (_item(),)
    assert write_skill_feedback(context_dir, feedback) is True

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("unchanged cache must not be rewritten")

    monkeypatch.setattr(
        "dummyindex.context.domains.memory.miner.feedback.write_text_atomic",
        forbidden,
    )
    assert write_skill_feedback(context_dir, feedback) is False


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 1, "skills": [], "extra": True},
        {"schema_version": 2, "skills": []},
        {"schema_version": True, "skills": []},
        {"schema_version": 1, "skills": {}},
        _payload([{"skill": "UPPER", "corrections": 2, "sessions": 1}]),
        _payload([{"skill": "good", "corrections": True, "sessions": 1}]),
        _payload([{"skill": "good", "corrections": 0, "sessions": 1}]),
        _payload([{"skill": "good", "corrections": 2, "sessions": 3}]),
        _payload(
            [
                {"skill": "same", "corrections": 3, "sessions": 1},
                {"skill": "same", "corrections": 2, "sessions": 1},
            ]
        ),
        _payload(
            [
                {"skill": "low", "corrections": 2, "sessions": 1},
                {"skill": "high", "corrections": 3, "sessions": 1},
            ]
        ),
        _payload(
            [
                {
                    "skill": "good",
                    "corrections": 2,
                    "sessions": 1,
                    "excerpt": "secret",
                }
            ]
        ),
        _payload(
            [
                {"skill": f"s-{index:02}", "corrections": 2, "sessions": 1}
                for index in range(MAX_CACHE_ENTRIES + 1)
            ]
        ),
    ],
)
def test_cache_reader_rejects_invalid_schema_and_bounds(
    tmp_path: Path, payload: object
) -> None:
    context_dir = tmp_path / ".context"
    _write_payload(context_dir, payload)
    assert read_skill_feedback(context_dir) == ()


def test_cache_reader_rejects_malformed_oversized_and_symlink(
    tmp_path: Path,
) -> None:
    malformed_context = tmp_path / "malformed" / ".context"
    malformed = skill_feedback_cache_path(malformed_context)
    malformed.parent.mkdir(parents=True)
    malformed.write_text("{", encoding="utf-8")
    assert read_skill_feedback(malformed_context) == ()

    oversized_context = tmp_path / "oversized" / ".context"
    oversized = skill_feedback_cache_path(oversized_context)
    oversized.parent.mkdir(parents=True)
    oversized.write_bytes(b" " * (MAX_CACHE_BYTES + 1))
    assert read_skill_feedback(oversized_context) == ()

    link_context = tmp_path / "link" / ".context"
    target = tmp_path / "target.json"
    target.write_text(
        json.dumps(_payload([{"skill": "safe", "corrections": 2, "sessions": 1}])),
        encoding="utf-8",
    )
    link = skill_feedback_cache_path(link_context)
    link.parent.mkdir(parents=True)
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert read_skill_feedback(link_context) == ()


def test_prompt_projection_has_adhd_generic_current_and_revocation_rules() -> None:
    cached = (
        _item("i-have-adhd", 4, 3),
        _item("generic-review", 3, 2),
    )
    rendered = render_skill_feedback(cached)
    assert "Apply its ADHD-friendly response behavior directly" in rendered
    assert "invoke and follow it" in rendered
    assert "generic-review" in rendered

    revoked = render_skill_feedback(
        cached,
        current=(
            SkillDirective(
                skill="i-have-adhd",
                kind=SkillDirectiveKind.REVOCATION,
            ),
        ),
    )
    assert "i-have-adhd" not in revoked
    assert "generic-review" in revoked

    same_turn = render_skill_feedback(
        (),
        current=(
            SkillDirective(
                skill="one-off",
                kind=SkillDirectiveKind.CORRECTION,
            ),
        ),
    )
    assert "one-off" in same_turn


def test_prompt_projection_enforces_exact_count_and_character_caps() -> None:
    cached = tuple(_item(f"skill-{index:02}", 100 - index, 1) for index in range(20))
    rendered = render_skill_feedback(cached)
    assert rendered.count("\n- `") == MAX_PROMPT_SKILLS
    assert len(rendered) <= MAX_PROMPT_CHARS
    assert "skill-00" in rendered
    assert "skill-08" not in rendered


def test_current_positive_survives_eight_skill_cap_without_raw_prompt() -> None:
    secret = "raw-secret-user-language"
    cached = tuple(_item(f"cached-{index}", 100 - index, 1) for index in range(12))
    rendered = render_skill_feedback(
        cached,
        current=(
            SkillDirective(
                skill="current-request",
                kind=SkillDirectiveKind.CORRECTION,
            ),
        ),
    )
    assert "current-request" in rendered
    assert secret not in rendered
