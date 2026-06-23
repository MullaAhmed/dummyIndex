"""Tests for the debt-marker vocabulary in ``pipeline/extract/python_rationale.py``.

Covers the shared ``DEBT_PREFIXES`` constant (reused by the later debt
harvester) and the addition of ``# DEBT:`` to the rationale-comment set. The
existing rationale prefixes must remain present, and a ``# DEBT:`` comment line
must now produce a rationale node. No subprocess — ``extract_python`` is the
real tree-sitter post-pass, driven over a hand-written ``.py`` file under
``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.pipeline.extract.languages.wrappers import extract_python
from dummyindex.pipeline.extract.python_rationale import (
    _RATIONALE_PREFIXES,
    DEBT_PREFIXES,
)

# Every prefix the module recognised before this change.
_PRE_EXISTING_RATIONALE_PREFIXES = (
    "# NOTE:",
    "# IMPORTANT:",
    "# HACK:",
    "# WHY:",
    "# RATIONALE:",
    "# TODO:",
    "# FIXME:",
)


@pytest.mark.unit
def test_debt_prefixes_is_importable_and_complete() -> None:
    assert DEBT_PREFIXES == ("# TODO:", "# FIXME:", "# HACK:", "# DEBT:")


@pytest.mark.unit
def test_rationale_prefixes_keeps_every_pre_existing_prefix() -> None:
    for prefix in _PRE_EXISTING_RATIONALE_PREFIXES:
        assert prefix in _RATIONALE_PREFIXES


@pytest.mark.unit
def test_rationale_prefixes_now_includes_debt() -> None:
    assert "# DEBT:" in _RATIONALE_PREFIXES


@pytest.mark.unit
def test_rationale_prefixes_has_no_duplicates() -> None:
    assert len(_RATIONALE_PREFIXES) == len(set(_RATIONALE_PREFIXES))


@pytest.mark.unit
def test_debt_comment_line_produces_a_rationale_node(tmp_path: Path) -> None:
    src = tmp_path / "sample.py"
    src.write_text(
        "def f():\n    # DEBT: x; upgrade: y\n    return 1\n",
        encoding="utf-8",
    )

    result = extract_python(src)

    rationale = [
        node
        for node in result["nodes"]
        if node.get("file_type") == "rationale"
        and "# DEBT: x; upgrade: y" in node.get("label", "")
    ]
    assert len(rationale) == 1
