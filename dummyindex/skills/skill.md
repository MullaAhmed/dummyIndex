---
name: dummyindex
description: Index any codebase into a navigable .context/ folder. Runs the deterministic CLI for structure (every file/class/function/method, hierarchical tree, knowledge graph), then uses the current Claude session to rewrite stub abstracts with semantic ones, fill PROJECT.md with a real description, give every top-level directory a role, tailor playbooks to this repo, and write a community report from the graph. Updates CLAUDE.md so future sessions in this repo consult .context/ before grepping.
---

# /dummyindex — Context Engine

Two passes:

1. **Deterministic backbone** (CLI, no LLM): AST extraction → `tree.json` (project → dir → file → class → method), `map/files.json`, `map/symbols.json`, `conventions/naming.{md,json}`, `architecture/overview.md`, generic `playbooks/*.md`, `graph/graph.json` (+ `graph.html` for small repos), `INDEX.md`, `HOW_TO_USE.md`, `PROJECT.md`, plus a managed block in `<path>/CLAUDE.md`.
2. **Semantic enrichment** (you, the Claude session): replace every stub `abstract` in `tree.json` with what the symbol actually does; rewrite `PROJECT.md` and `architecture/overview.md` with real descriptions; tailor each `playbooks/*.md` to this repo; write `graph/GRAPH_REPORT.md` summarizing communities and god-nodes.

After both passes, the `.context/` folder is the canonical project orientation for any future Claude session in this repo.

## Invoke

Trigger when:
- The user types `/dummyindex`, `/dummyindex <path>`, or `/dummyindex ingest <path>`.
- The user asks to "index this project", "set up dummyindex on `<path>`", "create `.context/` for this repo", or anything semantically equivalent.
- The user says "rebuild", "refresh", or "update the index" — see the *Rebuild* section instead of doing a fresh ingest.

Default `<path>` is the current working directory. Resolve to an absolute path before continuing.

## Procedure

### 1. Sanity-check the target

```bash
ls -la <path>
```

If the directory doesn't exist or is empty, stop and tell the user.

### 2. Run the deterministic backbone

```bash
dummyindex ingest <path>
```

Expected output: one line `context init: wrote N files to <root>/.context` plus a `files`/`symbols`/`languages` summary and a `CLAUDE.md -> managed block written` confirmation. Takes seconds to tens of seconds. No API budget.

**Where `.context/` and `CLAUDE.md` land** — important when the user asks for a sub-tree ingest:

- `<path>` is the **scan scope** (what gets indexed).
- The **output root** is where `.context/` and `CLAUDE.md` are written. Default rules:
  - If `<path>` is a **relative** path that resolves to a strict subdirectory of the current working directory → output root = cwd (the enclosing repo). So `cd /repo && dummyindex ingest app` indexes only `app/` but writes `/repo/.context/` and `/repo/CLAUDE.md`.
  - If `<path>` is `.`, `cwd`, or an **absolute** path → output root = `<path>` itself.
- Override with `--root <dir>`: `dummyindex ingest app --root /repo/app` forces the index inside the subdir.

For every later step in this skill (steps 6–8 below), if you ran a sub-tree ingest, run the matching CLI commands against the same enclosing repo path the ingest used, not the subdir — e.g. `dummyindex context enrich-plan .` from the same cwd, or `dummyindex context enrich-apply . --from-json …`. The `--root` smart default applies to every `dummyindex context …` subcommand.

If `dummyindex` isn't available, the user hasn't installed it — tell them to run `pip install --user --break-system-packages dummyindex` (or `uv tool install dummyindex`), then `dummyindex install`.

### 3. Gather project signals

Before enriching, read (if present):

- `<path>/README.md`, `<path>/README.*`
- `<path>/pyproject.toml`, `<path>/package.json`, `<path>/Cargo.toml`, `<path>/go.mod`, `<path>/build.gradle*`, `<path>/pom.xml`, `<path>/composer.json`, `<path>/Gemfile`, `<path>/Makefile`
- `<path>/.context/PROJECT.md` — current metadata-only version
- `<path>/.context/architecture/overview.md` — current heuristic layout
- `<path>/.context/map/files.json` — file list with language + size
- `<path>/.context/conventions/naming.md` — derived rules

