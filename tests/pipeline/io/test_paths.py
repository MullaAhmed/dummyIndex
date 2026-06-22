"""Tests for the path-confinement primitives in ``pipeline/io/paths.py``.

``resolve_under_root`` is pure (only ``.resolve()``); ``is_safe_read_target``
touches the filesystem (``lstat``/``stat``). Both are exercised here against
real on-disk shapes built under ``tmp_path`` — real symlinks and a real FIFO
via ``os.mkfifo`` — with no mocking, matching the ``test_git.py`` style.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from dummyindex.pipeline.io import is_safe_read_target, resolve_under_root


# ----- resolve_under_root ---------------------------------------------------


@pytest.mark.unit
def test_in_root_path_returns_resolved(tmp_path: Path) -> None:
    # Positive control: a descendant resolves to itself, under the root.
    target = tmp_path / "sub" / "file.txt"
    result = resolve_under_root(target, tmp_path)
    assert result == target.resolve()


@pytest.mark.unit
def test_root_itself_is_under_root(tmp_path: Path) -> None:
    result = resolve_under_root(tmp_path, tmp_path)
    assert result == tmp_path.resolve()


@pytest.mark.unit
def test_dotdot_escape_returns_none(tmp_path: Path) -> None:
    escape = tmp_path / ".." / "outside.txt"
    assert resolve_under_root(escape, tmp_path) is None


@pytest.mark.unit
def test_absolute_path_join_escape_returns_none(tmp_path: Path) -> None:
    # ``root / "/etc/x"`` collapses to ``/etc/x`` — an absolute join escapes.
    escape = tmp_path / "/etc/x"
    assert resolve_under_root(escape, tmp_path) is None


@pytest.mark.unit
def test_already_resolved_in_root_candidate_returns_resolved(tmp_path: Path) -> None:
    # Pass a path that is already fully resolved — .resolve() is idempotent.
    already = (tmp_path / "nested" / "doc.md").resolve()
    result = resolve_under_root(already, tmp_path)
    assert result == already


@pytest.mark.unit
def test_sibling_directory_is_not_under_root(tmp_path: Path) -> None:
    # A path sharing a prefix string but not actually nested must be rejected.
    root = tmp_path / "proj"
    root.mkdir()
    sibling = tmp_path / "proj-evil" / "x.txt"
    assert resolve_under_root(sibling, root) is None


# ----- is_safe_read_target --------------------------------------------------


@pytest.mark.unit
def test_normal_small_file_is_accepted(tmp_path: Path) -> None:
    f = tmp_path / "ok.txt"
    f.write_text("hello", encoding="utf-8")
    assert is_safe_read_target(f, max_bytes=1024) is True


@pytest.mark.unit
def test_symlink_target_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("data", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    # Even though the target is a benign small file, the link itself is refused.
    assert is_safe_read_target(link, max_bytes=1024) is False


@pytest.mark.unit
def test_oversize_file_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "big.bin"
    f.write_bytes(b"x" * 2048)
    assert is_safe_read_target(f, max_bytes=1024) is False


@pytest.mark.unit
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="os.mkfifo unavailable on this platform")
def test_fifo_non_regular_is_rejected(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    assert is_safe_read_target(fifo, max_bytes=1024) is False


@pytest.mark.unit
def test_directory_is_rejected(tmp_path: Path) -> None:
    d = tmp_path / "adir"
    d.mkdir()
    assert is_safe_read_target(d, max_bytes=1024) is False


@pytest.mark.unit
def test_missing_file_returns_false_without_raising(tmp_path: Path) -> None:
    assert is_safe_read_target(tmp_path / "nope.txt", max_bytes=1024) is False


@pytest.mark.unit
def test_file_exactly_at_limit_is_accepted(tmp_path: Path) -> None:
    f = tmp_path / "edge.bin"
    f.write_bytes(b"y" * 1024)
    assert is_safe_read_target(f, max_bytes=1024) is True
