# 03 — Architecture

Five layers, each with a single responsibility.

## Layer 1 — Deterministic backbone (Python)

- Walks the repo.
- Detects code files. Skips agent config (`.claude/`, `.agents/`, `.codex/`,
  `.cursor/`, …), active Codex instruction files, and noise (`node_modules`,
  `.git`, …).
- Parses every file via tree-sitter when a grammar exists.
- Uses regex extractors for the few supported formats without a tree-sitter grammar (Blade, Dart). It skips files in any other language. It has no LLM extraction fallback (the roadmap lists the fallback as deferred).
- Extracts classes, functions, methods, exports — uniformly across languages.
- Builds a structure graph: files contain symbols, classes contain methods.
- Builds a call graph: who calls whom.
- Runs Louvain community detection (NetworkX) over the call graph — deterministic and byte-reproducible across machines.
- Identifies entry-point candidates (in-degree 0 in call subgraph + heuristic filters).
- Hashes content for incremental rebuilds.

**Output**: `tree.json`, `map/files.json`, `map/symbols.json`, `features/symbol-graph.json`, conventions.

**Speed**: seconds to tens of seconds. No network — extraction is entirely tree-sitter + regex, never an LLM call.

## Layer 2 — Skill orchestration (markdown)

- The `SKILL.md` is the entry point.
- Markdown describes the workflow, not code.
- Calls the Python CLI for atomic operations (scaffolding, atomic file writes, renames).
- Dispatches subagents through the active host for operations that need judgment.
  Claude uses `Task`. Codex uses its native `explorer`, `worker`, and `default` agents.
- Reads procedure markdowns for each phase of work.

**Why markdown**: the workflow is the contract. It must be human-readable, version-controlled, and overridable.

## Layer 3 — Multi-agent council (subagents)

