# Folder organization

How source under `dummyindex/` is grouped, and where a new file goes.

## The organizing axis: domain-first, then layered

This repo groups code **by domain**. A feature owns its logic, data, and on-disk output in one directory. Code is also arranged in a **strict import layering**. Both rules are stated in `docs/reference/01-conventions.md` §1–§3. That doc is graded **low confidence** in `source-docs/INDEX.json`. Its prose cites many code paths, which trips broken-ref detection. Its *structure* claims still cross-check clean against the live tree. So they are reused here with `path:range` evidence.

Top-level layers (`.context/tree.json`, real dirs):

| Dir | Role |
|---|---|
| `pipeline/` | deterministic backbone: tree-sitter extract → structure/graph |
| `analysis/` | graph analytics on pipeline output (`analysis/cluster.py` — Leiden) |
| `export/` | render graph → on-disk JSON (`export/graph.py:to_json`) |
| `context/` | the `.context/` engine: `build/` (lifecycle), `output/` (renderers), `domains/` (behaviour) |
| `cli/` | one wire-only dispatcher module per subcommand |
| `installer/`, `usage/`, `skills/` | install surface, transcript token reporting, bundled markdown |

Import direction (verified): `context → analysis, pipeline`. `analysis →
pipeline`. `pipeline →` stdlib/third-party only. `usage/` is stdlib-only. Its files import nothing under `dummyindex.*`. `context/domains/*` never imports `cli`. Grep is clean except a docstring in `equip/__init__.py:6`.

## The CLI / domain split (the load-bearing pattern)

`cli/<sub>.py` is **wire-only**. It parses argv, lazy-imports a domain function, then prints and exits. Logic lives under `context/domains/<x>/`. See `cli/query.py:7-15`. `run(args)` imports `query, render_json` from `context.domains.query` inside the function body. `cli/features.py:35-36` does the same. New CLI work follows this shape. Never put business logic in `cli/`.

## How a domain directory is split

A `.context/` domain that outgrows one file splits into canonical concern files. `context/domains/features/` demonstrates this:

- `models.py`: frozen dataclasses, data only (`features/models.py`)
- `constants.py` / `enums.py`: fixed-alphabet constants (`features/constants.py`)
- `errors.py`: typed exceptions (`features/errors.py:FeatureRenameError`)
- `helpers.py` / `ops.py` / `builder.py` / `render.py`: behaviour, grouped by verb
- `__init__.py`: public re-export surface

A domain past ~10 modules **nests by concern**. Example: `context/domains/equip/` splits into `generate/ plugins/ lifecycle/ wiring/` (`equip/generate/catalog.py`, `equip/wiring/safety.py`, …). A CLI subcommand with private siblings becomes a package too: `cli/equip/`, `cli/build_loop/`.

**Filenames never carry a leading underscore.** Privacy is the package boundary (`__init__.py`) and the function level (`_name`). Not the filename.

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

Test (`01-conventions.md` §3): a module that merely *uses* a domain is not *part* of it. If a sibling domain with the same need would want it, it is cross-cutting. Such modules go top-level. `export/graph.py` lives top-level. It is transport-shaped (graph → bytes). Both `context/build/graph.py` and the features scaffolder consume it anyway.

## Flagged conflicts (AST wins)

- **Stated rule violated:** §2 says "`cli.<sub>` cannot import another `cli.<sub>`". But `cli/check.py:19` does `from .rebuild import run`. `cli/refresh.py:5` imports `.migrate`. `cli/reconcile_gate.py:12` imports `.memory`. `cli/statusline.py:28` imports `.plan_update`. Shared-helper spirit holds: these reuse one entrypoint. Literal rule breaks in ≥4 places. Treat sibling import as a real, narrow exception, not a clean invariant.
- **Stale rule:** the "new module" table lists `runtime/<file>.py`. But `dummyindex/runtime/` does not exist. The doc's own prose admits it was removed. Do not create `runtime/` for a new helper. Re-establish the layer only deliberately. Cross-cutting stdlib helpers currently land in the consuming area's `common.py`/`helpers.py`.
