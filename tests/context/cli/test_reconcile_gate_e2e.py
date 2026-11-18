"""End-to-end: the `reconcile-gate` CLI emits a block over a drifted repo."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _make_drifted_repo(root: Path) -> None:
    """A `.context/features/<id>/` whose feature.json maps a source file that
    is newer than the (absent) feature docs → drift via mtime."""
    feat = root / ".context" / "features" / "auth"
    feat.mkdir(parents=True)
    (feat / "feature.json").write_text(
        json.dumps({"feature_id": "auth", "files": ["auth.py"]}), encoding="utf-8"
    )
    (root / "auth.py").write_text("x = 1\n", encoding="utf-8")


def _substantial_source_session(root: Path) -> Path:
    """A substantial session (enough output tokens) that actually edited a
    source file — both conditions the gate now requires before blocking."""
    transcript = root / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {"type": "assistant", "message": {"usage": {"output_tokens": 100_000}}}
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Edit",
                            "input": {"file_path": str(root / "auth.py")},
                        }
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return transcript


@pytest.mark.integration
def test_cli_emits_block_for_drifted_repo(tmp_path: Path) -> None:
    _make_drifted_repo(tmp_path)
    transcript = _substantial_source_session(tmp_path)
    stdin = json.dumps(
        {
            "stop_hook_active": False,
            "session_id": "sess1",
            "transcript_path": str(transcript),
        }
    )
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "dummyindex",
            "context",
            "reconcile-gate",
            "--root",
            str(tmp_path),
        ],
        input=stdin,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout.strip())
    assert payload["decision"] == "block"
    assert "auth" in payload["reason"]


@pytest.mark.integration
def test_cli_allows_planning_only_session_on_drifted_repo(tmp_path: Path) -> None:
    """A substantial session that edited NO source (planning/git/tool-update
    only) must NOT be trapped by the gate, even on a drifted repo — inherited
    drift surfaces via the SessionStart report instead (audit cluster C3)."""
    _make_drifted_repo(tmp_path)
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        json.dumps(
            {"type": "assistant", "message": {"usage": {"output_tokens": 100_000}}}
        )
        + "\n",
        encoding="utf-8",
    )
    stdin = json.dumps(
        {
            "stop_hook_active": False,
            "session_id": "sess-planning",
            "transcript_path": str(transcript),
        }
    )
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "dummyindex",
            "context",
            "reconcile-gate",
            "--root",
            str(tmp_path),
        ],
        input=stdin,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == ""  # no block


@pytest.mark.integration
def test_cli_silent_on_reentry(tmp_path: Path) -> None:
    _make_drifted_repo(tmp_path)
    stdin = json.dumps({"stop_hook_active": True})
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "dummyindex",
            "context",
            "reconcile-gate",
            "--root",
            str(tmp_path),
        ],
        input=stdin,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == ""
