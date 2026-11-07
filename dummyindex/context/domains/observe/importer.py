"""Claude transcript importer: exposure rows, human corrections and hostile-text reasons."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from ..config import current_dummyindex_version
from ..evolve_gate import EvolveError
from ..living_rules import rules_in
from ..memory.miner.scan import _human_prompt_text
from .enums import CorrectionStatus
from .keys import keyed_id, session_key
from .models import Correction
from .security import scan_text

DETECTOR_VERSION = 1
TOOL_BUFFER_MAX = 64 * 1024
PREFIX_MAX = 4096
INJECTED = (
    "# AGENTS.md instructions",
    "<skill>",
    "<environment_context>",
    "<user_instructions>",
    "<system-reminder>",
    "<command-",
    "<local-command-",
)
LEARNING_MARK = "<!-- dummyindex:learning -->"
CORRECTION = re.compile(
    r"\b(wrong|instead|correction|never again|keep failing|doesn.t work|not working)\b",
    re.I,
)
QUOTED = re.compile(r"```.*?```|^>.*$", re.S | re.M)
EXPOSED_DIRS = ("conventions", "features", "playbooks", "equipment")
SKILL_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,63}\Z")
SKILL_PREFIX = "skill:"
VIA_READ = "read"
VIA_SKILL = "skill"
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_SKIP_ORIGINS = frozenset({"learning", "evolve"})
_NT = os.name == "nt"
_EMPTY_HASH = hashlib.sha256(b"").hexdigest()


def human_text(obj: dict) -> str | None:
    """External human prompt text, or None for injected, learning or synthetic rows."""
    text = _human_prompt_text(obj)
    if text is None or text.lstrip().startswith(INJECTED) or LEARNING_MARK in text:
        return None
    return text


def is_correction(text: str) -> bool:
    """Liberal prefilter: correction wording outside quoted spans."""
    return bool(CORRECTION.search(QUOTED.sub("", text)))


def exposure_item(raw_path: object, root: Path) -> str | None:
    """Repo-relative POSIX item for an exposed convention, feature, playbook, equipment or skill file."""
    if not isinstance(raw_path, str):
        return None
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        base = root.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    head = len(base.parts)
    if _fold(resolved.parts[:head]) != _fold(base.parts):
        return None
    rel = resolved.parts[head:]
    low = [part.casefold() for part in rel]
    if not low:
        return None
    in_context = len(low) > 2 and low[0] == ".context" and low[1] in EXPOSED_DIRS
    is_skill = low[-1] == "skill.md" and "skills" in low[:-1]
    if not (in_context or is_skill):
        return None
    return PurePosixPath(*rel).as_posix()


def item_version(root: Path, item: str) -> tuple[str | None, list[str]]:
    """Content sha256 and managed rule ids of one item; (None, []) when unreadable."""
    target = _item_path(root, item)
    if target is None:
        return None, []
    try:
        data = target.read_bytes()
    except OSError:
        return None, []
    version = hashlib.sha256(data).hexdigest()
    try:
        rules = [rule["id"] for rule in rules_in(data.decode("utf-8"))]
    except (EvolveError, UnicodeDecodeError, KeyError):
        rules = []
    return version, rules


def import_claude(
    path: Path,
    root: Path,
    cursor: dict,
    ledger: dict,
    *,
    source_id: str,
    exposures: list[dict],
    now: datetime | None = None,
) -> tuple[list[dict], dict]:
    """Import rows past the cursor; returns (new exposure rows, new cursor). Mutates ledger."""
    with path.open("rb") as handle:
        offset = _resume_offset(handle, path, cursor)
        if _skipped_header(handle, root):
            return [], cursor
        session = session_key(path.stem)
        ledger["sessions"][session] = {"source": source_id, "day": _day(None, now)}
        handle.seek(offset)
        walk = _Walk(
            cursor if offset else {}, ledger, root, source_id, session, exposures, now
        )
        end = _walk_rows(handle, walk)
        handle.seek(0)
        prefix = handle.read(min(end, PREFIX_MAX))
    new_cursor = {
        "offset": end,
        "prefix_size": len(prefix),
        "prefix": _fingerprint(prefix),
        **walk.state(),
    }
    return walk.rows, new_cursor


class _Walk:
    """Mutable scan state over one transcript's rows."""

    def __init__(
        self,
        state: dict,
        ledger: dict,
        root: Path,
        source_id: str,
        session: str,
        exposures: list[dict],
        now: datetime | None,
    ) -> None:
        self.turn = int(state.get("turn", 0))
        self.model = state.get("model")
        self.reasons = set(state.get("reasons", ()))
        self.buffered = int(state.get("buffered", 0))
        self.skip_calls = set(state.get("skip_calls", ()))
        self.ledger = ledger
        self.root = root
        self.source_id = source_id
        self.session = session
        self.now = now
        self.cli = current_dummyindex_version()
        self.seen = list(exposures)
        self.calls = {row.get("call") for row in exposures}
        self.rows: list[dict] = []

    def row(self, obj: dict, start: int) -> None:
        """Route one transcript row by type."""
        if obj.get("isSidechain") is True:
            return
        kind = obj.get("type")
        if kind == "assistant":
            self._assistant(obj)
        elif kind == "user":
            self._user(obj, start)

    def state(self) -> dict:
        """Cursor fields carried between scans."""
        return {
            "turn": self.turn,
            "model": self.model,
            "reasons": sorted(self.reasons),
            "buffered": self.buffered,
            "skip_calls": sorted(self.skip_calls),
        }

    def _assistant(self, obj: dict) -> None:
        message = obj.get("message")
        if not isinstance(message, dict):
            return
        model = message.get("model")
        if isinstance(model, str):
            self.model = model
        content = message.get("content")
        if not isinstance(content, list):
            return
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                self._tool_use(block, obj, model if isinstance(model, str) else None)

    def _tool_use(self, block: dict, obj: dict, model: str | None) -> None:
        target = _tool_target(block, self.root)
        block_id = block.get("id")
        if target is None or not isinstance(block_id, str):
            return
        item, via = target
        self.skip_calls.add(block_id)
        call = keyed_id("call", block_id)
        if call in self.calls:
            return
        version, rules = item_version(self.root, item)
        row = {
            "item": item,
            "version": version,
            "rules": rules,
            "session": self.session,
            "turn": self.turn,
            "day": _day(obj.get("timestamp"), self.now),
            "via": via,
            "call": call,
            "model": model,
            "cli": self.cli,
            "detector": DETECTOR_VERSION,
        }
        self.calls.add(call)
        self.rows.append(row)
        self.seen.append(row)

    def _user(self, obj: dict, start: int) -> None:
        text = human_text(obj)
        if text is not None:
            self._human(obj, text, start)
            return
        message = obj.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            return
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                self._tool_result(block)

    def _human(self, obj: dict, text: str, start: int) -> None:
        self.turn += 1
        if is_correction(text):
            self._correction(obj, text, start)
        self.reasons = set()
        self.buffered = 0
        self.skip_calls = set()

    def _correction(self, obj: dict, text: str, start: int) -> None:
        uuid = obj.get("uuid")
        timestamp = obj.get("timestamp")
        ts = timestamp if isinstance(timestamp, str) else ""
        if isinstance(uuid, str) and uuid:
            cid = keyed_id("claude", uuid)
        else:
            cid = keyed_id("claude", timestamp, text)
        day = _day(timestamp, self.now)
        self.ledger["events"].setdefault(
            cid,
            {
                "id": cid,
                "host": "claude",
                "kind": "human_correction",
                "origin": "human",
                "timestamp": timestamp,
                "day": day,
            },
        )
        if cid in self.ledger["corrections"]:
            return
        record = Correction(
            id=cid,
            host="claude",
            session=self.session,
            turn=self.turn,
            day=day,
            source_id=self.source_id,
            byte_offset=start,
            model=self.model,
            cli=self.cli,
            detector=DETECTOR_VERSION,
            candidates=self._candidates(),
            quarantine=tuple(sorted(self.reasons | set(scan_text(text)))),
            status=CorrectionStatus.OPEN,
            ts=ts,
        )
        self.ledger["corrections"][cid] = record.to_dict()

    def _candidates(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    row["item"]
                    for row in self.seen
                    if row.get("session") == self.session
                    and row.get("turn", 0) < self.turn
                }
            )
        )

    def _tool_result(self, block: dict) -> None:
        tool_use_id = block.get("tool_use_id")
        if isinstance(tool_use_id, str) and tool_use_id in self.skip_calls:
            return
        room = TOOL_BUFFER_MAX - self.buffered
        if room <= 0:
            return
        piece = _result_text(block.get("content"))[:room]
        self.buffered += len(piece)
        self.reasons |= set(scan_text(piece))


