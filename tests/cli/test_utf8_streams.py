"""Windows-encoding guard: CLI streams are reconfigured to UTF-8 (issue 18).

A console code page like cp1252 used to crash any CLI output containing
characters outside the page (``∪``, ``→``) with ``UnicodeEncodeError``.
``ensure_utf8_streams`` reconfigures real streams to UTF-8 with
``errors="replace"`` and leaves everything else (UTF-8 hosts, StringIO,
pytest capture) untouched.
"""

from __future__ import annotations

import io
import sys

from dummyindex.io import ensure_utf8_streams


def _cp1252_stream() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


def test_reconfigures_cp1252_streams(monkeypatch) -> None:
    out, err = _cp1252_stream(), _cp1252_stream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    ensure_utf8_streams()

    assert out.encoding == "utf-8"
    assert err.encoding == "utf-8"
    assert out.errors == "replace"
    assert err.errors == "replace"


def test_output_no_longer_crashes_on_non_codepage_chars(monkeypatch) -> None:
    out = _cp1252_stream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", _cp1252_stream())

    ensure_utf8_streams()
    print("features ∪ new, marker → no-op", file=out)  # the exact crashers

    out.flush()
    text = out.buffer.getvalue().decode("utf-8")
    assert "∪" in text and "→" in text


def test_leaves_utf8_streams_alone(monkeypatch) -> None:
    out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))

    ensure_utf8_streams()

    assert out.encoding == "utf-8"
    assert out.errors == "strict"  # not reconfigured at all


def test_ignores_streams_without_reconfigure(monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())

    ensure_utf8_streams()  # must not raise


def test_main_reconfigures_before_printing(monkeypatch, capsys) -> None:
    from dummyindex.__main__ import main

    out = _cp1252_stream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", _cp1252_stream())
    monkeypatch.setattr(sys, "argv", ["dummyindex", "--version"])

    main()

    assert out.encoding == "utf-8"
    out.flush()
    assert out.buffer.getvalue().strip()  # the version printed without a crash
