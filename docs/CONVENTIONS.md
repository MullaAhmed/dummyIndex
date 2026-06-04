# dummyindex — Conventions

The canonical reference for *how* this codebase is organised and *how* code
in it is written. Adapted from the BOS Backend conventions doc for a
**synchronous Python CLI tool** — sections that assumed HTTP/JWT/Postgres
/async have been replaced by their CLI-equivalents, dropped, or marked
N/A with rationale.

Hierarchy of authority:

1. **Code wins.** When this doc disagrees with code, the code is right.
   Open a PR to fix the doc.
2. **`.context/`** — the live, machine-generated index. When it disagrees
   with the code, the code wins; rebuild the index.
3. **This file** — the long form, with examples and rationale.
4. **CLAUDE.md** — short, points agents at `.context/` first.

## Table of contents

1. [Folder organisation](#1-folder-organisation)
2. [Layering rules](#2-layering-rules)
3. [Where does a new module go?](#3-where-does-a-new-module-go)
4. [File-size & splitting rules](#4-file-size--splitting-rules)
5. [Naming](#5-naming)
6. [Constants must be enums](#6-constants-must-be-enums)
7. [Every data class is frozen](#7-every-data-class-is-frozen)
8. [CLI subcommand shape](#8-cli-subcommand-shape)
9. [Module-class shape](#9-module-class-shape)
10. [Errors: explicit exception hierarchy](#10-errors-explicit-exception-hierarchy)
11. [JSON read/write helpers](#11-json-readwrite-helpers)
12. [Logging](#12-logging)
13. [Security](#13-security)
14. [Testing](#14-testing)
15. [Pre-flight](#15-pre-flight)
16. [KISS, YAGNI, no single-line wrappers, no dangling code](#16-kiss-yagni-no-single-line-wrappers-no-dangling-code)
17. [Things to avoid](#17-things-to-avoid)
18. [BOS sections that do not apply here](#18-bos-sections-that-do-not-apply-here)

---

## 1. Folder organisation

**Domain-first.** A domain owns its logic, its data, and its on-disk output.
Pieces of the same domain live next to each other.

```
dummyindex/
├── __init__.py              # narrow public surface via lazy __getattr__
├── __main__.py              # CLI entrypoint: install + ingest + context dispatch
│
├── cli/                     # `dummyindex context <subcommand>` dispatch
│   ├── __init__.py          # public: dispatch, _resolve_context_root + handlers table
│   ├── _usage.py            # `_USAGE` help text
│   ├── _common.py           # arg parsing + scope/root resolution
│   ├── _migrate.py          # legacy `.context/` layout migrations
│   ├── init.py              # _cmd_init
│   ├── rebuild.py           # _cmd_rebuild
│   ├── bootstrap.py         # _cmd_bootstrap (regenerate CLAUDE.md block)
│   ├── enrich.py            # _cmd_enrich_plan + _cmd_enrich_apply
│   ├── features.py          # rename / merge / flow-remove / section-write
│   ├── refresh.py           # _cmd_refresh_indexes
│   ├── check.py             # _cmd_check (drift detection)
│   ├── hooks.py             # _cmd_hooks
│   ├── council.py           # _cmd_council_log
│   ├── conventions.py       # _cmd_conventions_write
│   ├── query.py             # _cmd_query (PageIndex retrieval)
│   └── reality_check.py     # _cmd_reality_check
│
├── pipeline/                # the deterministic backbone
│   ├── __init__.py
│   ├── enums.py             # ConfidenceLevel, NodeKind, EdgeRelation
│   ├── io/                  # filesystem-touching helpers
│   │   ├── __init__.py      # re-exports detect, file_hash, save_cached…
│   │   ├── cache.py         # content-hash cache for tree-sitter parses
│   │   └── detect.py        # file-type detection + collection
│   ├── build/               # extraction → structure / graph
│   │   ├── __init__.py      # build_from_json, build_structure, validate_extraction
│   │   ├── structure.py     # nodes+edges → folder/file/class hierarchy
│   │   └── validate.py      # schema check before assembly
│   └── extract/             # tree-sitter AST → nodes+edges
│       ├── __init__.py      # public: extract(), collect_files()
│       ├── config.py        # LanguageConfig dataclass
│       ├── _common.py       # _make_id / _read_text / _resolve_name / _find_body
│       ├── _imports.py      # per-language _import_<lang> handlers
│       ├── _helpers.py      # C/C++ name resolvers + JS/C#/Swift extra walks
│       ├── _configs.py      # _<LANG>_CONFIG instances
│       ├── _generic.py      # _extract_generic (the parametric driver)
│       ├── _python_rationale.py # Python docstring + rationale post-pass
│       ├── _resolve.py      # cross-file import resolvers (Python, Java)
│       └── languages/
│           ├── __init__.py
│           ├── _wrappers.py # thin wrappers around _extract_generic
│           ├── blade.py / dart.py / verilog.py
│           └── julia.py / go.py / rust.py / zig.py / powershell.py / objc.py / elixir.py
│
├── export/                  # render graph → on-disk JSON
│   ├── __init__.py          # public: to_json
│   ├── _common.py           # _CONFIDENCE_SCORE_DEFAULTS, _node_community_map, _strip_diacritics
│   └── graph.py             # to_json (the HTML viewer lives in context/output/viewer.py)
│
├── analysis/                # graph analytics on top of pipeline output
│   └── cluster.py            # Leiden community detection
│
├── context/                 # the `.context/` context-engine
│   ├── __init__.py          # re-exports the public surface
│   ├── enums.py             # DocConfidence, ContextSubcommand
│   ├── hooks.py             # git + Claude Code auto-refresh hooks
│   ├── schemas/             # ships JSON Schemas for `.context/` artefacts
│   ├── build/               # lifecycle: source → on-disk index
│   │   ├── __init__.py
│   │   ├── runner.py        # build_all + BuildResult
│   │   ├── incremental.py   # rebuild_changed
│   │   ├── meta.py          # Meta dataclass + SCHEMA_VERSION
│   │   ├── maps.py          # FilesMap / SymbolsMap dataclasses
│   │   ├── tree.py          # Tree / TreeNode + write_tree
│   │   ├── graph.py         # GraphResult + build_graph
│   │   ├── conventions.py   # naming-rule analyser
│   │   └── manifest.py      # snapshot for drift detection
│   ├── output/              # render the build artefacts
│   │   ├── __init__.py
│   │   ├── bootstrap.py     # CLAUDE.md managed block
│   │   ├── docs.py          # PROJECT.md / INDEX.md
│   │   ├── instructions.py  # HOW_TO_USE.md / architecture overview / playbooks
│   │   └── viewer.py        # `.context/features/` HTML scaffold
│   └── domains/             # behaviour rooted in a particular .context/ area
│       ├── __init__.py
│       ├── enrich.py        # enrich-plan + enrich-apply work-list
│       ├── query.py         # PageIndex-style retrieval
│       ├── reality_check.py # post-synthesis fact-check
│       ├── council.py       # multi-agent debate log
│       ├── features/        # feature + flow detection and writeback
│       │   ├── __init__.py
│       │   ├── _constants.py # SCHEMA_VERSION + flow-depth cap + sentinels
│       │   ├── models.py    # Flow / FlowStep / Feature / *Result dataclasses
│       │   ├── errors.py    # FeatureRenameError
│       │   ├── _helpers.py  # path / range / json-write helpers
│       │   ├── builder.py   # scaffold_features (community→feature, BFS→flow)
│       │   ├── ops.py       # rename / merge / remove_flow / write_section
│       │   ├── render.py    # markdown stub renderers + viewer hookup
│       │   ├── indexes.py   # refresh_features_index_md + rebuild_features_graph
│       │   └── docs.py      # per-feature docs.md from source-docs catalog
│       └── source_docs/     # docs catalog + broken-ref detection
│           ├── __init__.py
│           ├── _constants.py # SCHEMA_VERSION + classification thresholds
│           ├── models.py    # DocEntry + DocCatalog dataclasses
│           ├── refs.py      # extract_code_refs / find_broken_refs / regex set
│           ├── discovery.py # in-repo doc discovery + _DOC_EXTENSIONS
│           ├── keys.py      # harvest_json_keys
│           ├── catalog.py   # build_doc_catalog + age/confidence classifiers
│           ├── writers.py   # write_catalog (INDEX.json + INDEX.md)
│           └── readers.py   # read_catalog
│
└── skills/                  # bundled markdown for the /dummyindex skill
```

Each large area ships the canonical trio when it grows beyond a single
file:

- `<area>/__init__.py` — public re-exports (the test surface).
- `<area>/enums.py` — fixed-alphabet constants for the area.
- `<area>/models.py` — frozen dataclasses (data only, no behaviour).

Private-to-package helpers prefix `_`: `_common.py`, `_resolve.py`,
`_html_common.py`.

---

## 2. Layering rules

```
__main__   → context.cli, context (public surface), usage
context    → analysis, pipeline
analysis   → pipeline
pipeline   → (stdlib + third-party only)
usage      → (stdlib only)
```

| Layer | Can import from | Cannot import from |
|---|---|---|
| `__main__` | `context.cli`, `context` (public surface only), `usage` | private modules under either |
| `context.cli.<sub>` | `context`, `pipeline`, `analysis` | another `context.cli.<sub>` (use `_common` instead) |
| `context.<domain>` | `context.*`, `pipeline.*`, `analysis.*` | `context.cli.*` |
| `analysis` | `pipeline.*` | `context.*` |
| `pipeline` | stdlib + third-party (networkx, tree-sitter) | `analysis`, `context` |
| `usage` | stdlib only | `context`, `pipeline`, `analysis` |

> `usage/` is a standalone domain at the bottom of the tree: it reads Claude
> Code's own transcripts under `~/.claude/projects/` for `dummyindex usage`
> and has nothing to do with `.context/`, so it imports only the stdlib. Its
> CLI boundary lives in `__main__` (`_run_usage`), mirroring `install`.

> There was once a `runtime/` layer (stdlib-only cross-cutting helpers). Its
> only member — `security.py`'s `sanitize_label` — was removed with the
> legacy `export.to_html` path, so the package is gone. Re-introduce a
> `runtime/` layer at the bottom of this table if a genuinely cross-cutting,
> stdlib-only helper appears again.

**The CLI dispatcher is wire-only.** Each subcommand module parses its
args, calls a domain function (under `context/` or `pipeline/`), and
prints/exits. No business logic in the dispatcher.

---

## 3. Where does a new module go?

| Kind of code | Lives in |
|---|---|
| Tree-sitter extraction for language X | `pipeline/extract/<x>.py` |
| Cross-file resolution shared by N languages | `pipeline/extract/_resolve.py` |
| Output format (HTML/JSON/SVG/…) for graph/structure | `pipeline/export/<format>.py` |
| `.context/` domain logic (features, docs, instructions, runner) | `context/<domain>.py` or `context/<domain>/` |
| CLI subcommand dispatcher | `context/cli/<subcommand>.py` |
| Pure analytics on the graph | `analysis/<file>.py` |
| Cross-cutting helper used by ≥ 2 areas, no I/O | `runtime/<file>.py` |
| Token reporting over Claude Code transcripts (`dummyindex usage`) | `usage/<file>.py` |
| Bundled markdown shipped with the skill (incl. slash commands) | `skills/...` |

**The trap:** if a module merely *uses* a domain, that doesn't make it part
of that domain. Ask: "would a sibling domain need this same thing if it
had the same requirement?" — if yes, it's cross-cutting.

Worked example. The output renderers in `pipeline/export/*.py` are
consumed by both `context/graph.py` and `context/features/builder.py`.
They live in `pipeline/` because they're transport-shaped (graph → bytes),
not feature-shaped.

---

## 4. File-size & splitting rules

Two independent rules — **whichever fires first wins.**

### A. Split by concern (always)

Inside a package, separate files for separate concerns even when each file
would be tiny. A 30-line `enums.py` is correct; a 200-line file mixing
enums, dataclasses, free functions, and a builder class is wrong even
under the size threshold.

| File | Holds |
|---|---|
| `enums.py` | Enums + `frozenset` lookup sets derived from them |
| `models.py` | Frozen dataclasses — data only, no behaviour |
| `<verb>.py` (`builder.py`, `render.py`, `discovery.py`, …) | One concern's logic |
| `_common.py` / `_<thing>.py` | Module-private helpers shared inside the package |
| `__init__.py` | Public re-exports (the surface the rest of the package depends on) |

Canonical layouts:

- Multi-language extractor: `pipeline/extract/{__init__,config,_common,_resolve,python,js,…}.py`
- Graph exporter: `export/{__init__,_common,graph}.py` (promoted to top-level; only `to_json` survives — `to_html` + `_html_assets.py` were removed as dead code, and the live HTML viewer is `context/output/viewer.py`)
- Feature builder: `context/features/{__init__,enums,models,errors,builder,ops,render}.py`

### B. Split by size

| Lines | Action |
|---|---|
| ≤ 200 | Default — single file. |
| 200–400 | Acceptable. |
| 400–600 | Acceptable for builders in extremis. |
| > 600 | Split. Move sub-concerns into sibling files. |

CLI dispatchers should stay under ~300 lines. Files of ~800+ lines are a
smell — extract `models.py`, `enums.py`, sibling per-concern files.

---

## 5. Naming

### 5.1 General

- `snake_case` for variables, functions, modules, packages.
- `PascalCase` for classes (dataclasses, enums).
- `UPPER_SNAKE` for module-level constants and `frozenset`/`tuple` exports.
- Private to a module: leading underscore (`_log`, `_make_id`, `_resolve_name`).
- Private to a class: leading underscore on instance attributes
  (`self._cache`, `self._root`).

### 5.2 Domain naming

- Functions emitting an on-disk artefact use the verb `to_<thing>` or
  `write_<thing>` (`to_json`, `write_section`, `write_plan`).
- Functions that *return* something derived from inputs use the verb
  `build_<thing>` (`build_from_json`, `build_structure`, `build_all`).
- Functions that *check* something return a bool prefixed
  `is_*`/`has_*`/`should_*`.
- Path-typed parameters are `path`, `root`, `out_path`, `cache_root` —
  never `p`, `dir`, `file`.
- Loop indices: `i`, `j` only in tight numeric loops; otherwise name the
  thing (`for row in rows`, `for node_id in nodes`).

### 5.3 Pydantic-style suffixes are **not used here** (no HTTP boundary)

The BOS `*Request` / `*Response` suffixes do not apply. This codebase
names dataclasses after the thing they represent (`Feature`, `Flow`,
`Meta`, `DocEntry`, `BuildResult`).

### 5.4 Don't brand identifiers with third-party product names

Module, class, function, and variable names use **generic / protocol-
neutral** language. Reserve the third-party brand for the few wire/file
literals where the spec requires the brand to appear (e.g. an Obsidian
canvas key, a Neo4j Cypher keyword).

| Layer | Convention | Example |
|---|---|---|
| Module / package | Generic | `pipeline/export/canvas.py`, not `obsidian_canvas.py` |
| Class names | Generic | `CanvasRenderer`, not `ObsidianCanvasRenderer` |
| Function names | Generic | `to_canvas(graph, out_path)`, not `to_obsidian_canvas(...)` |
| Wire / file literals | Whatever the spec mandates | `"canvas": {...}` is fine because Obsidian reads that exact key |

---

## 6. Constants must be enums

If a value has a fixed set of options, it is an `Enum` (or `StrEnum` /
`IntEnum`) — not a bare string, not a `Literal`, not a tuple, not a dict
of magic strings.

### 6.1 Three locations, three purposes

| Where | What | Example |
|---|---|---|
| `pipeline/enums.py` | Backbone enums | `NodeKind`, `EdgeKind`, `Language`, `ConfidenceLevel` |
| `context/<area>/enums.py` | Per-area enums + lookup sets | `DocConfidence`, `DocCategory`, `FeatureKind` |
| `pipeline/export/enums.py` | Output-format enums | `OutputFormat`, `ArtefactKind` |

### 6.2 String-valued enums for on-disk artefacts

Every value that lands in a JSON/Markdown file as a string is a `StrEnum`
so `.value` is wire-compatible with the artefact format on disk.

```python
class ConfidenceLevel(StrEnum):
    """Confidence on a node's name/summary. Persisted in tree.json."""
    EXTRACTED = "EXTRACTED"   # deterministic AST output, no LLM
    INFERRED = "INFERRED"     # LLM-enriched, judgment call
    PINNED = "PINNED"         # human-curated, do not auto-overwrite
```

If the schema changes, mirror it here in the same commit.

### 6.3 Lookup sets are `frozenset`s derived from the enum

Immutable, hashable, derived rather than duplicated.

```python
INFERABLE_LEVELS: frozenset[ConfidenceLevel] = frozenset(
    {ConfidenceLevel.EXTRACTED, ConfidenceLevel.INFERRED}
)
```

### 6.4 What about one-off literals?

A constant used at exactly one site, with no fixed alphabet, can be a
module-level `UPPER_SNAKE`. But ask first: is there a sibling value? If
yes, make it an enum now.

---

## 7. Every data class is frozen

This is the adapted form of BOS §7. The BOS rule says "every model is
Pydantic, every model is frozen." This codebase has **no HTTP boundary
and no user-input validation surface**, so Pydantic adds runtime cost
without payoff. The rule here:

1. **`@dataclass(frozen=True)`** for every data class.
2. **No exceptions outside `tests/`** — every Feature, Flow, Meta,
   DocEntry, BuildResult is frozen.
3. **Behaviour goes elsewhere.** Data classes hold data; a sibling
   `<domain>/builder.py` or service class holds the logic that produces
   them.

```python
@dataclass(frozen=True)
class Feature:
    feature_id: str
    name: str
    summary: str
    flows: tuple[Flow, ...] = ()  # tuple, not list, to keep frozen semantics

@dataclass(frozen=True)
class Flow:
    flow_id: str
    steps: tuple[FlowStep, ...] = ()
```

**Use `tuple[...]` not `list[...]`** for collection fields on a frozen
class. Lists are mutable; freezing the container hides that.

### 7.1 Mutable defaults

Use `field(default_factory=tuple)` not `default=()` if the type system
prefers, but a literal `()` is fine. Never `default=[]` or
`default_factory=list`.

### 7.2 Validation

Field-level validation lives in `__post_init__` raising `ValueError`.
Cross-cutting "is this artefact valid?" checks live in
`pipeline/validate.py`. Do **not** push validation into the function that
*uses* the dataclass.

---

## 8. CLI subcommand shape

Every subcommand is a module under `context/cli/`. Each module exports
exactly one entry function and any subcommand-private helpers.

```python
# context/cli/init.py
def run(argv: list[str]) -> int:
    """`dummyindex context init [path] [--root DIR] [--docs PATH]…`"""
    path, root, opts = _parse_args(argv)
    result = build_all(scope=path, root=root, docs_paths=opts.docs)
    print(_format_summary(result))
    return 0
```

`context/cli/__init__.py` keeps the dispatcher table:

```python
SUBCOMMANDS: dict[ContextSubcommand, Callable[[list[str]], int]] = {
    ContextSubcommand.INIT: init.run,
    ContextSubcommand.REBUILD: rebuild.run,
    …
}

def dispatch(argv: list[str]) -> int: …
```

Rules:

1. **No business logic in the CLI.** Argument parsing → call a domain
   function → format the result → exit code.
2. **Each subcommand returns an `int` exit code.** `0` success, `2` bad
   args, `1` runtime failure.
3. **Subcommands do not import each other.** Shared helpers live in
   `context/cli/_common.py`.
4. **Subcommand names live in `ContextSubcommand`** (a `StrEnum`), not as
   bare strings in the dispatcher.

---

## 9. Module-class shape

Domain logic that owns state or coordinates multiple steps is a class:

```python
class FeatureBuilder:
    """Build features + flows from a Leiden-clustered graph."""

    def __init__(
        self,
        *,
        graph_path: Path,
        out_dir: Path,
        cache: ContextCache | None = None,
    ) -> None:
        self._graph_path = graph_path
        self._out_dir = out_dir
        self._cache = cache

    def build(self) -> ScaffoldResult: ...
```

Rules:

1. **Constructor args are keyword-only** (after `*`). Prevents positional
   drift across PRs.
2. **No state beyond injected dependencies.** No per-instance caches that
   outlive a single `.build()` call unless explicitly designed.
3. **Returns frozen dataclasses** (`ScaffoldResult`, `RenameResult`).
4. **Raises typed exceptions** (`FeatureRenameError`), never bare
   `Exception` or `ValueError("…")` for domain errors.

For pure functions with no state, prefer a module-level `def` over a
class with a single method. Single-method classes are a smell.

---

## 10. Errors: explicit exception hierarchy

Each domain area that raises errors defines a typed exception in its
package:

```
context/features/errors.py        # FeatureRenameError
context/source_docs/errors.py     # DocCatalogError
pipeline/extract/errors.py        # ExtractionError, LanguageNotSupportedError
```

Rules:

1. **No bare `raise ValueError("…")` for domain conditions.** Use a typed
   subclass so callers can `except FeatureRenameError`.
2. **Carry context as kwargs on the exception**, accessible via attrs.
3. **The CLI dispatcher catches typed exceptions** and maps them to exit
   codes + stderr lines. Inner code raises; the CLI translates.

---

## 11. JSON read/write helpers

All `.context/` artefacts are JSON. Use the existing helpers in
`pipeline/cache.py` and the per-domain serialisers — do not re-implement
`json.dumps(..., default=...)` ad-hoc.

When serialising a frozen dataclass, write a `_to_dict()` helper next to
the class (or use `dataclasses.asdict`). When loading, use a sibling
`_from_dict()` that validates the schema version against
`Meta.SCHEMA_VERSION`.

---

## 12. Logging

This is a CLI tool — user-visible output is **stdout/stderr via `print`**,
not a structured logger. The rules:

- **`print(...)` is allowed**, but only at the CLI boundary
  (`context/cli/*` and `__main__.py`). Internal modules do not print.
- **Errors go to stderr**: `print(msg, file=sys.stderr)`.
- **Progress lines are stdout** and follow the existing two-space
  alignment seen in the installer:

  ```
    skill installed  ->  ~/.claude/skills/dummyindex/SKILL.md
    companions       ->  12 markdown(s)
  ```

If a future maintainer needs structured logs, introduce a
`runtime/logging.py` with `get_logger(__name__)` and rewire — do not
sprinkle `logging.getLogger(__name__)` calls ad-hoc.

---

## 13. Security

- The tool **reads** the user's filesystem but never executes code from
  it. Tree-sitter parses source into an AST; nothing from the scanned repo
  is ever `eval`'d, imported, or run.
- No network calls, no credentials, no secrets. If a future feature needs
  a network call (e.g. pushing to a remote graph DB), credentials come from
  explicit function args / env vars, never hardcoded.
- **HTML output is the only injection surface.** The single HTML artefact
  is `.context/features/graph.html`, emitted from the `VIEWER_HTML` template
  in `context/output/viewer.py`. It loads `graph.json` and renders
  **client-side**: AST-derived strings reach the DOM only through the
  template's own `escapeHtml()` helper (used at every `innerHTML`
  interpolation) or D3's `.text()` (which sets `textContent`, not HTML).
  Never interpolate an unescaped source-derived string into `innerHTML`.
- If a future feature reintroduces **server-side** HTML/SVG generation in
  Python, it must escape source-derived strings before output. There is no
  shared Python sanitiser today — the previous
  `runtime.security.sanitize_label` was removed along with the legacy
  `export.to_html` path it served.

---

## 14. Testing

- Framework: **pytest** with markers (`unit`, `integration`).
- Tests mirror `dummyindex/` layout under `tests/`.
- Coverage target: **80 %** (`pytest --cov=dummyindex`).
- The test surface is the **public re-exports in each package's
  `__init__.py`**. When splitting a file into a subpackage, the
  `__init__.py` re-exports the names tests already import so test imports
  do **not** change.
- Assertions in tests use bare `assert`.

---

## 15. Pre-flight

Before declaring work done:

```bash
uv run pytest -q                                          # all green
uv run ruff check dummyindex tests                        # if ruff is wired
uv run ruff format --check dummyindex tests               # if ruff is wired
dummyindex context rebuild --changed                      # refresh .context/
```

For UI / output changes, actually open the HTML in a browser or run the
CLI end-to-end. Typecheck and unit tests verify code correctness, not
artefact correctness — if you can't visually inspect, say so explicitly
rather than claiming success.

---

## 16. KISS, YAGNI, no single-line wrappers, no dangling code

| Principle | What it means in practice |
|---|---|
| **KISS** | Two designs that satisfy the requirement → pick the one with fewer moving parts. Three similar lines beat a premature abstraction. |
| **YAGNI** | No flags / hooks / refresh paths "just in case". Ship what's asked; the next ask gets its own PR. |
| **No single-line wrapper functions** | `def foo(x): return bar(x)` adds a name without adding meaning. Inline the call, or give the wrapper a real reason (default args, type narrowing, behavioural change). |
| **No dangling code** | Unused imports, helpers without callers, dead branches, leftover legacy fields. Every cleanup pass is a first-class chore. |

Edge case: a one-line "wrapper" is fine when it satisfies a type-system
constraint (injecting a default, narrowing a return type). Add a
single-line comment saying why.

---

## 17. Things to avoid

- ❌ `print(...)` outside `context/cli/*` and `__main__.py`. Domain
  modules return values and raise typed exceptions; the CLI prints.
- ❌ Bare-string magic values where a fixed alphabet exists. Use an enum.
- ❌ Hardcoded paths under `.context/`. Use the helpers in
  `context.meta` / `context.manifest` that derive paths from the root.
- ❌ `list[...]` field on a frozen dataclass. Use `tuple[...]`.
- ❌ `@dataclass` without `frozen=True` outside `tests/`.
- ❌ Mixing enums, dataclasses, and free functions in one file when each
  is non-trivial. Split by concern.
- ❌ Branding identifiers with third-party product names (`ObsidianFoo`,
  `Neo4jBar`). Reserve the brand for wire literals.
- ❌ Bare `raise ValueError(...)` for domain errors. Define a typed
  exception in the area's `errors.py`.
- ❌ Cross-subcommand imports inside `context/cli/`. Shared helpers go in
  `_common.py`.
- ❌ Committing `--no-verify`, `--amend`, or destructive git ops without
  explicit ask.
- ❌ Comments that restate the code. Comments explain *why*, not *what*.

---

## 18. BOS sections that do not apply here

The original BOS doc describes a FastAPI async backend. Several sections
have no analog in this synchronous CLI tool. They are intentionally
**not** adopted:

| BOS section | Status | Why |
|---|---|---|
| §8 Endpoints (`response_model=…`, status codes) | N/A | No HTTP server. |
| §9 Service-class shape (pool injection, async methods) | Partially adapted to §9 above (sync, no pool, keyword-only init). |
| §10 Async everywhere | N/A | This is a synchronous CLI. tree-sitter is sync; no DB; no network. |
| §11 BackendError hierarchy | Adapted to §10 above — per-area typed exceptions, not an HTTP-mapped tree. |
| §12 Soft delete + restore | N/A | No DB. `.context/` artefacts are regenerated, not soft-deleted. |
| §13 Tenant scope | N/A | Single-user local tool. |
| §14 JSONB read/write | N/A | No Postgres. `.context/` is plain JSON on disk. |
| §15 Transactions, locking, cascade | N/A | No DB. File writes are atomic via `tmp` + rename in the existing helpers. |
| §16 Observability (OTEL, structlog, audit log) | N/A | CLI tool. Stdout/stderr is the observability surface. |
| §17 Security (JWT, CORS, asyncpg, Fernet) | Replaced by §13 above — filesystem-only threat model. |

The substantive content from those sections is replaced where applicable
(e.g. §11 BackendError → typed per-area exceptions; §17 Security →
sanitisation rule for HTML output). The sections themselves stay marked
N/A here so a future reader of both docs can see the deliberate gap.