You now know what this repo is, the stack, the build/test commands, and the conventions in force.

### 4. Rewrite PROJECT.md

Replace the metadata page with a real one. Preserve the **At a glance** stats block at the bottom (do not lose the counts), but lead with:

- **What this project is** — one short paragraph: purpose, who uses it, what problem it solves. Ground in README + manifest description.
- **Stack** — bulleted: runtimes, key frameworks, datastores. Pull from manifest deps.
- **Entry points** — bulleted: run, test, build, lint commands. Pull from scripts / manifest / Makefile.
- **Where to start reading** — 3-5 paths from `map/files.json` a new contributor should open first.

Use the `Write` tool — this file is fully regenerated on every rebuild, so overwrite is safe.

### 5. Rewrite architecture/overview.md

Keep the `## Stack` and `## Top-level layout` headings. Under each top-level directory listed in `map/files.json`, write 2-4 sentences: what lives there, what its responsibility is, the entry-point file, the file most worth opening first. For repos with fewer than 10 files, collapse to a single paragraph instead of per-directory sections.

Read 1-3 representative files per top-level directory to ground each description. Don't load everything.

### 6. Rewrite tree.json abstracts

Stub abstracts look like `"Function greet at app.py:1."`, `"python file at app.py (2 top-level definitions)."`, `"Codebase rooted at <name>."`. Replace each with what the node **does** in 1-2 sentences.

Generate the work list:

```bash
cd <path>
dummyindex context enrich-plan .
```

That writes `.context/_enrich_plan.json` — an ordered list of node_ids needing enrichment, grouped into `batches` (one `structure` batch for the project + directory nodes, then one `file_subtree` batch per file). Each node lists `path`, `range`, the deterministic `stub_abstract`, and `evidence_files` (where to read).

Walk batches in order: structure first (top-down orientation), then each file subtree. For each node, read the source range it points at (`map/symbols.json` has the file + line range; use the `Read` tool with `offset` / `limit`). Write a 1-2 sentence abstract grounded in the source.

Apply abstracts back **one batch at a time** via the CLI — partial progress survives an interrupt because each batch is its own write:

```bash
cd <path>
# Build the JSON for the batch you just enriched (any small file path works).
cat > /tmp/dummyindex-batch.json <<'JSON'
{
  "n-prj-myrepo": "Toy greeter package exposing a single greet() function.",
  "app_py": "Entry-point module — defines greet() and a small Greeter class.",
  "app_greet": "Returns a friendly greeting for the given name.",
  "app_greeter": "Stateful greeter holding a prefix used for every greeting it produces."
}
JSON
dummyindex context enrich-apply . --from-json /tmp/dummyindex-batch.json
```

The CLI is idempotent: re-running with the same JSON is a no-op, and any `node_id` you mistype gets warned about on stderr and exits non-zero so you can fix it before moving on. Every touched node has its `confidence` bumped from `EXTRACTED` → `INFERRED` — that's the audit trail. Future agents can tell what's machine-extracted vs LLM-derived.

For repos large enough that per-leaf enrichment risks context overflow, prioritize this order and stop when context pressure gets real: structure batch → file subtrees ordered by importance (entry points first, then libraries, then tests). Tell the user where you stopped — the work-list at `.context/_enrich_plan.json` plus the `INFERRED` confidence markers on already-enriched nodes are enough for a follow-up session to resume cleanly.

### 7. Tailor playbooks

The five files under `.context/playbooks/` ship generic. Rewrite each so the steps reference *this* repo's actual structure:

- Real test framework + command (from manifest or recognizable test files)
- Real lint / build commands
- Real directories (where features live, where endpoints live, where migrations live — read from `map/files.json` and `architecture/overview.md`)
- The naming rules from `conventions/naming.md`

Keep the `## 1. ...` numbered headings so the structure is predictable for future agents. Use `Write` to overwrite each playbook.

### 8. Write graph/GRAPH_REPORT.md

