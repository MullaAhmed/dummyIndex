"""Real file/database adapters; no reads from the developer's host history."""

import json
import sqlite3
from pathlib import Path

import pytest

from dummyindex.context.domains.evidence import expose_case, read_ledger, scan_hosts
from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.usage.transcripts import encode_project_slug


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_hosts_are_project_scoped_incremental_and_fork_deduplicated(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    projects = tmp_path / "claude"
    row = {
        "type": "user",
        "cwd": str(root),
        "uuid": "one",
        "message": {"content": "Wrong, use the accepted contract instead."},
    }
    first = projects / encode_project_slug(root) / "one.jsonl"
    _jsonl(
        first,
        [
            row,
            {**row, "uuid": "meta", "isMeta": True},
            {
                **row,
                "uuid": "injected",
                "message": {"content": "# AGENTS.md instructions\nwrong instead"},
            },
        ],
    )
    _jsonl(first.with_name("fork.jsonl"), [row])
    _jsonl(projects / "other-project" / "foreign.jsonl", [{**row, "uuid": "other"}])
    sessions = tmp_path / "codex"
    _jsonl(
        sessions / "one.jsonl",
        [
            {"type": "session_meta", "payload": {"cwd": str(root)}},
            {
                "type": "event_msg",
                "id": "codex-one",
                "payload": {
                    "type": "user_message",
                    "message": "This is wrong, do it instead.",
                },
            },
        ],
    )
    _jsonl(
        sessions / "other.jsonl",
        [
            {"type": "session_meta", "payload": {"cwd": str(tmp_path / "other")}},
            {
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "wrong instead"},
            },
        ],
    )
    assert (
        scan_hosts(context, claude_projects=projects, codex_sessions=sessions)["added"]
        == 2
    )
    assert (
        scan_hosts(context, claude_projects=projects, codex_sessions=sessions)["added"]
        == 0
    )
    with first.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({**row, "uuid": "two"}))
    assert scan_hosts(context, claude_projects=projects)["added"] == 0
    with first.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    assert scan_hosts(context, claude_projects=projects)["added"] == 1
    persisted = (context / "gc/evidence.json").read_text(encoding="utf-8")
    assert "accepted contract" not in persisted
    assert str(root) not in persisted


def test_codex_readonly_database_and_jsonl_share_native_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    state, history = tmp_path / "state.sqlite", tmp_path / "history.sqlite"
    with sqlite3.connect(state) as db:
        db.execute("CREATE TABLE threads(id TEXT,cwd TEXT)")
        db.executemany(
            "INSERT INTO threads VALUES (?,?)",
            [("mine", str(root)), ("foreign", str(tmp_path / "foreign"))],
        )
    with sqlite3.connect(history) as db:
        db.execute(
            "CREATE TABLE thread_items(thread_id TEXT,item_id TEXT,item_type TEXT,item_json TEXT)"
        )
        for thread, identity in (("mine", "one"), ("foreign", "two")):
            db.execute(
                "INSERT INTO thread_items VALUES (?,?,?,?)",
                (
                    thread,
                    identity,
                    "userMessage",
                    json.dumps(
                        {
                            "content": [
                                {"type": "text", "text": "Wrong, do this instead."}
                            ]
                        }
                    ),
                ),
            )
    before = (state.read_bytes(), history.read_bytes())
    assert scan_hosts(context, codex_state=state, codex_history=history)["added"] == 1
    assert scan_hosts(context, codex_state=state, codex_history=history)["added"] == 0
    assert before == (state.read_bytes(), history.read_bytes())
    sessions = tmp_path / "sessions"
    _jsonl(
        sessions / "one.jsonl",
        [
            {"type": "session_meta", "payload": {"cwd": str(root)}},
            {
                "type": "response_item",
                "id": "one",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Wrong, do this instead."}
                    ],
                },
            },
        ],
    )
    assert scan_hosts(context, codex_sessions=sessions)["added"] == 0


def test_lineage_survives_raw_eviction_and_blocks_split_laundering(
    tmp_path: Path,
) -> None:
    context = tmp_path / ".context"
    context.mkdir()
    expose_case(context, "original", split="train")
    expose_case(context, "derived", split="validation", derived_from=("original",))
    with pytest.raises(EvolveError, match="ancestor"):
        expose_case(context, "grandchild", split="heldout", derived_from=("derived",))
    expose_case(context, "clean", split="heldout", derived_from=("not-yet-used",))
    with pytest.raises(EvolveError, match="held-out"):
        expose_case(context, "not-yet-used", split="train")
    assert read_ledger(context)["exposure"]["original"]["splits"] == ["train"]


def test_unknown_database_schema_does_not_advance_cursor(tmp_path: Path) -> None:
    context = tmp_path / ".context"
    context.mkdir()
    state, history = tmp_path / "state.sqlite", tmp_path / "history.sqlite"
    for path in (state, history):
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE unknown(id TEXT)")
    with pytest.raises(EvolveError, match="unsupported"):
        scan_hosts(context, codex_state=state, codex_history=history)
    assert read_ledger(context)["cursors"] == {}


@pytest.mark.parametrize("first, second", [("train", "heldout"), ("heldout", "train")])
def test_byte_identical_case_alias_cannot_cross_splits(tmp_path, first, second):
    import hashlib

    context = tmp_path / ".context"
    context.mkdir()
    fingerprint = hashlib.sha256(b"identical actual case").hexdigest()
    expose_case(context, "original", split=first, content_sha256=fingerprint)
    with pytest.raises(EvolveError, match="held-out"):
        expose_case(context, "renamed-copy", split=second, content_sha256=fingerprint)
