# 01 — Session-memory implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a markdown-first, remember-equivalent session-memory store inside dummyindex: a `.context/memory/` tier store, a `dummyindex context memory` CLI, a `/dummyindex-remember` skill, SessionStart injection folded into the existing drift hook, and detect-and-suppress coexistence with the `remember` plugin.

**Architecture:** Deterministic mechanics (store creation, tier rolling, the SessionStart emit, remember-plugin detection) live in a new domain package `dummyindex/context/domains/memory/` and are exposed through a wire-only CLI subcommand `dummyindex context memory <verb>`. Prose (writing the session summary, compressing rolled tiers, promoting core memories) is the in-session agent's job, driven by the `/dummyindex-remember` skill markdown. No background pipeline, no LLM dependency.

**Tech Stack:** Python 3.10+ (stdlib only for this feature), pytest, the existing `dummyindex` CLI dispatch + SessionStart hook installer.

**Spec:** `docs/specs/01-session-memory-design.md`

**Conventions (must follow — `docs/reference/01-conventions.md`):** domain package ships `enums.py` / `models.py` / `errors.py` / verb files + `__init__.py` re-exports; constants are enums; every dataclass is `frozen=True` with `tuple[...]` collection fields; typed exceptions per area (no bare `ValueError`); `print` only at the CLI boundary (`cli/*`, `__main__`); CLI returns `int` (0 ok / 2 bad-args / 1 runtime); atomic writes via tmp + replace; tests under `tests/context/`, pytest markers, bare `assert`.

> **Run all commands from the repo root** `/mnt/windows-ssd/Projects/memory/dummyindex`. Tests run with `uv run pytest`.

---

## File structure

**Create — domain package `dummyindex/context/domains/memory/`:**
- `__init__.py` — public re-exports (the test surface).
- `enums.py` — `MemoryTier` + `TIER_HEADINGS`.
- `errors.py` — `SessionMemoryError`, `MemoryStoreError`.
- `models.py` — frozen `Section`, `RollReport`.
- `_parse.py` — `split_sections`, `section_date`, `render` (markdown section helpers).
- `store.py` — `memory_dir`, `tier_path`, `write_text_atomic`, `ensure_memory_store`.
- `detect.py` — `remember_plugin_present`.
- `roll.py` — `roll_tiers`.
- `emit.py` — `render_session_start`.

**Create — CLI + skill:**
- `dummyindex/cli/memory.py` — `_cmd_memory` (wire-only).
- `dummyindex/skills/memory/SKILL.md` — the `/dummyindex-remember` skill.

**Create — tests:**
- `tests/context/test_memory.py` — domain unit tests.
- `tests/context/test_memory_cli.py` — CLI integration tests.

**Modify:**
- `dummyindex/context/enums.py` — add `ContextSubcommand.MEMORY`.
- `dummyindex/cli/__init__.py` — import + register `_cmd_memory`.
- `dummyindex/cli/_usage.py` — document `memory`.
- `dummyindex/context/hooks.py` — second SessionStart command.
- `dummyindex/context/build/runner.py` — seed `.context/memory/` in `build_all`.
- `dummyindex/__main__.py` — copy the memory skill to its own top-level skill dir.
- `pyproject.toml` — package-data for `skills/memory/*.md`.
- `dummyindex/skills/skill.md` — pointer section.
- `tests/context/test_hooks.py` — assert both SessionStart commands.
- `tests/context/test_runner.py` — assert ingest seeds + rebuild preserves memory.

---

## Task 1: Domain scaffolding — enums, errors, models, parse, store

**Files:**
- Create: `dummyindex/context/domains/memory/__init__.py` (stub for now), `enums.py`, `errors.py`, `models.py`, `_parse.py`, `store.py`
- Test: `tests/context/test_memory.py`

- [ ] **Step 1: Write failing tests for store + parse**

Create `tests/context/test_memory.py`:

```python
"""Unit tests for the session-memory domain."""
from __future__ import annotations

import pytest

from dummyindex.context.domains.memory import (
    MemoryTier,
    ensure_memory_store,
    memory_dir,
)
from dummyindex.context.domains.memory._parse import (
    render,
    section_date,
    split_sections,
)
from dummyindex.context.domains.memory.models import Section

pytestmark = pytest.mark.unit


def _ctx(tmp_path):
    return tmp_path / ".context"


def test_ensure_memory_store_creates_all_tiers(tmp_path):
    created = ensure_memory_store(_ctx(tmp_path))
    assert set(created) == {t.value for t in MemoryTier}
    mdir = memory_dir(_ctx(tmp_path))
    assert (mdir / "now.md").read_text(encoding="utf-8").startswith("# Now")
    assert (mdir / "core-memories.md").read_text(encoding="utf-8").startswith("# Core memories")


def test_ensure_memory_store_is_non_destructive(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    (memory_dir(ctx) / "now.md").write_text(
        "# Now\n\n## 2026-06-05 10:00 | main\nkeep me\n", encoding="utf-8"
    )
    created = ensure_memory_store(ctx)
    assert created == ()
    assert "keep me" in (memory_dir(ctx) / "now.md").read_text(encoding="utf-8")


def test_split_sections_separates_preamble_and_sections():
    text = "# Now\n\n## 2026-06-05 10:00 | main\nbody one\n\n## 2026-06-04 09:00 | dev\nbody two\n"
    pre, secs = split_sections(text)
    assert pre == "# Now"
    assert len(secs) == 2
    assert secs[0].heading == "## 2026-06-05 10:00 | main"
    assert "body one" in secs[0].body


def test_section_date_extracts_iso_date():
    assert section_date("## 2026-06-05 10:00 | main") == "2026-06-05"
    assert section_date("## no date here") is None


def test_render_roundtrips_sections():
    text = "# Recent\n\n## 2026-06-05\nalpha\n"
    pre, secs = split_sections(text)
    out = render(pre, secs)
    assert "# Recent" in out and "## 2026-06-05" in out and "alpha" in out
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/context/test_memory.py -q`
Expected: FAIL — `ModuleNotFoundError: dummyindex.context.domains.memory`.

