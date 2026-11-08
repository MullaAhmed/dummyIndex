"""`sessions list` domain: states, identity, bounds, tolerant parsing.

Fixtures are copies of dummyPlane's synthetic session store
(`tests/fixtures/sessions/projects`, described in its README). They are
staged into tmp_path and their mtimes set explicitly, so the 5-minute
liveness window is deterministic.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dummyindex.context.domains import sessions
from dummyindex.context.domains.sessions import list_sessions
from tests.paths import FIXTURES_DIR

FIXTURE_PROJECTS = FIXTURES_DIR / "sessions" / "projects"
NOW = datetime(2026, 3, 1, 10, 1, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(seconds=30)).timestamp()
OLD = (NOW - timedelta(hours=1)).timestamp()

ACTIVE_SID = "11111111-1111-4111-8111-111111111111"
FINISHED_SID = "22222222-2222-4222-8222-222222222222"
SIDE_SID = "33333333-3333-4333-8333-333333333333"
MALFORMED_SID = "44444444-4444-4444-8444-444444444444"
AGENT_ID = "aaaa1111bbbb2222c"


def _stage(tmp_path: Path, *, active_recent: bool = False) -> Path:
    """Copy the fixture store under tmp_path/projects; every file gets an old
    mtime, and the active session's main file gets a recent one on request."""
    projects = tmp_path / "projects"
    shutil.copytree(FIXTURE_PROJECTS, projects)
    for path in projects.rglob("*"):
        if path.is_file():
            os.utime(path, (OLD, OLD))
    if active_recent:
        active = projects / "C--Fixture-active-app" / f"{ACTIVE_SID}.jsonl"
        os.utime(active, (RECENT, RECENT))
    return projects


def _by_key(items: list[dict]) -> dict[tuple[str, str | None], dict]:
    return {(i["session_id"], i["agent_id"]): i for i in items}


def _codes(item: dict) -> list[str]:
    return [w["code"] for w in item["warnings"]]


@pytest.mark.unit
def test_recent_tool_use_session_is_active_and_unknown_fields_skipped(
    tmp_path: Path,
) -> None:
    items = _by_key(list_sessions(_stage(tmp_path, active_recent=True), now=NOW))
    active = items[(ACTIVE_SID, None)]
    assert active["state"] == "active"
    assert active["cwd"] == "C:\\Fixture\\active-app"
    # queue-operation is an unknown record type: skipped with no warning.
    assert active["warnings"] == []
    assert active["started_at"] == "2026-03-01T10:00:00.000000+00:00"
    assert active["last_event_at"] == "2026-03-01T10:00:04.000000+00:00"


@pytest.mark.unit
def test_old_tool_use_session_is_unknown_with_warning(tmp_path: Path) -> None:
    items = _by_key(list_sessions(_stage(tmp_path), now=NOW))
    item = items[(ACTIVE_SID, None)]
    assert item["state"] == "unknown"
    assert _codes(item) == ["unknown_state"]


@pytest.mark.unit
def test_finished_session_uses_record_cwd_not_folder_name(tmp_path: Path) -> None:
    items = _by_key(list_sessions(_stage(tmp_path), now=NOW))
    item = items[(FINISHED_SID, None)]
    assert item["state"] == "finished"
    # Folder is C--Fixture-My-Projects-finished-app; the record cwd has a space.
    assert item["cwd"] == "C:\\Fixture\\My Projects\\finished app"
    assert item["warnings"] == []


@pytest.mark.unit
def test_subagent_is_a_child_keyed_by_agent_id(tmp_path: Path) -> None:
    items = _by_key(list_sessions(_stage(tmp_path), now=NOW))
    parent = items[(SIDE_SID, None)]
    child = items[(SIDE_SID, AGENT_ID)]
    assert parent["state"] == "finished"  # last assistant is end_turn
    assert parent["parent_session_id"] is None
    assert child["state"] == "finished"  # meta.finished is true
    assert child["agent_type"] == "Explore"
    assert child["parent_session_id"] == SIDE_SID
    assert child["session_id"] == SIDE_SID
    assert child["warnings"] == []


