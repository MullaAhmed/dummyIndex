# Commands

Every dummyindex command in one place — **slash commands** in Claude Code,
equivalent **`$skill-name` mentions** in Codex, and the CLI commands the active
agent runs as its deterministic backbone. The only terminal commands a human
runs are the one-time install bootstrap.

For the long-form description of each CLI command and all its flags, see
[guide/07-cli.md](guide/07-cli.md). This page is the quick reference.

---

## Agent commands

Use the Claude spelling in Claude Code and the Codex spelling in Codex. Codex
also lists them through `/skills`.

| Claude Code | Codex | What it does |
|---|---|---|
| `/dummyindex` | `$dummyindex` | **Setup mode.** Ingest the repo, run the council, and write the host guidance. Claude also installs managed hooks. |
| `/dummyindex <path>` | `$dummyindex <path>` | Scope the run to a subdirectory or absolute path. |
| `/dummyindex --refresh` | `$dummyindex --refresh` | Regenerate `.context/` indexes from disk (no council). |
| `/dummyindex --recouncil [feature]` | `$dummyindex --recouncil [feature]` | Re-run the council for the whole repo, or one feature. |
| `/dummyindex --reconfigure` | `$dummyindex --reconfigure` | Re-run onboarding. Codex-only uses `current` with no Claude hook; `both` uses `current` and retains or asks for Claude's hook preference. |
| `/dummyindex --reorg-docs` | `$dummyindex --reorg-docs` | Opt-in, destructive in-place documentation reorg (guarded; clean tree required). |
| `/dummyindex-plan "<feature>"` | `$dummyindex-plan "<feature>"` | NL feature request → consistency-checked proposal. Claude auto-equips; Codex does not run equip or create `.claude/**`. |
| `/dummyindex-build` | `$dummyindex-build` | Drive the proposal checklist wave-by-wave. Claude requires its equipment manifest; Codex proceeds without one through native built-ins. |
| `/dummyindex-equip` | `$dummyindex-equip` | Claude renders/evolves `.claude/` equipment and approved plugins. Codex performs a read-only native routing report and writes no equipment. |
| `/dummyindex-remember` | `$dummyindex-remember` | Save a cross-session handoff to `.context/session-memory/`. |
| `/dummyindex-audit "<description>"` | `$dummyindex-audit "<description>"` | Run an adversarial audit panel and write a ranked report. |
| `/dummyindex-gc` | `$dummyindex-gc` | Sweep stale generated proposals/audits with confirmation. |
| `/dummyindex-update` | `$dummyindex-update` | Update the CLI, selected host skills, and repo wiring non-destructively. |
| `/tokens` | `/status` or `/usage` | Host-native token information. `dummyindex usage` parses Claude transcripts, so it is intentionally not exposed as a Codex skill. |

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
| `dummyindex install [--platform claude\|codex\|both] [--scope user\|project] [--dir PATH] [--skill-only] [--no-onboarding] [--defaults] [--no-superpowers]` | Register the selected host skill family; on a git repo, also build `.context/` and write host guidance. Defaults: Claude=`sonnet-4.6`/hooks on; Codex=`current`/hooks off; both=`current`/Claude hooks on. `--no-superpowers` disables Claude's default plugin wiring. |
| `dummyindex uninstall [--platform claude\|codex\|both] [--scope user\|project] [--dir PATH]` | Remove the selected host skill family and Claude command aliases when selected. Project-scope Codex removes that project's managed block; user-scope Codex removes global guidance plus only a current/`--dir` project block stamped as its auto-init. Claude guidance/hooks remain intact. |

### Index / backbone