- [ ] **Step 3: Create `enums.py`**

```python
"""Closed alphabet for the session-memory store."""
from __future__ import annotations

from enum import Enum


class MemoryTier(str, Enum):
    """The on-disk tier files under `.context/memory/`."""

    NOW = "now.md"
    RECENT = "recent.md"
    ARCHIVE = "archive.md"
    CORE = "core-memories.md"


# The H1 title each freshly-seeded tier file carries.
TIER_HEADINGS: dict[MemoryTier, str] = {
    MemoryTier.NOW: "# Now",
    MemoryTier.RECENT: "# Recent",
    MemoryTier.ARCHIVE: "# Archive",
    MemoryTier.CORE: "# Core memories",
}
```

- [ ] **Step 4: Create `errors.py`**

```python
"""Typed errors for the session-memory domain.

Named `SessionMemoryError` (not `MemoryError`) so we never shadow the
builtin `MemoryError`.
"""
from __future__ import annotations


class SessionMemoryError(Exception):
    """Base for session-memory domain failures."""


class MemoryStoreError(SessionMemoryError):
    """Raised when the memory store cannot be created or read."""
```

- [ ] **Step 5: Create `models.py`**

```python
"""Frozen data carriers for the session-memory domain."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """A `## …` markdown section: its heading line and its body text."""

    heading: str
    body: str


@dataclass(frozen=True)
class RollReport:
    """What a single `roll_tiers` call relocated."""

    now_to_recent: int = 0
    recent_to_archive: int = 0
    moved_dates: tuple[str, ...] = ()
```

- [ ] **Step 6: Create `_parse.py`**

```python
"""Markdown section helpers shared by the tier files.

A tier file is an H1 title (`# Now`) followed by zero or more `## …`
sections. These helpers split / re-join that shape so `roll` can relocate
whole sections without disturbing the rest.
"""
from __future__ import annotations

import re

from .models import Section

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def split_sections(text: str) -> tuple[str, tuple[Section, ...]]:
    """Split markdown into ``(preamble, sections)`` on ``## `` headings.

    The preamble is everything before the first ``## `` line (e.g. the
    ``# Now`` title). Each Section keeps its heading verbatim and the body
    up to the next ``## `` line.
    """
    preamble: list[str] = []
    sections: list[Section] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is None:
                preamble = body
            else:
                sections.append(Section(heading, "\n".join(body).strip("\n")))
            heading = line
            body = []
        else:
            body.append(line)
    if heading is None:
        preamble = body
    else:
        sections.append(Section(heading, "\n".join(body).strip("\n")))
    return "\n".join(preamble).strip("\n"), tuple(sections)


def section_date(heading: str) -> str | None:
    """Return the first ``YYYY-MM-DD`` in a heading, or ``None``."""
    match = _DATE_RE.search(heading)
    return match.group(1) if match else None


def render(preamble: str, sections: tuple[Section, ...]) -> str:
    """Inverse of :func:`split_sections` — join into a text block."""
    parts: list[str] = []
    if preamble:
        parts.append(preamble)
    for section in sections:
        block = section.heading if not section.body else f"{section.heading}\n{section.body}"
        parts.append(block)
    return "\n\n".join(parts).rstrip("\n") + "\n"
```

- [ ] **Step 7: Create `store.py`**

```python
"""Create and locate the `.context/memory/` tier store."""
from __future__ import annotations

from pathlib import Path

from .enums import TIER_HEADINGS, MemoryTier


def memory_dir(context_dir: Path) -> Path:
    """The `memory/` directory inside a `.context/` directory."""
    return context_dir / "memory"


def tier_path(context_dir: Path, tier: MemoryTier) -> Path:
    """Absolute path to one tier file."""
    return memory_dir(context_dir) / tier.value


