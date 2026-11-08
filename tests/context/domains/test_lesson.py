from pathlib import Path

import pytest

from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.context.domains.lesson import (
    Confidence,
    DeltaOp,
    Verdict,
    lesson_to_delta,
    validate_lesson,
)
from dummyindex.context.domains.living_rules import plan_rule, sha256

pytestmark = pytest.mark.unit

TARGET = ".context/conventions/testing.md"
EVIDENCE = (".context/gc/closeouts/build.json",)


def _raw(**over: object) -> dict:
    return {
        "cue": "cache edited",
        "lesson": "invalidate on digest change",
        "evidence": "closeout build",
        "confidence": "high",
        **over,
    }


@pytest.fixture
def project(tmp_path: Path) -> Path:
    context = tmp_path / ".context"
    (context / "conventions").mkdir(parents=True)
    (tmp_path / TARGET).write_text("# Testing\n\nOwner text.\n", encoding="utf-8")
    (tmp_path / "cache.py").write_text("VALUE = 1\n", encoding="utf-8")
    evidence = tmp_path / EVIDENCE[0]
    evidence.parent.mkdir(parents=True)
    evidence.write_text('{"outcome":"verified"}\n', encoding="utf-8")
    return context


def _delta(context: Path, rule_id: str = "cache-contract", **over: object):
    lesson = validate_lesson(_raw()).lesson
    path = context.parent / TARGET
    return lesson_to_delta(
        lesson,
        rule_id,
        target=TARGET,
        current_text=path.read_text(encoding="utf-8"),
        expected_sha256=sha256(path.read_bytes()),
        sources=("cache.py",),
        evidence=EVIDENCE,
        **over,
    )


def _apply(context: Path, rule_id: str = "cache-contract") -> bytes:
    content = plan_rule(context, **_delta(context, rule_id).plan_kwargs)["content"]
    (context.parent / TARGET).write_bytes(content.encode())
    return content.encode()


def test_valid_lesson_round_trips() -> None:
    edits = [{"component": "skill", "change": "cut", "verdict": "confounded"}]
    check = validate_lesson(_raw(edits=edits))
    assert not check.legacy_shape
    assert check.lesson.confidence is Confidence.HIGH
    assert check.lesson.edits[0].verdict is Verdict.CONFOUNDED
    assert check.lesson.to_dict()["edits"] == edits


@pytest.mark.parametrize("name", ["cue", "lesson", "evidence", "confidence"])
@pytest.mark.parametrize("bad", ["missing", "", "  ", 3])
def test_missing_or_empty_field_rejected(name: str, bad: object) -> None:
    raw = _raw()
    if bad == "missing":
        del raw[name]
    else:
        raw[name] = bad
    with pytest.raises(EvolveError):
        validate_lesson(raw)


def test_list_of_lessons_rejected() -> None:
    with pytest.raises(EvolveError, match="not a list"):
        validate_lesson([_raw(), _raw()])


def test_bad_confidence_and_verdict_rejected() -> None:
    with pytest.raises(EvolveError, match="confidence"):
        validate_lesson(_raw(confidence="certain"))
    edit = {"component": "a", "change": "b", "verdict": "great"}
    with pytest.raises(EvolveError, match="verdict"):
        validate_lesson(_raw(edits=[edit]))
    with pytest.raises(EvolveError):
        validate_lesson(_raw(edits=["nope"]))


def test_legacy_reflection_flagged_not_rejected() -> None:
    legacy = {"target": TARGET, "rule_id": "x", "body": "b", "verified": True}
    check = validate_lesson(legacy)
    assert check.legacy_shape and check.lesson is None
    with pytest.raises(EvolveError):
        validate_lesson({})


def test_delta_is_pure_and_add_vs_revise(project: Path) -> None:
    path = project.parent / TARGET
    before = path.read_bytes()
    delta = _delta(project)
    assert path.read_bytes() == before
    assert delta == _delta(project)
    with pytest.raises(TypeError):
        delta.plan_kwargs["body"] = "x"  # type: ignore[index]
    assert delta.op is DeltaOp.ADD
    _apply(project)
    assert _delta(project).op is DeltaOp.REVISE
    assert _delta(project, "other").op is DeltaOp.ADD


def test_supersede_only_when_explicit(project: Path) -> None:
    _apply(project)
    assert _delta(project, "next").op is DeltaOp.ADD
    assert (
        _delta(project, "next", supersedes=("cache-contract",)).op is DeltaOp.SUPERSEDE
    )


def test_double_apply_is_byte_identical(project: Path) -> None:
    prefix = (project.parent / TARGET).read_bytes()
    first = _apply(project)
    assert _apply(project) == first
    assert first.startswith(prefix)
    assert first[len(prefix) :].lstrip().startswith(b"<!-- dummyindex:rule")


def test_owner_edit_between_plan_and_apply_refused(project: Path) -> None:
    delta = _delta(project)
    path = project.parent / TARGET
    path.write_text(path.read_text(encoding="utf-8") + "Edit.\n", encoding="utf-8")
    with pytest.raises(EvolveError, match="changed since review"):
        plan_rule(project, **delta.plan_kwargs)