| Command | What it does |
|---------|--------------|
| `dummyindex ingest [path] [--root DIR] [--platform claude\|codex\|both] [--no-hooks] [--no-superpowers] [--force] [--depth light\|standard\|deep] [--docs PATH]...` | Build `.context/` plus selected host guidance. Alias for `context init`; `--force` permits replacing a curated index. |
| `dummyindex context init [path] [--root DIR] [--platform claude\|codex\|both] [--no-hooks] [--no-superpowers] [--force] [--depth light\|standard\|deep] [--docs PATH]...` | Same as `ingest`. |
| `dummyindex context rebuild [--changed] [--full] [path] [--root DIR] [--docs PATH]...` | Full or incremental (`--changed`) re-index. On an enriched index `--changed` preserves the curated taxonomy + enrichment and only refreshes deterministic artefacts (reports drift); `--full` forces a destructive re-cluster. |
| `dummyindex context bootstrap [path] [--root DIR] [--platform claude\|codex\|both]` | Regenerate the selected host guidance: Claude's managed `CLAUDE.md` block, the active Codex project instruction file, or both (default: Claude). |
| `dummyindex status [path] [--root DIR] [--json]` | Read-only overview (also `dummyindex context status`): index present + enriched?, `.context` stamp vs CLI version, commit-anchored drift one-liner, equipment item count + schema version, proposal done/total, session-memory presence. Never initialized → exit 0, writes nothing. |
| `dummyindex context statusline [path] [--root DIR]` | Print the cached `.context/` freshness badge (`[ctx ✓]` / `[ctx: N drift]`) for a shell `statusLine`. Reads the pre-computed badge cache (written by the SessionStart `plan-update` path); never recomputes. Missing/malformed cache or any error → empty stdout, exit 0. |
| `dummyindex context check [path] [--root DIR] [--auto-refresh] [--quiet] [--docs PATH]... [--versions]` | Manifest-based drift check (manual). `--versions` separately compares CLI/context with every repo/user × Claude/Codex skill stamp, reports PATH shadowing, and always exits 0. |
| `dummyindex context plan-update [path] [--root DIR]` | Drift report for the SessionStart hook (advisory; markdown to stdout). |
| `dummyindex context reconcile-gate [path] [--root DIR]` | Stop-hook gate (reads hook JSON on stdin). Emits a `decision: block` that blocks session exit **once** when `.context/` is stale after a substantial session, directing the agent to run the scoped council/reconcile + `reconcile-stamp`. Drift-only, scoped, block-once (`stop_hook_active`); silent when fresh / trivial / opted out. **The hook never writes or stamps `.context/`** — the agent does. |

### Hooks

| Command | What it does |
|---------|--------------|
| `dummyindex context hooks install\|uninstall\|status [path] [--root DIR] [--global]` | Manage the managed Claude Code hooks in `.claude/settings.json`: SessionStart drift/memory/GC signal, Stop handoff nudge **+ reconcile gate**, PreCompact breadcrumb, and PreToolUse `Write` doc guard. `--global` targets `~/.claude/settings.json` so they fire in every repo; a repo's own `--local` install overrides the global one. |
| `dummyindex context hooks defer-check [path] [--root DIR]` | Exit-code probe used by the global hook guard: exit 0 (defer) when the repo has its own `--local` dummyindex hooks, else exit 1. Prints nothing. |

**Reconcile-gate opt-out:** set `"auto_council": false` in `.context/config.json` to disable the gate for a repo even when the global hooks are installed (opt-out, not opt-in — absent file/key means enabled).

### Retrieval

| Command | What it does |
|---------|--------------|
| `dummyindex context query "..." [--root DIR] [--top-k N] [--budget N] [--json]` | Ranked feature shortlist for a question (PageIndex-style, no LLM). |
| `dummyindex context debt [path] [--root DIR] [--write] [--json]` | Technical-debt ledger over the repo's Python source: a per-file, path-sorted list of `TODO`/`FIXME`/`HACK`/`DEBT` markers, each tagged with its upgrade trigger. `--write` persists `.context/debt.md`; `--json` for machine output. Deterministic, no LLM. |

### Onboarding & config

