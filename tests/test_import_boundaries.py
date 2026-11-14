"""Import-boundary test for the shared / context / evolve split (spec C1-C5).

Stdlib-only AST scanner over ``dummyindex/**/*.py`` covering R1-R7: direction,
root pairs, private names, moved symbols, old paths, resolution and dynamic
imports. Also checks fresh-interpreter imports for the split packages.
"""

from __future__ import annotations

import ast
import subprocess
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
EVOLVE_OLD_DOMAINS = (
    "evidence",
    "evolve",
    "evolve_experiments",
    "evolve_gate",
    "evolve_learning",
    "evolve_native",
    "evolve_native_response",
    "evolve_native_snapshot",
    "evolve_promotion",
    "living_rules",
    "observe",
    "probation",
)
OLD_PREFIXES = (
    "dummyindex.context.domains.atomic_io",
    "dummyindex.context.domains.lesson",
    *(f"dummyindex.context.domains.{name}" for name in EVOLVE_OLD_DOMAINS),
    "dummyindex.cli.evolve",
    "dummyindex.cli.evolve_probation",
)
_DOMAINS = "dummyindex/context/domains"
OLD_FILES = (
    "dummyindex/context/domains/atomic_io.py",
    "dummyindex/context/domains/lesson/__init__.py",
    "dummyindex/context/domains/lesson/enums.py",
    "dummyindex/context/domains/lesson/models.py",
    *(
        f"{_DOMAINS}/{name}.py"
        for name in EVOLVE_OLD_DOMAINS
        if name not in ("observe", "probation")
    ),
    *(
        f"{_DOMAINS}/observe/{name}.py"
        for name in (
            "__init__",
            "attribution",
            "enums",
            "importer",
            "keys",
            "ledger",
            "models",
            "security",
        )
    ),
    *(
        f"{_DOMAINS}/probation/{name}.py"
        for name in (
            "__init__",
            "actions",
            "constants",
            "enums",
            "models",
            "render",
            "rules",
            "store",
            "sync",
        )
    ),
    "dummyindex/cli/evolve.py",
    "dummyindex/cli/evolve_probation.py",
)
# Composition root may lazily import exactly these evolve modules (spec C1).
ROOT_PAIRS = {
    ("dummyindex/cli/__init__.py", "dummyindex.evolve.cli.evolve"),
    ("dummyindex/cli/__init__.py", "dummyindex.evolve.evolve_learning"),
    ("dummyindex/cli/__init__.py", "dummyindex.evolve.probation"),
}
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
    kind: str  # "import", "from", "import_module", "__import__" or "attr" (alias read)
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
    reads: list[Edge]  # `alias._x` attribute reads, one Edge per read


def _layer(parts: tuple[str, ...]) -> str:
    if len(parts) > 1 and parts[1] == "shared":
        return "shared"
    if len(parts) > 1 and parts[1] == "evolve":
        return "evolve"
    return "context"


def _module_layer(module: str) -> str | None:
    parts = tuple(module.split("."))
    if parts[0] != PKG:
        return None
    return _layer(parts)


def _module_name(rel: Path) -> str:
    parts = rel.with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _relative_base(
    module: str, is_init: bool, level: int, name: str | None
) -> str | None:
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


def _from_edges(
    node: ast.ImportFrom,
    base: str,
    modules: set[str],
    path: str,
    lazy: bool,
    layer: str,
) -> list[Edge]:
    # `from pkg import name` targets pkg.name when that is a module, else pkg.
    edges: list[Edge] = []
    rest: list[str] = []
    names = [alias.name for alias in node.names]
    for name in names:
        if name != "*" and f"{base}.{name}" in modules:
            edges.append(
                Edge(path, node.lineno, f"{base}.{name}", (name,), "from", lazy, layer)
            )
        else:
            rest.append(name)
    if rest or not names:
        edges.append(Edge(path, node.lineno, base, tuple(rest), "from", lazy, layer))
    return edges


