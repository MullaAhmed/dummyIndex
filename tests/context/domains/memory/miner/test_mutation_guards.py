"""Tests that pin behaviours a mutation audit found unguarded.

Each test here corresponds to a mutant that survived the first test suite —
a change to the miner that broke a documented guarantee while every test
stayed green. The docstrings name the mutant, so a later reader can tell
these apart from ordinary coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.memory.miner import (
    canonical_signature,
    detect_repeated_signatures,
    iter_transcript_files,
    mine_and_feed,
    project_dir_name,
)
from dummyindex.context.domains.memory.miner.models import ToolCallRecord
from dummyindex.context.domains.memory.miner.render import FAILURE_PATTERNS_FILENAME
from dummyindex.context.domains.memory.store import memory_dir

pytestmark = pytest.mark.unit


def _records(signature: str, *, tool: str, count: int, size: int, error: bool):
    return [
        ToolCallRecord(
            tool_name=tool, signature=signature, is_error=error, output_bytes=size
        )
        for _ in range(count)
    ]


def test_results_sort_by_waste_even_when_alphabetical_order_disagrees() -> None:
    """Mutant: sort by signature only, dropping the waste key.

    The original fixture happened to order the same either way, so replacing
    the sort key changed nothing. Here alphabetical order is the *reverse* of
    waste order, so only the real key produces the documented output.
    """
    low_waste_early_name = _records("aaa", tool="Read", count=3, size=40, error=True)
    high_waste_late_name = _records("zzz", tool="Read", count=3, size=4000, error=True)
    results = detect_repeated_signatures(
        [low_waste_early_name, high_waste_late_name], min_occurrences=3
    )
    assert [r.signature for r in results] == ["zzz", "aaa"]


def test_shell_bare_integers_collapse_without_any_pagination_idiom() -> None:
    """Mutant: drop the bare-integer collapse from the shell branch.

    The original fixture used `head -50` / `head -100`, which the pagination
    regex already strips — so the integer-collapse half was never exercised.
    These commands carry no pagination idiom at all.
    """
    five = canonical_signature("Bash", {"command": "git log -5 --oneline"})
    ten = canonical_signature("Bash", {"command": "git log -10 --oneline"})
    assert five == ten


def test_iter_transcript_files_returns_sorted_order(
    monkeypatch, tmp_path: Path
) -> None:
    """Mutant: return the raw glob instead of a sorted tuple.

    The original test asserted membership only, but transcript order decides
    which record lands first in a group, so order is output-affecting.
    Asserting `found == sorted(found)` is not enough either — it passes
    whenever the filesystem happens to hand back sorted entries, which it
    usually does. So the glob is forced to yield reverse order: if the sort
    were dropped, that reversed order would come straight through.
    """
    project = tmp_path / "proj"
    project.mkdir(parents=True)
    names = ("a.jsonl", "b.jsonl", "c.jsonl")
    for name in names:
        (project / name).write_text("", encoding="utf-8")

    real_rglob = Path.rglob
    monkeypatch.setattr(
        Path, "rglob", lambda self, pat: reversed(sorted(real_rglob(self, pat)))
    )
    assert [p.name for p in iter_transcript_files(project)] == list(names)


def test_write_goes_through_write_text_atomic(monkeypatch, tmp_path: Path) -> None:
    """Mutant: swap `write_text_atomic` for a plain `Path.write_text`.

    The original test only asserted the file existed and no `.tmp` sibling
    remained — both true of a plain write. This asserts the atomic helper is
    the call actually made, which is what the checklist item claims.
    """
    calls: list[Path] = []
    real = __import__(
        "dummyindex.context.domains.memory.miner.render", fromlist=["write_text_atomic"]
    ).write_text_atomic

    def spy(path: Path, text: str) -> None:
        calls.append(path)
        real(path, text)

    monkeypatch.setattr(
        "dummyindex.context.domains.memory.miner.render.write_text_atomic", spy
    )
    context_dir = tmp_path / "repo" / ".context"
    mine_and_feed(context_dir, store_override=tmp_path / "cfg")

    assert calls == [memory_dir(context_dir) / FAILURE_PATTERNS_FILENAME]


# --- over-merge regressions (structured inputs stay verbatim) --------------


@pytest.mark.parametrize(
    ("tool", "left", "right", "why"),
    [
        (
            "Read",
            {"file_path": "/repo/Foo.py"},
            {"file_path": "/repo/foo.py"},
            "case-differing paths are different files on a case-sensitive fs",
        ),
        (
            "Grep",
            {"pattern": "TODO"},
            {"pattern": "todo"},
            "grep is case-sensitive by default",
        ),
        (
            "Edit",
            {"file_path": "/r/a.py", "old_string": "Foo", "new_string": "Bar"},
            {"file_path": "/r/a.py", "old_string": "foo", "new_string": "bar"},
            "a case-only edit is a real, distinct edit",
        ),
        (
            "Edit",
            {"file_path": "/r/a.py", "old_string": "a b"},
            {"file_path": "/r/a.py", "old_string": "a  b"},
            "a spacing-only edit is a real, distinct edit",
        ),
        (
            "mcp__search",
            {"query": "x", "n": 1},
            {"query": "x", "n": 5},
            "`n` on an unknown tool is semantic, not a fetch window",
        ),
        (
            "Task",
            {"prompt": "do x"},
            {"prompt": "do  x"},
            "prompt whitespace is content",
        ),
    ],
)
def test_structured_inputs_that_differ_do_not_merge(tool, left, right, why) -> None:
    assert canonical_signature(tool, left) != canonical_signature(tool, right), why


@pytest.mark.parametrize(
    ("tool", "left", "right"),
    [
        ("Read", {"file_path": "/r/a.py"}, {"file_path": "/r/a.py", "offset": 200}),
        (
            "Read",
            {"file_path": "/r/a.py", "limit": 50},
            {"file_path": "/r/a.py", "limit": 500},
        ),
        (
            "Grep",
            {"pattern": "x", "head_limit": 10},
            {"pattern": "x", "head_limit": 90},
        ),
    ],
)
def test_pagination_variants_still_merge(tool, left, right) -> None:
    """The point of the field-drop: widening a fetch is the same call."""
    assert canonical_signature(tool, left) == canonical_signature(tool, right)


def test_signature_is_json_serializable_without_str_coercion() -> None:
    """Mutant: restore `default=str`, which can embed a memory address."""
    sig = canonical_signature("Read", {"file_path": "/r/a.py", "nested": {"k": [1, 2]}})
    payload = sig.split("::", 1)[1]
    assert json.loads(payload) == {"file_path": "/r/a.py", "nested": {"k": [1, 2]}}


def test_unreadable_store_directory_is_not_an_error(tmp_path: Path) -> None:
    """Mutant: drop the OSError guard around `iterdir`."""
    from dummyindex.context.domains.memory.miner import discover_project_dirs

    store = tmp_path / "projects"
    (store / project_dir_name(tmp_path / "r")).mkdir(parents=True)
    store.chmod(0o000)
    try:
        assert discover_project_dirs(store) == ()
    finally:
        store.chmod(0o755)
