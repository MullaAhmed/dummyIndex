"""Context-layout migration: retired paths, managed rules, cache scope.

The nine suites under ``tests/fixtures/retired_equipment_evals/`` are the
starter suites this repo committed under 0.37, copied verbatim (LF, as stored
in git) with::

    git show v0.37.0:.context/equipment-evals/<name>.suite.json

The directory's ``.gitattributes`` (``* -text``) keeps checkouts byte-exact;
the tests still derive both line-ending variants from the bytes themselves.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dummyindex.context.build import runner, upgrade
from dummyindex.context.build.upgrade import (
    LayoutMigration,
    _is_starter_suite,
    ensure_context_gitignore,
    migrate_context_layout,
    retire_paths,
)
from dummyindex.context.domains import atomic_io
from dummyindex.context.domains.atomic_io import is_link
from tests.paths import FIXTURES_DIR

pytestmark = pytest.mark.unit

_FIXTURES = FIXTURES_DIR / "retired_equipment_evals"
_FIXTURE_NAMES = sorted(p.name for p in _FIXTURES.glob("*.suite.json"))
_EVAL_BACKUPS = "_doc_backups/retired/0.37.0/equipment-evals"
_HASH_ENTRY = "ab" * 32 + ".json"


def _lf(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes().replace(b"\r\n", b"\n")


def _variant(data: bytes, endings: str) -> bytes:
    return data.replace(b"\n", b"\r\n") if endings == "crlf" else data


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _link_dir(link: Path, target: Path, kind: str = "any") -> None:
    """Create a directory symlink or (Windows) junction at ``link``."""
    if kind in ("any", "symlink"):
        try:
            link.symlink_to(target, target_is_directory=True)
            return
        except OSError:
            if kind == "symlink" or os.name != "nt":
                pytest.skip("symlink creation unavailable on this host")
    if os.name != "nt":
        pytest.skip("junctions exist only on Windows")
    import _winapi  # Windows-only; junctions need no symlink privilege.

    _winapi.CreateJunction(str(target), str(link))


def _edit_json(data: bytes, mutate) -> bytes:
    payload = json.loads(data)
    mutate(payload)
    return (json.dumps(payload, indent=2) + "\n").encode()


def _one_char_prompt_edit(data: bytes) -> bytes:
    edited = data.replace(b"unrelated", b"unrelatee", 1)
    assert edited != data
    return edited


def _extra_case(data: bytes) -> bytes:
    return _edit_json(
        data,
        lambda p: p["cases"].append(
            {"case_id": "mine", "prompt": "a real prompt", "expects_trigger": True}
        ),
    )


def _extra_key(data: bytes) -> bytes:
    return _edit_json(data, lambda p: p.update(notes="hand-authored"))


def _flipped_expects_trigger(data: bytes) -> bytes:
    return _edit_json(data, lambda p: p["cases"][-1].update(expects_trigger=True))


_EDITS = {
    "one-char-prompt-edit": _one_char_prompt_edit,
    "extra-case": _extra_case,
    "extra-key": _extra_key,
    "flipped-expects-trigger": _flipped_expects_trigger,
    "bom": lambda data: b"\xef\xbb\xbf" + data,
    "non-json": lambda data: b"not json {\n",
}


def test_fixture_set_is_the_nine_committed_suites() -> None:
    assert len(_FIXTURE_NAMES) == 9
    for name in _FIXTURE_NAMES:
        assert b"\r" not in _lf(name)


@pytest.mark.parametrize("endings", ["lf", "crlf"])
@pytest.mark.parametrize("name", _FIXTURE_NAMES)
def test_committed_starter_suite_is_deleted_without_backup(
    tmp_path: Path, name: str, endings: str
) -> None:
    ctx = tmp_path / ".context"
    suite = _write(ctx / "equipment-evals" / name, _variant(_lf(name), endings))

    assert _is_starter_suite(suite) is True
    removed, backed_up, errors = retire_paths(ctx)

    assert removed == (f"equipment-evals/{name}",)
    assert backed_up == ()
    assert errors == ()
    assert not (ctx / "equipment-evals").exists()
    assert not (ctx / "_doc_backups").exists()


@pytest.mark.parametrize("edit", sorted(_EDITS))
@pytest.mark.parametrize(
    "name", ["python-tester.suite.json", "dummyindex-verify.suite.json"]
)
def test_edited_suite_is_backed_up_byte_identical_then_deleted(
    tmp_path: Path, name: str, edit: str
) -> None:
    ctx = tmp_path / ".context"
    data = _EDITS[edit](_lf(name))
    suite = _write(ctx / "equipment-evals" / name, data)

    assert _is_starter_suite(suite) is False
    removed, backed_up, errors = retire_paths(ctx)

    assert errors == ()
    assert removed == (f"equipment-evals/{name}",)
    assert backed_up == (f"{_EVAL_BACKUPS}/{name}",)
    assert (ctx / backed_up[0]).read_bytes() == data
    assert not (ctx / "equipment-evals").exists()


def test_result_file_is_backed_up_even_with_starter_bytes(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    data = _lf("python-tester.suite.json")
    result = _write(ctx / "equipment-evals" / "python-tester.result.json", data)

    assert _is_starter_suite(result) is False
    removed, backed_up, errors = retire_paths(ctx)

    assert (removed, errors) == (("equipment-evals/python-tester.result.json",), ())
    assert backed_up == (f"{_EVAL_BACKUPS}/python-tester.result.json",)
    assert (ctx / backed_up[0]).read_bytes() == data


def test_py310_enum_rendering_and_generic_positive_are_starters(
    tmp_path: Path,
) -> None:
    # py3.10 formats a (str, Enum) member as its value in the case id while
    # `!r` still renders the member.
    py310 = _lf("python-tester.suite.json").replace(
        b'"Capability.TEST-positive"', b'"test-positive"'
    )
    generic = (
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "positive",
                        "prompt": "<replace: a synthetic prompt that SHOULD "
                        "trigger the bare-tool tool>",
                        "expects_trigger": True,
                    },
                    {
                        "case_id": "decoy-negative",
                        "prompt": "<replace: an unrelated prompt that should "
                        "NOT trigger this tool>",
                        "expects_trigger": False,
                    },
                ]
            },
            indent=2,
        )
        + "\n"
    ).encode()
    unknown_member = _lf("python-tester.suite.json").replace(
        b"Capability.TEST", b"Capability.NOPE"
    )

    assert _is_starter_suite(_write(tmp_path / "python-tester.suite.json", py310))
    assert _is_starter_suite(_write(tmp_path / "bare-tool.suite.json", generic))
    assert not _is_starter_suite(_write(tmp_path / "other.suite.json", generic))
    assert not _is_starter_suite(
        _write(tmp_path / "x" / "python-tester.suite.json", unknown_member)
    )
    assert not _is_starter_suite(tmp_path / "missing.suite.json")
    (tmp_path / "dir.suite.json").mkdir()
    assert not _is_starter_suite(tmp_path / "dir.suite.json")


def test_nested_tree_is_emptied_bottom_up_and_second_run_is_noop(
    tmp_path: Path,
) -> None:
    ctx = tmp_path / ".context"
    evals = ctx / "equipment-evals"
    for name in _FIXTURE_NAMES[:2]:
        _write(evals / name, _lf(name))
    nested = _write(evals / "runs" / "deep" / "a.benchmark.json", b'{"runs": []}\n')
    (evals / "empty" / "inner").mkdir(parents=True)

    removed, backed_up, errors = retire_paths(ctx)

    assert errors == ()
    assert backed_up == (f"{_EVAL_BACKUPS}/runs/deep/a.benchmark.json",)
    assert set(removed) == {
        *(f"equipment-evals/{n}" for n in _FIXTURE_NAMES[:2]),
        "equipment-evals/runs/deep/a.benchmark.json",
    }
    assert not nested.exists()
    assert not evals.exists()
    assert retire_paths(ctx) == ((), (), ())


def test_existing_backup_is_reused_or_never_overwritten(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    first = _write(ctx / _EVAL_BACKUPS / "x.result.json", b"first\n")
    _write(ctx / "equipment-evals" / "x.result.json", b"second\n")
    _write(ctx / "equipment-evals" / "y.result.json", b"same\n")
    _write(ctx / _EVAL_BACKUPS / "y.result.json", b"same\n")

    removed, backed_up, errors = retire_paths(ctx)

    assert errors == ()
    assert len(removed) == 2
    assert backed_up == (
        f"{_EVAL_BACKUPS}/x.result.1.json",
        f"{_EVAL_BACKUPS}/y.result.json",
    )
    assert first.read_bytes() == b"first\n"
    assert (ctx / backed_up[0]).read_bytes() == b"second\n"


@pytest.mark.parametrize("kind", ["symlink", "junction"])
def test_linked_root_is_unlinked_and_target_untouched(
    tmp_path: Path, kind: str
) -> None:
    outside = tmp_path / "outside"
    starter = _write(
        outside / "python-tester.suite.json", _lf("python-tester.suite.json")
    )
    notes = _write(outside / "notes.txt", b"keep me\n")
    ctx = tmp_path / ".context"
    ctx.mkdir()
    _link_dir(ctx / "equipment-evals", outside, kind)

    removed, backed_up, errors = retire_paths(ctx)

    assert (removed, backed_up, errors) == (("equipment-evals",), (), ())
    assert not os.path.lexists(ctx / "equipment-evals")
    assert starter.read_bytes() == _lf("python-tester.suite.json")
    assert notes.read_bytes() == b"keep me\n"
    assert not (ctx / "_doc_backups").exists()


def test_link_inside_retired_dir_is_unlinked_as_entry(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    secret = _write(outside / "secret.result.json", b"outside\n")
    ctx = tmp_path / ".context"
    evals = ctx / "equipment-evals"
    evals.mkdir(parents=True)
    _link_dir(evals / "linked", outside)

    removed, backed_up, errors = retire_paths(ctx)

    assert (removed, backed_up, errors) == (("equipment-evals/linked",), (), ())
    assert not evals.exists()
    assert secret.read_bytes() == b"outside\n"


def test_linked_backup_root_is_refused_and_file_kept(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    ctx = tmp_path / ".context"
    edited = _write(ctx / "equipment-evals" / "x.result.json", b"mine\n")
    _link_dir(ctx / "_doc_backups", outside)

    removed, backed_up, errors = retire_paths(ctx)

    assert (removed, backed_up) == ((), ())
    assert len(errors) == 1
    assert errors[0].startswith("equipment-evals/x.result.json: backup failed")
    assert edited.read_bytes() == b"mine\n"
    assert list(outside.iterdir()) == []


def test_legacy_graph_dir_is_backed_up_and_removed(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    graph = _write(ctx / "graph" / "graph.json", b'{"nodes": []}\n')
    report = _write(ctx / "graph" / "GRAPH_REPORT.md", b"# Report\n")

    removed, backed_up, errors = retire_paths(ctx)

    assert errors == ()
    assert set(removed) == {"graph/graph.json", "graph/GRAPH_REPORT.md"}
    assert set(backed_up) == {
        "_doc_backups/retired/0.6.0/graph/graph.json",
        "_doc_backups/retired/0.6.0/graph/GRAPH_REPORT.md",
    }
    backups = ctx / "_doc_backups" / "retired" / "0.6.0" / "graph"
    assert (backups / "graph.json").read_bytes() == b'{"nodes": []}\n'
    assert (backups / "GRAPH_REPORT.md").read_bytes() == b"# Report\n"
    assert not graph.exists() and not report.exists()
    assert not (ctx / "graph").exists()


def test_missing_retired_paths_are_silent(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    ctx.mkdir()
    assert retire_paths(ctx) == ((), (), ())
    assert retire_paths(tmp_path / "absent") == ((), (), ())


def test_is_link_is_fail_closed(tmp_path: Path, monkeypatch) -> None:
    plain = _write(tmp_path / "plain.txt", b"x")
    assert is_link(tmp_path / "missing") is False
    assert is_link(plain) is False
    assert is_link(tmp_path) is False
    (tmp_path / "target").mkdir()
    _link_dir(tmp_path / "linked", tmp_path / "target")

    assert is_link(tmp_path / "linked") is True

    def _denied(path):
        raise PermissionError(13, "denied", str(path))

    monkeypatch.setattr(atomic_io, "os", SimpleNamespace(lstat=_denied))
    assert is_link(plain) is True


def _seed_upgrade_state(ctx: Path) -> None:
    ensure_context_gitignore(ctx)
    gitignore = ctx / ".gitignore"
    gitignore.write_text(
        "".join(
            line + "\n"
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip() != "_council-log.json"
        ),
        encoding="utf-8",
    )
    _write(ctx / "_enrich_plan.json", b"{}\n")
    _write(ctx / "cache" / "_enrich_plan.json", b"{}\n")
    _write(ctx / "cache" / "extraction-version", b"0.36.0\n")
    _write(ctx / "cache" / _HASH_ENTRY, b"{}\n")
    _write(ctx / "cache" / "manifest.json", b"{}\n")
    name = "python-tester.suite.json"
    _write(ctx / "equipment-evals" / name, _lf(name))
    _write(ctx / "equipment-evals" / "x.result.json", b"mine\n")


def test_migrate_context_layout_fixes_everything_once(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    _seed_upgrade_state(ctx)

    result = migrate_context_layout(ctx, package_version="9.9.9")

    assert isinstance(result, LayoutMigration)
    assert result.errors == ()
    assert result.removed == (
        "_enrich_plan.json",
        "equipment-evals/python-tester.suite.json",
        "equipment-evals/x.result.json",
        "cache: 1 stale extraction entries",
    )
    assert result.backed_up == (f"{_EVAL_BACKUPS}/x.result.json",)
    lines = (ctx / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "_council-log.json" in lines
    assert (ctx / ".gitattributes").is_file()
    assert not (ctx / "_enrich_plan.json").exists()
    assert (ctx / "cache" / "_enrich_plan.json").is_file()
    assert not (ctx / "cache" / _HASH_ENTRY).exists()
    assert (ctx / "cache" / "manifest.json").is_file()
    stamp = (ctx / "cache" / "extraction-version").read_text(encoding="utf-8")
    assert stamp.strip() == "9.9.9"
    assert not (ctx / "equipment-evals").exists()

    again = migrate_context_layout(ctx, package_version="9.9.9")
    assert again == LayoutMigration()


def test_migrate_without_version_leaves_cache_alone(tmp_path: Path) -> None:
    ctx = tmp_path / ".context"
    _seed_upgrade_state(ctx)

    for version in (None, ""):
        result = migrate_context_layout(ctx, package_version=version)
        assert result.errors == ()
        assert not any(item.startswith("cache:") for item in result.removed)
    assert (ctx / "cache" / _HASH_ENTRY).is_file()


_STEPS = (
    "ensure_context_gitignore",
    "ensure_context_gitattributes",
    "remove_legacy_enrich_plan",
    "retire_paths",
    "scope_cache_to_version",
)


@pytest.mark.parametrize("failing", _STEPS)
def test_one_failing_step_is_recorded_and_the_rest_still_run(
    tmp_path: Path, monkeypatch, failing: str
) -> None:
    ctx = tmp_path / ".context"
    _seed_upgrade_state(ctx)
    (ctx / ".gitattributes").unlink(missing_ok=True)

    def _boom(*_args, **_kwargs):
        raise OSError("injected")

    monkeypatch.setattr(upgrade, failing, _boom)
    result = migrate_context_layout(ctx, package_version="9.9.9")

    assert result.errors == (f"{failing}: injected",)
    gitignore = (ctx / ".gitignore").read_text(encoding="utf-8").splitlines()
    effects = {
        "ensure_context_gitignore": "_council-log.json" in gitignore,
        "ensure_context_gitattributes": (ctx / ".gitattributes").is_file(),
        "remove_legacy_enrich_plan": not (ctx / "_enrich_plan.json").exists(),
        "retire_paths": not (ctx / "equipment-evals").exists(),
        "scope_cache_to_version": not (ctx / "cache" / _HASH_ENTRY).exists(),
    }
    assert effects == {step: step != failing for step in _STEPS}


def test_unlink_failure_on_one_entry_is_contained(tmp_path: Path, monkeypatch) -> None:
    ctx = tmp_path / ".context"
    _seed_upgrade_state(ctx)
    real_unlink = os.unlink

    def _unlink(path, *args, **kwargs):
        if Path(path).name == "python-tester.suite.json":
            raise PermissionError(13, "locked", str(path))
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(upgrade.os, "unlink", _unlink)
    result = migrate_context_layout(ctx, package_version="9.9.9")

    assert len(result.errors) == 1
    assert result.errors[0].startswith(
        "retire_paths: equipment-evals/python-tester.suite.json: "
    )
    assert "equipment-evals/x.result.json" in result.removed
    assert "cache: 1 stale extraction entries" in result.removed
    assert (ctx / "equipment-evals" / "python-tester.suite.json").is_file()


def test_runner_reexports_the_moved_helpers() -> None:
    for name in (
        "_MANAGED_GITIGNORE_PATTERNS",
        "_MANAGED_GITATTRIBUTES_RULES",
        "_CONTEXT_GITIGNORE_HEADER",
        "_CONTEXT_GITATTRIBUTES_HEADER",
        "_ensure_managed_lines",
        "ensure_context_gitignore",
        "ensure_context_gitattributes",
        "remove_legacy_enrich_plan",
    ):
        assert getattr(runner, name) is getattr(upgrade, name)


def test_upgrade_imports_neither_runner_nor_installer() -> None:
    tree = ast.parse(inspect.getsource(upgrade))
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any("runner" in module or "installer" in module for module in imported)


# --- format_migration_report -------------------------------------------------

_PREFIX = "  .context/        ->  "


def test_format_report_is_empty_for_a_clean_migration() -> None:
    assert upgrade.format_migration_report(LayoutMigration()) == []


def test_format_report_caps_removed_at_five_with_overflow_line() -> None:
    removed = tuple(f"equipment-evals/s{i}.suite.json" for i in range(8))
    lines = upgrade.format_migration_report(LayoutMigration(removed=removed))
    assert lines == [
        *(f"{_PREFIX}removed equipment-evals/s{i}.suite.json" for i in range(5)),
        f"{_PREFIX}… and 3 more removed",
    ]


def test_format_report_exactly_cap_items_has_no_overflow_line() -> None:
    removed = tuple(f"r{i}" for i in range(5))
    backed_up = tuple(f"_doc_backups/retired/0.37.0/b{i}" for i in range(5))
    lines = upgrade.format_migration_report(
        LayoutMigration(removed=removed, backed_up=backed_up)
    )
    assert len(lines) == 10
    assert not any("more" in line for line in lines)


def test_format_report_orders_categories_and_caps_each() -> None:
    migration = LayoutMigration(
        removed=("a",),
        backed_up=tuple(f"_doc_backups/retired/0.37.0/b{i}" for i in range(7)),
        errors=tuple(f"step{i}: boom" for i in range(6)),
    )
    lines = upgrade.format_migration_report(
        migration, (("features/symbol-graph.json", "RuntimeError('x')"),)
    )
    assert lines == [
        f"{_PREFIX}removed a",
        *(
            f"{_PREFIX}backed up to .context/_doc_backups/retired/0.37.0/b{i}"
            for i in range(5)
        ),
        f"{_PREFIX}… and 2 more backed up",
        *(f"{_PREFIX}warning: migration step{i}: boom" for i in range(5)),
        f"{_PREFIX}… and 1 more migration warnings",
        f"{_PREFIX}warning: features/symbol-graph.json failed (RuntimeError('x')); "
        "version stamp not advanced — fix the cause, then run "
        "`dummyindex context rebuild --changed`",
    ]


def test_format_report_never_caps_failures_and_honours_prefix_and_cap() -> None:
    failed = tuple((f"artifact-{i}", "err") for i in range(7))
    lines = upgrade.format_migration_report(
        LayoutMigration(removed=("x", "y", "z")), failed, prefix="  ", cap=1
    )
    assert lines[:2] == ["  removed x", "  … and 2 more removed"]
    assert len(lines) == 2 + 7
    assert all(
        line.startswith("  warning: artifact-") and "version stamp not advanced" in line
        for line in lines[2:]
    )
