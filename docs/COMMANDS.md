# Commands

Every dummyindex command in one place — the **slash commands** *you* run inside a
Claude Code session, and the **CLI commands** the *agent* runs as its deterministic
backbone. You don't type the CLI by hand: the skill and council invoke it to move
bytes around atomically, and everything that needs judgment stays in markdown. The
only terminal commands a human runs are the one-time `install` bootstrap
(`pip install dummyindex` + `dummyindex install`) — after that, your interface is the
slash commands below.

For the long-form description of each CLI command and all its flags, see
[guide/07-cli.md](guide/07-cli.md). This page is the quick reference.

---

## Slash commands (inside Claude Code)

Run these in a Claude Code session opened in your repo.

| Command | What it does |
|---------|--------------|
| `/dummyindex` | **Setup mode.** Ingest the repo, run the council, install the SessionStart drift hook, write the `CLAUDE.md` managed block. |
| `/dummyindex <path>` | Scope the run to a subdirectory or absolute path (e.g. `/dummyindex ./src`). |
| `/dummyindex --refresh` | Regenerate `.context/` indexes from disk (no council). |
| `/dummyindex --recouncil [feature]` | Re-run the council for the whole repo, or one feature. |
| `/dummyindex --reconfigure` | Re-run the 5-question onboarding (scope, mode, model, hook, docs). |
| `/dummyindex --reorg-docs` | Opt-in, destructive in-place documentation reorg (guarded; clean tree required). |
| `/dummyindex-plan "<feature>"` | NL feature request → a consistency-checked proposal in `.context/proposals/<slug>/`, then **auto-equips** the toolkit scoped to that proposal. |
| `/dummyindex-build` | Drive the proposal's `checklist.md` to completion through the equipped agents (verify-before-tick; warns and halts if the repo isn't equipped). |
| `/dummyindex-equip` | Standalone: (re)equip or evolve the project-tuned toolkit in `.claude/`. `/dummyindex-plan` already auto-equips. |
| `/dummyindex-remember` | Save a cross-session handoff to `.context/session-memory/`. |
| `/dummyindex-audit "<description>"` | On-demand **argue-and-audit** panel: a task-dependent set of auditors file findings, then argue them (≤3 rebuttal rounds, early stop on agreement) into a ranked `report.md` under `.context/audits/<slug>/`. Read-only — reports findings, doesn't fix. |
| `/tokens` | Token usage for the current chat — context window now + deduplicated session totals (incl. subagents). Wraps `dummyindex usage`. |

---

## CLI commands (the agent's backbone)

**The agent runs these, not you.** No LLM cost — the deterministic backbone the
skill and council invoke to move bytes around atomically. Listed here for
transparency, not as a human workflow; your interface is the slash commands above.
The one exception is the **Install** bootstrap below, which a human runs once in a
terminal to put the skill in place.

`dummyindex --help` / `dummyindex context --help` print the authoritative,
version-current list.

### Install — the human bootstrap (run once, in a terminal)

The only CLI commands a human runs by hand. Everything from the next subsection on
is agent-invoked.

| Command | What it does |
|---------|--------------|
| `dummyindex install [--scope user\|project] [--dir PATH] [--skill-only] [--no-onboarding] [--defaults]` | Register the skill; on a git repo, also build `.context/`, write `CLAUDE.md`, install the drift hook. `--skill-only` registers the skill alone. |
| `dummyindex uninstall [--scope user\|project] [--dir PATH]` | Remove the skill (and project-scope hooks). |

### Index / backbone

| Command | What it does |
|---------|--------------|
| `dummyindex ingest [path] [--root DIR] [--docs PATH]...` | Build `.context/` backbone + `CLAUDE.md` block. Alias for `context init`. |
| `dummyindex context init [path] [--root DIR] [--no-hooks] [--docs PATH]...` | Same as `ingest`. |
| `dummyindex context rebuild [--changed] [--full] [path] [--root DIR] [--docs PATH]...` | Full or incremental (`--changed`) re-index. On an enriched index `--changed` preserves the curated taxonomy + enrichment and only refreshes deterministic artefacts (reports drift); `--full` forces a destructive re-cluster. |
| `dummyindex context bootstrap [path] [--root DIR]` | Regenerate only the `CLAUDE.md` managed block. |
| `dummyindex context check [path] [--root DIR] [--auto-refresh] [--quiet] [--docs PATH]...` | Manifest-based drift check (manual). |
| `dummyindex context plan-update [path] [--root DIR]` | Drift report for the SessionStart hook (advisory; markdown to stdout). |

### Hooks

| Command | What it does |
|---------|--------------|
| `dummyindex context hooks install\|uninstall\|status [path] [--root DIR]` | Manage the three managed Claude Code hooks in `.claude/settings.json` (SessionStart drift report, Stop handoff nudge, PreCompact breadcrumb). |

### Retrieval

| Command | What it does |
|---------|--------------|
| `dummyindex context query "..." [--root DIR] [--top-k N] [--budget N] [--json]` | Ranked feature shortlist for a question (PageIndex-style, no LLM). |

### Onboarding & config

