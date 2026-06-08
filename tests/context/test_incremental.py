"""Tests for dummyindex.context.incremental — rebuild_changed quick-exit."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from dummyindex.context.build import ChangeSet, rebuild_changed
# `_is_enriched_index` is a private helper imported white-box on purpose:
# these are guard tests for the fail-safe (bias-to-preserve) semantics of
# the data-loss stopper, which has no public surface of its own.
from dummyindex.context.build.incremental import _is_enriched_index
from dummyindex.context.build.runner import build_all
from dummyindex.context.domains.features import rename_feature

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def primed_repo(tmp_path: Path) -> Path:
    """Sample repo with .context/ already built once."""
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    build_all(dest, cache_root=tmp_path / "cache")
    return dest


@pytest.mark.integration
def test_first_run_no_existing_context_treats_all_as_added(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh"
    shutil.copytree(_FIXTURE_ROOT, fresh)
    result = rebuild_changed(fresh, cache_root=tmp_path / "cache")
    assert result.skipped is False
    assert result.build_result is not None
    assert len(result.changes.added) >= 1
    assert result.changes.modified == ()
    assert result.changes.removed == ()


@pytest.mark.integration
def test_no_changes_skips(primed_repo: Path, tmp_path: Path) -> None:
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.skipped is True
    assert result.build_result is None
    assert not result.changes.has_changes


@pytest.mark.integration
def test_modified_file_triggers_rebuild(primed_repo: Path, tmp_path: Path) -> None:
    app_py = primed_repo / "app.py"
    app_py.write_text(
        app_py.read_text(encoding="utf-8") + "\n# trivial edit\n",
        encoding="utf-8",
    )
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.skipped is False
    assert "app.py" in result.changes.modified
    assert result.changes.added == ()
    assert result.changes.removed == ()
    assert result.build_result is not None


@pytest.mark.integration
def test_added_file_triggers_rebuild(primed_repo: Path, tmp_path: Path) -> None:
    new_py = primed_repo / "extra.py"
    new_py.write_text("def added() -> int:\n    return 1\n", encoding="utf-8")
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.skipped is False
    assert "extra.py" in result.changes.added


@pytest.mark.integration
def test_removed_file_triggers_rebuild(primed_repo: Path, tmp_path: Path) -> None:
    (primed_repo / "helpers.py").unlink()
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.skipped is False
    assert "helpers.py" in result.changes.removed


@pytest.mark.integration
def test_rebuild_produces_updated_files_json(
    primed_repo: Path, tmp_path: Path
) -> None:
    new_py = primed_repo / "addition.py"
    new_py.write_text("def added() -> int:\n    return 99\n", encoding="utf-8")
    rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    files_json = (primed_repo / ".context" / "map" / "files.json").read_text(
        encoding="utf-8"
    )
    assert "addition.py" in files_json


@pytest.mark.unit
def test_changeset_has_changes_property() -> None:
    empty = ChangeSet(added=(), modified=(), removed=())
    assert empty.has_changes is False
    only_added = ChangeSet(added=("a.py",), modified=(), removed=())
    assert only_added.has_changes is True
    only_modified = ChangeSet(added=(), modified=("b.py",), removed=())
    assert only_modified.has_changes is True
    only_removed = ChangeSet(added=(), modified=(), removed=("c.py",))
    assert only_removed.has_changes is True


# ----- enriched-index guard (Phase 1: the data-loss stopper) ----------------

_SPEC_SENTINEL = "<!-- COUNCIL-AUTHORED SPEC — DO NOT REGENERATE -->"
_TREE_SENTINEL = "Enriched abstract that must survive a --changed rebuild."


def _enrich(repo: Path) -> str:
    """Turn a freshly-built deterministic index into a curated one.

    Renames the first community feature (which flips its confidence to
    INFERRED via the council's real op), stamps a sentinel into that
    feature's spec.md, and stamps a sentinel into tree.json's root
    abstract. Returns the renamed feature's new id.
    """
    context_dir = repo / ".context"
    features_dir = context_dir / "features"
    index = json.loads((features_dir / "INDEX.json").read_text(encoding="utf-8"))
    first_id = index["features"][0]["feature_id"]
    new_id = "authentication"
    rename_feature(
        features_dir,
        from_id=first_id,
        to_id=new_id,
        new_name="Authentication",
        new_summary="Curated by the council.",
    )
    spec = features_dir / new_id / "spec.md"
    spec.write_text(_SPEC_SENTINEL + "\n", encoding="utf-8")

    tree_path = context_dir / "tree.json"
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    tree["root"]["abstract"] = _TREE_SENTINEL
    tree_path.write_text(json.dumps(tree, indent=2) + "\n", encoding="utf-8")
    return new_id


@pytest.mark.unit
def test_is_enriched_index_detects_named_feature(tmp_path: Path) -> None:
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text(
        json.dumps(
            {
                "features": [
                    {"feature_id": "auth", "confidence": "EXTRACTED"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _is_enriched_index(tmp_path / ".context") is True


@pytest.mark.unit
def test_is_enriched_index_detects_inferred_confidence(tmp_path: Path) -> None:
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text(
        json.dumps(
            {
                "features": [
                    {"feature_id": "community-0", "confidence": "INFERRED"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _is_enriched_index(tmp_path / ".context") is True


@pytest.mark.unit
def test_is_enriched_index_false_for_deterministic(tmp_path: Path) -> None:
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text(
        json.dumps(
            {
                "features": [
                    {"feature_id": "community-0", "confidence": "EXTRACTED"},
                    {"feature_id": "community-unassigned", "confidence": "EXTRACTED"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _is_enriched_index(tmp_path / ".context") is False


@pytest.mark.unit
def test_is_enriched_index_false_when_index_absent(tmp_path: Path) -> None:
    # Genuinely absent INDEX.json → no index → safe to full-build.
    (tmp_path / ".context" / "features").mkdir(parents=True)
    assert _is_enriched_index(tmp_path / ".context") is False


@pytest.mark.unit
def test_is_enriched_index_true_on_corrupt_json(tmp_path: Path) -> None:
    # Merge-conflict markers / truncated write → JSONDecodeError. We MUST
    # bias to preserve: returning False here would trigger a destructive
    # full rebuild on a possibly-enriched index.
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text(
        "<<<<<<< HEAD\n{not valid json\n=======\n}\n>>>>>>> branch\n",
        encoding="utf-8",
    )
    assert _is_enriched_index(tmp_path / ".context") is True


@pytest.mark.unit
def test_is_enriched_index_true_when_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exists but unreadable (e.g. PermissionError). chmod 000 is a no-op as
    # root, so simulate the OSError via monkeypatch. Bias to preserve.
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    index_json = features_dir / "INDEX.json"
    index_json.write_text("{}", encoding="utf-8")

    real_read_text = Path.read_text

    def boom(self: Path, *args: object, **kwargs: object) -> str:
        if self == index_json:
            raise PermissionError("denied")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)
    assert _is_enriched_index(tmp_path / ".context") is True


@pytest.mark.unit
def test_is_enriched_index_true_on_non_dict_payload(tmp_path: Path) -> None:
    # Parses, but the top-level value isn't an object → malformed →
    # preserve rather than assume "not enriched".
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert _is_enriched_index(tmp_path / ".context") is True


@pytest.mark.unit
def test_is_enriched_index_true_when_features_key_missing(tmp_path: Path) -> None:
    # A dict with no `features` key is malformed (a real index always has
    # one) → preserve.
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text(
        json.dumps({"schema_version": 1}), encoding="utf-8"
    )
    assert _is_enriched_index(tmp_path / ".context") is True


@pytest.mark.unit
def test_is_enriched_index_false_when_features_empty(tmp_path: Path) -> None:
    # Present and explicitly empty → genuinely nothing to lose → full build.
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text(
        json.dumps({"features": []}), encoding="utf-8"
    )
    assert _is_enriched_index(tmp_path / ".context") is False


@pytest.mark.unit
def test_is_enriched_index_true_when_partially_enriched(tmp_path: Path) -> None:
    # Some features still deterministic, at least one INFERRED → preserve.
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text(
        json.dumps(
            {
                "features": [
                    {"feature_id": "community-0", "confidence": "EXTRACTED"},
                    {"feature_id": "community-1", "confidence": "INFERRED"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _is_enriched_index(tmp_path / ".context") is True


@pytest.mark.unit
def test_is_enriched_index_matches_enum_repr_confidence(tmp_path: Path) -> None:
    # Confidence may serialise as the enum repr `ConfidenceLevel.INFERRED`
    # rather than the bare value. The check must match robustly.
    features_dir = tmp_path / ".context" / "features"
    features_dir.mkdir(parents=True)
    (features_dir / "INDEX.json").write_text(
        json.dumps(
            {
                "features": [
                    {
                        "feature_id": "community-0",
                        "confidence": "ConfidenceLevel.INFERRED",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    assert _is_enriched_index(tmp_path / ".context") is True


@pytest.mark.integration
def test_enriched_index_survives_changed_rebuild(
    primed_repo: Path, tmp_path: Path
) -> None:
    """The core regression: --changed must not clobber a curated index."""
    new_id = _enrich(primed_repo)
    context_dir = primed_repo / ".context"
    features_dir = context_dir / "features"

    index_before = (features_dir / "INDEX.json").read_text(encoding="utf-8")

    # Make a real source change so rebuild_changed doesn't quick-exit.
    app_py = primed_repo / "app.py"
    app_py.write_text(
        app_py.read_text(encoding="utf-8") + "\n# edit\n", encoding="utf-8"
    )

    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")

    # Took the non-destructive path: no full build_all.
    assert result.preserved_enriched is True
    assert result.build_result is None

    # Curated feature folder + enriched spec.md survive verbatim.
    assert (features_dir / new_id / "feature.json").is_file()
    assert _SPEC_SENTINEL in (features_dir / new_id / "spec.md").read_text(
        encoding="utf-8"
    )

    # INDEX.json unchanged — no re-clustering. The curated feature stays
    # named; the verbatim match proves no community-* re-scaffold ran (a
    # re-cluster would drop `authentication` and re-stub the folder).
    index_after = (features_dir / "INDEX.json").read_text(encoding="utf-8")
    assert index_after == index_before
    assert new_id in index_after

    # Enriched tree abstract preserved (tree.json not regenerated).
    tree = json.loads((context_dir / "tree.json").read_text(encoding="utf-8"))
    assert tree["root"]["abstract"] == _TREE_SENTINEL


@pytest.mark.integration
def test_enriched_changed_rebuild_advances_indexed_commit(
    primed_repo: Path, tmp_path: Path
) -> None:
    _enrich(primed_repo)
    context_dir = primed_repo / ".context"
    (primed_repo / "app.py").write_text(
        (primed_repo / "app.py").read_text(encoding="utf-8") + "\n# x\n",
        encoding="utf-8",
    )
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.preserved_enriched is True
    # meta.json gets re-stamped with the (off-git here → None) anchor and a
    # fresh updated_at; the field exists either way.
    meta = json.loads((context_dir / "meta.json").read_text(encoding="utf-8"))
    assert "indexed_commit" in meta


@pytest.mark.integration
def test_deterministic_index_still_full_builds_on_changed(
    primed_repo: Path, tmp_path: Path
) -> None:
    """A fresh community-*/EXTRACTED index has nothing to lose → full build."""
    (primed_repo / "extra.py").write_text(
        "def added() -> int:\n    return 1\n", encoding="utf-8"
    )
    result = rebuild_changed(primed_repo, cache_root=tmp_path / "cache_2")
    assert result.preserved_enriched is False
    assert result.build_result is not None


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.mark.integration
def test_enriched_changed_rebuild_captures_committed_drift(
    tmp_path: Path,
) -> None:
    """BLOCK 2 regression: reconcile must diff the PRIOR anchor..HEAD.

    With the old order (refresh advances ``meta.indexed_commit`` to the new
    HEAD *before* reconcile reads it), a change committed since the index
    anchor is diffed away — reconcile sees HEAD..worktree (clean) and drops
    all committed drift. This proves committed drift is captured.
    """
    repo = tmp_path / "repo"
    shutil.copytree(_FIXTURE_ROOT, repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")  # commit A — the index anchor

    build_all(repo, cache_root=tmp_path / "cache")
    new_id = _enrich(repo)

    context_dir = repo / ".context"
    feature_json = json.loads(
        (context_dir / "features" / new_id / "feature.json").read_text(
            encoding="utf-8"
        )
    )
    owned = [f for f in feature_json.get("files", []) if (repo / f).is_file()]
    assert owned, "curated feature must own at least one real file"
    target = owned[0]

    # Commit a real change to an owned file (HEAD advances A -> B). This is
    # the committed drift the buggy order silently dropped.
    edited = repo / target
    edited.write_text(
        edited.read_text(encoding="utf-8") + "\n# committed drift\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "edit owned file")

    result = rebuild_changed(repo, cache_root=tmp_path / "cache_2")

    assert result.preserved_enriched is True
    assert result.reconcile is not None
    assert new_id in result.reconcile.drifted_features


@pytest.mark.integration
def test_full_flag_forces_recluster_on_enriched(
    primed_repo: Path, tmp_path: Path
) -> None:
    """--full overrides the guard and re-clusters, discarding the taxonomy."""
    new_id = _enrich(primed_repo)
    features_dir = primed_repo / ".context" / "features"
    (primed_repo / "app.py").write_text(
        (primed_repo / "app.py").read_text(encoding="utf-8") + "\n# y\n",
        encoding="utf-8",
    )
    result = rebuild_changed(
        primed_repo, cache_root=tmp_path / "cache_2", full=True
    )
    assert result.preserved_enriched is False
    assert result.build_result is not None
    # A full re-cluster ran: INDEX.json no longer lists the curated feature
    # and community-* stubs are back. (The renamed folder is orphaned on
    # disk, not deleted — that orphaning is exactly the destructive
    # behaviour --full is allowed to cause and the guard otherwise prevents.)
    index_after = (features_dir / "INDEX.json").read_text(encoding="utf-8")
    assert new_id not in index_after
    assert "community-" in index_after