def write_text_atomic(path: Path, text: str) -> None:
    """Write ``text`` via a tmp file + ``replace`` (atomic on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def ensure_memory_store(context_dir: Path) -> tuple[str, ...]:
    """Create `memory/` + empty tier stubs if missing.

    Idempotent and **non-destructive**: an existing tier file is never
    overwritten. Returns the tier filenames newly created this call.
    """
    created: list[str] = []
    mdir = memory_dir(context_dir)
    mdir.mkdir(parents=True, exist_ok=True)
    for tier in MemoryTier:
        path = mdir / tier.value
        if path.exists():
            continue
        write_text_atomic(path, TIER_HEADINGS[tier] + "\n")
        created.append(tier.value)
    return tuple(created)
```

- [ ] **Step 8: Create a temporary `__init__.py` exposing what Task 1 tests import**

```python
"""Session-memory store (full surface wired in Task 6)."""
from __future__ import annotations

from .enums import MemoryTier
from .store import ensure_memory_store, memory_dir, tier_path, write_text_atomic

__all__ = [
    "MemoryTier",
    "ensure_memory_store",
    "memory_dir",
    "tier_path",
    "write_text_atomic",
]
```

- [ ] **Step 9: Run tests, verify they pass**

Run: `uv run pytest tests/context/test_memory.py -q`
Expected: PASS (6 tests).

- [ ] **Step 10: Commit**

```bash
git add dummyindex/context/domains/memory tests/context/test_memory.py
git commit -m "feat(memory): tier-store scaffolding (enums, models, parse, store)"
```

---

## Task 2: Remember-plugin detection

**Files:**
- Create: `dummyindex/context/domains/memory/detect.py`
- Test: `tests/context/test_memory.py` (append)

- [ ] **Step 1: Write the failing test** (append to `tests/context/test_memory.py`)

```python
from dummyindex.context.domains.memory.detect import remember_plugin_present


def test_remember_plugin_detection(tmp_path):
    assert remember_plugin_present(tmp_path) is False
    (tmp_path / ".remember").mkdir()
    assert remember_plugin_present(tmp_path) is True
```

- [ ] **Step 2: Run, verify it fails**

Run: `uv run pytest tests/context/test_memory.py::test_remember_plugin_detection -q`
Expected: FAIL — `ModuleNotFoundError ...memory.detect`.

- [ ] **Step 3: Create `detect.py`**

```python
"""Detect a co-installed `remember` plugin so we can stand down."""
from __future__ import annotations

from pathlib import Path


def remember_plugin_present(root: Path) -> bool:
    """True when the `remember` plugin's store exists at the repo root.

    The plugin writes its tiered history into ``<root>/.remember/``. When
    that directory exists the plugin is active, and dummyindex suppresses
    its own SessionStart memory block to avoid two competing injections.
    """
    return (root / ".remember").is_dir()
```

- [ ] **Step 4: Run, verify it passes**

Run: `uv run pytest tests/context/test_memory.py::test_remember_plugin_detection -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/detect.py tests/context/test_memory.py
git commit -m "feat(memory): detect co-installed remember plugin"
```

---

## Task 3: Tier rolling (idempotent)

**Files:**
- Create: `dummyindex/context/domains/memory/roll.py`
- Test: `tests/context/test_memory.py` (append)

- [ ] **Step 1: Write failing tests** (append to `tests/context/test_memory.py`)

```python
from datetime import date

from dummyindex.context.domains.memory import roll_tiers


def test_roll_moves_old_now_entries_to_recent(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "now.md").write_text(
        "# Now\n\n## 2026-06-05 14:00 | main\ntoday work\n\n"
        "## 2026-06-03 09:00 | main\nold work\n",
        encoding="utf-8",
    )
    report = roll_tiers(ctx, today=date(2026, 6, 5))
    assert report.now_to_recent == 1
    now_txt = (mdir / "now.md").read_text(encoding="utf-8")
    recent_txt = (mdir / "recent.md").read_text(encoding="utf-8")
    assert "today work" in now_txt and "old work" not in now_txt
    assert "old work" in recent_txt
    assert "2026-06-03" in report.moved_dates


def test_roll_is_idempotent(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "now.md").write_text(
        "# Now\n\n## 2026-06-03 09:00 | main\nold work\n", encoding="utf-8"
    )
    roll_tiers(ctx, today=date(2026, 6, 5))
    now_snap = (mdir / "now.md").read_text(encoding="utf-8")
    recent_snap = (mdir / "recent.md").read_text(encoding="utf-8")
    report2 = roll_tiers(ctx, today=date(2026, 6, 5))
    assert report2.now_to_recent == 0 and report2.recent_to_archive == 0
    assert (mdir / "now.md").read_text(encoding="utf-8") == now_snap
    assert (mdir / "recent.md").read_text(encoding="utf-8") == recent_snap


def test_roll_moves_stale_recent_to_archive(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "recent.md").write_text(
        "# Recent\n\n## 2026-05-01\nway old\n", encoding="utf-8"
    )
    report = roll_tiers(ctx, today=date(2026, 6, 5), recent_keep_days=7)
    assert report.recent_to_archive == 1
    assert "way old" in (mdir / "archive.md").read_text(encoding="utf-8")
    assert "way old" not in (mdir / "recent.md").read_text(encoding="utf-8")


def test_roll_keeps_undated_sections_in_place(tmp_path):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    mdir = memory_dir(ctx)
    (mdir / "now.md").write_text(
        "# Now\n\n## scratch note\nno date\n", encoding="utf-8"
    )
    report = roll_tiers(ctx, today=date(2026, 6, 5))
    assert report.now_to_recent == 0
    assert "no date" in (mdir / "now.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run, verify they fail**

Run: `uv run pytest tests/context/test_memory.py -k roll -q`
Expected: FAIL — `cannot import name 'roll_tiers'`.

- [ ] **Step 3: Create `roll.py`**

```python
"""Relocate dated tier entries downward. Deterministic + idempotent.

``now.md`` sections dated before today move into ``recent.md``;
``recent.md`` sections older than ``recent_keep_days`` move into
``archive.md``. Sections with no parseable date stay put. Compression of
the relocated prose is the agent's job, not this function's.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

from ._parse import render, section_date, split_sections
from .enums import TIER_HEADINGS, MemoryTier
from .models import RollReport, Section
from .store import memory_dir, write_text_atomic


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _partition(
    sections: tuple[Section, ...], predicate: Callable[[Section], bool]
) -> tuple[list[Section], list[Section]]:
    keep: list[Section] = []
    move: list[Section] = []
    for section in sections:
        (move if predicate(section) else keep).append(section)
    return keep, move


def _sort_desc(sections: list[Section]) -> tuple[Section, ...]:
    """Newest date first; undated sections sort last, order preserved."""
    return tuple(
        sorted(sections, key=lambda s: section_date(s.heading) or "", reverse=True)
    )


def _ordinal(iso_date: str) -> int:
    year, month, day = (int(part) for part in iso_date.split("-"))
    return date(year, month, day).toordinal()


