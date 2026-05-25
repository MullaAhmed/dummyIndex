# 03 — Architecture

Five layers, each with a single responsibility.

## Layer 1 — Deterministic backbone (Python)

- Walks the repo.
- Detects code files. Skips agent config (`.claude/`, `.cursor/`, …) and noise (`node_modules`, `.git`, …).
- Parses every file via tree-sitter when a grammar exists.
- Falls back to LLM-driven extraction for languages without tree-sitter coverage.
- Extracts classes, functions, methods, exports — uniformly across languages.
- Builds a structure graph: files contain symbols, classes contain methods.
- Builds a call graph: who calls whom.
- Runs Leiden community detection over the call graph.
- Identifies entry-point candidates (in-degree 0 in call subgraph + heuristic filters).
- Hashes content for incremental rebuilds.

**Output**: `tree.json`, `map/files.json`, `map/symbols.json`, `features/symbol-graph.json`, conventions.

**Speed**: seconds to tens of seconds. No network (when tree-sitter handles the language). LLM fallback only when needed.

## Layer 2 — Skill orchestration (markdown)

- The `SKILL.md` is the entry point.
- Markdown describes the workflow, not code.
- Calls Python CLI for atomic operations (scaffolding, atomic file writes, renames).
- Dispatches subagents (Task tool) for any operation requiring judgment.
- Reads procedure markdowns for each phase of work.

**Why markdown**: the workflow is the contract. It must be human-readable, version-controlled, and overridable.

## Layer 3 — Multi-agent council (subagents)

- Five personas: architect, senior developer, database engineer, security analyst, product manager.
- A chairman synthesizer integrates their outputs.
- Three stages: independent perspectives → cross-review → synthesis.
- Each persona has its own context window (Task tool subagent).
- Outputs are markdown files written back into `.context/features/<id>/`.

**Why subagents**: persona isolation matters. The security analyst should not be tempted to make architectural compromises; the architect should not be tempted to wave away threats.

## Layer 4 — Atomic Python tools (CLI)

- Tiny CLI surface for operations the skill must do atomically.
- `flow-remove` — delete a noise flow, update every JSON reference.
- `features-rename` — atomic feature folder rename.
- `section-write` — atomic write of a markdown section into the right place.
- `council-log` — append to the audit log so resumption is safe.
- `refresh-indexes` — rebuild human-readable indexes from machine-readable ones.

**Why Python here**: these operations touch multiple files transactionally. Markdown instructions calling raw `mv` or `cat >` are not atomic. The CLI is.

## Layer 5 — Always-on auto-refresh loop

dummyindex is **not a one-time setup**. It's a continuous co-evolution layer.

- A git **post-commit hook** runs `dummyindex context rebuild --changed` after every commit.
- A **`PostToolUse` hook** in `.claude/settings.json` runs `rebuild --changed` after Claude edits files.
- A **`SessionStart` hook** runs a fast staleness check; if `.context/` lags the code, refresh before the session begins.
- The agent **never works against stale context** — staleness is detected and resolved transparently.

```
┌─ git commit ──────────────────────────────────────┐
│ ─► post-commit hook                                │
│    ─► dummyindex context rebuild --changed         │
└────────────────────────────────────────────────────┘
┌─ Claude edits a file ──────────────────────────────┐
│ ─► PostToolUse hook                                │
│    ─► dummyindex context rebuild --changed         │
└────────────────────────────────────────────────────┘
┌─ Claude starts a session ──────────────────────────┐
│ ─► SessionStart hook                               │
│    ─► dummyindex context check --auto-refresh      │
│    ─► refreshes if stale, no-op if current         │
└────────────────────────────────────────────────────┘
```

- Council enrichment (Layer 3) is NOT triggered by these hooks — it's manual / weekly.
- Only the deterministic backbone (Layer 1 + Layer 4 reconcile) runs in the auto-refresh loop.
- The agent can request a fresh council via `/dummyindex --recouncil` after a big refactor.

**Why hook-driven**: the user shouldn't have to remember to refresh. The repo's truth is git + the editor; dummyindex follows.

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
│   ├── Phase 3: dispatch council per feature     │
│   │     ├── Stage 1 (parallel perspectives)     │
│   │     ├── Stage 2 (cross-review)              │
│   │     └── Stage 3 (chairman synthesis)        │
│   ├── Phase 4: senior dev filters + narrates    │
│   ├── Phase 5: agents call atomic CLI to commit │
│   ├── Phase 6: refresh-indexes                  │
│   └── Phase 7: install hooks (first run only)   │
└─────────────────────────────────────────────────┘
                     │
                     ▼
            <repo>/.context/   (the artifact)
                     │
                     │  (auto-refreshed by hooks)
                     ▼
         consumed by every agent session
```

## What this architecture buys

- **Layer independence**. Python can be tested without LLMs. Markdown can change without breaking Python. Personas can swap without touching either.
- **Predictable cost**. Layer 1 is free. Layer 3 is metered (modes: light/standard/deep), runs on demand.
- **Resumability**. The audit log + content hashes mean a failed council can resume from where it stopped.
- **Portability**. The `.context/` folder is plain text + JSON. Any agent can read it.
- **Always current**. The auto-refresh loop guarantees the index reflects the code at any session start.

## What it does NOT do

- No model selection inside the code. The session's model is what runs.
- No vector store. No embeddings. Structured retrieval only (see [12 — Retrieval](./12-retrieval.md)).
- No daemon. The hooks are event-driven, not polling.
