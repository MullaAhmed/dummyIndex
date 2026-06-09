# 03 — Architecture

Five layers, each with a single responsibility.

## Layer 1 — Deterministic backbone (Python)

- Walks the repo.
- Detects code files. Skips agent config (`.claude/`, `.cursor/`, …) and noise (`node_modules`, `.git`, …).
- Parses every file via tree-sitter when a grammar exists.
- Uses regex extractors for the few supported formats without a tree-sitter grammar (Blade, Dart). Files in any other language are skipped — there is no LLM extraction fallback (it's roadmapped, deferred).
- Extracts classes, functions, methods, exports — uniformly across languages.
- Builds a structure graph: files contain symbols, classes contain methods.
- Builds a call graph: who calls whom.
- Runs Leiden community detection over the call graph.
- Identifies entry-point candidates (in-degree 0 in call subgraph + heuristic filters).
- Hashes content for incremental rebuilds.

**Output**: `tree.json`, `map/files.json`, `map/symbols.json`, `features/symbol-graph.json`, conventions.

**Speed**: seconds to tens of seconds. No network — extraction is entirely tree-sitter + regex, never an LLM call.

## Layer 2 — Skill orchestration (markdown)

- The `SKILL.md` is the entry point.
- Markdown describes the workflow, not code.
- Calls Python CLI for atomic operations (scaffolding, atomic file writes, renames).
- Dispatches subagents (Task tool) for any operation requiring judgment.
- Reads procedure markdowns for each phase of work.

**Why markdown**: the workflow is the contract. It must be human-readable, version-controlled, and overridable.

## Layer 3 — Multi-agent council (subagents)

- Three role classes: **dev** (parameterised stack specialist), **architect** (reorganiser), **critics** (DBA / security / PM).
- Three sequential stages — `/specify` → `/plan` → `/critique` — modelled on [spec-kit](https://github.com/github/spec-kit).
- Each stage has one author, one artifact: `spec.md` (dev) → `plan.md` (dev → architect) → `concerns.md` (critics).
- Each persona runs in its own context window (Task tool subagent).
- Mode (`light` / `standard` / `deep`) gates how many critics run and whether they cross-review.

**Why sequential**: the v0.13 parallel-essay model produced 5 overlapping perspectives that the chairman had to stitch. The new pipeline gives each artifact a single owner — no synthesis drift, no redundancy.

**Why subagents**: persona isolation still matters. The dev shouldn't wear the security hat mid-paragraph; the security critic shouldn't be tempted to wave away threats to keep the architect happy.

## Layer 4 — Atomic Python tools (CLI)

- Tiny CLI surface for operations the skill must do atomically.
- `flow-remove` — delete a noise flow, update every JSON reference.
- `features-rename` — atomic feature folder rename.
- `section-write` — atomic write of a markdown section into the right place.
- `council-log` — append to the audit log so resumption is safe.
- `refresh-indexes` — rebuild human-readable indexes from machine-readable ones.

**Why Python here**: these operations touch multiple files transactionally. Markdown instructions calling raw `mv` or `cat >` are not atomic. The CLI is.

## Layer 5 — Session hooks

dummyindex is **not a one-time setup**. It's a continuous co-evolution layer. The core install wires **three** Claude Code hooks — `SessionStart`, `Stop`, and `PreCompact` — **none of which rebuild the index**; they report drift and checkpoint session state, nothing more. (Separately, `/dummyindex-equip` — v0.15 — may wire the detected formatter as a `PostToolUse` hook under its own `DUMMYINDEX_EQUIP` sentinel; that belongs to equip's toolkit, not the core install.)

- The **`SessionStart` hook** runs `dummyindex context plan-update`, which prints a drift report (one line per feature whose source mtime exceeds its docs' mtime) to stdout. Claude Code takes that stdout as `additionalContext`.
- The **`Stop` hook** runs `dummyindex context memory nudge` — a handoff-checkpoint CTA, surfaced only when a session was significant and hasn't been saved.
- The **`PreCompact` hook** runs `dummyindex context memory breadcrumb` — writes a deterministic breadcrumb to `now.md` before the context window is compacted.
- The **running Claude session** — which knows *what* changed and *why* — updates the affected `.context/features/<id>/*.md` in place. The shell never rebuilds the backbone.
- The agent **never works against silently stale context** — drift is surfaced at session start and the session resolves it with full understanding.

The SessionStart drift flow (the `Stop`/`PreCompact` hooks are session bookkeeping, not shown):

```
┌─ Claude starts a session ──────────────────────────┐
│ ─► SessionStart hook                               │
│    ─► dummyindex context plan-update               │
│    ─► prints drift report (empty if nothing stale) │
│    ─► fed to the session as additionalContext      │
│ ─► the session updates features/<id>/*.md in place │
└────────────────────────────────────────────────────┘
```

**Why hooks no longer rebuild**: pre-v0.13.5, git `post-commit` + Claude `PostToolUse` + `SessionStart` all fired a shell-side `rebuild --changed`. But the council/skill never runs from a shell hook, so that deterministic-only rebuild re-scaffolded features on every edit — clobbering `features/INDEX.json`, leaving orphan `community-N/` folders and placeholder flow narratives the skill never came back to fill. Drift detection now lives in `dummyindex.context.drift` (mtime-based, with heuristic decay: editing a feature doc advances its mtime and the drift signal goes quiet).

- Council enrichment (Layer 3) is never hook-triggered — it's manual (`/dummyindex --recouncil`) or scheduled.
- A full deterministic `rebuild --changed` is still available as a **manual** CLI command; it's just no longer wired to a hook.

**Why session-driven**: the user shouldn't have to remember to refresh, and the *agent* — not a blind shell — is the right actor to reconcile prose with code, because it has the context of the change.

## Information flow

```
┌─────────────────────────────────────────────────┐
│  /dummyindex <path>   (user types in Claude)    │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  SKILL.md (orchestrator)                        │
│   ├── Phase 1: run Python CLI for backbone      │
│   ├── Phase 2: structural review (architect)    │
│   ├── Phase 3: per-feature pipeline             │
│   │     ├── /specify (stack-specialist dev)     │
│   │     ├── /plan    (architect reorganises)    │
│   │     └── /critique (critics, mode-gated)     │
│   ├── Phase 4: dev filters + narrates flows     │
│   ├── Phase 5: agents call atomic CLI to commit │
│   ├── Phase 6: refresh-indexes                  │
│   └── Phase 7: install hooks (first run only)   │
└─────────────────────────────────────────────────┘
                     │
                     ▼
            <repo>/.context/   (the artifact)
                     │
                     │  (drift surfaced at session start; updated by explicit rebuild/reconcile)
                     ▼
         consumed by every agent session
```

## What this architecture buys

- **Layer independence**. Python can be tested without LLMs. Markdown can change without breaking Python. Personas can swap without touching either.
- **Predictable cost**. Layer 1 is free. Layer 3 is metered (modes: light/standard/deep), runs on demand.
- **Resumability**. The audit log + content hashes mean a failed council can resume from where it stopped.
- **Portability**. The `.context/` folder is plain text + JSON. Any agent can read it.
- **Always current**. The SessionStart drift hook surfaces staleness at session start; the session reconciles it before doing task work.

## What it does NOT do

- No model selection inside the code. The session's model is what runs.
- No vector store. No embeddings. Structured retrieval only (see [12 — Retrieval](./12-retrieval.md)).
- No daemon. The hooks are event-driven, not polling.
