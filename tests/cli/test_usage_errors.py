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
