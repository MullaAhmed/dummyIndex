"""Tests for ``domains/docguard/citations.py``."""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.docguard.citations import (
    DISPOSABLE_REF,
    added_citations,
    cites_disposable,
    scan_durable,
)


@pytest.mark.unit
def test_cites_disposable_forms():
    assert cites_disposable("see .context/proposals/foo-bar/spec.md")
    assert cites_disposable("see audits/x_1/")
    assert cites_disposable(r"see .context\proposals\foo\spec.md")
    assert not cites_disposable("proposals/foo")
    assert not cites_disposable("nothing here")
    assert DISPOSABLE_REF.search("x audits/a-1/y")
    assert DISPOSABLE_REF.search("proposals/foo/") is not None


@pytest.mark.unit
def test_added_citations_only_new():
    old = "a proposals/one/ b"
    new = "a proposals/one/ b audits/two/ and proposals\\three\\"
    assert added_citations(old, new) == ["audits/two/", "proposals/three/"]
    assert added_citations(old, old) == []
    assert added_citations("proposals\\one\\", "proposals/one/") == []
    assert added_citations("", "") == []


@pytest.mark.unit
def test_scan_durable(tmp_path: Path):
    ctx = tmp_path / ".context"
    (ctx / "features" / "f" / "council").mkdir(parents=True)
    (ctx / "conventions").mkdir()
    (ctx / "architecture").mkdir()
    (ctx / "features" / "f" / "spec.md").write_text("x proposals/a/ y", "utf-8")
    (ctx / "features" / "f" / "council" / "c.md").write_text("proposals/b/", "utf-8")
    (ctx / "features" / "f" / "graph.json").write_text("proposals/c/", "utf-8")
    (ctx / "conventions" / "n.md").write_text("clean", "utf-8")
    (ctx / "architecture" / "overview.md").write_text("audits\\z\\", "utf-8")
    (ctx / "architecture" / "o.md").write_text("proposals/skip/", "utf-8")
    (ctx / "PROJECT.md").write_text("proposals/p/", "utf-8")
    (ctx / "proposals" / "q").mkdir(parents=True)
    (ctx / "proposals" / "q" / "spec.md").write_text("proposals/q/", "utf-8")
    assert sorted(scan_durable(tmp_path)) == [
        (".context/PROJECT.md", ["proposals/p/"]),
        (".context/architecture/overview.md", ["audits/z/"]),
        (".context/features/f/spec.md", ["proposals/a/"]),
    ]


@pytest.mark.unit
def test_scan_durable_skips_generated(tmp_path: Path):
    ctx = tmp_path / ".context"
    (ctx / "features" / "f").mkdir(parents=True)
    (ctx / "conventions").mkdir()
    cite = "see proposals/a/"
    (ctx / "features" / "f" / "docs.md").write_text(cite, "utf-8")
    (ctx / "INDEX.md").write_text(cite, "utf-8")
    (ctx / "HOW_TO_NAVIGATE.md").write_text(cite, "utf-8")
    (ctx / "conventions" / "naming.md").write_text(cite, "utf-8")
    assert scan_durable(tmp_path) == []
    (ctx / "features" / "f" / "spec.md").write_text(cite, "utf-8")
    assert scan_durable(tmp_path) == [(".context/features/f/spec.md", ["proposals/a/"])]


@pytest.mark.unit
def test_scan_durable_no_context(tmp_path: Path):
    assert scan_durable(tmp_path) == []
