"""Tests for ``context/domains/gc/anchor.py`` — the committed GC anchor and
the commit-throttled fire-once signal.

The storage split is the spine of these tests: the *anchor* lives in the
COMMITTED ``.context/gc/state.json`` (``GC_STATE_REL``), while the per-session
fire-once memo lives in the GITIGNORED ``.context/cache/gc-nudge-state.json``
(``GC_MEMO_REL``). They are distinct files and must never be conflated.

Real throwaway ``git init`` repos under ``tmp_path`` exercise the throttle;
off-git cases assert the graceful no-op contract (never a raise).
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from dummyindex.context.domains.gc.anchor import (
    anchor_orphaned,
    gc_commits_since,
    read_gc_anchor,
    should_signal,
    stamp_gc,
    write_gc_anchor,
)
from dummyindex.context.domains.gc.constants import GC_MEMO_REL, GC_STATE_REL


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _init_repo(path: Path) -> None:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t.t")
    _git(path, "config", "user.name", "t")


def _commit_all(path: Path, message: str) -> str:
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", message)
    return _git(path, "rev-parse", "HEAD").strip()


def _context_dir(root: Path) -> Path:
    ctx = root / ".context"
    ctx.mkdir(parents=True, exist_ok=True)
    return ctx


# ----- read / write round-trip ---------------------------------------------


@pytest.mark.unit
def test_write_then_read_round_trips_the_anchor(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    write_gc_anchor(ctx, "abc123")
    assert read_gc_anchor(ctx) == "abc123"


@pytest.mark.unit
def test_write_gc_anchor_writes_canonical_state_shape(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    write_gc_anchor(ctx, "deadbeef")
    payload = json.loads((ctx / GC_STATE_REL).read_text(encoding="utf-8"))
    assert payload == {"anchor": "deadbeef"}


@pytest.mark.unit
def test_read_gc_anchor_none_when_missing(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    assert read_gc_anchor(ctx) is None


@pytest.mark.unit
def test_read_gc_anchor_none_on_corrupt_file(tmp_path: Path) -> None:
    # Corrupt JSON must degrade to None — NEVER a garbage sha.
    ctx = _context_dir(tmp_path)
    state = ctx / GC_STATE_REL
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{ broken", encoding="utf-8")
    assert read_gc_anchor(ctx) is None


@pytest.mark.unit
def test_read_gc_anchor_none_on_non_dict(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    state = ctx / GC_STATE_REL
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("[1, 2, 3]", encoding="utf-8")
    assert read_gc_anchor(ctx) is None


@pytest.mark.unit
def test_read_gc_anchor_none_when_anchor_key_not_a_string(tmp_path: Path) -> None:
    ctx = _context_dir(tmp_path)
    state = ctx / GC_STATE_REL
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"anchor": 42}), encoding="utf-8")
    assert read_gc_anchor(ctx) is None


# ----- gc_commits_since -----------------------------------------------------


@pytest.mark.unit
def test_gc_commits_since_counts_from_recorded_anchor(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, anchor)

    (tmp_path / "a.py").write_text("x = 2\n", encoding="utf-8")
    _commit_all(tmp_path, "second")
    (tmp_path / "a.py").write_text("x = 3\n", encoding="utf-8")
    _commit_all(tmp_path, "third")

    assert gc_commits_since(ctx, tmp_path) == 2


@pytest.mark.unit
def test_gc_commits_since_none_when_no_anchor_recorded(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "init")
    # No anchor written → None (signal goes dark), never a count.
    assert gc_commits_since(ctx, tmp_path) is None


# ----- should_signal: threshold edge ----------------------------------------


@pytest.mark.unit
def test_should_signal_true_at_exact_threshold(tmp_path: Path) -> None:
    # Anchor N commits back, threshold == N → fires.
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 0\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, anchor)
    for i in range(3):
        (tmp_path / "a.py").write_text(f"x = {i + 1}\n", encoding="utf-8")
        _commit_all(tmp_path, f"c{i}")

    assert gc_commits_since(ctx, tmp_path) == 3
    assert should_signal(ctx, tmp_path, "S", threshold=3) is True


@pytest.mark.unit
def test_should_signal_false_just_under_threshold(tmp_path: Path) -> None:
    # threshold == N+1 with only N commits → does not fire.
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 0\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, anchor)
    for i in range(3):
        (tmp_path / "a.py").write_text(f"x = {i + 1}\n", encoding="utf-8")
        _commit_all(tmp_path, f"c{i}")

    assert should_signal(ctx, tmp_path, "S", threshold=4) is False


# ----- should_signal: fire-once memo ----------------------------------------


@pytest.mark.unit
def test_should_signal_fires_once_per_session(tmp_path: Path) -> None:
    # First over-threshold call for session "S" → True; the second → False.
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 0\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, anchor)
    for i in range(3):
        (tmp_path / "a.py").write_text(f"x = {i + 1}\n", encoding="utf-8")
        _commit_all(tmp_path, f"c{i}")

    assert should_signal(ctx, tmp_path, "S", threshold=3) is True
    assert should_signal(ctx, tmp_path, "S", threshold=3) is False


@pytest.mark.unit
def test_should_signal_empty_session_never_suppresses(tmp_path: Path) -> None:
    # An empty session id must NOT be recorded and must NOT silence on repeat —
    # it degrades to "emit when over threshold".
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 0\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, anchor)
    for i in range(3):
        (tmp_path / "a.py").write_text(f"x = {i + 1}\n", encoding="utf-8")
        _commit_all(tmp_path, f"c{i}")

    assert should_signal(ctx, tmp_path, "", threshold=3) is True
    assert should_signal(ctx, tmp_path, "", threshold=3) is True
    # An empty id is never persisted, so no memo file is created by it.
    assert not (ctx / GC_MEMO_REL).exists()


@pytest.mark.unit
def test_should_signal_under_threshold_does_not_mark_memo(tmp_path: Path) -> None:
    # A call that doesn't reach the threshold must not consume the fire-once
    # token: once over threshold the FIRST real over-threshold call fires.
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 0\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, anchor)
    for i in range(3):
        (tmp_path / "a.py").write_text(f"x = {i + 1}\n", encoding="utf-8")
        _commit_all(tmp_path, f"c{i}")

    assert should_signal(ctx, tmp_path, "S", threshold=10) is False  # under
    assert should_signal(ctx, tmp_path, "S", threshold=3) is True  # now over


# ----- storage split: committed anchor vs gitignored memo -------------------


@pytest.mark.unit
def test_storage_split_distinct_paths_for_anchor_and_memo(tmp_path: Path) -> None:
    # The anchor is written under gc/ (committed); the fire-once memo is written
    # under cache/ (gitignored). After a signal both files exist at DISTINCT
    # paths — the storage-split invariant.
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 0\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, anchor)
    for i in range(3):
        (tmp_path / "a.py").write_text(f"x = {i + 1}\n", encoding="utf-8")
        _commit_all(tmp_path, f"c{i}")

    assert should_signal(ctx, tmp_path, "S", threshold=3) is True

    anchor_path = ctx / GC_STATE_REL
    memo_path = ctx / GC_MEMO_REL
    assert anchor_path.exists()
    assert memo_path.exists()
    assert anchor_path != memo_path
    # Same-named files would defeat the split; assert the rel-paths differ.
    assert GC_STATE_REL != GC_MEMO_REL
    assert GC_STATE_REL.split("/")[0] == "gc"
    assert GC_MEMO_REL.split("/")[0] == "cache"


@pytest.mark.unit
def test_signal_now_is_injectable(tmp_path: Path) -> None:
    # An injected ``now`` is honoured (mirrors nudge.mark_nudged) — the memo is
    # written without touching the wall clock.
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 0\n", encoding="utf-8")
    anchor = _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, anchor)
    for i in range(3):
        (tmp_path / "a.py").write_text(f"x = {i + 1}\n", encoding="utf-8")
        _commit_all(tmp_path, f"c{i}")

    frozen = datetime(2020, 1, 1, 12, 0, 0)
    assert should_signal(ctx, tmp_path, "S", threshold=3, now=frozen) is True
    memo = json.loads((ctx / GC_MEMO_REL).read_text(encoding="utf-8"))
    assert "S" in memo


# ----- stamp_gc -------------------------------------------------------------


@pytest.mark.unit
def test_stamp_gc_off_git_is_noop_returning_none(tmp_path: Path) -> None:
    # No git, no `to` → no HEAD to anchor to → no-op, returns None, no crash.
    ctx = _context_dir(tmp_path)
    assert stamp_gc(ctx, tmp_path) is None
    assert read_gc_anchor(ctx) is None


@pytest.mark.unit
def test_stamp_gc_writes_head_and_zeroes_commits_since(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    head = _commit_all(tmp_path, "init")

    stamped = stamp_gc(ctx, tmp_path)
    assert stamped == head
    assert read_gc_anchor(ctx) == head
    # Anchor == HEAD → exactly 0 commits since (a genuine "nothing since").
    assert gc_commits_since(ctx, tmp_path) == 0


@pytest.mark.unit
def test_stamp_gc_honours_explicit_to(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    first = _commit_all(tmp_path, "init")
    (tmp_path / "a.py").write_text("x = 2\n", encoding="utf-8")
    _commit_all(tmp_path, "second")

    stamped = stamp_gc(ctx, tmp_path, to=first)
    assert stamped == first
    assert read_gc_anchor(ctx) == first
    # One commit landed after the explicitly-stamped first commit.
    assert gc_commits_since(ctx, tmp_path) == 1


# ----- anchor_orphaned ------------------------------------------------------


@pytest.mark.unit
def test_anchor_orphaned_true_for_unknown_recorded_sha(tmp_path: Path) -> None:
    # An anchor recorded, git present, but the sha is unknown to the repo (a
    # history rewrite orphaned it) → orphaned.
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, "0123456789abcdef0123456789abcdef01234567")
    assert anchor_orphaned(ctx, tmp_path) is True


@pytest.mark.unit
def test_anchor_orphaned_false_for_known_sha(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    head = _commit_all(tmp_path, "init")
    write_gc_anchor(ctx, head)
    assert anchor_orphaned(ctx, tmp_path) is False


@pytest.mark.unit
def test_anchor_orphaned_false_when_no_anchor_recorded(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    ctx = _context_dir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(tmp_path, "init")
    # No anchor recorded at all → not orphaned (nothing to orphan).
    assert anchor_orphaned(ctx, tmp_path) is False


@pytest.mark.unit
def test_anchor_orphaned_false_off_git(tmp_path: Path) -> None:
    # Git absent → cannot be "orphaned by a rewrite"; the off-git no-op contract
    # keeps this False rather than reading a recorded-but-uncountable sha as
    # orphaned.
    ctx = _context_dir(tmp_path)
    write_gc_anchor(ctx, "0123456789abcdef0123456789abcdef01234567")
    assert anchor_orphaned(ctx, tmp_path) is False
