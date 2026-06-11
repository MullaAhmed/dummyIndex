# Design — Always-on, drift-triggered auto-council

- **Date:** 2026-06-11
- **Status:** Draft (awaiting review)
- **Topic:** Make dummyindex keep `.context/` fresh automatically across every session — even when the session is driving a *different* plugin — by hard-blocking session exit once, when drift exists, with a directive that the live agent run the scoped council.

---

## 1. Motivation

`.context/` only stays accurate if *someone* reconciles it after code changes. Today that
someone is the live Claude session, prompted by a **soft** SessionStart drift report. A
session opened to drive a different plugin (feature-dev, vercel, …) does its work, the
source moves ahead of the docs, and nothing reconciles — the report is informational and
easy to ignore. The index silently rots.

**Goal:** when `.context/` is genuinely stale, the system should *guarantee* a reconcile
happens — at the natural moment (session end), scoped to only what drifted, and across
every repo where dummyindex is installed — without the user ever having to ask, and
without a plugin choice suppressing it.

### The four decisions that shape this (from brainstorming)

1. **Auto-trigger the council**, not just report drift.
2. **Drift-only, scoped** to the drifted features (no-op when `.context/` is fresh; never
   re-councils clean features).
3. **At session end**, via a `Stop` hook that **blocks once** with a council directive — so
   the user's actual work runs first, uninterrupted.
4. **Global install** by default reach (`~/.claude/settings.json`), with a **per-repo
   override** taking precedence.

### Why this does NOT resurrect the 0.13.5 footgun

The auto-`rebuild --changed` mechanism removed in 0.13.5 was dangerous because **the hook
itself mutated `.context/`**, overwriting council-enriched feature folders with raw
`community-N` placeholders. This design keeps that invariant intact:

- The hook **never writes and never stamps** `.context/`. It only *detects drift* and
  *blocks the session's exit once* with a `reason` directive.
- The **agent** runs the council (`recouncil`), the reconcile placement/enrichment, and the
  `reconcile-stamp`.

So both prior decisions still hold: **"hooks only report; the session acts"** and
**"NO hook may stamp the anchor."** What changes is only *forcefulness* (soft nudge →
block-once) and *reach* (per-repo → global).

### Why the council can't "just auto-run"

The council is an **agent loop** (dev → architect → critics, dispatched via the Task tool),
not a deterministic CLI step. A hook fires a shell command; it cannot summon subagents. So
the only mechanism available in Claude Code is: **hook detects drift → hook hands the agent
a directive → agent runs the council.** A `Stop` hook `decision: block` is the lever that
forces the directive to be acted on before the session can end.

---

## 2. Hook contracts relied on

Empirically verified previously in this repo (see
`2026-06-08-auto-handoff-nudge-design.md`):

| Channel | Reaches | Verdict |
|---|---|---|
| `additionalContext` (Stop, `hookSpecificOutput`) | the **model** | ✅ reaches model; auto-grants an immediate agent turn |
| editing `.claude/settings.json` mid-session | — | ✅ takes effect without restart (one-time approve-hooks prompt) |

Relied on but **to be locally verified before relying on them** (standard Claude Code Stop
semantics):

- A `Stop` hook returning `{"decision":"block","reason":"…"}` on stdout (exit 0) **prevents
  the session from stopping** and surfaces `reason` to the model, granting it a turn.
- The Stop hook receives JSON on stdin including **`stop_hook_active`** (true when the stop
  was already once blocked by a hook), **`session_id`**, and **`transcript_path`**.
- `~/.claude/settings.json` hooks are **merged additively** with `.claude/settings.json`
  hooks — there is no native override; both fire if both are present.

**Verification task (pre-implementation):** wire a throwaway `Stop` block hook into this
repo, confirm block + `reason` + `stop_hook_active` re-entry behaviour, then remove it.
Mirror the empirical-table approach of the auto-handoff-nudge spec.

---

## 3. Components

### 3.1 New deterministic verb: `dummyindex context reconcile-gate`