| Command | What it does |
|---------|--------------|
| `dummyindex context preflight [path] [--root DIR] [--json]` | Read-only inventory of the repo's `.claude/` setup. |
| `dummyindex context onboard [path] --model ... [--scope ...] [--mode ...] [--hook\|--no-hook] [--doc PATH]... [--defaults]` | Persist first-run council preferences to `.context/config.json`. |
| `dummyindex context config show [path] [--root DIR]` | Print `.context/config.json` (exit 1 if none yet). |

### Usage (token reporting)

A human checks tokens via the **`/tokens`** slash command (above), which wraps
`dummyindex usage`; the agent calls these directly.

| Command | What it does |
|---------|--------------|
| `dummyindex usage` | Current chat: context window now + deduplicated session totals incl. subagents. This is what `/tokens` runs. |
| `dummyindex usage chat` | Same as `dummyindex usage` (the default). |
| `dummyindex usage daily` | Per-day token totals aggregated across every project. |
| `dummyindex usage session` | Per-session token totals across every project. |
| `dummyindex usage monthly` | Per-month token totals across every project. |
| `dummyindex usage blocks` | Usage grouped into billing blocks across every project. |

### Session memory

| Command | What it does |
|---------|--------------|
| `dummyindex context memory session-start\|roll\|init [path] [--root DIR]` | Cross-session memory store under `.context/session-memory/`. |
| `dummyindex context memory nudge [--root DIR]` | Stop-hook command: prints a handoff CTA (`additionalContext`) for significant, un-saved sessions. Auto-installed. |
| `dummyindex context memory breadcrumb [--root DIR]` | PreCompact-hook command: writes a deterministic breadcrumb to `now.md`. Auto-installed. |

### Build loop

| Command | What it does |
|---------|--------------|
| `dummyindex context propose --slug S --title "..." [--root DIR] [--force]` | Scaffold + consistency-scan a proposal (`spec.md`/`plan.md`/`checklist.md`). |
| `dummyindex context equip [apply\|add-specialist\|status\|refresh\|reset\|uninstall\|patch] [...]` | Render and evolve the project-tuned toolkit in `.claude/`. `add-specialist <cap>` generates a grounded db/security/performance/docs/search specialist. |
| `dummyindex context build --proposal S (--next \| --check "<item>" \| --status) [--json]` | Deterministic state machine over a proposal's checklist. |

### Enrichment, features & council (called by the skill/council)

The council calls these to move bytes around atomically; a human never runs them by hand.

| Command | What it does |
|---------|--------------|
| `dummyindex context enrich-plan` / `enrich-apply --from-json FILE` | Emit / merge tree-abstract enrichment. |
| `dummyindex context features-rename` / `features-merge` / `flow-remove` | Atomic feature/flow restructuring. |
| `dummyindex context scaffold-feature --id ID --name "..." [--summary "..."] --file PATH...` | Atomically fold net-new files into a **new** feature (deterministic, no re-cluster). Members derived from `map/symbols.json`; rejects duplicate/`community-*` id, no file, or a file outside the repo. |
| `dummyindex context assign-files --feature ID --file PATH...` | Atomically add net-new files to an **existing** feature (members recomputed; counts/graph refreshed; enriched `spec.md`/`plan.md` preserved; already-assigned files skipped). |
| `dummyindex context unassign-files --feature ID --file PATH...` | Subtractive inverse of `assign-files`: remove files from a feature (members recomputed; enriched docs preserved). Tolerates deleted files; refuses to empty a feature (use `features-remove`). |
| `dummyindex context features-remove --feature ID [--force]` | Delete a feature whose code is gone (folder + INDEX + graph). Refuses if it still owns files on disk (live) unless `--force`. |
| `dummyindex context section-write` / `council-log` / `conventions-write` | Atomic markdown placement + council bookkeeping. |
| `dummyindex context reality-check --feature ID [--demote] [--json]` | Fact-check a feature's docs against the AST. |
| `dummyindex context dev-pick --feature ID` | Resolve which stack-specialist persona authors a feature. |
| `dummyindex context refresh-indexes [path] [--root DIR]` | Rebuild `INDEX.md` + `graph.{json,html}` from disk. |
| `dummyindex context doc-reorg guard\|list\|backup\|restore [...]` | Safety net for the destructive doc reorg. |

### Reconcile (commit-anchored update)

`.context/` tracks the commit it was last reconciled against (`meta.indexed_commit`). These keep it current **non-destructively** — no re-cluster, curated taxonomy + enrichment preserved. Procedure: `skills/council/65-reconcile.md`.

| Command | What it does |
|---------|--------------|
| `dummyindex context reconcile [path] [--root DIR] [--json]` | **Read-only** drift report since the anchor: drifted features, removed files, unassigned new files, features awaiting enrichment. `--json` for the council procedure. |
| `dummyindex context mark-enriched --feature ID` | Clear a feature's `.pending-enrichment` marker after (re-)enriching it. Set by `scaffold-feature`/`assign-files`; blocks `reconcile-stamp` while set. Idempotent. |
| `dummyindex context reconcile-stamp [path] [--root DIR] [--force]` | **Write boundary** — advance the anchor to HEAD once everything's reconciled. Refuses (exit 1) while unassigned files / awaiting-enrichment features remain (not on drift alone); `--force` overrides + warns. Off-git is a no-op. |

### Meta

| Command | What it does |
|---------|--------------|
| `dummyindex --version` / `-V` | Print the installed version. |
| `dummyindex --help` / `-h`, `dummyindex context --help` | Authoritative command list with flags. |
