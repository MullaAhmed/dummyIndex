# 08 — Skill orchestration

Markdown is the workflow. Python is the toolbox. Subagents are the workforce.

## File layout under the package

```
dummyindex/skills/
├── SKILL.md                       # the entry point — the conductor
├── council/                       # procedure markdowns for deep enrichment
│   ├── 00-overview.md             # the council pattern; when to invoke
│   ├── 10-structural-review.md    # architect's regrouping pre-stage
│   ├── 20-stage1-perspectives.md  # parallel persona dispatch
│   ├── 30-stage2-cross-review.md  # anonymized peer review
│   ├── 40-stage3-synthesis.md     # chairman writes canonical docs
│   ├── 50-flow-narrative.md       # senior dev filters + narrates flows
│   ├── filter-trivial.md          # skip rules
│   └── resume.md                  # how to pick up where we left off
├── retrieval/                     # how the agent walks .context/
│   ├── 00-overview.md             # PageIndex-style tree search
│   ├── 10-feature-lookup.md       # INDEX.json → feature drill-down
│   ├── 20-symbol-lookup.md        # map/symbols.json walks
│   └── 30-flow-trace.md           # following a flow narrative to source
└── agents/                        # persona prompt templates
    ├── architect.md
    ├── senior-developer.md
    ├── database-engineer.md
    ├── security-analyst.md
    ├── product-manager.md
    └── chairman.md
```

## How `SKILL.md` works

Triggered when the user types `/dummyindex` or `/dummyindex <path>`.

The skill body is short. It's a conductor, not a worker.

Pseudocode of the skill's logic:

```
1. Resolve scope and root (per the scope-vs-root rules in CLI).

2. Phase 1 — deterministic backbone:
     Run: `dummyindex ingest <path>`
     Output expected: .context/ folder + 3-line CLAUDE.md block + hooks installed.
     Verify INDEX.json and features/INDEX.json exist before continuing.

3. Phase 2 — structural review:
     Read features/INDEX.json.
     Dispatch ONE architect subagent (via Task tool).
       Persona: agents/architect.md
       Procedure: council/10-structural-review.md
       Output: a regrouping plan (merges/splits as features-rename calls).
     Apply each rename.

4. Phase 3 — per-feature council:
     For each non-trivial feature in INDEX.json:
       If `_council-log.json` shows fully complete + source unchanged: skip.
       Else dispatch:
         a. Stage 1 — 5 personas in parallel (Task subagents).
         b. Stage 2 — each persona reviews the 4 others (parallel).
         c. Stage 3 — chairman synthesizes.
       Each stage logs to council-log via CLI.

5. Phase 4 — flow refinement:
     For each enriched feature, dispatch senior-developer to:
       - Discard noise flows: `dummyindex context flow-remove --feature X --flow Y`
       - Narrate kept flows: write to flows/<id>.md

6. Phase 5 — reconcile:
     Run: `dummyindex context refresh-indexes <path>`

7. Phase 6 — report:
     Tell the user: counts, mode used, cost estimate, where to start reading.
```

## How retrieval works (the always-on path)

The SKILL.md described above runs only when explicitly invoked. The **always-on retrieval** is different: it's instructions the agent follows in **every session**, encoded in `.context/HOW_TO_USE.md` and `.context/features/HOW_TO_NAVIGATE.md` (written into the repo).

```
Every Claude Code session in the repo
   │
   ▼ reads <repo>/CLAUDE.md (3-line managed block)
   │
   ▼ which points at .context/HOW_TO_USE.md
   │
   ▼ which tells the agent the PageIndex-style tree-walk procedure:
       1. Start at features/INDEX.json.
       2. Reason over the TOC. Pick relevant features.
       3. Drill into feature.json + README.md.
       4. Drill into domain section (architecture/implementation/...) as needed.
       5. Drill into flows/<id>.md for sequence narratives.
       6. Resolve symbols via map/symbols.json (path:range).
       7. Read source files cited by the docs.
```

The retrieval procedure markdowns under `skills/retrieval/` are the source of truth for what gets copied into `.context/HOW_TO_USE.md` at ingest time. Updating them and re-running `dummyindex context bootstrap` propagates the new guidance into the repo.

## Slash-command surface (inspired by KARIMO)

`/dummyindex` is the primary entry point but the skill supports subcommands:

- `/dummyindex` — full first-time ingest + council (deep mode default).
- `/dummyindex --scaffold-only` — backbone only, skip council.
- `/dummyindex --recouncil [feature_id]` — re-run council (one feature or all).
- `/dummyindex --refresh` — equivalent to `dummyindex context refresh-indexes`.
- `/dummyindex --query "..."` — PageIndex tree search (roadmap v0.9).
- `/dummyindex --status` — show staleness, hook health, last council run.

## Why markdown for orchestration

- Workflows change. Code is brittle for workflow changes.
- Markdown is human-readable, version-controlled, overridable.
- The skill IS the spec. The spec IS the skill. No drift.
- A user can fork a procedure markdown without recompiling anything.

## Why Python for the CLI

- Atomic file operations need transactions.
- Schema validation needs structured types.
- Walking the AST needs a real parser.
- The CLI is the **stable kernel**; markdown evolves on top.

## How agents are dispatched

The skill uses Claude Code's `Task` tool with `subagent_type: "general-purpose"`.

Per dispatch:
- The skill **reads the persona markdown** (`agents/architect.md`).
- The skill **substitutes context** (the feature's JSON, the source file list, the cross-perspectives if stage 2/3).
- The skill **passes the rendered prompt** to the Task tool.
- The subagent runs in its own context window.
- The subagent **writes back** using `Write` or `dummyindex context section-write`.
- The subagent **logs completion** via `dummyindex context council-log`.

## Why subagents instead of inline calls

- Persona isolation. The architect should not be tempted to wear the security hat mid-paragraph.
- Context window economics. Five 30K-token contexts in parallel beat one 150K-token context sequentially.
- Resumability. Each subagent's output is durable before the next starts.
- Auditability. Each subagent's full prompt + response is recoverable from the audit log.

## What lives where, restated

| Concern | Where |
|---|---|
| "What command runs the AST?" | Python (`dummyindex/pipeline/extract.py`) |
| "What does an architect agent look at?" | Markdown (`skills/agents/architect.md`) |
| "How do five agents coordinate?" | Markdown procedure (`skills/council/*.md`) |
| "How does the agent walk the tree?" | Markdown (`skills/retrieval/*.md` → `.context/HOW_TO_USE.md`) |
| "How does a feature folder get renamed atomically?" | Python CLI (`features-rename`) |
| "When do we skip stage 2?" | Markdown (the procedure decides) |
| "What confidence value is on a node?" | Python (the JSON schema enforces it) |

## Skill markdown style

- Numbered steps for procedural sections.
- Tables for decision matrices.
- Code blocks ONLY for CLI invocations agents will actually run.
- No prose explaining what the user will see — that's redundant with `HOW_TO_USE.md`.
- Each procedure markdown stays under 200 lines.
