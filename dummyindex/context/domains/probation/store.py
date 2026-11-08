"""Filesystem store for probation items; callers hold ``locked``."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..atomic_io import write_text_atomic
from ..evolve_gate import EvolveError, safe_file
from ..living_rules import _ID
from ..observe import observe_lock
from .models import Item

PROBATION_REL = ".context/cache/evolution/probation"
STATE_NAME = "_state.json"


def _default_state() -> dict[str, Any]:
    return {
        "consumed": [],
        "digested": [],
        "routed": [],
        "last_block_bytes": 0,
        "last_report": None,
    }


def _dump(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvolveError(f"unreadable probation file: {path.name}") from exc
    if not isinstance(data, dict):
        raise EvolveError(f"probation file is not an object: {path.name}")
    return data


def _read_item(path: Path) -> Item:
    return Item.from_dict(_read_json(path))


def item_path(context_dir: Path, item_id: str) -> Path:
    if not isinstance(item_id, str) or not _ID.fullmatch(item_id):
        raise EvolveError("invalid probation id")
    return safe_file(
        context_dir.parent, f"{PROBATION_REL}/{item_id}.json", exists=False
    )


def load_items(context_dir: Path) -> list[Item]:
    directory = context_dir.parent / PROBATION_REL
    if not directory.is_dir():
        return []
    items = [
        _read_item(path) for path in directory.glob("*.json") if path.name != STATE_NAME
    ]
    return sorted(items, key=lambda item: item.id)


def load_item(context_dir: Path, item_id: str) -> Item | None:
    path = item_path(context_dir, item_id)
    if not path.is_file():
        return None
    return _read_item(path)


def save_item(context_dir: Path, item: Item) -> None:
    write_text_atomic(item_path(context_dir, item.id), _dump(item.to_dict()))


def load_state(context_dir: Path) -> dict[str, Any]:
    state = _default_state()
    path = safe_file(context_dir.parent, f"{PROBATION_REL}/{STATE_NAME}", exists=False)
    if path.is_file():
        state.update(_read_json(path))
    return state


def save_state(context_dir: Path, state: dict[str, Any]) -> None:
    path = safe_file(context_dir.parent, f"{PROBATION_REL}/{STATE_NAME}", exists=False)
    write_text_atomic(path, _dump(state))


@contextmanager
def locked(context_dir: Path) -> Iterator[None]:
    with observe_lock(context_dir) as held:
        if not held:
            raise EvolveError("evidence import is running; retry")
        yield
