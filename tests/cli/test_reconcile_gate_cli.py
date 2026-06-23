"""Tests for the `context reconcile-gate` CLI wrapper."""

from __future__ import annotations

import json

from dummyindex.cli import reconcile_gate as cli
from dummyindex.context import reconcile_gate as rg


def test_prints_block_payload(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli, "read_hook_stdin", lambda: {"stop_hook_active": False, "session_id": "s"}
    )
    monkeypatch.setattr(
        cli, "resolve_transcript", lambda hook, root: ("s", tmp_path / "t.jsonl")
    )
    monkeypatch.setattr(
        rg,
        "decide_block",
        lambda **kw: json.dumps({"decision": "block", "reason": "x"}),
    )
    rc = cli.run(["--root", str(tmp_path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out.strip())["decision"] == "block"


def test_returns_zero_and_silent_when_none(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "read_hook_stdin", lambda: {"stop_hook_active": True})
    monkeypatch.setattr(cli, "resolve_transcript", lambda hook, root: ("", None))
    monkeypatch.setattr(rg, "decide_block", lambda **kw: None)
    rc = cli.run(["--root", str(tmp_path)])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_rejects_unknown_argument(capsys, tmp_path):
    rc = cli.run(["--root", str(tmp_path), "--bogus"])
    assert rc == 2