| Command | What it does |
|---------|--------------|
| `dummyindex context preflight [path] [--root DIR] [--json]` | Read-only inventory of the repo's `.claude/` setup; actionable on Claude and informational during a Codex-only run. |
| `dummyindex context onboard [path] --model ... [--scope ...] [--mode ...] [--hook\|--no-hook] [--doc PATH]... [--platform claude\|codex\|both] [--defaults]` | Persist first-run council preferences. `--defaults` uses the explicit platform or infers managed guidance (Claude fallback when absent). Codex-only persists `current`/hooks off; Claude-only uses `sonnet-4.6`/hooks on; `both` uses `current`/Claude hooks on. The host workflow then runs `hooks install` or `hooks uninstall` so Claude's live managed-hook state matches that preference. |
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
| `dummyindex context memory nudge [--root DIR]` | Claude Stop-hook command: prints a handoff CTA (`additionalContext`) for significant, un-saved sessions. Auto-installed on Claude only. |
| `dummyindex context memory breadcrumb [--root DIR]` | Claude PreCompact-hook command: writes a deterministic breadcrumb to `now.md`. Auto-installed on Claude only. |

### Build loop

The `context equip ...` CLI family below manages Claude equipment. The Claude
skills invoke it; the Codex plan/build/equip skills deliberately do not. Codex
uses already available native skills/custom agents plus built-in
`explorer`/`worker`/`default`, and needs no `.context/equipment.json`.

| Command | What it does |
|---------|--------------|
| `dummyindex context propose --slug S --title "..." [--root DIR] [--force]` | Scaffold + consistency-scan a proposal (`spec.md`/`plan.md`/`checklist.md`). |
| `dummyindex context equip [apply\|add-specialist\|status\|refresh\|reset\|uninstall\|patch] [...]` | Render and evolve the project-tuned toolkit in `.claude/`. `add-specialist <cap>` generates a grounded db/security/performance/docs/search specialist. |
| `dummyindex context equip discover [QUERY] [--repo OWNER/NAME] [--json]` | Plugin manager: search the marketplaces + GitHub and print a ranked **dry-run** plan with each candidate's blast radius (auto-matches detected capabilities when no QUERY). |
| `dummyindex context equip install <plugin>@<marketplace> [--yes] [--scope project\|local\|user] [--repo OWNER/NAME] [--usage-doc PATH\|--skip-usage-doc]` | Wire an approved plugin natively into `.claude/settings.json` (`extraKnownMarketplaces` + `enabledPlugins`), **or vendor a collection skill** into `.claude/skills/`; records it in `equipment.json`. `--yes` required to enable an untrusted, code-running plugin. **Exactly one** of `--usage-doc PATH` / `--skip-usage-doc` is mandatory (else exit 2) — the usage playbook. |
| `dummyindex context equip verify <plugin>@<marketplace> [--root DIR]` | Read-only supply-chain drift check: re-resolve an installed plugin against upstream and report whether its pinned sha still matches. |
| `dummyindex context equip remove NAME [--root DIR] [--delete-file] [--keep-wiring]` | Drop one item from the manifest (and its `settings.json` wiring); `--delete-file` also removes a PRISTINE generated/vendored file. |
| `dummyindex context equip eval <tool> --observations FILE [--suite FILE] [--run-label L] [--force] [--json]` | Score a tool's trigger-description suite against observed firing decisions → precision/recall/accuracy; writes `.context/equipment-evals/<tool>.result.json` and lists each misfire. |
| `dummyindex context equip benchmark <tool> [--root DIR] [--json]` | Aggregate repeated eval runs → mean accuracy + variance + flaky cases (a reporter: zero runs warns and exits 0, writing nothing). |
| `dummyindex context build --proposal S (--next-wave \| --next \| --check "<item>" \| --skip "<item>" --reason "<why>" \| --status) [--json]` | Deterministic state machine over a proposal's checklist; `--next-wave` emits the whole parallel-dispatch frontier (`## Wave N` group); `--skip` closes an item as `- [~]` with a mandatory `--reason`. |

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
| `dummyindex context council-batch --next [--feature ID]... [--force] [--mode light\|standard\|deep] [--cap N] [--tree-enrich] [--json]` | Next parallel batch of council dispatch-units (earliest incomplete stage across features); `--feature` scopes the frontier; `--force` re-councils already-complete scoped features (requires `--feature`); `--cap N` bounds the batch size. |
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

