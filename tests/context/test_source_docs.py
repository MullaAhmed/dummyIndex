"""Tests for the source-docs catalog + staleness model.

The advisor flagged that "advisory" is meaningless unless the staleness
signals actually fire. The most load-bearing test in this file is
``test_broken_refs_flag_stale_doc`` — it edits a doc to reference a
class that no longer exists in the AST and asserts the catalog drops
confidence + lists the broken ref.
"""
from __future__ import annotations
from dummyindex.context.enums import DocConfidence

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.build.runner import build_all
from dummyindex.context.domains.source_docs import (
    build_doc_catalog,
    discover_default_doc_paths,
    extract_code_refs,
    find_broken_refs,
    looks_like_code_ref,
    read_catalog,
    write_catalog,
)

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_discover_default_finds_root_level_markdown(sample_repo: Path) -> None:
    """Root-level *.md files that don't match the well-known names list
    (BRIEF.md / arbitrary-name.md) still get discovered."""
    (sample_repo / "BRIEF.md").write_text("# Brief\n\nshort\n", encoding="utf-8")
    (sample_repo / "RANDOM.md").write_text("# Random\n", encoding="utf-8")
    (sample_repo / "README.md").write_text("# Sample\n\nIntro paragraph.\n", encoding="utf-8")

    found = {p.name for p in discover_default_doc_paths(sample_repo)}
    assert "BRIEF.md" in found
    assert "RANDOM.md" in found
    assert "README.md" in found


def test_discover_finds_common_doc_dirs(sample_repo: Path) -> None:
    (sample_repo / "docs").mkdir()
    (sample_repo / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (sample_repo / "adr").mkdir()
    (sample_repo / "adr" / "001-choice.md").write_text("# ADR 001\n", encoding="utf-8")

    found = {p.name for p in discover_default_doc_paths(sample_repo)}
    assert "docs" in found
    assert "adr" in found


# ---------------------------------------------------------------------------
# Reference extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token,expected",
    [
        ("App", True),                 # CamelCase
        ("make_app", True),            # snake_case
        ("make_app()", True),          # function call
        ("App.run", True),             # dotted
        ("App.run()", True),
        ("app.py", True),              # file path
        ("dummyindex/context/runner.py", True),
        ("hello", False),              # plain prose word
        ("true", False),               # whitelisted
        ("let x = 1", False),          # has spaces
        ("THIS_IS_CONSTANT", False),   # all-caps with underscores → not in our pattern; OK
    ],
)
def test_looks_like_code_ref(token: str, expected: bool) -> None:
    assert looks_like_code_ref(token) is expected


def test_extract_code_refs_skips_code_fences() -> None:
    text = """
Here is `MyClass` and `helper_fn()`.

```python
NotMyClass = 1
```

Also referencing `app.py`.
"""
    refs = extract_code_refs(text)
    assert "MyClass" in refs
    assert "helper_fn()" in refs
    assert "app.py" in refs
    assert "NotMyClass" not in refs


def test_framework_identifiers_are_not_broken() -> None:
    """Claude Code tool names + hook event names are framework refs,
    not project symbols — must not be flagged broken."""
    refs = ("Task", "Write", "Read", "Edit", "PostToolUse", "SessionStart", "subagent_type")
    broken = find_broken_refs(
        refs,
        symbol_names=frozenset(),
        file_paths=frozenset(),
    )
    assert broken == ()


def test_doc_paths_match_basename_via_widened_file_set() -> None:
    """When file_paths includes the catalog's own doc files, refs like
    `README.md` match against the doc's own basename."""
    refs = ("README.md", "CHANGELOG.md", "docs/brief/03-architecture.md")
    file_paths = frozenset({
        "README.md",
        "CHANGELOG.md",
        "docs/brief/03-architecture.md",
        "src/app.py",
    })
    broken = find_broken_refs(
        refs,
        symbol_names=frozenset(),
        file_paths=file_paths,
    )
    assert broken == ()


