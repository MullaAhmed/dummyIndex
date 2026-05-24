<p align="center">
  <a href="https://github.com/MullaAhmed/dummyindex"><img src="https://raw.githubusercontent.com/MullaAhmed/dummyIndex/refs/heads/main/docs/logo-text.svg" width="260" alt="dummyIndex"/></a>
</p>

# dummyindex

A Claude Code skill that turns any repo into a `.context/` folder Claude can navigate without grepping.

```
dummyindex install                    # one-time, user-global
cd /path/to/your/repo
claude                                # open Claude Code in your repo
> /dummyindex ingest .
```

That's it. After `/dummyindex` finishes, future Claude Code sessions in this repo will consult `.context/` before reading files at random.

---

## What it does

Two passes — one deterministic, one Claude-driven.

**Pass 1 — `dummyindex ingest <path>` (seconds, no LLM):**

```
<path>/.context/
├── INDEX.md                          # what's in this folder
├── HOW_TO_USE.md                     # agent-facing navigation guide
├── PROJECT.md                        # one-page project summary
├── meta.json                         # counts, languages, generated_at
├── tree.json                         # PageIndex hierarchy: project → dir → file → class → method
├── map/
│   ├── files.json                    # every file with language + size
│   └── symbols.json                  # every symbol with path + line range
├── conventions/
│   ├── naming.md                     # statistically derived rules
│   └── naming.json
├── architecture/overview.md          # top-level layout + role hints
├── playbooks/                        # generic add-feature / fix-bug / refactor recipes
└── graph/
    ├── graph.json                    # NetworkX node-link with Leiden communities
    └── graph.html                    # interactive viewer (small repos only)

<path>/CLAUDE.md                      # managed block telling future sessions to read .context/
```

**Pass 2 — `/dummyindex` skill in Claude Code (semantic enrichment):**

The skill uses the running Claude session to:

- Replace deterministic stub abstracts in `tree.json` with what each node *does*
- Rewrite `PROJECT.md` and `architecture/overview.md` with real descriptions grounded in README + manifests + a sampling of source files
- Tailor the five `playbooks/*.md` to this repo's actual directories, test framework, and conventions
- Generate `graph/GRAPH_REPORT.md` summarizing communities and god-nodes

Every enriched node has its `confidence` bumped from `EXTRACTED` → `INFERRED` — that's the audit trail.

---

## Install

User-global (one-time):

```bash
pip install --user --break-system-packages dummyindex   # or: uv tool install dummyindex
dummyindex install                                       # copies skill into ~/.claude/skills/
```

Per-repo (no global state):

```bash
cd /path/to/your/repo
dummyindex install --scope project                       # writes .claude/skills/dummyindex/SKILL.md in this repo
```

Both modes work with Claude Code's normal skill discovery — `/dummyindex` becomes available in any session opened in (or under) the install location.

---

## Use

Inside a Claude Code session opened in your repo:

```
/dummyindex .                  # first time: ingest + enrich
/dummyindex ingest ./some/sub  # ingest a subdirectory
```

The skill takes care of running the CLI and then doing the LLM enrichment in-session.

If you only want the deterministic backbone (no LLM), call the CLI directly:

```bash
dummyindex ingest .                                # full build, writes .context/ + CLAUDE.md
dummyindex context rebuild --changed .             # incremental, only re-hashes changed files
dummyindex context bootstrap .                     # regenerate the CLAUDE.md managed block only
dummyindex context enrich-plan .                   # emit .context/_enrich_plan.json (work-list)
dummyindex context enrich-apply . --from-json X    # merge {node_id: abstract} into tree.json
```

---

## How a Claude Code session uses `.context/`

The managed block in `<path>/CLAUDE.md` tells Claude to consult `.context/HOW_TO_USE.md` first, then walk:

| Question | File |
|---|---|
| What is this project? | `.context/PROJECT.md` |
| What's the high-level layout? | `.context/architecture/overview.md` |
| Where is `X` defined? | `.context/map/symbols.json` |
| What's in this directory? | `.context/tree.json` |
| Naming style for new code? | `.context/conventions/naming.md` |
| How do I add an endpoint / migration / fix a bug? | `.context/playbooks/*.md` |
| Communities, god-nodes, hidden dependencies? | `.context/graph/GRAPH_REPORT.md` |

If the index disagrees with the code, the code wins — note the discrepancy and run `dummyindex context rebuild --changed .`.

---

## Refresh after code changes

```bash
dummyindex context rebuild --changed .
```

Only re-extracts files whose content hash changed. Outputs an added/modified/removed summary. Re-run the `/dummyindex` skill afterward if you want enrichment over the changed subtrees too.

---

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

Tests live in `tests/`. The smoke test in `.github/workflows/ci.yml` is the closest thing to an end-to-end check: install in project scope, ingest the repo itself, verify expected files exist.

---

## License

MIT — see `LICENSE`.
