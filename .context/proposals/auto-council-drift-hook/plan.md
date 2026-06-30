# Always-on Drift-Triggered Auto-Council — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `.context/` is stale and a session did real work, a `Stop` hook blocks the session's exit *once* with a scoped directive telling the live agent to run the council/reconcile — installable globally (`~/.claude/settings.json`) with per-repo override precedence.

**Architecture:** A new deterministic decision module (`reconcile_gate.py`) reads the Stop-hook stdin, computes drift via the existing `compute_drift`, gates on a substantive-session signal, and emits a `{"decision":"block","reason":…}` JSON — at most once per stop (guarded by `stop_hook_active`). The hook never writes or stamps `.context/`; the agent runs the council and `reconcile-stamp`. The Stop gate is added as a *second command inside the existing Stop hook entry*. Global install reuses the existing `claude_settings` machinery against `~/.claude/settings.json`; global hook bodies carry a `defer-check` guard so a repo with its own `--local` dummyindex hooks (the override) suppresses the global ones.

**Tech Stack:** Python 3 (stdlib + existing `dummyindex.context` modules), pytest. Frozen dataclasses, enum constants, thin CLI wrappers over pure decision functions — per `CONVENTIONS.md`.

---

## Reference: existing code this plan builds on

- `dummyindex/context/drift.py` — `compute_drift(project_root) -> DriftReport`; `DriftReport.has_drift`, `.by_feature() -> dict[str, tuple[str,...]]`, `.unassigned_new_files`, `.awaiting_enrichment`.
- `dummyindex/context/domains/memory/transcript.py` — `read_session_signal(path) -> SessionSignal(output_tokens, subagent_file_count, main_turns)`.
- `dummyindex/context/domains/memory/nudge.py` — `is_significant(output_tokens, subagent_file_count) -> bool`.
- `dummyindex/context/hooks.py` — `_SESSION_START_HOOK`, `_STOP_HOOK`, `_PRE_COMPACT_HOOK`, `SENTINEL`, `install/uninstall/status`, `HookResult`, `HookStatus`, `_CLAUDE_HOOKS`, `CURRENT_CLAUDE_EVENTS`, `_claude_hook_installed`.
- `dummyindex/context/claude_settings.py` — `install_hook_entry(settings_path, event, body, *, sentinel)`, `remove_hook_entries(settings_path, *, sentinel)`, `load_settings`, `write_settings`, `MalformedSettingsError`.
- `dummyindex/cli/hooks.py` — `run(args)` for `context hooks {install|uninstall|status}`.
- `dummyindex/cli/memory.py` — `_read_hook_stdin()`, `_resolve_transcript(hook, root)`; the `nudge` verb shows the Stop-hook CLI pattern (read stdin, decide, print, **always return 0**).
- `dummyindex/cli/__init__.py` — `_HANDLERS` table; `dummyindex/context/enums.py:ContextSubcommand`.

## File structure (created / modified)

- **Create** `dummyindex/context/reconcile_gate.py` — pure decision logic (`auto_council_enabled`, `decide_block`, `render_block`).
- **Create** `dummyindex/cli/reconcile_gate.py` — thin CLI wrapper for `context reconcile-gate`.
- **Modify** `dummyindex/context/enums.py` — add `ContextSubcommand.RECONCILE_GATE`.
- **Modify** `dummyindex/cli/__init__.py` — import + register the handler.
- **Modify** `dummyindex/context/hooks.py` — add gate command to the Stop entry; scope-aware `install/uninstall/status`; global guard wrapping; `local_install_present`.
- **Modify** `dummyindex/cli/hooks.py` — `--global`/`--local` flags + `defer-check` verb.
- **Modify** `dummyindex/cli/help.py` and `docs/COMMANDS.md` — document the verb + flags.
- **Tests** under `tests/` mirroring the module tree.

---

## Task 0: Empirically verify the Stop `decision: block` contract

