# Design — Auto-handoff nudge

- **Date:** 2026-06-08
- **Status:** Draft (awaiting review)
- **Topic:** Make `/dummyindex-remember` effectively automatic without ever auto-authoring a handoff.

---

## 1. Motivation

Cross-session memory (`.context/session-memory/`) only fills if the user remembers to
type `/dummyindex-remember`. A user who installs dummyindex **without** the superpowers
`remember` plugin gets no automatic handoff at all, which defeats the point of the store.
We want the system to prompt for a handoff at the moments it matters — after a long or
subagent-heavy stretch of work, and right before context is lost to compaction — without
silently fabricating a low-quality summary.

**Goal:** detect "a handoff is worth saving," then **nudge** (never silently author the
rich handoff) and lay down a deterministic **breadcrumb** so a session is never lost even
if the nudge is ignored.

### Why it can't "just auto-run the skill"

`/dummyindex-remember` is a **skill**, not a CLI command — its value (a first-person
summary, prose compression, promoting durable facts) is judgment work only the model can
do. A hook fires a deterministic shell command; it cannot summon the agent to author
prose. So the feature is necessarily: **detect → nudge the agent / breadcrumb**, not
detect → auto-write.

---

## 2. Verified hook contracts (empirical, this session)

A throwaway `Stop` hook was wired into this repo's `settings.json`, fired once, then
removed. Observed directly:

| Channel | Reaches | Verdict |
|---|---|---|
| `additionalContext` (Stop, `hookSpecificOutput`) | the **model** | ✅ reaches model; **auto-grants an immediate agent turn** with no user input |
| `systemMessage` (Stop) | the **user**'s terminal | ✅ shown to user |
| `stderr` on exit 0 (Stop) | the **user**'s terminal | ✅ shown to user |
| editing `.claude/settings.json` mid-session | — | ✅ takes effect without restart; triggers a one-time **approve-hooks** prompt |

From the subagent research (Claude Code docs), confirmed but **not yet locally verified**
(verify in isolation before relying on them):

- **PreCompact cannot inject `additionalContext`** — it is deterministic and cannot reach
  the model after compaction. It *can* run a shell command and (per docs) emit a
  top-level `systemMessage`.
- **SessionStart fires again after compaction** with `source == "compact"` — this is the
  existing post-compaction continuity path (`memory session-start` already runs there).
- Stop/PreCompact hooks receive JSON on stdin including `transcript_path`, `session_id`,
  and (PreCompact) `compact_trigger`.

**Design consequence:** the agent-facing nudge rides on **Stop → `additionalContext`**
(auto-grants a turn, so the agent posts an in-chat CTA). PreCompact's only reliable job is
the deterministic **breadcrumb** write; it does not talk to the model.

---

## 3. Design overview

Two new deterministic CLI verbs, wired to two hook events:

```
Stop event ───► dummyindex context memory nudge   ──► (if significant & not suppressed)
                                                       prints additionalContext JSON
                                                       ──► agent gets a turn, posts a
                                                           one-line CTA offering to run
                                                           /dummyindex-remember
PreCompact ───► dummyindex context memory breadcrumb ► writes a deterministic breadcrumb
                                                        entry to now.md (never the model)
```

Post-compaction continuity is unchanged: the existing `SessionStart` (`source==compact`)
hook re-emits the memory block via `memory session-start`.

---

## 4. Components & file layout

Reuses existing modules — no new top-level packages.

