"""Stage-2 attribution: resolution packets, recorded verdicts and exposure writes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..atomic_io import write_text_atomic
from ..config import current_dummyindex_version
from ..evolve_gate import EvolveError, safe_file
from ..memory.miner.signatures import canonical_signature
from . import ledger
from .enums import CorrectionStatus, ExposureVia, Verdict
from .importer import DETECTOR_VERSION, human_text
from .keys import evolution_enabled, keyed_id, session_key
from .models import Attribution, Correction

TEXT_MAX = 1000
STUB_DIR = ".context/gc/evidence"
STUB_SCHEMA = 2
VERDICTS = ("attributed", "unrelated", "unknown")
LOCK_BUSY = "evidence import is running; retry"


def _row(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _ordered(records) -> list[dict]:
    return sorted(
        records,
        key=lambda r: (
            r.get("day", ""),
            r.get("ts", ""),
            r.get("turn", 0),
            r.get("id", ""),
        ),
    )


def corrections(context_dir: Path) -> list[dict]:
    """Correction records in (day, ts, turn, id) order."""
    return _ordered(ledger.load(context_dir)["corrections"].values())


def open_corrections(context_dir: Path) -> list[dict]:
    """Open correction records, oldest first."""
    return [
        rec
        for rec in corrections(context_dir)
        if rec.get("status") == CorrectionStatus.OPEN.value
    ]


def attributions(context_dir: Path) -> list[dict]:
    """Recorded attribution rows."""
    return list(ledger.load(context_dir)["attributions"])


def exposures(context_dir: Path, item: str | None = None) -> list[dict]:
    """Exposure rows, optionally filtered by item."""
    return ledger.read_exposures(context_dir, item)


def _candidate_rows(context_dir: Path, record: Correction) -> dict[str, dict]:
    """Last exposure row per candidate item, same session, earlier turn."""
    rows: dict[str, dict] = {}
    for row in ledger.read_exposures(context_dir):
        if row.get("session") != record.session or row.get("turn", 0) >= record.turn:
            continue
        if row.get("item") in record.candidates:
            rows[row["item"]] = row
    return rows


def _transcript(context_dir: Path, record: Correction) -> Path | None:
    """Local raw transcript path of the correction, None when gone."""
    source = ledger.read_sources(context_dir).get(record.source_id)
    if not isinstance(source, str) or not Path(source).is_file():
        return None
    return Path(source)


def _text_of(obj: dict) -> str:
    """Concatenated text blocks of one assistant row."""
    message = obj.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return ""
    return "".join(
        block["text"]
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


def _pair(obj: dict, assistant: str) -> tuple[str, str] | None:
    human = human_text(obj) if obj else None
    if human is None:
        return None
    return human[:TEXT_MAX], assistant[:TEXT_MAX]


def _texts(path: Path, byte_offset: int | None) -> tuple[str, str] | None:
    """Human text at byte_offset and latest assistant text before it, None if missing."""
    if byte_offset is None:
        return None
    assistant = ""
    with path.open("rb") as handle:
        while True:
            start = handle.tell()
            raw = handle.readline()
            if not raw or start > byte_offset:
                return None
            obj = _row(raw)
            if start == byte_offset:
                return _pair(obj, assistant)
            if obj.get("isSidechain") is True:
                continue
            if obj.get("type") == "assistant":
                text = _text_of(obj)
                if text:
                    assistant = text


def _packet(rec: dict, texts, rows: dict[str, dict]) -> dict:
    human, assistant = texts
    candidates = [
        {
            "item": item,
            "version": row.get("version"),
            "rules": list(row.get("rules") or []),
        }
        for item, row in sorted(rows.items())
    ]
    return {
        "correction": rec,
        "human_text": human,
        "assistant_text": assistant,
        "candidates": candidates,
        "verdicts": list(VERDICTS),
    }


def _next_packet(context_dir: Path) -> dict | None:
    data = ledger.load(context_dir)
    packet = None
    changed = False
    for rec in _ordered(data["corrections"].values()):
        if _skip_for_packet(rec):
            continue
        record = Correction.from_dict(rec)
        rows = _candidate_rows(context_dir, record)
        if not rows:
            continue
        path = _transcript(context_dir, record)
        texts = _texts(path, record.byte_offset) if path else None
        if texts is None:
            rec["status"] = CorrectionStatus.EXPIRED.value
            changed = True
            continue
        packet = _packet(rec, texts, rows)
        break
    if changed:
        ledger.save(context_dir, data)
    return packet


def _skip_for_packet(rec: dict) -> bool:
    return (
        rec.get("status") != CorrectionStatus.OPEN.value
        or bool(rec.get("quarantine"))
        or not rec.get("candidates")
    )


def resolution_packet(context_dir: Path) -> dict | None:
    """Oldest open, unquarantined correction with candidates, for the resolver."""
    with ledger.observe_lock(context_dir) as held:
        if not held:
            raise EvolveError(LOCK_BUSY)
        return _next_packet(context_dir)


def _verdict(value: str | Verdict) -> Verdict:
    try:
        return Verdict(value)
    except ValueError as exc:
        raise EvolveError(f"unknown verdict: {value}") from exc


def _is_candidate_item(rows: dict[str, dict], item: object) -> bool:
    if not isinstance(item, str):
        return False
    if item in rows:
        return True
    path, sep, rule = item.partition("#")
    return bool(sep) and path in rows and rule in (rows[path].get("rules") or [])


def _validate(
    context_dir: Path,
    record: Correction,
    kind: Verdict,
    item: str | None,
    retracts: bool,
) -> None:
    if kind is not Verdict.ATTRIBUTED:
        if item is not None:
            raise EvolveError("only an attributed verdict takes an item")
        if retracts:
            raise EvolveError("retracts requires an attributed verdict")
        return
    if record.quarantine:
        raise EvolveError("quarantined correction cannot be attributed")
    if not _is_candidate_item(_candidate_rows(context_dir, record), item):
        raise EvolveError(f"item is not a candidate of this correction: {item}")


def _record(
    context_dir: Path,
    correction_id: str,
    *,
    verdict: str | Verdict,
    item: str | None,
    durable: bool,
    retracts: bool,
    now: datetime | None,
) -> dict:
    kind = _verdict(verdict)
    data = ledger.load(context_dir)
    rec = data["corrections"].get(correction_id)
    if rec is None:
        raise EvolveError(f"unknown correction: {correction_id}")
    record = Correction.from_dict(rec)
    if record.status is not CorrectionStatus.OPEN:
        raise EvolveError("correction is not open: already recorded or expired")
    _validate(context_dir, record, kind, item, retracts)
    row = Attribution(
        correction=record.id,
        verdict=kind,
        item=item,
        durable=bool(durable),
        retracts=bool(retracts),
        session=record.session,
        turn=record.turn,
        day=ledger.day_of(None, now),
    ).to_dict()
    data["attributions"].append(row)
    rec["status"] = CorrectionStatus.RESOLVED.value
    ledger.save(context_dir, data, now)
    return row


def record_attribution(
    context_dir: Path,
    correction_id: str,
    *,
    verdict: str | Verdict,
    item: str | None = None,
    durable: bool = False,
    retracts: bool = False,
    now: datetime | None = None,
) -> dict:
    """Record one verdict for an open correction and resolve it."""
    with ledger.observe_lock(context_dir) as held:
        if not held:
            raise EvolveError(LOCK_BUSY)
        return _record(
            context_dir,
            correction_id,
            verdict=verdict,
            item=item,
            durable=durable,
            retracts=retracts,
            now=now,
        )


def _input(block: dict) -> dict:
    value = block.get("input")
    return value if isinstance(value, dict) else {}


def _tool_signatures(obj: dict) -> list[str]:
    message = obj.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [
        canonical_signature(block["name"], _input(block))
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "tool_use"
        and isinstance(block.get("name"), str)
    ]


def _call_rows(path: Path) -> list[tuple[int, str]]:
    calls: list[tuple[int, str]] = []
    turn = 0
    with path.open("rb") as handle:
        for raw in handle:
            obj = _row(raw)
            if not obj or obj.get("isSidechain") is True:
                continue
            if obj.get("type") == "user" and human_text(obj) is not None:
                turn += 1
            elif obj.get("type") == "assistant":
                calls.extend((turn, sig) for sig in _tool_signatures(obj))
    return calls


def session_tool_calls(context_dir: Path, session: str) -> list[tuple[int, str]] | None:
    """Read-only (turn, tool signature) rows of one keyed session, None if transcript gone."""
    entry = ledger.load(context_dir)["sessions"].get(session)
    source_id = entry.get("source") if isinstance(entry, dict) else None
    if not isinstance(source_id, str):
        return None
    source = ledger.read_sources(context_dir).get(source_id)
    if not isinstance(source, str) or not Path(source).is_file():
        return None
    return _call_rows(Path(source))


def commit_evidence_stub(context_dir: Path, correction_id: str) -> str:
    """Write the gc evidence stub for one correction; return its repo-relative path."""
    rec = ledger.load(context_dir)["corrections"].get(correction_id)
    if rec is None:
        raise EvolveError(f"unknown correction: {correction_id}")
    rel = f"{STUB_DIR}/{correction_id}.json"
    path = safe_file(context_dir.parent, rel, exists=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    stub = {
        "schema_version": STUB_SCHEMA,
        "id": correction_id,
        "host": rec["host"],
        "kind": "human_correction",
        "day": rec["day"],
        "detector": rec["detector"],
    }
    write_text_atomic(path, json.dumps(stub, sort_keys=True, indent=2) + "\n")
    return rel


def _inject_row(
    session_id: str,
    turn: int,
    item: str,
    version: str | None,
    via: str,
    now: datetime | None,
) -> dict:
    return {
        "item": item,
        "version": version,
        "rules": [],
        "session": session_key(session_id),
        "turn": turn,
        "day": ledger.day_of(None, now),
        "via": ExposureVia(via).value,
        "call": keyed_id("inject", session_id, turn, item, version),
        "model": None,
        "cli": current_dummyindex_version(),
        "detector": DETECTOR_VERSION,
    }


def record_exposure(
    context_dir: Path,
    *,
    session_id: str,
    turn: int,
    items: list[tuple[str, str | None]],
    via: str = "inject",
    now: datetime | None = None,
) -> int:
    """Log loader injections for one session turn; 0 when disabled or locked."""
    if not evolution_enabled():
        return 0
    with ledger.observe_lock(context_dir) as held:
        if not held:
            return 0
        rows = [
            _inject_row(session_id, turn, item, version, via, now)
            for item, version in items
        ]
        return ledger.append_exposures(context_dir, rows)
