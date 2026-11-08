from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone

import pytest

from dummyindex.context.domains.evolve_gate import EvolveError
from dummyindex.context.domains.living_rules import durable_evidence
from dummyindex.context.domains.observe import (
    attributions,
    commit_evidence_stub,
    corrections,
    exposures,
    observe_lock,
    open_corrections,
    record_attribution,
    record_exposure,
    resolution_packet,
    session_key,
    session_tool_calls,
)
from dummyindex.context.domains.observe import importer as I
from dummyindex.context.domains.observe import ledger as L

pytestmark = pytest.mark.unit

TODAY = datetime.now(timezone.utc).date().isoformat()
TICK = itertools.count()
RULE_TEXT = (
    '<!-- dummyindex:rule {"id": "r1"} -->\nbody\n<!-- dummyindex:rule:end r1 -->\n'
)


def _ts():
    return f"{TODAY}T10:00:{next(TICK) % 60:02d}Z"


def _root(tmp_path):
    return tmp_path / "repo"


def _write(path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("".join(json.dumps(row) + "\n" for row in rows))


def _human(root, text, uuid):
    return {
        "type": "user",
        "userType": "external",
        "uuid": uuid,
        "timestamp": _ts(),
        "cwd": str(root),
        "message": {"role": "user", "content": text},
    }


def _assistant(uuid, blocks):
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": _ts(),
        "message": {"role": "assistant", "model": "m", "content": blocks},
    }


def _text(uuid, text):
    return _assistant(uuid, [{"type": "text", "text": text}])


def _tool(uuid, tid, name, tool_input):
    return _assistant(
        uuid, [{"type": "tool_use", "id": tid, "name": name, "input": tool_input}]
    )


def _read(root, uuid, tid):
    conv = str(root / ".context" / "conventions" / "x.md")
    return _tool(uuid, tid, "Read", {"file_path": conv})


def _bash(uuid, tid):
    return _tool(uuid, tid, "Bash", {"command": "ls -la"})


def _result(uuid, tid, text):
    return {
        "type": "user",
        "userType": "external",
        "uuid": uuid,
        "timestamp": _ts(),
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tid, "content": text}],
        },
    }


def _seed(tmp_path, rows, name="sess-1"):
    root = _root(tmp_path)
    context = root / ".context"
    conv = context / "conventions" / "x.md"
    conv.parent.mkdir(parents=True, exist_ok=True)
    conv.write_bytes(RULE_TEXT.encode("utf-8"))
    path = tmp_path / "t" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, rows)
    led = L.load(context)
    new, _cursor = I.import_claude(
        path, root, {}, led, source_id=name, exposures=L.read_exposures(context)
    )
    with L.observe_lock(context) as held:
        assert held
        L.append_exposures(context, new)
        L.save(context, led)
        L.write_sources(context, {name: str(path)})
    return root, context, path


def _packet_rows(root, correction):
    return [
        _human(root, "start", "h0"),
        _read(root, "a1", "R1"),
        _human(root, correction, "h1"),
    ]


def test_packet_order_and_skips(tmp_path):
    root = _root(tmp_path)
    rows = [
        _human(root, "start", "h0"),
        _read(root, "a1", "R1"),
        _human(root, "wrong, use B instead", "h1"),
        _bash("a2", "B1"),
        _result("r2", "B1", "out\u200bput"),
        _human(root, "wrong again", "h2"),
        _human(root, "thanks", "h3"),
        _human(root, "that is wrong", "h4"),
    ]
    _, context, _ = _seed(tmp_path, rows)
    _seed(tmp_path, [_human(root, "that is wrong", "o1")], name="sess-2")
    sess1 = session_key("sess-1")

    first = resolution_packet(context)
    assert first is not None
    assert first["correction"]["turn"] == 2
    assert first["correction"]["session"] == sess1
    assert first["verdicts"] == ["attributed", "unrelated", "unknown"]
    record_attribution(context, first["correction"]["id"], verdict="unknown")

    second = resolution_packet(context)
    assert second is not None
    assert second["correction"]["turn"] == 5
    assert second["correction"]["session"] == sess1

    quarantined = next(
        rec
        for rec in corrections(context)
        if rec["turn"] == 3 and rec["session"] == sess1
    )
    assert quarantined["quarantine"] == ["invisible-unicode"]
    record_attribution(context, second["correction"]["id"], verdict="unknown")
    assert resolution_packet(context) is None


def test_packet_texts_truncated_to_1000(tmp_path):
    root = _root(tmp_path)
    rows = [
        _human(root, "start", "h0"),
        _read(root, "a1", "R1"),
        _text("a2", "y" * 1500),
        _human(root, "wrong " + "x" * 1500, "h1"),
    ]
    _, context, _ = _seed(tmp_path, rows)
    packet = resolution_packet(context)
    assert packet is not None
    assert len(packet["human_text"]) == 1000
    assert len(packet["assistant_text"]) == 1000
    assert set(packet["assistant_text"]) == {"y"}


def test_assistant_text_survives_tool_only_rows(tmp_path):
    root = _root(tmp_path)
    rows = [
        _human(root, "start", "h0"),
        _read(root, "a1", "R1"),
        _text("a2", "keep me"),
        _bash("a3", "B1"),
        _result("r3", "B1", "out"),
        _human(root, "wrong instead", "h1"),
    ]
    _, context, _ = _seed(tmp_path, rows)
    packet = resolution_packet(context)
    assert packet is not None
    assert packet["assistant_text"] == "keep me"


