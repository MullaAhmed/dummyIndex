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
    ConfidenceTransition,
    _extract_claims,
    demote_feature_on_contradiction,
    promote_feature_on_clean,
    reality_check_feature,
    render_report_md,
    write_report,
)


def _add_repo_file(root: Path, rel_path: str, line_count: int) -> None:
    """Write a file with ``line_count`` lines and register it in map/files.json."""
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(f"line {n}\n" for n in range(1, line_count + 1)), encoding="utf-8"
    )
    files_json = root / ".context" / "map" / "files.json"
    payload = json.loads(files_json.read_text(encoding="utf-8"))
    payload["files"].append({"path": rel_path, "language": "python"})
    files_json.write_text(json.dumps(payload), encoding="utf-8")


def _set_feature_files(root: Path, feature_id: str, files: list[str]) -> None:
    feature_json = root / ".context" / "features" / feature_id / "feature.json"
    payload = json.loads(feature_json.read_text(encoding="utf-8"))
    payload["files"] = files
    feature_json.write_text(json.dumps(payload), encoding="utf-8")


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


def test_reality_check_reads_plan_and_concerns(fake_context: Path) -> None:
    """v0.14: claims in `plan.md` + `concerns.md` are line-checked. `spec.md`
    is intent-level and deliberately NOT in the canonical reading set, so any
    claim it carries must be ignored — guarding against a regression that adds
    spec.md back to ``_CANONICAL_DOCS``."""
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text(
        "# plan\n\n`run` calls `helper`.\n", encoding="utf-8"
    )
    (feat / "concerns.md").write_text(
        "# concerns\n\n`run` calls `nonexistent_function`.\n", encoding="utf-8"
    )
    # A contradicted claim in spec.md must NOT be counted — if it were read,
    # claims_total would be 3 and contradicted would be 2.
    (feat / "spec.md").write_text(
        "# spec\n\n`run` calls `another_missing_fn`.\n", encoding="utf-8"
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.claims_total == 2
    assert report.verified == 1
    assert report.contradicted == 1


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
    # `_reality-check.json` is written sort_keys=True — a re-dump with sorted
    # keys must be byte-identical to what landed on disk.
    json_text = json_path.read_text(encoding="utf-8")
    assert json_text == json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


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
    assert isinstance(changed, ConfidenceTransition)
    assert changed.kind == "demoted"
    assert changed.to_value == ConfidenceLevel.AMBIGUOUS.value

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
    assert changed is None


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


# ---------------------------------------------------------------------------
# file:line resolution — basename disambiguation + on-disk fallback
# ---------------------------------------------------------------------------


def test_basename_citation_resolves_via_feature_files(fake_context: Path) -> None:
    """A bare `__init__.py:150` citation must resolve against the FEATURE's
    own files, not an arbitrary same-basename file — and deterministically."""
    _add_repo_file(fake_context, "pkg/a/__init__.py", 0)
    _add_repo_file(fake_context, "pkg/b/__init__.py", 200)
    _set_feature_files(fake_context, "community-0", ["pkg/b/__init__.py"])

    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("See `__init__.py:150`.\n", encoding="utf-8")

    for _ in range(3):  # identical across repeated calls
        report = reality_check_feature(fake_context / ".context", "community-0")
        assert report.verified == 1
        assert report.contradicted == 0


def test_basename_citation_ambiguous_when_not_feature_scoped(
    fake_context: Path,
) -> None:
    """Multiple same-basename candidates, none in the feature's files →
    ambiguous (never contradicted), with the candidates listed."""
    _add_repo_file(fake_context, "pkg/a/__init__.py", 5)
    _add_repo_file(fake_context, "pkg/b/__init__.py", 5)

    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("See `__init__.py:3`.\n", encoding="utf-8")

    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.contradicted == 0
    assert report.ambiguous == 1
    reason = report.claims[0].reason or ""
    assert "pkg/a/__init__.py" in reason
    assert "pkg/b/__init__.py" in reason


def test_citation_to_on_disk_file_not_in_index_verifies(fake_context: Path) -> None:
    """`package.json:20` exists on disk but not in map/files.json — the claim
    is about the file, so it verifies (was: contradicted 'file not found')."""
    pkg = fake_context / "package.json"
    pkg.write_text("".join(f'"k{n}": {n},\n' for n in range(36)), encoding="utf-8")

    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("Declared in `package.json:20`.\n", encoding="utf-8")

    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.verified == 1
    assert report.contradicted == 0


def test_citation_to_feature_own_doc_verifies(fake_context: Path) -> None:
    """A feature's concerns.md may cite its own spec.md by bare name."""
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "spec.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (feat / "concerns.md").write_text("See `spec.md:3`.\n", encoding="utf-8")

    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.verified == 1
    assert report.contradicted == 0


def test_citation_to_genuinely_missing_file_contradicted(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("See `ghost.py:5`.\n", encoding="utf-8")

    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.contradicted == 1
    assert "not found" in (report.claims[0].reason or "")


# ---------------------------------------------------------------------------
# calls/uses — stdlib & third-party references are unverifiable, not false
# ---------------------------------------------------------------------------


def test_uses_stdlib_dotted_token_is_ambiguous(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text(
        "`run` uses `os.environ.setdefault`.\n", encoding="utf-8"
    )
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.contradicted == 0
    assert report.ambiguous == 1
    assert "not verifiable" in (report.claims[0].reason or "")


def test_calls_third_party_dotted_token_is_ambiguous(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("`run` calls `requests.get`.\n", encoding="utf-8")
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.contradicted == 0
    assert report.ambiguous == 1


def test_calls_external_subject_is_ambiguous(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("`os.path.join` calls `helper`.\n", encoding="utf-8")
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.contradicted == 0
    assert report.ambiguous == 1


def test_calls_missing_undotted_symbol_still_contradicted(fake_context: Path) -> None:
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("`run` calls `NoSuchRepoFunc`.\n", encoding="utf-8")
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.contradicted == 1


def test_calls_repo_rooted_dotted_token_missing_leaf_contradicted(
    fake_context: Path,
) -> None:
    """`app.missing_fn` is rooted in the repo's own `app` module — a missing
    leaf there is a real grounding error, not an external reference."""
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("`run` calls `app.missing_fn`.\n", encoding="utf-8")
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.contradicted == 1


# ---------------------------------------------------------------------------
# Demote inverse — stash + promote on a clean re-run
# ---------------------------------------------------------------------------


def _report_for(fake_context: Path, text: str):
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text(text, encoding="utf-8")
    return reality_check_feature(fake_context / ".context", "community-0")


def test_demote_stashes_prior_confidence(fake_context: Path) -> None:
    report = _report_for(fake_context, "`run` calls `nonexistent_function`.\n")
    demote_feature_on_contradiction(fake_context / ".context" / "features", report)
    feat = fake_context / ".context" / "features" / "community-0"
    payload = json.loads((feat / "feature.json").read_text(encoding="utf-8"))
    assert payload["confidence"] == ConfidenceLevel.AMBIGUOUS
    assert payload["confidence_demoted_from"] == ConfidenceLevel.INFERRED


def test_promote_on_clean_restores_stashed_confidence(fake_context: Path) -> None:
    features_dir = fake_context / ".context" / "features"
    bad = _report_for(fake_context, "`run` calls `nonexistent_function`.\n")
    demote_feature_on_contradiction(features_dir, bad)

    clean = _report_for(fake_context, "`run` calls `helper`.\n")
    assert clean.contradicted == 0
    changed = promote_feature_on_clean(features_dir, clean)
    assert isinstance(changed, ConfidenceTransition)
    assert changed.kind == "restored"
    assert changed.from_value == ConfidenceLevel.AMBIGUOUS.value

    feat = features_dir / "community-0"
    payload = json.loads((feat / "feature.json").read_text(encoding="utf-8"))
    assert payload["confidence"] == ConfidenceLevel.INFERRED
    assert "confidence_demoted_from" not in payload
    index_payload = json.loads((features_dir / "INDEX.json").read_text(encoding="utf-8"))
    assert index_payload["features"][0]["confidence"] == ConfidenceLevel.INFERRED


def test_promote_is_noop_without_stash_or_demotion(fake_context: Path) -> None:
    features_dir = fake_context / ".context" / "features"
    clean = _report_for(fake_context, "`run` calls `helper`.\n")
    # Not demoted: confidence is INFERRED, no stash — promote must not touch it.
    assert promote_feature_on_clean(features_dir, clean) is None
    payload = json.loads(
        (features_dir / "community-0" / "feature.json").read_text(encoding="utf-8")
    )
    assert payload["confidence"] == ConfidenceLevel.INFERRED

    # AMBIGUOUS without a stash (legacy demotion) — also untouched.
    payload["confidence"] = ConfidenceLevel.AMBIGUOUS.value
    (features_dir / "community-0" / "feature.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    assert promote_feature_on_clean(features_dir, clean) is None


def test_demote_twice_then_clean_restores_original(fake_context: Path) -> None:
    features_dir = fake_context / ".context" / "features"
    bad = _report_for(fake_context, "`run` calls `nonexistent_function`.\n")
    demote_feature_on_contradiction(features_dir, bad)
    demote_feature_on_contradiction(features_dir, bad)  # idempotent re-demote

    clean = _report_for(fake_context, "`run` calls `helper`.\n")
    assert isinstance(promote_feature_on_clean(features_dir, clean), ConfidenceTransition)
    payload = json.loads(
        (features_dir / "community-0" / "feature.json").read_text(encoding="utf-8")
    )
    assert payload["confidence"] == ConfidenceLevel.INFERRED


def test_promote_refuses_dirty_report(fake_context: Path) -> None:
    features_dir = fake_context / ".context" / "features"
    bad = _report_for(fake_context, "`run` calls `nonexistent_function`.\n")
    demote_feature_on_contradiction(features_dir, bad)
    assert promote_feature_on_clean(features_dir, bad) is None


def test_cli_demote_then_clean_run_restores_confidence(
    fake_context: Path, capsys
) -> None:
    """The documented loop: fix the docs, re-run `reality-check --demote`,
    and the demotion self-heals."""
    from dummyindex.cli import dispatch

    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text(
        "`run` calls `nonexistent_function`.\n", encoding="utf-8"
    )
    rc = dispatch([
        "reality-check", "--feature", "community-0",
        "--root", str(fake_context), "--demote",
    ])
    assert rc == 1
    payload = json.loads((feat / "feature.json").read_text(encoding="utf-8"))
    assert payload["confidence"] == ConfidenceLevel.AMBIGUOUS

    (feat / "plan.md").write_text("`run` calls `helper`.\n", encoding="utf-8")
    rc = dispatch([
        "reality-check", "--feature", "community-0",
        "--root", str(fake_context), "--demote",
    ])
    capsys.readouterr()
    assert rc == 0
    payload = json.loads((feat / "feature.json").read_text(encoding="utf-8"))
    assert payload["confidence"] == ConfidenceLevel.INFERRED


def test_cli_demote_ignores_false_positive_shaped_claims(
    fake_context: Path, capsys
) -> None:
    """External references + unindexed-but-real file citations must not
    demote: the report carries no contradictions at all."""
    from dummyindex.cli import dispatch

    (fake_context / "package.json").write_text("{}\n" * 30, encoding="utf-8")
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text(
        "`run` uses `os.environ.setdefault`. Declared in `package.json:20`.\n",
        encoding="utf-8",
    )
    rc = dispatch([
        "reality-check", "--feature", "community-0",
        "--root", str(fake_context), "--demote",
    ])
    capsys.readouterr()
    assert rc == 0
    payload = json.loads((feat / "feature.json").read_text(encoding="utf-8"))
    assert payload["confidence"] == ConfidenceLevel.INFERRED


def test_cli_demote_reports_all_three_transitions(
    fake_context: Path, capsys
) -> None:
    """`reality-check --demote` prints the confidence delta the mutation
    applied — one line per transition: `demoted X→AMBIGUOUS`, then on a clean
    re-run `restored …→Y`, and `unchanged` when nothing moved."""
    from dummyindex.cli import dispatch

    feat = fake_context / ".context" / "features" / "community-0"
    args = [
        "reality-check", "--feature", "community-0",
        "--root", str(fake_context), "--demote",
    ]

    # 1) A contradiction demotes: INFERRED → AMBIGUOUS.
    (feat / "plan.md").write_text(
        "`run` calls `nonexistent_function`.\n", encoding="utf-8"
    )
    rc = dispatch(args)
    out = capsys.readouterr()
    assert rc == 1
    assert "demoted INFERRED→AMBIGUOUS" in (out.out + out.err)

    # 2) A clean re-run restores the stashed value: AMBIGUOUS → INFERRED.
    (feat / "plan.md").write_text("`run` calls `helper`.\n", encoding="utf-8")
    rc = dispatch(args)
    out = capsys.readouterr()
    assert rc == 0
    assert "restored AMBIGUOUS→INFERRED" in (out.out + out.err)

    # 3) A second clean re-run touches nothing — `unchanged`.
    rc = dispatch(args)
    out = capsys.readouterr()
    assert rc == 0
    assert "unchanged" in (out.out + out.err)


# ---------------------------------------------------------------------------
# Confidence mirror — atomicity, no-match signal, sorted keys
# ---------------------------------------------------------------------------


def test_demote_fault_injection_leaves_both_files_unchanged(
    fake_context: Path, monkeypatch
) -> None:
    """A raise BEFORE the first replace (monkeypatch ``Path.replace``) must
    leave BOTH feature.json and INDEX.json byte-identical — the staged tmps
    are never committed, so a demotion can't lose the stash mid-write."""
    features_dir = fake_context / ".context" / "features"
    feature_json = features_dir / "community-0" / "feature.json"
    index_json = features_dir / "INDEX.json"
    before_feature = feature_json.read_bytes()
    before_index = index_json.read_bytes()

    report = _report_for(fake_context, "`run` calls `nonexistent_function`.\n")
    assert report.has_contradictions

    # `_report_for` writes plan.md; re-snapshot feature.json bytes right
    # before the mirror so the comparison is exact.
    before_feature = feature_json.read_bytes()

    def _boom(self, target):  # noqa: ANN001
        raise OSError("injected fault before commit")

    monkeypatch.setattr(Path, "replace", _boom)

    with pytest.raises(OSError):
        demote_feature_on_contradiction(features_dir, report)

    assert feature_json.read_bytes() == before_feature
    assert index_json.read_bytes() == before_index


def test_promote_fault_injection_preserves_stash(
    fake_context: Path, monkeypatch
) -> None:
    """The stash-critical direction: a raise before the first replace during
    a promote must leave the on-disk feature.json (stash intact) and
    INDEX.json untouched, so the demotion stays restorable."""
    features_dir = fake_context / ".context" / "features"
    feature_json = features_dir / "community-0" / "feature.json"
    index_json = features_dir / "INDEX.json"

    bad = _report_for(fake_context, "`run` calls `nonexistent_function`.\n")
    demote_feature_on_contradiction(features_dir, bad)  # now AMBIGUOUS + stash

    clean = _report_for(fake_context, "`run` calls `helper`.\n")
    before_feature = feature_json.read_bytes()
    before_index = index_json.read_bytes()

    def _boom(self, target):  # noqa: ANN001
        raise OSError("injected fault before commit")

    monkeypatch.setattr(Path, "replace", _boom)
    with pytest.raises(OSError):
        promote_feature_on_clean(features_dir, clean)

    assert feature_json.read_bytes() == before_feature
    assert index_json.read_bytes() == before_index
    # The stash survived — the feature is still restorable.
    payload = json.loads(feature_json.read_text(encoding="utf-8"))
    assert payload["confidence"] == ConfidenceLevel.AMBIGUOUS
    assert payload["confidence_demoted_from"] == ConfidenceLevel.INFERRED


def test_mirror_surfaces_no_index_match_signal(fake_context: Path) -> None:
    """When no INDEX entry matches the feature_id, the mirror surfaces a
    discernible signal (matched=False) instead of a silent no-op."""
    from dummyindex.context.domains.reality_check.confidence import (
        _mirror_confidence_to_index,
    )

    features_dir = fake_context / ".context" / "features"
    # feature_id present in feature.json but absent from INDEX.json.
    staged = _mirror_confidence_to_index(
        features_dir, "no-such-feature", ConfidenceLevel.AMBIGUOUS.value
    )
    assert staged is not None  # INDEX.json exists, so it is staged
    _index_path, _index_tmp, matched = staged
    assert matched is False  # zero-match signal surfaced

    # A real match returns True.
    staged = _mirror_confidence_to_index(
        features_dir, "community-0", ConfidenceLevel.AMBIGUOUS.value
    )
    assert staged is not None
    _index_path, _index_tmp, matched = staged
    assert matched is True


def test_mirror_returns_none_when_index_absent(fake_context: Path) -> None:
    """A missing INDEX.json is a distinct signal (None) from a zero-match."""
    from dummyindex.context.domains.reality_check.confidence import (
        _mirror_confidence_to_index,
    )

    features_dir = fake_context / ".context" / "features"
    (features_dir / "INDEX.json").unlink()
    assert (
        _mirror_confidence_to_index(
            features_dir, "community-0", ConfidenceLevel.AMBIGUOUS.value
        )
        is None
    )


def test_demote_dumps_both_files_with_sorted_keys(fake_context: Path) -> None:
    """Every persisted dump (feature.json + INDEX.json) is sort_keys=True."""
    features_dir = fake_context / ".context" / "features"
    report = _report_for(fake_context, "`run` calls `nonexistent_function`.\n")
    demote_feature_on_contradiction(features_dir, report)

    feature_text = (features_dir / "community-0" / "feature.json").read_text(
        encoding="utf-8"
    )
    index_text = (features_dir / "INDEX.json").read_text(encoding="utf-8")

    # A re-dump with sort_keys=True must be byte-identical to what was written.
    feature_payload = json.loads(feature_text)
    index_payload = json.loads(index_text)
    assert feature_text == json.dumps(feature_payload, indent=2, sort_keys=True) + "\n"
    assert index_text == json.dumps(index_payload, indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# Trust boundary — path confinement, feature-id injection, meta-root anchoring
# ---------------------------------------------------------------------------
#
# In-repo-symlink policy (documented): confinement resolves the symlink (via
# ``resolve_under_root`` → ``Path.resolve()``) BEFORE the containment check.
#   * A symlink whose realpath ESCAPES ``repo_root`` is caught at confinement
#     and yields a "contradicted / outside the repository root" verdict — the
#     out-of-tree target is never opened. This is the security-critical case.
#   * A symlink whose realpath stays IN-root is a legitimate citation target:
#     it resolves to a real in-tree file and verifies normally (the cited file
#     genuinely lives in the repo). The ``is_safe_read_target`` read gate still
#     refuses non-regular files (FIFO / device) and oversize blobs.


def _spy_path_open(monkeypatch):
    """Patch ``pathlib.Path.open`` (the real read call site, verify.py) to
    record every path it is invoked on. Returns the list of opened paths."""
    import pathlib

    opened: list[Path] = []
    real_open = pathlib.Path.open

    def _recording_open(self, *a, **kw):
        opened.append(Path(self))
        return real_open(self, *a, **kw)

    monkeypatch.setattr(pathlib.Path, "open", _recording_open)
    return opened


@pytest.mark.parametrize(
    "citation",
    [
        # Relative ``../`` escape (extension-bearing, so the grammar accepts it).
        "`../../secrets.env:1`",
        # Absolute path outside the repo (extension-bearing).
        "`/tmp/dummyindex_oracle_probe.json:1`",
    ],
)
def test_out_of_root_citation_never_opens_target(
    fake_context: Path, monkeypatch, citation: str
) -> None:
    """An extension-bearing citation resolving OUTSIDE ``repo_root`` is
    contradicted/ambiguous and the target file is NEVER opened — proven by
    spying ``pathlib.Path.open`` and asserting it is never called for an
    out-of-root path. Gates EVERY ``_resolve_cited_path`` return branch."""
    # Materialise a real out-of-root target so a leak would actually succeed:
    # the test must fail loudly if the gate is removed, not silently.
    probe = Path("/tmp/dummyindex_oracle_probe.json")
    probe.write_text("x\n" * 50, encoding="utf-8")
    secrets = fake_context.parent / "secrets.env"
    secrets.write_text("API_KEY=hunter2\n", encoding="utf-8")
    try:
        opened = _spy_path_open(monkeypatch)
        feat = fake_context / ".context" / "features" / "community-0"
        (feat / "plan.md").write_text(f"See {citation}.\n", encoding="utf-8")

        report = reality_check_feature(fake_context / ".context", "community-0")

        assert report.verified == 0
        assert report.contradicted + report.ambiguous == 1
        # No opened path may land outside the repo root.
        root = fake_context.resolve()
        for p in opened:
            rp = p.resolve()
            assert rp == root or root in rp.parents, (
                f"verifier opened an out-of-root path: {rp}"
            )
        assert probe.resolve() not in [p.resolve() for p in opened]
        assert secrets.resolve() not in [p.resolve() for p in opened]
    finally:
        probe.unlink(missing_ok=True)


def test_extensionless_absolute_path_is_grammar_rejected_not_confinement(
    fake_context: Path,
) -> None:
    """CONTROL — ``/etc/passwd:1`` carries no ``.ext`` before ``:line``, so
    ``_FILE_LINE_RE`` rejects it BEFORE it reaches the verifier. This is a
    grammar rejection, NOT a confinement rejection: the claim simply never
    materialises as a file:line claim. Documented so the extension-bearing
    proof strings above are not mistaken for the only barrier."""
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("See `/etc/passwd:1`.\n", encoding="utf-8")
    report = reality_check_feature(fake_context / ".context", "community-0")
    # No file:line claim was extracted at all — grammar-rejected.
    assert not any(c.kind == "file:line" for c in report.claims)


def _add_repo_file_register_only(root: Path, rel_path: str) -> None:
    """Register ``rel_path`` in map/files.json WITHOUT writing the file (it
    already exists, e.g. as a symlink)."""
    files_json = root / ".context" / "map" / "files.json"
    payload = json.loads(files_json.read_text(encoding="utf-8"))
    payload["files"].append({"path": rel_path, "language": "python"})
    files_json.write_text(json.dumps(payload), encoding="utf-8")


def test_in_repo_symlink_escaping_root_is_confined(
    fake_context: Path, monkeypatch
) -> None:
    """An in-repo symlink whose realpath escapes ``repo_root`` is caught at
    confinement and never opened (documented in-repo-symlink policy)."""
    outside = fake_context.parent / "outside_target.py"
    outside.write_text("secret 1\nsecret 2\n", encoding="utf-8")
    link = fake_context / "leak.py"
    link.symlink_to(outside)
    _add_repo_file_register_only(fake_context, "leak.py")

    opened = _spy_path_open(monkeypatch)
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("See `leak.py:1`.\n", encoding="utf-8")

    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.verified == 0
    assert report.contradicted + report.ambiguous == 1
    assert outside.resolve() not in [p.resolve() for p in opened]


def test_in_repo_symlink_within_root_verifies(
    fake_context: Path,
) -> None:
    """An in-repo symlink whose target stays IN-root is a legitimate citation:
    confinement resolves it to a real in-tree file and it verifies. The
    security boundary only blocks links that ESCAPE the root (covered above)."""
    real = fake_context / "real_target.py"
    real.write_text("a\nb\nc\n", encoding="utf-8")
    link = fake_context / "alias.py"
    link.symlink_to(real)
    _add_repo_file_register_only(fake_context, "alias.py")

    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("See `alias.py:2`.\n", encoding="utf-8")
    report = reality_check_feature(fake_context / ".context", "community-0")
    fl = [c for c in report.claims if c.kind == "file:line"]
    assert len(fl) == 1
    assert fl[0].status == "verified"


def test_legit_in_root_citation_still_verifies(fake_context: Path) -> None:
    """POSITIVE CONTROL — confinement must not break a legitimate in-root
    citation: ``app.py:3`` still verifies after every branch is gated."""
    feat = fake_context / ".context" / "features" / "community-0"
    (feat / "plan.md").write_text("See `app.py:3`.\n", encoding="utf-8")
    report = reality_check_feature(fake_context / ".context", "community-0")
    assert report.verified == 1
    assert report.contradicted == 0


# ----- feature-id injection at the CLI boundary -----------------------------


@pytest.mark.parametrize(
    "bad_id",
    ["../../escape", "..", "a/b", "a\\b", "with\x00nul"],
)
def test_cli_rejects_feature_id_traversal(
    fake_context: Path, capsys, bad_id: str
) -> None:
    """``reality-check --feature ../../escape`` is rejected at the CLI boundary
    with a non-zero exit and NO write outside ``.context/features/``."""
    from dummyindex.cli import dispatch

    features_dir = fake_context / ".context" / "features"
    before = sorted(p.name for p in features_dir.iterdir())

    rc = dispatch([
        "reality-check", "--feature", bad_id, "--root", str(fake_context),
    ])
    captured = capsys.readouterr()
    assert rc != 0
    assert "feature" in captured.err.lower()
    # No new entry created anywhere under features/ ...
    after = sorted(p.name for p in features_dir.iterdir())
    assert before == after
    # ... and nothing written outside .context/features/ (the escape target).
    assert not (fake_context / "escape").exists()
    assert not (fake_context.parent / "escape").exists()


def test_verifier_rejects_feature_id_traversal(fake_context: Path) -> None:
    """Defence in depth: the verifier entry point also rejects a traversing
    feature id (independent of the CLI guard)."""
    with pytest.raises(ValueError):
        reality_check_feature(fake_context / ".context", "../../escape")


# ----- meta.json root anchoring to the resolved git toplevel ----------------


@pytest.fixture
def nested_git_context(tmp_path: Path) -> Path:
    """A repo with a REAL ``.git`` toplevel whose ``.context/`` lives in a
    SUBDIRECTORY — so ``context_dir.parent`` is NOT the repo root. This is the
    nested-``.context/`` case the flat ``fake_context`` cannot exercise.

    Returns the git toplevel (the trusted anchor).
    """
    toplevel = tmp_path / "monorepo"
    sub = toplevel / "packages" / "svc"
    sub.mkdir(parents=True)
    # A real git working tree at the toplevel (a .git directory is enough for
    # is_git_repo / resolve_git_dir).
    (toplevel / ".git").mkdir()
    (toplevel / "HEAD_FILE.py").write_text("a\nb\nc\n", encoding="utf-8")

    ctx = sub / ".context"
    ctx.mkdir()
    # meta root recorded honestly as the genuine toplevel.
    (ctx / "meta.json").write_text(
        json.dumps({"root": str(toplevel)}), encoding="utf-8"
    )
    (ctx / "map").mkdir()
    (ctx / "map" / "symbols.json").write_text(
        json.dumps({"schema_version": 1, "symbols": []}), encoding="utf-8"
    )
    (ctx / "map" / "files.json").write_text(
        json.dumps({"schema_version": 1, "files": [
            {"path": "HEAD_FILE.py", "language": "python"},
        ]}),
        encoding="utf-8",
    )
    (ctx / "features").mkdir()
    (ctx / "features" / "symbol-graph.json").write_text(
        json.dumps({"nodes": [], "links": []}), encoding="utf-8"
    )
    feat = ctx / "features" / "community-0"
    feat.mkdir()
    (feat / "feature.json").write_text(json.dumps({
        "feature_id": "community-0",
        "kind": "community",
        "name": "community-0",
        "summary": None,
        "members": [],
        "files": ["HEAD_FILE.py"],
        "entry_points": [],
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
    return toplevel


def test_meta_root_honored_when_it_is_the_git_toplevel(
    nested_git_context: Path,
) -> None:
    """POSITIVE CONTROL — a ``meta.json`` root that IS the genuine git toplevel
    is honored: a citation to a file living at the toplevel (one directory
    ABOVE ``context_dir.parent``) resolves and verifies."""
    ctx = nested_git_context / "packages" / "svc" / ".context"
    feat = ctx / "features" / "community-0"
    (feat / "plan.md").write_text("See `HEAD_FILE.py:2`.\n", encoding="utf-8")
    report = reality_check_feature(ctx, "community-0")
    assert report.verified == 1
    assert report.contradicted == 0


def test_meta_root_at_filesystem_root_falls_back_to_anchor(
    nested_git_context: Path,
) -> None:
    """A poisoned ``meta.json`` root of ``/`` (not the git toplevel) must be
    rejected: the verifier falls back to the trusted git-toplevel anchor, so a
    citation that would only resolve relative to ``/`` does not gain reach."""
    ctx = nested_git_context / "packages" / "svc" / ".context"
    (ctx / "meta.json").write_text(json.dumps({"root": "/"}), encoding="utf-8")
    feat = ctx / "features" / "community-0"
    # HEAD_FILE.py lives at the real toplevel; with the anchor it still
    # resolves (the toplevel IS the fallback). A file only reachable from "/"
    # (e.g. /etc/hostname) must NOT verify — proving root anchored to the
    # toplevel, not "/".
    (feat / "plan.md").write_text(
        "See `HEAD_FILE.py:2` and `etc/hostname:1`.\n", encoding="utf-8"
    )
    report = reality_check_feature(ctx, "community-0")
    statuses = {c.subject: c.status for c in report.claims if c.kind == "file:line"}
    assert statuses.get("HEAD_FILE.py") == "verified"
    assert statuses.get("etc/hostname") != "verified"


def test_meta_root_anchor_resolves_dotted_spelling(
    nested_git_context: Path,
) -> None:
    """Equality anchors to the RESOLVED toplevel, not raw string equality: a
    ``meta.json`` root spelled with a trailing ``/.`` still matches."""
    ctx = nested_git_context / "packages" / "svc" / ".context"
    (ctx / "meta.json").write_text(
        json.dumps({"root": str(nested_git_context) + "/."}), encoding="utf-8"
    )
    feat = ctx / "features" / "community-0"
    (feat / "plan.md").write_text("See `HEAD_FILE.py:2`.\n", encoding="utf-8")
    report = reality_check_feature(ctx, "community-0")
    assert report.verified == 1
