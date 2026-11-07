from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.docbudget import (
    BudgetGroup,
    check,
    format_ratchet,
    read_ratchet,
    update_ratchet,
)
from dummyindex.context.domains.docbudget.constants import CONTEXT_CEILING
from dummyindex.context.domains.docbudget.ratchet import is_skill_file, scan

pytestmark = pytest.mark.unit

DOC = ".context/PROJECT.md"
OVERVIEW = ".context/architecture/overview.md"


def _write(root: Path, rel: str, words: int) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(" ".join(["w"] * words) + "\n", encoding="utf-8")


def test_grown_doc_flagged(tmp_path: Path) -> None:
    _write(tmp_path, DOC, 12)
    (v,) = check(tmp_path, {DOC: 10})
    assert (v.path, v.words, v.recorded) == (DOC, 12, 10)


def test_unchanged_and_shrunk_pass(tmp_path: Path) -> None:
    _write(tmp_path, DOC, 10)
    assert check(tmp_path, {DOC: 10}) == ()
    assert check(tmp_path, {DOC: 20}) == ()


def test_unrecorded_over_ceiling_flagged(tmp_path: Path) -> None:
    _write(tmp_path, DOC, CONTEXT_CEILING + 1)
    (v,) = check(tmp_path, {})
    assert v.recorded is None


def test_skills_scope(tmp_path: Path) -> None:
    skill = "dummyindex/skills/a/SKILL.md"
    _write(tmp_path, skill, 5)
    assert check(tmp_path, {}, BudgetGroup.CONTEXT) == ()
    (v,) = check(tmp_path, {skill: 3}, BudgetGroup.SKILLS)
    assert v.words == 5


def test_update_lowers_but_refuses_raise(tmp_path: Path) -> None:
    _write(tmp_path, DOC, 5)
    _write(tmp_path, OVERVIEW, 30)
    res = update_ratchet(tmp_path, {DOC: 10, OVERVIEW: 20})
    assert res.ratchet[DOC] == 5
    assert res.ratchet[OVERVIEW] == 20
    assert res.lowered == (DOC,)
    assert [v.path for v in res.refused] == [OVERVIEW]


def test_deterministic_sort_and_lf(tmp_path: Path) -> None:
    for name in ("b", "a", "c"):
        _write(tmp_path, f".context/conventions/{name}.md", 2)
    res = update_ratchet(tmp_path, {})
    text = format_ratchet(res.ratchet)
    assert "\r" not in text
    paths = [ln.split("\t")[0] for ln in text.splitlines()]
    assert paths == sorted(paths) and len(paths) == 3
    out = tmp_path / "r.txt"
    out.write_bytes(text.encode())
    assert read_ratchet(out) == res.ratchet
    assert format_ratchet(read_ratchet(out)) == text


def test_oversized_unrecorded_seeded_then_passes(tmp_path: Path) -> None:
    _write(tmp_path, DOC, CONTEXT_CEILING + 50)
    res = update_ratchet(tmp_path, {})
    assert res.ratchet == {DOC: CONTEXT_CEILING + 50}
    assert res.refused == ()
    assert check(tmp_path, res.ratchet) == ()


def test_malformed_ratchet_line_raises(tmp_path: Path) -> None:
    bad = ("no-tab-here", DOC + chr(9) + "abc", chr(9) + "5")
    for body in bad:
        f = tmp_path / "r.txt"
        f.write_text(body + chr(10), encoding="utf-8")
        with pytest.raises(ValueError, match="r.txt:1"):
            read_ratchet(f)


def test_is_skill_file_exact_case() -> None:
    assert is_skill_file(Path("x/SKILL.md"))
    assert not is_skill_file(Path("x/skill.md"))
    assert not is_skill_file(Path("x/Skill.md"))


def test_scan_skills_ignores_lowercase_skill_md(tmp_path: Path) -> None:
    _write(tmp_path, "dummyindex/skills/a/SKILL.md", 4)
    _write(tmp_path, "dummyindex/skills/skill.md", 9)
    assert scan(tmp_path, BudgetGroup.SKILLS) == {"dummyindex/skills/a/SKILL.md": 4}
