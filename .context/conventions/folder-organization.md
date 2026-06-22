# Folder organization

How source under `dummyindex/` is grouped, and where a new file goes.

## The organizing axis: domain-first, then layered

This repo groups code **by domain** (a feature owns its logic + data + on-disk
output, living in one directory), arranged within a **strict import layering**.
Both rules are stated in `docs/reference/01-conventions.md` §1–§3. That doc is
graded **low confidence** in `source-docs/INDEX.json` (its prose cites many code
paths, tripping broken-ref detection) — but its *structure* claims cross-check
clean against the live tree, so they are reused here with `path:range` evidence.

The top-level layers (`.context/tree.json`, real dirs):

| Dir | Role |
|---|---|
| `pipeline/` | deterministic backbone: tree-sitter extract → structure/graph |
| `analysis/` | graph analytics on pipeline output (`analysis/cluster.py` — Leiden) |
| `export/` | render graph → on-disk JSON (`export/graph.py:to_json`) |
| `context/` | the `.context/` engine: `build/` (lifecycle), `output/` (renderers), `domains/` (behaviour) |
| `cli/` | one wire-only dispatcher module per subcommand |
| `installer/`, `usage/`, `skills/` | install surface, transcript token reporting, bundled markdown |

Import direction (verified): `context → analysis, pipeline`; `analysis →
pipeline`; `pipeline →` stdlib/third-party only. `usage/` is stdlib-only — its
files import nothing under `dummyindex.*`. `context/domains/*` never imports
`cli` (grep is clean except a docstring in `equip/__init__.py:6`).

## The CLI / domain split (the load-bearing pattern)

`cli/<sub>.py` is **wire-only**: parse argv, lazy-import a domain function,
print/exit. Logic lives under `context/domains/<x>/`. See `cli/query.py:7-15`
— `run(args)` imports `query, render_json` from `context.domains.query` inside
the function body. `cli/features.py:35-36` does the same. New CLI work follows
this shape — never put business logic in `cli/`.

## How a domain directory is split

Once a `.context/` domain outgrows one file it splits into canonical concern
files, demonstrated by `context/domains/features/`:

- `models.py` — frozen dataclasses, data only (`features/models.py`)
- `constants.py` / `enums.py` — fixed-alphabet constants (`features/constants.py`)
- `errors.py` — typed exceptions (`features/errors.py:FeatureRenameError`)
- `helpers.py` / `ops.py` / `builder.py` / `render.py` — behaviour by verb
- `__init__.py` — the public re-export surface

When a domain passes ~10 modules it **nests by concern**, the way
`context/domains/equip/` splits into `generate/ plugins/ lifecycle/ wiring/`
(`equip/generate/catalog.py`, `equip/wiring/safety.py`, …). A CLI subcommand
that needs private siblings becomes a package too: `cli/equip/`, `cli/build_loop/`.

**Filenames never carry a leading underscore** — privacy is the package
boundary (`__init__.py`) and the function level (`_name`), not the filename.

## Where a new file goes

| Kind of code | Lives in |
|---|---|
| Tree-sitter extraction for language X | `pipeline/extract/languages/<x>.py` |
| Cross-file resolver shared by N languages | `pipeline/extract/resolve.py` |
| Graph output format | `export/<format>.py` |
| `.context/` domain logic | `context/domains/<domain>.py` or `<domain>/` |
| CLI subcommand | `cli/<sub>.py` (→ `cli/<sub>/` when it needs siblings) |
| Pure graph analytics | `analysis/<file>.py` |
| Token reporting over transcripts | `usage/<file>.py` |

The test (`01-conventions.md` §3): a module that merely *uses* a domain is not
*part* of it — if a sibling domain with the same need would want it, it is
cross-cutting and goes top-level. `export/graph.py` lives top-level because it
is transport-shaped (graph → bytes), though both `context/build/graph.py` and
the features scaffolder consume it.

## Flagged conflicts (AST wins)

- **Stated rule violated:** §2 says "`cli.<sub>` cannot import another
  `cli.<sub>`". But `cli/check.py:19` does `from .rebuild import run`,
  `cli/refresh.py:5` imports `.migrate`, `cli/reconcile_gate.py:12` imports
  `.memory`, `cli/statusline.py:28` imports `.plan_update`. The shared-helper
  spirit holds (these reuse one entrypoint), but the literal rule is broken in
  ≥4 places — treat sibling-import as a real, if narrow, exception, not a clean
  invariant.
- **Stale rule:** the "new module" table lists `runtime/<file>.py`, but
  `dummyindex/runtime/` does not exist (the doc's own prose admits it was
  removed). Do not create `runtime/` for a new helper unless re-establishing
  the layer deliberately; cross-cutting stdlib helpers currently land in the
  consuming area's `common.py`/`helpers.py`.
