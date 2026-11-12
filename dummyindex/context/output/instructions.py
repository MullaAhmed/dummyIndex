"""Agent-facing instruction generators for `.context/`.

- `HOW_TO_USE.md`        — host-neutral agent navigation guide.
- `architecture/overview.md` — deterministic top-level architecture summary.
- `playbooks/*.md`       — task-specific recipes referencing `.context/` files.

All generators are pure: no LLM, no I/O beyond returning strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dummyindex.context.build.maps import FilesMap, SymbolsMap
from dummyindex.context.build.meta import Meta
from dummyindex.context.domains.source_docs import DocCatalog, DocEntry
from dummyindex.context.enums import DOC_CONFIDENCE_ORDER

# --- HOW_TO_USE.md


_HOW_TO_USE = """\
# How to use `.context/`

Canonical machine-readable context for AI code agents (Claude Code, Cursor, Codex, Aider). dummyIndex generates it. The deterministic backbone (map, tree, `naming`, source-docs) refreshes via `dummyindex context rebuild --changed`. That preserves curated feature docs. It never re-clusters an enriched index.

Curated content (feature `spec.md`/`plan.md`/`concerns.md`, conventions) updates through reconcile. `dummyindex context reconcile` reports the delta: read-only, **writes nothing**. Then run `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex. The skill places new files and re-enriches drifted features. Finish with `dummyindex context reconcile-stamp` to advance the commit anchor.

Bounded retrieval: `dummyindex context query` and `dummyindex context graph`. Default cap is 16,000 bytes. The symbol graph may be a manifest over `symbol-graph.parts/`. Use the shared reader or graph CLI, not plain node-link JSON. Collision-affected IDs change when a new definition that conflicts enters the scan. Unresolved references list candidates.

## Read this folder *first* for any non-trivial work

Before you grep, read files, or ask the user for context, consult these in order:

| Question | Look at |
|---|---|
| "What is this project?" | `PROJECT.md` |
| "What's the layout?" | `architecture/overview.md`, then `tree.json` |
| "How does feature `Z` work?" / "What's the flow when…?" | **Start at `features/INDEX.json`** (entries live under a top-level `features` array, each keyed **`feature_id`** — *not* `id` — with `name`/`summary` plus `member_count`/`file_count`/`entry_point_count`/`flow_count`) — then `features/<feature_id>/feature.json` (raw `members`/`files`/`entry_points`/`flow_ids` lists, no `*_count` keys) + `features/<feature_id>/spec.md`. Drill into `plan.md` (implementation) / `concerns.md` (risks). See `features/HOW_TO_NAVIGATE.md`. |
| "Where is `X` defined?" | `map/symbols.json` — every class / function / method has `path` + `range` |
| "What files contain `Y`?" | `map/files.json` — full file inventory with language + size |
| "How does `X` relate to `Y`?" / "Communities / hidden dependencies?" | `dummyindex context graph` queries the symbol graph (`contains`, `method`, `inherits`, `imports`, `calls` edges + Leiden communities; legacy JSON or bounded shards). Ambiguous definitions return cited candidates. |
| "What's the naming style?" | `conventions/naming.md` — honor this when adding new code |
| "How is code grouped into folders?" | `conventions/folder-organization.md` |
| "What patterns / idioms does this repo use?" | `conventions/coding-practices.md` |
| "How are tests written here?" | `conventions/testing.md` |
| "How does this repo talk to its database?" | `conventions/data-access.md` |
| "How do I add / change / fix X?" | `playbooks/` — task-specific recipes |
| "How do I retire stale proposals/audits?" | `playbooks/gc-context.md` — the context-hygiene GC sweep (`/dummyindex-gc` on Claude, `$dummyindex-gc` on Codex) |

## Retrieval principle: walk the tree, don't grep

This index uses **PageIndex-style, reason-based retrieval**. Procedure for any non-trivial question:

1. **(Optional fast first cut)** Run `dummyindex context query "<task or question>"`. It scores each feature by token overlap with its name, summary, files and symbols. It prints top-K with cited markdown excerpts: a deterministic ranked shortlist, no LLM. Use it to pick features to open. Then continue to reason. Add `--top-k N` to widen, `--json` for machine output.
2. Read `features/INDEX.json`, the table of contents. `coverage.json` accounts for indexed files, file-only navigation, unassigned source and excluded paths with reasons. It also records source ownership, extraction status and identity ambiguities. Query output caps at 16,000 UTF-8 bytes. Set `--max-bytes N` to bound it.
3. Reason over names and summaries. Pick 1–3 features the task touches. The `query` rank is a hint, not the verdict. Reason over the TOC yourself.
4. Read the chosen `feature.json` and `spec.md`.
5. Drill into `plan.md` (implementation) and `concerns.md` (risks).
6. Follow `path:range` citations to source to verify.

**Never grep the source tree first.** The tree is already mapped. Reason over the map. This beats string search on source.

## Concrete examples

**Asked to add a new feature?** Read `playbooks/add-feature.md`. Check for duplicates in `map/symbols.json`. Mirror the structure of a feature already in the repo, found through `tree.json`, and honor `conventions/naming.md`. Write tests first.

**Asked to find or modify something specific?** Do not grep blindly. `map/symbols.json` lists every symbol's `path:range`. Load it once, find the match, jump to the code.

**Asked an architectural question?** Start with `PROJECT.md` and `architecture/overview.md`. Most questions answer themselves at that level. Drill into `tree.json` only for finer detail.

**For a rename or refactor?** `map/symbols.json` lists every site to consider. Combine with conventional grep for callers.

## When the index is wrong

The code is the source of truth. If the index disagrees with a file, trust the file. Then fix the index by the path that matches what is stale:

- **Stale deterministic artefacts** (moved or renamed symbol, new or deleted file, out-of-date `map/` or `tree.json`): run `dummyindex context rebuild --changed`. It re-hashes every source file and refreshes only changed deterministic bits. On a curated index it **preserves feature taxonomy and enrichment**. It does **not** touch `features/<id>/*.md` or re-cluster. It never undoes curated work.
- **Stale or absent feature docs** cover drifted specs, plans and concerns, and new code in no feature. `rebuild --changed` does **not** fix these.
  - Edit the doc in-session by hand. See Conventions for agents.
  - Or run `dummyindex context reconcile`. It shows the delta. It only reads, and it **writes nothing**. It does not re-cluster, so it is safe any time.
  - Then run `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex. The skill places new files and enriches drifted features.
  - Finish with `dummyindex context reconcile-stamp`.
- **When your explicit instruction contradicts a `.context/` spec or plan, you win.** Code and user intent are the source of truth. Note the divergence and proceed. Flag it so a later reconcile folds it in.

## Feature-oriented navigation

The `features/` folder is the **behavioral** view. The `tree.json` file is the structural view. Start at `features/INDEX.json` when asked how something works or what a flow does. The `features/INDEX.json` file points to the `feature.json` file of each feature. It also points to `flows/<flow-id>.json`. Answer from the index, not from grep.

Folder names get renamed during enrichment, but `feature_id` stays stable. Always navigate by ID.

## What gets committed and why

**Commit everything in `.context/`**, except `cache/` and the scratch artefacts listed in `.context/.gitignore`. A fresh clone must navigate this index without the CLI. The reconcile loop anchors on committed state.

The managed `.context/.gitattributes` marks heavy machine-layer artefacts (`tree.json`, `map/files.json`, `map/symbols.json`, `features/symbol-graph.json`, `features/graph.json`, `features/graph.html`) as `linguist-generated`. GitHub collapses their large rebuild diffs in PR review. Local `git diff` and merges stay untouched.

The committed layout, top-down:

| Path | What it is |
|---|---|
| `PROJECT.md`, `INDEX.md`, `architecture/` | project overview + entry index |
| `map/`, `tree.json`, `source-docs/` | deterministic backbone (regenerated by `rebuild --changed`) |
| `features/` | curated behavioral view (per-feature `spec.md`/`plan.md`/`concerns.md`) |
| `conventions/`, `playbooks/` | authored house style + task recipes |
| `proposals/<slug>/`, `audits/<slug>/` | **generated per-task workspaces**, swept by the hygiene GC (below) |
| `gc/state.json` | **committed** GC commit anchor (`{"anchor": sha}`); the per-session nudge memo lives in gitignored `cache/`, never here |
| `gc/evolution.jsonl`, `gc/evolve/<run>/` | **committed** evolve loop state (append-only decision history + per-run harvest/candidates/staged artifacts) written by `context evolve`; CLI-owned, never hand-edited |
| `fleet/run-<id>/` | **committed** fleet-run artifacts (`RUN-MANIFEST.md` first, `state.json` last) written by `context fleet init`; resumed via the CLI verbs, never hand-edited |
| `cache/`, `_doc_backups/` | per-machine scratch, **gitignored**, never referenced |

## Context-hygiene GC (lifecycle of generated docs)

dummyindex generates per-task workspaces: `.context/proposals/<slug>/` (plan artifacts) and `.context/audits/<slug>/` (argue-and-audit panels). Workspaces are **disposable**. Superseded plans, abandoned scaffolds and long-fixed audits mislead the next agent. The **context-hygiene GC** retires them.

**Generated docs are garbage-collected: deleted, not archived.** There is no `_archive/` tier from now on. The old `proposals/_archive/` convention is itself a delete candidate.

Disposition is decisive deletion. Distill nothing. Keep nothing around in case. A `done`-but-still-relevant plan stays. Only genuinely **stale / superseded / dead / no-longer-useful** docs go.

**How the sweep runs.** It is an LLM council step, run as `/dummyindex-gc` on Claude or `$dummyindex-gc` on Codex. Subagents walk candidate docs PageIndex-style, through `dummyindex context query`. They judge each doc against current code and work in flight. Then they propose a delete-list.

Deletion always needs user confirmation. Until you confirm, the sweep deletes nothing. The sweep deletes dead **docs** directly.

**Trivially-dead code** is a private symbol with zero callers that passes every exclusion guard. It takes the normal implementer and tester path. Remove it only if the full suite stays green.

Anything broader routes to a new proposal. It is never removed automatically. GC never edits or removes source code directly.

**When the nudge fires.** The nudge uses a commit-count throttle, not a clock. When at least N commits (default 10) land since the last GC anchor, Claude's SessionStart hook prints a one-line nudge.

The nudge reads `N commits since last hygiene sweep — run /dummyindex-gc`. Codex installs no dummyindex GC hook. Invoke `$dummyindex-gc` explicitly. The sweep stamps a fresh anchor to reset the counter. Either skill runs on demand at any time.

**Deterministic CLI:** `dummyindex context gc`, four verbs. Order of use: see `playbooks/gc-context.md`.

| Verb | What it does |
|---|---|
| `gc status [--json]` | read-only sweep report — every candidate doc with its signals, plus the throttle state (`commits_since` / `anchor` / `threshold` / `should_signal`). The skill and Claude's SessionStart hook consume this. |
| `gc delete --kind proposal\\|audit (--slug S \\| --path P)` | delete **one** workspace dir. A dry-run without `--yes` (deletes nothing); refuses a sentinel/escaping target and an untracked workspace (needs `--allow-untracked`). Never touches source code. |
| `gc stamp [--to SHA]` | advance the committed GC anchor in `gc/state.json` to HEAD (off-git no-op). |
| `gc signal` | Claude's SessionStart throttle probe. Prints the nudge iff over threshold and not already signalled this session. |

## CI, linting & secret scanners

- `sha256` fields in `map/files.json` and `source-docs/INDEX.json` are **content fingerprints** of source files, not credentials. Entropy scanners (e.g. detect-secrets' "Hex High Entropy String") flag them as false positives.
- **Do not blanket-exclude `.context/` from every pre-commit hook.** You lose JSON validity, merge-conflict and large-file checks on the index. Scope the exclusion to the entropy scanner only. Example for detect-secrets:

  ```yaml
  - id: detect-secrets
    exclude: ^\\\\.context/(map/|source-docs/INDEX\\\\.json)
  ```

  Or audit the hits once into your `.secrets.baseline` allowlist.
- Generated files end with one newline and carry no whitespace at line ends. Whitespace fixers pass without rewrites.

## Conventions for agents

- **Two layers, two rules.**
  - Deterministic artefacts (`map/files.json`, `map/symbols.json`, `tree.json`, `conventions/naming.md`, `source-docs/INDEX.json`, `features/*` indexes and graphs) regenerate on `rebuild --changed`. **Do not hand-edit them.** Your edits get overwritten.
  - The curated layer (`features/<id>/spec.md`, `plan.md`, `concerns.md`, and authored `conventions/*.md` except `naming.md`) is council-owned. Edit it in-session to clear drift. `rebuild --changed` preserves it. Hand-edit a feature doc to fix it.
  - Never hand-edit a generated map or index.
- `cache/` is per-machine and gitignored. Never reference it.
- Always check `conventions/naming.md` before you name a new symbol or file.
"""


def generate_how_to_use_md() -> str:
    return _HOW_TO_USE


# --- architecture/overview.md


_DIR_ROLE_HINTS: dict[str, str] = {
    "test": "test suite",
    "tests": "test suite",
    "spec": "test suite",
    "specs": "test suite",
    "src": "source code",
    "lib": "library code",
    "app": "application code",
    "apps": "application code",
    "docs": "documentation",
    "doc": "documentation",
    "migrations": "database migrations",
    "migration": "database migrations",
    "db": "database layer",
    "database": "database layer",
    "schema": "database schemas",
    "schemas": "database schemas",
    "models": "data models",
    "model": "data models",
    "api": "HTTP / API surface",
    "routes": "HTTP routes",
    "handlers": "request handlers",
    "controllers": "request handlers",
    "components": "UI components",
    "pages": "UI pages",
    "views": "UI views",
    "utils": "utility helpers",
    "util": "utility helpers",
    "helpers": "utility helpers",
    "services": "business-logic services",
    "service": "business-logic services",
    "cli": "CLI commands",
    "commands": "CLI commands",
    "workers": "background workers / jobs",
    "jobs": "background jobs",
    "scripts": "operational scripts",
    "config": "configuration",
    "configs": "configuration",
    "infra": "infrastructure / deployment",
    "infrastructure": "infrastructure / deployment",
    "deploy": "deployment",
    "k8s": "kubernetes manifests",
    "terraform": "terraform / IaC",
    "static": "static assets",
    "public": "public / static assets",
    "assets": "static assets",
    "fixtures": "test fixtures",
    "examples": "examples",
    "tools": "development tools",
}


@dataclass(frozen=True)
class _DirSummary:
    name: str
    role_hint: str | None
    file_count: int
    languages: tuple[str, ...]
    symbol_count: int


def generate_architecture_overview_md(
    repo_root: Path,
    files_map: FilesMap,
    symbols_map: SymbolsMap,
    meta: Meta,
    *,
    doc_catalog: DocCatalog | None = None,
) -> str:
    by_dir = _group_files_by_top_level_dir(files_map)
    symbols_by_dir = _group_symbols_by_top_level_dir(symbols_map)

    summaries: list[_DirSummary] = []
    for dirname in sorted(by_dir):
        files = by_dir[dirname]
        langs = tuple(sorted({f.language for f in files if f.language}))
        summaries.append(
            _DirSummary(
                name=dirname,
                role_hint=_role_hint_for(dirname),
                file_count=len(files),
                languages=langs,
                symbol_count=len(symbols_by_dir.get(dirname, ())),
            )
        )

    lines: list[str] = ["# Architecture overview", ""]
    lines.append(
        "Auto-derived from the directory layout and AST extraction. "
        "Heuristic role hints come from common directory naming patterns."
    )
    lines.append("")

    lines.append("## Stack")
    lines.append("")
    if meta.languages:
        lines.append(f"- **Languages:** {', '.join(meta.languages)}")
    lines.append(f"- **Files:** {meta.file_count}")
    lines.append(f"- **Symbols:** {meta.symbol_count}")
    lines.append("")

    lines.append("## Top-level layout")
    lines.append("")
    if not summaries:
        lines.append("_No subdirectories detected — all source at repo root._")
        lines.append("")
    else:
        lines.append("| Path | Role (heuristic) | Files | Symbols | Languages |")
        lines.append("|---|---|---:|---:|---|")
        for s in summaries:
            role = s.role_hint or "_unknown_"
            langs = ", ".join(s.languages) if s.languages else "—"
            lines.append(
                f"| `{s.name}/` | {role} | {s.file_count} | {s.symbol_count} | {langs} |"
            )
        lines.append("")

    root_files = [f for f in files_map.files if "/" not in f.path]
    if root_files:
        lines.append("## Repo-root files")
        lines.append("")
        for f in sorted(root_files, key=lambda x: x.path):
            lang = f.language or "—"
            lines.append(f"- `{f.path}` ({lang}, {f.size_bytes} bytes)")
        lines.append("")

    if doc_catalog is not None:
        arch_docs = _select_architecture_docs(doc_catalog)
        if arch_docs:
            lines.append("## Documented architecture")
            lines.append("")
            lines.append(
                "These checked-in docs describe the architecture. "
                "**Advisory only** — the AST-derived layout above is the "
                "source of truth. Each doc carries a `confidence` from "
                "`source-docs/INDEX.md`; treat low-confidence entries as "
                "history."
            )
            lines.append("")
            for d in arch_docs:
                title = f" — {d.title}" if d.title else ""
                lines.append(
                    f"- [`{d.path}`](../../{d.path}) (**{d.confidence}**{title})"
                )
            lines.append("")

    lines.append("## How to use this file")
    lines.append("")
    lines.append(
        "This is a fast-orienting overview. For specifics, walk `tree.json` "
        "for full hierarchy and consult `map/symbols.json` for exact line "
        "locations. Honor `conventions/naming.md` when adding new code in any "
        "of the directories above."
    )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _group_files_by_top_level_dir(files_map: FilesMap) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in files_map.files:
        head, _, _ = f.path.partition("/")
        if not _:
            continue  # root file, not in any dir
        out.setdefault(head, []).append(f)
    return out


def _group_symbols_by_top_level_dir(symbols_map: SymbolsMap) -> dict[str, list]:
    out: dict[str, list] = {}
    for s in symbols_map.symbols:
        head, _, _ = s.path.partition("/")
        if not _:
            continue
        out.setdefault(head, []).append(s)
    return out


def _role_hint_for(dirname: str) -> str | None:
    return _DIR_ROLE_HINTS.get(dirname.lower())


# Filename signals that a doc is architecture-relevant. Case-insensitive
# substring match on the last path segment.
_ARCH_DOC_SIGNALS: tuple[str, ...] = (
    "architecture",
    "design",
    "overview",
    "system",
    "structure",
    "diagram",
)


def _select_architecture_docs(catalog: DocCatalog) -> list[DocEntry]:
    """Filter the catalog to docs that name architecture explicitly."""
    out: list[DocEntry] = []
    for d in catalog.docs:
        if d.is_external:
            continue
        name = d.path.rsplit("/", 1)[-1].lower()
        if any(sig in name for sig in _ARCH_DOC_SIGNALS):
            out.append(d)
            continue
        # Also match by H1 / H2 mentioning "architecture".
        if d.title and "architecture" in d.title.lower():
            out.append(d)
            continue
    # High-confidence first so the most useful pointer is at the top.
    out.sort(key=lambda d: (DOC_CONFIDENCE_ORDER.get(d.confidence, 3), d.path))
    return out


# --- playbooks/*.md


_PLAYBOOK_BODIES: dict[str, str] = {
    "add-feature": """\
# Playbook — add a feature

Use this when the user asks for a new capability not present yet (page, endpoint, component, job, integration).

## 1. Confirm it's new
- Grep `map/symbols.json` for similar names. If a near-match exists, treat it as an **update**, not an addition (see `update.md` if present).
- Check `tree.json` for a directory that already groups this kind of thing.

## 2. Decide where it goes
- Mirror an existing feature's location and structure. Find a peer feature in `tree.json`.
- Honor `conventions/naming.md`. Match casing for files, classes, functions, and methods.

## 3. Test first
- If `tests/` exists, write a test in the mirrored path. Do this before touching production code.
- Use the same test framework as the rest of the project. Look for pytest, jest, vitest, etc. in `PROJECT.md` or `map/files.json`.

## 4. Implement
- Start from the mirrored peer feature. Change identifiers and adapt logic.
- Wire imports, routes, and exports the same way the peer does.

## 5. Verify and re-index
- Run the project's test command. Find it in `PROJECT.md` entry points or scripts.
- `dummyindex context rebuild --changed` refreshes the deterministic map (symbols, files, tree) against your edits. It preserves curated feature docs.
- **A new feature is new code that belongs to no feature yet.** After committing, run `dummyindex context reconcile`.
- Then invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex to place and enrich.
- Then run `dummyindex context reconcile-stamp` so a feature owns the new files.
- The reconciliation procedure ships inside that installed skill, not under `.context/playbooks/`.

## Common pitfalls
- Adding a duplicate of something that already exists. Always check `map/symbols.json` first.
- Naming inconsistent with `conventions/naming.md`.
- Forgetting the export or registration step. Find the existing wiring file in `tree.json`.
""",
    "add-endpoint": """\
# Playbook — add an HTTP endpoint

## 1. Find the existing endpoint pattern
- In `tree.json`, look for `api/`, `routes/`, `handlers/`, `controllers/`, or `webhooks/` directories.
- Pick a peer endpoint of the same kind (GET, POST, webhook, etc.). Read it.

## 2. Validate against project conventions
- File naming: see `conventions/naming.md`.
- Handler shape: mirror the peer's signature, error handling, and response shape.

## 3. Inputs and outputs
- If a request or response schema exists (Pydantic, Zod, OpenAPI), define one for the new endpoint.
- Add it to the common schemas module in use.
- For URL params and query strings, follow the project's typed-parsing pattern.

## 4. Auth and rate limits
- Check whether the peer endpoint uses an auth middleware or decorator. If yes, apply the same.
- Check for a rate-limit pattern (e.g. `@throttle`, `RateLimiter`). Apply it if relevant.

## 5. Tests
- Mirror the peer's test file. Cover: happy path, validation failure, auth failure (if applicable), and 5xx handling.

## 6. Register the route
- The new endpoint must be importable and discoverable.
- Find where the peer endpoint is registered: router, blueprint, `app.include_router`, etc. Add the new endpoint there.

## 7. Re-index
- `dummyindex context rebuild --changed` refreshes the deterministic map. It preserves curated feature docs.
- If you added new files, also run `dummyindex context reconcile`.
- Then invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex to place and enrich.
- Then run `reconcile-stamp` so a feature owns them. The reconciliation procedure ships inside that installed skill.
""",
    "add-migration": """\
# Playbook — add a database migration

## 1. Identify the migration tool
- Look for `alembic/`, `migrations/`, `prisma/`, `drizzle/`, `db/migrate/`, or similar in `tree.json`.
- Read the most recent migration to see naming and structure.

## 2. Generate the migration scaffold
- Use the project's tool: `alembic revision`, `prisma migrate dev`, `npx drizzle-kit generate`, etc.
- Find the command in `PROJECT.md`, or by inspecting the tool's config.

## 3. Write the schema change
- Write up and down (or migrate and rollback). Both must be exercised.
- Match style of recent migrations: column naming, defaults, indexes.

## 4. Update the corresponding model / schema
- Find the application-level model in `map/symbols.json`. It lists the class.
- Add the field or change with matching types.

## 5. Backfill if needed
- For non-null columns on existing tables, choose an order.
- Option one: backfill data first, then add NOT NULL.
- Option two: add nullable, then backfill in a follow-up.

## 6. Test
- If the project has a test database, run migrations against it in CI.
- Add a fixture covering the new state if a model assertion exists.

## 7. Re-index
- `dummyindex context rebuild --changed` refreshes the deterministic map. It preserves curated feature docs.
- If you added new files, also run `dummyindex context reconcile`.
- Then invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex to place and enrich.
- Then run `reconcile-stamp` so a feature owns them. The reconciliation procedure ships inside that installed skill.

## Risks worth flagging to the user
- Migrations that lock tables for >100ms on large tables. Call this out before merging.
- Schema changes without rollback paths.
""",
    "fix-bug": """\
# Playbook — fix a bug

## 1. Reproduce first
- Re-state the bug in your own words. If the symptom is unclear, ask the user one surgical question.
- Find the smallest set of inputs that reproduce it.

## 2. Locate the suspected code
- Search `map/symbols.json` for the symptom surface: the API, the CLI, or the UI handler.
- Walk inward via call sites. `tree.json` gives parent and child structure. For cross-file callers, grep is fine.

## 3. Write a failing test
- Locate the project's test file for that module via `tree.json` or `map/files.json`.
- Add a test that fails on the current code and passes with the fix. This becomes the regression test.

## 4. Make the minimal fix
- Smallest possible change. No drive-by refactors.
- Honor `conventions/naming.md`, even for one-line additions.

## 5. Verify
- Run the project's test suite.
- Confirm the failing test passes now. Confirm no other tests broke.

## 6. Re-index
- `dummyindex context rebuild --changed` refreshes the deterministic map. It preserves curated feature docs.
- A bug fix rarely adds files, so this is usually enough.
- If the fix changed how a feature works, update that feature's `spec.md` or `concerns.md` in-session.
- Or run the reconcile procedure: invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex. The procedure ships inside that installed skill.

## Anti-patterns
- Root-cause the bug. Do not wrap the symptom in a try/except.
- Do not remove the failing assertion instead of fixing the underlying code.
- No reformatting of unrelated lines in the same PR.
""",
    "refactor": """\
# Playbook — refactor without behavior change

## 1. Set the boundary
- Define scope: one symbol, or one directory. Define what is not in scope.
- Write down the public surface that must not change.

## 2. Lock behavior with tests
- If the affected code lacks tests, add them before refactoring.
- Use `map/symbols.json` to find every entry point in scope.
- Tests must fail if behavior changes. That is the whole point.

## 3. Make the refactor in small, reversible steps
- Order: rename, then move, then extract, then reorganize.
- One commit per kind of change is easier to review.
- After each step, run tests. Stop at the first regression.

## 4. Honor conventions
- `conventions/naming.md` applies to new names the refactor introduces.
- This includes extracted helpers and renamed symbols.

## 5. Re-index after each substantive step
- `dummyindex context rebuild --changed` keeps the deterministic map current.
- It preserves curated feature docs and never re-clusters.
- If a refactor moved code across feature boundaries, run the reconcile procedure afterward.
- Invoke `/dummyindex --recouncil` on Claude or `$dummyindex --recouncil` on Codex. This keeps feature ownership accurate.
- The procedure ships inside that installed skill.

## 6. Verify the public surface
- Manually confirm each item in your "must not change" list still matches.

## Anti-patterns
- Sneaking behavior changes into a "refactor" PR.
- Renaming things en masse without checking call sites.
- Skipping the tests-first step.
""",
}


PLAYBOOK_IDS: tuple[str, ...] = tuple(sorted(_PLAYBOOK_BODIES))


def generate_playbook_md(playbook_id: str) -> str:
    if playbook_id not in _PLAYBOOK_BODIES:
        raise KeyError(
            f"unknown playbook '{playbook_id}'; available: {', '.join(PLAYBOOK_IDS)}"
        )
    return _PLAYBOOK_BODIES[playbook_id]


# --- Writers


def write_how_to_use_md(path: Path) -> None:
    _atomic_write(path, generate_how_to_use_md())


def write_architecture_overview_md(
    path: Path,
    repo_root: Path,
    files_map: FilesMap,
    symbols_map: SymbolsMap,
    meta: Meta,
    *,
    doc_catalog: DocCatalog | None = None,
) -> None:
    _atomic_write(
        path,
        generate_architecture_overview_md(
            repo_root, files_map, symbols_map, meta, doc_catalog=doc_catalog
        ),
    )


def write_playbook_md(path: Path, playbook_id: str) -> None:
    _atomic_write(path, generate_playbook_md(playbook_id))


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
