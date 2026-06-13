"""Output hygiene: generated `.context/` trees must be pre-commit-clean.

Consumer repos run standard pre-commit hooks (end-of-file-fixer,
trailing-whitespace, detect-secrets) over the committed `.context/` tree.
These tests pin three invariants:

1. every generated text file ends with exactly one newline and has no
   trailing whitespace (the whole-tree walk catches future writer
   regressions, not just today's offenders);
2. the heavy machine-layer artefacts get a managed `.gitattributes`
   marking them ``linguist-generated`` (they stay *committed* — a fresh
   clone must navigate the index without the CLI — but GitHub folds
   their generated diffs out of PR review);
3. the legacy pre-0.21 root-level ``_enrich_plan.json`` scratch file is
   cleaned up on the next build.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterator

import pytest

from tests.paths import SAMPLE_REPO

from dummyindex.context.build.runner import (
    _MANAGED_GITATTRIBUTES_RULES,
    build_all,
    ensure_context_gitattributes,
    ensure_context_gitignore,
    remove_legacy_enrich_plan,
)

# Top-level .context/ entries covered by the managed .gitignore — local
# scratch, never committed, so pre-commit hooks never see them.
_GITIGNORED_TOP_LEVEL = frozenset({"cache", "_doc_backups"})


@pytest.fixture(scope="module")
def built_context(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One shared full build — the walk tests are read-only."""
    tmp = tmp_path_factory.mktemp("hygiene")
    repo = tmp / "repo"
    shutil.copytree(SAMPLE_REPO, repo)
    build_all(repo, dummyindex_version="0.0.0-test", cache_root=tmp / "cache")
    return repo / ".context"


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(SAMPLE_REPO, dest)
    return dest


def _generated_text_files(context_dir: Path) -> Iterator[tuple[str, str]]:
    for path in sorted(context_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(context_dir)
        if rel.parts[0] in _GITIGNORED_TOP_LEVEL:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary artefact — not pre-commit's concern
        yield rel.as_posix(), text


# ----- invariant: every committed artefact is pre-commit-clean ---------------


@pytest.mark.integration
def test_every_generated_file_ends_with_exactly_one_newline(
    built_context: Path,
) -> None:
    offenders = [
        rel
        for rel, text in _generated_text_files(built_context)
        if text and (not text.endswith("\n") or text.endswith("\n\n"))
    ]
    assert not offenders, (
        f"end-of-file-fixer would rewrite these generated files: {offenders}"
    )


@pytest.mark.integration
def test_no_generated_file_has_trailing_whitespace(built_context: Path) -> None:
    offenders = [
        f"{rel}:{i}"
        for rel, text in _generated_text_files(built_context)
        for i, line in enumerate(text.splitlines(), 1)
        if line != line.rstrip()
    ]
    assert not offenders, (
        f"trailing-whitespace hook would rewrite: {offenders[:10]}"
    )


@pytest.mark.integration
def test_symbol_graph_json_ends_with_newline(built_context: Path) -> None:
    """Regression pin: the one writer that bypassed `+ \"\\n\"` at v0.25.0."""
    text = (built_context / "features" / "symbol-graph.json").read_text(
        encoding="utf-8"
    )
    assert text.endswith("\n") and not text.endswith("\n\n")


# ----- managed .gitattributes -------------------------------------------------


@pytest.mark.unit
def test_fresh_gitattributes_contains_every_managed_rule(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    ensure_context_gitattributes(ctx)
    lines = {
        ln.strip()
        for ln in (ctx / ".gitattributes").read_text(encoding="utf-8").splitlines()
    }
    assert all(rule in lines for rule in _MANAGED_GITATTRIBUTES_RULES)
    # The machine layer is folded, never local-diff-suppressed: no `-diff`
    # (it would hide merge conflicts in working trees).
    assert not any("-diff" in rule for rule in _MANAGED_GITATTRIBUTES_RULES)


@pytest.mark.unit
def test_gitattributes_merge_preserves_user_lines(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True)
    (ctx / ".gitattributes").write_text(
        "tree.json linguist-generated\nmy-export.csv -diff\n", encoding="utf-8"
    )
    ensure_context_gitattributes(ctx)
    text = (ctx / ".gitattributes").read_text(encoding="utf-8")
    lines = {ln.strip() for ln in text.splitlines()}
    assert "my-export.csv -diff" in lines
    assert all(rule in lines for rule in _MANAGED_GITATTRIBUTES_RULES)
    # No duplicate of the already-present managed rule.
    stripped = [ln.strip() for ln in text.splitlines()]
    assert stripped.count("tree.json linguist-generated") == 1


@pytest.mark.unit
def test_ensure_context_gitattributes_is_idempotent(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    ensure_context_gitattributes(ctx)
    first = (ctx / ".gitattributes").read_text(encoding="utf-8")
    ensure_context_gitattributes(ctx)
    assert (ctx / ".gitattributes").read_text(encoding="utf-8") == first


@pytest.mark.integration
def test_build_all_writes_managed_gitattributes(built_context: Path) -> None:
    ga = built_context / ".gitattributes"
    assert ga.exists()
    lines = {ln.strip() for ln in ga.read_text(encoding="utf-8").splitlines()}
    assert "features/symbol-graph.json linguist-generated" in lines


# ----- legacy scratch cleanup --------------------------------------------------


@pytest.mark.unit
def test_remove_legacy_enrich_plan_unlinks_root_copy_only(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    (ctx / "cache").mkdir(parents=True)
    (ctx / "_enrich_plan.json").write_text("{}", encoding="utf-8")
    (ctx / "cache" / "_enrich_plan.json").write_text('{"keep": true}', encoding="utf-8")

    assert remove_legacy_enrich_plan(ctx) is True
    assert not (ctx / "_enrich_plan.json").exists()
    # The current (gitignored) cache copy is untouched.
    assert (ctx / "cache" / "_enrich_plan.json").read_text(
        encoding="utf-8"
    ) == '{"keep": true}'
    # Second call: nothing left to do.
    assert remove_legacy_enrich_plan(ctx) is False


@pytest.mark.integration
def test_build_all_removes_legacy_root_enrich_plan(
    sample_repo: Path, tmp_path: Path
) -> None:
    ctx = sample_repo / ".context"
    ctx.mkdir(parents=True)
    (ctx / "_enrich_plan.json").write_text("{}", encoding="utf-8")

    build_all(sample_repo, dummyindex_version="0.0.0-test", cache_root=tmp_path / "c")

    assert not (ctx / "_enrich_plan.json").exists()


# ----- public gitignore helper (reconcile-only repos import this) -------------


@pytest.mark.unit
def test_ensure_context_gitignore_is_public(tmp_path: Path) -> None:
    """Non-build verbs (enrich-plan, …) upgrade old trees via the public name."""
    ctx = tmp_path / ".context"
    ensure_context_gitignore(ctx)
    assert "_enrich_plan.json" in (ctx / ".gitignore").read_text(encoding="utf-8")