| File | Change |
|---|---|
| `dummyindex/context/domains/memory/nudge.py` | **new** — significance detection, suppression, `additionalContext` text rendering. |
| `dummyindex/context/domains/memory/breadcrumb.py` | **new** — deterministic breadcrumb entry from git state + transcript counts; prepend to `now.md`. |
| `dummyindex/context/domains/memory/enums.py` | add `MemoryVerb.NUDGE = "nudge"`, `MemoryVerb.BREADCRUMB = "breadcrumb"`. |
| `dummyindex/context/domains/memory/__init__.py` | export the new entry points. |
| `dummyindex/cli/memory.py` | dispatch the two new verbs (wire-only: parse stdin/args, call domain, print, exit 0). |
| `dummyindex/usage/transcripts.py` | reuse `load_session()` (`main_turns`, `subagent_turns`, `subagent_file_count`) for significance; extract a tiny shared helper if a clean import boundary is needed. |
| `dummyindex/context/hooks.py` | add `PreCompact` + `Stop` entries under the existing `DUMMYINDEX_AUTO_REFRESH` sentinel; extend `HookStatus`, `CURRENT_CLAUDE_EVENTS`, install/uninstall/status. |
| `dummyindex/cli/_usage.py` | document the two new verbs in `context --help`. |
| `tests/context/` | new unit tests (see §11). |

**Layering rule (repo convention):** the CLI layer is wire-only; all logic lives in the
`domains/memory/` domain. Frozen dataclasses, enum constants, typed errors.

---

## 5. Significance detection (session-scoped)

Reuses `usage.transcripts.load_session(main_transcript)`. A session is **significant**
when either:

- **Subagents:** `subagent_file_count > 0` — a `Task`/subagent ran at some point this
  session ("a call that had subagents"); **or**
- **Long:** cumulative main-thread `output_tokens` ≥ **40,000** (starting constant).

Session granularity (not per-turn) is deliberate: once-per-session suppression (§6) makes
the turn-vs-session distinction moot, and it reuses `load_session` directly. Thresholds
are **hardcoded module constants** (named, in `nudge.py`) — no user-facing knobs in v1;
they get calibrated by watching the feature nag once, then tuned in code.

The `nudge` verb reads the hook's stdin JSON for `transcript_path` + `session_id`
(falling back to `usage.transcripts.find_main_transcript` if absent).

---

## 6. Suppression & state

`nudge` prints nothing (→ no agent turn) when **any** of:

- a nudge already fired for this `session_id` (once per session), **or**
- `now.md`'s top entry is **fresh** (a handoff was just saved — nothing to prompt), **or**
- the `remember` plugin is present (§10).

State: `.context/cache/nudge-state.json` — `{ "<session_id>": { "nudged_at": "<iso>" } }`.
`.context/cache/` is already gitignored (internal scratch). Written atomically
(temp-file + rename), like the rest of the store.

**Cheap-checks-first ordering (performance).** The `Stop` hook fires on *every* turn, so
`nudge` must short-circuit before the expensive transcript parse. Order: (1) `.remember/`
present? (2) marker set for this `session_id`? (3) `now.md` top entry fresh (by mtime /
parsed date)? — all O(1) file checks. Only if none suppress does it call `load_session`
to compute significance. This keeps per-turn overhead to a couple of `stat`s until the one
turn that actually nudges.

---

## 7. Breadcrumb format

`breadcrumb` prepends one entry to the **top** of `now.md`, tagged so a later rich handoff
clearly supersedes it and the roller/agent can compress it:

```
## YYYY-MM-DD HH:MM | <branch> (auto-breadcrumb)
Auto-saved before compaction. N files changed (+A/-B); subagents: S; main turns: T.
Touched: path/one.py, path/two.py, … (capped at ~8, "+k more").
```

Fully deterministic — no LLM. Sources: `git rev-parse --abbrev-ref HEAD`,
`git diff --stat`, and `load_session` counts. Idempotent within a session: if the top
entry is already this session's auto-breadcrumb, update it in place rather than stacking a
second one (multiple compactions in one session → one breadcrumb that advances).

The breadcrumb is the **floor** the user chose ("breadcrumb + prompt"): even if every CTA
is ignored, the session leaves a factual trace.

---

## 8. Stop nudge — `additionalContext` contract

