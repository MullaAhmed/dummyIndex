"""Guards on what the miner is allowed to write down.

These are the tests for an audit finding, not for a feature. The first cut of
the miner scanned the host's entire transcript store and rendered a
200-character slice of raw tool output into `.context/session-memory/`, which
is git-tracked — so an unrelated private repo's source, and any credential
that had ever appeared in a tool result, were candidates for being committed
here. Everything below exists to keep that from coming back.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from dummyindex.context.domains.memory.miner import (
    mine_and_feed,
    project_dir_name,
    sanitize_signature,
    scan_transcript_store,
)
from dummyindex.context.domains.memory.miner.render import FAILURE_PATTERNS_FILENAME
from dummyindex.context.domains.memory.miner.scope import REDACTED
from dummyindex.context.domains.memory.store import memory_dir

pytestmark = pytest.mark.unit


def _tool_use(call_id: str, name: str, tool_input: dict) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": call_id,
                        "name": name,
                        "input": tool_input,
                    }
                ]
            },
        }
    )


def _tool_result(call_id: str, content: str, *, is_error: bool = False) -> str:
    return json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": content,
                        "is_error": is_error,
                    }
                ]
            },
        }
    )


def _seed_project(project_dir: Path, path_read: str, output: str) -> None:
    lines = []
    for i in range(4):
        lines.append(_tool_use(f"c{i}", "Read", {"file_path": path_read}))
        lines.append(_tool_result(f"c{i}", output, is_error=True))
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "session.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


# --- project scoping -------------------------------------------------------


def test_scan_scoped_to_repo_ignores_other_projects(tmp_path: Path) -> None:
    """A second repo's transcripts must not reach this repo's report."""
    store = tmp_path / "cfg" / "projects"
    mine = tmp_path / "mine"
    other = tmp_path / "other"
    _seed_project(store / project_dir_name(mine), str(mine / "a.py"), "boom")
    _seed_project(store / project_dir_name(other), str(other / "secret.py"), "boom")

    scoped = scan_transcript_store(store, repo_root=mine)
    assert scoped.scanned_sessions == 1
    assert all("secret.py" not in s.signature for s in scoped.signatures)

    pooled = scan_transcript_store(store)
    assert pooled.scanned_sessions == 2


def test_scoping_matches_exactly_not_by_prefix(tmp_path: Path) -> None:
    """Sibling repos share a prefix; a prefix match would leak across them."""
    mine = tmp_path / "mono"
    sibling = tmp_path / "mono-backend"
    store = tmp_path / "cfg" / "projects"
    _seed_project(store / project_dir_name(mine), str(mine / "a.py"), "boom")
    _seed_project(store / project_dir_name(sibling), str(sibling / "leak.py"), "boom")

    report = scan_transcript_store(store, repo_root=mine)
    assert report.scanned_sessions == 1
    assert all("leak.py" not in s.signature for s in report.signatures)


# --- path sanitization -----------------------------------------------------


def test_in_repo_paths_become_relative_and_foreign_paths_are_redacted() -> None:
    root = Path("/srv/repo")
    inside = sanitize_signature(
        'read::{"file_path": "/srv/repo/pkg/mod.py"}', repo_root=root
    )
    assert "pkg/mod.py" in inside
    assert "/srv/repo" not in inside

    outside = sanitize_signature('read::{"file_path": "/etc/shadow"}', repo_root=root)
    assert "/etc/shadow" not in outside
    assert REDACTED in outside


def test_rendered_report_contains_no_absolute_paths(tmp_path: Path) -> None:
    """The end-to-end guarantee: nothing absolute reaches the tracked file."""
    repo = tmp_path / "repo"
    context_dir = repo / ".context"
    store = tmp_path / "cfg"
    _seed_project(
        store / "projects" / project_dir_name(repo),
        str(repo / "deep" / "mod.py"),
        "Error: No such file or directory",
    )

    mine_and_feed(context_dir, store_override=store)
    text = (memory_dir(context_dir) / FAILURE_PATTERNS_FILENAME).read_text(
        encoding="utf-8"
    )

    # No POSIX-absolute path survives anywhere in the rendered body.
    assert not re.search(r"(?<![\w.])/[A-Za-z][^\s\"'`,;)]{2,}", text), text
    assert "deep/mod.py" in text


def test_rendered_report_never_contains_tool_output(tmp_path: Path) -> None:
    """No excerpt of tool output is retained, so no secret can ride along."""
    repo = tmp_path / "repo"
    context_dir = repo / ".context"
    store = tmp_path / "cfg"
    secret = "ghp_EXAMPLETOKENVALUE0000000000000000"
    _seed_project(
        store / "projects" / project_dir_name(repo),
        str(repo / "a.py"),
        f"Error: auth failed for {secret}",
    )

    mine_and_feed(context_dir, store_override=store)
    text = (memory_dir(context_dir) / FAILURE_PATTERNS_FILENAME).read_text(
        encoding="utf-8"
    )
    assert secret not in text
    assert "sample:" not in text


def test_rendered_report_warns_that_edits_are_overwritten(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    context_dir = repo / ".context"
    mine_and_feed(context_dir, store_override=tmp_path / "empty-cfg")
    text = (memory_dir(context_dir) / FAILURE_PATTERNS_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "overwritten" in text.splitlines()[0]
