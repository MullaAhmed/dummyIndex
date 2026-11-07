from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone

import pytest

from dummyindex.context.domains.config import current_dummyindex_version
from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.context.domains.evolve_promotion import project_lock
from dummyindex.context.domains.observe import importer as I
from dummyindex.context.domains.observe import ledger as L

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)
TS = "2026-11-01T10:00:00Z"
RULE_TEXT = (
    '<!-- dummyindex:rule {"id": "r1"} -->\nbody\n<!-- dummyindex:rule:end r1 -->\n'
)
CONV_REL = ".context/conventions/x.md"


def _write(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("".join(json.dumps(row) + "\n" for row in rows))


def _append(path, rows):
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("".join(json.dumps(row) + "\n" for row in rows))


def _human(root, text, uuid):
    return {
        "type": "user",
        "userType": "external",
        "uuid": uuid,
        "timestamp": TS,
        "cwd": str(root),
        "message": {"role": "user", "content": text},
    }


def _call(uuid, tid, name, tool_input):
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": TS,
        "message": {
            "role": "assistant",
            "model": "claude-test",
            "content": [
                {"type": "tool_use", "id": tid, "name": name, "input": tool_input}
            ],
        },
    }


def _read(uuid, tid, path):
    return _call(uuid, tid, "Read", {"file_path": str(path)})


def _result(uuid, tid, text):
    return {
        "type": "user",
        "userType": "external",
        "uuid": uuid,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tid, "content": text}],
        },
    }


def _corrections(led):
    return sorted(led["corrections"].values(), key=lambda rec: rec["turn"])


def _rule_file(root):
    conv = root / ".context" / "conventions" / "x.md"
    conv.parent.mkdir(parents=True)
    conv.write_bytes(RULE_TEXT.encode("utf-8"))
    return conv


def test_injected_meta_internal_and_result_rows_are_not_corrections(tmp_path):
    root = tmp_path
    path = root / "s.jsonl"
    rows = [
        _human(root, "<system-reminder>wrong instead</system-reminder>", "u1"),
        {**_human(root, "wrong instead", "u2"), "isMeta": True},
        {**_human(root, "wrong instead", "u3"), "userType": "internal"},
        _result("u4", "T1", "wrong instead"),
    ]
    _write(path, rows)
    led = L.empty()
    I.import_claude(path, root, {}, led, source_id="src", exposures=[], now=NOW)
    assert led["corrections"] == {}


def test_invisible_unicode_in_tool_result_quarantines_next_correction(tmp_path):
    root = tmp_path
    path = root / "s.jsonl"
    rows = [
        _human(root, "start", "h0"),
        _call("a1", "B1", "Bash", {"command": "echo"}),
        _result("r1", "B1", "out\u200bput"),
        _human(root, "wrong instead", "h1"),
        _human(root, "thanks", "h2"),
        _human(root, "wrong instead again", "h3"),
    ]
    _write(path, rows)
    led = L.empty()
    I.import_claude(path, root, {}, led, source_id="src", exposures=[], now=NOW)
    first, second = _corrections(led)
    assert first["quarantine"] == ["invisible-unicode"]
    assert second["quarantine"] == []


def test_exposed_read_result_is_not_buffered(tmp_path):
    root = tmp_path
    conv = _rule_file(root)
    path = root / "s.jsonl"
    rows = [
        _human(root, "start", "h0"),
        _read("a1", "R1", conv),
        _result("r1", "R1", "<!-- dummyindex:rule x -->"),
        _human(root, "wrong instead", "h1"),
    ]
    _write(path, rows)
    led = L.empty()
    I.import_claude(path, root, {}, led, source_id="src", exposures=[], now=NOW)
    (correction,) = _corrections(led)
    assert correction["quarantine"] == []


def test_read_exposure_then_correction_gives_candidate(tmp_path):
    root = tmp_path
    conv = _rule_file(root)
    path = root / "s.jsonl"
    rows = [
        _human(root, "start", "h0"),
        _read("a1", "R1", conv),
        _result("r1", "R1", "body"),
        _human(root, "wrong instead", "h1"),
    ]
    _write(path, rows)
    led = L.empty()
    exposures, _ = I.import_claude(
        path, root, {}, led, source_id="src", exposures=[], now=NOW
    )
    assert len(exposures) == 1
    exp = exposures[0]
    assert exp["item"] == CONV_REL
    assert exp["version"] == hashlib.sha256(conv.read_bytes()).hexdigest()
    assert exp["rules"] == ["r1"]
    assert exp["model"] == "claude-test"
    assert exp["cli"] == current_dummyindex_version()
    assert exp["detector"] == I.DETECTOR_VERSION
    assert exp["via"] == "read"
    assert exp["turn"] == 1
    (correction,) = _corrections(led)
    assert correction["candidates"] == [CONV_REL]
    assert correction["model"] == "claude-test"
    assert correction["turn"] == 2


