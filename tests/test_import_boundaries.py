"""Import-boundary test for the shared / context / evolve split (spec C1-C5).

Stdlib-only AST scanner over ``dummyindex/**/*.py``. Wave 2 rules: R1 (shared
side only), R4-R7. R2, R3 and the context->evolve half of R1 come with the
evolve wave.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.paths import REPO_ROOT

PKG = "dummyindex"
# Old home (last module segment, unchanged by the move) -> symbols that moved to shared.
MOVED = {
    "evolve_gate": {"EvolveError", "safe_file"},
    "evolve_promotion": {"project_lock"},
    "living_rules": {"rules_in"},
}
OLD_PREFIXES = (
    "dummyindex.context.domains.atomic_io",
    "dummyindex.context.domains.lesson",
)
OLD_FILES = (
    "dummyindex/context/domains/atomic_io.py",
    "dummyindex/context/domains/lesson/__init__.py",
    "dummyindex/context/domains/lesson/enums.py",
    "dummyindex/context/domains/lesson/models.py",
)
# Known, reviewed dynamic import sites (R7 allowlist).
DYNAMIC_ALLOW = {
    ("dummyindex/__init__.py", 30),
    ("dummyindex/pipeline/extract/generic.py", 25),
}
DYNAMIC_NAMES = ("import_module", "__import__")


@dataclass(frozen=True)
class Edge:
    path: str
    line: int
    module: str
    names: tuple[str, ...]
    kind: str  # "import", "from", "import_module" or "__import__"
    lazy: bool
    layer: str


@dataclass(frozen=True)
class Dynamic:
    path: str
    line: int
    func: str


@dataclass
class Scan:
    files: list[str]
    modules: set[str]
    edges: list[Edge]
    dynamic: list[Dynamic]


def _layer(parts: tuple[str, ...]) -> str:
    if len(parts) > 2 and parts[1] == "shared":
        return "shared"
    if len(parts) > 2 and parts[1] == "evolve":
        return "evolve"
    return "context"


def _module_name(rel: Path) -> str:
    parts = rel.with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _relative_base(module: str, is_init: bool, level: int, name: str | None) -> str | None:
    # An __init__.py is its own package; any other module lives in its parent.
    package = module if is_init else module.rpartition(".")[0]
    parts = package.split(".")
    if level - 1 >= len(parts):
        return None
    base = ".".join(parts[: len(parts) - (level - 1)])
    return f"{base}.{name}" if name else base


def _lazy_nodes(tree: ast.AST) -> set[int]:
    lazy: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lazy.update(id(child) for child in ast.walk(node))
    return lazy


def _from_edges(node: ast.ImportFrom, base: str, modules: set[str], path: str, lazy: bool, layer: str) -> list[Edge]:
    # `from pkg import name` targets pkg.name when that is a module, else pkg.
    edges: list[Edge] = []
    rest: list[str] = []
    names = [alias.name for alias in node.names]
    for name in names:
        if name != "*" and f"{base}.{name}" in modules:
            edges.append(Edge(path, node.lineno, f"{base}.{name}", (name,), "from", lazy, layer))
        else:
            rest.append(name)
    if rest or not names:
        edges.append(Edge(path, node.lineno, base, tuple(rest), "from", lazy, layer))
    return edges


def _file_edges(path: Path, rel: Path, modules: set[str]) -> tuple[list[Edge], list[Dynamic]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel.as_posix())
    module = _module_name(rel)
    is_init = rel.name == "__init__.py"
    layer = _layer(rel.parts)
    rel_text = rel.as_posix()
    lazy = _lazy_nodes(tree)
    edges: list[Edge] = []
    dynamic: list[Dynamic] = []
    for node in ast.walk(tree):
        is_lazy = id(node) in lazy
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(Edge(rel_text, node.lineno, alias.name, (), "import", is_lazy, layer))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                resolved = _relative_base(module, is_init, node.level, node.module)
                if resolved is None:
                    continue
                base = resolved
            edges.extend(_from_edges(node, base, modules, rel_text, is_lazy, layer))
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in DYNAMIC_NAMES:
                continue
            arg = node.args[0] if node.args else None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                edges.append(Edge(rel_text, node.lineno, arg.value, (), name, is_lazy, layer))
            else:
                dynamic.append(Dynamic(rel_text, node.lineno, name))
    return edges, dynamic


def scan(root: Path) -> Scan:
    files = sorted((root / PKG).rglob("*.py"))
    rels = [path.relative_to(root) for path in files]
    modules = {_module_name(rel) for rel in rels}
    edges: list[Edge] = []
    dynamic: list[Dynamic] = []
    for path, rel in zip(files, rels, strict=True):
        file_edges, file_dynamic = _file_edges(path, rel, modules)
        edges.extend(file_edges)
        dynamic.extend(file_dynamic)
    return Scan([rel.as_posix() for rel in rels], modules, edges, dynamic)


def _edge_violations(edge: Edge, modules: set[str]) -> list[str]:
    names = ", ".join(edge.names) or edge.kind
    top = edge.module.split(".")[0]
    found: list[str] = []

    def add(rule: str) -> None:
        found.append(f"{rule} {edge.path}:{edge.line} -> {edge.module} ({names})")

    if edge.layer == "shared":  # R1: shared imports only shared and stdlib
        if top == PKG:
            if edge.module != "dummyindex.shared" and not edge.module.startswith("dummyindex.shared."):
                add("R1")
        elif top not in sys.stdlib_module_names:
            add("R1")
    if set(edge.names) & MOVED.get(edge.module.rpartition(".")[2], set()):  # R4
        add("R4")
    if any(edge.module == prefix or edge.module.startswith(prefix + ".") for prefix in OLD_PREFIXES):  # R5
        add("R5")
    if top == PKG and edge.module not in modules:  # R6
        add("R6")
    return found


def violations(root: Path) -> list[str]:
    result = scan(root)
    found: list[str] = []
    for edge in result.edges:
        found.extend(_edge_violations(edge, result.modules))
    for site in result.dynamic:  # R7
        if (site.path, site.line) not in DYNAMIC_ALLOW:
            found.append(f"R7 {site.path}:{site.line} -> {site.func} (dynamic)")
    for old in OLD_FILES:  # R5: a moved-away file must not come back
        if old in result.files:
            found.append(f"R5 {old}:0 -> {old} (exists)")
    return sorted(found)


def _tree(root: Path, files: dict[str, str]) -> Path:
    package_dirs = {root / PKG}
    for rel, source in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
        for parent in Path(rel).parents:
            if parent.parts and parent.parts[0] == PKG:
                package_dirs.add(root / parent)
    for directory in package_dirs:
        init = directory / "__init__.py"
        if not init.exists():
            init.write_text("", encoding="utf-8")
    return root


CASES = [
    pytest.param(
        {"dummyindex/shared/a.py": "from dummyindex.context import helper\n", "dummyindex/context/__init__.py": ""},
        ["R1 dummyindex/shared/a.py:1 -> dummyindex.context (helper)"],
        id="shared-to-context",
    ),
    pytest.param(
        {"dummyindex/shared/a.py": "from dummyindex.evolve import helper\n", "dummyindex/evolve/__init__.py": ""},
        ["R1 dummyindex/shared/a.py:1 -> dummyindex.evolve (helper)"],
        id="shared-to-evolve",
    ),
    pytest.param(
        {
            "dummyindex/shared/a.py": (
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from dummyindex.context import helper\n"
            ),
            "dummyindex/context/__init__.py": "",
        },
        ["R1 dummyindex/shared/a.py:3 -> dummyindex.context (helper)"],
        id="type-checking-shared-to-context",
    ),
    pytest.param(
        {
            "dummyindex/shared/a.py": 'import importlib\nimportlib.import_module("dummyindex.context.x")\n',
            "dummyindex/context/x.py": "",
        },
        ["R1 dummyindex/shared/a.py:2 -> dummyindex.context.x (import_module)"],
        id="literal-import-module-shared-to-context",
    ),
    pytest.param(
        {"dummyindex/shared/__init__.py": "from ..context import helper\n", "dummyindex/context/__init__.py": ""},
        ["R1 dummyindex/shared/__init__.py:1 -> dummyindex.context (helper)"],
        id="relative-init-shared-to-context",
    ),
    pytest.param(
        {
            "dummyindex/context/user.py": "from dummyindex.context.domains.evolve_gate import EvolveError\n",
            "dummyindex/context/domains/evolve_gate.py": "",
        },
        ["R4 dummyindex/context/user.py:1 -> dummyindex.context.domains.evolve_gate (EvolveError)"],
        id="moved-symbol-absolute",
    ),
    pytest.param(
        {
            "dummyindex/context/domains/user.py": "from .evolve_gate import EvolveError\n",
            "dummyindex/context/domains/evolve_gate.py": "",
        },
        ["R4 dummyindex/context/domains/user.py:1 -> dummyindex.context.domains.evolve_gate (EvolveError)"],
        id="moved-symbol-relative",
    ),
    pytest.param(
        {
            "dummyindex/context/user.py": "from dummyindex.context.domains.atomic_io import write_text_atomic\n",
            "dummyindex/context/domains/atomic_io.py": "",
        },
        [
            "R5 dummyindex/context/domains/atomic_io.py:0 -> dummyindex/context/domains/atomic_io.py (exists)",
            "R5 dummyindex/context/user.py:1 -> dummyindex.context.domains.atomic_io (write_text_atomic)",
        ],
        id="old-path-import-and-old-file",
    ),
    pytest.param(
        {"dummyindex/context/user.py": "from dummyindex.nope import thing\n"},
        ["R6 dummyindex/context/user.py:1 -> dummyindex.nope (thing)"],
        id="unresolved-base",
    ),
    pytest.param(
        {"dummyindex/context/user.py": "import importlib\n\n\ndef load(name):\n    return importlib.import_module(name)\n"},
        ["R7 dummyindex/context/user.py:5 -> import_module (dynamic)"],
        id="dynamic-import-module",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(("files", "expected"), CASES)
def test_forbidden_form_reports_exact_message(tmp_path: Path, files: dict[str, str], expected: list[str]) -> None:
    assert violations(_tree(tmp_path, files)) == sorted(expected)


@pytest.mark.unit
def test_allowed_tree_reports_nothing(tmp_path: Path) -> None:
    files = {
        "dummyindex/context/user.py": "from dummyindex.shared.atomic_io import write_text_atomic\n",
        "dummyindex/shared/atomic_io.py": "import os\nfrom pathlib import Path\n\n\ndef write_text_atomic():\n    pass\n",
        "dummyindex/shared/errors.py": "class EvolveError(Exception):\n    pass\n",
        "dummyindex/shared/lesson/rules.py": "from dummyindex.shared.errors import EvolveError\n",
    }
    assert violations(_tree(tmp_path, files)) == []


@pytest.mark.unit
def test_real_tree_has_no_violations() -> None:
    assert violations(REPO_ROOT) == []


@pytest.mark.unit
def test_real_tree_scans_every_module() -> None:
    assert len(scan(REPO_ROOT).files) == len(list((REPO_ROOT / PKG).rglob("*.py")))


@pytest.mark.unit
def test_real_tree_has_context_to_shared_edge() -> None:
    edges = scan(REPO_ROOT).edges
    assert any(edge.layer == "context" and edge.module.startswith("dummyindex.shared") for edge in edges)
