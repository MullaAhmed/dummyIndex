# Agent-facing instructions — plan

confidence: INFERRED

## Where it lives

`dummyindex/context/output/instructions.py` — the sole module. Tests: `tests/context/output/test_instructions.py` (unit + `build_all` integration) and `tests/test_skills_doc_hygiene.py` (string-level anti-regression guards over the generated prose and shipped skills). Inputs come from sibling builders: `FilesMap`/`SymbolsMap` (`context.build.maps`), `Meta` (`context.build.meta`), `DocCatalog`/`DocEntry` (`context.domains.source_docs`), and the `DOC_CONFIDENCE_ORDER` enum (`context.enums`). Writers are driven by `context.build.runner.build_all`, which lists the written files in `INDEX.md`.

## Architecture in three sentences

Two kinds of generator share one module: static templates (`HOW_TO_USE.md`, the five playbooks) that return frozen hand-authored strings, and one derived generator (`architecture/overview.md`) that folds the file/symbol maps + meta + optional doc catalog into markdown. Every generator is pure (string-in/string-out, no LLM, no side-effecting I/O), so each has a thin `write_*` wrapper that calls `_atomic_write` (`tmp` file + `replace`) to land it on disk crash-safely. Playbook selection is a dict lookup keyed by id, with `KeyError` on miss and `PLAYBOOK_IDS` exporting the sorted catalog for callers to iterate.

## Data model

No persistent data model — the feature owns no schema or store. State is three in-module literals: `_HOW_TO_USE` (the navigation template, `instructions.py:24-109`), `_DIR_ROLE_HINTS` (dir-name → role-hint lookup, `:119-168`) plus `_ARCH_DOC_SIGNALS` (arch-filename substrings, `:306-313`), and `_PLAYBOOK_BODIES` (five id → markdown recipes, `:338-487`). The only derived structure is the frozen `_DirSummary` dataclass (`:171-177`) built per top-level directory during overview generation.

## Key decisions

- **Templates over generation.** HOW_TO_USE and playbooks are hand-authored constants, not assembled from the index — they encode policy/process prose that must read cleanly and stay diff-stable, so they are locked by string-level tests rather than synthesized.
- **Purity + atomic write split.** Generators never touch disk; `write_*` + `_atomic_write` isolate I/O at the boundary, matching the repo's CLI-boundary-I/O convention and making the generators trivially unit-testable.
- **Heuristic, advisory architecture.** The overview is explicitly AST-derived-is-truth; checked-in arch docs are surfaced only as advisory pointers sorted by confidence, and unknown dirs degrade to `_unknown_` rather than guessing.
- **Stable ids.** `feature_id` (not folder name) is the navigation key throughout HOW_TO_USE; playbook ids are sorted into `PLAYBOOK_IDS` so iteration order is deterministic.

## Open questions

- Playbook set is fixed at five with no extension seam — adding a kind (e.g. `update`, referenced as a hypothetical in `add-feature`) means editing `_PLAYBOOK_BODIES` directly. Intentional or a future seam?
- `repo_root` is a parameter of `generate_architecture_overview_md` but unused in the body — vestigial signature or reserved for future per-root logic?
