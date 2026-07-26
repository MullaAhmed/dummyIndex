# Plan — graph consumption upgrade

Waves honor dependencies; items within a wave are independent and parallel.
Every item: tests first (repo standard), respect `conventions/coding-practices.md`
(frozen dataclasses, enum constants, typed exceptions, wire-only `cli/<sub>.py`,
file-size caps), run the affected test files before ticking.

## Wave A (parallel, independent)

**A1 — query verbs.** New `ContextSubcommand.GRAPH` in `context/enums.py`;
wire-only `cli/graph.py` added to the dispatch dict in `cli/__init__.py`
(mirror `cli/scan.py`); domain logic in new
`context/domains/graph_query.py` (load `features/symbol-graph.json` node-link
via networkx, no new store). Verbs: `callers-of <sym>`, `callees-of <sym>`,
`impact <sym> [--depth N]`, `path <a> <b>`, `neighbors <sym> [--hops N]`,
`dead-code`, `community <id|name>`. Bounded output with `--limit`; every row
cites `source_file:source_location`; attach the docstring from the co-located
`rationale_for` node when present. Symbol lookup accepts node id, bare name,
or `path:name` with unambiguous-prefix matching; ambiguity lists candidates.
`--json` for machine output. Typed errors for missing artifact / unknown
symbol.

**A2 — deterministic builders.** In `context/build/graph.py` (or sibling
`context/build/communities.py` if size caps demand): after `symbol-graph.json`
is written, (1) compute personalized PageRank (`networkx.pagerank`,
personalization seeded on entry-point symbols and non-test files; test files
down-weighted ~0.1 — bakeoff showed test nodes dominate degree signal) and
write a ranked shortlist consumed by `features/scan/seed.py` so the seed's
node selection + ordering is rank-driven (keep the existing per-feature
`service` collapse as fallback when the symbol graph is absent); (2) roll
communities up into `features/graph-communities.json` — frozen dataclass
models beside `features/scan/models.py`; per community: stable slug (dominant
feature id + top member name, NOT the raw Leiden integer — ids renumber
between runs), size, top-k members by PageRank (with `path:line`), owning
feature from `features/INDEX.json`, one-line summary (deterministic: top
member docstrings; the council may overwrite later). Wire both into
`context/build/enriched_refresh.py` so `rebuild --changed` regenerates them
while preserving INFERRED `graph.json` exactly as today.

**A3 — schema extension.** `features/scan/models.py`: optional `symbol_ref`
(`symbolRef` on wire) + `evidence` (`EXTRACTED`|`INFERRED`) on `ScanNode`,
emitted via `_put`. `features/scan/validate.py` + `constants.py`:
MAX_SCAN_NODES 60 → 120 (edges 120 → 240); validate `evidence` against the
enum; when a symbol graph / communities artifact is present, validate each
`symbolRef` resolves (referential integrity across artifacts) — absent
artifacts degrade to a warning, not an error. Old scans without the new
fields must still pass.

**A4 — extractor dispatch fix (narrow).** In `pipeline/extract/` (python
resolver): (1) dict literals whose values are `module.attr` / bare function
references inside enum-keyed mappings become `calls` edges from the mapping's
enclosing scope to the referenced symbol; (2) function-body `from X import Y`
becomes an `imports_from` edge attributed to the enclosing function's module.
Precision over recall: only resolve references that match a known extracted
symbol; tests pin both patterns using this repo's own
`cli/__init__.py` dispatch dict and `cli/rebuild.py`-style local imports as
fixtures.

## Wave B (after A2 + A3)

**B1 — council prompt rewrite.** `skills/council/58-codebase-scan.md`: the
draft is now the ranked seed — instruct EDIT (rename, merge, promote the AI
surface, set edge verbs/labels), not invent; groups come from
`graph-communities.json` communities/features, not improvisation; require
`symbolRef` on every repo-owned node and `evidence` per node (EXTRACTED =
kept from seed verbatim, INFERRED = added/renamed); update "Checks before you
call this done" and the caps text (aim 40–80 of 120). Touch `skills/skill.md`
/ `council/00-overview.md` references if counts/wording changed.

**B2 — viewer three-tier zoom + focus+expand.** `context/output/viewer/`
(`script.py`, `styles.py`, `__init__.py`): tier 1 curated map (default,
unchanged); tier 2 community aggregate (one supernode per
`graph-communities.json` entry, edge weights = cross-community call volume);
tier 3 click-to-expand a curated node into its top-k symbol-graph neighbors
from a precomputed expansion index inlined at render time (k≈8 per node,
hard total budget ≤ 300KB — enforce in Python at embed time, truncate by
rank). Render `evidence`/confidence distinctly (solid vs dashed border).
Keep: no CDN, no fetch, `_embed()` neutralization, `safeKind` closed
alphabet; extend the existing escape discipline to all new interpolation
sinks (the v2 commit closed two XSS paths — do not reopen).

## Wave C (after all)

**C1 — review.** Opus adversarial review of the full diff (conventions,
security of new HTML sinks, layering, wire-only CLI); fix findings.

**C2 — prove it on this repo.** Full test suite; `dummyindex context rebuild
--changed`; `scan-check`; then author the curated scan for THIS repo from the
new ranked seed (the council stage that never ran) and re-render
`graph.html`; docs: `docs/guide/04-data-model.md`, `docs/guide/07-cli.md`,
`docs/COMMANDS.md`, CHANGELOG.