def roll_tiers(
    context_dir: Path,
    *,
    today: date | None = None,
    recent_keep_days: int = 7,
) -> RollReport:
    today = today or date.today()
    today_str = today.isoformat()
    cutoff_ordinal = today.toordinal() - recent_keep_days

    mdir = memory_dir(context_dir)
    now_path = mdir / MemoryTier.NOW.value
    recent_path = mdir / MemoryTier.RECENT.value
    archive_path = mdir / MemoryTier.ARCHIVE.value

    now_pre, now_secs = split_sections(_read(now_path))
    rec_pre, rec_secs = split_sections(_read(recent_path))
    arc_pre, arc_secs = split_sections(_read(archive_path))

    def _is_before_today(section: Section) -> bool:
        iso = section_date(section.heading)
        return iso is not None and iso < today_str

    def _is_stale_recent(section: Section) -> bool:
        iso = section_date(section.heading)
        return iso is not None and _ordinal(iso) < cutoff_ordinal

    now_keep, now_down = _partition(now_secs, _is_before_today)
    rec_pool = list(rec_secs) + now_down
    rec_keep, rec_down = _partition(tuple(rec_pool), _is_stale_recent)
    arc_all = list(arc_secs) + rec_down

    if not now_down and not rec_down:
        return RollReport()  # nothing relocated → leave files byte-for-byte unchanged

    write_text_atomic(
        now_path, render(now_pre or TIER_HEADINGS[MemoryTier.NOW], _sort_desc(now_keep))
    )
    write_text_atomic(
        recent_path,
        render(rec_pre or TIER_HEADINGS[MemoryTier.RECENT], _sort_desc(rec_keep)),
    )
    write_text_atomic(
        archive_path,
        render(arc_pre or TIER_HEADINGS[MemoryTier.ARCHIVE], _sort_desc(arc_all)),
    )

    moved = now_down + rec_down
    moved_dates = tuple(
        sorted({iso for s in moved if (iso := section_date(s.heading)) is not None})
    )
    return RollReport(
        now_to_recent=len(now_down),
        recent_to_archive=len(rec_down),
        moved_dates=moved_dates,
    )
```

- [ ] **Step 4: Run, verify they pass**

Run: `uv run pytest tests/context/test_memory.py -k roll -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/roll.py tests/context/test_memory.py
git commit -m "feat(memory): idempotent tier rolling (now->recent->archive)"
```

---

## Task 4: SessionStart emit (read-only, suppressible)

**Files:**
- Create: `dummyindex/context/domains/memory/emit.py`
- Test: `tests/context/test_memory.py` (append)

- [ ] **Step 1: Write failing tests** (append to `tests/context/test_memory.py`)

```python
from dummyindex.context.domains.memory import render_session_start


def _seed_now(tmp_path, body):
    ctx = _ctx(tmp_path)
    ensure_memory_store(ctx)
    (memory_dir(ctx) / "now.md").write_text(
        f"# Now\n\n## 2026-06-05 10:00 | main\n{body}\n", encoding="utf-8"
    )


def test_session_start_none_when_no_store(tmp_path):
    assert render_session_start(tmp_path) is None


def test_session_start_none_when_store_empty(tmp_path):
    ensure_memory_store(_ctx(tmp_path))
    assert render_session_start(tmp_path) is None


def test_session_start_none_when_remember_present(tmp_path):
    _seed_now(tmp_path, "did stuff")
    (tmp_path / ".remember").mkdir()
    assert render_session_start(tmp_path) is None


def test_session_start_emits_block(tmp_path):
    _seed_now(tmp_path, "did stuff")
    block = render_session_start(tmp_path)
    assert block is not None
    assert "=== HANDOFF ===" in block
    assert "=== MEMORY ===" in block
    assert "/dummyindex-remember" in block
    assert "did stuff" in block


def test_session_start_truncates(tmp_path):
    _seed_now(tmp_path, "x" * 9000)
    block = render_session_start(tmp_path, max_chars=500)
    assert len(block) <= 520
    assert "truncated" in block
```

- [ ] **Step 2: Run, verify they fail**

Run: `uv run pytest tests/context/test_memory.py -k session_start -q`
Expected: FAIL — `cannot import name 'render_session_start'`.

- [ ] **Step 3: Create `emit.py`**

```python
"""Render the SessionStart memory block (read-only).

Returns ``None`` (emit nothing) when the remember plugin is present or
the store has no meaningful content yet.
"""
from __future__ import annotations

from pathlib import Path

from .detect import remember_plugin_present
from .enums import MemoryTier
from .store import memory_dir