@pytest.mark.unit
def test_malformed_session_is_unknown_with_counted_warning_and_no_exception(
    tmp_path: Path,
) -> None:
    items = _by_key(list_sessions(_stage(tmp_path), now=NOW))
    item = items[(MALFORMED_SID, None)]
    assert item["state"] == "unknown"
    assert item["cwd"] == "D:\\Fixture\\malformed.app"
    codes = _codes(item)
    assert codes[0] == "unparseable_line"
    # One warning for two bad lines: the truncated JSON and the bare array.
    assert item["warnings"][0]["message"].startswith("2 unparseable lines")
    assert "unknown_state" in codes


@pytest.mark.unit
def test_child_with_fresh_unfinished_meta_is_active(tmp_path: Path) -> None:
    projects = _stage(tmp_path)
    meta = (
        projects
        / "C--Fixture-sidechain-app"
        / SIDE_SID
        / "subagents"
        / f"agent-{AGENT_ID}.meta.json"
    )
    meta.write_text(json.dumps({"agentType": "Plan", "finished": False}), "utf-8")
    child_jsonl = meta.with_name(f"agent-{AGENT_ID}.jsonl")
    os.utime(child_jsonl, (RECENT, RECENT))
    child = _by_key(list_sessions(projects, now=NOW))[(SIDE_SID, AGENT_ID)]
    assert child["state"] == "active"
    assert child["agent_type"] == "Plan"


@pytest.mark.unit
def test_child_without_meta_is_unknown_with_missing_meta(tmp_path: Path) -> None:
    projects = _stage(tmp_path)
    sub = projects / "C--Fixture-sidechain-app" / SIDE_SID / "subagents"
    (sub / f"agent-{AGENT_ID}.meta.json").unlink()
    child = _by_key(list_sessions(projects, now=NOW))[(SIDE_SID, AGENT_ID)]
    assert child["state"] == "unknown"
    assert child["agent_type"] is None
    assert _codes(child) == ["missing_meta"]


