"""Guard tests: the LLM judgment stays OUT of the eval domain code.

The equip eval stage keeps a hard split — the deterministic scoring/serialize
artifact lives in ``dummyindex/context/domains/equip/eval/`` (pure), and the
LLM judgment ("would a tool described as X fire on prompt Y?") lives in the
``dummyindex-equip`` skill markdown, fed into the domain only as in-memory
:class:`TriggerObservation` data. This module proves both halves of that spine:

1. A static **AST import-scan** of every ``eval/*.py`` file asserts none of them
   import a subprocess / network / LLM-call surface — so the domain can never
   shell out or reach the network to make a firing decision.
2. A positive **purity test** runs ``score_run`` with ``builtins.open`` AND
   ``pathlib.Path.read_text`` monkeypatched to raise, proving trigger decisions
   arrive only as in-memory data and are never read from disk.

Both are ``unit`` (pure, in-process, no I/O — the AST scan reads its own source
via the imported package's ``__file__``, not the build pipeline).
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

from dummyindex.context.domains.equip import eval as eval_pkg
from dummyindex.context.domains.equip.eval import (
    EvalCase,
    EvalOutcome,
    EvalResult,
    TriggerObservation,
    score_run,
)

# Subprocess + network + LLM-call surfaces. If the eval domain imports any of
# these it could shell out or reach the network to make a firing decision —
# exactly the "LLM judge in code" the spine forbids.
FORBIDDEN_MODULES: frozenset[str] = frozenset(
    {
        "subprocess",
        "socket",
        "ssl",
        "urllib",
        "http",
        "requests",
        "httpx",
        "aiohttp",
        "urllib3",
        "ftplib",
        "smtplib",
        "telnetlib",
        "asyncio",
    }
)

# An empty glob would let the scan vacuously pass — pin the real floor. The
# package is the canonical trio plus enums/errors/score/cases: 6 modules today.
MIN_SCANNED_FILES = 5


def _eval_package_dir() -> Path:
    """Resolve the eval package directory robustly via the imported package."""
    pkg_file = eval_pkg.__file__
    assert pkg_file is not None, "eval package has no __file__ to resolve"
    return Path(pkg_file).parent


def _top_level_imports(source: str) -> set[str]:
    """Top-level module of every absolute import in one source file.

    ``import urllib.request`` -> ``urllib``; ``from http import client`` ->
    ``http``. Relative imports (``from . import x``, ``node.level > 0``) are
    intra-package and never network/subprocess surfaces, so they are ignored.
    """
    modules: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import — intra-package, skip
            if node.module:
                modules.add(node.module.split(".", 1)[0])
    return modules


@pytest.mark.unit
def test_eval_package_imports_no_subprocess_or_network() -> None:
    """AST-scan every ``eval/*.py``: no subprocess / network / LLM-call import."""
    pkg_dir = _eval_package_dir()
    py_files = sorted(pkg_dir.glob("*.py"))

    # Guard against a vacuous pass on an empty / mis-resolved glob.
    assert len(py_files) >= MIN_SCANNED_FILES, (
        f"expected >= {MIN_SCANNED_FILES} eval modules to scan, "
        f"found {len(py_files)} under {pkg_dir}"
    )

    offenders: list[tuple[str, str]] = []
    for py_file in py_files:
        source = py_file.read_text(encoding="utf-8")
        for module in sorted(_top_level_imports(source) & FORBIDDEN_MODULES):
            offenders.append((py_file.name, module))

    assert not offenders, (
        "eval domain modules must not import a subprocess/network/LLM-call "
        f"surface (LLM judgment belongs in the skill, not code); found: {offenders}"
    )


@pytest.mark.unit
def test_score_run_is_pure_with_filesystem_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``score_run`` scores an in-memory suite with the filesystem turned off.

    Monkeypatch ``builtins.open`` and ``pathlib.Path.read_text`` to raise, then
    score a mixed fixture: any disk read would blow up. A clean, correct
    :class:`EvalResult` proves trigger decisions arrive only as in-memory
    :class:`TriggerObservation` data, never read from disk.
    """

    def _no_open(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(
            "score_run must not open a file (LLM judge stays out of code)"
        )

    def _no_read_text(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("score_run must not read from disk")

    monkeypatch.setattr(builtins, "open", _no_open)
    monkeypatch.setattr(Path, "read_text", _no_read_text)

    cases = (
        EvalCase(
            case_id="pos", prompt="synthetic trigger prompt", expects_trigger=True
        ),
        EvalCase(case_id="neg", prompt="synthetic decoy prompt", expects_trigger=False),
    )
    observations = (
        TriggerObservation(case_id="pos", fired=True),  # TP
        TriggerObservation(case_id="neg", fired=False),  # TN
    )

    result = score_run(cases, observations, tool_name="fixture-tool")

    assert isinstance(result, EvalResult)
    assert result.tool_name == "fixture-tool"
    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.accuracy == 1.0
    assert result.misfires == ()
    assert dict(result.cases) == {
        "pos": EvalOutcome.TRUE_POSITIVE,
        "neg": EvalOutcome.TRUE_NEGATIVE,
    }
