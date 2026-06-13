"""Tests for dummyindex.context.domains.atomic_io — shared write helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.atomic_io import (
    normalize_eof_newline,
    write_text_atomic,
)


@pytest.mark.unit
def test_write_text_atomic_is_byte_faithful(tmp_path: Path) -> None:
    """The atomic writer must never alter content — equip's hash baselines
    fingerprint the in-memory text, so on-disk bytes must match exactly."""
    target = tmp_path / "artifact.md"
    write_text_atomic(target, "no trailing newline")
    assert target.read_text(encoding="utf-8") == "no trailing newline"


@pytest.mark.unit
def test_normalize_appends_missing_eof_newline(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    target.write_text('{"a": 1}', encoding="utf-8")
    assert normalize_eof_newline(target) is True
    assert target.read_text(encoding="utf-8") == '{"a": 1}\n'


@pytest.mark.unit
def test_normalize_collapses_extra_trailing_newlines(tmp_path: Path) -> None:
    """end-of-file-fixer wants *exactly one* trailing newline — surplus blank
    lines at EOF fail the hook just like a missing newline does."""
    target = tmp_path / "doc.md"
    target.write_text("# Title\n\nbody\n\n\n", encoding="utf-8")
    assert normalize_eof_newline(target) is True
    assert target.read_text(encoding="utf-8") == "# Title\n\nbody\n"


@pytest.mark.unit
def test_normalize_is_noop_on_clean_file(tmp_path: Path) -> None:
    target = tmp_path / "clean.md"
    target.write_text("clean\n", encoding="utf-8")
    assert normalize_eof_newline(target) is False
    assert target.read_text(encoding="utf-8") == "clean\n"


@pytest.mark.unit
def test_normalize_leaves_empty_file_untouched(tmp_path: Path) -> None:
    target = tmp_path / "empty"
    target.write_bytes(b"")
    assert normalize_eof_newline(target) is False
    assert target.read_bytes() == b""


@pytest.mark.unit
def test_normalize_preserves_crlf_final_line(tmp_path: Path) -> None:
    target = tmp_path / "crlf.txt"
    target.write_bytes(b"line\r\n")
    assert normalize_eof_newline(target) is False
    assert target.read_bytes() == b"line\r\n"