def test_trimmed_exposure_skips_correction(tmp_path):
    root = _root(tmp_path)
    rows = _packet_rows(root, "wrong instead")
    _, context, _ = _seed(tmp_path, rows)
    exposure = context / "cache" / "evolution" / "exposure.jsonl"
    exposure.write_text("", encoding="utf-8")
    assert resolution_packet(context) is None
    (rec,) = corrections(context)
    assert rec["status"] == "open"


def test_lock_is_reentrant_for_observe_calls(tmp_path):
    root = _root(tmp_path)
    rows = _packet_rows(root, "wrong, use B instead")
    _, context, _ = _seed(tmp_path, rows)
    with observe_lock(context) as held:
        assert held
        assert (
            record_exposure(
                context,
                session_id="s-lock",
                turn=0,
                items=[("probation:b", "v")],
            )
            == 1
        )
        packet = resolution_packet(context)
        assert packet is not None
        row = record_attribution(context, packet["correction"]["id"], verdict="unknown")
    assert row["verdict"] == "unknown"


def test_missing_transcript_expires_correction(tmp_path):
    root = _root(tmp_path)
    rows = _packet_rows(root, "wrong instead")
    _, context, path = _seed(tmp_path, rows)
    path.unlink()
    assert resolution_packet(context) is None
    (rec,) = corrections(context)
    assert rec["status"] == "expired"


def test_record_attribution_validation(tmp_path):
    root = _root(tmp_path)
    rows = _packet_rows(root, "wrong, use B instead")
    _, context, _ = _seed(tmp_path, rows)
    (rec,) = corrections(context)
    cid = rec["id"]

    with pytest.raises(EvolveError):
        record_attribution(
            context, cid, verdict="attributed", item=".context/conventions/other.md"
        )
    with pytest.raises(EvolveError):
        record_attribution(context, cid, verdict="unrelated", retracts=True)
    with pytest.raises(EvolveError):
        record_attribution(
            context, cid, verdict="unrelated", item=".context/conventions/x.md"
        )
    with pytest.raises(EvolveError):
        record_attribution(context, cid, verdict="bogus")
    with pytest.raises(EvolveError):
        record_attribution(
            context, cid, verdict="attributed", item=".context/conventions/x.md#r2"
        )

    row = record_attribution(
        context,
        cid,
        verdict="attributed",
        item=".context/conventions/x.md#r1",
        durable=True,
    )
    assert {
        "correction",
        "verdict",
        "item",
        "durable",
        "retracts",
        "session",
        "turn",
        "day",
    } <= set(row)
    assert row["verdict"] == "attributed"
    assert row["item"] == ".context/conventions/x.md#r1"
    assert row["durable"] is True

    with pytest.raises(EvolveError):
        record_attribution(context, cid, verdict="unknown")
    assert len(attributions(context)) == 1
    assert cid not in {rec["id"] for rec in open_corrections(context)}


def test_record_exposure_writes_no_raw_session_id(tmp_path):
    root = _root(tmp_path)
    context = root / ".context"
    context.mkdir(parents=True)
    assert (
        record_exposure(
            context,
            session_id="raw-session-xyz",
            turn=0,
            items=[("probation:a", "v1")],
        )
        == 1
    )
    assert (
        record_exposure(
            context,
            session_id="raw-session-xyz",
            turn=0,
            items=[("probation:a", "v1")],
        )
        == 0
    )
    rows = exposures(context, item="probation:a")
    assert len(rows) == 1
    row = rows[0]
    assert row["via"] == "inject"
    assert row["model"] is None
    assert row["rules"] == []
    assert row["session"] == session_key("raw-session-xyz")
    for path in root.rglob("*"):
        if path.is_file():
            assert b"raw-session-xyz" not in path.read_bytes()


def test_session_tool_calls(tmp_path):
    root = _root(tmp_path)
    rows = [
        _human(root, "start", "h0"),
        _read(root, "a1", "R1"),
        _bash("a2", "B1"),
        _human(root, "wrong instead", "h1"),
    ]
    _, context, path = _seed(tmp_path, rows)
    calls = session_tool_calls(context, session_key("sess-1"))
    assert isinstance(calls, list)
    assert all(isinstance(call, tuple) and len(call) == 2 for call in calls)
    assert all(isinstance(turn, int) and isinstance(sig, str) for turn, sig in calls)
    assert any(turn == 1 and "x.md" in sig for turn, sig in calls)

    path.unlink()
    assert session_tool_calls(context, session_key("sess-1")) is None
    assert session_tool_calls(context, session_key("unknown-session")) is None


def test_commit_evidence_stub(tmp_path):
    root = _root(tmp_path)
    rows = _packet_rows(root, "wrong instead")
    _, context, _ = _seed(tmp_path, rows)
    (rec,) = corrections(context)
    cid = rec["id"]

    rel = commit_evidence_stub(context, cid)
    assert rel == f".context/gc/evidence/{cid}.json"
    data = json.loads((root / rel).read_text(encoding="utf-8"))
    assert set(data) == {"schema_version", "id", "host", "kind", "day", "detector"}
    assert data["schema_version"] == 2
    assert data["kind"] == "human_correction"
    assert rel in durable_evidence(context, (rel,))

    with pytest.raises(EvolveError):
        commit_evidence_stub(context, "missing-id")