def test_skill_and_read_items(tmp_path):
    root = tmp_path
    cache = root / ".context" / "cache" / "x"
    cache.parent.mkdir(parents=True)
    cache.write_text("cache", encoding="utf-8")
    src = root / "src" / "a.py"
    src.parent.mkdir()
    src.write_text("print(1)\n", encoding="utf-8")
    skill = root / "pkg" / "skills" / "foo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# foo\n", encoding="utf-8")
    path = root / "s.jsonl"
    rows = [
        _human(root, "start", "h0"),
        _call("a1", "S1", "Skill", {"skill": "dummyindex-build"}),
        _result("r1", "S1", "ok"),
        _read("a2", "R2", cache),
        _result("r2", "R2", "cache"),
        _read("a3", "R3", src),
        _result("r3", "R3", "print"),
        _read("a4", "R4", skill),
        _result("r4", "R4", "# foo"),
    ]
    _write(path, rows)
    led = L.empty()
    exposures, _ = I.import_claude(
        path, root, {}, led, source_id="src", exposures=[], now=NOW
    )
    items = {row["item"]: row["via"] for row in exposures}
    assert items == {
        "skill:dummyindex-build": "skill",
        "pkg/skills/foo/SKILL.md": "read",
    }


@pytest.mark.skipif(
    sys.platform != "win32", reason="drive-letter casing is Windows only"
)
def test_windows_drive_case_and_backslash_match(tmp_path):
    conv = _rule_file(tmp_path)
    raw = str(conv).replace("/", "\\")
    raw = raw[0].swapcase() + raw[1:]
    assert I.exposure_item(raw, tmp_path) == CONV_REL


def test_incremental_import_continues_turn_count(tmp_path):
    root = tmp_path
    conv = _rule_file(root)
    path = root / "s.jsonl"
    _write(path, [_human(root, "start", "h0")])
    led = L.empty()
    first_rows, cursor = I.import_claude(
        path, root, {}, led, source_id="src", exposures=[], now=NOW
    )
    assert first_rows == []
    assert led["corrections"] == {}
    _append(
        path,
        [
            _read("a1", "R1", conv),
            _result("r1", "R1", "body"),
            _human(root, "wrong instead", "h1"),
        ],
    )
    second_rows, _ = I.import_claude(
        path, root, cursor, led, source_id="src", exposures=[], now=NOW
    )
    assert len(second_rows) == 1
    assert second_rows[0]["turn"] == 1
    (correction,) = _corrections(led)
    assert correction["turn"] == 2


def test_forked_copy_adds_no_duplicate(tmp_path):
    root = tmp_path
    conv = _rule_file(root)
    rows = [
        _human(root, "start", "h0"),
        _read("a1", "R1", conv),
        _result("r1", "R1", "body"),
        _human(root, "wrong instead", "h1"),
    ]
    path = root / "s.jsonl"
    fork = root / "fork.jsonl"
    _write(path, rows)
    _write(fork, rows)
    led = L.empty()
    first, _ = I.import_claude(
        path, root, {}, led, source_id="src", exposures=[], now=NOW
    )
    assert len(first) == 1
    count = len(led["corrections"])
    second, _ = I.import_claude(
        fork, root, {}, led, source_id="fork", exposures=first, now=NOW
    )
    assert second == []
    assert len(led["corrections"]) == count


def test_partial_last_line_waits_for_newline(tmp_path):
    root = tmp_path
    path = root / "s.jsonl"
    line = json.dumps(_human(root, "wrong instead", "h1"))
    path.write_bytes(line.encode("utf-8"))
    led = L.empty()
    _, cursor = I.import_claude(
        path, root, {}, led, source_id="src", exposures=[], now=NOW
    )
    assert led["corrections"] == {}
    with path.open("ab") as handle:
        handle.write(b"\n")
    I.import_claude(path, root, cursor, led, source_id="src", exposures=[], now=NOW)
    assert len(led["corrections"]) == 1


