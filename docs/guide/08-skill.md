# 08 — Skill orchestration

Markdown is the workflow. Python is the toolbox. Subagents are the workforce.

## File layout under the package

```
dummyindex/skills/
├── skill.md                       # the entry point — the conductor (installed as SKILL.md)
├── council/                       # procedure markdowns for the pipeline
│   ├── 00-overview.md             # the pipeline pattern; when to invoke
│   ├── 05-onboarding.md           # first-run host-aware setup
│   ├── 10-structural-review.md    # architect's regrouping pre-stage
│   ├── 15-conventions.md          # phase 1.5 conventions fan-out
│   ├── 18-filter-trivial.md       # skip rules for trivial features
│   ├── 19-resume.md               # how to pick up where we left off
│   ├── 20-specify.md              # stage 1 — dev drafts spec.md + plan.md
│   ├── 22-parallel-dispatch.md    # fan features/stages out to parallel Tasks
│   ├── 30-plan.md                 # stage 2 — architect reorganises plan.md
│   ├── 40-critique.md             # stage 3 — critics write concerns.md (mode-gated)
│   ├── 45-reality-check.md        # phase 3.5 fact-check vs the AST
│   ├── 50-flow-narrative.md       # dev filters + narrates flows
│   ├── 52-tree-enrich.md          # fill tree.json node abstracts (retrieval)
│   ├── 55-context7.md / 56-github.md  # optional MCP protocols
│   ├── 60-doc-reorg.md            # destructive --reorg-docs procedure
│   └── 65-reconcile.md            # fold new code back into .context/ (build loop-closer)
├── retrieval/                     # how the agent walks .context/
│   ├── 00-overview.md             # PageIndex-style tree search
│   ├── 10-feature-lookup.md       # INDEX.json → feature drill-down
│   ├── 20-symbol-lookup.md        # map/symbols.json walks
│   └── 30-flow-trace.md           # following a flow narrative to source
├── agents/                        # persona prompt templates
│   ├── architect.md               # reorganiser (also runs the structural-review pre-stage)
│   ├── dev.md                     # parameterised stack specialist (slots: framework, Context7 docs)
│   ├── critic-database.md
│   ├── critic-security.md
│   └── critic-product.md
├── commands/                      # bundled slash commands (/tokens)
├── statusline/                    # statusline.{sh,ps1} — the [ctx ✓] freshness badge
├── memory/SKILL.md                # sibling skill: dummyindex-remember
├── plan/SKILL.md                  # sibling skill: dummyindex-plan
├── build/SKILL.md                 # sibling skill: dummyindex-build
├── equip/                         # sibling skill: dummyindex-equip
│   ├── SKILL.md
│   └── templates/                 # *.tmpl agent/skill render templates
├── audit/                         # sibling skill: dummyindex-audit
│   ├── SKILL.md
│   └── agents/                    # auditor persona catalog
├── update/SKILL.md                # sibling skill: dummyindex-update
└── gc/SKILL.md                    # sibling skill: dummyindex-gc
```

## How `SKILL.md` works

Triggered by `/dummyindex` on Claude Code or `$dummyindex` on Codex, optionally
with a path.

The skill body is short. It is a conductor, not a worker.

Pseudocode of the skill's logic:

```
1. Resolve scope and root (per the scope-vs-root rules in CLI).

2. Phase 1 — deterministic backbone:
     Run: `dummyindex ingest <path> --platform <active-host>` (forward `--docs`).
     Output expected: .context/ plus host guidance. Claude also gets managed
     hooks; Codex gets its active project instruction file
     (AGENTS.override.md, AGENTS.md, or a configured fallback) and no
     dummyindex-installed hook.
     Verify INDEX.json and features/INDEX.json exist before continuing.
     Phase 1 also writes `source-docs/INDEX.{json,md}` — the catalog of
     existing prose docs with per-doc confidence + broken-references.

3. Phase 2 — structural review:
     Read features/INDEX.json.
     Dispatch ONE architect through the active host's subagent mechanism.
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

The `SKILL.md` described above runs only when explicitly invoked. The **always-on retrieval** is different. It is a set of instructions the agent follows in **every session**. The instructions are encoded in `.context/HOW_TO_USE.md` and `.context/features/HOW_TO_NAVIGATE.md` (written into the repo).

```
Every supported host session in the repo
   │
   ▼ Claude reads .claude/CLAUDE.md; Codex reads its active project instruction file
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

The retrieval procedure markdowns under `skills/retrieval/` are the source of truth for what ingest copies into `.context/HOW_TO_USE.md`. Update them and re-run `dummyindex ingest` (or `dummyindex context rebuild`). This propagates the new guidance into the repo. The ingest/rebuild runner writes `HOW_TO_USE.md`. `bootstrap` does not write it. `bootstrap` regenerates only the selected host guidance block.

## Host command surface (inspired by KARIMO)

`/dummyindex` is the Claude Code entry point. `$dummyindex` is the Codex
equivalent. The same arguments work on both:

- `/dummyindex` — full first-time ingest + pipeline. Standard mode is the default. The first run also triggers onboarding (v0.14).
- `/dummyindex --mode light|standard|deep` — override the council mode for this run.
- `/dummyindex --scaffold-only` — backbone only, skip the pipeline.
- `/dummyindex --recouncil [feature_id]` — re-run the pipeline (one feature or all).
- `/dummyindex --reconfigure` — re-run the onboarding questions (v0.14).
- `/dummyindex --refresh` — equivalent to `dummyindex context refresh-indexes`.
- `/dummyindex --status` — show the read-only index, drift, version, depth,
  equipment, proposal, and memory overview.

The PageIndex tree search itself is the standalone CLI verb `dummyindex context query "..."`. It uses no LLM. The plan skill reuses it for grounding.

## Sibling skills

Seven sibling skills ship inside `dummyindex/skills/`. They install under
`~/.claude/skills/` for Claude Code or `~/.agents/skills/` for Codex (alongside
the primary skill, that is the eight-command family). In the table below,
replace the leading `/` with `$` for Codex.

| Skill | Package directory | What it orchestrates |
|---|---|---|
| `/dummyindex-plan` | `dummyindex/skills/plan/` | NL request → grounded proposal + light critique. Claude then auto-equips; Codex performs no equip discovery/install/apply. |
| `/dummyindex-equip` | `dummyindex/skills/equip/` | Claude lifecycle-manages a project toolkit in `.claude/`; Codex emits a read-only route map over available native agents/skills and writes no equipment. |
| `/dummyindex-build` | `dummyindex/skills/build/` | Drives the checklist wave-by-wave with verify-before-tick, then reconciles. Claude requires equipment and may learn via `equip patch`; Codex needs no manifest and uses native built-ins. |
| `/dummyindex-remember` | `dummyindex/skills/memory/` | Captures a first-person handoff summary → `dummyindex context memory roll` → `.context/session-memory/` tier rotation |
| `/dummyindex-audit` | `dummyindex/skills/audit/` | `dummyindex context audit` scaffold → task-dependent auditor panel argues findings (≤3 rounds) → ranked `report.md` under `.context/audits/<slug>/` |
| `/dummyindex-update` | `dummyindex/skills/update/` | Resolves the latest GitHub release tag → force-reinstalls the CLI via the detected method (uv tool / pipx / pip) → re-runs `dummyindex install` for a non-destructive refresh → verifies the CLI, skill family, and repo wiring all moved |
| `/dummyindex-gc` | `dummyindex/skills/gc/` | `dummyindex context gc status` (read-only sweep + commit-throttle state) → parallel council walks `.context/` to judge each candidate keep / stale / superseded / dead → user confirms → deletes decisively: docs via `gc delete --kind proposal\|audit --yes`, trivially-dead private code via implementer+tester (only if the suite stays green), broader dead code routed to a new proposal. Never archives, never removes anything unconfirmed |

Each sibling skill is markdown-first. It follows the same conductor pattern. Python does the deterministic moves. The skill dispatches agents for everything that requires judgment.

## Why markdown for orchestration

- Workflows change. Code is brittle for workflow changes.
- Markdown is human-readable, version-controlled, overridable.
- The skill IS the spec. The spec IS the skill. No drift.
- A user can fork a procedure markdown without recompiling anything.

## Why Python for the CLI

- Atomic file operations need transactions.
- Schema validation needs structured types.
- An AST walk needs a real parser.
- The CLI is the **stable kernel**. Markdown evolves on top.

## How agents are dispatched

On Claude Code the skill uses the `Task` tool and named specialist types. The
installed Codex copy maps read-only work to built-in `explorer`. It maps
implementation and artifact authoring to `worker`, and it maps
coordination/unmatched work to `default`. It also inlines the same persona
mandate. That mapping needs no `.claude/agents/` or equipment manifest.

Per dispatch:
- The skill **reads the persona markdown** (`agents/dev.md`, `agents/architect.md`, or a `agents/critic-*.md`).
- The skill **substitutes context**: the dev (stage 1) gets the feature's JSON + source file list. The architect (stage 2) gets the dev's draft `plan.md`, and the critics (stage 3) get the finalised `plan.md`. The skill also substitutes `features/<id>/docs.md` when it exists. For the dev, the skill fills the `{{framework}}` slot from stack detection. The `{{framework_docs}}` slot carries verbatim Context7 excerpts when a `*context7*` MCP server is exposed. The lookup protocol lives in `council/55-context7.md`, and a missing server is not a failure.
- The skill **includes the doc-evidence directive** verbatim — "treat catalogued docs as hypotheses, verify against `map/symbols.json` before quoting. Quote `high`/`medium` only, never `low`. Flag any code-vs-doc conflict into the council audit log."
- The skill passes the rendered prompt to the active host's subagent mechanism.
- The subagent runs in its own context window.
- The subagent **writes back** with the active host's edit mechanism or
  `dummyindex context section-write`.
- The subagent **logs completion** via `dummyindex context council-log`.

## Why subagents instead of inline calls

- Persona isolation. The dev should not wear the security hat mid-paragraph. The security critic should not soften a threat to please the architect.
- Context window economics. Each stage gets a focused ~30K-token window scoped to its inputs. One bloated context would carry every persona's concerns at once.
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
- Code blocks ONLY for CLI invocations agents will run.
- No prose that explains what the user will see. That is redundant with `HOW_TO_USE.md`.
- Each procedure markdown stays under 200 lines.