The graph at `.context/graph/graph.json` is NetworkX node-link JSON with Leiden communities and edges typed `contains` / `method` / `inherits` / `imports`. Generate a plain-language report:

```bash
cd <path>
python3 - <<'PY'
import json
from collections import defaultdict
from pathlib import Path

g = json.loads(Path(".context/graph/graph.json").read_text(encoding="utf-8"))
nodes = g.get("nodes", [])
links = g.get("links", g.get("edges", []))

by_comm = defaultdict(list)
for n in nodes:
    by_comm[n.get("community", -1)].append(n)

deg = defaultdict(int)
for e in links:
    deg[e["source"]] += 1
    deg[e["target"]] += 1

out = []
out.append("# Knowledge graph report\n")
out.append(f"- Nodes: {len(nodes)}  Edges: {len(links)}  Communities: {len(by_comm)}\n")
out.append("\n## God nodes (top connected)\n")
for nid, _ in sorted(deg.items(), key=lambda x: -x[1])[:10]:
    n = next((x for x in nodes if x.get("id") == nid), {})
    out.append(f"- `{n.get('label', nid)}` (degree {deg[nid]})\n")
out.append("\n## Communities\n")
for cid, members in sorted(by_comm.items()):
    sample = [m.get("label", m.get("id","?")) for m in members[:8]]
    out.append(f"\n### Community {cid} ({len(members)} symbols)\n")
    out.append(f"Members: {', '.join(sample)}\n")
Path(".context/graph/GRAPH_REPORT.md").write_text("".join(out), encoding="utf-8")
print("wrote .context/graph/GRAPH_REPORT.md")
PY
```

Then read the file you just wrote and, under each `### Community N` heading, add 2-3 sentences describing the cluster's role: what does this group of symbols collectively do? Use the member names and their source files to ground the summary. Update the file in place with `Edit`.

### 9. Stamp INDEX.md

Prepend a one-line note to `.context/INDEX.md` so future sessions know enrichment ran:

```
> **Enriched on <ISO date>** by the Claude session — `tree.json` abstracts, `PROJECT.md`, `architecture/overview.md`, `playbooks/*.md`, and `graph/GRAPH_REPORT.md` are LLM-derived (`confidence: INFERRED`); the rest is deterministic (`confidence: EXTRACTED`).
```

### 10. Report to the user

Tell them what was created and enriched, and what the next step is:

- `<path>/.context/HOW_TO_USE.md` — start here in any future session
- `<path>/.context/PROJECT.md` — what this project is + entry points
- `<path>/.context/architecture/overview.md` — semantic top-level map
- `<path>/.context/tree.json` — every symbol with a real abstract (`INFERRED` where enriched)
- `<path>/.context/graph/GRAPH_REPORT.md` — communities and god-nodes
- `<path>/.context/playbooks/*.md` — tailored recipes
- `<path>/CLAUDE.md` — managed block

Next step: start a new Claude Code session in `<path>`. Future sessions read the managed CLAUDE.md block and consult `.context/` before grepping or opening files at random.

## Rebuild (refresh after code changes)

If the user says "rebuild", "refresh", or "update the index" and `.context/` already exists:

```bash
dummyindex context rebuild --changed <path>
```

The output names the added/modified/removed files. Re-run steps 6 and (if entry points or top-level layout changed) 4-5-7-8 for only the affected `node_id`s. Don't redo enrichment for untouched subtrees.

## What NOT to do

- **Don't skip the CLI in step 2.** Without it there's no backbone to enrich.
- **Don't write to `.context/` by hand outside the procedures above** — files are regenerated on rebuild.
- **Don't commit `.context/cache/`** — already gitignored by the build.
- **Don't clobber existing CLAUDE.md content.** The bootstrap writer is idempotent: it manages exactly one delimited `<!-- dummyindex:begin -->`…`<!-- dummyindex:end -->` block and preserves the rest.
- **Don't dispatch subagents for the enrichment.** You — the Claude session running this skill — are the LLM. Subagents fragment context and slow things down.
- **Don't try to enrich every leaf on a giant repo in one pass.** Batch by directory; the apply-updates script in step 6 is designed for incremental writeback so partial progress survives interrupts.