def test_extra_names_accepts_json_schema_fields() -> None:
    """JSON schema keys (harvested via harvest_json_keys) accepted via extra_names."""
    refs = ("feature_id", "node_id", "broken_refs", "confidence")
    broken = find_broken_refs(
        refs,
        symbol_names=frozenset(),
        file_paths=frozenset(),
        extra_names=frozenset({"feature_id", "node_id", "broken_refs", "confidence"}),
    )
    assert broken == ()


def test_harvest_json_keys_walks_nested_objects(tmp_path: Path) -> None:
    """harvest_json_keys must surface keys at every nesting depth."""
    from dummyindex.context.domains.source_docs import harvest_json_keys

    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({
        "feature_id": "x",
        "members": [{"node_id": 1, "kind": "class"}],
        "meta": {"schema_version": 1, "by_confidence": {DocConfidence.HIGH: 3}},
    }), encoding="utf-8")
    keys = harvest_json_keys([schema])
    assert "feature_id" in keys
    assert "node_id" in keys
    assert "kind" in keys
    assert "schema_version" in keys
    assert "by_confidence" in keys
    assert "high" in keys


def test_find_broken_refs_basic() -> None:
    refs = ("MyClass", "helper_fn", "app.py", "OldGoneClass")
    broken = find_broken_refs(
        refs,
        symbol_names=frozenset({"MyClass", "helper_fn"}),
        file_paths=frozenset({"app.py"}),
    )
    assert broken == ("OldGoneClass",)


def test_find_broken_refs_matches_basename() -> None:
    """Docs often cite `runner.py` without the dir prefix — accept that."""
    refs = ("runner.py",)
    broken = find_broken_refs(
        refs,
        symbol_names=frozenset(),
        file_paths=frozenset({"dummyindex/context/runner.py"}),
    )
    assert broken == ()


def test_find_broken_refs_matches_dotted_tail() -> None:
    """`parser.parse_body` should match if `parse_body` exists as a symbol."""
    refs = ("parser.parse_body",)
    broken = find_broken_refs(
        refs,
        symbol_names=frozenset({"parse_body"}),
        file_paths=frozenset(),
    )
    assert broken == ()


# ---------------------------------------------------------------------------
# Catalog construction
# ---------------------------------------------------------------------------


