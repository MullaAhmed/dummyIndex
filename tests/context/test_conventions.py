"""Tests for dummyindex.context.conventions."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dummyindex.context.conventions import (
    CONVENTION_SECTIONS,
    SCHEMA_VERSION,
    ConventionSectionError,
    NamingRule,
    NamingRules,
    analyze_naming,
    classify_casing,
    write_convention_section,
    write_naming_json,
    write_naming_md,
)
from dummyindex.context.maps import (
    FileEntry,
    FilesMap,
    SymbolEntry,
    SymbolsMap,
    build_maps,
)

_FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_repo"


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "sample_repo"
    shutil.copytree(_FIXTURE_ROOT, dest)
    return dest


# --- Casing classifier --------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "name, expected",
    [
        ("MyClass", "PascalCase"),
        ("PaymentRepo", "PascalCase"),
        ("myFunction", "camelCase"),
        ("startWebApp", "camelCase"),
        ("snake_case_name", "snake_case"),
        ("format_currency", "snake_case"),
        ("MAX_VALUE", "SCREAMING_SNAKE"),
        ("API_KEY", "SCREAMING_SNAKE"),
        ("kebab-case-name", "kebab-case"),
        ("lowercase", "lowercase"),
        ("index", "lowercase"),
        ("_private_helper", "snake_case"),
        ("__init", "lowercase"),
        ("__init__", "snake_case"),
        ("", "unknown"),
        ("UPPER", "SCREAMING_SNAKE"),
        ("Mixed_Case_Thing", "mixed"),
    ],
)
def test_classify_casing(name: str, expected: str) -> None:
    assert classify_casing(name) == expected


# --- analyze_naming on the fixture -------------------------------------------


@pytest.mark.integration
def test_analyze_naming_returns_rules(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    rules = analyze_naming(files_map, symbols_map)
    assert isinstance(rules, NamingRules)
    assert rules.schema_version == SCHEMA_VERSION
    assert rules.rules


@pytest.mark.integration
def test_python_function_is_snake_case(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    rules = analyze_naming(files_map, symbols_map)
    matching = [
        r for r in rules.rules if r.language == "python" and r.kind == "function"
    ]
    assert matching, "expected a python/function rule"
    assert matching[0].casing == "snake_case"
    assert matching[0].confidence >= 0.80


@pytest.mark.integration
def test_python_class_is_pascalcase(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    rules = analyze_naming(files_map, symbols_map)
    matching = [
        r for r in rules.rules if r.language == "python" and r.kind == "class"
    ]
    assert matching, "expected a python/class rule"
    assert matching[0].casing == "PascalCase"


@pytest.mark.integration
def test_typescript_class_is_pascalcase(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    rules = analyze_naming(files_map, symbols_map)
    matching = [
        r for r in rules.rules if r.language == "typescript" and r.kind == "class"
    ]
    assert matching, "expected a typescript/class rule"
    assert matching[0].casing == "PascalCase"


@pytest.mark.integration
def test_typescript_function_is_camelcase(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    rules = analyze_naming(files_map, symbols_map)
    matching = [
        r for r in rules.rules
        if r.language == "typescript" and r.kind == "function"
    ]
    assert matching, "expected a typescript/function rule"
    assert matching[0].casing == "camelCase"


@pytest.mark.integration
def test_dunders_are_ignored(sample_repo: Path, tmp_path: Path) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    rules = analyze_naming(files_map, symbols_map)
    py_methods = [
        r for r in rules.rules if r.language == "python" and r.kind == "method"
    ]
    if py_methods:
        for exc in py_methods[0].exceptions:
            assert not (exc.startswith("__") and exc.endswith("__"))


@pytest.mark.integration
def test_below_threshold_yields_no_rule() -> None:
    # Half PascalCase, half camelCase, n=4, no style ≥80% → no rule.
    files = FilesMap(
        schema_version=SCHEMA_VERSION,
        files=(
            FileEntry(
                path="x.py", language="python", size_bytes=1, sha256="0" * 64
            ),
        ),
    )
    symbols = SymbolsMap(
        schema_version=SCHEMA_VERSION,
        symbols=tuple(
            SymbolEntry(symbol_id=f"s{i}", kind="class", name=name, path="x.py")
            for i, name in enumerate(["Foo", "Bar", "doThing", "moreStuff"])
        ),
    )
    rules = analyze_naming(files, symbols)
    matching = [
        r for r in rules.rules if r.language == "python" and r.kind == "class"
    ]
    assert not matching


@pytest.mark.integration
def test_threshold_exception_listing() -> None:
    files = FilesMap(
        schema_version=SCHEMA_VERSION,
        files=(
            FileEntry(
                path="x.py", language="python", size_bytes=1, sha256="0" * 64
            ),
        ),
    )
    # 4 PascalCase + 1 snake_case = 80% conformance — exactly threshold → rule emitted
    symbols = SymbolsMap(
        schema_version=SCHEMA_VERSION,
        symbols=tuple(
            SymbolEntry(symbol_id=f"s{i}", kind="class", name=name, path="x.py")
            for i, name in enumerate(["Foo", "Bar", "Baz", "Qux", "weird_one"])
        ),
    )
    rules = analyze_naming(files, symbols)
    rule = next(
        r for r in rules.rules if r.language == "python" and r.kind == "class"
    )
    assert rule.casing == "PascalCase"
    assert "weird_one" in rule.exceptions


# --- Writers -----------------------------------------------------------------


@pytest.mark.integration
def test_write_naming_json_roundtrip(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    rules = analyze_naming(files_map, symbols_map)
    out = tmp_path / ".context" / "conventions" / "naming.json"
    write_naming_json(out, rules)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert len(payload["rules"]) == len(rules.rules)


@pytest.mark.integration
def test_write_naming_md_contains_rule_names(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    rules = analyze_naming(files_map, symbols_map)
    out = tmp_path / ".context" / "conventions" / "naming.md"
    write_naming_md(out, rules, generated_at="2026-05-24T00:00:00Z")
    text = out.read_text(encoding="utf-8")
    assert "# Naming conventions" in text
    assert "python" in text or "typescript" in text
    if any(r.language == "python" and r.kind == "function" for r in rules.rules):
        assert "snake_case" in text
    if any(r.language == "typescript" and r.kind == "function" for r in rules.rules):
        assert "camelCase" in text


@pytest.mark.integration
def test_write_naming_md_empty_rules(tmp_path: Path) -> None:
    out = tmp_path / "naming.md"
    write_naming_md(out, NamingRules(schema_version=SCHEMA_VERSION, rules=()))
    text = out.read_text(encoding="utf-8")
    assert "No conventions inferred" in text


@pytest.mark.integration
def test_writers_atomic_no_tmp_remains(
    sample_repo: Path, tmp_path: Path
) -> None:
    files_map, symbols_map = build_maps(sample_repo, cache_root=tmp_path / "cache")
    rules = analyze_naming(files_map, symbols_map)
    json_out = tmp_path / "naming.json"
    md_out = tmp_path / "naming.md"
    write_naming_json(json_out, rules)
    write_naming_md(md_out, rules)
    assert not list(tmp_path.glob("*.tmp"))


# --- Agent-derived convention sections --------------------------------------


@pytest.mark.unit
def test_convention_sections_catalog_covers_required_docs() -> None:
    """The conventions catalog is the source of truth for the council prompts.

    These four sections must exist; if one is renamed the corresponding
    council/15-conventions.md prompt has to be updated too."""
    assert "folder-organization" in CONVENTION_SECTIONS
    assert "coding-practices" in CONVENTION_SECTIONS
    assert "testing" in CONVENTION_SECTIONS
    assert "data-access" in CONVENTION_SECTIONS


@pytest.mark.integration
def test_write_convention_section_writes_to_conventions_dir(
    tmp_path: Path,
) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    source = tmp_path / "src.md"
    source.write_text("# Folder organization\n\nBody.\n", encoding="utf-8")

    written = write_convention_section(
        context_dir,
        section="folder-organization",
        source_file=source,
    )

    expected = context_dir / "conventions" / "folder-organization.md"
    assert written == expected
    assert expected.read_text(encoding="utf-8") == "# Folder organization\n\nBody.\n"


@pytest.mark.unit
def test_write_convention_section_rejects_unknown_section(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    source = tmp_path / "x.md"
    source.write_text("body", encoding="utf-8")

    with pytest.raises(ConventionSectionError, match="unknown convention section"):
        write_convention_section(
            context_dir, section="naming", source_file=source
        )


@pytest.mark.unit
def test_write_convention_section_rejects_missing_source(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    with pytest.raises(ConventionSectionError, match="source file not found"):
        write_convention_section(
            context_dir,
            section="testing",
            source_file=tmp_path / "missing.md",
        )


@pytest.mark.integration
def test_write_convention_section_is_atomic(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    context_dir.mkdir()
    source = tmp_path / "src.md"
    source.write_text("first version", encoding="utf-8")
    write_convention_section(
        context_dir, section="coding-practices", source_file=source
    )

    source.write_text("second version", encoding="utf-8")
    out = write_convention_section(
        context_dir, section="coding-practices", source_file=source
    )

    assert out.read_text(encoding="utf-8") == "second version"
    assert not list((context_dir / "conventions").glob("*.tmp"))