### Audit panel (behind `/dummyindex-audit` or `$dummyindex-audit`)

The CLI plumbing the argue-and-audit skill drives; a human runs the slash command, not these.

| Command | What it does |
|---------|--------------|
| `dummyindex context audit start --describe "..." [--scope PATH]... [--mode light\|standard\|deep] [--model ...] [--slug S] [--force] [--json]` | Scaffold `.context/audits/<slug>/` and emit the persona catalog. Codex passes `--model current` explicitly; Claude uses a configured or user-selected Claude model. |
| `dummyindex context audit show --slug S [--json]` | Report an audit's state + completed rounds + report path. |
| `dummyindex context audit-log --slug S --round N --persona P --status STATE [--note "..."]` | Append to `audits/<slug>/_debate-log.json` (debate resumption). Status: `started\|complete\|failed\|skipped`. |

### Context-hygiene GC (behind `/dummyindex-gc` or `$dummyindex-gc`)

Deterministic plumbing for the GC council sweep; `/dummyindex-gc` on Claude or `$dummyindex-gc` on Codex drives the judgment + user confirm. Generated docs are **deleted, never archived**. Never deletes source code.

| Command | What it does |
|---------|--------------|
| `dummyindex context gc status [--json] [--root DIR]` | Read-only sweep: every candidate doc under `proposals/` + `audits/` with its signals, plus the commit-throttle state (`commits_since` / anchor / threshold / `should_signal`). Exit 0. |
| `dummyindex context gc delete --kind proposal\|audit (--slug S \| --path P) [--yes] [--allow-untracked] [--force-partial]` | Remove ONE doc workspace. Without `--yes` it's a dry-run (deletes nothing); `--yes` performs the bounded, guarded delete. Refuses a sentinel / escaping / untracked target. |
| `dummyindex context gc stamp [--to SHA] [--root DIR]` | Advance the committed GC anchor (`.context/gc/state.json`) to HEAD (or `--to`). Off-git is a no-op. |
| `dummyindex context gc signal [--root DIR]` | SessionStart throttle probe: prints the one-line nudge iff commits since the anchor ≥ threshold and it hasn't already signalled this session. Always exit 0. |

### Managed doc homes

Keep internal planning docs (plans / specs / design / audits) in their managed `.context/` homes instead of straying under `docs/`.

| Command | What it does |
|---------|--------------|
| `dummyindex context migrate-docs [--root DIR] [--yes] [--force] [--json]` | Relocate stray planning docs that leaked under `docs/` into their managed homes (`.context/proposals/<slug>/` or `.context/audits/<slug>/`), preserving git history. Dry-run by default; `--yes` performs the moves; `--force` fills only missing files in an existing home. Never touches source or moves outside `docs/`. |
| `dummyindex context guard-doc-write [--root DIR]` | PreToolUse Write-guard (reads hook JSON on stdin): denies a Write that would create an internal planning doc in an unmanaged location, naming the `.context/` home it belongs in; allows everything else. Fail-open (never exit 2). Config-gated by `doc_guard_enabled`; a `doc_guard_allow` glob exempts a path. |

### Config escalation

| Command | What it does |
|---------|--------------|
| `dummyindex context wire [path] [--root DIR] [--yes]` | Interactive escalation surface for the `wired` config list: re-classifies each entry, then PROMPTS before wiring each declared-but-absent plugin. A `kind: skill` entry is surfaced as manual, never auto-wired. `--yes` auto-affirms; a non-TTY stdin without `--yes` prints the would-prompt list and exits 0 (never blocks). |

### Meta

| Command | What it does |
|---------|--------------|
| `dummyindex --version` / `-V` | Print the installed version. |
| `dummyindex --help` / `-h`, `dummyindex context --help` | Authoritative command list with flags. |
