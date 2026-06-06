# 08 — Skill orchestration

Markdown is the workflow. Python is the toolbox. Subagents are the workforce.

## File layout under the package

```
dummyindex/skills/
├── SKILL.md                       # the entry point — the conductor
├── council/                       # procedure markdowns for the pipeline
│   ├── 00-overview.md             # the pipeline pattern; when to invoke
│   ├── 10-structural-review.md    # architect's regrouping pre-stage
│   ├── 18-filter-trivial.md       # skip rules for trivial features
│   ├── 19-resume.md               # how to pick up where we left off
│   ├── 20-specify.md              # stage 1 — dev drafts spec.md + plan.md
│   ├── 30-plan.md                 # stage 2 — architect reorganises plan.md
│   ├── 40-critique.md             # stage 3 — critics write concerns.md (mode-gated)
│   ├── 50-flow-narrative.md       # dev filters + narrates flows
│   └── 52-tree-enrich.md          # fill tree.json node abstracts (retrieval)
├── retrieval/                     # how the agent walks .context/
│   ├── 00-overview.md             # PageIndex-style tree search
│   ├── 10-feature-lookup.md       # INDEX.json → feature drill-down
│   ├── 20-symbol-lookup.md        # map/symbols.json walks
│   └── 30-flow-trace.md           # following a flow narrative to source
└── agents/                        # persona prompt templates
    ├── architect.md               # reorganiser (also runs the structural-review pre-stage)
    ├── dev.md                     # parameterised stack specialist (slots: framework, Context7 docs)
    ├── critic-database.md
    ├── critic-security.md
    └── critic-product.md
```

## How `SKILL.md` works

Triggered when the user types `/dummyindex` or `/dummyindex <path>`.

The skill body is short. It's a conductor, not a worker.

Pseudocode of the skill's logic:

```
1. Resolve scope and root (per the scope-vs-root rules in CLI).

2. Phase 1 — deterministic backbone:
     Run: `dummyindex ingest <path>` (forward `--docs` for any external doc roots).
     Output expected: .context/ folder + 3-line CLAUDE.md block + hooks installed.
     Verify INDEX.json and features/INDEX.json exist before continuing.
     Phase 1 also writes `source-docs/INDEX.{json,md}` — the catalog of
     existing prose docs with per-doc confidence + broken-references.

3. Phase 2 — structural review:
     Read features/INDEX.json.
     Dispatch ONE architect subagent (via Task tool).
       Persona: agents/architect.md
       Procedure: council/10-structural-review.md
       Output: a regrouping plan (merges/splits as features-rename calls).
     Apply each rename.

4. Phase 3 — per-feature pipeline:
     For each non-trivial feature in INDEX.json:
       If `_council-log.json` shows fully complete + source unchanged: skip.
       Else dispatch sequentially:
         a. Stage 1 — /specify: pick stack persona from feature signals, dispatch
            one dev subagent. Writes spec.md + plan.md.
         b. Stage 2 — /plan: dispatch architect to reorganise plan.md (in place).
            Writes council/02-architect-notes.md alongside.
         c. Stage 3 — /critique (mode-gated):
            - light:    skip.
            - standard: pick one critic by relevance (DBA/security/PM), file findings.
            - deep:     all relevant critics + cross-review, then merge into concerns.md.
       Each stage logs to council-log via CLI.

5. Phase 4 — flow refinement:
     For each enriched feature, dispatch the same dev persona to:
       - Discard noise flows: `dummyindex context flow-remove --feature X --flow Y`
       - Narrate kept flows: write to flows/<id>.md

6. Phase 4.5 — tree enrichment (mode-gated; skip in light):
     Fill tree.json node abstracts (EXTRACTED stubs → INFERRED) so future-session
     retrieval over the tree reads real prose: enrich-plan → dispatch subagents
     per scope → enrich-apply. See council/52-tree-enrich.md.

7. Phase 5 — reconcile:
     Run: `dummyindex context refresh-indexes <path>`

8. Phase 6 — report:
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
       3. Drill into feature.json + spec.md (the WHAT).
       4. Drill into plan.md (HOW) or concerns.md (RISKS) as the task needs.
       5. Drill into flows/<id>.md for sequence narratives.
       6. Resolve symbols via map/symbols.json (path:range).
       7. Read source files cited by the docs.
```

The retrieval procedure markdowns under `skills/retrieval/` are the source of truth for what gets copied into `.context/HOW_TO_USE.md` at ingest time. Updating them and re-running `dummyindex context bootstrap` propagates the new guidance into the repo.

## Slash-command surface (inspired by KARIMO)

