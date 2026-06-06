<p align="center">
  <a href="https://github.com/MullaAhmed/dummyindex"><img src="https://raw.githubusercontent.com/MullaAhmed/dummyIndex/refs/heads/main/docs/logo-text.svg" width="260" alt="dummyIndex"/></a>
</p>

# dummyindex

The persistent context engine for a repo. A Claude Code skill that turns any codebase into a `.context/` folder Claude can navigate without grepping — deterministic AST extraction plus a six-persona council that fills in the judgment.

```
pip install --user dummyindex          # or: uv tool install dummyindex
dummyindex install                     # one-time, user-global
cd /path/to/your/repo
claude                                 # open Claude Code in your repo
> /dummyindex <path>                   # e.g. /dummyindex ./src
```

After the first run, every future Claude Code session in this repo consults `.context/` before reading source at random. Auto-refresh hooks keep the index current with every commit and edit.

### Choose `<path>` deliberately

`<path>` is not a placeholder for "the repo" — it's a scoping decision. Whatever you point at gets extracted into `.context/`, and **every future Claude Code session in this repo will read that index**. So pick the code you actually want Claude to navigate.

Most real repos contain things that should *not* land in the index:

- local scripts, scratch files, experimental notebooks
- hard-coded secrets, `.env.local`, fixture credentials
- vendored third-party code you don't own
- generated artifacts, build outputs, large data dumps
- internal docs or notes that aren't part of the shipped surface

Prefer scoping to the actual source tree — `./src`, `./packages/api`, `./apps/web` — rather than the repo root. You can always add more scopes later with another `/dummyindex <other-path>`. If the repo is genuinely a clean source tree with nothing to exclude, `/dummyindex .` is fine.

---

## What it does

Six phases — one deterministic, five Claude-driven via a multi-agent council.

**Phase 1 — Deterministic backbone (`dummyindex ingest <path>`, seconds, no LLM):**

```
<root>/.context/
├── INDEX.md                          # what's in this folder
├── HOW_TO_USE.md                     # agent-facing navigation guide
├── PROJECT.md                        # one-page project summary
├── meta.json                         # counts, languages, generated_at
├── tree.json                         # PageIndex hierarchy: project → dir → file → class → method
├── map/
│   ├── files.json                    # every file with language + size
│   └── symbols.json                  # every symbol with path + line range
├── conventions/
│   ├── naming.md                     # statistically derived (Phase 1)
│   ├── naming.json
│   ├── folder-organization.md        # agent-authored (Phase 1.5)
│   ├── coding-practices.md
│   ├── testing.md
│   └── data-access.md
├── architecture/overview.md
├── playbooks/                        # add-feature / fix-bug / refactor / etc.
├── source-docs/
│   ├── INDEX.json                    # catalog of existing prose docs (READMEs, ADRs, docs/)
│   └── INDEX.md                      # with per-doc confidence + broken-references
├── features/
│   ├── INDEX.json + INDEX.md         # behavioral table of contents
│   ├── HOW_TO_NAVIGATE.md
│   ├── symbol-graph.json             # NetworkX symbol graph + Leiden communities
│   ├── graph.json + graph.html       # feature/flow graph + interactive viewer
│   └── <feature-id>/
│       ├── feature.json
│       ├── spec.md                   # what it does (intent, contracts) — entry point
│       ├── plan.md                   # how it's implemented (architecture, file map)
│       ├── concerns.md               # risks + gaps (data, security, product)
│       ├── docs.md                   # pointer list to source-docs matching this feature
│       ├── flows/<flow-id>.json
│       └── council/_council-log.json
└── cache/manifest.json               # per-machine, gitignored

<root>/.claude/CLAUDE.md              # managed block telling future sessions to read .context/
```

**Phases 1.5 → 6 — `/dummyindex` skill (multi-agent council):**