@pytest.mark.unit
def test_unparseable_only_file_is_unknown_not_an_error(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    folder = projects / "C--Junk"
    folder.mkdir(parents=True)
    path = folder / "55555555-5555-4555-8555-555555555555.jsonl"
    path.write_text("not json at all\n[1, 2]\n", encoding="utf-8")
    os.utime(path, (OLD, OLD))
    (item,) = list_sessions(projects, now=NOW)
    assert item["state"] == "unknown"
    assert item["cwd"] is None
    assert "unparseable_session" in _codes(item)
    assert "unparseable_line" in _codes(item)
    assert "missing_cwd" in _codes(item)
    # session_id is the file stem, which needs no record to exist.
    assert item["session_id"] == "55555555-5555-4555-8555-555555555555"
    assert "session_id_mismatch" not in _codes(item)


@pytest.mark.unit
def test_empty_session_is_active_when_recent_and_unknown_otherwise(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    folder = projects / "C--Empty"
    folder.mkdir(parents=True)
    path = folder / "66666666-6666-4666-8666-666666666666.jsonl"
    path.write_bytes(b"")
    os.utime(path, (RECENT, RECENT))
    (item,) = list_sessions(projects, now=NOW)
    assert item["state"] == "active"
    os.utime(path, (OLD, OLD))
    (item,) = list_sessions(projects, now=NOW)
    assert item["state"] == "unknown"
    assert "empty_session" in _codes(item)


@pytest.mark.unit
def test_root_filter_is_by_record_cwd_and_respects_path_boundaries(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    for name, cwd in (("a", tmp_path / "a"), ("ab", tmp_path / "ab")):
        folder = projects / name
        folder.mkdir(parents=True)
        record = {
            "type": "assistant",
            "sessionId": f"sid-{name}",
            "cwd": str(cwd),
            "timestamp": "2026-03-01T10:00:00.000Z",
            "message": {"stop_reason": "end_turn"},
        }
        (folder / f"sid-{name}.jsonl").write_text(json.dumps(record) + "\n", "utf-8")
    items = list_sessions(projects, now=NOW, root=tmp_path / "a")
    assert [i["session_id"] for i in items] == ["sid-a"]


@pytest.mark.unit
def test_missing_projects_root_is_an_empty_listing(tmp_path: Path) -> None:
    assert list_sessions(tmp_path / "nope", now=NOW) == []


@pytest.mark.unit
def test_subagent_listing_is_capped_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sessions, "MAX_SUBAGENTS_PER_SESSION", 0)
    items = list_sessions(_stage(tmp_path), now=NOW)
    parent = _by_key(items)[(SIDE_SID, None)]
    assert (SIDE_SID, AGENT_ID) not in _by_key(items)
    assert "subagents_truncated" in _codes(parent)


@pytest.mark.unit
def test_exhausted_budget_refuses_transcript_but_keeps_meta_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The main file (2241 bytes) is always charged, which exhausts a 1500-byte
    # budget. The subagent transcript is refused, but its meta sidecar is not:
    # the state still comes from meta.finished, and the loss is reported.
    monkeypatch.setattr(sessions, "MAX_BYTES_PER_SESSION", 1500)
    child = _by_key(list_sessions(_stage(tmp_path), now=NOW))[(SIDE_SID, AGENT_ID)]
    assert child["state"] == "finished"
    assert child["agent_type"] == "Explore"
    assert child["cwd"] == "C:\\Fixture\\sidechain-app"  # parent's cwd
    assert _codes(child) == ["read_limit_reached"]


@pytest.mark.unit
def test_large_transcript_reads_only_head_and_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sessions, "WINDOW_BYTES", 4096)
    monkeypatch.setattr(sessions, "_WHOLE_FILE_MAX", 2 * 4096)
    folder = tmp_path / "projects" / "C--Big"
    folder.mkdir(parents=True)
    path = folder / "77777777-7777-4777-8777-777777777777.jsonl"
    lines = [
        json.dumps(
            {
                "type": "user",
                "sessionId": "77777777-7777-4777-8777-777777777777",
                "cwd": "C:\\Big",
                "timestamp": "2026-03-01T10:00:00.000Z",
            }
        )
    ]
    lines += [
        json.dumps({"type": "filler", "pad": "x" * 200, "n": i}) for i in range(400)
    ]
    lines.append(
        json.dumps(
            {
                "type": "assistant",
                "sessionId": "77777777-7777-4777-8777-777777777777",
                "timestamp": "2026-03-01T10:05:00.000Z",
                "message": {"stop_reason": "end_turn"},
            }
        )
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.utime(path, (OLD, OLD))

    read = sessions._read_transcript(path, path.stat().st_size)
    assert len(read.records) < len(lines)  # the middle was never read
    (item,) = list_sessions(tmp_path / "projects", now=NOW)
    assert item["state"] == "finished"
    assert item["cwd"] == "C:\\Big"
    assert item["last_event_at"] == "2026-03-01T10:05:00.000000+00:00"


@pytest.mark.unit
def test_items_are_sorted_newest_first(tmp_path: Path) -> None:
    items = list_sessions(_stage(tmp_path), now=NOW)
    stamps = [i["last_event_at"] or "" for i in items]
    assert stamps == sorted(stamps, reverse=True)


@pytest.mark.unit
def test_forked_transcript_is_identified_by_its_file_stem(tmp_path: Path) -> None:
    # Real store case: a fork in the same folder copies the parent's records,
    # so its first sessionId names the parent. Identity must stay distinct.
    parent = "aaaaaaaa-0000-4000-8000-000000000001"
    fork = "bbbbbbbb-0000-4000-8000-000000000002"
    folder = tmp_path / "projects" / "C--Forked"
    folder.mkdir(parents=True)

    def record(sid: str, stamp: str, stop: str) -> str:
        return json.dumps(
            {
                "type": "assistant",
                "sessionId": sid,
                "timestamp": stamp,
                "cwd": "C:/Forked",
                "message": {"stop_reason": stop},
            }
        )

    shared = record(parent, "2026-03-01T10:00:00.000Z", "end_turn")
    later = record(fork, "2026-03-01T10:02:00.000Z", "end_turn")
    (folder / f"{parent}.jsonl").write_text(shared + "\n", encoding="utf-8")
    (folder / f"{fork}.jsonl").write_text(
        shared + "\n" + later + "\n", encoding="utf-8"
    )
    for name in (parent, fork):
        os.utime(folder / f"{name}.jsonl", (OLD, OLD))

    items = list_sessions(tmp_path / "projects", now=NOW)
    by_id = {i["session_id"]: i for i in items}
    assert len(items) == 2
    assert set(by_id) == {parent, fork}
    assert by_id[fork]["state"] == "finished"
    assert by_id[fork]["last_event_at"] == "2026-03-01T10:02:00.000000+00:00"
    assert "session_id_mismatch" in _codes(by_id[fork])
    assert "session_id_mismatch" not in _codes(by_id[parent])
