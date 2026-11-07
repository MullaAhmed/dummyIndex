"""Parse and atomically rewrite a proposal's ``checklist.md``.

A ``- [ ]`` box is open; any other mark (``x`` done, ``~`` skipped) closes it. A
leading ``**GATE**``/``GATE`` marks a human-decision item and a trailing ``— via
<tool>`` its binding tool; both are parsed out while ``text`` stays verbatim. A
``## Wave N``/``## Group N`` heading opens a parallel group (the plan only groups
disjoint-file tasks); other headings close it, and unwaved items are singletons.
"""

from __future__ import annotations

import re
import time
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from .errors import BuildLoopError
from .models import ChecklistItem

# A checkbox line: optional indent, "- ", "[", a single fill char, "]",
# a space, then the item text. The fill char is " " (unchecked) or any
# non-space (treated as checked — "x" in practice).
_ITEM_RE = re.compile(r"^(?P<indent>\s*)- \[(?P<mark>.)\]\s+(?P<text>.*\S)\s*$")

# Headings drive wave grouping. A heading whose text starts with "wave" or
# "group" opens a parallel group; any other heading closes it (so a plain
# title never accidentally parallelises a legacy flat checklist).
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_WAVE_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(?:wave|group)\b", re.IGNORECASE)

# A human-decision gate: the item text leads with `**GATE**` (the form real
# plan sessions write) or bare `GATE`. Case-sensitive + word-bound so prose
# like "gate the rollout" or "GATEWAY" never becomes a gate.
_GATE_RE = re.compile(r"^(?:\*{1,2})?GATE\b")

# A trailing `— via <tool>` tag (em-dash) names the binding tool/skill that
# must execute the item. The tag stays in the item text verbatim.
_VIA_RE = re.compile(r"\s+—\s+via\s+(\S+)\s*$")
_TASK_ID_RE = re.compile(r"\s*<!--\s*task:([A-Za-z0-9_-]+)\s*-->")


def _item_identity(raw_text: str) -> tuple[str, str]:
    marker = _TASK_ID_RE.search(raw_text)
    text = _TASK_ID_RE.sub("", raw_text).strip()
    original = text.split(" — skipped:", 1)[0].strip()
    item_id = (
        marker.group(1)
        if marker
        else "task-" + sha256(original.encode()).hexdigest()[:16]
    )
    return text, item_id


def parse_checklist(path: Path) -> tuple[ChecklistItem, ...]:
    """Parse ``checklist.md`` into an ordered tuple of items.

    Only checkbox lines become items; headings steer ``group`` assignment
    (wave headings open a shared group, other headings close it) and
    prose / blank lines are ignored, so a checklist may carry a title
    without breaking indexing.
    """
    if not path.is_file():
        raise BuildLoopError(f"checklist not found: {path}")
    items: list[ChecklistItem] = []
    next_group = 0
    in_wave = False  # an open `## Wave N` heading governs items below
    wave_group: int | None = None  # set at its first item; empty headings burn no id
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ITEM_RE.match(line)
        if m is None:
            if _WAVE_HEADING_RE.match(line):
                in_wave, wave_group = True, None
            elif _HEADING_RE.match(line):
                in_wave, wave_group = False, None
            continue
        if in_wave:
            if wave_group is None:
                wave_group = next_group
                next_group += 1
            group = wave_group
        else:
            group = next_group
            next_group += 1
        # Any non-space mark closes the box: "x" (done) or "~" (skipped).
        done = m.group("mark").strip() != ""
        text, item_id = _item_identity(m.group("text"))
        via_match = _VIA_RE.search(text)
        items.append(
            ChecklistItem(
                index=len(items),
                text=text,
                done=done,
                group=group,
                gate=bool(_GATE_RE.match(text)),
                via=via_match.group(1) if via_match else None,
                item_id=item_id,
            )
        )
    return tuple(items)


def next_wave(items: tuple[ChecklistItem, ...]) -> tuple[ChecklistItem, ...]:
    """Every unchecked item sharing the first unchecked item's group.

    This is the parallel-dispatch frontier: groups are monotonic in
    document order, so the first unchecked item always belongs to the
    earliest incomplete group — and that group must finish before any
    later one starts. Returns ``()`` when everything is ticked.
    """
    first = next((it for it in items if not it.done), None)
    if first is None:
        return ()
    return tuple(it for it in items if not it.done and it.group == first.group)


def counts(items: tuple[ChecklistItem, ...]) -> tuple[int, int]:
    """Return ``(done, total)`` for a parsed checklist."""
    done = sum(1 for it in items if it.done)
    return done, len(items)


