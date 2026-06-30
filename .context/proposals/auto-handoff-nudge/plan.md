# Auto-handoff Nudge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/dummyindex-remember` effectively automatic — a `PreCompact` hook writes a deterministic breadcrumb to `now.md`, and a `Stop` hook nudges the agent to offer a real handoff after a long or subagent-heavy session — without ever auto-authoring the handoff.

**Architecture:** Two new deterministic `context memory` verbs (`nudge`, `breadcrumb`) live in the `domains/memory/` domain (pure logic, inputs injected); the CLI layer reads the hook's stdin JSON and prints/writes. `nudge` emits a `Stop` `additionalContext` JSON (verified to reach the model and grant a turn) only when significant and not suppressed; `breadcrumb` prepends a tagged entry to `now.md`. Both wire into `.claude/settings.json` via the existing `DUMMYINDEX_AUTO_REFRESH` sentinel in `hooks.py`. Neither ever touches `meta.indexed_commit` (the commit-anchor stamping rule: no hook may stamp).

**Tech Stack:** Python 3.10+, pytest, ruff, mypy. Reuses `dummyindex/usage/transcripts.py` (`load_session`, `find_main_transcript`), `domains/memory/` (`_parse`, `store`, `_io.write_text_atomic`, `detect.remember_plugin_present`).

**Spec:** `docs/specs/2026-06-08-auto-handoff-nudge-design.md`

**Convention notes (this repo):** frozen dataclasses, enum constants, typed errors, CLI-boundary I/O, files <800 lines, immutable patterns. Run `python-reviewer` after touching `dummyindex/` or `tests/`. Commit each task locally (no push, no `Co-Authored-By`).

---

## File Structure

| File | Responsibility |
|---|---|
| `dummyindex/context/domains/memory/enums.py` | **modify** — add `MemoryVerb.NUDGE`/`BREADCRUMB`; add `AUTO_BREADCRUMB_TAG` constant. |
| `dummyindex/context/domains/memory/nudge.py` | **create** — significance, suppression state, now.md freshness, `additionalContext` rendering, `decide_nudge` orchestrator. |
| `dummyindex/context/domains/memory/breadcrumb.py` | **create** — `BreadcrumbFacts`, `render_entry`, `write_breadcrumb`, `gather_breadcrumb_facts` (git + transcript). |
| `dummyindex/context/domains/memory/__init__.py` | **modify** — export the new entry points. |
| `dummyindex/cli/memory.py` | **modify** — dispatch `nudge`/`breadcrumb`; `_read_hook_stdin` helper. |
| `dummyindex/context/hooks.py` | **modify** — `Stop` + `PreCompact` entries; `HookStatus` fields; install loop; `CURRENT_CLAUDE_EVENTS`; `status`. |
| `dummyindex/cli/hooks.py` | **modify** — print Stop + PreCompact in `status`. |
| `dummyindex/cli/_usage.py` | **modify** — document the new verbs. |
| `tests/context/test_nudge.py` | **create** — significance / suppression / freshness / decide / CLI. |
| `tests/context/test_breadcrumb.py` | **create** — render / write / gather / CLI. |
| `tests/context/test_hooks.py` | **modify** — update for 3 hooks; add Stop/PreCompact wiring asserts. |
| `docs/COMMANDS.md`, `docs/guide/07-cli.md` | **modify** — document the new verbs. |

---

### Task 1: Add the new verbs + breadcrumb tag to the memory enum

**Files:**
- Modify: `dummyindex/context/domains/memory/enums.py`
- Test: `tests/context/test_nudge.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/context/test_nudge.py`:

```python
"""Tests for the Stop-hook handoff nudge (dummyindex context memory nudge)."""
from __future__ import annotations

from dummyindex.context.domains.memory.enums import AUTO_BREADCRUMB_TAG, MemoryVerb


def test_new_memory_verbs_exist():
    assert MemoryVerb("nudge") is MemoryVerb.NUDGE
    assert MemoryVerb("breadcrumb") is MemoryVerb.BREADCRUMB


def test_auto_breadcrumb_tag_constant():
    assert AUTO_BREADCRUMB_TAG == "(auto-breadcrumb)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -v`
Expected: FAIL — `AttributeError: NUDGE` / `ImportError: AUTO_BREADCRUMB_TAG`.

- [ ] **Step 3: Implement**

In `dummyindex/context/domains/memory/enums.py`, add to `MemoryVerb`:

```python
class MemoryVerb(str, Enum):
    """The verbs accepted by `dummyindex context memory <verb>`."""

    SESSION_START = "session-start"
    ROLL = "roll"
    INIT = "init"
    NUDGE = "nudge"
    BREADCRUMB = "breadcrumb"
```

And add the module-level constant (near `TIER_HEADINGS`):

```python
# Heading suffix marking a deterministic, auto-written breadcrumb entry in
# now.md — distinguishes it from an agent-authored handoff.
AUTO_BREADCRUMB_TAG = "(auto-breadcrumb)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/enums.py tests/context/test_nudge.py
git commit -m "feat(memory): add nudge/breadcrumb verbs + auto-breadcrumb tag"
```

---

### Task 2: Significance detection

**Files:**
- Create: `dummyindex/context/domains/memory/nudge.py`
- Test: `tests/context/test_nudge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_nudge.py`:

```python
from datetime import datetime, timezone

from dummyindex.context.domains.memory import nudge as nudge_mod
from dummyindex.usage.models import TurnUsage


def _turn(output_tokens: int) -> TurnUsage:
    return TurnUsage(
        timestamp=datetime(2026, 6, 8, tzinfo=timezone.utc),
        session_id="s",
        project="p",
        model="claude-opus-4-8",
        input_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        output_tokens=output_tokens,
        is_subagent=False,
    )


def test_significant_when_subagents_used():
    assert nudge_mod.is_significant((_turn(10),), subagent_file_count=1) is True


def test_significant_when_output_tokens_over_threshold():
    big = (_turn(nudge_mod.LONG_OUTPUT_TOKENS),)
    assert nudge_mod.is_significant(big, subagent_file_count=0) is True


def test_not_significant_when_small_and_no_subagents():
    small = (_turn(100), _turn(200))
    assert nudge_mod.is_significant(small, subagent_file_count=0) is False


def test_total_main_output_tokens_sums():
    assert nudge_mod.total_main_output_tokens((_turn(100), _turn(250))) == 350
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -k significant -v`
Expected: FAIL — `ModuleNotFoundError: ...memory.nudge`.

- [ ] **Step 3: Implement**

Create `dummyindex/context/domains/memory/nudge.py`:

```python
"""Stop-hook handoff nudge: decide whether to prompt for a session handoff.

Deterministic. No prose — the rich handoff is the agent's job via
/dummyindex-remember. This module only decides *whether* to nudge and
renders the `additionalContext` payload the Stop hook prints to stdout.
"""
from __future__ import annotations

import json
from collections.abc import Iterable

from dummyindex.usage.models import TurnUsage

# A session is "long" once its main-thread output crosses this many tokens.
# Starting constant — calibrated by observation, not user-configurable in v1.
LONG_OUTPUT_TOKENS = 40_000


def total_main_output_tokens(main_turns: Iterable[TurnUsage]) -> int:
    """Sum of main-thread output tokens across the session's turns."""
    return sum(turn.output_tokens for turn in main_turns)


def is_significant(
    main_turns: tuple[TurnUsage, ...], subagent_file_count: int
) -> bool:
    """True when the session is worth prompting a handoff for.

    Significant if any subagent ran, or the main-thread output crossed the
    long-session threshold.
    """
    if subagent_file_count > 0:
        return True
    return total_main_output_tokens(main_turns) >= LONG_OUTPUT_TOKENS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -k "significant or total" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/nudge.py tests/context/test_nudge.py
git commit -m "feat(memory): session-significance detection for the nudge"
```

---

### Task 3: Suppression state (per-session marker)

**Files:**
- Modify: `dummyindex/context/domains/memory/nudge.py`
- Test: `tests/context/test_nudge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_nudge.py`:

```python
from pathlib import Path


def test_already_nudged_false_then_true(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    assert nudge_mod.already_nudged(ctx, "sess-1") is False
    nudge_mod.mark_nudged(ctx, "sess-1", now)
    assert nudge_mod.already_nudged(ctx, "sess-1") is True
    # State lives under the gitignored cache dir.
    assert (ctx / "cache" / "nudge-state.json").exists()


def test_mark_nudged_is_per_session(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    nudge_mod.mark_nudged(ctx, "sess-1", now)
    assert nudge_mod.already_nudged(ctx, "sess-2") is False


def test_empty_session_id_never_nudged(tmp_path: Path):
    ctx = tmp_path / ".context"
    assert nudge_mod.already_nudged(ctx, "") is False
    nudge_mod.mark_nudged(ctx, "", datetime(2026, 6, 8, tzinfo=timezone.utc))
    assert not (ctx / "cache" / "nudge-state.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -k nudged -v`
Expected: FAIL — `AttributeError: already_nudged`.

- [ ] **Step 3: Implement**

Add to `dummyindex/context/domains/memory/nudge.py` (imports + functions):

```python
from datetime import datetime
from pathlib import Path

from .._io import write_text_atomic


def _state_path(context_dir: Path) -> Path:
    """Per-session nudge marker file (gitignored cache)."""
    return context_dir / "cache" / "nudge-state.json"


def _load_state(context_dir: Path) -> dict:
    path = _state_path(context_dir)
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    return obj if isinstance(obj, dict) else {}


def already_nudged(context_dir: Path, session_id: str) -> bool:
    """True when a nudge has already fired for this session."""
    if not session_id:
        return False
    return session_id in _load_state(context_dir)


def mark_nudged(context_dir: Path, session_id: str, now: datetime) -> None:
    """Record that we nudged this session. No-op for an empty session id."""
    if not session_id:
        return
    state = _load_state(context_dir)
    state[session_id] = {"nudged_at": now.isoformat()}
    write_text_atomic(_state_path(context_dir), json.dumps(state, indent=2) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -k nudged -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/nudge.py tests/context/test_nudge.py
git commit -m "feat(memory): per-session nudge suppression state"
```

---

### Task 4: now.md freshness check (ignore breadcrumbs)

**Files:**
- Modify: `dummyindex/context/domains/memory/nudge.py`
- Test: `tests/context/test_nudge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_nudge.py`:

```python
def _write_now(ctx: Path, body: str) -> None:
    mdir = ctx / "session-memory"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "now.md").write_text(body, encoding="utf-8")


def test_real_handoff_today_suppresses(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    _write_now(ctx, "# Now\n\n## 2026-06-08 13:00 | main\nDid real work.\n")
    assert nudge_mod.real_handoff_saved_today(tmp_path, now) is True


def test_auto_breadcrumb_today_does_not_suppress(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    _write_now(ctx, "# Now\n\n## 2026-06-08 13:00 | main (auto-breadcrumb)\nx\n")
    assert nudge_mod.real_handoff_saved_today(tmp_path, now) is False


def test_old_handoff_does_not_suppress(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    _write_now(ctx, "# Now\n\n## 2026-06-01 09:00 | main\nold.\n")
    assert nudge_mod.real_handoff_saved_today(tmp_path, now) is False


def test_empty_now_does_not_suppress(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=timezone.utc)
    _write_now(ctx, "# Now\n")
    assert nudge_mod.real_handoff_saved_today(tmp_path, now) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -k handoff -v`
