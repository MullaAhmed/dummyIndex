"""Generated `.context/` docs and scaffolds pass the STE strict lint."""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.build.conventions import (
    NamingRule,
    NamingRules,
    write_naming_md,
)
from dummyindex.context.build.maps import (
    FileEntry,
    FilesMap,
    SymbolEntry,
    SymbolsMap,
)
from dummyindex.context.build.meta import SCHEMA_VERSION, Meta
from dummyindex.context.domains.audit import ensure_audit
from dummyindex.context.domains.config import CouncilMode, ModelChoice
from dummyindex.context.domains.docbudget.style import lint_text
from dummyindex.context.domains.proposals import ensure_proposal
from dummyindex.context.output.docs import generate_index_md
from dummyindex.context.output.instructions import (
    PLAYBOOK_IDS,
    write_architecture_overview_md,
    write_how_to_use_md,
    write_playbook_md,
)


def _strict_violations(text: str) -> list[str]:
    return [
        f"line {v.line} {v.rule}: {v.excerpt!r}"
        for v in lint_text(text)
        if v.severity == "strict"
    ]


def _assert_clean(path: Path) -> None:
    violations = _strict_violations(path.read_text(encoding="utf-8"))
    assert violations == [], f"{path.name}: {violations}"


def _meta(root: Path) -> Meta:
    return Meta(
        schema_version=SCHEMA_VERSION,
        dummyindex_version="0.0.0-test",
        created_at="2026-05-24T00:00:00+00:00",
        updated_at="2026-05-24T00:00:00+00:00",
        root=str(root.resolve()),
        languages=("python",),
        file_count=3,
        symbol_count=2,
    )


@pytest.mark.unit
def test_how_to_use_renders_strict_clean(tmp_path: Path) -> None:
    path = tmp_path / ".context" / "HOW_TO_USE.md"
    write_how_to_use_md(path)
    _assert_clean(path)


@pytest.mark.unit
def test_architecture_overview_renders_strict_clean(tmp_path: Path) -> None:
    repo = tmp_path / "demo"
    repo.mkdir()
    files = FilesMap(
        schema_version=1,
        files=(
            FileEntry(
                path="src/app.py", language="python", size_bytes=1, sha256="a" * 64
            ),
            FileEntry(
                path="tests/test_app.py",
                language="python",
                size_bytes=1,
                sha256="b" * 64,
            ),
            FileEntry(path="README.md", language=None, size_bytes=1, sha256="c" * 64),
        ),
    )
    symbols = SymbolsMap(
        schema_version=1,
        symbols=(
            SymbolEntry(symbol_id="s1", kind="class", name="App", path="src/app.py"),
            SymbolEntry(symbol_id="s2", kind="function", name="run", path="src/app.py"),
        ),
    )
    path = tmp_path / ".context" / "architecture" / "overview.md"
    write_architecture_overview_md(path, repo, files, symbols, _meta(repo))
    _assert_clean(path)


@pytest.mark.unit
@pytest.mark.parametrize("playbook_id", PLAYBOOK_IDS)
def test_every_playbook_renders_strict_clean(tmp_path: Path, playbook_id: str) -> None:
    path = tmp_path / ".context" / "playbooks" / f"{playbook_id}.md"
    write_playbook_md(path, playbook_id)
    _assert_clean(path)


@pytest.mark.unit
def test_index_md_renders_strict_clean(tmp_path: Path) -> None:
    path = tmp_path / ".context" / "INDEX.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        generate_index_md(["HOW_TO_USE.md", "PROJECT.md", "architecture/overview.md"]),
        encoding="utf-8",
    )
    _assert_clean(path)


@pytest.mark.unit
def test_naming_md_renders_strict_clean(tmp_path: Path) -> None:
    rules = NamingRules(
        schema_version=1,
        rules=(
            NamingRule(
                language="python",
                kind="function",
                casing="snake_case",
                evidence_count=9,
                total_observed=10,
                confidence=0.9,
                exceptions=("main",),
            ),
        ),
    )
    path = tmp_path / ".context" / "conventions" / "naming.md"
    write_naming_md(path, rules, generated_at="2026-05-24")
    _assert_clean(path)


@pytest.mark.integration
def test_proposal_scaffolds_render_strict_clean(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    written = ensure_proposal(context_dir, "demo", "Add export")
    for rel in written:
        if rel.endswith(".md"):
            _assert_clean(context_dir / rel)


@pytest.mark.integration
def test_audit_scaffolds_render_strict_clean(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    personas = tmp_path / "personas"
    personas.mkdir()
    (personas / "security.md").write_text(
        "---\nname: Sec\nsubagent_type: Security Engineer\ndescription: sec\n---\n",
        encoding="utf-8",
    )
    start = ensure_audit(
        context_dir,
        description="Audit error handling in the CLI dispatcher",
        mode=CouncilMode.STANDARD,
        model=ModelChoice.OPUS,
        scope=("dummyindex/cli",),
        personas_dir=personas,
    )
    target = context_dir / "audits" / start.slug
    md_files = sorted(target.rglob("*.md"))
    assert md_files, "audit scaffold wrote no markdown"
    for path in md_files:
        _assert_clean(path)