def _file_edges(
    path: Path, rel: Path, modules: set[str]
) -> tuple[list[Edge], list[Dynamic], list[Edge]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel.as_posix())
    module = _module_name(rel)
    is_init = rel.name == "__init__.py"
    layer = _layer(rel.parts)
    rel_text = rel.as_posix()
    lazy = _lazy_nodes(tree)
    edges: list[Edge] = []
    dynamic: list[Dynamic] = []
    aliases: dict[
        str, str
    ] = {}  # local name -> module, for `import a.b as x` and `from a import b`
    for node in ast.walk(tree):
        is_lazy = id(node) in lazy
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(
                    Edge(
                        rel_text, node.lineno, alias.name, (), "import", is_lazy, layer
                    )
                )
                if alias.asname:
                    aliases[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                resolved = _relative_base(module, is_init, node.level, node.module)
                if resolved is None:
                    continue
                base = resolved
            for alias in node.names:
                if f"{base}.{alias.name}" in modules:
                    aliases[alias.asname or alias.name] = f"{base}.{alias.name}"
            edges.extend(_from_edges(node, base, modules, rel_text, is_lazy, layer))
        elif isinstance(node, ast.Call):
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            )
            if name not in DYNAMIC_NAMES:
                continue
            arg = node.args[0] if node.args else None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                edges.append(
                    Edge(rel_text, node.lineno, arg.value, (), name, is_lazy, layer)
                )
            else:
                dynamic.append(Dynamic(rel_text, node.lineno, name))
    reads: list[Edge] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            attr = node.attr
            if attr.startswith("_") and not (
                attr.startswith("__") and attr.endswith("__")
            ):  # dunders are exempt
                reads.append(
                    Edge(
                        rel_text,
                        node.lineno,
                        aliases[node.value.id],
                        (attr,),
                        "attr",
                        id(node) in lazy,
                        layer,
                    )
                )
    return edges, dynamic, reads


def scan(root: Path) -> Scan:
    files = sorted((root / PKG).rglob("*.py"))
    rels = [path.relative_to(root) for path in files]
    modules = {_module_name(rel) for rel in rels}
    edges: list[Edge] = []
    dynamic: list[Dynamic] = []
    reads: list[Edge] = []
    for path, rel in zip(files, rels, strict=True):
        file_edges, file_dynamic, file_reads = _file_edges(path, rel, modules)
        edges.extend(file_edges)
        dynamic.extend(file_dynamic)
        reads.extend(file_reads)
    return Scan([rel.as_posix() for rel in rels], modules, edges, dynamic, reads)


def _edge_violations(edge: Edge, modules: set[str]) -> list[str]:
    names = ", ".join(edge.names) or edge.kind
    top = edge.module.split(".")[0]
    target = _module_layer(edge.module)
    found: list[str] = []

    def add(rule: str, shown: str = names) -> None:
        found.append(f"{rule} {edge.path}:{edge.line} -> {edge.module} ({shown})")

    if edge.layer == "shared":  # R1: shared imports only shared and stdlib
        if top == PKG:
            if edge.module != "dummyindex.shared" and not edge.module.startswith(
                "dummyindex.shared."
            ):
                add("R1")
        elif top not in sys.stdlib_module_names:
            add("R1")
    if (
        edge.layer == "context"
        and target == "evolve"
        and (edge.path, edge.module) not in ROOT_PAIRS
    ):  # R1
        add("R1")
    if (edge.path, edge.module) in ROOT_PAIRS and not edge.lazy:  # R2
        add("R2")
    private = [name for name in edge.names if name.startswith("_")]
    if (
        private and target is not None and target != edge.layer
    ):  # R3: cross-layer private name or alias read
        add("R3", ", ".join(private))
    if set(edge.names) & MOVED.get(edge.module.rpartition(".")[2], set()):  # R4
        add("R4")
    # `from pkg import old_name` names a module that no longer exists, so also match pkg.old_name.
    targets = (edge.module, *(f"{edge.module}.{name}" for name in edge.names))
    if any(
        target == prefix or target.startswith(prefix + ".")
        for target in targets
        for prefix in OLD_PREFIXES
    ):
        add("R5")
    if top == PKG and edge.module not in modules:  # R6
        add("R6")
    return found