def _resolve_index(items: tuple[ChecklistItem, ...], key: int | str) -> int:
    """Map a user-supplied ``key`` to a 0-based item index.

    Tries a task ID, then ``index:N``, then an int or digit string (refused if
    another item's leading ``N.`` label claims it), then an exact or unique
    case-insensitive text match. Raises ``BuildLoopError`` on no/ambiguous match.
    """
    identity_matches = [it.index for it in items if it.item_id and it.item_id == key]
    if len(identity_matches) > 1:
        raise BuildLoopError(
            f"ambiguous task ID {key!r}; add unique <!-- task:ID --> markers"
        )
    if identity_matches:
        return identity_matches[0]
    if isinstance(key, str) and key.startswith("index:"):
        try:
            key = int(key.partition(":")[2])
        except ValueError as exc:
            raise BuildLoopError(f"invalid explicit checklist index {key!r}") from exc
    if isinstance(key, int):
        idx = key
    elif isinstance(key, str) and key.strip().lstrip("-").isdigit():
        idx = int(key.strip())
        labels = [
            it.index
            for it in items
            if re.match(rf"^{re.escape(key.strip())}[.)\s]", it.text)
        ]
        if labels and labels != [idx]:
            raise BuildLoopError(
                f"ambiguous numeric checklist key {key!r}; use a task ID or index:{idx}"
            )
    else:
        needle = str(key).strip().lower()
        if not needle:
            raise BuildLoopError("checklist key must not be empty")
        exact = [it.index for it in items if needle == it.text.lower()]
        if len(exact) == 1:
            return exact[0]
        matched = [it for it in items if needle in it.text.lower()]
        if not matched:
            raise BuildLoopError(f"no checklist item matches {key!r}")
        if len(matched) > 1:
            # Cap candidates so a broad selector cannot flood the error.
            shown = matched[:5]
            listing = "; ".join(f"{it.index}: {it.text}" for it in shown)
            more = "" if len(matched) <= 5 else f"; … and {len(matched) - 5} more"
            raise BuildLoopError(
                f"ambiguous checklist key {key!r} matches {len(matched)} items "
                f"({listing}{more}); retry with an index"
            )
        return matched[0].index
    if idx < 0 or idx >= len(items):
        raise BuildLoopError(
            f"checklist index {idx} out of range (0..{len(items) - 1})"
        )
    return idx


def _rewrite_item_line(path: Path, idx: int, *, mark: str, suffix: str = "") -> None:
    """Atomically rewrite the ``idx``-th checkbox line as ``- [<mark>]``.

    ``suffix`` is appended after the item text; every other line is kept verbatim.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    seen = -1
    rewritten: list[str] = []
    found = False
    for line in lines:
        body = line.rstrip("\n")
        m = _ITEM_RE.match(body)
        if m is not None:
            seen += 1
            if seen == idx:
                newline = "\n" if line.endswith("\n") else ""
                rewritten.append(
                    f"{m.group('indent')}- [{mark}] {m.group('text')}{suffix}{newline}"
                )
                found = True
                continue
        rewritten.append(line)

    if not found:  # pragma: no cover - parse + rewrite agree by construction
        raise BuildLoopError(f"failed to locate checklist item {idx} for rewrite")

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(rewritten), encoding="utf-8")
    tmp.replace(path)


def flip_item(path: Path, key: int | str) -> ChecklistItem:
    """Atomically set the item identified by ``key`` to ``- [x]``.

    Returns the resulting (ticked) item. Idempotent: if the target is
    already ticked, the file is left untouched and the existing item is
    returned.
    """
    with _mutation_lock(path):
        return _flip_item_unlocked(path, key)


def _flip_item_unlocked(path: Path, key: int | str) -> ChecklistItem:
    """The caller owns the project lock across any related receipt update."""
    items = parse_checklist(path)
    idx = _resolve_index(items, key)
    target = items[idx]
    if target.done:
        # No-op: already ticked. Don't rewrite the file (keeps mtime and
        # makes the operation truly idempotent).
        return target
    _rewrite_item_line(path, idx, mark="x")
    return replace(target, done=True)


def skip_item(path: Path, key: int | str, reason: str) -> ChecklistItem:
    """Atomically close the item as ``- [~] … — skipped: <reason>``.

    For renegotiated scope: ``~`` parses as done, so the wave advances, but the
    file records why instead of a bare ``- [x]`` that claims the item was built.
    Requires a non-empty ``reason`` (whitespace collapsed to keep one line) and
    refuses an already-closed box, so a skip never overwrites a tick.
    """
    clean_reason = " ".join(str(reason).split())
    if not clean_reason:
        raise BuildLoopError("skip requires a non-empty reason")
    with _mutation_lock(path):
        items = parse_checklist(path)
        idx = _resolve_index(items, key)
        target = items[idx]
        if target.done:
            raise BuildLoopError(
                f"checklist item {idx} is already closed — cannot skip it"
            )
        annotation = f" — skipped: {clean_reason}"
        _rewrite_item_line(path, idx, mark="~", suffix=annotation)
        return replace(target, done=True, text=f"{target.text}{annotation}")


@contextmanager
def _mutation_lock(path: Path):
    """Serialize cooperating task writers, including parallel wave completions."""
    from ..evolve_gate import EvolveError
    from ..evolve_promotion import project_lock

    root = (
        path.parents[3]
        if path.parent.parent.name == "proposals"
        and path.parent.parent.parent.name == ".context"
        else path.parent
    )
    deadline = time.monotonic() + 5
    with ExitStack() as held:
        while True:
            try:
                held.enter_context(project_lock(root))
                break
            except EvolveError as exc:
                if (
                    not str(exc).startswith("another evolve writer")
                    or time.monotonic() >= deadline
                ):
                    raise BuildLoopError(str(exc)) from exc
                time.sleep(0.01)
        yield
