from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..atomic_io import write_text_atomic
from ..evolve_gate import EvolveError, safe_file
from ..evolve_promotion import project_lock
from .keys import retention_days

LEDGER_REL = ".context/cache/evolution/ledger.json"
EXPOSURE_REL = ".context/cache/evolution/exposure.jsonl"
SOURCES_REL = ".context/cache/evidence-sources.json"
LOCK_NAME = "observe.lock"
SCHEMA_VERSION = 1
DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
LEDGER_DICTS = ("events", "cursors", "corrections", "sessions")


def empty() -> dict:
    """Fresh local ledger shape."""
    return {
        "schema_version": SCHEMA_VERSION,
        "events": {},
        "cursors": {},
        "corrections": {},
        "attributions": [],
        "sessions": {},
    }


def _invalid(detail: str) -> EvolveError:
    return EvolveError(
        f"invalid local evidence ledger; preserve and repair it: {detail}"
    )


def _ledger_path(context_dir: Path) -> Path:
    return safe_file(context_dir.parent, LEDGER_REL, exists=False)


def _exposure_path(context_dir: Path) -> Path:
    return safe_file(context_dir.parent, EXPOSURE_REL, exists=False)


def _sources_path(context_dir: Path) -> Path:
    return safe_file(context_dir.parent, SOURCES_REL, exists=False)


def load(context_dir: Path) -> dict:
    """Read the local ledger, or an empty one when absent."""
    path = _ledger_path(context_dir)
    if not path.exists():
        return empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _invalid(str(exc)) from exc
    if not isinstance(data, dict):
        raise _invalid("top level is not an object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise _invalid(f"schema_version is not {SCHEMA_VERSION}")
    for key in LEDGER_DICTS:
        if key in data and not isinstance(data[key], dict):
            raise _invalid(f"{key} is not an object")
    if "attributions" in data and not isinstance(data["attributions"], list):
        raise _invalid("attributions is not a list")
    return {**empty(), **data}


def day_of(timestamp: object, now: datetime | None = None) -> str:
    """ISO day from a timestamp string, else from now."""
    if isinstance(timestamp, str) and DAY_RE.fullmatch(timestamp[:10]):
        return timestamp[:10]
    return (now or datetime.now(timezone.utc)).date().isoformat()


def cutoff(now: datetime | None = None) -> str:
    """Oldest kept day as an ISO date string."""
    current = now or datetime.now(timezone.utc)
    return (current.date() - timedelta(days=retention_days())).isoformat()


def _kept(value: object, cut: str) -> bool:
    day = value.get("day") if isinstance(value, dict) else None
    return not (isinstance(day, str) and day < cut)


def _expired_line(line: str, cut: str) -> bool:
    try:
        row = json.loads(line)
    except ValueError:
        return False
    return not _kept(row, cut)


def prune_exposures(context_dir: Path, cut: str) -> None:
    """Drop exposure rows older than cut; rewrite only when some row expired."""
    path = _exposure_path(context_dir)
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if not _expired_line(line, cut)]
    if len(kept) == len(lines):
        return
    write_text_atomic(path, "".join(line + "\n" for line in kept))


def save(context_dir: Path, ledger: dict, now: datetime | None = None) -> None:
    """Prune expired rows, write the ledger atomically, then prune exposures."""
    cut = cutoff(now)
    for key in LEDGER_DICTS:
        ledger[key] = {k: v for k, v in ledger[key].items() if _kept(v, cut)}
    ledger["attributions"] = [row for row in ledger["attributions"] if _kept(row, cut)]
    path = _ledger_path(context_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(ledger, sort_keys=True, indent=2) + "\n")
    prune_exposures(context_dir, cut)


def read_exposures(context_dir: Path, item: str | None = None) -> list[dict]:
    """Exposure rows in file order, optionally filtered by item; bad lines skipped."""
    path = _exposure_path(context_dir)
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and (item is None or row.get("item") == item):
            rows.append(row)
    return rows


def append_exposures(context_dir: Path, rows: list[dict]) -> int:
    """Append rows whose call is new to the file; return rows written."""
    seen = {row.get("call") for row in read_exposures(context_dir)}
    fresh: list[dict] = []
    for row in rows:
        call = row.get("call")
        if call in seen:
            continue
        seen.add(call)
        fresh.append(row)
    if not fresh:
        return 0
    path = _exposure_path(context_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in fresh:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return len(fresh)


def read_sources(context_dir: Path) -> dict[str, str]:
    """Source ID to transcript path map; empty when absent or unreadable."""
    path = _sources_path(context_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_sources(context_dir: Path, mapping: dict[str, str]) -> None:
    """Merge mapping over stored sources and write atomically."""
    merged = {**read_sources(context_dir), **mapping}
    path = _sources_path(context_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(merged, sort_keys=True, indent=2) + "\n")


@contextmanager
def observe_lock(context_dir: Path) -> Iterator[bool]:
    """Yield True when the observe lock is held, False when another writer holds it."""
    with ExitStack() as stack:
        try:
            stack.enter_context(
                project_lock(context_dir.resolve().parent, lock_name=LOCK_NAME)
            )
            held = True
        except EvolveError:
            held = False
        yield held