Expected: FAIL — `AttributeError: real_handoff_saved_today`.

- [ ] **Step 3: Implement**

Add to `dummyindex/context/domains/memory/nudge.py`:

```python
from .enums import AUTO_BREADCRUMB_TAG, MemoryTier
from ._parse import read_text_or_empty, section_date, split_sections
from .store import memory_dir


def real_handoff_saved_today(root: Path, now: datetime) -> bool:
    """True when now.md's newest entry is a real (non-breadcrumb) handoff
    dated today — meaning the user already saved, so don't nudge."""
    now_path = memory_dir(root / ".context") / MemoryTier.NOW.value
    _preamble, sections = split_sections(read_text_or_empty(now_path))
    if not sections:
        return False
    top = sections[0]
    iso = section_date(top.heading)
    return iso == now.date().isoformat() and AUTO_BREADCRUMB_TAG not in top.heading
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -k handoff -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/nudge.py tests/context/test_nudge.py
git commit -m "feat(memory): suppress nudge when a real handoff was saved today"
```

---

### Task 5: additionalContext rendering + `decide_nudge` orchestrator

**Files:**
- Modify: `dummyindex/context/domains/memory/nudge.py`
- Test: `tests/context/test_nudge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_nudge.py`:

```python
def test_render_additional_context_shape():
    out = nudge_mod.render_additional_context(
        total_output_tokens=50000, subagent_file_count=3
    )
    obj = json.loads(out)
    assert obj["hookSpecificOutput"]["hookEventName"] == "Stop"
    ctx = obj["hookSpecificOutput"]["additionalContext"]
    assert "/dummyindex-remember" in ctx
    assert "Do NOT save automatically" in ctx


def test_decide_returns_none_when_remember_plugin_present(tmp_path: Path):
    (tmp_path / ".remember").mkdir()
    out = nudge_mod.decide_nudge(
        root=tmp_path,
        main_transcript=None,
        session_id="s",
        now=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )
    assert out is None


def test_decide_returns_none_when_already_nudged(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, tzinfo=timezone.utc)
    nudge_mod.mark_nudged(ctx, "s", now)
    out = nudge_mod.decide_nudge(
        root=tmp_path, main_transcript=None, session_id="s", now=now
    )
    assert out is None


def test_decide_fires_and_marks_for_subagent_session(tmp_path: Path, monkeypatch):
    transcript = tmp_path / "main.jsonl"
    transcript.write_text("", encoding="utf-8")
    now = datetime(2026, 6, 8, tzinfo=timezone.utc)
    # Force load_session → one small main turn + 2 subagent files (significant).
    monkeypatch.setattr(
        nudge_mod, "load_session", lambda p: ((_turn(10),), (), 2)
    )
    out = nudge_mod.decide_nudge(
        root=tmp_path, main_transcript=transcript, session_id="s", now=now
    )
    assert out is not None
    assert "Stop" in out
    # Marker is now set → a second decide is suppressed.
    assert nudge_mod.already_nudged(tmp_path / ".context", "s") is True
    assert nudge_mod.decide_nudge(
        root=tmp_path, main_transcript=transcript, session_id="s", now=now
    ) is None


def test_decide_returns_none_when_not_significant(tmp_path: Path, monkeypatch):
    transcript = tmp_path / "main.jsonl"
    transcript.write_text("", encoding="utf-8")
    monkeypatch.setattr(nudge_mod, "load_session", lambda p: ((_turn(10),), (), 0))
    out = nudge_mod.decide_nudge(
        root=tmp_path,
        main_transcript=transcript,
        session_id="s",
        now=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )
    assert out is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -k "render_additional or decide" -v`
Expected: FAIL — `AttributeError: render_additional_context` / `decide_nudge`.

- [ ] **Step 3: Implement**

Add to `dummyindex/context/domains/memory/nudge.py`:

```python
from typing import Optional

from .detect import remember_plugin_present
from dummyindex.usage.transcripts import load_session


def render_additional_context(
    *, total_output_tokens: int, subagent_file_count: int
) -> str:
    """The Stop-hook stdout payload that reaches the model and grants a turn."""
    message = (
        f"dummyindex: this session is substantial (subagents: {subagent_file_count}; "
        f"~{total_output_tokens:,} main-thread output tokens) and no handoff has been "
        f"saved this session. In one short line, offer the user the option to checkpoint "
        f"a session handoff, and only if they agree run /dummyindex-remember. "
        f"Do NOT save automatically."
    )
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": message,
            }
        }
    )


def decide_nudge(
    *,
    root: Path,
    main_transcript: Optional[Path],
    session_id: str,
    now: datetime,
) -> Optional[str]:
    """Return the additionalContext JSON to print, or None to stay silent.

    Cheap checks first (O(1) file stats) so the per-turn Stop hook only pays
    for the transcript parse on the rare turn that actually nudges.
    """
    if remember_plugin_present(root):
        return None
    context_dir = root / ".context"
    if already_nudged(context_dir, session_id):
        return None
    if real_handoff_saved_today(root, now):
        return None
    if main_transcript is None or not main_transcript.exists():
        return None
    main_turns, _subagent_turns, subagent_file_count = load_session(main_transcript)
    if not is_significant(main_turns, subagent_file_count):
        return None
    mark_nudged(context_dir, session_id, now)
    return render_additional_context(
        total_output_tokens=total_main_output_tokens(main_turns),
        subagent_file_count=subagent_file_count,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -v`