| Phase | What runs |
|---|---|
| 1.2 — Onboarding | First run (no `.context/config.json`): a 5-question setup (scope, mode, model, hook, docs) persisted to a committed `config.json`. |
| 1.5 — Conventions | Agents author the four `conventions/*.md` files beyond `naming`. |
| 2 — Structural review | Architect proposes feature regrouping; applied atomically via `features-rename`. |
| 3 — Per-feature pipeline | Sequential, spec-kit-shaped: `/specify` (a stack-specialist dev drafts `spec.md` + `plan.md`) → `/plan` (architect reorganises `plan.md`) → `/critique` (critics file `concerns.md`, mode-gated). |
| 4 — Flow narrative | The same dev filters and narrates the end-to-end flows per feature. |
| 5 — Reconcile | `dummyindex context refresh-indexes` rebuilds INDEX files and the feature graph. |
| 6 — Report | Counts, mode, where to start reading, cost. |

Trivial features are filtered out (or merged into siblings) before councilling so the LLM budget goes to what matters. Every enriched node has its `confidence` bumped from `EXTRACTED` → `INFERRED` — that's the audit trail.

---

## Two modes + the build loop (v0.15)

dummyindex runs in two modes per repo.

**Setup mode (one-time):** `/dummyindex` + `/dummyindex-equip` — preflight → ingest → onboarding → council enrichment → equip. Builds `.context/`, installs hooks, and generates a project-tuned toolkit in `.claude/` (agents, skills, hooks, recorded in `equipment.json`).

**Ongoing mode (every session after):** the spine plans, builds, and evolves. The SessionStart hook injects drift + memory; `/dummyindex-plan` turns a feature request into a consistency-checked proposal; `/dummyindex-build` drives the checklist through the equipped agents (verify-before-tick), then re-indexes; `equip status|refresh|patch` evolves the toolkit as the project grows. `/dummyindex-remember` saves cross-session memory to `.context/session-memory/`.

### Sibling skills (v0.15)

Four top-level skills ship alongside `/dummyindex`:

| Skill | What it does |
|---|---|
| `/dummyindex-plan "<feature>"` | NL request → consistency-checked `.context/proposals/<slug>/` (`spec.md` / `plan.md` / `checklist.md`) via `dummyindex context propose`. Reuses `query` to avoid duplicating existing features and to cite relevant conventions. |
| `/dummyindex-equip` | Renders a project-tuned toolkit into `.claude/` via `dummyindex context equip`: `<stack>-implementer/tester` + `<proj>-reviewer` agents + `<proj>-verify` skill, toolchain commands baked in, formatter hook wired into `settings.json`. Supports lifecycle verbs: `status | refresh | reset | uninstall | patch`. |
| `/dummyindex-build` | Drives a proposal's `checklist.md` to completion (`dummyindex context build`): dispatches each task to its mapped agent (or `general-purpose` fallback), verify-before-tick, then a post-build learning step → `equip patch`, then `rebuild --changed`. |
| `/dummyindex-remember` | Appends a first-person summary to `.context/session-memory/now.md`, runs `dummyindex context memory roll`, and promotes durable facts to `core-memories.md`. |

### Equip v2 — evolving toolkit engine

The toolkit is **origin-hash baselined**: every generated file is classified as `pristine`, `user-modified`, or `missing`. User-modified files are never stomped — not on `apply`, not on `refresh`. `equip reset NAME` is the explicit escape hatch to restore a file to its pristine render. `equip patch --item NAME --from-file F` applies a sanctioned exact-once old→new change (re-baselines + bumps the patch version) so build-run learnings flow back into the generated tooling without breaking user edits. The whole lifecycle is recorded in `.context/equipment.json` (schema v2).

> **Core principle:** dummyindex stays the spine — it never writes production code itself; it plans, equips `.context/`-grounded tooling into `.claude/`, and orchestrates; the generated tooling + dispatched agents do the writing. Agent dispatch is always skill-layer.

---

## Install

User-global (one-time):

```bash
pip install --user dummyindex        # or: uv tool install dummyindex
dummyindex install                   # copies skill into ~/.claude/skills/dummyindex/
```

Per-repo (no global state):

```bash
cd /path/to/your/repo
dummyindex install --scope project   # writes .claude/skills/dummyindex/SKILL.md in this repo
```

Both modes work with Claude Code's normal skill discovery — `/dummyindex` becomes available in any session opened in (or under) the install location.