`/dummyindex` is the primary entry point but the skill supports subcommands:

- `/dummyindex` — full first-time ingest + pipeline (standard mode default; first run also triggers onboarding, v0.14).
- `/dummyindex --mode light|standard|deep` — override the council mode for this run.
- `/dummyindex --scaffold-only` — backbone only, skip the pipeline.
- `/dummyindex --recouncil [feature_id]` — re-run the pipeline (one feature or all).
- `/dummyindex --reconfigure` — re-run the onboarding questions (v0.14).
- `/dummyindex --refresh` — equivalent to `dummyindex context refresh-indexes`.
- `/dummyindex --query "..."` — PageIndex tree search (shipped v0.12).
- `/dummyindex --status` — show drift, hook health, last council run.

## Sibling skills (v0.15)

Four top-level skill directories ship beside `dummyindex/skills/`, each installed as its own `~/.claude/skills/<name>/` entry:

| Skill | Directory | What it orchestrates |
|---|---|---|
| `/dummyindex-plan` | `dummyindex/skills/dummyindex-plan/` | NL feature request → `dummyindex context propose` → consistency-checked `.context/proposals/<slug>/` |
| `/dummyindex-equip` | `dummyindex/skills/dummyindex-equip/` | `dummyindex context equip` + lifecycle verbs (`status|refresh|reset|uninstall|patch`) → project-tuned toolkit in `.claude/` |
| `/dummyindex-build` | `dummyindex/skills/dummyindex-build/` | `dummyindex context build` → drives proposal checklist, dispatches equipped agents, post-build `equip patch`, then `rebuild --changed` |
| `/dummyindex-remember` | `dummyindex/skills/dummyindex-remember/` | Captures a first-person handoff summary → `dummyindex context memory roll` → `.context/session-memory/` tier rotation |

Each sibling skill is markdown-first and follows the same conductor pattern: Python does the deterministic moves; the skill dispatches agents for everything requiring judgment.

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

The skill uses Claude Code's `Task` tool. Each persona maps to a specialist `subagent_type` (the dev picker resolves to `Backend Architect` / `Frontend Developer` / `Data Engineer` / `AI Engineer` / `Senior Developer`; critics to `Data Engineer` / `Security Engineer` / `general-purpose`).

Per dispatch:
- The skill **reads the persona markdown** (`agents/dev.md`, `agents/architect.md`, or a `agents/critic-*.md`).
- The skill **substitutes context**: the feature's JSON + source file list for the dev (stage 1); the dev's draft `plan.md` for the architect (stage 2); the finalised `plan.md` for the critics (stage 3); `features/<id>/docs.md` when it exists. For the dev, the `{{framework}}` slot is filled from stack detection (and Context7 docs once v0.15 lands).
- The skill **includes the doc-evidence directive** verbatim — "treat catalogued docs as hypotheses, verify against `map/symbols.json` before quoting; quote `high`/`medium` only, never `low`; flag any code-vs-doc conflict into the council audit log."
- The skill **passes the rendered prompt** to the Task tool.
- The subagent runs in its own context window.
- The subagent **writes back** using `Write` or `dummyindex context section-write`.
- The subagent **logs completion** via `dummyindex context council-log`.

## Why subagents instead of inline calls

- Persona isolation. The dev shouldn't wear the security hat mid-paragraph; the security critic shouldn't soften a threat to please the architect.
- Context window economics. Each stage gets a focused ~30K-token window scoped to its inputs, instead of one bloated context carrying every persona's concerns at once.
- Resumability. Each stage's output is durable before the next starts — the pipeline resumes from `_council-log.json`.
- Auditability. Each subagent's full prompt + response is recoverable from the audit log.

## What lives where, restated

| Concern | Where |
|---|---|
| "What command runs the AST?" | Python (`dummyindex/pipeline/extract.py`) |
| "What does the dev agent look at?" | Markdown (`skills/agents/dev.md`) |
| "How do the pipeline stages coordinate?" | Markdown procedure (`skills/council/*.md`) |
| "How does the agent walk the tree?" | Markdown (`skills/retrieval/*.md` → `.context/HOW_TO_USE.md`) |
| "How does a feature folder get renamed atomically?" | Python CLI (`features-rename`) |
| "When do we skip `/critique`?" | Markdown (the mode gate decides) |
| "What confidence value is on a node?" | Python (the JSON schema enforces it) |

## Skill markdown style

- Numbered steps for procedural sections.
- Tables for decision matrices.
- Code blocks ONLY for CLI invocations agents will actually run.
- No prose explaining what the user will see — that's redundant with `HOW_TO_USE.md`.
- Each procedure markdown stays under 200 lines.
