"""Tests for the narrow Python dispatch-idiom resolver (item A4).

Fixtures model this repo's own idioms so the callers-of / dead-code blind
spot provably closes:

- ``cli/__init__.py``'s enum-keyed dispatch dict
  (``{ContextSubcommand.SCAN_CHECK: scan.run}``) — the handler function must
  gain an incoming ``calls`` edge from the mapping's enclosing scope;
- ``cli/rebuild.py``-style function-body ``from X import Y`` — the enclosing
  function's module must gain an ``imports_from`` edge (previously only
  module-level imports were seen).

Precision over recall: only references that match a known extracted symbol
resolve; ambiguous or unbound references produce no edge.
"""

from __future__ import annotations

import pytest

from dummyindex.pipeline.enums import ConfidenceLevel
from dummyindex.pipeline.extract import extract

_ENUMS_PY = """\
class ContextSubcommand:
    SCAN_CHECK = "scan-check"
    REBUILD = "rebuild"
"""

_SCAN_PY = """\
def run(args):
    return 0
"""


def _extract_dir(tmp_path):
    return extract(sorted(tmp_path.rglob("*.py")), cache_root=tmp_path)


def _calls_to(result, target):
    return [
        e for e in result["edges"] if e["relation"] == "calls" and e["target"] == target
    ]


def _imports_from(result, source):
    return [
        e
        for e in result["edges"]
        if e["relation"] == "imports_from" and e["source"] == source
    ]


# --- (1) enum-keyed dispatch dict → calls edges --------------------------------


@pytest.mark.unit
def test_enum_keyed_dispatch_dict_produces_calls_edge(tmp_path):
    """The cli/__init__.py idiom: a module-level enum-keyed dict whose value is
    ``scan.run`` gives the handler an incoming calls edge (source = file)."""
    (tmp_path / "enums.py").write_text(_ENUMS_PY)
    (tmp_path / "scan.py").write_text(_SCAN_PY)
    (tmp_path / "__init__.py").write_text(
        "from enums import ContextSubcommand\n"
        "\n"
        "from . import scan\n"
        "\n"
        "_HANDLERS = {\n"
        "    ContextSubcommand.SCAN_CHECK: scan.run,\n"
        "}\n"
    )

    result = _extract_dir(tmp_path)

    edges = _calls_to(result, "scan_run")
    assert edges, "handler must gain an incoming calls edge (blind spot closed)"
    (edge,) = edges
    assert edge["source"] == "init_py"
    assert edge["confidence"] == ConfidenceLevel.INFERRED
    assert edge["confidence_score"] < 1.0
    assert edge["source_file"].endswith("__init__.py")
    assert edge["source_location"] == "L6"


@pytest.mark.unit
def test_dispatch_dict_inside_function_scopes_edge_to_function(tmp_path):
    """A dispatch dict built inside a function attributes the calls edge to
    the enclosing function node, not the file."""
    (tmp_path / "enums.py").write_text(_ENUMS_PY)
    (tmp_path / "scan.py").write_text(_SCAN_PY)
    (tmp_path / "disp.py").write_text(
        "from enums import ContextSubcommand\n"
        "import scan\n"
        "\n"
        "def dispatch(argv):\n"
        "    handlers = {ContextSubcommand.SCAN_CHECK: scan.run}\n"
        "    return handlers\n"
    )

    result = _extract_dir(tmp_path)

    assert [e["source"] for e in _calls_to(result, "scan_run")] == ["disp_dispatch"]


@pytest.mark.unit
def test_bare_known_function_values_resolve(tmp_path):
    """Bare identifier values resolve against same-file functions and
    ``from X import name`` bindings — nothing else."""
    (tmp_path / "enums.py").write_text(_ENUMS_PY)
    (tmp_path / "scan.py").write_text("def run_scan(args):\n    return 0\n")
    (tmp_path / "disp.py").write_text(
        "from enums import ContextSubcommand\n"
        "from scan import run_scan\n"
        "\n"
        "def run_rebuild(args):\n"
        "    return 0\n"
        "\n"
        "_HANDLERS = {\n"
        "    ContextSubcommand.SCAN_CHECK: run_scan,\n"
        "    ContextSubcommand.REBUILD: run_rebuild,\n"
        "}\n"
    )

    result = _extract_dir(tmp_path)

    assert {e["source"] for e in _calls_to(result, "scan_run_scan")} == {"disp_py"}
    assert {e["source"] for e in _calls_to(result, "disp_run_rebuild")} == {"disp_py"}