def _fold(parts: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(part.casefold() for part in parts) if _NT else parts


def _item_path(root: Path, item: str) -> Path | None:
    if item.startswith(SKILL_PREFIX):
        name = item[len(SKILL_PREFIX) :]
        if not SKILL_NAME.match(name):
            return None
        return root / ".claude" / "skills" / name / "SKILL.md"
    return root / item


def _tool_target(block: dict, root: Path) -> tuple[str, str] | None:
    tool_input = block.get("input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if block.get("name") == "Read":
        item = exposure_item(tool_input.get("file_path"), root)
        return (item, VIA_READ) if item else None
    if block.get("name") == "Skill":
        skill = tool_input.get("skill")
        if isinstance(skill, str) and skill:
            return f"{SKILL_PREFIX}{skill}", VIA_SKILL
    return None


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        part["text"]
        for part in content
        if isinstance(part, dict)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    )


def _day(timestamp: object, now: datetime | None) -> str:
    if isinstance(timestamp, str) and _DAY.fullmatch(timestamp[:10]):
        return timestamp[:10]
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _loads_dict(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _same_project(raw: object, root: Path) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        return Path(raw).resolve() == root.resolve()
    except (OSError, RuntimeError, ValueError):
        return False


def _skip_origin(value: object) -> bool:
    return isinstance(value, str) and value in _SKIP_ORIGINS


def _resume_offset(handle, path: Path, cursor: dict) -> int:
    offset = cursor.get("offset", 0)
    prefix = handle.read(min(int(cursor.get("prefix_size", 0)), PREFIX_MAX))
    if (
        not isinstance(offset, int)
        or offset < 0
        or path.stat().st_size < offset
        or _fingerprint(prefix) != cursor.get("prefix", _EMPTY_HASH)
    ):
        return 0
    return offset


def _skipped_header(handle, root: Path) -> bool:
    handle.seek(0)
    first = _loads_dict(handle.readline())
    declared = first.get("cwd")
    if declared and not _same_project(declared, root):
        return True
    return _skip_origin(first.get("origin")) or _skip_origin(first.get("source"))


def _walk_rows(handle, walk: _Walk) -> int:
    while True:
        start = handle.tell()
        raw = handle.readline()
        if not raw or not raw.endswith(b"\n"):
            handle.seek(start)
            return start
        obj = _loads_dict(raw)
        if obj:
            walk.row(obj, start)