New module `dummyindex/context/reconcile_gate.py` (pure decision logic) + a thin CLI
wrapper in `dummyindex/cli/` registered under `context`. Mirrors how `memory nudge` is a
thin wrapper over `memory/nudge.py:decide_nudge`.

**Behaviour** (`decide_block(...) -> Optional[str]`):

1. Read the Stop-hook JSON from **stdin**: `stop_hook_active`, `session_id`,
   `transcript_path`. (CLI boundary parses; the decision function takes typed args.)
2. **Cheap gates first** (O(1)), bail to silence (print nothing, exit 0) on any:
   - `.context/features/` absent → not an indexed repo.
   - `stop_hook_active is True` → we already blocked once this stop; **block at most once**,
     never trap the session.
   - opt-out marker present (see §3.4).
3. Compute drift with the existing `compute_drift(root) -> DriftReport`.
   - `not report.has_drift` → silence.
4. **Substantive-session gate** (reuse `memory/transcript.py:read_session_signal` +
   `memory/nudge.py:is_significant`): only block when the session actually did work
   (subagents ran or output ≥ `LONG_OUTPUT_TOKENS`). A trivial 10-second session is never
   trapped by pre-existing drift; that case still gets the existing soft SessionStart
   report.
5. Otherwise emit `{"decision":"block","reason": <directive>}` and exit 0.

**The directive (`reason`)** is scoped and points at the canonical flow, listing the exact
drifted items from the report:

- mtime-drifted feature IDs (`report.by_feature()`) → `recouncil <feature>` per
  `council/65-reconcile.md`.
- `report.unassigned_new_files` / `report.awaiting_enrichment` → reconcile place/enrich.
- Ends with the stamp step (`reconcile-stamp` / `mark-enriched`) — **run by the agent**, so
  the anchor advances exactly once, by the agent, never the hook.

The gate is **idempotent across the block→reconcile→stop cycle**: once the agent reconciles
and stamps, `compute_drift` returns empty, the next Stop fires, drift check passes, exit 0,
session ends. No session-state bookkeeping needed — drift *is* the state.

### 3.2 Stop hook gains a second entry

In `context/hooks.py`, under the existing `SENTINEL`, the `Stop` event gets a second hook
command alongside `memory nudge`:

```
dummyindex context reconcile-gate --scope <global|project>
```

Separate concerns, separate entries: `memory nudge` = handoff checkpoint (soft,
`additionalContext`); `reconcile-gate` = reconcile drift (hard, `decision: block`). Both
self-gate on `command -v dummyindex` and tolerate failure (`|| true`, `exit 0`).

### 3.3 Global install — `--global` / `--local`

`dummyindex context hooks install` (and `uninstall`/`status`) gain a `--global` flag that
targets `~/.claude/settings.json` instead of the repo's `.claude/settings.json`. Default
**stays `--local`** for back-compat. The self-gating already baked into every hook command
(`command -v dummyindex` + `.context/` existence via `compute_drift`/`plan-update`) means
the global hooks **no-op in non-indexed repos**, so a single global install is safe across a
machine.

`status` reports both scopes. `uninstall --global` scrubs our sentinel'd entries from the
user settings file using the same preserve-or-refuse logic as the local path.

### 3.4 Per-repo override precedence + opt-out

Because Claude Code merges user + project hooks additively (no native override), precedence
lives **in the command**:

- The **global**-scope command (`--scope global`) first checks
  `$CLAUDE_PROJECT_DIR/.claude/settings.json` for our `SENTINEL` under the same event. If
  the repo has its own `--local` dummyindex hooks installed, the global command **yields
  (exit 0)** — the per-repo install is authoritative, nothing double-fires.
- The **project**-scope command (`--scope project`) always runs; it *is* the override.
- **Opt-out:** a repo with global installed but wanting dummyindex hooks off reads a disable
  marker. **Concretely:** the gate reads `.context/config.json` and treats
  `"auto_council": false` as off; absence of the file or key means **enabled** (opt-out, not
  opt-in). When set false, the gate no-ops even though global is installed. (If
  `equipment.json` later grows a general settings block, the key can migrate there; for v1
  it lives in `.context/config.json`.)