def violations(root: Path) -> list[str]:
    result = scan(root)
    found: list[str] = []
    for edge in [*result.edges, *result.reads]:
        found.extend(_edge_violations(edge, result.modules))
    for site in result.dynamic:  # R7
        if (site.path, site.line) not in DYNAMIC_ALLOW:
            found.append(f"R7 {site.path}:{site.line} -> {site.func} (dynamic)")
    if (
        "dummyindex/cli/__init__.py" in result.files
    ):  # R2: every root pair must still be imported
        seen = {(edge.path, edge.module) for edge in result.edges}
        for path, module in sorted(ROOT_PAIRS):
            if (path, module) not in seen:
                found.append(f"R2 {path}:0 -> {module} (stale)")
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
        {
            "dummyindex/shared/a.py": "from dummyindex.context import helper\n",
            "dummyindex/context/__init__.py": "",
        },
        ["R1 dummyindex/shared/a.py:1 -> dummyindex.context (helper)"],
        id="shared-to-context",
    ),
    pytest.param(
        {
            "dummyindex/shared/a.py": "from dummyindex.evolve import helper\n",
            "dummyindex/evolve/__init__.py": "",
        },
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
        {
            "dummyindex/shared/__init__.py": "from ..context import helper\n",
            "dummyindex/context/__init__.py": "",
        },
        ["R1 dummyindex/shared/__init__.py:1 -> dummyindex.context (helper)"],
        id="relative-init-shared-to-context",
    ),
    pytest.param(
        {
            "dummyindex/evolve/user.py": "from dummyindex.evolve.evolve_gate import EvolveError\n",
            "dummyindex/evolve/evolve_gate.py": "",
        },
        [
            "R4 dummyindex/evolve/user.py:1 -> dummyindex.evolve.evolve_gate (EvolveError)"
        ],
        id="moved-symbol-absolute",
    ),
    pytest.param(
        {
            "dummyindex/evolve/user.py": "from .evolve_gate import EvolveError\n",
            "dummyindex/evolve/evolve_gate.py": "",
        },
        [
            "R4 dummyindex/evolve/user.py:1 -> dummyindex.evolve.evolve_gate (EvolveError)"
        ],
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
        {
            "dummyindex/context/user.py": "import importlib\n\n\ndef load(name):\n    return importlib.import_module(name)\n"
        },
        ["R7 dummyindex/context/user.py:5 -> import_module (dynamic)"],
        id="dynamic-import-module",
    ),
    pytest.param(
        {
            "dummyindex/context/user.py": "from dummyindex.context.domains import atomic_io\n",
            "dummyindex/context/domains/__init__.py": "",
        },
        ["R5 dummyindex/context/user.py:1 -> dummyindex.context.domains (atomic_io)"],
        id="old-module-as-name-absolute",
    ),
    pytest.param(
        {
            "dummyindex/context/user.py": "from dummyindex.context.domains import lesson\n",
            "dummyindex/context/domains/__init__.py": "",
        },
        ["R5 dummyindex/context/user.py:1 -> dummyindex.context.domains (lesson)"],
        id="old-package-as-name-absolute",
    ),
    pytest.param(
        {"dummyindex/context/domains/user.py": "from . import atomic_io\n"},
        [
            "R5 dummyindex/context/domains/user.py:1 -> dummyindex.context.domains (atomic_io)"
        ],
        id="old-module-as-name-relative",
    ),
    pytest.param(
        {
            "dummyindex/shared/a.py": "from dummyindex.evolve import probation\n",
            "dummyindex/evolve/probation/__init__.py": "",
        },
        ["R1 dummyindex/shared/a.py:1 -> dummyindex.evolve.probation (probation)"],
        id="shared-to-evolve-module-resolved",
    ),
    pytest.param(
        {"dummyindex/shared/a.py": "import requests\n"},
        ["R1 dummyindex/shared/a.py:1 -> requests (import)"],
        id="shared-to-third-party",
    ),
    pytest.param(
        {
            "dummyindex/shared/a.py": '__import__("dummyindex.context.x")\n',
            "dummyindex/context/x.py": "",
        },
        ["R1 dummyindex/shared/a.py:1 -> dummyindex.context.x (__import__)"],
        id="shared-dunder-import-to-context",
    ),
    pytest.param(
        {
            "dummyindex/context/user.py": 'import importlib\nimportlib.import_module("dummyindex.nope")\n'
        },
        ["R6 dummyindex/context/user.py:2 -> dummyindex.nope (import_module)"],
        id="literal-import-module-unresolved",
    ),
    pytest.param(
        {"dummyindex/context/domains/user.py": "from ..nope import thing\n"},
        ["R6 dummyindex/context/domains/user.py:1 -> dummyindex.context.nope (thing)"],
        id="relative-unresolved",
    ),
    # --- v2: R1 context->evolve, R2 root pairs, R3 private names, R5 evolve paths ---
    pytest.param(
        {
            "dummyindex/context/user.py": "from dummyindex.evolve import probation\n",
            "dummyindex/evolve/probation/__init__.py": "",
        },
        ["R1 dummyindex/context/user.py:1 -> dummyindex.evolve.probation (probation)"],
        id="context-to-evolve-module",
    ),
    pytest.param(
        {
            "dummyindex/context/user.py": (
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from dummyindex.evolve import probation\n"
            ),
            "dummyindex/evolve/probation/__init__.py": "",
        },
        ["R1 dummyindex/context/user.py:3 -> dummyindex.evolve.probation (probation)"],
        id="context-to-evolve-type-checking",
    ),
    pytest.param(
        {
            "dummyindex/context/user.py": 'import importlib\nimportlib.import_module("dummyindex.evolve.x")\n',
            "dummyindex/evolve/x.py": "",
        },
        ["R1 dummyindex/context/user.py:2 -> dummyindex.evolve.x (import_module)"],
        id="context-literal-import-module-to-evolve",
    ),
    pytest.param(
        {
            "dummyindex/context/__init__.py": "from ..evolve import helper\n",
            "dummyindex/evolve/__init__.py": "",
        },
        ["R1 dummyindex/context/__init__.py:1 -> dummyindex.evolve (helper)"],
        id="context-relative-init-to-evolve",
    ),
    pytest.param(
        {
            "dummyindex/cli/__init__.py": "from dummyindex.evolve.probation import session_block\n",
            "dummyindex/evolve/probation/__init__.py": "",
        },
        [
            "R2 dummyindex/cli/__init__.py:1 -> dummyindex.evolve.probation (session_block)",
            "R2 dummyindex/cli/__init__.py:0 -> dummyindex.evolve.cli.evolve (stale)",
            "R2 dummyindex/cli/__init__.py:0 -> dummyindex.evolve.evolve_learning (stale)",
        ],
        id="root-pair-not-lazy-and-stale",
    ),
    pytest.param(
        {
            "dummyindex/evolve/a.py": "from dummyindex.context.x import _hidden\n",
            "dummyindex/context/x.py": "",
        },
        ["R3 dummyindex/evolve/a.py:1 -> dummyindex.context.x (_hidden)"],
        id="cross-layer-private-name",
    ),
    pytest.param(
        {
            "dummyindex/evolve/a.py": "from dummyindex.context import x\nx._hidden()\n",
            "dummyindex/context/x.py": "",
        },
        ["R3 dummyindex/evolve/a.py:2 -> dummyindex.context.x (_hidden)"],
        id="cross-layer-alias-private-read",
    ),
    pytest.param(
        {
            "dummyindex/evolve/a.py": "from dummyindex.evolve.b import _h\n",
            "dummyindex/evolve/b.py": "",
            "dummyindex/context/x.py": "",
        },
        [],
        id="same-layer-private-name-allowed",
    ),
    pytest.param(
        {
            "dummyindex/evolve/a.py": "from dummyindex.context import x\nx.__file__\n",
            "dummyindex/context/x.py": "",
        },
        [],
        id="cross-layer-dunder-read-allowed",
    ),
    pytest.param(
        {
            "dummyindex/context/domains/user.py": "from dummyindex.context.domains.probation import session_block\n",
            "dummyindex/context/domains/probation/__init__.py": "",
        },
        [
            "R5 dummyindex/context/domains/probation/__init__.py:0 -> "
            "dummyindex/context/domains/probation/__init__.py (exists)",
            "R5 dummyindex/context/domains/user.py:1 -> dummyindex.context.domains.probation (session_block)",
        ],
        id="old-evolve-path-import-and-old-file",
    ),
    pytest.param(
        {"dummyindex/context/domains/evolve_gate.py": ""},
        [
            "R5 dummyindex/context/domains/evolve_gate.py:0 -> dummyindex/context/domains/evolve_gate.py (exists)"
        ],
        id="old-evolve-file-exists",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(("files", "expected"), CASES)
def test_forbidden_form_reports_exact_message(
    tmp_path: Path, files: dict[str, str], expected: list[str]
) -> None:
    assert violations(_tree(tmp_path, files)) == sorted(expected)


@pytest.mark.unit
def test_allowed_tree_reports_nothing(tmp_path: Path) -> None:
    files = {
        "dummyindex/context/user.py": (
            "from dummyindex.shared.atomic_io import write_text_atomic\n\n\ndef helper():\n    pass\n"
        ),
        "dummyindex/shared/atomic_io.py": "import os\nfrom pathlib import Path\n\n\ndef write_text_atomic():\n    pass\n",
        "dummyindex/shared/errors.py": "class EvolveError(Exception):\n    pass\n",
        "dummyindex/shared/lesson/rules.py": "from dummyindex.shared.errors import EvolveError\n",
        "dummyindex/evolve/__init__.py": "",
        "dummyindex/evolve/user.py": (
            "from dummyindex.shared.errors import EvolveError\nfrom dummyindex.context.user import helper\n"
        ),
        "dummyindex/evolve/probation/__init__.py": "def session_block():\n    pass\n",
        "dummyindex/evolve/cli/evolve.py": "def run():\n    pass\n",
        "dummyindex/evolve/evolve_learning.py": "def learn_after_closeout():\n    pass\n",
        "dummyindex/cli/__init__.py": (
            "def _probation_block():\n"
            "    from dummyindex.evolve.probation import session_block\n"
            "    return session_block\n\n\n"
            "def _closeout_learning():\n"
            "    from dummyindex.evolve.evolve_learning import learn_after_closeout\n"
            "    return learn_after_closeout\n\n\n"
            "def _run_evolve():\n"
            "    from dummyindex.evolve.cli.evolve import run\n"
            "    return run\n"
        ),
    }
    assert violations(_tree(tmp_path, files)) == []


@pytest.mark.unit
def test_real_tree_has_no_violations() -> None:
    assert violations(REPO_ROOT) == []


@pytest.mark.unit
def test_real_tree_scans_every_module() -> None:
    assert len(scan(REPO_ROOT).files) == len(list((REPO_ROOT / PKG).rglob("*.py")))


@pytest.mark.unit
def test_real_tree_has_every_allowed_direction() -> None:
    edges = scan(REPO_ROOT).edges
    assert any(
        edge.layer == "context" and edge.module.startswith("dummyindex.shared")
        for edge in edges
    )
    assert any(
        edge.layer == "evolve" and edge.module.startswith("dummyindex.shared")
        for edge in edges
    )
    assert any(
        edge.layer == "evolve" and edge.module.startswith("dummyindex.context")
        for edge in edges
    )
    assert any(
        edge.path == "dummyindex/cli/__init__.py"
        and edge.lazy
        and edge.module.startswith("dummyindex.evolve")
        for edge in edges
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "module",
    [
        "dummyindex.shared",
        "dummyindex.shared.guard",
        "dummyindex.shared.atomic_io",
        "dummyindex.shared.lesson",
        "dummyindex.evolve",
        "dummyindex.evolve.cli.evolve",
        "dummyindex.evolve.cli.evolve_probation",
    ],
)
def test_fresh_interpreter_imports_module(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_fresh_interpreter_cli_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "dummyindex", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