@pytest.mark.unit
def test_unresolvable_or_unbound_values_produce_no_edges(tmp_path):
    """Precision over recall: string keys, unbound module objects, unknown
    attrs, nested attributes, and stdlib refs all produce no calls edge."""
    (tmp_path / "enums.py").write_text(_ENUMS_PY)
    (tmp_path / "scan.py").write_text(_SCAN_PY)
    # helpers.py defines run() but disp.py never imports helpers.
    (tmp_path / "helpers.py").write_text("def run(args):\n    return 1\n")
    (tmp_path / "disp.py").write_text(
        "import sys\n"
        "from enums import ContextSubcommand\n"
        "import scan\n"
        "\n"
        "STRING_KEYED = {'scan-check': scan.run}\n"
        "UNBOUND = {ContextSubcommand.SCAN_CHECK: helpers.run}\n"
        "UNKNOWN_ATTR = {ContextSubcommand.SCAN_CHECK: scan.missing}\n"
        "NESTED = {ContextSubcommand.SCAN_CHECK: scan.run.extra}\n"
        "STDLIB = {ContextSubcommand.SCAN_CHECK: sys.exit}\n"
    )

    result = _extract_dir(tmp_path)

    disp_calls = [
        e
        for e in result["edges"]
        if e["relation"] == "calls" and e["source"] == "disp_py"
    ]
    assert disp_calls == []
    assert _calls_to(result, "scan_run") == []
    assert _calls_to(result, "helpers_run") == []


@pytest.mark.unit
def test_ambiguous_module_stem_is_skipped(tmp_path):
    """Two files with the same stem both defining the referenced symbol —
    no guessing across packages, no edge."""
    (tmp_path / "enums.py").write_text(_ENUMS_PY)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "scan.py").write_text("def run(args):\n    return 1\n")
    (tmp_path / "b" / "scan.py").write_text("def run(args):\n    return 2\n")
    (tmp_path / "disp.py").write_text(
        "from enums import ContextSubcommand\n"
        "from a import scan\n"
        "\n"
        "_HANDLERS = {ContextSubcommand.SCAN_CHECK: scan.run}\n"
    )

    result = _extract_dir(tmp_path)

    assert _calls_to(result, "scan_run") == []


# --- (2) function-body `from X import Y` → imports_from ------------------------


@pytest.mark.unit
def test_function_body_from_import_yields_inferred_imports_from(tmp_path):
    """The cli/rebuild.py idiom: a lazy in-function import produces an
    imports_from edge attributed to the enclosing function's module."""
    (tmp_path / "incremental.py").write_text(
        "def rebuild_changed(root):\n    return 0\n"
    )
    (tmp_path / "rebuild.py").write_text(
        "def run(args):\n"
        "    from incremental import rebuild_changed\n"
        "    return rebuild_changed(args)\n"
    )

    result = _extract_dir(tmp_path)

    (edge,) = _imports_from(result, "rebuild_py")
    assert edge["target"] == "incremental"
    assert edge["confidence"] == ConfidenceLevel.INFERRED
    assert edge["confidence_score"] < 1.0
    assert edge["source_location"] == "L2"


@pytest.mark.unit
def test_function_body_relative_import_resolves_to_file_node(tmp_path):
    """A relative in-function import resolves to the target file's node id
    (post-remap), exactly like a module-level relative import would."""
    (tmp_path / "incremental.py").write_text(
        "def rebuild_changed(root):\n    return 0\n"
    )
    (tmp_path / "rebuild.py").write_text(
        "def run(args):\n    from .incremental import rebuild_changed\n    return 0\n"
    )

    result = _extract_dir(tmp_path)

    (edge,) = _imports_from(result, "rebuild_py")
    assert edge["target"] == "incremental_py"
    assert edge["confidence"] == ConfidenceLevel.INFERRED


@pytest.mark.unit
def test_module_level_import_stays_extracted_and_undoubled(tmp_path):
    """A module-level from-import is untouched: exactly one EXTRACTED edge,
    no INFERRED duplicate."""
    (tmp_path / "incremental.py").write_text(
        "def rebuild_changed(root):\n    return 0\n"
    )
    (tmp_path / "rebuild.py").write_text(
        "from incremental import rebuild_changed\n"
        "\n"
        "def run(args):\n"
        "    return rebuild_changed(args)\n"
    )

    result = _extract_dir(tmp_path)

    (edge,) = _imports_from(result, "rebuild_py")
    assert edge["confidence"] == ConfidenceLevel.EXTRACTED


# --- determinism ----------------------------------------------------------------


@pytest.mark.unit
def test_dispatch_edges_deterministic_across_cached_rebuilds(tmp_path):
    """Second extraction (served from the per-file cache) yields the same
    dispatch / local-import edge set — the artifacts are committed and diffed."""
    (tmp_path / "enums.py").write_text(_ENUMS_PY)
    (tmp_path / "scan.py").write_text(_SCAN_PY)
    (tmp_path / "disp.py").write_text(
        "from enums import ContextSubcommand\n"
        "import scan\n"
        "\n"
        "_HANDLERS = {ContextSubcommand.SCAN_CHECK: scan.run}\n"
        "\n"
        "def run(args):\n"
        "    from enums import ContextSubcommand as _cs\n"
        "    return _cs\n"
    )

    def triples(result):
        return sorted(
            (e["source"], e["target"], e["relation"])
            for e in result["edges"]
            if e["relation"] in ("calls", "imports_from")
        )

    first = triples(_extract_dir(tmp_path))
    second = triples(_extract_dir(tmp_path))
    assert first == second
    assert ("disp_py", "scan_run", "calls") in first
