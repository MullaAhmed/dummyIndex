"""Tests for the atomic placement ops (`scaffold_feature` / `assign_files`)
and their `dummyindex context scaffold-feature / assign-files` CLI front-ends.

These are the Phase-2 ops the council uses to fold net-new files into the
curated taxonomy WITHOUT re-clustering. They mirror the existing atomic-op
pattern in `context/domains/features/ops.py` (validate-everything-before-
write, tmp-rename atomicity, hand-maintained INDEX.json + regenerated
INDEX.md/graph).

Unlike the `_GRAPH`-based scaffold tests, these ops read real files on
disk and a real `map/symbols.json`, so each fixture writes both.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context.domains.features import (
    PENDING_ENRICHMENT_MARKER,
    FeatureRenameError,
    assign_files,
    clear_pending_enrichment,
    scaffold_feature,
)
from dummyindex.pipeline.enums import ConfidenceLevel


_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


# ----- fixtures -------------------------------------------------------------


def _repo_with_symbols(tmp_path: Path) -> tuple[Path, Path]:
    """Build a tiny repo_root with real files + a `.context/` carrying a
    hand-written `map/symbols.json` and a seeded `features/` dir.

    Returns ``(repo_root, features_dir)``.
    """
    repo_root = tmp_path / "repo"
    (repo_root / "app").mkdir(parents=True)
    (repo_root / "app" / "auth.py").write_text("def login():\n    pass\n", encoding="utf-8")
    (repo_root / "app" / "session.py").write_text("def open_session():\n    pass\n", encoding="utf-8")
    (repo_root / "app" / "other.py").write_text("def helper():\n    pass\n", encoding="utf-8")

    context_dir = repo_root / ".context"
    map_dir = context_dir / "map"
    map_dir.mkdir(parents=True)
    symbols = {
        "schema_version": 1,
        "symbols": [
            {"symbol_id": "sym_login", "kind": "function", "name": "login",
             "path": "app/auth.py", "range": [1, 2], "parent": None, "exported": True},
            {"symbol_id": "sym_open", "kind": "function", "name": "open_session",
             "path": "app/session.py", "range": [1, 2], "parent": None, "exported": True},
            {"symbol_id": "sym_helper", "kind": "function", "name": "helper",
             "path": "app/other.py", "range": [1, 2], "parent": None, "exported": True},
        ],
    }
    (map_dir / "symbols.json").write_text(json.dumps(symbols, indent=2), encoding="utf-8")

    features_dir = context_dir / "features"
    features_dir.mkdir(parents=True)
    # Seed an empty INDEX.json so the ops have something to extend; the ops
    # also tolerate its absence, but a real index is the common case.
    (features_dir / "INDEX.json").write_text(
        json.dumps({"schema_version": 1, "features": [], "flow_count": 0}, indent=2),
        encoding="utf-8",
    )
    return repo_root, features_dir


# ----- scaffold_feature -----------------------------------------------------


@pytest.mark.unit
def test_scaffold_feature_creates_coherent_folder(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    result = scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        name="Authentication",
        summary="Login + session.",
        files=[repo_root / "app" / "auth.py", repo_root / "app" / "session.py"],
    )

    feat_dir = features_dir / "authentication"
    assert (feat_dir / "feature.json").is_file()
    assert (feat_dir / "spec.md").is_file()
    payload = json.loads((feat_dir / "feature.json").read_text(encoding="utf-8"))
    assert payload["feature_id"] == "authentication"
    assert payload["kind"] == "community"
    assert payload["name"] == "Authentication"
    assert payload["summary"] == "Login + session."
    # Files normalized to repo-relative POSIX, sorted.
    assert payload["files"] == ["app/auth.py", "app/session.py"]
    # Members derived from symbols whose path is one of the files.
    assert set(payload["members"]) == {"sym_login", "sym_open"}
    assert "sym_helper" not in payload["members"]
    assert payload["entry_points"] == []
    assert payload["flow_ids"] == []
    assert payload["confidence"] == ConfidenceLevel.EXTRACTED
    assert result.feature_id == "authentication"


@pytest.mark.unit
def test_scaffold_feature_spec_md_is_extracted_stub(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        name="Authentication",
        files=[repo_root / "app" / "auth.py"],
    )
    spec = (features_dir / "authentication" / "spec.md").read_text(encoding="utf-8")
    # Same deterministic stub writer scaffold_features uses.
    assert "# Feature: Authentication" in spec
    assert "Deterministic stub" in spec
    assert ConfidenceLevel.EXTRACTED in spec


@pytest.mark.unit
def test_scaffold_feature_appears_in_index_with_counts(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        name="Authentication",
        files=[repo_root / "app" / "auth.py", repo_root / "app" / "session.py"],
    )
    idx = json.loads((features_dir / "INDEX.json").read_text(encoding="utf-8"))
    by_id = {e["feature_id"]: e for e in idx["features"]}
    assert "authentication" in by_id
    entry = by_id["authentication"]
    assert entry["member_count"] == 2
    assert entry["file_count"] == 2
    assert entry["entry_point_count"] == 0
    assert entry["flow_count"] == 0
    assert entry["path"] == "features/authentication/"
    # INDEX.md + graph.json regenerated.
    index_md = (features_dir / "INDEX.md").read_text(encoding="utf-8")
    assert "authentication" in index_md
    gv = json.loads((features_dir / "graph.json").read_text(encoding="utf-8"))
    assert "authentication" in {n["id"] for n in gv["nodes"] if n["kind"] == "feature"}


@pytest.mark.unit
def test_scaffold_feature_seeds_index_when_absent(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    (features_dir / "INDEX.json").unlink()
    scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        name="Authentication",
        files=[repo_root / "app" / "auth.py"],
    )
    idx = json.loads((features_dir / "INDEX.json").read_text(encoding="utf-8"))
    assert [e["feature_id"] for e in idx["features"]] == ["authentication"]


@pytest.mark.unit
def test_scaffold_feature_rejects_duplicate_id(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    (features_dir / "authentication").mkdir()
    with pytest.raises(FeatureRenameError, match="already exists"):
        scaffold_feature(
            features_dir,
            repo_root=repo_root,
            feature_id="authentication",
            name="Authentication",
            files=[repo_root / "app" / "auth.py"],
        )


@pytest.mark.unit
def test_scaffold_feature_rejects_community_id(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    with pytest.raises(FeatureRenameError, match="community"):
        scaffold_feature(
            features_dir,
            repo_root=repo_root,
            feature_id="community-7",
            name="Reserved",
            files=[repo_root / "app" / "auth.py"],
        )
    # Reserved id rejected before any folder is created.
    assert not (features_dir / "community-7").exists()


@pytest.mark.unit
def test_scaffold_feature_rejects_no_files(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    with pytest.raises(FeatureRenameError, match="at least one"):
        scaffold_feature(
            features_dir,
            repo_root=repo_root,
            feature_id="authentication",
            name="Authentication",
            files=[],
        )


@pytest.mark.unit
def test_scaffold_feature_rejects_missing_file(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    with pytest.raises(FeatureRenameError, match="not a file"):
        scaffold_feature(
            features_dir,
            repo_root=repo_root,
            feature_id="authentication",
            name="Authentication",
            files=[repo_root / "app" / "does_not_exist.py"],
        )
    # Validation happens before any write — no half-built folder.
    assert not (features_dir / "authentication").exists()


@pytest.mark.unit
def test_scaffold_feature_writes_docs_md_when_catalog_matches(tmp_path: Path) -> None:
    """When the source-docs catalog has a doc referencing the scaffolded
    file's path, scaffold_feature writes a docs.md pointer list.

    Exercises the synthesized ``node_by_id`` path (member name → node label)
    that placement.py builds for ``_write_feature_docs``.
    """
    from dummyindex.context.domains.source_docs import (
        DocCatalog,
        DocEntry,
        write_catalog,
    )

    repo_root, features_dir = _repo_with_symbols(tmp_path)
    context_dir = features_dir.parent

    # A real doc on disk whose text mentions the scaffolded file's path and
    # the member symbol name, so both match heuristics fire.
    doc_file = repo_root / "docs" / "auth.md"
    doc_file.parent.mkdir(parents=True)
    doc_file.write_text(
        "# Auth notes\n\nSee `app/auth.py` and the `login()` entry point.\n",
        encoding="utf-8",
    )
    catalog = DocCatalog(
        schema_version=1,
        generated_at="2026-01-01T00:00:00Z",
        repo_root=str(repo_root),
        docs=(
            DocEntry(
                path="docs/auth.md",
                abs_path=str(doc_file),
                doc_type="markdown",
                title="Auth notes",
                headings=("Auth notes",),
                sha256="x",
                size_bytes=doc_file.stat().st_size,
                mtime=doc_file.stat().st_mtime,
                age_delta_seconds=None,
                age_bucket="fresh",
                referenced_count=1,
                broken_refs=(),
                broken_ratio=0.0,
                confidence="high",
                is_external=False,
                source_root=str(repo_root),
            ),
        ),
    )
    write_catalog(context_dir, catalog)

    scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        name="Authentication",
        files=[repo_root / "app" / "auth.py"],
    )

    docs_md = features_dir / "authentication" / "docs.md"
    assert docs_md.is_file()
    body = docs_md.read_text(encoding="utf-8")
    assert "docs/auth.md" in body


@pytest.mark.unit
def test_scaffold_feature_skips_docs_md_without_catalog(tmp_path: Path) -> None:
    """No source-docs catalog → no docs.md (best-effort, never errors)."""
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        name="Authentication",
        files=[repo_root / "app" / "auth.py"],
    )
    assert not (features_dir / "authentication" / "docs.md").exists()


@pytest.mark.unit
def test_scaffold_feature_rejects_file_outside_repo(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(FeatureRenameError, match="under the repo"):
        scaffold_feature(
            features_dir,
            repo_root=repo_root,
            feature_id="authentication",
            name="Authentication",
            files=[outside],
        )


# ----- assign_files ---------------------------------------------------------


def _seeded_feature(tmp_path: Path) -> tuple[Path, Path]:
    """A repo with one already-scaffolded feature owning app/auth.py."""
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        name="Authentication",
        summary="Login.",
        files=[repo_root / "app" / "auth.py"],
    )
    # Enrich the spec.md so we can prove assign-files preserves it.
    (features_dir / "authentication" / "spec.md").write_text(
        "# Feature: Authentication\n\nHand-written enriched prose.\n",
        encoding="utf-8",
    )
    return repo_root, features_dir


@pytest.mark.unit
def test_assign_files_adds_files_and_recomputes_members(tmp_path: Path) -> None:
    repo_root, features_dir = _seeded_feature(tmp_path)
    result = assign_files(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        files=[repo_root / "app" / "session.py"],
    )
    payload = json.loads(
        (features_dir / "authentication" / "feature.json").read_text(encoding="utf-8")
    )
    assert payload["files"] == ["app/auth.py", "app/session.py"]
    assert set(payload["members"]) == {"sym_login", "sym_open"}
    assert result.feature_id == "authentication"


@pytest.mark.unit
def test_assign_files_updates_index_counts(tmp_path: Path) -> None:
    repo_root, features_dir = _seeded_feature(tmp_path)
    assign_files(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        files=[repo_root / "app" / "session.py"],
    )
    idx = json.loads((features_dir / "INDEX.json").read_text(encoding="utf-8"))
    entry = {e["feature_id"]: e for e in idx["features"]}["authentication"]
    assert entry["file_count"] == 2
    assert entry["member_count"] == 2


@pytest.mark.unit
def test_assign_files_preserves_enriched_spec(tmp_path: Path) -> None:
    repo_root, features_dir = _seeded_feature(tmp_path)
    assign_files(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        files=[repo_root / "app" / "session.py"],
    )
    spec = (features_dir / "authentication" / "spec.md").read_text(encoding="utf-8")
    assert "Hand-written enriched prose." in spec


@pytest.mark.unit
def test_assign_files_idempotent_skips_already_assigned(tmp_path: Path) -> None:
    repo_root, features_dir = _seeded_feature(tmp_path)
    # auth.py is already on the feature; re-assigning it is a no-op, not an error.
    result = assign_files(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        files=[repo_root / "app" / "auth.py"],
    )
    payload = json.loads(
        (features_dir / "authentication" / "feature.json").read_text(encoding="utf-8")
    )
    assert payload["files"] == ["app/auth.py"]
    assert result.feature_id == "authentication"


@pytest.mark.unit
def test_assign_files_rejects_missing_feature(tmp_path: Path) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    with pytest.raises(FeatureRenameError, match="not found"):
        assign_files(
            features_dir,
            repo_root=repo_root,
            feature_id="ghost",
            files=[repo_root / "app" / "auth.py"],
        )


@pytest.mark.unit
def test_assign_files_rejects_no_files(tmp_path: Path) -> None:
    repo_root, features_dir = _seeded_feature(tmp_path)
    with pytest.raises(FeatureRenameError, match="at least one"):
        assign_files(
            features_dir,
            repo_root=repo_root,
            feature_id="authentication",
            files=[],
        )


@pytest.mark.unit
def test_assign_files_rejects_missing_file(tmp_path: Path) -> None:
    repo_root, features_dir = _seeded_feature(tmp_path)
    with pytest.raises(FeatureRenameError, match="not a file"):
        assign_files(
            features_dir,
            repo_root=repo_root,
            feature_id="authentication",
            files=[repo_root / "app" / "nope.py"],
        )
    # Feature untouched — validation before write.
    payload = json.loads(
        (features_dir / "authentication" / "feature.json").read_text(encoding="utf-8")
    )
    assert payload["files"] == ["app/auth.py"]


@pytest.mark.unit
def test_assign_files_rejects_file_outside_repo(tmp_path: Path) -> None:
    # Symmetry with scaffold_feature: assign_files shares _normalize_files, so an
    # outside-repo path must be rejected here too (guards against a future
    # divergence that takes assign_files off the shared helper).
    repo_root, features_dir = _seeded_feature(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(FeatureRenameError, match="under the repo"):
        assign_files(
            features_dir,
            repo_root=repo_root,
            feature_id="authentication",
            files=[outside],
        )


# ----- pending-enrichment marker --------------------------------------------


@pytest.mark.unit
def test_scaffold_feature_drops_pending_marker(tmp_path: Path) -> None:
    """A scaffolded feature is born owing enrichment → carries the marker."""
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    result = scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="authentication",
        name="Authentication",
        files=[repo_root / "app" / "auth.py"],
    )
    marker = features_dir / "authentication" / PENDING_ENRICHMENT_MARKER
    assert marker.is_file()
    assert (
        f"features/authentication/{PENDING_ENRICHMENT_MARKER}"
        in result.files_touched
    )


@pytest.mark.unit
def test_assign_files_drops_pending_marker(tmp_path: Path) -> None:
    """Assigning files to an existing feature re-flags it for enrichment.

    Added files don't show as drift (drift is modified/removed only) and the
    feature is no longer unassigned (it now owns them), so without this marker
    a place-then-restart would let the stamp advance past an un-re-enriched
    feature. The marker is the bridge.
    """
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="auth",
        name="Auth",
        files=[repo_root / "app" / "auth.py"],
    )
    # Clear it so the assign is what re-marks the feature.
    clear_pending_enrichment(features_dir, "auth")
    result = assign_files(
        features_dir,
        repo_root=repo_root,
        feature_id="auth",
        files=[repo_root / "app" / "session.py"],
    )
    marker = features_dir / "auth" / PENDING_ENRICHMENT_MARKER
    assert marker.is_file()
    assert f"features/auth/{PENDING_ENRICHMENT_MARKER}" in result.files_touched


@pytest.mark.unit
def test_clear_pending_enrichment_removes_marker_idempotently(
    tmp_path: Path,
) -> None:
    repo_root, features_dir = _repo_with_symbols(tmp_path)
    scaffold_feature(
        features_dir,
        repo_root=repo_root,
        feature_id="auth",
        name="Auth",
        files=[repo_root / "app" / "auth.py"],
    )
    marker = features_dir / "auth" / PENDING_ENRICHMENT_MARKER
    assert marker.is_file()

    cleared = clear_pending_enrichment(features_dir, "auth")
    assert cleared == f"features/auth/{PENDING_ENRICHMENT_MARKER}"
    assert not marker.exists()

    # Idempotent: a second clear is a no-op, not an error.
    assert clear_pending_enrichment(features_dir, "auth") is None


@pytest.mark.unit
def test_clear_pending_enrichment_errors_on_missing_feature(
    tmp_path: Path,
) -> None:
    _repo_root, features_dir = _repo_with_symbols(tmp_path)
    with pytest.raises(FeatureRenameError):
        clear_pending_enrichment(features_dir, "does-not-exist")


# ----- CLI front-ends -------------------------------------------------------


def _ingested(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(_FIXTURE, target)
    assert dispatch(["init", str(target)]) == 0
    return target


@pytest.mark.integration
def test_cli_scaffold_feature_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_scaffold")
    capsys.readouterr()
    # Pick a real source file from the ingested map.
    files_map = json.loads(
        (target / ".context" / "map" / "files.json").read_text(encoding="utf-8")
    )
    a_file = files_map["files"][0]["path"]

    monkeypatch.chdir(target)
    rc = dispatch(
        [
            "scaffold-feature",
            "--id", "new-feature",
            "--name", "New Feature",
            "--summary", "A net-new feature.",
            "--file", a_file,
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "new-feature" in out
    payload = json.loads(
        (target / ".context" / "features" / "new-feature" / "feature.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["name"] == "New Feature"
    assert payload["files"] == [a_file]
    assert payload["confidence"] == ConfidenceLevel.EXTRACTED
    idx = json.loads(
        (target / ".context" / "features" / "INDEX.json").read_text(encoding="utf-8")
    )
    assert "new-feature" in {e["feature_id"] for e in idx["features"]}


@pytest.mark.integration
def test_cli_scaffold_feature_requires_id_name_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_scaffold_missing")
    capsys.readouterr()
    monkeypatch.chdir(target)
    rc = dispatch(["scaffold-feature", "--id", "x"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "--name" in err or "--file" in err


@pytest.mark.integration
def test_cli_scaffold_feature_rejects_community_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_scaffold_community")
    capsys.readouterr()
    files_map = json.loads(
        (target / ".context" / "map" / "files.json").read_text(encoding="utf-8")
    )
    a_file = files_map["files"][0]["path"]
    monkeypatch.chdir(target)
    rc = dispatch(
        ["scaffold-feature", "--id", "community-99", "--name", "X", "--file", a_file]
    )
    assert rc == 2
    assert "community" in capsys.readouterr().err


@pytest.mark.integration
def test_cli_assign_files_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_assign")
    capsys.readouterr()
    files_map = json.loads(
        (target / ".context" / "map" / "files.json").read_text(encoding="utf-8")
    )
    paths = [f["path"] for f in files_map["files"]]
    if len(paths) < 2:
        pytest.skip("fixture has fewer than two files; can't exercise assign")
    first, second = paths[0], paths[1]

    monkeypatch.chdir(target)
    # First scaffold a feature owning `first`, then assign `second` to it.
    assert dispatch(
        ["scaffold-feature", "--id", "host-feature", "--name", "Host", "--file", first]
    ) == 0
    capsys.readouterr()
    rc = dispatch(["assign-files", "--feature", "host-feature", "--file", second])
    assert rc == 0
    out = capsys.readouterr().out
    assert "host-feature" in out
    payload = json.loads(
        (target / ".context" / "features" / "host-feature" / "feature.json").read_text(
            encoding="utf-8"
        )
    )
    assert first in payload["files"]
    assert second in payload["files"]


@pytest.mark.integration
def test_cli_assign_files_requires_feature_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_assign_missing")
    capsys.readouterr()
    monkeypatch.chdir(target)
    rc = dispatch(["assign-files", "--feature", "x"])
    assert rc == 2
    assert "--file" in capsys.readouterr().err


@pytest.mark.integration
def test_cli_mark_enriched_clears_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_mark_enriched")
    files_map = json.loads(
        (target / ".context" / "map" / "files.json").read_text(encoding="utf-8")
    )
    a_file = files_map["files"][0]["path"]
    monkeypatch.chdir(target)
    assert dispatch(
        ["scaffold-feature", "--id", "placed", "--name", "Placed", "--file", a_file]
    ) == 0
    marker = target / ".context" / "features" / "placed" / PENDING_ENRICHMENT_MARKER
    assert marker.is_file()
    capsys.readouterr()

    rc = dispatch(["mark-enriched", "--feature", "placed"])
    assert rc == 0
    assert "placed" in capsys.readouterr().out
    assert not marker.exists()


@pytest.mark.integration
def test_cli_mark_enriched_requires_feature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _ingested(tmp_path, "cli_mark_enriched_missing")
    capsys.readouterr()
    monkeypatch.chdir(target)
    rc = dispatch(["mark-enriched"])
    assert rc == 2
    assert "--feature" in capsys.readouterr().err
