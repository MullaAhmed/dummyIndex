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
├── features/
│   ├── INDEX.json + INDEX.md         # behavioral table of contents
│   ├── HOW_TO_NAVIGATE.md
│   ├── symbol-graph.json             # NetworkX symbol graph + Leiden communities
│   ├── COMMUNITIES.md                # god-nodes, hidden dependencies
│   ├── graph.json + graph.html       # feature/flow graph + interactive viewer
│   └── <feature-id>/
│       ├── feature.json + README.md
│       ├── architecture.md + implementation.md + data-model.md
│       ├── security.md + product.md
│       ├── flows/<flow-id>.json
│       └── council/_council-log.json
└── cache/manifest.json               # per-machine, gitignored

<root>/.claude/CLAUDE.md              # managed block telling future sessions to read .context/
```

**Phases 1.5 → 6 — `/dummyindex` skill (multi-agent council):**

| Phase | What runs |
|---|---|
| 1.5 — Conventions | Agents author the four `conventions/*.md` files beyond `naming`. |
| 2 — Structural review | Architect proposes feature regrouping; applied atomically via `features-rename`. |
| 3 — Per-feature council | For each non-trivial feature, five personas run in parallel (architect, senior dev, DBA, security analyst, PM) → cross-review → chairman synthesis. |
| 4 — Flow narrative | Senior dev filters and narrates the end-to-end flows per feature. |
| 5 — Reconcile | `dummyindex context refresh-indexes` rebuilds INDEX files and the feature graph. |
| 6 — Report | Counts, mode, where to start reading, cost. |

Trivial features are filtered out (or merged into siblings) before councilling so the LLM budget goes to what matters. Every enriched node has its `confidence` bumped from `EXTRACTED` → `INFERRED` — that's the audit trail.

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
/dummyindex --no-hooks            # skip auto-refresh hooks during install
/dummyindex --status              # staleness, hook health, last council run
```

If you only want the deterministic backbone (no council, no LLM cost), call the CLI directly:

```bash
dummyindex ingest .                                # full backbone build + CLAUDE.md bootstrap + auto-refresh hooks
dummyindex ingest ./some/sub --root .              # scope a subdir, output under repo root
dummyindex context rebuild --changed .             # incremental, re-hashes only changed files
dummyindex context check . --auto-refresh         # drift check; rebuild if stale
dummyindex context bootstrap .                     # regenerate the .claude/CLAUDE.md block only
dummyindex context hooks install|uninstall|status . # manage git + Claude Code auto-refresh hooks
dummyindex context refresh-indexes .               # rebuild INDEX.md + features/graph.{json,html}
dummyindex context enrich-plan .                   # emit .context/_enrich_plan.json (work-list)
dummyindex context enrich-apply . --from-json X    # merge {node_id: abstract} into tree.json
dummyindex context features-rename --from ID --to ID [--name "…"] [--summary "…"]
dummyindex context features-merge  --from ID --into ID --as-section NAME
dummyindex context flow-remove     --feature ID --flow ID
dummyindex context section-write   --feature ID --section NAME --from-file PATH
dummyindex context conventions-write --section NAME --from-file PATH
dummyindex context council-log     --feature ID --stage N --agent NAME --status STATE [--note "…"]
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
| How does `X` relate to `Y`? | `.context/features/symbol-graph.json` |
| Communities, god-nodes, hidden dependencies? | `.context/features/COMMUNITIES.md` |
| Naming / folder layout / coding / testing / data-access style? | `.context/conventions/*.md` |
| How do I add an endpoint / migration / fix a bug? | `.context/playbooks/*.md` |

Retrieval is **PageIndex-style tree search** — reason over the table of contents, pick the feature(s), drill down. Don't grep first.

If the index disagrees with the code, the code wins — note the discrepancy and run `dummyindex context rebuild --changed .`.

---

## Always-on auto-refresh

`dummyindex ingest` installs auto-refresh hooks by default:

- **git post-commit** — runs `context rebuild --changed` after every commit so the index never drifts behind HEAD.
- **Claude Code `PostToolUse`** — incremental refresh after Claude edits a file.
- **Claude Code `SessionStart`** — drift check + auto-refresh when you open a session.

Manage them explicitly with `dummyindex context hooks install|uninstall|status`, or pass `--no-hooks` to `ingest` to skip.

For a one-shot manual refresh (no hooks):

```bash
dummyindex context rebuild --changed .
```

Re-run `/dummyindex --recouncil` if you want council enrichment over the changed features too.

---

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

Tests live in `tests/`. The smoke test in `.github/workflows/ci.yml` is the closest thing to an end-to-end check: install in project scope, ingest the repo itself, verify expected files exist.

Releases publish to PyPI on GitHub Release via OIDC trusted publishing (`.github/workflows/publish.yml`).

---

## License

MIT — see `LICENSE`.
