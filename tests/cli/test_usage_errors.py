r"""Mandatory-flag errors carry a usage pointer.

Terse one-line errors ("--from <id> and --into <id> are both required") gave the
agent nothing to act on, so it probed by running the verb bare — which for equip
used to EXECUTE. Every required-flag / unknown-arg exit now appends a
`run \`dummyindex context <cmd> --help\` for usage` hint, centralised in
``cli.common.usage_error``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.cli import dispatch


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [
        ["features-merge"],
        ["features-rename"],
        ["scaffold-feature"],
        ["build"],
        ["council-batch"],
        ["conventions-write"],
    ],
)
def test_required_flag_error_points_at_help(
    argv: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path)
    code = dispatch([*argv, "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 2, f"{argv} should exit 2"
    assert "--help" in err, f"{argv} error gives no usage pointer:\n{err}"
    assert argv[0] in err, f"{argv} hint names the wrong command:\n{err}"
    assert _snapshot(tmp_path) == before, f"{argv} mutated the cwd"


@pytest.mark.unit
def test_usage_error_helper_shape(capsys: pytest.CaptureFixture[str]) -> None:
    from dummyindex.cli.common import usage_error

    code = usage_error("features-merge", "--from <id> is required")
    err = capsys.readouterr().err
    assert code == 2
    assert "error: --from <id> is required" in err
    assert "dummyindex context features-merge --help" in err


@pytest.mark.unit
def test_kv_parser_keeps_recognized_but_disallowed_flags_as_leftovers() -> None:
    from dummyindex.cli.common import parse_kv_flags

    parsed, leftover = parse_kv_flags(
        ["--feature", "auth", "--platform=codex"], allowed={"--feature"}
    )

    assert parsed == {"feature": "auth"}
    assert leftover == ["--platform=codex"]


@pytest.mark.unit
def test_kv_parser_does_not_consume_an_option_as_a_missing_value() -> None:
    from dummyindex.cli.common import parse_kv_flags

    parsed, leftover = parse_kv_flags(
        ["--note", "--platform=codex"], allowed={"--note"}
    )

    assert parsed == {}
    assert leftover == ["--note", "--platform=codex"]


@pytest.mark.unit
def test_value_parsers_require_equals_for_option_looking_literal_values() -> None:
    from dummyindex.cli.common import (
        parse_kv_flags,
        parse_path_and_root,
        pull_repeatable_flag,
    )

    scope, explicit_root, rest = parse_path_and_root(
        ["--root", "--platform=codex", "--docs", "--manual"]
    )
    doc_values, rest = pull_repeatable_flag(rest, "docs")
    parsed, leftover = parse_kv_flags(rest, allowed={"--platform"})

    assert scope == Path(".")
    assert explicit_root is None
    assert doc_values == []
    assert parsed == {"platform": "codex"}
    assert leftover == ["--root", "--docs", "--manual"]

    doc_values, rest = pull_repeatable_flag(["--docs=--manual"], "docs")
    parsed, leftover = parse_kv_flags(["--note=--literal"], allowed={"--note"})
    assert doc_values == ["--manual"]
    assert rest == []
    assert parsed == {"note": "--literal"}
    assert leftover == []


@pytest.mark.integration
def test_init_missing_docs_value_cannot_swallow_platform_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    code = dispatch(
        [
            "init",
            "--root",
            str(tmp_path),
            "--docs",
            "--platform=codex",
            "--no-hooks",
        ]
    )

    assert code == 2
    assert "--docs" in capsys.readouterr().err
    assert not (tmp_path / ".context").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.integration
def test_kv_command_does_not_swallow_unsupported_platform_as_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    feature_dir = tmp_path / ".context" / "features" / "auth"
    feature_dir.mkdir(parents=True)
    log_path = feature_dir / "council" / "_council-log.json"

    code = dispatch(
        [
            "council-log",
            "--root",
            str(tmp_path),
            "--feature",
            "auth",
            "--stage",
            "1",
            "--agent",
            "architect",
            "--status",
            "complete",
            "--note",
            "--platform=codex",
        ]
    )

    assert code == 2
    assert "--platform=codex" in capsys.readouterr().err
    assert not log_path.exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [
        ["reconcile"],
        ["reality-check"],
        ["features-merge"],
        ["flow-remove"],
        ["section-write"],
        ["scaffold-feature"],
        ["assign-files"],
        ["unassign-files"],
        ["features-remove"],
        ["mark-enriched"],
        ["doc-reorg", "guard"],
        ["dev-pick"],
        ["council-batch"],
        ["council-log"],
        ["council-log", "backfill"],
        ["conventions-write"],
    ],
)
def test_kv_subcommands_reject_unsupported_platform_flag(
    argv: list[str],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = dispatch([*argv, "--root", str(tmp_path), "--platform", "codex"])

    assert code == 2
    assert "--platform" in capsys.readouterr().err
