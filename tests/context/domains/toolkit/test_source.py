"""Source grammar: a github source may only name plain path segments and a plain ref."""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.toolkit import ToolkitError, toolkit_install
from dummyindex.context.domains.toolkit.source import parse_source
from tests.context.domains.toolkit.helpers import SKILL_TEXT, FakeGh

pytestmark = pytest.mark.unit

HOSTILE = [
    "github:o/r/d?ref=evil&x=/q",
    "github:o/r/d#frag",
    "github:o/r/d%2e%2e/x",
    "github:o/r/{a,b}",
    "github:o/r/a b",
    "github:o/r/a&b",
    "github:o/r/a\\b",
    "github:o/r/a:b",
    "github:o/r/d@main?x=1",
    "github:o/r/d@main..x",
    "github:o/r/../x",
    "github:o/r/./x",
    "github:o/r/x//y",
    "github:o/bad?x/r/d",
]


@pytest.mark.parametrize("source", HOSTILE)
def test_hostile_segments_and_refs_are_invalid_source(source: str) -> None:
    with pytest.raises(ToolkitError) as exc:
        parse_source(source)
    assert exc.value.code == "invalid_source"


def test_query_text_in_a_source_is_refused_before_any_network(
    root: Path, home: Path
) -> None:
    calls: list[list[str]] = []

    def recorder(argv: list[str]):
        calls.append(list(argv))
        return FakeGh()(argv)

    with pytest.raises(ToolkitError) as exc:
        toolkit_install(
            "skill",
            "github:owner/repo/skills/demo?ref=evil&x=/q",
            root=root,
            home=home,
            scope="project",
            preview=True,
            runner=recorder,
        )
    assert exc.value.code == "invalid_source"
    assert calls == []


def test_plain_segments_and_refs_still_parse() -> None:
    parsed = parse_source("github:owner/repo/skills/demo.v1_x-2@feature/a.b")
    assert parsed.repo == "owner/repo"
    assert parsed.subpath == "skills/demo.v1_x-2"
    assert parsed.git_ref == "feature/a.b"


def test_plain_source_previews_with_the_skill_text(root: Path, home: Path) -> None:
    gh = FakeGh(contents={"owner/repo": {"skills/demo/SKILL.md": SKILL_TEXT}})
    prev = toolkit_install(
        "skill",
        "github:owner/repo/skills/demo@main",
        root=root,
        home=home,
        scope="project",
        preview=True,
        runner=gh,
    )
    assert prev["name"] == "demo"