Expected: PASS (all nudge-domain tests).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/nudge.py tests/context/test_nudge.py
git commit -m "feat(memory): decide_nudge orchestrator + additionalContext payload"
```

---

### Task 6: BreadcrumbFacts + render_entry (pure)

**Files:**
- Create: `dummyindex/context/domains/memory/breadcrumb.py`
- Test: `tests/context/test_breadcrumb.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/context/test_breadcrumb.py`:

```python
"""Tests for the PreCompact deterministic breadcrumb."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dummyindex.context.domains.memory import breadcrumb as bc
from dummyindex.context.domains.memory.enums import AUTO_BREADCRUMB_TAG


def _facts(**kw) -> bc.BreadcrumbFacts:
    base = dict(
        branch="main",
        files_changed=2,
        insertions=10,
        deletions=3,
        changed_files=("a.py", "b.py"),
        main_turns=12,
        subagents=1,
    )
    base.update(kw)
    return bc.BreadcrumbFacts(**base)


def test_render_entry_heading_is_tagged():
    now = datetime(2026, 6, 8, 14, 5, tzinfo=timezone.utc)
    section = bc.render_entry(_facts(), now)
    assert section.heading == f"## 2026-06-08 14:05 | main {AUTO_BREADCRUMB_TAG}"
    assert "2 files changed (+10/-3)" in section.body
    assert "subagents: 1" in section.body
    assert "a.py, b.py" in section.body


def test_render_entry_caps_file_list():
    files = tuple(f"f{i}.py" for i in range(12))
    section = bc.render_entry(_facts(changed_files=files, files_changed=12), now=datetime(2026, 6, 8, tzinfo=timezone.utc))
    assert "+4 more" in section.body  # 12 files, cap 8 → 4 more
    assert "f8.py" not in section.body


def test_render_entry_no_changes():
    section = bc.render_entry(
        _facts(changed_files=(), files_changed=0, insertions=0, deletions=0),
        now=datetime(2026, 6, 8, tzinfo=timezone.utc),
    )
    assert "(no tracked changes)" in section.body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_breadcrumb.py -k render -v`
Expected: FAIL — `ModuleNotFoundError: ...memory.breadcrumb`.

- [ ] **Step 3: Implement**

Create `dummyindex/context/domains/memory/breadcrumb.py`:

```python
"""PreCompact breadcrumb: a deterministic, factual now.md entry.

Written before context is lost to compaction so a session is never blank
even if the handoff CTA is ignored. No prose, no LLM. Tagged with
AUTO_BREADCRUMB_TAG so a later agent-authored handoff supersedes it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .enums import AUTO_BREADCRUMB_TAG
from .models import Section

# How many changed-file paths to list before collapsing to "+k more".
MAX_LISTED_FILES = 8


@dataclass(frozen=True)
class BreadcrumbFacts:
    """Deterministic session facts captured for a breadcrumb entry."""

    branch: str
    files_changed: int
    insertions: int
    deletions: int
    changed_files: tuple[str, ...]
    main_turns: int
    subagents: int


def render_entry(facts: BreadcrumbFacts, now: datetime) -> Section:
    """Build the tagged `## …` breadcrumb section."""
    heading = f"## {now:%Y-%m-%d %H:%M} | {facts.branch} {AUTO_BREADCRUMB_TAG}"
    listed = list(facts.changed_files[:MAX_LISTED_FILES])
    more = len(facts.changed_files) - len(listed)
    touched = ", ".join(listed) if listed else "(no tracked changes)"
    if more > 0:
        touched += f", +{more} more"
    body = (
        f"Auto-saved before compaction. {facts.files_changed} files changed "
        f"(+{facts.insertions}/-{facts.deletions}); subagents: {facts.subagents}; "
        f"main turns: {facts.main_turns}.\n"
        f"Touched: {touched}."
    )
    return Section(heading, body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_breadcrumb.py -k render -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/breadcrumb.py tests/context/test_breadcrumb.py
git commit -m "feat(memory): breadcrumb facts + entry rendering"
```

---

### Task 7: write_breadcrumb (prepend / replace-in-place)

**Files:**
- Modify: `dummyindex/context/domains/memory/breadcrumb.py`
- Test: `tests/context/test_breadcrumb.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_breadcrumb.py`:

```python
def _read_now(ctx: Path) -> str:
    return (ctx / "session-memory" / "now.md").read_text(encoding="utf-8")


def _seed_now(ctx: Path, body: str) -> None:
    mdir = ctx / "session-memory"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "now.md").write_text(body, encoding="utf-8")


def test_write_breadcrumb_prepends_to_now(tmp_path: Path):
    ctx = tmp_path / ".context"
    _seed_now(ctx, "# Now\n\n## 2026-06-07 09:00 | main\nReal handoff.\n")
    now = datetime(2026, 6, 8, 14, 5, tzinfo=timezone.utc)
    assert bc.write_breadcrumb(ctx, _facts(), now) is True
    text = _read_now(ctx)
    assert text.startswith("# Now")
    # Breadcrumb is newest (top), the real handoff is preserved below it.
    bc_idx = text.index(AUTO_BREADCRUMB_TAG)
    real_idx = text.index("Real handoff.")
    assert bc_idx < real_idx