To remove:

```bash
dummyindex uninstall                 # or: --scope project [--dir PATH]
```

---

## Use

Inside a Claude Code session opened in your repo:

```
/dummyindex                       # full ingest + standard-mode council, install hooks
/dummyindex ./some/sub            # scope to a subdirectory
/dummyindex --scaffold-only       # Phase 1 only, skip council
/dummyindex --mode light|standard|deep   # cost vs. depth (default: standard)
/dummyindex --recouncil           # re-run council on every feature
/dummyindex --recouncil <feature> # re-run on one feature
/dummyindex --recouncil --force   # ignore hash cache
/dummyindex --refresh             # rebuild INDEX files only
/dummyindex --no-trivial-filter   # council every feature, including trivial
/dummyindex --no-hooks            # skip the SessionStart drift hook during install
/dummyindex --status              # staleness, hook health, last council run
```

If you only want the deterministic backbone (no council, no LLM cost), call the CLI directly:

```bash
dummyindex ingest .                                # full backbone build + CLAUDE.md bootstrap + SessionStart drift hook
dummyindex ingest . --docs ./design-docs           # add an external doc folder to the source-docs catalog
dummyindex ingest . --docs ../adr --docs ../rfcs   # --docs is repeatable
dummyindex ingest ./some/sub --root .              # scope a subdir, output under repo root
dummyindex context rebuild --changed .             # incremental, re-hashes only changed files (manual)
dummyindex context check . --auto-refresh          # drift check; rebuild if stale (manual)
dummyindex context plan-update .                   # drift report for the SessionStart hook (stdout)
dummyindex context bootstrap .                     # regenerate the .claude/CLAUDE.md block only
dummyindex context hooks install|uninstall|status . # manage the SessionStart drift hook
dummyindex context refresh-indexes .               # rebuild INDEX.md + features/graph.{json,html}
dummyindex context enrich-plan .                   # emit .context/_enrich_plan.json (work-list)
dummyindex context enrich-apply . --from-json X    # merge {node_id: abstract} into tree.json
dummyindex context query "how does auth work"      # ranked feature shortlist (PageIndex-style, no LLM)
dummyindex context features-rename --from ID --to ID [--name "…"] [--summary "…"]
dummyindex context features-merge  --from ID --into ID [--as-section supporting] [--note "…"]
dummyindex context flow-remove     --feature ID --flow ID
dummyindex context section-write   --feature ID --section NAME --from-file PATH
dummyindex context conventions-write --section NAME --from-file PATH
dummyindex context council-log     --feature ID --stage N --agent NAME --status STATE [--note "…"]
dummyindex context memory session-start|roll|init .   # session-memory store at .context/session-memory/
dummyindex context propose  --slug S --title "..."    # build loop — scaffold a proposal
dummyindex context equip [apply] .                    # build loop — render project toolkit into .claude/
dummyindex context equip status|refresh|reset|uninstall|patch  # toolkit lifecycle
dummyindex context build --proposal S --next|--check|--status  # build loop — drive checklist
```

---

## How a Claude Code session uses `.context/`

The managed block in `<root>/.claude/CLAUDE.md` tells Claude to consult `.context/HOW_TO_USE.md` first, then walk:

| Question | File |
|---|---|
| What is this project? | `.context/PROJECT.md` |
| What's the high-level layout? | `.context/architecture/overview.md` |
| Where is `X` defined? | `.context/map/symbols.json` |
| What's in this directory? | `.context/tree.json` |
| How does feature `Z` work? / What's the flow when…? | **`.context/features/INDEX.json`** → `features/<id>/feature.json` + `README.md` |
| How does `X` relate to `Y`? / Communities, hidden dependencies? | `.context/features/symbol-graph.json` |
| Naming / folder layout / coding / testing / data-access style? | `.context/conventions/*.md` |
| What existing prose docs cover this? Are they current? | `.context/source-docs/INDEX.json` (confidence + broken-refs per doc) |
| How do I add an endpoint / migration / fix a bug? | `.context/playbooks/*.md` |