def test_save_prunes_rows_older_than_retention(tmp_path):
    ctx = tmp_path / ".context"
    ctx.mkdir()
    old_day, new_day = "2026-01-01", "2026-11-01"
    assert L.cutoff(NOW) == "2026-10-09"
    led = L.empty()
    led["events"] = {
        "old": {
            "id": "old",
            "host": "claude",
            "kind": "human_correction",
            "origin": "human",
            "timestamp": TS,
            "day": old_day,
        },
        "new": {
            "id": "new",
            "host": "claude",
            "kind": "human_correction",
            "origin": "human",
            "timestamp": TS,
            "day": new_day,
        },
    }
    led["corrections"] = {
        "old": {"id": "old", "day": old_day},
        "new": {"id": "new", "day": new_day},
    }
    led["sessions"] = {
        "s_old": {"source": "src", "day": old_day},
        "s_new": {"source": "src", "day": new_day},
    }
    led["attributions"] = [
        {"correction": "old", "day": old_day},
        {"correction": "new", "day": new_day},
    ]
    L.append_exposures(
        ctx,
        [
            {"call": "c_old", "item": CONV_REL, "day": old_day},
            {"call": "c_new", "item": CONV_REL, "day": new_day},
        ],
    )
    L.save(ctx, led, now=NOW)
    reloaded = L.load(ctx)
    assert set(reloaded["events"]) == {"new"}
    assert set(reloaded["corrections"]) == {"new"}
    assert set(reloaded["sessions"]) == {"s_new"}
    assert [row["correction"] for row in reloaded["attributions"]] == ["new"]
    assert [row["call"] for row in L.read_exposures(ctx)] == ["c_new"]


def test_append_exposures_drops_duplicate_calls(tmp_path):
    ctx = tmp_path / ".context"
    ctx.mkdir()
    assert (
        L.append_exposures(
            ctx,
            [
                {"call": "a", "item": CONV_REL},
                {"call": "a", "item": CONV_REL},
                {"call": "b", "item": CONV_REL},
            ],
        )
        == 2
    )
    assert (
        L.append_exposures(
            ctx,
            [{"call": "b", "item": CONV_REL}, {"call": "c", "item": CONV_REL}],
        )
        == 1
    )
    assert [row["call"] for row in L.read_exposures(ctx)] == ["a", "b", "c"]


def test_load_bad_json_raises(tmp_path):
    ctx = tmp_path / ".context"
    ctx.mkdir()
    ledger_path = tmp_path / L.LEDGER_REL
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(EvolveError):
        L.load(ctx)


def test_observe_lock_nested_is_reentrant(tmp_path):
    ctx = tmp_path / ".context"
    ctx.mkdir()
    with L.observe_lock(ctx) as outer:
        assert outer is True
        with L.observe_lock(ctx) as inner:
            assert inner is True
    with L.observe_lock(ctx) as again:
        assert again is True


def test_observe_lock_refused_by_other_holder(tmp_path):
    ctx = tmp_path / ".context"
    ctx.mkdir()
    with project_lock(tmp_path, lock_name="observe.lock"):
        with L.observe_lock(ctx) as held:
            assert held is False


def test_append_exposures_after_partial_line_keeps_new_row(tmp_path):
    ctx = tmp_path / ".context"
    ctx.mkdir()
    exposure = tmp_path / L.EXPOSURE_REL
    exposure.parent.mkdir(parents=True)
    exposure.write_bytes(b'{"call": "a", "it')
    assert L.append_exposures(ctx, [{"call": "b", "item": CONV_REL}]) == 1
    assert [row["call"] for row in L.read_exposures(ctx)] == ["b"]


def test_legacy_cursor_resumes_without_duplicates(tmp_path):
    root = tmp_path
    conv = _rule_file(root)
    path = root / "s.jsonl"
    _write(
        path,
        [
            _human(root, "start", "h0"),
            _read("a1", "R1", conv),
            _result("r1", "R1", "body"),
            _human(root, "thanks", "h1"),
        ],
    )
    led = L.empty()
    exposures, cur = I.import_claude(
        path, root, {}, led, source_id="src", exposures=[], now=NOW
    )
    assert len(exposures) == 1
    legacy = {k: cur[k] for k in ("offset", "prefix_size", "prefix")}
    _append(path, [_human(root, "wrong instead", "h2")])
    rows, _ = I.import_claude(
        path, root, legacy, led, source_id="src", exposures=exposures, now=NOW
    )
    assert rows == []
    assert len(led["corrections"]) == 1
    (correction,) = _corrections(led)
    assert correction["turn"] == 3
    assert correction["candidates"] == [CONV_REL]