**Files:** none (manual verification; record results into the spec's §2 table).

- [ ] **Step 1: Wire a throwaway Stop block hook**

Add temporarily to this repo's `.claude/settings.json` under `hooks.Stop` (a NEW entry, no sentinel collision):

```json
{ "matcher": "*", "hooks": [ { "type": "command", "command": "cat > /tmp/stopdump.json; echo '{\"decision\":\"block\",\"reason\":\"TEST-BLOCK: confirm this reaches the model and grants a turn\"}'" } ] }
```

- [ ] **Step 2: Trigger a stop and observe**

End a turn. Confirm: (a) the session is blocked from stopping, (b) `reason` reaches the model (it gets a turn), (c) `/tmp/stopdump.json` contains `stop_hook_active` (note its value on the *second* block), `session_id`, `transcript_path`.

- [ ] **Step 3: Confirm block-once via `stop_hook_active`**

Confirm that on the re-entrant stop the input JSON has `"stop_hook_active": true`. This is the field `decide_block` keys on to avoid trapping the session.

- [ ] **Step 4: Remove the throwaway hook**

Delete the temporary entry from `.claude/settings.json`. Record findings in `docs/specs/2026-06-11-auto-council-drift-hook-design.md` §2 (flip the "to be verified" rows to verified, or adjust the design if the contract differs).

- [ ] **Step 5: Commit the spec update**

```bash
git add docs/specs/2026-06-11-auto-council-drift-hook-design.md
git commit -m "docs: record verified Stop block-hook contract for auto-council gate"
```

---

## Task 1: `auto_council_enabled` opt-out reader

**Files:**
- Create: `dummyindex/context/reconcile_gate.py`
- Test: `tests/context/test_reconcile_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/context/test_reconcile_gate.py
import json
from pathlib import Path

from dummyindex.context.reconcile_gate import auto_council_enabled


def _write(p: Path, payload: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


def test_enabled_by_default_when_no_config(tmp_path: Path) -> None:
    assert auto_council_enabled(tmp_path) is True


def test_enabled_when_config_lacks_key(tmp_path: Path) -> None:
    _write(tmp_path / ".context" / "config.json", {"other": 1})
    assert auto_council_enabled(tmp_path) is True


def test_disabled_when_auto_council_false(tmp_path: Path) -> None:
    _write(tmp_path / ".context" / "config.json", {"auto_council": False})
    assert auto_council_enabled(tmp_path) is False


def test_enabled_when_config_malformed(tmp_path: Path) -> None:
    cfg = tmp_path / ".context" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("{ not json", encoding="utf-8")
    assert auto_council_enabled(tmp_path) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/context/test_reconcile_gate.py -q`
Expected: FAIL — `ModuleNotFoundError: dummyindex.context.reconcile_gate`.

- [ ] **Step 3: Write minimal implementation**

```python
# dummyindex/context/reconcile_gate.py
"""Stop-hook reconcile gate: block session exit once when `.context/` is stale.

Deterministic decision logic. The hook NEVER writes or stamps `.context/` —
it computes drift and, when a substantive session leaves the index stale,
emits a Stop `decision: block` whose `reason` directs the live agent to run
the council/reconcile and `reconcile-stamp`. Mirrors `memory/nudge.py`:
the CLI wrapper reads stdin and prints; this module only decides.
"""
from __future__ import annotations

import json
from pathlib import Path


def auto_council_enabled(root: Path) -> bool:
    """Opt-out check: False only when `.context/config.json` sets
    ``"auto_council": false``. Absent file / key / malformed JSON → enabled
    (opt-out, not opt-in)."""
    cfg = root / ".context" / "config.json"
    if not cfg.is_file():
        return True
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return True
    if not isinstance(data, dict):
        return True
    return data.get("auto_council") is not False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/context/test_reconcile_gate.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/reconcile_gate.py tests/context/test_reconcile_gate.py
git commit -m "feat(context): auto_council opt-out reader for reconcile gate"
```

---

## Task 2: `render_block` directive

**Files:**
- Modify: `dummyindex/context/reconcile_gate.py`
- Test: `tests/context/test_reconcile_gate.py`

- [ ] **Step 1: Write the failing test**

```python
from dummyindex.context.drift import DriftReport, DriftRow
from dummyindex.context.reconcile_gate import render_block


def test_render_block_lists_drifted_features_and_stamp() -> None:
    report = DriftReport(
        rows=(DriftRow(rel_path="a.py", feature_id="auth"),
              DriftRow(rel_path="b.py", feature_id="billing")),
        unassigned_new_files=("new/x.py",),
        awaiting_enrichment=("search",),
    )
    payload = render_block(report)
    obj = json.loads(payload)
    assert obj["decision"] == "block"
    reason = obj["reason"]
    assert "auth" in reason and "billing" in reason       # drifted features
    assert "new/x.py" in reason                            # unplaced files
    assert "search" in reason                              # awaiting enrichment
    assert "reconcile-stamp" in reason                     # agent stamps, not the hook
    assert "auto_council" in reason                        # opt-out hint
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/context/test_reconcile_gate.py::test_render_block_lists_drifted_features_and_stamp -q`
Expected: FAIL — `ImportError: cannot import name 'render_block'`.

- [ ] **Step 3: Write minimal implementation** (append to `reconcile_gate.py`)

```python
from dummyindex.context.drift import DriftReport


def render_block(report: DriftReport) -> str:
    """Build the Stop `decision: block` JSON. `reason` is the agent-facing,
    scoped reconcile directive. The hook stamps nothing — the agent runs the
    council and `reconcile-stamp`."""
    features = sorted(report.by_feature().keys())
    parts = [
        "dummyindex reconcile gate: `.context/` is stale after a substantial "
        "session. Before this session ends, reconcile the drifted parts so the "
        "index stays a reliable answer to \"how does this code work?\". Run the "
        "reconcile procedure (council/65-reconcile.md): for each drifted feature "
        "below, re-run its council enrichment (`/dummyindex --recouncil <feature>`); "
        "place any new files; then `dummyindex context reconcile-stamp`. Do NOT "
        "skip silently — this is the per-session reconcile gate.",
    ]
    if features:
        parts.append("Drifted features: " + ", ".join(features) + ".")
    if report.unassigned_new_files:
        parts.append("New unplaced files: " + ", ".join(report.unassigned_new_files) + ".")
    if report.awaiting_enrichment:
        parts.append("Awaiting enrichment: " + ", ".join(report.awaiting_enrichment) + ".")
    parts.append('To disable for this repo: set "auto_council": false in .context/config.json.')
    return json.dumps({"decision": "block", "reason": " ".join(parts)})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/context/test_reconcile_gate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/reconcile_gate.py tests/context/test_reconcile_gate.py
git commit -m "feat(context): scoped reconcile directive for the block gate"
```

---

## Task 3: `decide_block` — the gated decision

**Files:**
- Modify: `dummyindex/context/reconcile_gate.py`
- Test: `tests/context/test_reconcile_gate.py`

Decision order (bail to `None` = allow stop): `stop_hook_active` → opt-out → drift → substantive-session. `None` means "don't block."

- [ ] **Step 1: Write the failing test**

```python
import pytest
from dummyindex.context.domains.memory.transcript import SessionSignal
from dummyindex.context import reconcile_gate as rg


class _Stub:
    """Patchable seams so decide_block stays unit-testable without a repo."""


@pytest.fixture
def patched(monkeypatch, tmp_path):
    state = {
        "enabled": True,
        "report": DriftReport(rows=(DriftRow(rel_path="a.py", feature_id="auth"),)),
        "signal": SessionSignal(output_tokens=50_000, subagent_file_count=0, main_turns=3),
    }
    monkeypatch.setattr(rg, "auto_council_enabled", lambda root: state["enabled"])
    monkeypatch.setattr(rg, "compute_drift", lambda root: state["report"])
    monkeypatch.setattr(rg, "read_session_signal", lambda p: state["signal"])
    return state, tmp_path


def test_blocks_when_drift_substantive_not_active(patched):
    state, root = patched
    transcript = root / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    out = rg.decide_block(root=root, main_transcript=transcript, stop_hook_active=False)
    assert out is not None
    assert json.loads(out)["decision"] == "block"


def test_silent_when_stop_hook_active(patched):
    state, root = patched
    transcript = root / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    assert rg.decide_block(root=root, main_transcript=transcript, stop_hook_active=True) is None


def test_silent_when_opted_out(patched):
    state, root = patched
    state["enabled"] = False
    transcript = root / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    assert rg.decide_block(root=root, main_transcript=transcript, stop_hook_active=False) is None


def test_silent_when_no_drift(patched):
    state, root = patched
    state["report"] = DriftReport(rows=())
    transcript = root / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    assert rg.decide_block(root=root, main_transcript=transcript, stop_hook_active=False) is None


def test_silent_when_not_substantive(patched):
    state, root = patched
    state["signal"] = SessionSignal(output_tokens=10, subagent_file_count=0, main_turns=1)
    transcript = root / "t.jsonl"
    transcript.write_text("{}", encoding="utf-8")
    assert rg.decide_block(root=root, main_transcript=transcript, stop_hook_active=False) is None


def test_silent_when_no_transcript(patched):
    state, root = patched
    assert rg.decide_block(root=root, main_transcript=None, stop_hook_active=False) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/context/test_reconcile_gate.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'decide_block'`.

- [ ] **Step 3: Write minimal implementation** (append imports + function)

```python
# add to the import block at the top of reconcile_gate.py:
from typing import Optional

from dummyindex.context.drift import DriftReport, compute_drift
from dummyindex.context.domains.memory.nudge import is_significant
from dummyindex.context.domains.memory.transcript import read_session_signal


def decide_block(
    *,
    root: Path,
    main_transcript: Optional[Path],
    stop_hook_active: bool,
) -> Optional[str]:
    """Return the Stop block JSON to print, or None to allow the stop.

    Cheap gates first. Blocks at most once per stop (``stop_hook_active``),
    only when the index is stale AND the session did real work.
    """
    if stop_hook_active:                         # block-once: never trap the session
        return None
    if not auto_council_enabled(root):           # per-repo opt-out
        return None
    report = compute_drift(root)
    if not report.has_drift:                     # nothing stale → allow stop
        return None
    if main_transcript is None or not main_transcript.exists():
        return None                              # no proof of substantive work
    signal = read_session_signal(main_transcript)
    if not is_significant(signal.output_tokens, signal.subagent_file_count):
        return None                              # trivial session → don't trap
    return render_block(report)
```

Note: `render_block`'s own `from dummyindex.context.drift import DriftReport` (Task 2) is now redundant with this import block — keep a single import at the top of the module and delete the inline one.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/context/test_reconcile_gate.py -q`
Expected: PASS (all gate cases).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/reconcile_gate.py tests/context/test_reconcile_gate.py
git commit -m "feat(context): decide_block — drift+substantive gated, block-once"
```

---

## Task 4: CLI verb `context reconcile-gate`

**Files:**
- Create: `dummyindex/cli/reconcile_gate.py`
- Modify: `dummyindex/context/enums.py` (add enum member)
- Modify: `dummyindex/cli/__init__.py` (import + register)
- Test: `tests/cli/test_reconcile_gate_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_reconcile_gate_cli.py
import io
import json
from pathlib import Path

import pytest

from dummyindex.cli import reconcile_gate as cli
from dummyindex.context import reconcile_gate as rg


def test_prints_block_payload(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "_read_hook_stdin", lambda: {"stop_hook_active": False, "session_id": "s"})
    monkeypatch.setattr(cli, "_resolve_transcript", lambda hook, root: ("s", tmp_path / "t.jsonl"))
    monkeypatch.setattr(rg, "decide_block", lambda **kw: json.dumps({"decision": "block", "reason": "x"}))
    rc = cli.run(["--root", str(tmp_path)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out.strip())["decision"] == "block"


def test_returns_zero_and_silent_when_none(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "_read_hook_stdin", lambda: {"stop_hook_active": True})
    monkeypatch.setattr(cli, "_resolve_transcript", lambda hook, root: ("", None))
    monkeypatch.setattr(rg, "decide_block", lambda **kw: None)
    rc = cli.run(["--root", str(tmp_path)])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_reconcile_gate_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: dummyindex.cli.reconcile_gate`.

- [ ] **Step 3: Write minimal implementation**

`dummyindex/cli/reconcile_gate.py` (mirror `cli/memory.py`'s stdin/transcript helpers — import them to stay DRY):

```python
"""`dummyindex context reconcile-gate` — Stop-hook gate that blocks session
exit once when `.context/` is stale after a substantial session.

Wire-only: read the Stop-hook JSON from stdin, decide, print the block
payload (if any), and ALWAYS return 0 — a Stop hook must never fail the turn.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .common import parse_path_and_root, resolve_context_root
from .memory import _read_hook_stdin, _resolve_transcript


def run(args: list[str]) -> int:
    from dummyindex.context.reconcile_gate import decide_block

    scope, explicit_root, leftover = parse_path_and_root(args)
    if leftover:
        print(f"error: unknown argument(s): {leftover}", file=sys.stderr)
        return 2
    root = resolve_context_root(scope, explicit_root=explicit_root)

    hook = _read_hook_stdin()
    session_id, main_transcript = _resolve_transcript(hook, root)
    stop_hook_active = bool(hook.get("stop_hook_active"))
    payload = decide_block(
        root=root,
        main_transcript=main_transcript,
        stop_hook_active=stop_hook_active,
    )
    if payload:
        print(payload)
    return 0  # a Stop hook must never fail the turn
```

In `dummyindex/context/enums.py`, add to `ContextSubcommand` (after `PLAN_UPDATE`):

```python
    RECONCILE_GATE = "reconcile-gate"
```

In `dummyindex/cli/__init__.py`: add `reconcile_gate` to the `from . import (...)` block (keep alphabetical-ish ordering near `reconcile`), and add to `_HANDLERS`:

```python
    ContextSubcommand.RECONCILE_GATE: reconcile_gate.run,
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/cli/test_reconcile_gate_cli.py -q && python -m dummyindex context reconcile-gate --root . </dev/null`
Expected: tests PASS; the CLI call prints nothing and exits 0 (no `.context/features/` in this repo → no drift).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/cli/reconcile_gate.py dummyindex/context/enums.py dummyindex/cli/__init__.py tests/cli/test_reconcile_gate_cli.py
git commit -m "feat(cli): context reconcile-gate verb (Stop-hook block gate)"
```

---

## Task 5: Add the gate command to the Stop hook entry (local scope)

**Files:**
- Modify: `dummyindex/context/hooks.py`
- Test: `tests/context/test_hooks.py` (existing) — add cases

The Stop entry currently holds one command (`memory nudge`). Add the gate as a **second command in the same entry's `hooks` list** so `install_hook_entry`'s by-sentinel, per-entry dedup refreshes it in place.

- [ ] **Step 1: Write the failing test**

```python
# tests/context/test_hooks.py (add)
import json
from pathlib import Path
from dummyindex.context import hooks as H


def test_stop_entry_has_nudge_and_gate(tmp_path: Path):
    H.install(tmp_path)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    stop = settings["hooks"]["Stop"]
    assert len(stop) == 1  # single entry...
    cmds = [h["command"] for h in stop[0]["hooks"]]
    assert any("memory nudge" in c for c in cmds)
    assert any("reconcile-gate" in c for c in cmds)  # ...two commands


def test_install_is_idempotent_with_gate(tmp_path: Path):
    H.install(tmp_path)
    H.install(tmp_path)
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["Stop"]) == 1
    assert len(settings["hooks"]["Stop"][0]["hooks"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/context/test_hooks.py -q -k "gate or idempotent_with_gate"`
Expected: FAIL — only `memory nudge` present; no `reconcile-gate` command.

- [ ] **Step 3: Write minimal implementation**

In `dummyindex/context/hooks.py`, extend `_STOP_HOOK` to two commands:

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
        },
        {
            "type": "command",
            "command": (
                f"# {SENTINEL}\n"
                "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
                'dummyindex context reconcile-gate --root "$CLAUDE_PROJECT_DIR" '
                "2>/dev/null || true\n"
                "exit 0\n"
            ),
        },
    ],
}
```

Note: stderr is redirected (`2>/dev/null`) but **stdout is not** — the gate's block JSON must reach Claude Code on stdout.

- [ ] **Step 4: Run tests**

Run: `pytest tests/context/test_hooks.py -q`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/hooks.py tests/context/test_hooks.py
git commit -m "feat(hooks): add reconcile-gate command to the Stop hook entry"
```

---

## Task 6: Scope-aware install/uninstall/status + global guard + `local_install_present`

**Files:**
- Modify: `dummyindex/context/hooks.py`
- Test: `tests/context/test_hooks.py`

Add a `scope` parameter (`"local"` default | `"global"`). Local writes `project_root/.claude/settings.json` (unchanged behaviour, incl. legacy git/PostToolUse scrub). Global writes `Path.home()/.claude/settings.json`, skips the git scrub, and wraps every hook command with a `defer-check` guard so a repo with its own local install suppresses the global one. Add `local_install_present(project_root) -> bool` powering the `defer-check` CLI verb.

- [ ] **Step 1: Write the failing test**

```python
# tests/context/test_hooks.py (add)
def test_global_install_targets_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    H.install(tmp_path, scope="global")
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    # global bodies carry the defer-check guard
    cmds = [h["command"] for e in settings["hooks"]["SessionStart"] for h in e["hooks"]]
    assert any("hooks defer-check" in c for c in cmds)


def test_global_bodies_guarded_local_not(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    H.install(tmp_path, scope="local")
    local = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    lcmds = [h["command"] for e in local["hooks"]["Stop"] for h in e["hooks"]]
    assert not any("defer-check" in c for c in lcmds)


def test_local_install_present_detects_sentinel(tmp_path):
    assert H.local_install_present(tmp_path) is False
    H.install(tmp_path, scope="local")
    assert H.local_install_present(tmp_path) is True


def test_global_uninstall_scrubs_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    H.install(tmp_path, scope="global")
    H.uninstall(tmp_path, scope="global")
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert "hooks" not in settings or not settings["hooks"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/context/test_hooks.py -q -k "global or local_install_present"`
Expected: FAIL — `install()` takes no `scope`; `local_install_present` missing.

- [ ] **Step 3: Write minimal implementation**

In `dummyindex/context/hooks.py`:

```python
# Guard prefixed onto every GLOBAL hook command so a repo with its own
# (--local) dummyindex hooks — the per-repo override — suppresses the global
# ones. defer-check exits 0 (success) when the project has a local install,
# so `&& exit 0` short-circuits before the real command runs.
_GLOBAL_GUARD = (
    'dummyindex context hooks defer-check --root "$CLAUDE_PROJECT_DIR" '
    "2>/dev/null && exit 0\n"
)


def _settings_path_for(project_root: Path, scope: str) -> Path:
    if scope == "global":
        return Path.home() / ".claude" / "settings.json"
    return project_root / ".claude" / "settings.json"


def _guard_body(body: dict) -> dict:
    """Return a copy of a hook body with the defer-check guard inserted into
    each command, right after the `command -v dummyindex` self-gate line."""
    out = {**body, "hooks": []}
    for h in body["hooks"]:
        cmd = h["command"]
        marker = "command -v dummyindex >/dev/null 2>&1 || exit 0\n"
        if marker in cmd:
            cmd = cmd.replace(marker, marker + _GLOBAL_GUARD, 1)
        out["hooks"].append({**h, "command": cmd})
    return out


def local_install_present(project_root: Path) -> bool:
    """True when the repo has at least one of our hooks in its own
    `.claude/settings.json` (the per-repo override)."""
    return any(
        _claude_hook_installed(project_root, event)
        for event in CURRENT_CLAUDE_EVENTS
    )
```

Then thread `scope: str = "local"` through `install`, `uninstall`, `status`:

- `install(project_root, scope="local")`: compute `settings_path = _settings_path_for(project_root, scope)`. Run the git/PostToolUse legacy scrub **only when `scope == "local"`**. Select bodies: `bodies = _CLAUDE_HOOKS` for local; for global, map each through `_guard_body`: `[(ev, _guard_body(b)) for ev, b in _CLAUDE_HOOKS]`. Install into `settings_path`.
- `uninstall(project_root, scope="local")`: target `settings_path = _settings_path_for(...)`; run git scrub only for local; scrub via the existing per-event sentinel logic (already operates on a `settings_path`).
- `status(project_root, scope="local")`: read `_settings_path_for(...)` instead of the hardcoded project path. `_claude_hook_installed` gains an optional `scope`/`settings_path` — simplest: add `def _claude_hook_installed(project_root, event, *, settings_path=None)` defaulting to the local project path, and pass the resolved path from `status`. `local_install_present` keeps using the project default.

Keep all existing local-scope behaviour byte-identical when `scope="local"` (the default), so current tests and installed repos are unaffected.

- [ ] **Step 4: Run tests**

Run: `pytest tests/context/test_hooks.py -q`
Expected: PASS (new global/guard cases + all existing local cases unchanged).

- [ ] **Step 5: Commit**

```bash
git add dummyindex/context/hooks.py tests/context/test_hooks.py
git commit -m "feat(hooks): scope-aware install + global defer-check guard"
```

---

## Task 7: CLI `--global`/`--local` flags + `defer-check` verb

**Files:**
- Modify: `dummyindex/cli/hooks.py`
- Test: `tests/cli/test_hooks_cli.py` (create if absent)

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_hooks_cli.py
from pathlib import Path
from dummyindex.cli import hooks as cli


def test_defer_check_exit_codes(tmp_path, monkeypatch):
    # no local install -> exit 1 (do not defer)
    assert cli.run(["defer-check", "--root", str(tmp_path)]) == 1
    from dummyindex.context import hooks as H
    H.install(tmp_path, scope="local")
    # local install present -> exit 0 (defer)
    assert cli.run(["defer-check", "--root", str(tmp_path)]) == 0


def test_install_global_flag_targets_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    rc = cli.run(["install", "--global"])
    assert rc == 0
    assert (home / ".claude" / "settings.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/cli/test_hooks_cli.py -q`
Expected: FAIL — unknown verb `defer-check`; `--global` rejected as leftover.

- [ ] **Step 3: Write minimal implementation**

In `dummyindex/cli/hooks.py`:
- Accept `defer-check` in the verb set. Handle it first: parse `--root`, then `return 0 if local_install_present(project_root) else 1`.
- For `install`/`uninstall`/`status`, pop a `--global` / `--local` flag from `rest` **before** `parse_path_and_root` (so it isn't flagged as leftover), default `scope="local"`. Pass `scope=` to the underlying functions and to the status read.

```python
def run(args: list[str]) -> int:
    from dummyindex.context.hooks import (
        install as hooks_install,
        status as hooks_status,
        uninstall as hooks_uninstall,
        local_install_present,
    )
    if not args:
        print("error: usage: dummyindex context hooks install|uninstall|status|defer-check [--global]", file=sys.stderr)
        return 2
    verb, rest = args[0], args[1:]
    if verb not in ("install", "uninstall", "status", "defer-check"):
        print(f"error: unknown hooks verb {verb!r}", file=sys.stderr)
        return 2

    scope = "local"
    pruned: list[str] = []
    for a in rest:
        if a == "--global":
            scope = "global"
        elif a == "--local":
            scope = "local"
        else:
            pruned.append(a)
    cfg_scope, explicit_root, leftover = parse_path_and_root(pruned)
    if leftover:
        print(f"error: unknown argument(s): {leftover}", file=sys.stderr)
        return 2
    project_root = resolve_context_root(cfg_scope, explicit_root=explicit_root)

    if verb == "defer-check":
        return 0 if local_install_present(project_root) else 1
    if verb == "install":
        result = hooks_install(project_root, scope=scope)
        ...  # unchanged printing
        return 0 if not result.errors else 1
    if verb == "uninstall":
        result = hooks_uninstall(project_root, scope=scope)
        ...
        return 0 if not result.errors else 1
    s = hooks_status(project_root, scope=scope)
    print(f"hooks status @ {project_root} (scope={scope})")
    ...  # unchanged lines
    return 0 if s.all_installed else 1
```

(`defer-check` prints nothing — it is a pure exit-code probe for the shell guard.)

- [ ] **Step 4: Run tests**

Run: `pytest tests/cli/test_hooks_cli.py tests/context/test_hooks.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dummyindex/cli/hooks.py tests/cli/test_hooks_cli.py
git commit -m "feat(cli): hooks --global/--local + defer-check probe"
```

---

## Task 8: Integration test — end-to-end gate over a drifted fixture

**Files:**
- Test: `tests/integration/test_reconcile_gate_e2e.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_reconcile_gate_e2e.py
import json
import os
import subprocess
import sys
from pathlib import Path


def _make_drifted_repo(root: Path) -> None:
    """A .context/features/<id>/ whose feature.json maps a source file that is
    newer than the (absent) feature docs → drift via mtime."""
    feat = root / ".context" / "features" / "auth"
    feat.mkdir(parents=True)
    (feat / "feature.json").write_text(json.dumps({"feature_id": "auth", "files": ["auth.py"]}), encoding="utf-8")
    (root / "auth.py").write_text("x = 1\n", encoding="utf-8")  # newer than (no) docs


def test_cli_emits_block_for_drifted_repo(tmp_path, monkeypatch):
    _make_drifted_repo(tmp_path)
    # Substantial session: fake a transcript with enough output tokens.
    proj = tmp_path / ".transcripts"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(proj))
    sid = "sess1"
    tdir = proj / "projects" / "slug"
    tdir.mkdir(parents=True)
    transcript = tdir / f"{sid}.jsonl"
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"usage": {"output_tokens": 100000}}}) + "\n",
        encoding="utf-8",
    )
    stdin = json.dumps({"stop_hook_active": False, "session_id": sid, "transcript_path": str(transcript)})
    out = subprocess.run(
        [sys.executable, "-m", "dummyindex", "context", "reconcile-gate", "--root", str(tmp_path)],
        input=stdin, capture_output=True, text=True,
    )
    assert out.returncode == 0
    payload = json.loads(out.stdout.strip())
    assert payload["decision"] == "block"
    assert "auth" in payload["reason"]


def test_cli_silent_on_reentry(tmp_path):
    _make_drifted_repo(tmp_path)
    stdin = json.dumps({"stop_hook_active": True})
    out = subprocess.run(
        [sys.executable, "-m", "dummyindex", "context", "reconcile-gate", "--root", str(tmp_path)],
        input=stdin, capture_output=True, text=True,
    )
    assert out.returncode == 0
    assert out.stdout.strip() == ""
```

- [ ] **Step 2: Run test to verify it fails (then passes once wired)**

Run: `pytest tests/integration/test_reconcile_gate_e2e.py -q`
Expected: PASS if Tasks 1–4 are complete (this validates the whole chain). If it fails on transcript discovery, confirm the fixture matches `transcript.py`'s `_projects_root()` / slug logic; the test pins `transcript_path` explicitly so discovery is bypassed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_reconcile_gate_e2e.py
git commit -m "test: e2e reconcile-gate block over a drifted fixture repo"
```

---

## Task 9: Docs, help text, CHANGELOG, version bump

**Files:**
- Modify: `dummyindex/cli/help.py` (USAGE)
- Modify: `docs/COMMANDS.md`
- Modify: `CHANGELOG.md`, `pyproject.toml`

- [ ] **Step 1: Update USAGE in `dummyindex/cli/help.py`**

Add under the context subcommand list:

```
  reconcile-gate [--root DIR]       Stop-hook gate: block exit once when .context/ is stale.
  hooks install|uninstall|status [--global]   Manage session hooks (global = ~/.claude).
  hooks defer-check [--root DIR]    Exit 0 when the repo has its own dummyindex hooks.
```

- [ ] **Step 2: Document in `docs/COMMANDS.md`**

Add a subsection describing the reconcile gate (drift-only, scoped, block-once, agent runs the council/stamp — the hook never stamps), the `--global` install, per-repo override via `--local`, and the `.context/config.json` → `"auto_council": false` opt-out.

- [ ] **Step 3: CHANGELOG + version**

Add a CHANGELOG entry under a new version (bump the minor in `pyproject.toml`, matching the repo's release cadence — current is `0.22.0`, so `0.23.0`). Summarize: always-on drift-triggered auto-council Stop gate; `--global` hook install with per-repo override; opt-out.

- [ ] **Step 4: Run the full suite + linters**

Run: `pytest -q && ruff check dummyindex && mypy dummyindex`
Expected: all green; coverage ≥ 80% on the new module (it is small and fully branch-tested).

- [ ] **Step 5: Reinstall the editable CLI so the live `dummyindex` reflects changes**

Per the repo's known gotcha (the `dummyindex` CLI is a uv-tool copy; repo edits don't reach it until reinstalled):

Run: `uv tool install --force --editable .`
Then verify: `dummyindex context reconcile-gate --root . </dev/null; echo "exit=$?"`
Expected: prints nothing, `exit=0`.

- [ ] **Step 6: Commit**

```bash
git add dummyindex/cli/help.py docs/COMMANDS.md CHANGELOG.md pyproject.toml
git commit -m "docs: document reconcile-gate, --global hooks, auto_council opt-out; bump 0.23.0"
```

---

## Self-review notes (spec coverage)

- Spec §3.1 reconcile-gate → Tasks 1–4. §3.2 Stop entry → Task 5. §3.3 global install → Tasks 6–7. §3.4 override + opt-out → Task 1 (opt-out) + Task 6 (`_GLOBAL_GUARD`/`defer-check`) + Task 7 (verb). §2 verification → Task 0. §5 safety (block-once, fail-open, no hook stamp) → Tasks 3 & 5 (stdout preserved; agent stamps). §6 testing → Tasks 1–8.
- Anchor invariant honored: no task makes the hook run `reconcile-stamp`/`mark-enriched`; the directive (Task 2) instructs the agent to.
- Naming consistency: `decide_block`, `render_block`, `auto_council_enabled`, `local_install_present`, `_GLOBAL_GUARD`, `_guard_body`, `_settings_path_for`, `scope` ∈ {"local","global"} used uniformly across tasks.
