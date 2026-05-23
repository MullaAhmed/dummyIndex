---
name: dummyindex
description: Index any codebase into a .context/ folder so Claude (and other agents) can navigate the code without grepping. Wires the index into CLAUDE.md so future sessions consume it automatically.
---

# /dummyindex — Context Engine

Drop into any repo and produce a `.context/` folder that makes the codebase navigable for AI coding agents. Updates `CLAUDE.md` so future Claude sessions in that directory consult the index before reading files at random.

This is dummyIndex **v0** — deterministic, no LLM calls. LLM-enriched summaries arrive in v0.1; MCP-driven routing in v0.2. See `BRIEF.md` and `V0_SCOPE.md` in this repo for the roadmap.

The legacy HTML knowledge-graph workflow (god-nodes, communities, surprising connections, `dummyindex-out/` viewer) lives at `skills/skill-legacy.md` and is no longer the default.

---

## Invoke

Trigger this skill when:

- The user types `/dummyindex` or `/dummyindex <path>`.
- The user asks to "index this project", "set up dummyindex on `<path>`", "create `.context/` for this repo", or anything semantically equivalent.
- The user wants to refresh an existing `.context/` after substantial changes (use the `rebuild` variant — see below).

Default path is the current working directory. If the user provides an explicit path, resolve it to an absolute path before continuing.

---

## Procedure

### 1. Sanity-check the target

Confirm `<path>` exists and is a directory.

```bash
ls -la <path>
```

If it doesn't exist or is empty, stop and tell the user before running anything.

### 2. Run the deterministic backbone

Run this single command via Bash:

```bash
dummyindex ingest <path>
```

What this does (no LLM calls, no API budget required):

- Detects every code file under `<path>` (Python, TypeScript, Go, Rust, Java, C/C++, Ruby, Kotlin, Scala, PHP, Swift, and 15+ more via tree-sitter).
- Extracts every class, function, method, and import via AST.
- Builds a hierarchical PageIndex-style `tree.json` (project → dir → file → class → method).
- Statistically infers naming conventions per language and symbol kind.
- Writes the full `.context/` folder and a managed block in `<path>/CLAUDE.md`.

Expected runtime: well under a minute on most repos. Tens of seconds even on monorepo scale.

### 3. Confirm the install

```bash
ls <path>/.context
head -25 <path>/.context/INDEX.md
```

Verify the headline files exist (the `INDEX.md` lists everything that was generated).

### 4. Report to the user

Tell the user what was created and where to go next. Concretely:

- **`<path>/.context/HOW_TO_USE.md`** — agent-facing navigation guide
- **`<path>/.context/PROJECT.md`** — one-page project summary
- **`<path>/.context/architecture/overview.md`** — top-level layout with role hints
- **`<path>/.context/map/symbols.json`** — every class / function / method with path:line
- **`<path>/.context/tree.json`** — hierarchical reasoning tree
- **`<path>/.context/conventions/naming.md`** — derived naming rules
- **`<path>/.context/playbooks/`** — task-specific recipes (`add-feature.md`, `add-endpoint.md`, `add-migration.md`, `fix-bug.md`, `refactor.md`)
- **`<path>/CLAUDE.md`** — managed block appended/refreshed

Then tell the user the next step depends on what they want:

- **To put it to work**: start a new Claude Code session in `<path>` (or reload the current one). The managed CLAUDE.md block tells Claude to consult `.context/` for any non-trivial request.
- **After substantial code changes**: re-run `dummyindex ingest <path>` (full) or `dummyindex context rebuild --changed <path>` (incremental, only re-hashes changed files).

### 5. If the user requested a rebuild instead of a fresh ingest

If the user said "rebuild", "refresh", "update the index", or similar — and `.context/` already exists at `<path>` — use the incremental command:

```bash
dummyindex context rebuild --changed <path>
```

Faster, and surfaces a per-file added/modified/removed summary.

---

## Caveats to surface to the user

- **Deterministic only in v0.** Every `abstract` in `tree.json` is a name-based stub (`"Class App at app.py:5."`). Don't expect Claude to lean on the tree for semantic meaning yet — LLM-generated summaries land in v0.1.
- **No feature/flow hypergraphs in v0.** No per-feature or per-flow markdown files. Those need either LLM enrichment or graphify's flow synthesis; deferred.
- **No MCP server in v0.** Claude reads `.context/` files passively (via file reads), not through `route()` / `walk()` / `expand()` tool calls. v0.2.

---

## What NOT to do

- **Do NOT dispatch subagents for the v0 ingest.** The deterministic CLI does all the work. Subagent-based summary enrichment is reserved for v0.1+; the legacy `skill-legacy.md` is for the HTML graph workflow only.
- **Do NOT write to `.context/` by hand.** All files are regenerated on rebuild.
- **Do NOT commit `.context/cache/`.** It's per-machine and `dummyindex` writes a `.context/.gitignore` that excludes it.
- **Do NOT clobber existing CLAUDE.md content.** The bootstrap writer is idempotent — it manages exactly one delimited block and preserves the rest. If the user has hand-edited inside the markers, surface that as a warning before re-running.
