"""Tests for `dummyindex context reality-check`.

Builds a tiny `.context/` skeleton by hand (not via build_all — that
spins the whole feature scaffolder), then exercises the verifier
against handcrafted claims.
"""
from __future__ import annotations
from dummyindex.pipeline.enums import ConfidenceLevel

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.reality_check import (
    _CALL_RE,
    _FILE_LINE_RE,
    _extract_claims,
    demote_feature_on_contradiction,
    reality_check_feature,
    render_report_md,
    write_report,
)


@pytest.fixture
def fake_context(tmp_path: Path) -> Path:
    """Build a minimal .context/ skeleton with a single feature."""
    root = tmp_path / "repo"
    root.mkdir()
    src = root / "app.py"
    # 5-line file — lets us test file:line claims.
    src.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n", encoding="utf-8")

    ctx = root / ".context"
    ctx.mkdir()
    (ctx / "meta.json").write_text(json.dumps({"root": str(root)}), encoding="utf-8")

    (ctx / "map").mkdir()
    (ctx / "map" / "symbols.json").write_text(json.dumps({
        "schema_version": 1,
        "symbols": [
            {"symbol_id": "s::App",     "name": "App",     "path": "app.py", "range": [1, 5]},
            {"symbol_id": "s::run",     "name": "run",     "path": "app.py", "range": [3, 4]},
            {"symbol_id": "s::helper",  "name": "helper",  "path": "app.py", "range": [2, 2]},
        ],
    }), encoding="utf-8")
    (ctx / "map" / "files.json").write_text(json.dumps({
        "schema_version": 1,
        "files": [{"path": "app.py", "language": "python", "size_bytes": 30, "loc": 5, "sha256": "..."}],
    }), encoding="utf-8")

    (ctx / "features").mkdir()
    (ctx / "features" / "symbol-graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "s::App",    "label": "App"},
            {"id": "s::run",    "label": ".run()"},
            {"id": "s::helper", "label": "helper()"},
        ],
        "links": [
            {"source": "s::run", "target": "s::helper", "relation": "calls"},
        ],
    }), encoding="utf-8")

    feat = ctx / "features" / "community-0"
    feat.mkdir()
    (feat / "feature.json").write_text(json.dumps({
        "feature_id": "community-0",
        "kind": "community",
        "name": "community-0",
        "summary": None,
        "members": ["s::App", "s::run", "s::helper"],
        "files": ["app.py"],
        "entry_points": ["s::run"],
        "flow_ids": [],
        "confidence": ConfidenceLevel.INFERRED,
    }), encoding="utf-8")
    (ctx / "features" / "INDEX.json").write_text(json.dumps({
        "schema_version": 1,
        "features": [{
            "feature_id": "community-0",
            "name": "community-0",
            "path": "features/community-0/",
            "confidence": ConfidenceLevel.INFERRED,
        }],
        "flow_count": 0,
    }), encoding="utf-8")

    return root


# ---------------------------------------------------------------------------
# Regex extraction
# ---------------------------------------------------------------------------


def test_call_re_extracts_subject_object() -> None:
    matches = list(_CALL_RE.finditer("`run` calls `helper`"))
    assert len(matches) == 1
    assert matches[0].group(1) == "run"
    assert matches[0].group(2) == "helper"


def test_call_re_strips_parens() -> None:
    matches = list(_CALL_RE.finditer("`run()` calls `helper()` in the entry point"))
    assert matches[0].group(1) == "run"
    assert matches[0].group(2) == "helper"


def test_file_line_re() -> None:
    m = _FILE_LINE_RE.search("see `app.py:3` for the body")
    assert m is not None
    assert m.group(1) == "app.py"
    assert m.group(2) == "3"


def test_extract_claims_finds_multiple_kinds() -> None:
    text = (
        "`run` calls `helper` and `App` uses `helper`.\n"
        "Note `app.py:2` and `app.py:99`.\n"
    )
    claims = _extract_claims(text, source_file="implementation.md")
    kinds = {c.kind for c in claims}
    assert "calls" in kinds
    assert "uses" in kinds
    assert "file:line" in kinds


