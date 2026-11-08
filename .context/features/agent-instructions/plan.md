# Agent-facing instructions — plan

confidence: INFERRED

## Bounded context

One module, `dummyindex/context/output/instructions.py` (565 lines), emits the three Claude-facing documents. They make a `.context/` index self-navigable without running the CLI: `HOW_TO_USE.md`, `architecture/overview.md`, and `playbooks/*.md`. The boundary is sharp. Every public generator is pure: string in, string out. It has no LLM and no disk read. Side effects live only in three thin `write_*` wrappers. The feature owns no schema and no store. Its mutable surface is four module-level literals.

Two test files guard two contracts. `tests/context/output/test_instructions.py` covers behaviour and `build_all` integration. `tests/test_skills_doc_hygiene.py` covers string-level anti-regression over the generated prose and shipped skills. These string tests lock the hand-authored templates.

## Upstream and downstream

- **Upstream (consumed):** `FilesMap` and `SymbolsMap` (`context.build.maps`), `Meta` (`context.build.meta`), `DocCatalog` and `DocEntry` (`context.domains.source_docs`), and `DOC_CONFIDENCE_ORDER` (`context.enums`). Only `generate_architecture_overview_md` reads these. The static generators have **zero** upstream inputs.
- **Downstream (callers):** `context.build.runner.build_all` drives the three `write_*` wrappers. It records the written paths in `INDEX.md`, asserted at `test_instructions.py:267`. It walks `PLAYBOOK_IDS` (`:522`) to emit one file per playbook.
- **Cycles:** none. The module is a leaf. It imports from `build`, `domains` and `enums`. Only `runner` imports it.

## Patterns named

- **Template-as-constant.** `_HOW_TO_USE` (`instructions.py:23-144`) and `_PLAYBOOK_BODIES` (`:370-519`) are frozen, hand-authored strings. `generate_how_to_use_md` (`:147`) and `generate_playbook_md` (`:525`) return them verbatim. They hold policy and process prose, not index-derived text. `test_skills_doc_hygiene.py` pins them, not structural assertions.
- **Pure generator plus boundary writer.** Each `generate_*` has no side effects. Each `write_*` (`:536`, `:540`, `:557`) is a one-liner that passes the string to `_atomic_write` (`:561-565`). This is the repo's keep-I/O-at-the-boundary convention (`.context/conventions/data-access.md:25`).
- **Tmp-file plus replace.** `_atomic_write` (`:561-565`) writes `path.suffix + ".tmp"`, then calls `replace()`. A concurrent reader never sees a half-written file. **See the divergence below.** It is a local copy, not the canonical helper.
- **Dict-keyed dispatch with KeyError on miss.** `generate_playbook_md` (`:525-530`) indexes `_PLAYBOOK_BODIES[playbook_id]`. It raises `KeyError` listing valid ids. `_role_hint_for` (`:332-334`) is a case-insensitive `_DIR_ROLE_HINTS.get` lookup that returns `None` on a miss.
- **Signal-substring filter, sorted by confidence.** `_select_architecture_docs` (`:348-364`) keeps docs whose filename matches `_ARCH_DOC_SIGNALS` (`:338-346`). It also keeps docs titled "architecture". It drops externals. It sorts by `DOC_CONFIDENCE_ORDER` so the strongest pointer leads.
- **Frozen per-row summary.** `_DirSummary` (`:207`) is the only derived structure. It holds one immutable record per top-level dir. `_group_files_by_top_level_dir` and `_group_symbols_by_top_level_dir` (`:312-331`) build it. Both skip root files.

## Data model

No persistent data model. State is four in-module literals: `_HOW_TO_USE` (`:23-144`), `_DIR_ROLE_HINTS` (`:154-203`), `_ARCH_DOC_SIGNALS` (`:338-346`) and `_PLAYBOOK_BODIES` (`:370-519`). `_DirSummary` exists only during overview generation.

## Decisions (promoted)

- **Templates over generation.** `HOW_TO_USE.md` and the five playbooks encode process prose. It must read cleanly and stay diff-stable. So they are hand-authored constants, locked by string-level tests. They are not assembled from the index. Those tests check the `— via` gate, read-only `reconcile` wording and the `feature_id` and INDEX.json field contract. They reject the known-bad `install --scope user` remedy and a bare `dummyindex --recouncil` verb (`test_skills_doc_hygiene.py:133-211`, `:568-600`). They also pin the codebase-scan ranked-seed contract, which requires `symbolRef` and `evidence` (`:614-676`). Fleet red-flag and identifier guards sit at `:699` and `:722`.
- **Purity and I/O split at the writer boundary.** Generators never touch disk. The `write_*` wrappers and `_atomic_write` isolate the one side effect. Each generator is then a string-compare unit test with no filesystem fixture.
- **AST-derived is truth. Checked-in docs are advisory.** `architecture/overview.md` is computed from maps and meta. Catalog docs are labelled **advisory only** and sorted high-confidence first. Unknown dirs render `_unknown_` instead of a guessed role (`:332-334`).
- **Stable ids are the navigation key.** `feature_id`, not folder name or `id`, keys the navigation table. `PLAYBOOK_IDS` is `sorted(_PLAYBOOK_BODIES)` (`:522`), so emission order is deterministic.

## Divergence to flag (convention vs. code; code wins, fix path below)

`_atomic_write` (`:561-565`) reimplements the tmp-file and replace shape. It does not call the canonical `write_text_atomic` (`domains/atomic_io.py:37-47`). `conventions/data-access.md:7-9, 27` warn against this exact pattern. It loses byte-faithfulness and breaks hash-baselining. Hash-baseline risk is low here, because these files are not equip-managed. The local copy also lacks the Windows `PermissionError` fallback in the cache writer (`pipeline/io/cache.py:98-105`). Candidate cleanup: route `write_*` through `write_text_atomic` and delete `_atomic_write`.

## Open questions

- **No playbook extension seam.** The set is fixed at five: `add-endpoint`, `add-feature`, `add-migration`, `fix-bug` and `refactor`. Adding a kind, such as the `update` recipe that `add-feature` mentions, means editing `_PLAYBOOK_BODIES` directly. Intentional, or a future registration seam?
- **`repo_root` is unused.** `generate_architecture_overview_md` accepts `repo_root` (`:216`) and threads it through `write_*` (`:542`). It never reads it. Is this a vestigial signature, or reserved for per-root logic? The overview comes entirely from the maps.