When significant and unsuppressed, `nudge` writes the suppression marker, then prints:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "Stop",
    "additionalContext": "dummyindex: this session is substantial (subagents: S; ~T main-thread output tokens) and no handoff has been saved. Offer the user a one-line CTA to checkpoint a handoff and, only if they agree, run /dummyindex-remember. Do NOT save automatically."
  }
}
```

The auto-granted turn lets the agent post an **in-chat, actionable** CTA (the user's
chosen "agent-relayed" delivery). Because the marker is now set, the *next* Stop produces
no output → no second turn → **no loop** (verified: the spike's single-fire guard behaved
exactly this way).

---

## 9. Hook wiring (`hooks.py`)

Add two entries beside the existing SessionStart hook, all under the
`DUMMYINDEX_AUTO_REFRESH` sentinel, each guarded by `command -v dummyindex`:

- **`Stop`** — runs `dummyindex context memory nudge --root "$CLAUDE_PROJECT_DIR"`.
  Unlike the drift wrappers, this one **must let stdout through** (it carries the
  `additionalContext` JSON). Still `exit 0` on any internal error.
- **`PreCompact`** — runs `dummyindex context memory breadcrumb --root "$CLAUDE_PROJECT_DIR"`,
  stdout/stderr suppressed, `exit 0` always.

Updates: add both to `CURRENT_CLAUDE_EVENTS`; extend `HookStatus` (new bool fields +
`all_installed`); `install` inserts all three idempotently and is still additive /
never-clobber; `uninstall` scrubs all three; `status` reports each. Installed by
`ingest` / `install --scope project` / `hooks install` exactly as today.

---

## 10. `remember` plugin coexistence

Mirror the existing precedent (`memory session-start` already stands down when
`.remember/` is present): when `remember_plugin_present(root)` is true, **both `nudge` and
`breadcrumb` stay silent / no-op**. The plugin owns handoffs in that repo; dummyindex does
not double-prompt or double-write.

> Consequence: in *this* repo (which has `.remember/`) the feature is a deliberate no-op —
> it is built for shipped installs that lack the plugin.

---

## 11. Testing plan (TDD, `tests/context/`)

Unit:

- **Significance:** subagent-present → significant; long (≥ threshold) → significant;
  small & no subagents → not significant; boundary at the threshold constant.
- **Suppression:** fires once per `session_id`; suppressed after marker; suppressed when
  `now.md` top entry is fresh; suppressed when `.remember/` present.
- **Breadcrumb:** deterministic given a fixed git state + transcript; `git diff --stat`
  parsing; file-list cap; in-place update on a second call in the same session.
- **Nudge stdout:** correct `hookSpecificOutput`/`additionalContext` JSON shape on fire;
  empty stdout when suppressed.

Wiring (extend existing `hooks.py` tests):

- install adds Stop + PreCompact + SessionStart idempotently; sentinel-scoped;
  uninstall removes only sentinel-bearing entries; status reports all three;
  user-authored hooks untouched.

Target the repo's 80%+ coverage bar; `ruff` + `mypy` clean.

---

## 12. Out of scope (v1) / verify at implementation

- **PreCompact `systemMessage` CTA** — the breadcrumb is the floor; a user-facing CTA on
  PreCompact is a possible add-on, but `systemMessage`-on-PreCompact is unverified locally.
  Verify in an isolated session before adding.
- **`SessionStart source==compact`** continuity — relied on but verify locally.
- **Threshold config knobs** — hardcoded until observed nagging justifies tuning.
- **Turn-scoped significance** — session-scoped is sufficient for v1.

---

## 13. Decisions log (forks the user chose)

1. **Write vs prompt:** *Breadcrumb + prompt* — PreCompact auto-writes a deterministic
   breadcrumb; the rich handoff stays prompt-driven.
2. **Verify hook contracts:** *Run the spike now* — done (§2).
3. **CTA delivery:** *Agent-relayed* via `additionalContext` (not passive `systemMessage`).
4. **`remember` coexistence:** *Silent when `.remember/` present* (default, §10).
5. **Significance thresholds:** subagents → always; long → ≥40k main output tokens
   (starting constant).
