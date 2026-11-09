"""Project-scoped host evidence: committed lineage plus the local observe ledger.

Transcript prose never reaches disk. Unknown database schemas fail explicitly.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from dummyindex.usage.transcripts import encode_project_slug

from .atomic_io import write_text_atomic
from .config import current_dummyindex_version
from .evolve_gate import EvolveError, safe_file
from .evolve_promotion import project_lock
from .memory.miner.scope import project_dir_name
from .observe import ledger as observe_ledger
from .observe.enums import CorrectionStatus
from .observe.importer import (
    CORRECTION as _CORRECTION,
)
from .observe.importer import (
    DETECTOR_VERSION,
    LEARNING_MARK,
    PREFIX_MAX,
    QUOTED,
    import_claude,
)
from .observe.importer import (
    INJECTED as _INJECTED,
)
from .observe.keys import evolution_enabled, keyed_id, session_key
from .observe.models import Correction
from .observe.security import scan_text

LEDGER = ".context/gc/evidence.json"
COMMITTED_SCHEMA = 2
_V1_EVENT_KEYS = ("id", "host", "kind", "origin", "timestamp")
_EMPTY_HASH = hashlib.sha256(b"").hexdigest()
_SKIP_ORIGINS = ("learning", "evolve")


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _committed_path(context_dir: Path) -> Path:
    return safe_file(context_dir.parent, LEDGER, exists=False)


def _read_committed(context_dir: Path) -> dict:
    path = _committed_path(context_dir)
    if not path.exists():
        return {"schema_version": COMMITTED_SCHEMA, "exposure": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        version = data.get("schema_version")
        if version == 1:
            keys = ("events", "cursors", "exposure")
        elif version == COMMITTED_SCHEMA:
            keys = ("exposure",)
        else:
            raise ValueError("invalid evidence ledger shape")
        if any(not isinstance(data.get(k), dict) for k in keys):
            raise ValueError("invalid evidence ledger shape")
        return data
    except (ValueError, AttributeError) as exc:
        raise EvolveError(
            f"invalid evidence ledger; preserve and repair it: {exc}"
        ) from exc


def _save(context_dir: Path, exposure: dict) -> None:
    body = {"schema_version": COMMITTED_SCHEMA, "exposure": exposure}
    write_text_atomic(
        _committed_path(context_dir),
        json.dumps(body, sort_keys=True, indent=2) + "\n",
    )


def _project(event: dict) -> dict:
    return {key: event[key] for key in _V1_EVENT_KEYS if key in event}


def _migrate(context_dir: Path, now: datetime | None = None) -> None:
    """Move schema-1 events and cursors into the local ledger; caller holds observe.lock."""
    committed = _read_committed(context_dir)
    if committed["schema_version"] != 1:
        return
    ledger = observe_ledger.load(context_dir)
    day = observe_ledger.day_of(None, now)
    for identity, event in committed["events"].items():
        ledger["events"].setdefault(identity, {**_project(event), "day": day})
    for source, cursor in committed["cursors"].items():
        ledger["cursors"].setdefault(source, cursor)
    observe_ledger.save(context_dir, ledger, now)
    _save(context_dir, committed["exposure"])


def read_ledger(context_dir: Path) -> dict:
    """Read-only view: committed exposure plus local events and cursors."""
    committed = _read_committed(context_dir)
    local = observe_ledger.load(context_dir)
    legacy = committed if committed["schema_version"] == 1 else {}
    return {
        "schema_version": COMMITTED_SCHEMA,
        "events": {
            **{k: _project(v) for k, v in legacy.get("events", {}).items()},
            **local["events"],
        },
        "cursors": {**legacy.get("cursors", {}), **local["cursors"]},
        "exposure": committed["exposure"],
    }


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            p.get("text", "")
            for p in content
            if isinstance(p, dict)
            and p.get("type") in {"text", "input_text"}
            and isinstance(p.get("text"), str)
        )
    return ""


def _event(
    host: str, obj: dict, session: str, now: datetime | None = None
) -> tuple[dict, str] | None:
    if (
        obj.get("isMeta")
        or obj.get("is_meta")
        or obj.get("origin") in {"learning", "evolve", "injected"}
    ):
        return None
    payload = obj.get("payload", obj)
    if not isinstance(payload, dict):
        return None
    kind = obj.get("type")
    text = ""
    category = ""
    if host == "claude":
        msg = obj.get("message", {})
        if kind == "user" and isinstance(msg, dict):
            text = _text(msg.get("content"))
            if not text and isinstance(msg.get("content"), list):
                results = [
                    p
                    for p in msg["content"]
                    if isinstance(p, dict) and p.get("type") == "tool_result"
                ]
                if results:
                    category = "tool_outcome"
                    text = json.dumps(results, sort_keys=True)
    elif kind == "event_msg" and payload.get("type") == "user_message":
        text = _text(payload.get("message"))
    elif (
        kind == "response_item"
        and payload.get("type") == "message"
        and payload.get("role") == "user"
    ):
        text = _text(payload.get("content"))
    elif kind == "userMessage":
        text = _text(obj.get("content"))
    if text and category != "tool_outcome":
        if text.lstrip().startswith(_INJECTED) or LEARNING_MARK in text:
            return None
        # Quoted examples and pasted instructions are not independent feedback.
        if not _CORRECTION.search(QUOTED.sub("", text)):
            return None
        category = "human_correction"
    elif category == "tool_outcome":
        pass
    elif kind == "response_item" and payload.get("type") == "function_call_output":
        category = "tool_outcome"
        text = str(payload.get("output", ""))
    else:
        return None
    timestamp = str(obj.get("timestamp", ""))
    native = obj.get("uuid") or obj.get("id") or payload.get("id")
    identity = keyed_id(host, native) if native else keyed_id(host, timestamp, text)
    event = {
        "id": identity,
        "host": host,
        "kind": category,
        "origin": "human" if category == "human_correction" else "tool",
        "timestamp": timestamp,
        "day": observe_ledger.day_of(timestamp, now),
    }
    return event, text


def _same_project(raw: object, root: Path) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        return Path(raw).resolve() == root.resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def _loads_dict(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _codex_skipped(raw: bytes, root: Path) -> bool:
    first = _loads_dict(raw)
    meta = first.get("payload", {}) if first.get("type") == "session_meta" else first
    if not isinstance(meta, dict) or not _same_project(meta.get("cwd"), root):
        return True
    return any(meta.get(key) in _SKIP_ORIGINS for key in ("origin", "source"))


def _rows(
    handle, host: str, session: str, now: datetime | None
) -> list[tuple[dict, str, int]]:
    rows: list[tuple[dict, str, int]] = []
    while True:
        start = handle.tell()
        raw = handle.readline()
        if not raw or not raw.endswith(b"\n"):
            handle.seek(start)  # retry an incomplete row on the next scan
            return rows
        obj = _loads_dict(raw)
        found = _event(host, obj, session, now) if obj else None
        if found:
            rows.append((found[0], found[1], start))


def _jsonl(
    path: Path, host: str, root: Path, previous: dict, now: datetime | None = None
) -> tuple[list[tuple[dict, str, int]], dict]:
    """Codex rows past the cursor as (event, text, byte offset), plus the new cursor."""
    offset = previous.get("offset", 0)
    with path.open("rb") as handle:
        prefix = handle.read(min(int(previous.get("prefix_size", 0)), PREFIX_MAX))
        if (
            not isinstance(offset, int)
            or offset < 0
            or path.stat().st_size < offset
            or hashlib.sha256(prefix).hexdigest() != previous.get("prefix", _EMPTY_HASH)
        ):
            offset = 0
        handle.seek(0)
        if _codex_skipped(handle.readline(), root):
            return [], previous
        handle.seek(offset)
        events = _rows(handle, host, path.stem, now)
        end = handle.tell()
        handle.seek(0)
        prefix = handle.read(min(end, PREFIX_MAX))
    return events, {
        "offset": end,
        "prefix_size": len(prefix),
        "prefix": hashlib.sha256(prefix).hexdigest(),
    }


def _admit(
    ledger: dict,
    event: dict,
    text: str,
    *,
    session: str,
    source_id: str,
    byte_offset: int | None,
) -> None:
    ledger["events"].setdefault(event["id"], event)
    if event["kind"] != "human_correction":
        return
    record = Correction(
        id=event["id"],
        host=event["host"],
        session=session_key(session),
        turn=0,
        day=event["day"],
        source_id=source_id,
        byte_offset=byte_offset,
        model=None,
        cli=current_dummyindex_version(),
        detector=DETECTOR_VERSION,
        candidates=(),
        quarantine=tuple(sorted(scan_text(text))),
        status=CorrectionStatus.OPEN,
        ts=event["timestamp"],
    )
    ledger["corrections"].setdefault(record.id, record.to_dict())


def _host_files(
    claude_projects: Path | None, codex_sessions: Path | None, root: Path
) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    if claude_projects is not None:
        for name in sorted({project_dir_name(root), encode_project_slug(root)}):
            folder = claude_projects / name
            if folder.is_dir():
                files += [("claude", p) for p in sorted(folder.glob("*.jsonl"))]
    if codex_sessions is not None and codex_sessions.is_dir():
        files += [("codex", p) for p in sorted(codex_sessions.rglob("*.jsonl"))]
    return files


def _import_file(
    host: str,
    path: Path,
    root: Path,
    ledger: dict,
    sources: dict[str, str],
    exposures: list[dict],
    now: datetime | None,
) -> list[dict]:
    resolved = path.resolve()
    source = digest([host, str(resolved)])
    sources[source] = str(resolved)
    stat = path.stat()
    cursor = ledger["cursors"].get(source, {})
    if (
        cursor.get("size") == stat.st_size
        and cursor.get("mtime_ns") == stat.st_mtime_ns
    ):
        return []
    if host == "claude":
        rows, new = import_claude(
            path, root, cursor, ledger, source_id=source, exposures=exposures, now=now
        )
    else:
        rows = []
        found, new = _jsonl(path, host, root, cursor, now)
        for event, text, offset in found:
            _admit(
                ledger,
                event,
                text,
                session=path.stem,
                source_id=source,
                byte_offset=offset,
            )
    new.update(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
    ledger["cursors"][source] = new
    return rows


def scan_hosts(
    context_dir: Path,
    *,
    claude_projects: Path | None = None,
    codex_sessions: Path | None = None,
    codex_state: Path | None = None,
    codex_history: Path | None = None,
    budget_s: float = 20.0,
    clock: Callable[[], float] = time.monotonic,
    now: datetime | None = None,
) -> dict:
    """Bounded incremental import under observe.lock; explicit roots aid testing."""
    if not evolution_enabled():
        return {"disabled": True}
    started = clock()
    with observe_ledger.observe_lock(context_dir) as held:
        if not held:
            return {"skipped": "locked"}
        _migrate(context_dir, now)
        root = context_dir.resolve().parent
        ledger = observe_ledger.load(context_dir)
        before = set(ledger["events"])
        known = observe_ledger.read_exposures(context_dir)
        new_rows: list[dict] = []
        sources: dict[str, str] = {}
        complete = True
        for host, path in _host_files(claude_projects, codex_sessions, root):
            if clock() - started >= budget_s:
                complete = False
                break
            try:
                rows = _import_file(
                    host, path, root, ledger, sources, known + new_rows, now
                )
            except OSError:
                continue
            new_rows += rows
        if complete and (codex_state is not None or codex_history is not None):
            sources.update(_database(ledger, root, codex_state, codex_history, now))
        added = len(set(ledger["events"]) - before)
        observe_ledger.write_sources(context_dir, sources)
        appended = observe_ledger.append_exposures(context_dir, new_rows)
        observe_ledger.save(context_dir, ledger, now)
    return {
        "added": added,
        "events": len(ledger["events"]),
        "sources": len(ledger["cursors"]),
        "corrections": len(ledger["corrections"]),
        "exposures": appended,
        "complete": complete,
        "learning": None,
    }


def _database(
    ledger: dict,
    root: Path,
    state: Path | None,
    history: Path | None,
    now: datetime | None,
) -> dict[str, str]:
    if state is None or history is None:
        raise EvolveError(
            "Codex database import requires both state and history databases"
        )
    source = digest(["codex-db", str(history.resolve())])
    previous = ledger["cursors"].get(source, {})
    try:
        with sqlite3.connect(state.resolve().as_uri() + "?mode=ro", uri=True) as db:
            threads = {
                row[0]
                for row in db.execute("SELECT id,cwd FROM threads")
                if _same_project(row[1], root)
            }
        with sqlite3.connect(history.resolve().as_uri() + "?mode=ro", uri=True) as db:
            maximum = (
                db.execute("SELECT max(rowid) FROM thread_items").fetchone()[0] or 0
            )
            after = previous.get("rowid", 0)
            if after > maximum:
                after = 0
            for _rowid, thread, item, blob in db.execute(
                "SELECT rowid,thread_id,item_id,item_json FROM thread_items WHERE rowid>? AND item_type='userMessage' ORDER BY rowid",
                (after,),
            ):
                if thread not in threads:
                    continue
                obj = _loads_dict(blob)
                if not obj:
                    continue
                obj.update(type="userMessage", id=item)
                found = _event("codex", obj, thread, now)
                if found:
                    _admit(
                        ledger,
                        found[0],
                        found[1],
                        session=thread,
                        source_id=source,
                        byte_offset=None,
                    )
            ledger["cursors"][source] = {"rowid": maximum}
    except sqlite3.Error as exc:
        raise EvolveError(f"unsupported or unreadable Codex database: {exc}") from exc
    return {source: str(history.resolve())}


def expose_case(
    context_dir: Path,
    case_id: str,
    *,
    split: str,
    derived_from: tuple[str, ...] = (),
    content_sha256: str | None = None,
) -> None:
    """Exposure survives raw-history cleanup and follows derived-case ancestry."""
    if split not in {"train", "validation", "heldout"} or not case_id:
        raise EvolveError("case requires an ID and train/validation/heldout split")
    if case_id.startswith("sha256:") or (
        content_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", content_sha256)
    ):
        raise EvolveError(
            "case content identity must be a SHA256; hash keys are reserved"
        )
    content_key = "sha256:" + content_sha256 if content_sha256 else None
    with project_lock(context_dir.parent):
        if _read_committed(context_dir)["schema_version"] == 1:
            with observe_ledger.observe_lock(context_dir) as held:
                if not held:
                    raise EvolveError("evidence import is running; retry")
                _migrate(context_dir)
        exposure = _read_committed(context_dir)["exposure"]
        ancestors = set(derived_from) | {case_id}
        if content_key:
            ancestors.add(content_key)
        pending = list(ancestors)
        while pending:
            for parent in exposure.get(pending.pop(), {}).get("parents", []):
                if parent not in ancestors:
                    ancestors.add(parent)
                    pending.append(parent)
        used = {
            s
            for ancestor in ancestors
            for s in exposure.get(ancestor, {}).get("splits", [])
        }
        if split == "heldout" and used & {"train", "validation"}:
            raise EvolveError(
                "exposed case or ancestor cannot become clean held-out data"
            )
        # Descendant heldout use must also prevent later ancestor training.
        if split in {"train", "validation"}:
            for raw in exposure.values():
                if "heldout" in raw.get("splits", []) and ancestors.intersection(
                    raw.get("lineage", [])
                ):
                    raise EvolveError(
                        "ancestor of a held-out case cannot be used for development"
                    )
            if "heldout" in used:
                raise EvolveError("held-out case cannot be used for development")
        current = exposure.setdefault(
            case_id, {"parents": [], "splits": [], "lineage": []}
        )
        current["parents"] = sorted(
            set(current["parents"])
            | set(derived_from)
            | ({content_key} if content_key else set())
        )
        current["lineage"] = sorted(ancestors)
        current["splits"] = sorted(set(current["splits"]) | {split})
        if content_key:
            content = exposure.setdefault(
                content_key, {"parents": [], "splits": [], "lineage": [content_key]}
            )
            content["splits"] = sorted(set(content["splits"]) | {split})
        _save(context_dir, exposure)
