"""`audit show --json` exposes the workspace directory.

Before this, `show --json` had no `dir` key at all, so locating
`.context/audits/<slug>/` from the payload took shell hacks. Now both `start`
and `show` emit the same repo-root-relative `dir` pointing at the real
workspace.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli import dispatch


@pytest.mark.integration
def test_audit_show_json_has_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".context").mkdir()
    dispatch(
        [
            "audit",
            "start",
            "--describe",
            "audit the cache layer",
            "--model",
            "sonnet-4.6",
            "--slug",
            "cache",
            "--root",
            str(tmp_path),
            "--json",
        ]
    )
    start_out = capsys.readouterr().out
    start_dir = json.loads(start_out)["dir"]

    code = dispatch(
        ["audit", "show", "--slug", "cache", "--root", str(tmp_path), "--json"]
    )
    out = capsys.readouterr().out
    assert code == 0
    payload = json.loads(out)
    assert "dir" in payload, "show --json must expose the workspace dir"
    assert payload["dir"] == start_dir, "start and show must agree on dir"
    assert (tmp_path / payload["dir"]).is_dir(), (
        "dir must resolve to the real workspace from the repo root"
    )