def test_write_breadcrumb_replaces_existing_breadcrumb(tmp_path: Path):
    ctx = tmp_path / ".context"
    now = datetime(2026, 6, 8, 14, 5, tzinfo=timezone.utc)
    _seed_now(ctx, "# Now\n")
    bc.write_breadcrumb(ctx, _facts(files_changed=1), now)
    bc.write_breadcrumb(ctx, _facts(files_changed=9), now)
    text = _read_now(ctx)
    # Only one breadcrumb section; the second call updated in place.
    assert text.count(AUTO_BREADCRUMB_TAG) == 1
    assert "9 files changed" in text
    assert "1 files changed" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_breadcrumb.py -k write -v`
Expected: FAIL — `AttributeError: write_breadcrumb`.

- [ ] **Step 3: Implement**

Add to `dummyindex/context/domains/memory/breadcrumb.py`:

```python
from pathlib import Path

from .._io import write_text_atomic
from ._parse import read_text_or_empty, render, split_sections
from .enums import TIER_HEADINGS, MemoryTier
from .store import memory_dir


def write_breadcrumb(context_dir: Path, facts: BreadcrumbFacts, now: datetime) -> bool:
    """Prepend the breadcrumb to now.md, or update the existing breadcrumb
    in place if the newest entry is already one. Returns True (written)."""
    now_path = memory_dir(context_dir) / MemoryTier.NOW.value
    preamble, sections = split_sections(read_text_or_empty(now_path))
    entry = render_entry(facts, now)
    if sections and AUTO_BREADCRUMB_TAG in sections[0].heading:
        new_sections = (entry, *sections[1:])
    else:
        new_sections = (entry, *sections)
    text = render(preamble or TIER_HEADINGS[MemoryTier.NOW], new_sections)
    write_text_atomic(now_path, text)
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_breadcrumb.py -k write -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/breadcrumb.py tests/context/test_breadcrumb.py
git commit -m "feat(memory): write_breadcrumb prepend/replace into now.md"
```

---

### Task 8: gather_breadcrumb_facts (git + transcript)

**Files:**
- Modify: `dummyindex/context/domains/memory/breadcrumb.py`
- Test: `tests/context/test_breadcrumb.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_breadcrumb.py`:

```python
import subprocess


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def test_gather_facts_reads_branch_and_diff(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "x.py").write_text("a = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "x.py")
    _git(tmp_path, "commit", "-qm", "init")
    (tmp_path / "x.py").write_text("a = 1\nb = 2\n", encoding="utf-8")

    facts = bc.gather_breadcrumb_facts(tmp_path, main_transcript=None)
    assert facts.files_changed == 1
    assert facts.insertions == 1
    assert "x.py" in facts.changed_files
    assert facts.main_turns == 0  # no transcript


def test_gather_facts_survives_non_git_dir(tmp_path: Path):
    facts = bc.gather_breadcrumb_facts(tmp_path, main_transcript=None)
    assert facts.branch == "unknown"
    assert facts.files_changed == 0
    assert facts.changed_files == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_breadcrumb.py -k gather -v`
Expected: FAIL — `AttributeError: gather_breadcrumb_facts`.

- [ ] **Step 3: Implement**

Add to `dummyindex/context/domains/memory/breadcrumb.py`:

```python
import subprocess
from typing import Optional

from dummyindex.usage.transcripts import load_session


def _git_text(root: Path, *args: str) -> str:
    """Run a git command in *root*, returning stdout or "" on any failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout


def _git_branch(root: Path) -> str:
    branch = _git_text(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    return branch or "unknown"


def _git_diffstat(root: Path) -> tuple[int, int, int, tuple[str, ...]]:
    """(files_changed, insertions, deletions, changed_files) vs HEAD.

    Parses `git diff --numstat HEAD`; binary files report '-' for counts and
    are counted as changed files with zero line deltas.
    """
    out = _git_text(root, "diff", "--numstat", "HEAD")
    files: list[str] = []
    insertions = 0
    deletions = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        add_s, del_s, path = parts
        insertions += int(add_s) if add_s.isdigit() else 0
        deletions += int(del_s) if del_s.isdigit() else 0
        files.append(path)
    return len(files), insertions, deletions, tuple(files)


def gather_breadcrumb_facts(
    root: Path, main_transcript: Optional[Path]
) -> BreadcrumbFacts:
    """Collect deterministic session facts: git state + transcript counts."""
    branch = _git_branch(root)
    files_changed, insertions, deletions, changed_files = _git_diffstat(root)
    main_turns = 0
    subagents = 0
    if main_transcript is not None and main_transcript.exists():
        turns, _sub_turns, subagents = load_session(main_transcript)
        main_turns = len(turns)
    return BreadcrumbFacts(
        branch=branch,
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
        changed_files=changed_files,
        main_turns=main_turns,
        subagents=subagents,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_breadcrumb.py -v`
Expected: PASS (all breadcrumb tests).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/breadcrumb.py tests/context/test_breadcrumb.py
git commit -m "feat(memory): gather breadcrumb facts from git + transcript"
```

---

### Task 9: Export the new domain entry points

**Files:**
- Modify: `dummyindex/context/domains/memory/__init__.py`
- Test: `tests/context/test_nudge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_nudge.py`:

```python
def test_domain_exports():
    from dummyindex.context.domains import memory as m

    assert hasattr(m, "decide_nudge")
    assert hasattr(m, "write_breadcrumb")
    assert hasattr(m, "gather_breadcrumb_facts")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -k exports -v`
Expected: FAIL — `decide_nudge` not exported.

- [ ] **Step 3: Implement**

Edit `dummyindex/context/domains/memory/__init__.py` — add imports + `__all__` entries:

```python
from .breadcrumb import BreadcrumbFacts, gather_breadcrumb_facts, write_breadcrumb
from .nudge import decide_nudge
```

Add to `__all__`: `"BreadcrumbFacts"`, `"decide_nudge"`, `"gather_breadcrumb_facts"`, `"write_breadcrumb"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py -k exports -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/domains/memory/__init__.py tests/context/test_nudge.py
git commit -m "feat(memory): export nudge + breadcrumb entry points"
```

---

### Task 10: CLI dispatch for `nudge` + `breadcrumb`

**Files:**
- Modify: `dummyindex/cli/memory.py`
- Test: `tests/context/test_nudge.py`, `tests/context/test_breadcrumb.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_nudge.py`:

```python
import io

from dummyindex.cli import dispatch


def test_cli_nudge_prints_payload_when_significant(tmp_path, monkeypatch, capsys):
    transcript = tmp_path / "main.jsonl"
    transcript.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(nudge_mod, "load_session", lambda p: ((_turn(10),), (), 2))
    hook_json = f'{{"session_id": "abc", "transcript_path": "{transcript}"}}'
    monkeypatch.setattr("sys.stdin", io.StringIO(hook_json))

    rc = dispatch(["memory", "nudge"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"hookEventName": "Stop"' in out


def test_cli_nudge_silent_when_not_significant(tmp_path, monkeypatch, capsys):
    transcript = tmp_path / "main.jsonl"
    transcript.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(nudge_mod, "load_session", lambda p: ((_turn(1),), (), 0))
    hook_json = f'{{"session_id": "abc", "transcript_path": "{transcript}"}}'
    monkeypatch.setattr("sys.stdin", io.StringIO(hook_json))

    rc = dispatch(["memory", "nudge"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""
```

Append to `tests/context/test_breadcrumb.py`:

```python
import io

from dummyindex.cli import dispatch


def test_cli_breadcrumb_writes_now(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id": "abc"}'))

    rc = dispatch(["memory", "breadcrumb"])
    assert rc == 0
    text = (tmp_path / ".context" / "session-memory" / "now.md").read_text()
    assert AUTO_BREADCRUMB_TAG in text


def test_cli_breadcrumb_silent_with_remember_plugin(tmp_path, monkeypatch):
    (tmp_path / ".remember").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id": "abc"}'))

    rc = dispatch(["memory", "breadcrumb"])
    assert rc == 0
    assert not (tmp_path / ".context" / "session-memory").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py tests/context/test_breadcrumb.py -k cli -v`
Expected: FAIL — `nudge`/`breadcrumb` not handled (unknown verb / no output).

- [ ] **Step 3: Implement**

Edit `dummyindex/cli/memory.py`. Update the imports at top:

```python
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from ._common import _parse_path_and_root, _resolve_context_root


def _read_hook_stdin() -> dict:
    """Parse the hook's JSON from stdin; {} when absent/at a TTY/malformed."""
    import json

    if sys.stdin is None or sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    if not raw.strip():
        return {}
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _resolve_transcript(hook: dict, root: Path):
    """(session_id, main_transcript) from the hook JSON, with fallbacks."""
    from dummyindex.usage.transcripts import (
        default_projects_root,
        find_main_transcript,
        resolve_session_id,
    )

    session_id = hook.get("session_id") or resolve_session_id() or ""
    transcript_path = hook.get("transcript_path")
    if transcript_path:
        return session_id, Path(transcript_path)
    main = find_main_transcript(
        default_projects_root(), session_id=session_id or None, cwd=root
    )
    return session_id, main
```

Then inside `_cmd_memory`, after `root = _resolve_context_root(...)`, add the two verb branches **before** the `SESSION_START` branch:

```python
    if verb is MemoryVerb.NUDGE:
        from dummyindex.context.domains.memory import decide_nudge

        hook = _read_hook_stdin()
        session_id, main_transcript = _resolve_transcript(hook, root)
        payload = decide_nudge(
            root=root,
            main_transcript=main_transcript,
            session_id=session_id,
            now=datetime.now(timezone.utc),
        )
        if payload:
            print(payload)
        return 0  # a Stop hook must never fail the turn

    if verb is MemoryVerb.BREADCRUMB:
        from dummyindex.context.domains.memory import (
            ensure_memory_store,
            gather_breadcrumb_facts,
            remember_plugin_present,
            write_breadcrumb,
        )

        if remember_plugin_present(root):
            return 0
        hook = _read_hook_stdin()
        _session_id, main_transcript = _resolve_transcript(hook, root)
        context_dir = root / ".context"
        ensure_memory_store(context_dir)
        facts = gather_breadcrumb_facts(root, main_transcript)
        write_breadcrumb(context_dir, facts, datetime.now(timezone.utc))
        return 0  # a PreCompact hook must never fail
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py tests/context/test_breadcrumb.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/cli/memory.py tests/context/test_nudge.py tests/context/test_breadcrumb.py
git commit -m "feat(memory): CLI dispatch for nudge + breadcrumb (stdin hook JSON)"
```

---

### Task 11: Wire Stop + PreCompact hooks in `hooks.py`

**Files:**
- Modify: `dummyindex/context/hooks.py`
- Modify: `tests/context/test_hooks.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_hooks.py`:

```python
@pytest.mark.integration
def test_install_writes_stop_and_precompact_hooks(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = install(tmp_path)
    assert set(result.installed) == {
        "claude/SessionStart",
        "claude/Stop",
        "claude/PreCompact",
    }
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    stop_cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    pre_cmd = settings["hooks"]["PreCompact"][0]["hooks"][0]["command"]
    assert "memory nudge" in stop_cmd
    assert "DUMMYINDEX_AUTO_REFRESH" in stop_cmd
    assert "memory breadcrumb" in pre_cmd


@pytest.mark.integration
def test_status_true_after_install_all_three(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    s = status(tmp_path)
    assert s.claude_session_start and s.claude_stop and s.claude_pre_compact
    assert s.all_installed


@pytest.mark.integration
def test_uninstall_removes_stop_and_precompact(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    install(tmp_path)
    result = uninstall(tmp_path)
    assert "claude/Stop" in result.removed
    assert "claude/PreCompact" in result.removed
```

Then **fix the two existing assertions** that now break:

- `test_install_writes_session_start_hook` — change
  `assert result.installed == ("claude/SessionStart",)` to
  `assert "claude/SessionStart" in result.installed`.
- `test_status_false_when_absent` — change
  `assert s == HookStatus(claude_session_start=False)` to
  `assert s == HookStatus(claude_session_start=False, claude_stop=False, claude_pre_compact=False)`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_hooks.py -k "stop_and_precompact or all_three" -v`
Expected: FAIL — `KeyError: 'Stop'` / `AttributeError: claude_stop`.

- [ ] **Step 3: Implement**

In `dummyindex/context/hooks.py`:

(a) After `_SESSION_START_HOOK`, add the two hook bodies:

```python
_STOP_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"# {SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context memory nudge --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        }
    ],
}

_PRE_COMPACT_HOOK = {
    "matcher": "*",
    "hooks": [
        {
            "type": "command",
            "command": (
                f"# {SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context memory breadcrumb --root "$CLAUDE_PROJECT_DIR" '
                ">/dev/null 2>&1 || true\n"
                "exit 0\n"
            ),
        }
    ],
}

# (event_name, hook_body) installed under our sentinel, in install order.
_CLAUDE_HOOKS: tuple[tuple[str, dict], ...] = (
    ("SessionStart", _SESSION_START_HOOK),
    ("Stop", _STOP_HOOK),
    ("PreCompact", _PRE_COMPACT_HOOK),
)
```

(b) Replace the `CURRENT_CLAUDE_EVENTS` line:

```python
CURRENT_CLAUDE_EVENTS: tuple[str, ...] = tuple(name for name, _ in _CLAUDE_HOOKS)
```

(c) Replace the `HookStatus` dataclass:

```python
@dataclass(frozen=True)
class HookStatus:
    claude_session_start: bool
    claude_stop: bool = False
    claude_pre_compact: bool = False

    @property
    def all_installed(self) -> bool:
        return (
            self.claude_session_start
            and self.claude_stop
            and self.claude_pre_compact
        )
```

(d) In `install`, replace the single SessionStart install block with a loop:

```python
    # Install the current Claude hooks (SessionStart drift + Stop nudge +
    # PreCompact breadcrumb), all under our sentinel.
    for event, body in _CLAUDE_HOOKS:
        try:
            inserted = install_hook_entry(
                settings_path, event, body, sentinel=SENTINEL
            )
            (installed if inserted else skipped).append(f"claude/{event}")
        except (OSError, MalformedSettingsError) as exc:
            errors.append((f"claude/{event}", str(exc)))
```

(e) Replace `status`:

```python
def status(project_root: Path) -> HookStatus:
    project_root = project_root.resolve()
    return HookStatus(
        claude_session_start=_claude_hook_installed(project_root, "SessionStart"),
        claude_stop=_claude_hook_installed(project_root, "Stop"),
        claude_pre_compact=_claude_hook_installed(project_root, "PreCompact"),
    )
```

> `uninstall` already iterates `CURRENT_CLAUDE_EVENTS`, so adding Stop/PreCompact there is automatic.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_hooks.py -v`
Expected: PASS (new + existing, including the two fixed assertions).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/hooks.py tests/context/test_hooks.py
git commit -m "feat(hooks): install Stop nudge + PreCompact breadcrumb hooks"
```

---

### Task 12: Update the `hooks status` CLI print

**Files:**
- Modify: `dummyindex/cli/hooks.py:52`
- Test: `tests/context/test_hooks.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/context/test_hooks.py`:

```python
@pytest.mark.integration
def test_cli_hooks_status_lists_all_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    dispatch(["hooks", "install"])
    capsys.readouterr()
    assert dispatch(["hooks", "status"]) == 0
    out = capsys.readouterr().out
    assert "claude/SessionStart" in out
    assert "claude/Stop" in out
    assert "claude/PreCompact" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/context/test_hooks.py -k lists_all_three -v`
Expected: FAIL — only `claude/SessionStart` printed.

- [ ] **Step 3: Implement**

In `dummyindex/cli/hooks.py`, find the status print line:

```python
    print(f"  claude/SessionStart   {'✓' if s.claude_session_start else '✗'}")
```

Replace with:

```python
    print(f"  claude/SessionStart   {'✓' if s.claude_session_start else '✗'}")
    print(f"  claude/Stop           {'✓' if s.claude_stop else '✗'}")
    print(f"  claude/PreCompact     {'✓' if s.claude_pre_compact else '✗'}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/context/test_hooks.py -k lists_all_three -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/cli/hooks.py tests/context/test_hooks.py
git commit -m "feat(hooks): print Stop + PreCompact in hooks status"
```

---

### Task 13: Document the new verbs

**Files:**
- Modify: `dummyindex/cli/_usage.py`
- Modify: `docs/COMMANDS.md`
- Modify: `docs/guide/07-cli.md`

- [ ] **Step 1: Update `_usage.py`**

Find the `memory session-start|roll|init` help block and replace the verb list line:

```
  memory session-start|roll|init|nudge|breadcrumb [path] [--root DIR]
```

Add two lines to its description:

```
                                    nudge: Stop-hook handoff CTA (significant
                                    sessions, once per session). breadcrumb:
                                    PreCompact deterministic now.md entry.
```

- [ ] **Step 2: Update `docs/COMMANDS.md`**

In the **Session memory** table, replace the single row with:

```markdown
| `dummyindex context memory session-start\|roll\|init [path] [--root DIR]` | Cross-session memory store under `.context/session-memory/`. |
| `dummyindex context memory nudge [--root DIR]` | Stop-hook command: prints a handoff CTA (`additionalContext`) for significant, un-saved sessions. Auto-installed. |
| `dummyindex context memory breadcrumb [--root DIR]` | PreCompact-hook command: writes a deterministic breadcrumb to `now.md`. Auto-installed. |
```

- [ ] **Step 3: Update `docs/guide/07-cli.md`**

Under `## Session memory (v0.15)`, add after the existing `memory` entry:

```markdown
### `dummyindex context memory nudge [path] [--root DIR]`

- The **Stop**-hook command. Reads the hook's stdin JSON (`transcript_path`,
  `session_id`). When the session is significant (subagents used, or ≥40k
  main-thread output tokens) and not already nudged / not already saved /
  no `remember` plugin, prints a `hookSpecificOutput.additionalContext`
  payload that prompts the agent to offer a handoff CTA. Otherwise silent.
  Never auto-saves; never fails the turn.

### `dummyindex context memory breadcrumb [path] [--root DIR]`

- The **PreCompact**-hook command. Writes a deterministic, tagged breadcrumb
  entry (branch, `git diff --stat`, file list, subagent + turn counts) to the
  top of `now.md` so a session is never lost to compaction. Silent when the
  `remember` plugin is present. Never stamps the commit anchor.
```

- [ ] **Step 4: Verify docs build / no broken refs**

Run: `.venv/bin/python -m dummyindex context --help` (confirm it still renders).
Expected: help text shows the updated `memory … nudge|breadcrumb` line.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/cli/_usage.py docs/COMMANDS.md docs/guide/07-cli.md
git commit -m "docs: document memory nudge + breadcrumb verbs"
```

---

### Task 14: Full verification gate

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (no regressions in `test_hooks.py`, `test_memory*.py`).

- [ ] **Step 2: Coverage for the new modules**

Run: `.venv/bin/python -m pytest tests/context/test_nudge.py tests/context/test_breadcrumb.py --cov=dummyindex.context.domains.memory.nudge --cov=dummyindex.context.domains.memory.breadcrumb --cov-report=term-missing`
Expected: ≥80% on both new modules; add tests for any uncovered branch.

- [ ] **Step 3: Lint + type-check**

Run: `.venv/bin/ruff check dummyindex/ tests/ && .venv/bin/mypy dummyindex/context/domains/memory/ dummyindex/cli/memory.py dummyindex/context/hooks.py`
Expected: clean.

- [ ] **Step 4: python-reviewer pass**

Dispatch the `python-reviewer` agent over the changed files (per repo convention after touching `dummyindex/`/`tests/`). Address any CRITICAL/HIGH findings.

- [ ] **Step 5: Manual smoke (no hooks installed in this repo — uses a tmp repo)**

Run:
```bash
tmp=$(mktemp -d); git -C "$tmp" init -q
echo '{"session_id":"smoke","transcript_path":"/nonexistent.jsonl"}' | .venv/bin/python -m dummyindex context memory nudge --root "$tmp"; echo "nudge rc=$?"
echo '{"session_id":"smoke"}' | .venv/bin/python -m dummyindex context memory breadcrumb --root "$tmp"
cat "$tmp/.context/session-memory/now.md"
```
Expected: `nudge rc=0` with no stdout (transcript absent → not significant); breadcrumb writes a `(auto-breadcrumb)` entry to `now.md`.

- [ ] **Step 6: Final commit (if reviewer changes were made)**

```bash
git add -A && git commit -m "test(memory): coverage + reviewer fixes for handoff nudge"
```

---

## Self-Review

**Spec coverage:**
- §3 detect→breadcrumb+CTA → Tasks 2–10 ✓
- §4 components/file layout → all tasks map to the listed files ✓
- §5 significance (subagents / ≥40k tokens, session-scoped) → Task 2 ✓
- §6 suppression + cheap-checks-first ordering → Tasks 3, 5 (`decide_nudge` orders remember→marker→freshness→parse) ✓
- §7 breadcrumb format + in-place update → Tasks 6, 7 ✓
- §8 `additionalContext` contract → Task 5 ✓
- §9 hook wiring (Stop + PreCompact, HookStatus, install loop, stdout-through) → Tasks 11, 12 ✓
- §10 remember-plugin deferral → Tasks 5 (nudge), 10 (breadcrumb CLI) ✓
- §11 test plan → Tasks 2–12 + 14 ✓
- §12 out-of-scope respected (no PreCompact systemMessage, no knobs, session-scoped) ✓
- Commit-anchor rule (no hook stamps `meta.indexed_commit`): nudge/breadcrumb only touch `now.md` + `nudge-state.json` ✓

**Placeholder scan:** none — every code step has complete code; every command has expected output.

**Type consistency:** `BreadcrumbFacts` fields identical across Tasks 6/7/8; `decide_nudge(root, main_transcript, session_id, now)` signature identical in Tasks 5 and 10; `load_session` patched consistently; `HookStatus(claude_session_start, claude_stop, claude_pre_compact)` consistent across Task 11 and the fixed existing test; `AUTO_BREADCRUMB_TAG` defined in `enums.py` (Task 1) and imported by both `nudge.py` and `breadcrumb.py`.
