# 01 — Session-memory subsystem design

**Date:** 2026-06-05
**Status:** Approved (design) → ready for implementation plan
**Skill trigger:** `/dummyindex-remember`

## 1. Context & goal

The [`remember`](https://github.com/Digital-Process-Tools/claude-remember) plugin gives Claude Code
continuous, tiered session memory: a SessionStart hook injects a `=== HANDOFF ===` / `=== MEMORY ===`
block, a PostToolUse + Haiku pipeline auto-captures activity, and a `remember` skill writes handoffs.
Memory is compressed across tiers (`now.md` → `today-*.md` → `recent.md` → `archive.md` →
`core-memories.md`).

**Goal:** ship a **self-contained, markdown-first** equivalent *inside dummyindex*, so any repo with
dummyindex installed gets remember-style cross-session continuity **without** the separate plugin.
It must follow dummyindex's own architecture: deterministic mechanics in the Python CLI ("the
toolbox"), prose/judgment by the in-session agent ("the workforce"), wired via markdown and CLAUDE.md
("never intercept").

This is **not** a port of remember's Python pipeline. See §10 for the deliberate fidelity deltas.

## 2. Locked decisions (from brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Fidelity | **Markdown-first equivalent** — no background Haiku pipeline; compression is agent-run. |
| 2 | Storage | **`.context/memory/`**, committed to git, carved out of all regeneration. |
| 3 | Consolidation trigger | **Every handoff-write rolls tiers** (idempotent, date-based). No hook-side staleness detection. |
| 4 | Capture | **One agent-written summary per handoff** — no PostToolUse, no mid-session auto-fill. |
| 5 | Coexistence with `remember` | **Detect-and-suppress** — when the remember plugin is present, dummyindex's SessionStart memory block stays silent; its store + skill still work. |
| 6 | Skill name | **`/dummyindex-remember`** (distinct from remember's `/remember` and the `/dummyindex` orchestrator). |

## 3. Architecture overview

```
Every session in a dummyindex repo
   │
   ▼ SessionStart hook (one entry, sentinel-marked) runs TWO commands:
   │     1. dummyindex context plan-update   → drift report
   │     2. dummyindex context memory session-start → MEMORY block
   │           └─ suppressed (exit 0, no output) if remember plugin present
   │   both stdout streams → additionalContext
   │
   ▼ during the session: nothing is written to memory
   │
   ▼ user/agent invokes /dummyindex-remember (or "save the session"):
        1. Read now.md (read-before-write)
        2. Append a first-person summary entry to now.md
        3. dummyindex context memory roll  → deterministic tier bucketing
        4. agent compresses the rolled-down prose in recent.md / archive.md
        5. agent promotes durable facts → core-memories.md
        6. "Saved."
```

Split of responsibilities:

| Concern | Where |
|---|---|
| Emit the SessionStart memory block; detect remember plugin | Python CLI (`memory session-start`) |
| Deterministic, idempotent tier rolling (date/size bucketing) | Python CLI (`memory roll`) |
| Seed `.context/memory/` on first ingest | Python (`ingest`/memory module) |
| Skip `memory/` during refresh/rebuild | Python (carve-out in refresh + rebuild) |
| Write the session summary; compress rolled prose; promote core memories | Agent (skill markdown) |

## 4. Store layout — `.context/memory/`

```
.context/memory/
  now.md            # reverse-chronological session summaries (newest first)
  recent.md         # last ~7 days, compressed
  archive.md        # older, heavily compressed
  core-memories.md  # durable cross-session facts + identity candidates
```

- Seeded with empty stubs by `ingest` (idempotent; never overwrites existing content).
- Committed to git by default, like the rest of `.context/`.
- **Never regenerated.** `refresh-indexes` and `rebuild` must explicitly skip this directory.
- The per-day `today-*.md` tier from remember is intentionally dropped (see §10).

### File formats

`now.md`
```markdown
# Now

## 14:30 | main
Designed the session-memory subsystem; chose markdown-first + `.context/memory/`.
Next: write the implementation plan.
```
Entries are reverse-chronological (`## HH:MM | <branch>`), first person, 2–4 lines each.

`recent.md` / `archive.md`
```markdown
# Recent      (or # Archive)

## 2026-06-05
Compressed one-paragraph summary of the day's sessions.
```
Dated sections; `roll` appends, the agent compresses.

`core-memories.md`
```markdown
# Core memories

- Durable fact / decision that should survive compression.
- IDENTITY CANDIDATE: a key moment worth preserving verbatim.
```

## 5. CLI surface — `dummyindex context memory <verb>`

New module `dummyindex/cli/memory.py` exporting `_cmd_memory(args) -> int`; registered as
`ContextSubcommand.MEMORY` in `dummyindex/context/enums.py` and `_HANDLERS` in
`dummyindex/cli/__init__.py`; documented in `dummyindex/cli/_usage.py`.

Pure mechanics live in a domain module `dummyindex/context/domains/memory/` (rolling, formatting,
detection), keeping the CLI a thin boundary per CONVENTIONS.

### `memory session-start [--root PATH]`
Read-only emit for the SessionStart hook.
- If `<root>/.context/memory/` is absent → exit 0, no output.
- **Suppress:** if the remember plugin is detected (see §7) → exit 0, no output.
- Else print:
  - `=== HANDOFF ===` with `Write next handoff to: <root>/.context/memory/ via /dummyindex-remember`
  - `=== MEMORY ===` with bounded excerpts: all of `now.md`, the head of `recent.md`, and
    `core-memories.md` (size-capped to keep additionalContext small).
- Never writes. Always exits 0 (hook must never fail a session).

### `memory roll [--root PATH] [--now-keep-days N]`
Deterministic, **idempotent** tier rolling, invoked by the skill.
- Parse `## YYYY-MM-DD` / `## HH:MM | branch` headers.
- Move `now.md` entries older than today (default) into a dated section of `recent.md`.
- Move `recent.md` dated sections older than ~7 days into `archive.md`.
- **Idempotent:** running twice in one day, or on already-rolled content, is a no-op (no duplicate
  sections, no re-moves).
- Print a short report of what moved (so the agent knows which prose to compress). Never deletes
  user content; only relocates between tiers.

### `memory init [--root PATH]` (internal; may be folded into `ingest`)
Create `.context/memory/` + empty stub tiers if absent. Idempotent.

## 6. SessionStart hook wiring

Extend the existing `_SESSION_START_HOOK` in `dummyindex/context/hooks.py` so the single
sentinel-marked entry runs **two** commands (both guarded, both `exit 0` on any failure):

```jsonc
{
  "matcher": "*",
  "hooks": [
    { "type": "command", "command": "# DUMMYINDEX_AUTO_REFRESH ... dummyindex context plan-update ..." },
    { "type": "command", "command": "# DUMMYINDEX_AUTO_REFRESH ... dummyindex context memory session-start ..." }
  ]
}
```

- One hook entry, not a competing second hook → consistent with "route via CLAUDE.md, never intercept".
- `install()` already refreshes its sentinel-bearing entry in place when the body changes, so
  upgraders pick up the second command automatically.
- `status()` / `uninstall()` continue to match on the sentinel — no change needed beyond the body.
- Drift report prints first, memory block second (order is cosmetic; both land in additionalContext).

## 7. Coexistence — detect-and-suppress

`memory session-start` suppresses its block when the remember plugin is active. Detection signal
(cheap, reliable, read-only):

- **Primary:** `<root>/.remember/` directory exists.
- (Optional secondary, if needed: a SessionStart hook command in `.claude/settings.json` that
  references the remember plugin / emits `=== HANDOFF ===`. Start with the `.remember/` check; only
  add this if the dir check proves insufficient.)

When suppressed: exit 0 with no stdout. The store and `/dummyindex-remember` skill remain fully
functional — only the SessionStart *injection* stands down, so the user never sees two memory blocks.

dummyindex never disables, edits, or otherwise manages the remember plugin's lifecycle.

## 8. Skill — `/dummyindex-remember`

New skill shipped under `dummyindex/skills/memory/SKILL.md` (a directory so it can carry companion
markdown later if needed). Installed by the existing `install()` copy loop (which must be extended to
copy the new subdir — see §9) into `<scope>/.claude/skills/dummyindex/...` and registered like the
other bundled skills.

Frontmatter: `name: dummyindex-remember`, `allowed-tools: Read, Write, Bash`, a description with
trigger phrases ("save the session", "remember this", "/dummyindex-remember").

Procedure (markdown, agent-run):
1. Resolve `<root>/.context/memory/`. If absent, run `dummyindex context memory init`.
2. **Read `now.md`** (satisfies read-before-write).
3. Append a first-person entry `## HH:MM | <branch>` summarizing what was done / decided / what's next
   (2–4 lines). Use session knowledge — no transcript parsing.
4. Run `dummyindex context memory roll` and read its report.
5. Compress the rolled-down content: tighten `recent.md` dated sections; heavily compress `archive.md`.
6. Promote durable cross-session facts / key moments to `core-memories.md`.
7. Say **"Saved."** — nothing else.

Style mirrors remember's skill: under ~20 lines of actual writing, specific (paths, branches, MR
numbers), forward-looking.

## 9. Packaging / install changes

- `pyproject.toml` `[tool.setuptools.package-data]` → add `skills/memory/*.md`.
- `dummyindex/__main__.py` `install()` copy loop → include the new `skills/memory` subdir alongside
  `agents/`, `council/`, `retrieval/`.
- `ingest`/`init` → seed `.context/memory/` (via `memory init`).
- `dummyindex/skills/skill.md` → a short pointer to the memory subsystem + `/dummyindex-remember`
  (the orchestrator stays focused on the context engine; memory is a sibling concern).
- `.context/HOW_TO_USE.md` generation → mention `memory/` as a non-generated, agent-maintained store
  (so future sessions know it exists and is not part of tree-search retrieval).

## 10. Differences from remember (explicit — the "exactly same" caveats)

1. **No background Haiku pipeline.** Compression is agent-run, on save.
2. **No PostToolUse auto-capture.** `now.md` gets one agent summary per `/dummyindex-remember`, not
   live mid-session entries. This is the single largest behavioral delta and was confirmed as
   acceptable.
3. **No per-day `today-*.md` tier.** Tiers are `now → recent → archive` (+ `core-memories`).
4. **Store at `.context/memory/`**, not `.remember/`.
5. **Detect-and-suppress** when remember is installed (remember has no equivalent of this).
6. **Same-shape UX:** SessionStart memory block + on-demand handoff skill + tiered, committed files.

## 11. Error handling

- Hook commands always `exit 0`; a missing CLI, missing `.context/`, or any error never breaks a
  session (`command -v dummyindex || exit 0` guard already present).
- `memory roll` on empty/malformed tiers → tolerant no-op.
- `memory roll` is idempotent → safe to run repeatedly (every save).
- remember present → silent suppression, not an error.
- Skill always Reads `now.md` before Writing.
- `.context/memory/` writes use the repo's atomic temp-file-then-replace pattern.

## 12. Testing

Conventions: pytest, frozen dataclasses, enum constants, typed exception hierarchy, CLI-boundary I/O,
small focused files. Run `python-reviewer` after changes under `dummyindex/` or `tests/`.

- **Unit (domain):** `roll` idempotency (same-day re-run = no-op); date bucketing (now→recent→archive
  boundaries); empty/malformed tier tolerance; `session-start` output shape; remember-detection
  (`.remember/` present vs absent → suppress vs emit).
- **Unit (carve-out):** `refresh-indexes` and `rebuild` leave `.context/memory/` untouched.
- **Integration:** `install` writes a SessionStart entry containing **both** commands; `ingest` seeds
  the memory dir; round-trip a save → roll → re-save and assert no duplication.
- Target ≥ 80% coverage on new modules.

## 13. Implementation surface (files)

**Add**
- `dummyindex/cli/memory.py` — `_cmd_memory` boundary.
- `dummyindex/context/domains/memory/` — rolling, formatting, detection (pure logic).
- `dummyindex/skills/memory/SKILL.md` — the `/dummyindex-remember` skill.
- `tests/test_memory_*.py` — unit + integration.

**Modify**
- `dummyindex/context/enums.py` — add `ContextSubcommand.MEMORY`.
- `dummyindex/cli/__init__.py` — register handler.
- `dummyindex/cli/_usage.py` — document `context memory`.
- `dummyindex/context/hooks.py` — add the second SessionStart command.
- `dummyindex/__main__.py` — copy `skills/memory` on install.
- `pyproject.toml` — package-data for `skills/memory/*.md`.
- `ingest`/`init` path — seed `.context/memory/`.
- `dummyindex/skills/skill.md`, `.context/HOW_TO_USE.md` generation — pointers.

## 14. Open questions

None blocking. (Secondary remember-detection signal in §7 is a fallback to add only if the
`.remember/` directory check proves insufficient in practice.)