def _write_doc(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_catalog_determinism(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_doc(repo / "README.md", "# Sample\n\nuses `App.run()`.\n")
    _write_doc(repo / "GUIDE.md", "# Guide\n\nsee `App`.\n")

    c1 = build_doc_catalog(
        [repo / "README.md", repo / "GUIDE.md"],
        repo_root=repo,
        symbol_names=frozenset({"App", "run"}),
        file_paths=frozenset({"app.py"}),
        newest_code_mtime=None,
    )
    c2 = build_doc_catalog(
        [repo / "README.md", repo / "GUIDE.md"],
        repo_root=repo,
        symbol_names=frozenset({"App", "run"}),
        file_paths=frozenset({"app.py"}),
        newest_code_mtime=None,
    )
    # Strip the timestamp; everything else must be byte-identical.
    d1 = c1.to_dict(); d1.pop("generated_at")
    d2 = c2.to_dict(); d2.pop("generated_at")
    assert d1 == d2


def test_broken_refs_flag_stale_doc(tmp_path: Path) -> None:
    """The load-bearing test: mutate a doc to mention an extinct class
    and verify confidence drops + broken_refs is populated.

    This is the test that exercises "advisory". Without it, "advisory"
    is just a vibe.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_doc(
        repo / "ARCHITECTURE.md",
        (
            "# Architecture\n\n"
            "The system is centered on `OldRenamedClass`, which lives in "
            "`legacy_module.py` and exposes `legacy_method()`. "
            "It also touches `also_gone_helper`.\n"
        ),
    )
    catalog = build_doc_catalog(
        [repo / "ARCHITECTURE.md"],
        repo_root=repo,
        symbol_names=frozenset({"NewClass", "new_method"}),
        file_paths=frozenset({"new_module.py"}),
        newest_code_mtime=None,
    )
    assert len(catalog.docs) == 1
    entry = catalog.docs[0]
    assert entry.confidence == DocConfidence.LOW
    assert set(entry.broken_refs) >= {
        "OldRenamedClass",
        "legacy_module.py",
        "legacy_method()",
        "also_gone_helper",
    }
    assert entry.referenced_count >= 4
    assert entry.broken_ratio == pytest.approx(1.0)


def test_high_confidence_when_refs_match(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_doc(
        repo / "README.md",
        "# Sample\n\nThe `App.run()` method is in `app.py`. Use `make_app()`.\n",
    )
    catalog = build_doc_catalog(
        [repo / "README.md"],
        repo_root=repo,
        symbol_names=frozenset({"App", "run", "make_app"}),
        file_paths=frozenset({"app.py"}),
        newest_code_mtime=None,
    )
    assert len(catalog.docs) == 1
    assert catalog.docs[0].confidence == DocConfidence.HIGH
    assert catalog.docs[0].broken_refs == ()


def test_age_bucket_old_lowers_confidence(tmp_path: Path) -> None:
    """A doc with enough broken refs AND an old mtime should drop to `low`.

    Old age alone isn't enough to crash confidence — we also need the
    broken-ref count to clear the small-doc floor (otherwise a 400-day
    old README with one missing identifier would unfairly flip to low).
    """
    import os
    import time

    repo = tmp_path / "repo"
    repo.mkdir()
    doc = repo / "STALE.md"
    _write_doc(
        doc,
        "# Stale\n\nReferences `GoneOne`, `GoneTwo`, `GoneThree`, `GoneFour`.\n",
    )
    # Pretend the doc was last touched 400 days before the newest code.
    very_old = time.time() - (400 * 86400)
    os.utime(doc, (very_old, very_old))

    catalog = build_doc_catalog(
        [doc],
        repo_root=repo,
        symbol_names=frozenset({"NewSymbol"}),
        file_paths=frozenset(),
        newest_code_mtime=time.time(),
    )
    assert catalog.docs[0].age_bucket in ("stale", "old")
    assert catalog.docs[0].confidence == DocConfidence.LOW


def test_tiny_doc_with_one_broken_ref_stays_medium(tmp_path: Path) -> None:
    """Regression: a 1-ref doc whose only ref is broken must stay
    `medium`, not flip to `low`. Otherwise example-mentioning ADRs
    get unfairly downgraded just for citing a hypothetical symbol.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_doc(
        repo / "TINY.md",
        "# Tiny\n\nThe example feature here is `Authentication`.\n",
    )
    catalog = build_doc_catalog(
        [repo / "TINY.md"],
        repo_root=repo,
        symbol_names=frozenset({"App"}),
        file_paths=frozenset(),
        newest_code_mtime=None,
    )
    entry = catalog.docs[0]
    assert entry.broken_refs == ("Authentication",)
    assert entry.confidence == DocConfidence.MEDIUM


def test_catalog_round_trip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_doc(repo / "README.md", "# Hi\n\nuses `App`.\n")
    catalog = build_doc_catalog(
        [repo / "README.md"],
        repo_root=repo,
        symbol_names=frozenset({"App"}),
        file_paths=frozenset(),
        newest_code_mtime=None,
    )
    ctx = tmp_path / ".context"
    write_catalog(ctx, catalog)
    loaded = read_catalog(ctx)
    assert loaded is not None
    assert len(loaded.docs) == 1
    assert loaded.docs[0].path == "README.md"


def test_external_doc_root_marked_external(tmp_path: Path) -> None:
    """A doc that lives outside repo_root must be `is_external=True`."""
    repo = tmp_path / "repo"
    external = tmp_path / "external-docs"
    repo.mkdir()
    external.mkdir()
    _write_doc(external / "ext.md", "# External\n\nMentions `App`.\n")

    catalog = build_doc_catalog(
        [external / "ext.md"],
        repo_root=repo,
        symbol_names=frozenset({"App"}),
        file_paths=frozenset(),
        newest_code_mtime=None,
        extra_doc_roots=(external,),
    )
    assert len(catalog.docs) == 1
    entry = catalog.docs[0]
    assert entry.is_external is True
    assert str(external.resolve()) in entry.source_root
    # External docs hold their absolute path because they have no
    # relative repo-root anchor.
    assert entry.path == str((external / "ext.md").resolve())


# ---------------------------------------------------------------------------
# End-to-end via build_all
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_build_all_writes_source_docs_catalog(
    sample_repo: Path, tmp_path: Path
) -> None:
    """Running ingest on a repo with README.md emits source-docs/INDEX.{json,md}."""
    (sample_repo / "README.md").write_text(
        "# Sample\n\nIntroduces `App.run()` which calls `make_app()`.\n",
        encoding="utf-8",
    )
    result = build_all(sample_repo, cache_root=tmp_path / "cache")

    assert "source-docs/INDEX.json" in result.written
    assert "source-docs/INDEX.md" in result.written
    catalog_json = result.context_dir / "source-docs" / "INDEX.json"
    payload = json.loads(catalog_json.read_text(encoding="utf-8"))
    paths_in_catalog = {d["path"] for d in payload["docs"]}
    assert "README.md" in paths_in_catalog


@pytest.mark.integration
def test_build_all_with_external_docs_root(
    sample_repo: Path, tmp_path: Path
) -> None:
    """--docs PATH (outside the repo) lands in the catalog as external."""
    external = tmp_path / "external"
    external.mkdir()
    (external / "design.md").write_text(
        "# Design\n\nDescribes `App` plus `unknown_symbol`.\n",
        encoding="utf-8",
    )
    result = build_all(
        sample_repo,
        cache_root=tmp_path / "cache",
        extra_doc_roots=[external],
    )
    catalog = result.doc_catalog
    assert catalog is not None
    paths = [d.path for d in catalog.docs]
    abs_design = str((external / "design.md").resolve())
    assert abs_design in paths
    external_entry = next(d for d in catalog.docs if d.path == abs_design)
    assert external_entry.is_external is True


@pytest.mark.integration
def test_manifest_includes_doc_files(
    sample_repo: Path, tmp_path: Path
) -> None:
    """A doc edit must surface in the drift manifest so rebuild --changed re-runs."""
    (sample_repo / "README.md").write_text(
        "# Sample\n\nuses `App`.\n", encoding="utf-8"
    )
    build_all(sample_repo, cache_root=tmp_path / "cache")
    manifest_path = sample_repo / ".context" / "cache" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "README.md" in manifest["files"], (
        f"manifest didn't catch README.md; saw: {list(manifest['files'])}"
    )


@pytest.mark.integration
def test_project_md_mentions_doc_catalog_when_docs_exist(
    sample_repo: Path, tmp_path: Path
) -> None:
    (sample_repo / "README.md").write_text(
        "# Sample\n\nIntroduces `App`.\n", encoding="utf-8"
    )
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    project_md = (result.context_dir / "PROJECT.md").read_text(encoding="utf-8")
    assert "Existing documentation" in project_md
    assert "confidence" in project_md.lower()


@pytest.mark.integration
def test_doc_referencing_other_doc_files_stays_high_confidence(
    sample_repo: Path, tmp_path: Path
) -> None:
    """A meta doc (README references CHANGELOG; CHANGELOG references README)
    must not be flagged stale. Both files exist in the repo; the
    widened file-path set picks them up.
    """
    (sample_repo / "README.md").write_text(
        "# Sample\n\nSee `CHANGELOG.md` for history. Uses `App.run()`.\n",
        encoding="utf-8",
    )
    (sample_repo / "CHANGELOG.md").write_text(
        "# Changelog\n\nSee `README.md` for setup.\n",
        encoding="utf-8",
    )
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    catalog = result.doc_catalog
    assert catalog is not None
    by_path = {d.path: d for d in catalog.docs}
    assert by_path["README.md"].confidence in (DocConfidence.HIGH, DocConfidence.MEDIUM)
    assert by_path["CHANGELOG.md"].confidence in (DocConfidence.HIGH, DocConfidence.MEDIUM)
    assert "CHANGELOG.md" not in by_path["README.md"].broken_refs
    assert "README.md" not in by_path["CHANGELOG.md"].broken_refs


@pytest.mark.integration
def test_feature_docs_caps_at_top_n(
    sample_repo: Path, tmp_path: Path
) -> None:
    """When a feature is mentioned in >10 docs, docs.md shows the top
    10 + an overflow pointer back to source-docs/INDEX.md."""
    # Spread 15 docs that all reference `App` so they all link to the
    # same community.
    for i in range(15):
        (sample_repo / f"DOC_{i:02d}.md").write_text(
            f"# Doc {i}\n\nMentions `App.run()` and `make_app()`.\n",
            encoding="utf-8",
        )
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    features_dir = result.context_dir / "features"
    feature_docs = list(features_dir.glob("*/docs.md"))
    assert feature_docs, "expected at least one features/<id>/docs.md"
    # At least one feature should have hit the cap.
    capped = [
        p for p in feature_docs
        if "more in" in p.read_text(encoding="utf-8")
    ]
    assert capped, (
        "docs.md never showed an overflow pointer — cap logic isn't firing"
    )


@pytest.mark.integration
def test_doc_edit_triggers_rebuild_changed(
    sample_repo: Path, tmp_path: Path
) -> None:
    """A README.md edit must cause rebuild --changed to actually rebuild,
    not skip with 'no source files changed'. The catalog's staleness
    signals depend on doc content — a stale catalog defeats the point.
    """
    from dummyindex.context.build.incremental import rebuild_changed

    (sample_repo / "README.md").write_text(
        "# Sample\n\nIntroduces `App`.\n", encoding="utf-8"
    )
    build_all(sample_repo, cache_root=tmp_path / "cache")

    # Touch the doc — append meaningful new content so the SHA changes.
    readme = sample_repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n## Update\n\nNew section.\n",
        encoding="utf-8",
    )

    result = rebuild_changed(sample_repo, cache_root=tmp_path / "cache2")
    assert result.skipped is False, "doc edit should have triggered rebuild"
    assert "README.md" in result.changes.modified


@pytest.mark.integration
def test_feature_docs_md_link_resolves_to_actual_file(
    sample_repo: Path, tmp_path: Path
) -> None:
    """Regression test: links inside features/<id>/docs.md must point at
    files that actually exist relative to that file's location.

    The catalog markdown lives 3 levels deep in .context/features/<id>/
    so every link needs three "../" hops to escape back to the repo
    root. An off-by-one here would land the link inside .context/.
    """
    (sample_repo / "README.md").write_text(
        "# Sample\n\nThe `App.run()` lives in `app.py`.\n",
        encoding="utf-8",
    )
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    features_dir = result.context_dir / "features"
    assert features_dir.exists()

    found_any = False
    import re
    link_re = re.compile(r"\[`[^`]+`\]\(([^)]+)\)")
    for feat_docs_md in features_dir.glob("*/docs.md"):
        found_any = True
        text = feat_docs_md.read_text(encoding="utf-8")
        for match in link_re.finditer(text):
            target = match.group(1)
            if target.startswith("/"):
                # External absolute path — skip relative-resolution check.
                continue
            resolved = (feat_docs_md.parent / target).resolve()
            assert resolved.exists(), (
                f"link {target!r} from {feat_docs_md} resolves to "
                f"{resolved} which does not exist"
            )
    assert found_any, "expected at least one features/<id>/docs.md to exist"


@pytest.mark.integration
def test_low_confidence_doc_renders_broken_refs_in_md(
    sample_repo: Path, tmp_path: Path
) -> None:
    """The human-readable catalog lists broken refs for low-confidence docs."""
    (sample_repo / "STALE.md").write_text(
        (
            "# Architecture\n\n"
            "Built on `ExtinctClass`, `gone_function()`, and "
            "`legacy_path.py`, plus `also_dead_helper`.\n"
        ),
        encoding="utf-8",
    )
    result = build_all(sample_repo, cache_root=tmp_path / "cache")
    md = (result.context_dir / "source-docs" / "INDEX.md").read_text(encoding="utf-8")
    assert "STALE.md" in md
    assert "low" in md.lower()
    assert "Broken references" in md or "broken refs" in md.lower()
