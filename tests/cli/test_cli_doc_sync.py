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

from dummyindex.context.domains.equip import SCHEMA_VERSION
from dummyindex.context.domains.equip.enums import EquipVerb
from dummyindex.context.enums import ContextSubcommand
from tests.paths import REPO_ROOT

_REPO_ROOT = REPO_ROOT
_COMMAND_REFERENCE = _REPO_ROOT / "docs" / "COMMANDS.md"
_CLI_GUIDE = _REPO_ROOT / "docs" / "guide" / "07-cli.md"
_SHIPPED_SKILL = _REPO_ROOT / "dummyindex" / "skills" / "skill.md"
_DEFAULT_PLUGIN_DOCS = (
    _COMMAND_REFERENCE,
    _CLI_GUIDE,
    _SHIPPED_SKILL,
)

# The build verb surface that must stay documented (these drift WITHIN the
# `build` subcommand, below name granularity, so they need their own guard).
_BUILD_VERBS = ("--next", "--next-wave", "--check", "--skip", "--status")


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
    assert not missing, f"`dummyindex context --help` has no usage line for: {missing}"


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


@pytest.mark.unit
def test_top_level_help_labels_default_plugin_opt_out_alias(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The canonical spelling leads; the old spelling remains labeled."""
    from dummyindex.__main__ import _print_help

    _print_help()
    out = " ".join(capsys.readouterr().out.split())
    assert "[--no-default-plugins] [--no-superpowers]" in out
    assert (
        "--no-default-plugins skip all default Claude plugins for this run; "
        "--no-superpowers is a compatibility alias."
    ) in out
    assert out.index("--no-default-plugins") < out.index("--no-superpowers")


@pytest.mark.unit
@pytest.mark.parametrize(
    "doc_path",
    _DEFAULT_PLUGIN_DOCS,
    ids=("command-reference", "cli-guide", "shipped-skill"),
)
def test_default_plugin_docs_pin_targets_and_reviewed_trust(
    doc_path: Path,
) -> None:
    """Every shipped long-form surface pins identity and reviewed blast radius."""
    text = doc_path.read_text(encoding="utf-8")
    flat = " ".join(text.split())

    required_tokens = (
        "superpowers@claude-plugins-official",
        "caveman@caveman",
        "JuliusBrussee/caveman@0d95a81d35a9f2d123a5e9430d1cfc43d55f1bb0",
        "i-have-adhd@i-have-adhd",
        "ayghri/i-have-adhd@0241185d6c7f2d0763a988ce52eceb13ea9f5c1f",
        "SessionStart",
        "UserPromptSubmit",
        "Node command hook",
        "runs_code=true",
        "one inert skill",
        "no executable plugin hook",
        "runs_code=false",
    )
    missing = [token for token in required_tokens if token not in flat]
    assert not missing, f"{doc_path.relative_to(_REPO_ROOT)} omits: {missing}"
    assert re.search(r"narrow,? reviewed built-in exception", flat)
    assert "equip" in flat
    assert "approval" in flat


@pytest.mark.unit
@pytest.mark.parametrize(
    "doc_path",
    _DEFAULT_PLUGIN_DOCS,
    ids=("command-reference", "cli-guide", "shipped-skill"),
)
def test_default_plugin_docs_pin_host_scope_and_opt_out_layers(
    doc_path: Path,
) -> None:
    """Host boundaries and the three opt-out scopes cannot drift independently."""
    text = doc_path.read_text(encoding="utf-8")
    flat = " ".join(text.split())

    for token in (
        "--no-default-plugins",
        "--no-superpowers",
        "Codex-only",
        ".claude/**",
        "Claude runner",
        "managed project",
        "global guidance",
        "default_plugins_enabled",
        "enabledPlugins",
        "tombstone",
    ):
        assert token in flat, f"{doc_path.relative_to(_REPO_ROOT)} omits {token!r}"

    assert re.search(
        r"(?i)(?:a )?malformed (?:`.context/config.json`|config) fails closed",
        flat,
    )
    assert re.search(r"(?i)claude.{0,20}`both`", flat)
    assert re.search(r"(?i)one[- ]run.{0,20}all", flat)
    assert re.search(r"(?i)durable.{0,20}all", flat)
    assert re.search(
        r"`default_plugins_enabled`.{0,20}`false`|"
        r"`default_plugins_enabled: false`",
        flat,
    )
    assert re.search(
        r"`enabledPlugins`.{0,80}`false`|`false`.{0,80}`enabledPlugins`", flat
    )
    assert re.search(r"(?i)compatibility alias|legacy", flat)
    assert re.search(
        r"(?i)do not persist|without persisting|neither flag persists", flat
    )


# ----- verb/flag-granularity guards -----------------------------------------
#
# Name-granularity guards (above) miss drift WITHIN a subcommand: equip's
# discover/install verbs and build's --next-wave/--skip flags shipped without a
# usage line, and an embedded `(v2)` literal lagged behind SCHEMA_VERSION. These
# turn that finer drift class into a red test too.


def _context_usage() -> str:
    import contextlib
    import io

    from dummyindex.cli import dispatch

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert dispatch(["--help"]) == 0
    return buf.getvalue()


@pytest.mark.unit
@pytest.mark.parametrize("verb", list(EquipVerb), ids=lambda v: v.value)
def test_usage_documents_every_equip_verb(verb: EquipVerb) -> None:
    """`context --help` AND the guide name every `equip <verb>`."""
    usage = _context_usage()
    pat = rf"equip {re.escape(verb.value)}\b"
    assert re.search(pat, usage), f"`context --help` has no `equip {verb.value}` line"
    guide = _CLI_GUIDE.read_text(encoding="utf-8")
    assert re.search(pat, guide), (
        f"docs/guide/07-cli.md does not document `equip {verb.value}`"
    )


@pytest.mark.unit
@pytest.mark.parametrize("flag", _BUILD_VERBS)
def test_usage_documents_build_verbs(flag: str) -> None:
    """Every build verb flag appears in the build usage block + the guide."""
    usage = _context_usage()
    assert flag in usage, f"`context --help` build block omits {flag}"
    guide = _CLI_GUIDE.read_text(encoding="utf-8")
    assert flag in guide, f"docs/guide/07-cli.md build section omits {flag}"


@pytest.mark.unit
@pytest.mark.parametrize("flag", ["--feature", "--force"])
def test_usage_documents_council_batch_scoping_flags(flag: str) -> None:
    """council-batch gained --feature/--force (scoped + forced re-council); the
    `--help` USAGE block must show them, not just the handler/docstring."""
    usage = _context_usage()
    cb = usage.split("council-batch", 1)[-1][:400]
    assert flag in cb, f"`context --help` council-batch block omits {flag}"


@pytest.mark.unit
def test_usage_equipment_schema_version_current() -> None:
    """The version literal next to equipment.json tracks SCHEMA_VERSION."""
    usage = _context_usage()
    assert f"(v{SCHEMA_VERSION})" in usage, (
        f"`context --help` should show equipment.json (v{SCHEMA_VERSION})"
    )
    guide = _CLI_GUIDE.read_text(encoding="utf-8")
    assert f"schema v{SCHEMA_VERSION}" in guide, (
        f"docs/guide/07-cli.md should say equipment.json schema v{SCHEMA_VERSION}"
    )


@pytest.mark.unit
def test_usage_build_status_names_the_real_loop_closer() -> None:
    """`context --help` must describe build --status's close-the-loop command
    as the actual RECONCILE_HINT, not a stale `rebuild --changed` — the audit
    found the help text and the CLI disagreeing, which made Claude skip the
    (non-destructive) reconcile."""
    from dummyindex.cli.build_loop.waves import RECONCILE_HINT

    usage = _context_usage()
    assert RECONCILE_HINT in usage, (
        f"`context --help` build --status text should name {RECONCILE_HINT!r}"
    )
    assert "rebuild --changed`." not in usage.split("--status reports")[-1][:200], (
        "build --status help still prescribes `rebuild --changed` as the closer"
    )


@pytest.mark.unit
def test_skill_routing_names_every_top_level_command() -> None:
    """The /dummyindex skill's verb-recognition rule lists every CLI command.

    Keeps the skill's routing carve-out in sync with __main__'s real command
    set, so a new top-level command can't silently fall back to being treated
    as an index scope path.
    """
    from dummyindex.__main__ import TOP_LEVEL_COMMANDS

    skill = (_REPO_ROOT / "dummyindex" / "skills" / "skill.md").read_text(
        encoding="utf-8"
    )
    missing = [cmd for cmd in TOP_LEVEL_COMMANDS if cmd not in skill]
    assert not missing, (
        f"dummyindex/skills/skill.md routing rule omits commands: {missing}"
    )
