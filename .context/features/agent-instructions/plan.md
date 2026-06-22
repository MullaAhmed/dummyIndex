# Agent-facing instructions — plan

confidence: INFERRED

## Bounded context

One module, `dummyindex/context/output/instructions.py` (534 lines), emits the three Claude-facing documents that make a `.context/` index self-navigable **without running the CLI**: `HOW_TO_USE.md`, `architecture/overview.md`, and `playbooks/*.md`. The boundary is sharp: every public generator is pure (string-in / string-out, no LLM, no disk read), and the only side effect lives in three thin `write_*` wrappers. The feature owns no schema and no store — its entire mutable surface is four module-level literals.

Tests guard two distinct contracts: `tests/context/output/test_instructions.py` (behaviour + `build_all` integration) and `tests/test_skills_doc_hygiene.py` (string-level anti-regression over the *generated prose* and the shipped skills — these are what lock the hand-authored templates).

## Upstream / downstream

- **Upstream (consumed):** `FilesMap` / `SymbolsMap` (`context.build.maps`), `Meta` (`context.build.meta`), `DocCatalog` / `DocEntry` (`context.domains.source_docs`), and `DOC_CONFIDENCE_ORDER` (`context.enums`). Only `generate_architecture_overview_md` touches these; the static generators have **zero** upstream inputs.
- **Downstream (called by):** `context.build.runner.build_all` drives all three `write_*` wrappers and records the written paths in `INDEX.md` (asserted at `test_instructions.py:215-237`). `PLAYBOOK_IDS` (`:490`) is the iteration contract `build_all` walks to emit one file per playbook.
- **Cycles:** none. The module is a leaf — it imports from `build`/`domains`/`enums` and is imported only by `runner`.

## Patterns named

- **Template-as-constant** — `_HOW_TO_USE` (`instructions.py:24-109`) and `_PLAYBOOK_BODIES` (`:338-487`) are frozen hand-authored strings returned verbatim by `generate_how_to_use_md` (`:112`) and `generate_playbook_md` (`:493`). They are policy/process prose, not synthesized from the index, and are pinned by `test_skills_doc_hygiene.py` rather than by structural assertions.
- **Pure generator + boundary writer** — each `generate_*` is side-effect-free; each `write_*` (`:505`, `:509`, `:526`) is a one-liner that pipes the generated string into `_atomic_write` (`:530-534`). This is the repo's keep-I/O-at-the-boundary convention (`conventions/data-access.md:25`).
- **Tmp-file + replace** — `_atomic_write` (`:530-534`) writes `path.suffix + ".tmp"` then `replace()`s, so a concurrent reader never sees a half-written file. **See the divergence flagged below** — it is a local reimplementation, not the canonical helper.
- **Dict-keyed dispatch with KeyError-on-miss** — `generate_playbook_md` looks up `_PLAYBOOK_BODIES[playbook_id]` and raises `KeyError` listing valid ids (`:493`); `_role_hint_for` is a case-insensitive `_DIR_ROLE_HINTS.get` returning `None` on miss (`:300-301`).
- **Signal-substring filter, confidence-sorted** — `_select_architecture_docs` (`:316-332`) keeps catalog docs whose filename matches `_ARCH_DOC_SIGNALS` (`:306-313`) or whose title names "architecture", drops externals, and sorts by `DOC_CONFIDENCE_ORDER` so the highest-confidence pointer leads.
- **Frozen per-row summary** — `_DirSummary` (`class at :172`) is the only derived structure: one immutable record per top-level dir, built during overview generation from `_group_files_by_top_level_dir` / `_group_symbols_by_top_level_dir` (`:280`, `:290`, both skip root files).

## Data model

No persistent data model. State is four in-module literals — `_HOW_TO_USE` (`:24-109`), `_DIR_ROLE_HINTS` (`:119-168`), `_ARCH_DOC_SIGNALS` (`:306-313`), `_PLAYBOOK_BODIES` (`:338-487`) — plus the per-directory `_DirSummary` dataclass (`class at :172`) materialized transiently during `generate_architecture_overview_md`.

## Decisions (promoted)

- **Templates over generation.** `HOW_TO_USE.md` and the five playbooks encode process prose that must read cleanly and stay diff-stable, so they are hand-authored constants locked by string-level tests — not assembled from the index. Consequence: `test_skills_doc_hygiene.py` is load-bearing, asserting the prose carries the `— via` gate, read-only `reconcile` wording, the `feature_id`/INDEX.json field contract, and never the known-bad `install --scope user` remedy or a bare `dummyindex --recouncil` verb (`test_skills_doc_hygiene.py:42-80`).
- **Purity / I-O split at the writer boundary.** Generators never touch disk; `write_*` + `_atomic_write` isolate the only side effect, making every generator a trivial unit test (string compare, no fs fixture).
- **AST-derived-is-truth; checked-in docs are advisory.** `architecture/overview.md` is computed from the maps/meta; surfaced `DocCatalog` entries are labelled **advisory only** and sorted high-confidence-first. Unknown dirs degrade to `_unknown_` rather than guessing a role (`:300-301`).
- **Stable ids as the navigation key.** `feature_id` (not folder name, not `id`) keys HOW_TO_USE's navigation table; `PLAYBOOK_IDS` is `sorted(_PLAYBOOK_BODIES)` (`:490`) so emission order is deterministic across runs.

## Divergence to flag (convention vs. code — code wins, but worth a fix path)

`_atomic_write` (`:530-534`) **reimplements** the tmp-file + replace shape instead of calling the canonical `write_text_atomic` (`domains/atomic_io.py:11-24`). The data-access convention explicitly warns against exactly this: "Don't bypass `write_text_atomic` with a plain reimplementation — you lose byte-faithfulness *and* break hash-baselining" (`conventions/data-access.md:7-9, 27`). For agent-instruction docs the hash-baseline risk is low today (these files are not equip-managed), but the local copy also misses the Windows `PermissionError` fallback that the cache writer carries (`pipeline/io/cache.py:98-105`). Candidate cleanup: route `write_*` through `write_text_atomic` and delete `_atomic_write`.

## Open questions

- **No playbook extension seam.** The set is fixed at five (`add-endpoint`, `add-feature`, `add-migration`, `fix-bug`, `refactor`); adding a kind — e.g. the `update` recipe referenced hypothetically inside `add-feature` — means editing `_PLAYBOOK_BODIES` directly. Intentional, or a future registration seam?
- **`repo_root` is accepted but unused** in `generate_architecture_overview_md` (param at `:181`, threaded through the `write_*` wrapper at `:511`) — vestigial signature or reserved for per-root logic? The overview is computed entirely from the maps.
