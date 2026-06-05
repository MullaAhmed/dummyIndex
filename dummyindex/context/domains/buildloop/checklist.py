"""Parse + atomically flip a proposal's ``checklist.md``.

A checklist is a flat markdown list of ``- [ ]`` / ``- [x]`` lines
(produced by Slice A). This module is the deterministic state layer:

- ``parse_checklist`` reads the file into ``ChecklistItem`` tuples.
- ``flip_item`` sets exactly one ``- [ ]`` → ``- [x]`` and writes the
  file back atomically (tmp + replace). Flipping an already-ticked item is
  a no-op (idempotent). The ``key`` is either the 0-based item index (int
  or digit string) or a case-insensitive substring of the item text.
- ``counts`` returns ``(done, total)``.

No ``print`` here — the CLI owns stdout. Boundary failures raise
``BuildLoopError``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Union

from .errors import BuildLoopError
from .models import ChecklistItem

# A checkbox line: optional indent, "- ", "[", a single fill char, "]",
# a space, then the item text. The fill char is " " (unchecked) or any
# non-space (treated as checked — "x" in practice).
_ITEM_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<mark>.)\]\s+(?P<text>.*\S)\s*$")


def parse_checklist(path: Path) -> tuple[ChecklistItem, ...]:
    """Parse ``checklist.md`` into an ordered tuple of items.

    Only checkbox lines participate; headings / prose / blank lines are
    ignored so a checklist may carry a title without breaking indexing.
    """
    if not path.is_file():
        raise BuildLoopError(f"checklist not found: {path}")
    items: list[ChecklistItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ITEM_RE.match(line)
        if m is None:
            continue
        done = m.group("mark").strip().lower() == "x"
        items.append(ChecklistItem(index=len(items), text=m.group("text"), done=done))
    return tuple(items)


def counts(items: tuple[ChecklistItem, ...]) -> tuple[int, int]:
    """Return ``(done, total)`` for a parsed checklist."""
    done = sum(1 for it in items if it.done)
    return done, len(items)


def _resolve_index(items: tuple[ChecklistItem, ...], key: Union[int, str]) -> int:
    """Map a user-supplied ``key`` to a 0-based item index.

    Accepts an int, a digit string (treated as an index), or a
    case-insensitive substring of the item text. Raises ``BuildLoopError``
    on no/ambiguous match so the CLI can surface a clear message.
    """
    if isinstance(key, int):
        idx = key
    elif isinstance(key, str) and key.strip().lstrip("-").isdigit():
        idx = int(key.strip())
    else:
        needle = str(key).strip().lower()
        matches = [it.index for it in items if needle in it.text.lower()]
        if not matches:
            raise BuildLoopError(f"no checklist item matches {key!r}")
        if len(matches) > 1:
            raise BuildLoopError(
                f"ambiguous checklist key {key!r} matches {len(matches)} items"
            )
        return matches[0]
    if idx < 0 or idx >= len(items):
        raise BuildLoopError(
            f"checklist index {idx} out of range (0..{len(items) - 1})"
        )
    return idx


def flip_item(path: Path, key: Union[int, str]) -> ChecklistItem:
    """Atomically set the item identified by ``key`` to ``- [x]``.

    Returns the resulting (ticked) item. Idempotent: if the target is
    already ticked, the file is left untouched and the existing item is
    returned. Only the n-th checkbox line in the file is rewritten — prose
    and other items are preserved verbatim.
    """
    items = parse_checklist(path)
    idx = _resolve_index(items, key)
    target = items[idx]
    if target.done:
        # No-op: already ticked. Don't rewrite the file (keeps mtime and
        # makes the operation truly idempotent).
        return target

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    seen = -1
    rewritten: list[str] = []
    flipped = False
    for line in lines:
        body = line.rstrip("\n")
        m = _ITEM_RE.match(body)
        if m is not None:
            seen += 1
            if seen == idx:
                newline = "\n" if line.endswith("\n") else ""
                rewritten.append(f"{m.group('indent')}- [x] {m.group('text')}{newline}")
                flipped = True
                continue
        rewritten.append(line)

    if not flipped:  # pragma: no cover - parse + rewrite agree by construction
        raise BuildLoopError(f"failed to locate checklist item {idx} for rewrite")

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(rewritten), encoding="utf-8")
    tmp.replace(path)
    return ChecklistItem(index=target.index, text=target.text, done=True)
