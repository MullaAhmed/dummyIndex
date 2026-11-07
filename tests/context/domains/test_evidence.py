"""Real file/database adapters; no reads from the developer's host history."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from dummyindex.context.domains import evidence
from dummyindex.context.domains.evidence import (
    digest,
    expose_case,
    read_ledger,
    scan_hosts,
)
from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.context.domains.evolve_promotion import project_lock
from dummyindex.context.domains.observe import ledger as L

CORRECTION = "Wrong, use the accepted contract instead."
SLUG = "proj"


@pytest.fixture(autouse=True)
def _short_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows MAX_PATH: keep the Claude project folder name short."""
    monkeypatch.setattr(evidence, "encode_project_slug", lambda root: SLUG)
    monkeypatch.setattr(evidence, "project_dir_name", lambda root: SLUG)


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _row(root: Path, uuid: str, text: str = CORRECTION) -> dict:
    return {
        "type": "user",
        "userType": "external",
        "cwd": str(root),
        "uuid": uuid,
        "message": {"role": "user", "content": text},
    }


def _empty_or_absent(path: Path) -> bool:
    return not path.exists() or (path.is_dir() and not any(path.iterdir()))


def test_hosts_are_project_scoped_incremental_and_fork_deduplicated(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    projects = tmp_path / "claude"
    row = {
        "type": "user",
        "userType": "external",
        "cwd": str(root),
        "uuid": "one",
        "message": {
            "role": "user",
            "content": "Wrong, use the accepted contract instead.",
        },
    }
    first = projects / SLUG / "one.jsonl"
    _jsonl(
        first,
        [
            row,
            {**row, "uuid": "meta", "isMeta": True},
            {
                **row,
                "uuid": "injected",
                "message": {
                    "role": "user",
                    "content": "# AGENTS.md instructions\nwrong instead",
                },
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
    ledger = L.load(context)
    assert any(c["host"] == "claude" for c in ledger["corrections"].values())
    committed = context / "gc/evidence.json"
    assert not committed.exists() or (
        "accepted contract" not in committed.read_text(encoding="utf-8")
    )
    assert str(root) not in json.dumps(ledger)
    assert _empty_or_absent(context / "gc/evidence")
    assert _empty_or_absent(context / "gc/learning")


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
    context = tmp_path / ".context"
    context.mkdir()
    fingerprint = hashlib.sha256(b"identical actual case").hexdigest()
    expose_case(context, "original", split=first, content_sha256=fingerprint)
    with pytest.raises(EvolveError, match="held-out"):
        expose_case(context, "renamed-copy", split=second, content_sha256=fingerprint)


def test_no_gc_file_holds_raw_session_or_text_digest(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    projects = tmp_path / "claude"
    _jsonl(projects / SLUG / "one.jsonl", [_row(root, "one")])
    assert scan_hosts(context, claude_projects=projects)["added"] == 1
    secrets = [
        hashlib.sha256(b"one").hexdigest(),
        digest("one"),
        hashlib.sha256(CORRECTION.encode()).hexdigest(),
    ]
    gc = context / "gc"
    if gc.exists():
        for path in gc.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                for secret in secrets:
                    assert secret.encode() not in data
    local = json.dumps(L.load(context), sort_keys=True)
    for secret in secrets:
        assert secret not in local


def test_schema_one_committed_ledger_migrates_without_duplicates(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    (context / "gc").mkdir(parents=True)
    projects = tmp_path / "claude"
    legacy_exposure = {
        "case": {"parents": [], "splits": ["train"], "lineage": ["case"]}
    }
    legacy = {
        "schema_version": 1,
        "events": {
            "legacy1": {
                "id": "legacy1",
                "host": "claude",
                "session": "s",
                "kind": "human_correction",
                "origin": "human",
                "timestamp": "2026-01-01T00:00:00Z",
                "content_sha256": "c",
            }
        },
        "cursors": {"old": {"offset": 0}},
        "exposure": legacy_exposure,
    }
    (context / "gc/evidence.json").write_text(json.dumps(legacy), encoding="utf-8")
    _jsonl(projects / SLUG / "mig.jsonl", [_row(root, "mig")])
    scan_hosts(context, claude_projects=projects)
    committed = json.loads((context / "gc/evidence.json").read_text(encoding="utf-8"))
    assert committed["schema_version"] == 2
    assert set(committed) == {"schema_version", "exposure"}
    assert committed["exposure"] == legacy_exposure
    view = read_ledger(context)
    assert "legacy1" in view["events"]
    assert "content_sha256" not in view["events"]["legacy1"]
    assert "session" not in view["events"]["legacy1"]
    assert len(view["events"]) == 2
    assert "old" in view["cursors"]
    again = scan_hosts(context, claude_projects=projects)
    assert again["added"] == 0
    assert len(read_ledger(context)["events"]) == 2


def test_budget_stops_between_files_and_rerun_completes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    projects = tmp_path / "claude"
    slug_dir = projects / SLUG
    for name in ("a", "b", "c"):
        _jsonl(slug_dir / f"{name}.jsonl", [_row(root, f"uuid-{name}")])
    clock = iter([0.0, 0.0, 100.0, 100.0, 100.0, 100.0]).__next__
    partial = scan_hosts(context, claude_projects=projects, budget_s=10, clock=clock)
    assert partial["complete"] is False
    assert len(L.load(context)["cursors"]) == 1
    full = scan_hosts(context, claude_projects=projects)
    assert full["complete"] is True
    assert len(L.load(context)["cursors"]) == 3


def test_unchanged_transcript_is_not_opened_but_touched_one_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    projects = tmp_path / "claude"
    path = projects / SLUG / "fast.jsonl"
    _jsonl(path, [_row(root, "fast")])
    assert scan_hosts(context, claude_projects=projects)["added"] == 1
    opened: list[Path] = []
    real_open = Path.open

    def counting_open(self, *args, **kwargs):
        if self.suffix == ".jsonl" and projects in self.parents:
            opened.append(self)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    assert scan_hosts(context, claude_projects=projects)["added"] == 0
    assert opened == []
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert scan_hosts(context, claude_projects=projects)["added"] == 0
    assert len(opened) >= 1


def test_held_observe_lock_skips_without_writes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    projects = tmp_path / "claude"
    _jsonl(projects / SLUG / "lock.jsonl", [_row(root, "lock")])
    with project_lock(root, lock_name="observe.lock"):
        assert scan_hosts(context, claude_projects=projects) == {"skipped": "locked"}
    assert not (context / "cache/evolution").exists()
    assert not (context / "cache/evidence-sources.json").exists()


def test_kill_switch_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    projects = tmp_path / "claude"
    _jsonl(projects / SLUG / "off.jsonl", [_row(root, "off")])
    monkeypatch.setenv("DUMMYINDEX_EVOLUTION", "off")
    assert scan_hosts(context, claude_projects=projects) == {"disabled": True}
    assert not (context / "cache").exists()
    assert not (context / "gc").exists()


def test_scan_result_reports_null_learning_and_complete(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    projects = tmp_path / "claude"
    _jsonl(projects / SLUG / "res.jsonl", [_row(root, "res")])
    result = scan_hosts(context, claude_projects=projects)
    assert result["learning"] is None
    assert result["complete"] is True


def test_unreadable_transcript_is_skipped_and_scan_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    context = root / ".context"
    context.mkdir(parents=True)
    projects = tmp_path / "claude"
    _jsonl(projects / SLUG / "bad.jsonl", [_row(root, "bad")])
    _jsonl(projects / SLUG / "good.jsonl", [_row(root, "good")])
    real = evidence.import_claude

    def fake(path: Path, *args, **kwargs):
        if path.name == "bad.jsonl":
            raise PermissionError("denied")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(evidence, "import_claude", fake)
    result = scan_hosts(context, claude_projects=projects)
    assert result["complete"] is True
    assert L.load(context)["corrections"]