Retrieval is **PageIndex-style tree search** — reason over the table of contents, pick the feature(s), drill down. Don't grep first.

If the index disagrees with the code, the code wins — note the discrepancy and run `dummyindex context rebuild --changed .`.

---

## SessionStart drift hook

`dummyindex ingest` installs a single Claude Code SessionStart hook by default. Every time you open a Claude Code session in the repo, the hook runs `dummyindex context plan-update` and appends a markdown report to the session's system prompt — listing features whose source files have been edited since the matching `.context/features/<id>/` docs were last touched. The running Claude session reads that report and updates the relevant docs in-session, where it has the full picture of *what* changed and *why*.

This replaced an earlier shell-side auto-refresh loop (`git post-commit` + `PostToolUse` both calling `rebuild --changed`) that re-ran the deterministic backbone on every edit. That mechanism produced raw `community-N` placeholder feature folders with BFS-trace flow markdowns nobody had asked an LLM to narrate, and clobbered council-enriched features. The SessionStart hook installs cleanly over those legacy entries: `dummyindex context hooks install` will scrub them and replace with the new drift hook.

Drift clears naturally. Once you edit a feature doc (`spec.md`, `plan.md`, `concerns.md`), its mtime advances past the source mtime and the file drops off the next drift report — no explicit "mark updated" command needed.

Manage the hook explicitly:

```bash
dummyindex context hooks install|uninstall|status .
dummyindex context plan-update .   # preview the drift report
```

Pass `--no-hooks` to `ingest` to skip installation. For a manual deterministic refresh of the backbone (tree, symbols, maps, structure graph), use:

```bash
dummyindex context rebuild --changed .
```

Re-run `/dummyindex --recouncil` if you want council enrichment over the changed features too.

---

## Existing prose docs (`source-docs/`)

Repos already have docs — READMEs, CHANGELOGs, architecture notes, ADRs, RFCs. The deterministic backbone catalogs them at `.context/source-docs/INDEX.{json,md}` with **explicit staleness signals** so future Claude sessions can quote them safely.

**Discovery is automatic.** Phase 1 picks up `README.md`, `CHANGELOG.md`, `ARCHITECTURE.md`, `SECURITY.md`, `BRIEF.md`, any other `*.md` at the repo root, plus `docs/`, `doc/`, `documentation/`, `ADR/`, `RFC/`. Pass `--docs PATH` (repeatable) to add doc folders that live outside the scan root:

```bash
dummyindex ingest ./src --docs ./design-docs --docs ../external-rfcs
```

**Confidence comes from the AST**, not heuristics. For each doc, the catalog extracts every backtick-wrapped code identifier (`MyClass`, `helper_fn()`, `app/api.py`) and checks it against `map/symbols.json` + `map/files.json`. Each entry gets:

- `confidence: high` — backticked refs match the current AST. Safe to quote (still cross-check at the symbol level).
- `confidence: medium` — partial drift. Verify each cited identifier before trusting.
- `confidence: low` — heavy broken-references, or doc is much older than the newest code. Historical context only.
- `broken_refs` — the exact list of identifiers the doc claims exist but the AST doesn't have. The audit trail for *why* the doc was downgraded.

The catalog is wired into the rest of `.context/`:

- `PROJECT.md` calls out the highest-confidence README + the confidence breakdown.
- `architecture/overview.md` adds a "Documented architecture" section pointing at design docs.
- `features/<id>/docs.md` (new) — pointer list to catalog entries that mention a feature's symbols or files. Pointers, not content copies, so staleness stays in one place.
- The `/dummyindex` council receives an explicit "treat docs as hypotheses, verify against the AST before quoting" directive in the `/specify` and `/critique` dispatch prompts.

Doc edits land in the drift manifest, so a `README.md` update triggers `dummyindex context rebuild --changed`.

---

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

Tests live in `tests/`. The smoke test in `.github/workflows/tests.yml` is the closest thing to an end-to-end check: install in project scope, ingest the repo itself, verify expected files exist.

Releases publish to PyPI on GitHub Release via OIDC trusted publishing (`.github/workflows/publish.yml`).

---

## License

MIT — see `LICENSE`.
