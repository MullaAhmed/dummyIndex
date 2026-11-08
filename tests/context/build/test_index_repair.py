"""Repair stale navigation and orphan coverage without losing authored context."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from dummyindex.context.build import enriched_refresh, upgrade
from dummyindex.context.build.enriched_refresh import refresh_deterministic_artifacts
from dummyindex.context.build.incremental import rebuild_changed
from dummyindex.context.build.meta import SCHEMA_VERSION
from dummyindex.context.build.runner import build_all
from dummyindex.context.build.scope import BuildScopeError
from dummyindex.context.domains.features import rename_feature

pytestmark = pytest.mark.integration


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src/main.py").write_text("def old():\n    return 1\n", encoding="utf-8")
    build_all(root)
    return root


def _curate(root: Path) -> Path:
    features = root / ".context/features"
    first = json.loads((features / "INDEX.json").read_text(encoding="utf-8"))[
        "features"
    ][0]["feature_id"]
    rename_feature(
        features,
        from_id=first,
        to_id="app",
        new_name="App",
        new_summary="Current application.",
    )
    spec = features / "app/spec.md"
    spec.write_text("Owner-authored specification.\n", encoding="utf-8")
    return spec


def _seed_meta(root: Path, **fields: object) -> Path:
    meta_path = root / ".context/meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(fields)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return meta_path


def _boom(*_args, **_kwargs):
    raise RuntimeError("boom")


@pytest.mark.parametrize(
    ("target", "artifact", "warning"),
    [
        ("build_graph", "features/symbol-graph.json", "symbol-graph refresh failed"),
        ("write_catalog", "source-docs/INDEX.json", "source-docs catalog refresh"),
    ],
)
def test_required_artifact_failure_holds_version_and_schema_stamp(
    tmp_path, monkeypatch, target, artifact, warning
):
    root = _repo(tmp_path)
    meta_path = _seed_meta(root, dummyindex_version="0.36.0", schema_version=1)
    monkeypatch.setattr(enriched_refresh, target, _boom)

    with pytest.warns(UserWarning, match=warning):
        result = refresh_deterministic_artifacts(root, dummyindex_version="9.9.9")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["dummyindex_version"] == "0.36.0"
    assert meta["schema_version"] == 1
    assert result.failed == ((artifact, "RuntimeError('boom')"),)
    project = (root / ".context/PROJECT.md").read_text(encoding="utf-8")
    assert "- **dummyIndex version:** 0.36.0" in project


@pytest.mark.parametrize(
    ("stored", "running", "allow_downgrade", "expected"),
    [
        ("0.37.0", "0.36.0", False, "0.37.0"),
        ("0.37.0", "unknown", False, "0.37.0"),
        ("0.37.0", None, False, "0.37.0"),
        ("0.37.0", "0.37.0", False, "0.37.0"),
        ("0.37.0", "9.9.9", False, "9.9.9"),
        ("unknown", "0.37.0", False, "0.37.0"),
        ("unknown", "unknown", False, "unknown"),
        ("0.37.0", "0.36.0", True, "0.36.0"),
    ],
)
def test_version_stamp_never_moves_backwards_unless_forced(
    tmp_path, stored, running, allow_downgrade, expected
):
    root = _repo(tmp_path)
    meta_path = _seed_meta(root, dummyindex_version=stored, schema_version=1)

    result = refresh_deterministic_artifacts(
        root, dummyindex_version=running, allow_downgrade=allow_downgrade
    )

    assert result.failed == ()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["dummyindex_version"] == expected
    # A successful refresh carrying a version upgrades the schema even when the
    # version is unchanged; no version means no stamp write at all.
    assert meta["schema_version"] == (1 if running is None else SCHEMA_VERSION)


def test_advancing_refresh_renders_new_stamp_and_schema(tmp_path):
    root = _repo(tmp_path)
    meta_path = _seed_meta(root, dummyindex_version="0.36.0", schema_version=1)

    refresh_deterministic_artifacts(root, dummyindex_version="9.9.9")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["dummyindex_version"] == "9.9.9"
    assert meta["schema_version"] == SCHEMA_VERSION == 2
    project = (root / ".context/PROJECT.md").read_text(encoding="utf-8")
    assert f"- **dummyIndex version:** {meta['dummyindex_version']}\n" in project
    naming = (root / ".context/conventions/naming.md").read_text(encoding="utf-8")
    assert meta["updated_at"] in naming


def test_refresh_migrates_retired_layout_and_reports_it(tmp_path):
    from dummyindex.export.storage import SHARD_GRACE_SECONDS

    root = _repo(tmp_path)
    context = root / ".context"
    legacy = context / "graph"
    legacy.mkdir()
    (legacy / "graph.json").write_text('{"nodes": []}\n', encoding="utf-8")
    (legacy / "GRAPH_REPORT.md").write_text("# Graph report\n", encoding="utf-8")
    (context / "_enrich_plan.json").write_text("{}\n", encoding="utf-8")
    gitignore = context / ".gitignore"
    gitignore.write_text(
        "".join(
            line
            for line in gitignore.read_text(encoding="utf-8").splitlines(True)
            if line.strip() != "_council-log.json"
        ),
        encoding="utf-8",
    )
    parts = context / "features/symbol-graph.parts"
    parts.mkdir(exist_ok=True)
    aged = time.time() - SHARD_GRACE_SECONDS - 60
    for i in range(3):
        orphan = parts / f"{i:064x}.json"
        orphan.write_text("{}", encoding="utf-8")
        os.utime(orphan, (aged, aged))

    result = refresh_deterministic_artifacts(root, dummyindex_version="9.9.9")

    assert not legacy.exists()
    assert not (context / "_enrich_plan.json").exists()
    assert "_council-log.json" in gitignore.read_text(encoding="utf-8").splitlines()
    assert not parts.exists()  # orphan shards: swept by the graph write
    assert {
        "graph/graph.json",
        "graph/GRAPH_REPORT.md",
        "_enrich_plan.json",
    } <= set(result.migration.removed)
    assert set(result.migration.backed_up) == {
        "_doc_backups/retired/0.6.0/graph/graph.json",
        "_doc_backups/retired/0.6.0/graph/GRAPH_REPORT.md",
    }
    assert result.migration.errors == ()
    assert result.failed == ()


def test_refresh_without_cache_dir_stamps_extraction_version(tmp_path):
    import shutil

    root = _repo(tmp_path)
    cache = root / ".context/cache"
    shutil.rmtree(cache, ignore_errors=True)
    assert not cache.exists()

    refresh_deterministic_artifacts(root, dummyindex_version="9.9.9")

    stamp = cache / "extraction-version"
    assert stamp.read_text(encoding="utf-8").strip() == "9.9.9"


def test_failing_migration_step_is_reported_and_refresh_still_returns(
    tmp_path, monkeypatch
):
    root = _repo(tmp_path)
    meta_path = _seed_meta(root, dummyindex_version="0.36.0")
    (root / ".context/_enrich_plan.json").write_text("{}\n", encoding="utf-8")

    def denied(*_args, **_kwargs):
        raise OSError("retire denied")

    monkeypatch.setattr(upgrade, "retire_paths", denied)

    result = refresh_deterministic_artifacts(root, dummyindex_version="9.9.9")

    assert result.migration.errors == ("retire_paths: retire denied",)
    assert "_enrich_plan.json" in result.migration.removed  # other steps ran
    assert result.failed == ()
    assert "features/symbol-graph.json" in result.written
    assert json.loads(meta_path.read_text())["dummyindex_version"] == "9.9.9"


def test_refresh_repairs_metadata_and_topology_preserving_annotations_and_notes(
    tmp_path,
):
    root = _repo(tmp_path)
    spec = _curate(root)
    original_spec = spec.read_bytes()
    context = root / ".context"
    meta_path = context / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(
        languages=["java"], root="/old/worktree", file_count=999, symbol_count=0
    )
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    project = context / "PROJECT.md"
    project.write_text(
        project.read_text(encoding="utf-8")
        + "\n## Notes\nFirst owner note.\n\n## Notes\nSecond owner note.\n",
        encoding="utf-8",
    )
    tree_path = context / "tree.json"
    old_tree = json.loads(tree_path.read_text(encoding="utf-8"))
    old_tree["root"]["abstract"] = "Authored overview."
    tree_path.write_text(json.dumps(old_tree), encoding="utf-8")
    (root / "src/new.py").write_text(
        "class New:\n    def method(self): return 2\n", encoding="utf-8"
    )

    refresh_deterministic_artifacts(root)

    repaired = json.loads(meta_path.read_text(encoding="utf-8"))
    assert repaired["languages"] == ["python"]
    assert repaired["root"] == "."
    assert repaired["symbol_count"] >= 3
    assert spec.read_bytes() == original_spec
    text = project.read_text(encoding="utf-8")
    assert "**Languages:** python" in text
    assert "First owner note." in text and "Second owner note." in text
    assert text.count("## Notes") == 2
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    assert tree["root"]["abstract"] == "Authored overview."
    assert "source-stale" in tree["root"]["labels"]
    assert "src/new.py" in json.dumps(tree)
    coverage = json.loads((context / "coverage.json").read_text(encoding="utf-8"))
    assert "src/new.py" in coverage["unassigned"]
    assert any(
        f["symbols"] >= 2 for f in coverage["files"] if f["path"] == "src/new.py"
    )


def test_rebuild_remembers_scan_scope_instead_of_expanding_to_output_root(tmp_path):
    root = tmp_path / "repo"
    app = root / "app"
    app.mkdir(parents=True)
    (app / "main.py").write_text("def run(): return 1\n", encoding="utf-8")
    (root / "unrelated.py").write_text("class Outside: pass\n", encoding="utf-8")
    build_all(app, out_root=root)
    _curate(root)
    (app / "main.py").write_text("def run(): return 2\n", encoding="utf-8")
    assert rebuild_changed(root).preserved_enriched
    files = json.loads((root / ".context/map/files.json").read_text(encoding="utf-8"))[
        "files"
    ]
    assert [f["path"] for f in files] == ["app/main.py"]
    assert (
        json.loads((root / ".context/meta.json").read_text())["config"]["scan_scope"]
        == "app"
    )


def test_orphaned_anchor_inventory_keeps_preexisting_unowned_source_visible(
    tmp_path, monkeypatch
):
    import dummyindex.context.build.git_delta as git_delta
    import dummyindex.context.build.reconcile as reconcile

    root = _repo(tmp_path)
    _curate(root)
    context = root / ".context"
    meta_path = context / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["indexed_commit"] = "a" * 40
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    (root / "src/unowned.py").write_text("def missed(): pass\n", encoding="utf-8")
    monkeypatch.setattr(
        git_delta, "commit_exists", lambda _root, commit: commit != "a" * 40
    )
    monkeypatch.setattr(reconcile, "commit_exists", git_delta.commit_exists)
    refresh_deterministic_artifacts(root)
    report = reconcile.compute_reconcile_report(context, root)
    assert report.anchor_broken
    assert "src/unowned.py" in report.unassigned_new_files
    assert "app" in report.awaiting_enrichment
    result = reconcile.stamp_reconciled(context, root, to_commit="b" * 40)
    assert result.refused
    assert json.loads(meta_path.read_text())["indexed_commit"] == "a" * 40


def test_disjoint_scope_cannot_write_context(tmp_path):
    scope = tmp_path / "source"
    destination = tmp_path / "other"
    scope.mkdir()
    destination.mkdir()
    with pytest.raises(BuildScopeError):
        build_all(scope, out_root=destination)
    assert not list(destination.iterdir())


def test_placement_updates_coverage_without_erasing_extraction_evidence(tmp_path):
    from dummyindex.context.domains.features import assign_files

    root = _repo(tmp_path)
    _curate(root)
    source = root / "src/new.py"
    source.write_text("def new(): pass\n")
    refresh_deterministic_artifacts(root)
    path = root / ".context/coverage.json"
    before = json.loads(path.read_text())
    assert "src/new.py" in before["unassigned"]
    before["identity_ambiguities"] = [{"original_id": "kept-provenance"}]
    path.write_text(json.dumps(before), encoding="utf-8")
    assign_files(
        root / ".context/features", repo_root=root, feature_id="app", files=[source]
    )
    after = json.loads(path.read_text())
    assert after["unassigned"] == []
    assert after["identity_ambiguities"] == before["identity_ambiguities"]
    assert next(row for row in after["files"] if row["path"] == "src/new.py")[
        "owners"
    ] == ["app"]


def test_linked_context_destination_is_preserved(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    old = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == context or old(path))
    with pytest.raises(BuildScopeError):
        build_all(root)
    assert not list(context.iterdir())


def test_reparse_destination_is_rejected_without_junction_api(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from dummyindex.context.build.scope import validate_context_destination

    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    original = Path.lstat
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda p: (
            SimpleNamespace(st_file_attributes=1024, st_mode=0o40755)
            if p == context
            else original(p)
        ),
    )
    with pytest.raises(BuildScopeError, match="linked"):
        validate_context_destination(root)


def test_same_size_body_edit_marks_annotation_stale(tmp_path):
    root = _repo(tmp_path)
    context = root / ".context"
    tree_path = context / "tree.json"
    tree = json.loads(tree_path.read_text())

    def annotate(node):
        if node.get("kind") == "function":
            node["abstract"] = "Returns one."
            node["confidence"] = "INFERRED"
        for child in node.get("children", []):
            annotate(child)

    annotate(tree["root"])
    tree_path.write_text(json.dumps(tree), encoding="utf-8")
    (root / "src/main.py").write_text("def old():\n    return 2\n", encoding="utf-8")
    refresh_deterministic_artifacts(root)
    text = tree_path.read_text()
    assert "Returns one." in text
    assert "source-stale" in text


def test_mechanical_summaries_refresh_instead_of_becoming_stale_annotations(tmp_path):
    root = _repo(tmp_path)
    (root / "src/main.py").write_text("\n\n\ndef old():\n    return 1\n")
    refresh_deterministic_artifacts(root)
    tree = json.loads((root / ".context/tree.json").read_text())

    def nodes(node):
        yield node
        for child in node.get("children", []):
            yield from nodes(child)

    function = next(n for n in nodes(tree["root"]) if n.get("kind") == "function")
    assert function["range"][0] == 4
    assert function["abstract"].endswith(":4.")
    assert "source-stale" not in function["labels"]


def test_authored_template_like_prose_is_preserved(tmp_path):
    root = _repo(tmp_path)
    path = root / ".context/tree.json"
    tree = json.loads(path.read_text())
    tree["root"]["abstract"] = (
        "Codebase rooted at reusable rules, with manual ownership notes."
    )
    path.write_text(json.dumps(tree), encoding="utf-8")
    refresh_deterministic_artifacts(root)
    assert json.loads(path.read_text())["root"]["abstract"] == tree["root"]["abstract"]


def test_same_named_methods_preserve_their_distinct_authored_summaries(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "models.py").write_text(
        "class A:\n    def run(self): return 1\n\nclass B:\n    def run(self): return 2\n"
    )
    build_all(root)
    path = root / ".context/tree.json"
    tree = json.loads(path.read_text())

    def nodes(node):
        yield node
        for child in node.get("children", []):
            yield from nodes(child)

    before = {}
    for node in nodes(tree["root"]):
        if node.get("kind") == "method":
            node["abstract"] = "Authored for " + node["node_id"]
            node["confidence"] = "INFERRED"
            before[node["node_id"]] = node["abstract"]
    path.write_text(json.dumps(tree), encoding="utf-8")
    refresh_deterministic_artifacts(root)
    after = {
        n["node_id"]: n["abstract"]
        for n in nodes(json.loads(path.read_text())["root"])
        if n.get("kind") == "method"
    }
    assert len(before) == 2 and before == after


@pytest.mark.parametrize("orphan", [False, True])
def test_reconcile_scope_excludes_unrelated_source(tmp_path, monkeypatch, orphan):
    import dummyindex.context.build.reconcile as reconcile
    from dummyindex.context.build.git_delta import ChangedPaths

    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "app/main.py").write_text("def run(): pass\n", encoding="utf-8")
    (root / "outside.py").write_text("def elsewhere(): pass\n", encoding="utf-8")
    build_all(root / "app", out_root=root)
    meta_path = root / ".context/meta.json"
    meta = json.loads(meta_path.read_text())
    meta["indexed_commit"] = "a" * 40
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setattr(reconcile, "commit_exists", lambda *_: not orphan)
    monkeypatch.setattr(reconcile, "is_ancestor_of_head", lambda *_: True)
    monkeypatch.setattr(
        reconcile,
        "changed_paths",
        lambda *_: ChangedPaths(added=("outside.py",), modified=(), removed=()),
    )
    report = reconcile.compute_reconcile_report(root / ".context", root)
    assert not report.unassigned_new_files


def test_portable_root_readers_ignore_process_cwd(tmp_path, monkeypatch):
    from dummyindex.context.build.communities import _indexed_root as communities_root
    from dummyindex.context.domains.features.helpers import (
        _indexed_root as feature_root,
    )
    from dummyindex.context.output.viewer.extras import _indexed_root as viewer_root

    root = _repo(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    context = root / ".context"
    assert feature_root(context) == root
    assert communities_root(context / "features") == root
    assert viewer_root(context / "features") == root


def test_root_build_ignore_does_not_hide_nested_source_package(tmp_path):
    root = tmp_path / "repo"
    nested = root / "package/build"
    nested.mkdir(parents=True)
    (nested / "module.py").write_text("class Builder:\n    def run(self): pass\n")
    (root / "build").mkdir()
    (root / "build/generated.py").write_text("class Generated: pass\n")
    (root / ".gitignore").write_text("/build/\n")
    build_all(root)
    coverage = json.loads((root / ".context/coverage.json").read_text())
    assert [f["path"] for f in coverage["files"]] == ["package/build/module.py"]
    assert any(e["path"] == "build" and e["reason"] for e in coverage["excluded"])


def test_unsupported_file_is_accounted_without_losing_python_extraction(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "main.py").write_text("def run(): pass\n")
    (root / "addon.ejs").write_text("Addon metadata\n")
    build_all(root)
    coverage = json.loads((root / ".context/coverage.json").read_text())
    rows = {row["path"]: row for row in coverage["files"]}
    assert rows["main.py"]["symbols"] >= 1
    assert rows["addon.ejs"]["state"] == "unsupported"
    assert rows["addon.ejs"]["reason"]


def test_detection_does_not_follow_external_source_directory(tmp_path):
    import os
    import subprocess

    from dummyindex.pipeline.io.detect import detect

    root, outside = tmp_path / "repo", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "escaped.py").write_text("class Outside: pass\n")
    link = root / "linked"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"New-Item -ItemType Junction -Path '{link}' -Value '{outside}' | Out-Null",
            ],
            check=True,
            capture_output=True,
        )
    result = detect(root)
    assert result["files"]["code"] == []
    assert any(
        row["path"] == "linked" and "linked" in row["reason"]
        for row in result["excluded"]
    )
    followed = detect(root, follow_symlinks=True)
    assert followed["files"]["code"] == []
    assert any("scan root" in row["reason"] for row in followed["excluded"])
