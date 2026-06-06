"""Doc-sync guards: every ContextSubcommand must be documented everywhere.

The CLI grew three subcommands in v0.15 and two help/doc surfaces silently
lagged (an earlier surface had drifted the same way the release before).
These tests turn that class of drift into a red test instead of an audit
finding. Guarded surfaces:

- ``dummyindex context --help`` — the canonical reference, exercised through
  the public ``dispatch(["--help"])`` path so wrapping/truncation count too.
- ``docs/guide/07-cli.md``     — the public CLI guide ("every command").
- ``dummyindex --help``        — derives its subcommand list from the enum at
  runtime; the test proves the lazy-import path actually renders every name
  (a silent fall-through to its except-branch would otherwise go unnoticed).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from dummyindex.context.enums import ContextSubcommand

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CLI_GUIDE = _REPO_ROOT / "docs" / "guide" / "07-cli.md"


@pytest.mark.unit
def test_usage_documents_every_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each subcommand starts its own usage line in `context --help`."""
    from dummyindex.cli import dispatch

    assert dispatch(["--help"]) == 0
    out = capsys.readouterr().out
    missing = [
        sub.value
        for sub in ContextSubcommand
        if not re.search(rf"^\s*{re.escape(sub.value)}\b", out, re.MULTILINE)
    ]
    assert not missing, (
        f"`dummyindex context --help` has no usage line for: {missing}"
    )


@pytest.mark.unit
def test_cli_guide_documents_every_subcommand() -> None:
    """docs/guide/07-cli.md names every subcommand as a documented command.

    A bare-substring check is deliberately not enough: `preflight` once
    appeared in prose while having no section. Require the full
    `dummyindex context <sub>` command form (the guide's heading style).
    """
    assert _CLI_GUIDE.is_file(), f"CLI guide not found at {_CLI_GUIDE}"
    text = _CLI_GUIDE.read_text(encoding="utf-8")
    missing = [
        sub.value
        for sub in ContextSubcommand
        if f"dummyindex context {sub.value}" not in text
    ]
    assert not missing, f"docs/guide/07-cli.md does not document: {missing}"


@pytest.mark.unit
def test_top_level_help_lists_every_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`dummyindex --help` renders every subcommand via its enum-derived list."""
    from dummyindex.__main__ import _print_help

    _print_help()
    out = capsys.readouterr().out
    missing = [sub.value for sub in ContextSubcommand if sub.value not in out]
    assert not missing, f"top-level --help output is missing: {missing}"