---

## 4. Data flow

```
session ends (other-plugin work done, source edited)
        │
        ▼
Stop hook fires  ──►  memory nudge (soft handoff CTA, unchanged)
        │
        └─►  reconcile-gate --scope <global|project>
                 │  read stdin: stop_hook_active, session_id, transcript
                 │  --scope global & per-repo sentinel present? ─► yield (exit 0)
                 │  opt-out marker?                              ─► yield (exit 0)
                 │  stop_hook_active true?                       ─► yield (exit 0)   (block-once)
                 │  compute_drift → has_drift?                   ─► no ─► yield
                 │  substantive session?                         ─► no ─► yield
                 ▼ yes to all
        print {"decision":"block","reason": <scoped council directive>}, exit 0
                 │
                 ▼
   session blocked from ending; agent gets a turn, reads directive
                 │
                 ▼
   AGENT runs: recouncil <drifted features> / reconcile place+enrich  →  reconcile-stamp
                 │  (hook never writes; agent stamps the anchor — once)
                 ▼
   drift cleared ─► next Stop: compute_drift empty ─► gate silent ─► session ends
```

---

## 5. Error handling & safety

- Every hook command tolerates failure: `command -v dummyindex || exit 0`, downstream
  `|| true`, terminal `exit 0`. A broken or slow `reconcile-gate` never wedges a session's
  ability to end (worst case: it fails to block, which is fail-open and safe).
- **Block-once** via `stop_hook_active` guarantees the user/agent can always end the session
  on the second stop even if they decline the reconcile — a strong prompt, not a trap.
- **Substantive gate** prevents trapping trivial sessions on pre-existing drift.
- **Opt-out** + per-repo override give a full kill switch.
- Honors the anchor invariant: the hook **never** runs `reconcile-stamp` or
  `mark-enriched`; only the agent does, so the commit anchor advances exactly once and only
  through the sanctioned reconcile path.

---

## 6. Testing

Follows the repo's deterministic-plumbing test style (pytest, `tests/` mirrors module
tree), targeting the existing 80%+ bar.

**Unit — `reconcile_gate.decide_block`:**
- No `.context/features/` → silence.
- `stop_hook_active=True` → silence (block-once).
- Drift present + substantive + not active + no opt-out → block JSON with the exact drifted
  feature IDs in `reason`.
- Drift present but non-substantive session → silence.
- Opt-out marker set → silence.
- `--scope global` with per-repo sentinel present → silence (override yields).
- `--scope global` with no per-repo sentinel → evaluates normally.
- Directive content: asserts drifted feature IDs, unassigned files, and the
  `reconcile-stamp` step all appear; asserts the gate never itself stamps.

**Unit — `hooks` install/uninstall/status `--global`:**
- `install --global` writes our three hooks (incl. the new Stop gate entry) into a fake
  `$HOME/.claude/settings.json`; idempotent; preserves user-authored hooks.
- `uninstall --global` scrubs only sentinel'd entries; preserve-or-refuse on malformed
  settings.
- `status` reports global + local independently.
- Stop event now carries **two** sentinel'd entries (nudge + gate); install/uninstall handle
  multiple entries per event.

**Integration:** an end-to-end gate run over a fixture repo with a drifted feature,
asserting the emitted block JSON; and a re-entry run (`stop_hook_active=True`) asserting
silence.

**Empirical pre-work:** the §2 verification task (throwaway Stop block hook) before wiring.

---

## 7. Out of scope (YAGNI)

- Running the council headlessly / in the hook (impossible — agent loop).
- Auto-stamping or any hook-side `.context/` mutation (violates the anchor invariant).
- Whole-repo council on drift (rejected: re-councils clean features, token-heavy).
- Unconditional every-session council (rejected: hijacks unrelated sessions).
- Making `LONG_OUTPUT_TOKENS` / gate thresholds user-configurable in v1.
