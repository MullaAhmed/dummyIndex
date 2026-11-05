"""Project-scoped host evidence and durable exposure lineage.

The ledger stores identities and categories, never transcript prose. Host files
remain local and are opened read-only. Unknown database schemas fail explicitly.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from dummyindex.usage.transcripts import encode_project_slug

from .atomic_io import write_text_atomic
from .evolve_gate import EvolveError, safe_file
from .evolve_promotion import project_lock
from .memory.miner.scope import project_dir_name

LEDGER = ".context/gc/evidence.json"
_INJECTED = (
    "# AGENTS.md instructions",
    "<skill>",
    "<environment_context>",
    "<user_instructions>",
)
_CORRECTION = re.compile(
    r"\b(wrong|instead|correction|never again|keep failing|doesn.t work|not working)\b",
    re.I,
)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def read_ledger(context_dir: Path) -> dict:
    path = safe_file(context_dir.parent, LEDGER, exists=False)
    if not path.exists():
        return {"schema_version": 1, "events": {}, "cursors": {}, "exposure": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or any(
            not isinstance(data.get(k), dict) for k in ("events", "cursors", "exposure")
        ):
            raise ValueError("invalid evidence ledger shape")
        return data
    except (ValueError, AttributeError) as exc:
        raise EvolveError(
            f"invalid evidence ledger; preserve and repair it: {exc}"
        ) from exc


def _save(context_dir: Path, ledger: dict) -> None:
    write_text_atomic(
        safe_file(context_dir.parent, LEDGER, exists=False),
        json.dumps(ledger, sort_keys=True, indent=2) + "\n",
    )


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


def _event(host: str, obj: dict, session: str) -> dict | None:
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
        if (
            text.lstrip().startswith(_INJECTED)
            or "<!-- dummyindex:learning -->" in text
        ):
            return None
        # Quoted examples and pasted instructions are not independent feedback.
        clean = re.sub(r"```.*?```|^>.*$", "", text, flags=re.S | re.M)
        if not _CORRECTION.search(clean):
            return None
        category = "human_correction"
    elif category == "tool_outcome":
        pass
    elif kind == "response_item" and payload.get("type") == "function_call_output":
        # A result is evidence of execution, not automatic proof of success.
        category = "tool_outcome"
        text = str(payload.get("output", ""))
    else:
        return None
    timestamp = str(obj.get("timestamp", ""))
    native = obj.get("uuid") or obj.get("id") or payload.get("id")
    # Copies/forks with a preserved native identity or timestamp/text collapse.
    identity = digest([host, native] if native else [host, timestamp, category, text])
    return {
        "id": identity,
        "host": host,
        "session": digest(session),
        "kind": category,
        "origin": "human" if category == "human_correction" else "tool",
        "timestamp": timestamp,
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
    }


def _same_project(raw: object, root: Path) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        return Path(raw).resolve() == root.resolve()
    except (OSError, RuntimeError):
        return False


def _jsonl(path: Path, host: str, root: Path, cursor: dict) -> tuple[list[dict], dict]:
    source = digest([host, str(path.resolve())])
    previous = cursor.get(source, {})
    offset = previous.get("offset", 0)
    # A prefix fingerprint detects rotation or replacement, including growth.
    with path.open("rb") as handle:
        prefix = handle.read(min(int(previous.get("prefix_size", 0)), 4096))
        if (
            not isinstance(offset, int)
            or offset < 0
            or path.stat().st_size < offset
            or hashlib.sha256(prefix).hexdigest()
            != previous.get("prefix", hashlib.sha256(b"").hexdigest())
        ):
            offset = 0
        handle.seek(0)
        header = handle.readline()
        try:
            first = json.loads(header)
        except ValueError:
            first = {}
        if not isinstance(first, dict):
            first = {}
        meta = (
            first.get("payload", {}) if first.get("type") == "session_meta" else first
        )
        declared = meta.get("cwd") if isinstance(meta, dict) else None
        if host == "codex" and not _same_project(declared, root):
            return [], previous
        if host == "claude" and declared and not _same_project(declared, root):
            return [], previous
        if isinstance(meta, dict) and (
            meta.get("origin") in {"learning", "evolve"}
            or meta.get("source") in {"learning", "evolve"}
        ):
            return [], previous
        handle.seek(offset)
        events = []
        while True:
            start = handle.tell()
            raw = handle.readline()
            if not raw or not raw.endswith(b"\n"):
                handle.seek(start)  # retry an incomplete row on the next scan
                break
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if isinstance(obj, dict):
                event = _event(host, obj, path.stem)
                if event:
                    event.update(source_id=source, byte_offset=start)
                    events.append(event)
        end = handle.tell()
        handle.seek(0)
        prefix = handle.read(min(end, 4096))
    return events, {
        "offset": end,
        "prefix_size": len(prefix),
        "prefix": hashlib.sha256(prefix).hexdigest(),
    }


def scan_hosts(
    context_dir: Path,
    *,
    claude_projects: Path | None = None,
    codex_sessions: Path | None = None,
    codex_state: Path | None = None,
    codex_history: Path | None = None,
) -> dict:
    """Incrementally import this project's evidence; explicit roots aid testing."""
    root = context_dir.resolve().parent
    with project_lock(root):
        ledger = read_ledger(context_dir)
        before_ids = set(ledger["events"])
        added = 0
        local_sources = {}
        for host, paths in (
            (
                "claude",
                sorted(
                    {
                        p
                        for name in {project_dir_name(root), encode_project_slug(root)}
                        for p in (claude_projects / name).glob("*.jsonl")
                    }
                )
                if claude_projects
                else [],
            ),
            (
                "codex",
                sorted(codex_sessions.rglob("*.jsonl")) if codex_sessions else [],
            ),
        ):
            for path in paths:
                source = digest([host, str(path.resolve())])
                local_sources[source] = str(path.resolve())
                events, cursor = _jsonl(path, host, root, ledger["cursors"])
                ledger["cursors"][source] = cursor
                for event in events:
                    if event["id"] not in ledger["events"]:
                        ledger["events"][event["id"]] = event
                        added += 1
        if codex_state is not None or codex_history is not None:
            if codex_state is None or codex_history is None:
                raise EvolveError(
                    "Codex database import requires both state and history databases"
                )
            added += _database(ledger, root, codex_state, codex_history)
            local_sources[digest(["codex-db", str(codex_history.resolve())])] = str(
                codex_history.resolve()
            )
        new_human = []
        for identity in sorted(set(ledger["events"]) - before_ids):
            event = ledger["events"][identity]
            if event["kind"] == "human_correction":
                event_file = safe_file(
                    root, f".context/gc/evidence/{identity}.json", exists=False
                )
                write_text_atomic(
                    event_file, json.dumps(event, sort_keys=True, indent=2) + "\n"
                )
                new_human.append(identity)
        _save(context_dir, ledger)
        local_path = safe_file(
            root, ".context/cache/evidence-sources.json", exists=False
        )
        existing_sources = (
            json.loads(local_path.read_text(encoding="utf-8"))
            if local_path.exists()
            else {}
        )
        write_text_atomic(
            local_path,
            json.dumps(existing_sources | local_sources, sort_keys=True, indent=2)
            + "\n",
        )
    learning = None
    if new_human:
        from .evolve_learning import enqueue_learning

        identity = new_human[0]
        learning = enqueue_learning(
            context_dir,
            event_id=f"human:{identity}",
            origin="human",
            evidence=[f".context/gc/evidence/{identity}.json"],
            cue="Inspect this actual human correction in its local source; reflect once on a verified narrow rule change or NO_ENTRY",
        )
    return {
        "added": added,
        "events": len(ledger["events"]),
        "sources": len(ledger["cursors"]),
        "learning": {"event_id": learning["event_id"], "state": learning["state"]}
        if learning
        else None,
    }


def _database(ledger: dict, root: Path, state: Path, history: Path) -> int:
    source = digest(["codex-db", str(history.resolve())])
    # created_at_ms + rowid is a stable resume key; rescan after shrink/rotation.
    previous = ledger["cursors"].get(source, {})
    added = 0
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
                try:
                    obj = json.loads(blob)
                except ValueError:
                    continue
                if not isinstance(obj, dict):
                    continue
                obj.update(type="userMessage", id=item)
                event = _event("codex", obj, thread)
                if event and event["id"] not in ledger["events"]:
                    event.update(source_id=source, rowid=_rowid)
                    ledger["events"][event["id"]] = event
                    added += 1
            ledger["cursors"][source] = {"rowid": maximum}
    except sqlite3.Error as exc:
        raise EvolveError(f"unsupported or unreadable Codex database: {exc}") from exc
    return added


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
        ledger = read_ledger(context_dir)
        exposure = ledger["exposure"]
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
        _save(context_dir, ledger)