def test_extract_claims_dedupes() -> None:
    text = "`run` calls `helper`. Yes, `run` calls `helper` again."
    claims = _extract_claims(text, source_file="x.md")
    assert len(claims) == 1


# ---------------------------------------------------------------------------
# End-to-end verification
# ---------------------------------------------------------------------------


def test_verified_call_passes(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "implementation.md").write_text(
        "# implementation\n\n`run` calls `helper`.\n", encoding="utf-8"
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.claims_total == 1
    assert report.verified == 1
    assert report.contradicted == 0


def test_contradicted_call_flagged(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "implementation.md").write_text(
        "`run` calls `nonexistent_function`.\n", encoding="utf-8"
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.contradicted == 1
    assert "not found" in (report.claims[0].reason or "")


def test_ambiguous_when_no_edge_but_symbols_exist(fake_context: Path) -> None:
    """Both symbols exist, but no calls edge — that's ambiguous, not contradicted."""
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "architecture.md").write_text(
        "`App` calls `helper`.\n", encoding="utf-8"
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.ambiguous == 1
    assert report.contradicted == 0


def test_file_line_verification(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "architecture.md").write_text(
        "See `app.py:3` for the run body.\n"
        "Also `app.py:99` for the closure.\n",
        encoding="utf-8",
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    statuses = {c.object: c.status for c in report.claims if c.kind == "file:line"}
    assert statuses["3"] == "verified"
    assert statuses["99"] == "contradicted"


def test_write_report_emits_both_artifacts(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "implementation.md").write_text(
        "`run` calls `helper`.\n", encoding="utf-8"
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    json_path, md_path = write_report(feat, report)
    assert json_path.exists()
    assert md_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["feature_id"] == "community-0"


def test_demote_on_contradiction_flips_confidence(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "architecture.md").write_text(
        "`run` calls `nonexistent_function`.\n", encoding="utf-8"
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.has_contradictions

    changed = demote_feature_on_contradiction(
        fake_context / ".context" / "features", report
    )
    assert changed is True

    feature_payload = json.loads((feat / "feature.json").read_text(encoding="utf-8"))
    assert feature_payload["confidence"] == ConfidenceLevel.AMBIGUOUS

    index_payload = json.loads(
        (fake_context / ".context" / "features" / "INDEX.json").read_text(encoding="utf-8")
    )
    assert index_payload["features"][0]["confidence"] == ConfidenceLevel.AMBIGUOUS


def test_demote_is_idempotent(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "architecture.md").write_text(
        "`run` calls `nope`.\n", encoding="utf-8"
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    # First call flips.
    demote_feature_on_contradiction(
        fake_context / ".context" / "features", report
    )
    # Second call is a no-op.
    changed = demote_feature_on_contradiction(
        fake_context / ".context" / "features", report
    )
    assert changed is False


def test_render_report_md_includes_contradictions(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "implementation.md").write_text(
        "`run` calls `nope`.\n", encoding="utf-8"
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    md = render_report_md(report)
    assert "Contradicted" in md


def test_missing_feature_raises(fake_context: Path) -> None:
    with pytest.raises(FileNotFoundError):
        reality_check_feature(fake_context / ".context", "nope-doesnt-exist")


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def test_cli_reality_check_subcommand(fake_context: Path, capsys) -> None:
    from dummyindex.cli import dispatch

    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "implementation.md").write_text(
        "`run` calls `helper`.\n", encoding="utf-8"
    )

    rc = dispatch([
        "reality-check",
        "--feature", "community-0",
        "--root", str(fake_context),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Reality check" in captured.out


def test_cli_reality_check_requires_feature(fake_context: Path, capsys) -> None:
    from dummyindex.cli import dispatch

    rc = dispatch(["reality-check", "--root", str(fake_context)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "feature" in captured.err.lower()
