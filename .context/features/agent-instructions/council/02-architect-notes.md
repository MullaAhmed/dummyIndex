# Architect notes — agent-instructions (stage 2)

## What I changed

- Replaced the "Where it lives" + "Architecture in three sentences" prose with a sharper **Bounded context** (one 534-line module, pure generators + thin writers, owns no schema) and split dependencies into an explicit **Upstream / downstream** section.
- Added a **Patterns named** section, each pattern anchored at `path:range` (template-as-constant, pure-generator/boundary-writer, tmp+replace, dict-dispatch-KeyError, signal-substring confidence-sort, frozen per-row summary).
- Promoted the four key decisions and tied "templates over generation" to the load-bearing `test_skills_doc_hygiene.py:42-80` guards (the thing that actually enforces it).
- Cut filler: dropped restating the spec's user-visible behaviour; kept the plan architectural.
- Corrected a stale range: `_DirSummary` was cited `:171-177`; verified `class _DirSummary` is at `:172` and relabelled it `class at :172`.

## Patterns named

- Template-as-constant — `_HOW_TO_USE` `instructions.py:24-109`, `_PLAYBOOK_BODIES` `:338-487`.
- Pure generator + boundary writer — `generate_*` vs `write_*` `:505/:509/:526` → `_atomic_write` `:530-534`.
- Tmp-file + replace — `_atomic_write` `:530-534`.
- Dict-keyed dispatch, KeyError-on-miss — `generate_playbook_md` `:493`; `_role_hint_for` `:300-301`.
- Signal-substring filter, confidence-sorted — `_select_architecture_docs` `:316-332` over `_ARCH_DOC_SIGNALS` `:306-313`.
- Frozen per-row summary — `_DirSummary` `class at :172` from `_group_*` `:280/:290`.

## Dependencies surfaced

- Upstream: `FilesMap`/`SymbolsMap` (`context.build.maps`), `Meta` (`context.build.meta`), `DocCatalog`/`DocEntry` (`context.domains.source_docs`), `DOC_CONFIDENCE_ORDER` (`context.enums`) — consumed only by the overview generator; static generators have zero inputs.
- Downstream: `context.build.runner.build_all` drives the three `write_*` and lists outputs in `INDEX.md` (`test_instructions.py:215-237`); walks `PLAYBOOK_IDS` `:490`.
- Cycles: none — leaf module.

## Decisions promoted

- Templates over generation (locked by `test_skills_doc_hygiene.py:42-80`, not structural tests).
- Purity / I-O split at the writer boundary.
- AST-derived-is-truth; checked-in arch docs advisory-only, confidence-sorted; unknown dirs → `_unknown_`.
- Stable `feature_id` / sorted `PLAYBOOK_IDS` as deterministic navigation keys.

## Divergence flagged (convention vs. code)

`_atomic_write` (`:530-534`) reimplements tmp+replace instead of calling the canonical `write_text_atomic` (`domains/atomic_io.py:11-24`). `conventions/data-access.md:7-9,27` warns this loses byte-faithfulness / hash-baselining and the local copy also lacks the Windows `PermissionError` fallback (`pipeline/io/cache.py:98-105`). Recorded as a candidate cleanup in the plan, not edited (source is out of scope).