- Three role classes: **dev** (parameterised stack specialist), **architect** (reorganiser), **critics** (DBA / security / PM).
- Three sequential stages — `/specify` → `/plan` → `/critique` — modelled on [spec-kit](https://github.com/github/spec-kit).
- Each stage has one author, one artifact: `spec.md` (dev) → `plan.md` (dev → architect) → `concerns.md` (critics).
- Each persona runs in its own host-native subagent context.
- Mode (`light` / `standard` / `deep`) gates how many critics run and whether they cross-review.

**Why sequential**: the v0.13 parallel-essay model produced 5 perspectives that overlapped and that the chairman had to stitch. The new pipeline gives each artifact a single owner — no synthesis drift, no redundancy.

**Why subagents**: persona isolation still matters. The dev should not wear the security hat mid-paragraph. The security critic should not feel tempted to wave away threats to keep the architect happy.

## Layer 4 — Atomic Python tools (CLI)

- Tiny CLI surface for operations the skill must do atomically.
- `flow-remove` — delete a noise flow, update every JSON reference.
- `features-rename` — atomic feature folder rename.
- `section-write` — atomic write of a markdown section into the right place.
- `council-log` — append to the audit log so resumption is safe.
- `refresh-indexes` — rebuild human-readable indexes from machine-readable ones.

**Why Python here**: these operations touch multiple files transactionally. Markdown instructions that call raw `mv` or `cat >` are not atomic. The CLI is atomic.

## Layer 5 — Host guidance and Claude session hooks

dummyindex is **not a one-time setup**. Claude receives durable guidance through `.claude/CLAUDE.md`. Codex receives
the same guidance through the active project instruction file (`AGENTS.override.md`,
`AGENTS.md`, or a configured fallback). The Claude
integration additionally wires five managed hooks — `UserPromptSubmit`,
`SessionStart`, `Stop`, `PreCompact`, and `PreToolUse` — none of which rebuild
the index. Codex has a native hook surface, but dummyindex does not install
these Claude definitions
into it. Separately, Claude `/dummyindex-equip` may wire a formatter
`PostToolUse` hook, but Codex `$dummyindex-equip` is read-only.

- The **`UserPromptSubmit` hook** has two independently valid commands. The first is a profile-independent static output-shape/skill-routing contract. The second is `dummyindex context memory prompt-context`, which adds bounded recurring-skill feedback plus a safe correction or revocation from the current prompt. Each emits valid hidden `additionalContext`. Neither depends on the order of the commands.
- The **`SessionStart` hook** runs four probes. Three may emit stdout that Claude Code takes as `additionalContext`:
  - `dummyindex context plan-update` — a drift report (one line per feature whose source mtime exceeds its docs' mtime). The report is empty when nothing is stale. This path also refreshes the freshness-badge cache that the statusline reads (its only write).
  - `dummyindex context memory session-start` — replays the last saved session-memory block so the session resumes with its own handoff.
  - `dummyindex context gc signal` — a commit-throttled nudge to run `/dummyindex-gc`. The probe emits the nudge only when ≥ N commits (default 10) have landed since the last hygiene-sweep anchor. It is silent otherwise.
  - `dummyindex context memory mine` — silently refreshes the gitignored recurring-skill cache from this repo's main-thread transcript rows across local Claude profiles.
- The **`Stop` hook** runs two probes. The first is `dummyindex context memory nudge`, a handoff-checkpoint CTA that surfaces only when a session was significant and has not been saved. The second is `dummyindex context reconcile-gate`. It blocks the session's exit **once** (a `decision: block` payload) when `.context/` is stale after a substantial session. It directs the agent to run the scoped reconcile + `reconcile-stamp`. Silent (allows stop) when fresh, on the re-entrant stop, on a trivial session, or when opted out (`"auto_council": false`).
- The **`PreCompact` hook** runs `dummyindex context memory breadcrumb` — writes a deterministic breadcrumb to `now.md` before Claude Code compacts the context window.
- The **`PreToolUse` hook** (matcher `Write`) runs `dummyindex context guard-doc-write`, which classifies the `Write` target. It emits a `permissionDecision: deny` when the write would create an internal planning doc in an unmanaged location. The deny names the `.context/` home that the doc belongs in. It mutates **nothing** (pure read → classify → deny), so it upholds the "hooks never rebuild the backbone" invariant.

    It fails open: it never exits 2, so it cannot block a session. It is config-gated by `doc_guard_enabled`, and a `doc_guard_allow` glob exempts a path. Edit/MultiEdit are not matched. They require the target to pre-exist, so they can only maintain an existing doc, never create a fresh leak.
- The **running Claude session** — which knows *what* changed and *why* — updates the affected `.context/features/<id>/*.md` in place. The shell never rebuilds the backbone.
- On Claude, hooks surface drift automatically at session start. On Codex,
  `AGENTS.md` requires explicit context checks/reconciliation without claiming an
  installed hook.

The new compliance branch reuses the Headroom-derived miner's deterministic
approach, but not its tool-signature report as a runtime input. It opens only
root `*.jsonl` main transcripts in the exact encoded project directory. It then
requires every candidate row's resolved `cwd` to equal the repo.

Only external
human text rows can become correction/revocation events. The local
`.context/cache/skill-feedback.json` projection contains safe slugs and counts,
never prompt text or event metadata. Strict schema, symlink, 32-KiB, 64-entry,
eight-skill, and 1,600-character bounds separate transcript data from injected
policy. `Stop` never scans history.

Install also surfaces an **emit-only statusline nudge**. If no `statusLine` is wired (local or global), it advises you to set `"statusLine": {"type": "command", "command": "dummyindex context statusline"}`. The setting makes the prompt carry a cached `.context/` freshness badge (`[ctx ✓]` / `[ctx: N drift]`). dummyindex never *writes* the `statusLine` for you. A scalar with no sentinel cannot be un-clobbered later. So this stays a suggestion.

The SessionStart drift flow (the `UserPromptSubmit`/`Stop`/`PreCompact`/`PreToolUse` hooks are interaction contracts, bookkeeping, and guards, not shown):

```
┌─ Claude starts a session ──────────────────────────┐
│ ─► SessionStart hook                               │
│    ─► dummyindex context plan-update               │
│    ─► prints drift report (empty if nothing stale) │
│    ─► fed to the session as additionalContext      │
│ ─► the session updates features/<id>/*.md in place │
└────────────────────────────────────────────────────┘
```

**Why hooks no longer rebuild**: pre-v0.13.5, git `post-commit` + Claude `PostToolUse` + `SessionStart` all fired a shell-side `rebuild --changed`. But the council/skill never runs from a shell hook, so that deterministic-only rebuild re-scaffolded features on every edit. It clobbered `features/INDEX.json`. It also left orphan `community-N/` folders and placeholder flow narratives that the skill never came back to fill. Drift detection now lives in `dummyindex.context.drift` (mtime-based, with heuristic decay). This decay works as follows: an edit to a feature doc advances its mtime, and the drift signal goes quiet.

- Council enrichment (Layer 3) is never hook-triggered. It is manual (`/dummyindex --recouncil`) or scheduled.
- A full deterministic `rebuild --changed` is still available as a **manual** CLI command. It is no longer wired to a hook.

**Why session-driven**: the user should not have to remember to refresh. The *agent* — not a blind shell — is the right actor to reconcile prose with code. This is because the agent has the context of the change.

## Information flow

```
┌─────────────────────────────────────────────────┐
│ /dummyindex (Claude) or $dummyindex (Codex)     │
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
│   └── Host guidance; Claude hooks when selected │
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

- **Layer independence**. You can test Python without LLMs. Markdown can change without breaking Python. Personas can swap without touching either.
- **Predictable cost**. Layer 1 is free. Layer 3 is metered (modes: light/standard/deep) and runs on demand.
- **Resumability**. The audit log + content hashes mean a failed council can resume from where it stopped.
- **Portability**. The `.context/` folder is plain text + JSON. Any agent can read it.
- **Explicitly current**. Claude hooks surface staleness and guardrails. Codex
  follows `AGENTS.md` and explicit skills. Either host reconciles in-session.

## What it does NOT do

- Python stores a host-facing model choice but does not call a model provider.
  Codex uses the explicit `current` selector for the running session model.
- No vector store. No embeddings. Structured retrieval only (see [12 — Retrieval](./12-retrieval.md)).
- No daemon. The hooks are event-driven. They do not poll.