_MAX_CHARS = 4000
_RECENT_HEAD = 1500


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _body_after_title(raw: str) -> str:
    """Everything below the leading ``# Title`` line, stripped."""
    lines = raw.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _head(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "\n…"


def render_session_start(root: Path, *, max_chars: int = _MAX_CHARS) -> str | None:
    if remember_plugin_present(root):
        return None
    mdir = memory_dir(root / ".context")
    if not mdir.is_dir():
        return None

    now = _body_after_title(_read(mdir / MemoryTier.NOW.value))
    recent = _body_after_title(_read(mdir / MemoryTier.RECENT.value))
    core = _body_after_title(_read(mdir / MemoryTier.CORE.value))
    if not (now or recent or core):
        return None

    parts: list[str] = ["=== MEMORY ==="]
    if now:
        parts.append(f"--- now.md ---\n{now}")
    if recent:
        parts.append(f"--- recent.md (head) ---\n{_head(recent, _RECENT_HEAD)}")
    if core:
        parts.append(f"--- core-memories.md ---\n{core}")

    handoff = (
        "=== HANDOFF ===\n"
        f"Write next handoff to: {mdir} — run /dummyindex-remember to save."
    )
    block = handoff + "\n\n" + "\n\n".join(parts)
    if len(block) > max_chars:
        block = block[:max_chars].rstrip() + "\n…(truncated)"
    return block
```

- [ ] **Step 4: Run, verify they pass**

Run: `uv run pytest tests/context/test_memory.py -k session_start -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/emit.py tests/context/test_memory.py
git commit -m "feat(memory): SessionStart emit with suppress + truncation"
```

---

## Task 5: Finalize domain public surface

**Files:**
- Modify: `dummyindex/context/domains/memory/__init__.py`

- [ ] **Step 1: Replace `__init__.py` with the full surface**

```python
"""Session-memory store: a markdown-first, agent-maintained remember-equivalent.

Deterministic mechanics live here; prose (writing/compressing summaries)
is the agent's job via the `/dummyindex-remember` skill.
"""
from __future__ import annotations

from .detect import remember_plugin_present
from .emit import render_session_start
from .enums import TIER_HEADINGS, MemoryTier
from .errors import MemoryStoreError, SessionMemoryError
from .models import RollReport, Section
from .roll import roll_tiers
from .store import (
    ensure_memory_store,
    memory_dir,
    tier_path,
    write_text_atomic,
)

__all__ = [
    "MemoryTier",
    "TIER_HEADINGS",
    "RollReport",
    "Section",
    "SessionMemoryError",
    "MemoryStoreError",
    "ensure_memory_store",
    "memory_dir",
    "tier_path",
    "write_text_atomic",
    "remember_plugin_present",
    "render_session_start",
    "roll_tiers",
]
```

- [ ] **Step 2: Run the full domain test file**

Run: `uv run pytest tests/context/test_memory.py -q`
Expected: PASS (all tests so far green).

- [ ] **Step 3: Commit**

```bash
git add dummyindex/context/domains/memory/__init__.py
git commit -m "feat(memory): finalize domain public surface"
```

---

## Task 6: CLI subcommand `dummyindex context memory <verb>`

**Files:**
- Create: `dummyindex/cli/memory.py`
- Modify: `dummyindex/context/enums.py`, `dummyindex/cli/__init__.py`, `dummyindex/cli/_usage.py`
- Test: `tests/context/test_memory_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/context/test_memory_cli.py`:

```python
"""Integration tests for `dummyindex context memory`."""
from __future__ import annotations

import pytest

from dummyindex.cli import dispatch

pytestmark = pytest.mark.integration


def test_memory_init_creates_store(tmp_path, capsys):
    rc = dispatch(["memory", "init", "--root", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / ".context" / "memory" / "now.md").exists()
    assert "memory init" in capsys.readouterr().out


def test_memory_roll_without_store_is_noop(tmp_path, capsys):
    rc = dispatch(["memory", "roll", "--root", str(tmp_path)])
    assert rc == 0
    assert "nothing to do" in capsys.readouterr().out


def test_memory_roll_reports_moves(tmp_path, capsys):
    dispatch(["memory", "init", "--root", str(tmp_path)])
    now = tmp_path / ".context" / "memory" / "now.md"
    now.write_text("# Now\n\n## 2020-01-01 09:00 | main\nancient\n", encoding="utf-8")
    rc = dispatch(["memory", "roll", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "memory roll" in out


def test_memory_session_start_silent_without_store(tmp_path, capsys):
    rc = dispatch(["memory", "session-start", "--root", str(tmp_path)])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_memory_session_start_prints_block(tmp_path, capsys):
    dispatch(["memory", "init", "--root", str(tmp_path)])
    now = tmp_path / ".context" / "memory" / "now.md"
    now.write_text("# Now\n\n## 2026-06-05 10:00 | main\nhello\n", encoding="utf-8")
    rc = dispatch(["memory", "session-start", "--root", str(tmp_path)])
    assert rc == 0
    assert "=== HANDOFF ===" in capsys.readouterr().out


def test_memory_no_verb_is_bad_args(capsys):
    assert dispatch(["memory"]) == 2


def test_memory_unknown_verb_is_bad_args(tmp_path):
    assert dispatch(["memory", "bogus", "--root", str(tmp_path)]) == 2
```

- [ ] **Step 2: Run, verify they fail**

Run: `uv run pytest tests/context/test_memory_cli.py -q`
Expected: FAIL — `unknown context subcommand 'memory'` (exit handling) / dispatch returns 2 for all.

- [ ] **Step 3: Add `MEMORY` to `ContextSubcommand`**

In `dummyindex/context/enums.py`, add the member to the `ContextSubcommand` enum (after `DOC_REORG`):

```python
    DOC_REORG = "doc-reorg"
    MEMORY = "memory"
```

- [ ] **Step 4: Create `dummyindex/cli/memory.py`**

```python
"""`dummyindex context memory <verb>` — session-memory store ops.

Verbs:
  session-start   read-only emit for the SessionStart hook (silent when the
                  remember plugin is present or the store is empty).
  roll            relocate dated entries down the tiers (idempotent).
  init            create `.context/memory/` + empty tier stubs.

Wire-only: parse args, call the memory domain, print, return an exit code.
"""
from __future__ import annotations

import sys
from datetime import date

from ._common import _parse_path_and_root, _resolve_context_root

_VERBS = ("session-start", "roll", "init")


def _cmd_memory(args: list[str]) -> int:
    from dummyindex.context.domains.memory import (
        ensure_memory_store,
        memory_dir,
        render_session_start,
        roll_tiers,
    )

    if not args:
        print(
            f"error: usage: dummyindex context memory {{{'|'.join(_VERBS)}}}",
            file=sys.stderr,
        )
        return 2
    verb, rest = args[0], args[1:]
    if verb not in _VERBS:
        print(f"error: unknown memory verb {verb!r}", file=sys.stderr)
        return 2

    scope, explicit_root, leftover = _parse_path_and_root(rest)
    if leftover:
        print(f"error: unknown argument(s): {leftover}", file=sys.stderr)
        return 2
    root = _resolve_context_root(scope, explicit_root=explicit_root)

    if verb == "session-start":
        block = render_session_start(root)
        if block:
            print(block)
        return 0  # a SessionStart hook must never fail the session

    context_dir = root / ".context"

    if verb == "init":
        created = ensure_memory_store(context_dir)
        if created:
            print(
                f"memory init: created {', '.join(created)} under "
                f"{memory_dir(context_dir)}"
            )
        else:
            print(f"memory init: store already present at {memory_dir(context_dir)}")
        return 0

    # verb == "roll"
    if not memory_dir(context_dir).is_dir():
        print("memory roll: no .context/memory/ store; nothing to do.")
        return 0
    report = roll_tiers(context_dir, today=date.today())
    suffix = (
        f" (dates: {', '.join(report.moved_dates)})" if report.moved_dates else ""
    )
    print(
        f"memory roll: now→recent {report.now_to_recent}, "
        f"recent→archive {report.recent_to_archive}{suffix}"
    )
    return 0
```

- [ ] **Step 5: Register the handler in `dummyindex/cli/__init__.py`**

Add the import alongside the others (after `from .init import _cmd_init`):

```python
from .memory import _cmd_memory
```

Add the handler entry to `_HANDLERS` (after the `DOC_REORG` line):

```python
    ContextSubcommand.DOC_REORG: _cmd_doc_reorg,
    ContextSubcommand.MEMORY: _cmd_memory,
```

- [ ] **Step 6: Document it in `dummyindex/cli/_usage.py`**

After the `refresh-indexes` block, add:

```
  memory session-start|roll|init [path] [--root DIR]
                                    Session-memory store under .context/memory/.
                                    session-start: emit the SessionStart block
                                    (silent if the remember plugin is present).
                                    roll: relocate dated entries now→recent→archive
                                    (idempotent). init: create the store stubs.
```

- [ ] **Step 7: Run, verify they pass**

Run: `uv run pytest tests/context/test_memory_cli.py -q`
Expected: PASS (7 tests).

- [ ] **Step 8: Commit**

```bash
git add dummyindex/cli/memory.py dummyindex/cli/__init__.py dummyindex/cli/_usage.py dummyindex/context/enums.py tests/context/test_memory_cli.py
git commit -m "feat(memory): wire `dummyindex context memory` subcommand"
```

---

## Task 7: SessionStart hook — second command

**Files:**
- Modify: `dummyindex/context/hooks.py`
- Test: `tests/context/test_hooks.py` (append)

- [ ] **Step 1: Write the failing test** (append to `tests/context/test_hooks.py`)

```python
def test_install_writes_memory_session_start_command(tmp_path):
    import json

    from dummyindex.context.hooks import install

    install(tmp_path)
    settings = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    commands = [
        h["command"]
        for entry in settings["hooks"]["SessionStart"]
        for h in entry["hooks"]
    ]
    assert any("plan-update" in c for c in commands)
    assert any("memory session-start" in c for c in commands)
```

- [ ] **Step 2: Run, verify it fails**

Run: `uv run pytest tests/context/test_hooks.py::test_install_writes_memory_session_start_command -q`
Expected: FAIL — only `plan-update` present.

- [ ] **Step 3: Add the second command to `_SESSION_START_HOOK`**

In `dummyindex/context/hooks.py`, extend the `hooks` list of `_SESSION_START_HOOK` with a second command (keep the existing `plan-update` command first):

```python
_SESSION_START_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"# {SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context plan-update --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        },
        {
            "type": "command",
            "command": (
                f"# {SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context memory session-start --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        },
    ],
}
```

> The installer already matches its entry by `SENTINEL` and refreshes the body in place when it differs, so existing installs pick up the second command on the next `dummyindex context hooks install` / `ingest`.

- [ ] **Step 4: Run the hooks test file**

Run: `uv run pytest tests/context/test_hooks.py -q`
Expected: PASS — the new test passes and existing hook tests still pass.

> If an existing test asserts the SessionStart entry has exactly one command, update it to assert *at least* the `plan-update` command is present (the entry now legitimately carries two). Re-run until green.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/hooks.py tests/context/test_hooks.py
git commit -m "feat(memory): inject memory block via existing SessionStart hook"
```

---

## Task 8: Seed the store on ingest + carve-out regression

**Files:**
- Modify: `dummyindex/context/build/runner.py`
- Test: `tests/context/test_runner.py` (append)

- [ ] **Step 1: Write failing tests** (append to `tests/context/test_runner.py`)

```python
def test_build_all_seeds_memory_store(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    from dummyindex.context.build.runner import build_all

    build_all(tmp_path, out_root=tmp_path, dummyindex_version="test")
    assert (tmp_path / ".context" / "memory" / "now.md").exists()
    assert (tmp_path / ".context" / "memory" / "core-memories.md").exists()


def test_rebuild_preserves_memory_content(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    from dummyindex.context.build.runner import build_all

    build_all(tmp_path, out_root=tmp_path, dummyindex_version="test")
    now_path = tmp_path / ".context" / "memory" / "now.md"
    now_path.write_text(
        "# Now\n\n## 2026-06-05 10:00 | main\nprecious note\n", encoding="utf-8"
    )
    build_all(tmp_path, out_root=tmp_path, dummyindex_version="test")
    assert "precious note" in now_path.read_text(encoding="utf-8")
```

> Check `build_all`'s signature in `dummyindex/context/build/runner.py` (around line 71). If the first positional is named `scope` rather than accepting a bare path, call it as the existing tests in this file do — mirror the closest existing `build_all(...)` call in `test_runner.py` for the exact argument names.

- [ ] **Step 2: Run, verify the seed test fails**

Run: `uv run pytest tests/context/test_runner.py -k memory -q`
Expected: FAIL — `.context/memory/now.md` does not exist.

- [ ] **Step 3: Seed the store in `build_all`**

In `dummyindex/context/build/runner.py`, locate the source-docs catalog `try/except` block (it appends `source-docs/INDEX.json` / `source-docs/INDEX.md` to `written`, ~line 210-216) and the `# INDEX.md is always written last` comment that follows (~line 218). Insert this block **between** them:

```python
    # Session-memory store (agent-maintained; never regenerated). Seed empty
    # tier stubs so the SessionStart hook + /dummyindex-remember have a home.
    # Idempotent and non-destructive — existing memory survives every rebuild.
    try:
        from dummyindex.context.domains.memory import ensure_memory_store

        for tier_name in ensure_memory_store(context_dir):
            written.append(f"memory/{tier_name}")
    except Exception as exc:
        import warnings

        warnings.warn(f"memory store seed failed: {exc!r}; continuing")
```

- [ ] **Step 4: Run, verify both tests pass**

Run: `uv run pytest tests/context/test_runner.py -k memory -q`
Expected: PASS (2 tests). The `rebuild` test confirms the carve-out: `ensure_memory_store` is non-destructive and nothing in `build_all` wipes `memory/`.

- [ ] **Step 5: Confirm no full-tree wipe exists (defensive check)**

Run: `grep -rn "rmtree" dummyindex/context | grep -i context`
Expected: no result that removes the whole `.context/` directory (only targeted legacy-path migrations). If a wipe of `context_dir` is found, add a guard that excludes `memory/`. (Current code has none — this is a verification step.)

- [ ] **Step 6: Commit**

```bash
git add dummyindex/context/build/runner.py tests/context/test_runner.py
git commit -m "feat(memory): seed .context/memory/ on ingest; preserve on rebuild"
```

---

## Task 9: The `/dummyindex-remember` skill markdown

**Files:**
- Create: `dummyindex/skills/memory/SKILL.md`

- [ ] **Step 1: Create `dummyindex/skills/memory/SKILL.md`**

```markdown
---
name: dummyindex-remember
description: Save a session handoff into dummyindex's `.context/memory/` store. Use at session end or when the user says "save the session", "remember this", or types "/dummyindex-remember". Appends a first-person summary to now.md, rolls now→recent→archive, and promotes durable facts to core-memories.md.
allowed-tools: Read, Write, Bash
---

# /dummyindex-remember — save the session into `.context/memory/`

> Installed from dummyindex `__VERSION__`.

Write a handoff so the next session continues cleanly. You were here — write in the first person ("I").

## Steps

1. **Locate the store** at `<repo>/.context/memory/`. If it's missing, create it:
   ```bash
   dummyindex context memory init
   ```

2. **Read `now.md`** (`<repo>/.context/memory/now.md`). A 1-line read is enough — the Write tool
   refuses to write an existing file you haven't read.

3. **Prepend one entry** to the TOP of `now.md` (newest first), dated so the roller can bucket it:
   ```
   ## YYYY-MM-DD HH:MM | <branch>
   <2–4 lines: what I did, what I decided, what's next. Specific: files, PRs, branches.>
   ```

4. **Roll the tiers** (deterministic + idempotent — relocates dated entries now→recent→archive):
   ```bash
   dummyindex context memory roll
   ```

5. **Compress the rolled prose.** Read the roller's report. For each date it moved into `recent.md`,
   tighten that `## YYYY-MM-DD` section to one compact paragraph. Heavily compress anything pushed
   into `archive.md`.

6. **Promote durable facts.** Move any cross-session fact or key moment worth keeping verbatim into
   `core-memories.md` as a bullet (prefix a standout moment with `IDENTITY CANDIDATE:`).

7. Say **"Saved."** — nothing else.

## Rules

- Under ~20 lines of actual writing. Forward-looking — the next session doesn't care about the journey.
- Specific: file paths, PR numbers, branch names.
- If there's nothing meaningful to hand off, append `No active work.` to `now.md` and stop.
- Never delete prior entries; the roller relocates, it doesn't erase.
```

- [ ] **Step 2: Commit**

```bash
git add dummyindex/skills/memory/SKILL.md
git commit -m "feat(memory): /dummyindex-remember skill"
```

---

## Task 10: Packaging + install copy

**Files:**
- Modify: `pyproject.toml`, `dummyindex/__main__.py`
- Test: `tests/test_install.py` (append)

- [ ] **Step 1: Write the failing install test** (append to `tests/test_install.py`)

```python
def test_install_copies_memory_skill(tmp_path):
    from dummyindex.__main__ import install

    install(scope="project", project_dir=tmp_path, skill_only=True)
    skill = tmp_path / ".claude" / "skills" / "dummyindex-remember" / "SKILL.md"
    assert skill.exists()
    assert "name: dummyindex-remember" in skill.read_text(encoding="utf-8")
```

> Check `install`'s real signature at the top of `dummyindex/__main__.py` (around line 101) and mirror the argument names used by the existing tests in `tests/test_install.py` (e.g. `scope=`, `project_dir=`, and the skill-only flag's exact name). Adjust the call above to match before running.

- [ ] **Step 2: Run, verify it fails**

Run: `uv run pytest tests/test_install.py -k memory_skill -q`
Expected: FAIL — the skill file is not copied.

- [ ] **Step 3: Add package-data in `pyproject.toml`**

In `[tool.setuptools.package-data]` under `dummyindex = [ ... ]`, add the new glob (after `"skills/retrieval/*.md",`):

```toml
    "skills/memory/*.md",
```

- [ ] **Step 4: Copy the memory skill in `install()`**

In `dummyindex/__main__.py`, after the companion-subdir copy loop and before the
`(skill_dir / ".dummyindex_version").write_text(...)` line (~line 173), add:

```python
    # The session-memory handoff ships as its OWN top-level skill so it is
    # invocable as /dummyindex-remember — a sibling of /dummyindex, not a
    # companion nested under it. (Claude Code discovers skills by
    # .claude/skills/<name>/SKILL.md.)
    mem_src = _SKILLS_DIR / "memory" / "SKILL.md"
    if mem_src.is_file():
        mem_dst = base / ".claude" / "skills" / "dummyindex-remember" / "SKILL.md"
        mem_dst.parent.mkdir(parents=True, exist_ok=True)
        mem_dst.write_text(
            mem_src.read_text(encoding="utf-8").replace("__VERSION__", __version__),
            encoding="utf-8",
        )
        print(f"  memory skill     ->  {mem_dst}")
```

- [ ] **Step 5: Run, verify it passes**

Run: `uv run pytest tests/test_install.py -k memory_skill -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml dummyindex/__main__.py tests/test_install.py
git commit -m "feat(memory): ship + install /dummyindex-remember skill"
```

---

## Task 11: Orchestrator pointer

**Files:**
- Modify: `dummyindex/skills/skill.md`

- [ ] **Step 1: Add a pointer section** to `dummyindex/skills/skill.md`, immediately before the `## Final word` heading:

```markdown
## Session memory (sibling skill)

dummyindex ships a markdown-first session-memory store at `.context/memory/`
(tiers `now.md` → `recent.md` → `archive.md`, plus `core-memories.md`). It is
**not** part of the generated index and is never regenerated — `ingest` only
seeds empty stubs; `refresh`/`rebuild` leave it untouched. The SessionStart hook
injects a memory block (suppressed automatically if the `remember` plugin is also
installed). To save a handoff, invoke **`/dummyindex-remember`**: it appends a
first-person summary to `now.md`, runs `dummyindex context memory roll`, and
promotes durable facts to `core-memories.md`.

```

- [ ] **Step 2: Commit**

```bash
git add dummyindex/skills/skill.md
git commit -m "docs(memory): point the orchestrator skill at session memory"
```

---

## Task 12: Full pre-flight + review

**Files:** none (verification)

- [ ] **Step 1: Full test suite**

Run: `uv run pytest -q`
Expected: all green (existing suite + new memory tests). Fix any regressions before continuing.

- [ ] **Step 2: Coverage on the new domain**

Run: `uv run pytest --cov=dummyindex.context.domains.memory --cov=dummyindex.cli.memory --cov-report=term-missing -q`
Expected: ≥ 80% on the new modules. Add targeted tests for any uncovered branch.

- [ ] **Step 3: Lint / format (if wired)**

Run: `uv run ruff check dummyindex tests && uv run ruff format --check dummyindex tests`
Expected: clean. Run `uv run ruff format dummyindex tests` if it reports diffs, then re-run tests.

- [ ] **Step 4: End-to-end smoke test**

```bash
cd /tmp && rm -rf di-mem-smoke && mkdir di-mem-smoke && cd di-mem-smoke
git init -q && printf 'def f():\n    return 1\n' > a.py
dummyindex context memory init --root .
printf '# Now\n\n## 2020-01-01 09:00 | main\nancient entry\n' > .context/memory/now.md
dummyindex context memory roll --root .
dummyindex context memory session-start --root .   # prints HANDOFF + MEMORY block
mkdir .remember
dummyindex context memory session-start --root .   # prints NOTHING (suppressed)
```
Expected: roll reports `now→recent 1`; first session-start prints the block; the second (with `.remember/`) prints nothing.

- [ ] **Step 5: Run the project's Python reviewer**

Per project convention, run the `python-reviewer` agent over the changes under `dummyindex/` and
`tests/`. Address any CRITICAL/HIGH findings (frozen-dataclass, enum-constant, layering,
CLI-boundary-I/O, file-size rules). Re-run `uv run pytest -q` after fixes.

- [ ] **Step 6: Refresh the repo's own context index**

Run: `dummyindex context rebuild --changed`
Expected: `.context/` updated to reflect the new modules.

- [ ] **Step 7: Final commit (if review produced fixes)**

```bash
git add -A
git commit -m "chore(memory): address review + refresh context index"
```

---

## Self-review (filled in)

**Spec coverage:**
- `.context/memory/` 4-tier store → Tasks 1, 8 (seed). ✓
- `memory session-start` emit + suppress → Tasks 4, 6. ✓
- `memory roll` idempotent tier bucketing → Tasks 3, 6. ✓
- `/dummyindex-remember` skill → Tasks 9, 10 (ship/install). ✓
- SessionStart injection folded into existing hook → Task 7. ✓
- Detect-and-suppress coexistence → Tasks 2, 4. ✓
- Carve-out (refresh/rebuild never regenerate `memory/`) → Task 8 (non-destructive seed + regression test + grep guard). ✓
- Differences-from-remember (no Haiku, no PostToolUse, no `today-*.md`) → encoded by omission; capture is one summary per skill run (Task 9). ✓
- Spec §9 mentioned editing `.context/HOW_TO_USE.md` generation: **dropped (YAGNI)** — the session-start block is self-describing and the orchestrator pointer (Task 11) covers discoverability. Noted as a deliberate deviation.

**Placeholder scan:** every code/test step carries complete code. Two steps ask the implementer to verify a real signature before calling (`build_all`, `install`) — these reference existing same-file tests for the exact form rather than guessing, which is verification, not a placeholder.

**Type consistency:** `ensure_memory_store(context_dir)`, `memory_dir(context_dir)`, `roll_tiers(context_dir, *, today, recent_keep_days)`, `render_session_start(root, *, max_chars)`, `remember_plugin_present(root)` — names/signatures match across the domain, CLI (Task 6), hook (Task 7), and runner (Task 8). `RollReport(now_to_recent, recent_to_archive, moved_dates)` and `Section(heading, body)` are used consistently.
