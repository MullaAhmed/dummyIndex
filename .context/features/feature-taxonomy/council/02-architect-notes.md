# Architect notes — stage 2 (feature-taxonomy plan)

## What I changed

- Added a **Bounded context** section drawing a sharp line: this domain owns the *shape of the taxonomy on disk*, not clustering (upstream) and not enriched prose (council/reconcile author it; this domain only places + preserves).
- Added a **Two op families** section naming the load-bearing `ops.py` (id-driven, edits existing folders) vs `placement.py` (file-set-driven, reconciles files↔taxonomy) split — previously only implied.
- Added an explicit **Dependencies** section (upstream / downstream / cycles) — this was the biggest gap; surfaced that `map/symbols.json` is the *only* cross-domain read and it is read-only, and proved no cycle.
- Verified every cited symbol against `map/symbols.json` and corrected location anchors to symbol start-lines (`builder._write_all` 280→237; reserved-id check relocated to `_validate_placement_id` `placement.py:395`; placement INDEX helpers re-anchored to 489/512/528).
- Promoted the section-gating constant to its literal value (`_CANONICAL_SECTIONS = {"spec","plan","concerns"}`, `cli/features.py:19`) and folded the old standalone "section-name gating" Open-question into Key decisions as a settled decision (CLI is the boundary), leaving only the docstring-correction as the residual open item.
- Cut filler: removed the redundant prose restating member-derivation twice; tightened "Where it lives" into per-concern bullets with `path:line` anchors.

## Patterns named

- Atomic feature-folder ops: validate-before-write + tmp-file+`replace` (`helpers.py:131-140`), a local reimplementation of `atomic_io.write_text_atomic` (`atomic_io.py:11-24`, convention `data-access.md`).
- Member derivation from symbols, never re-cluster: `_members_for_files` (`placement.py:457`) over the file set; clustering happens once in `scaffold_features` (`builder.py:35`).
- Hand-maintained INDEX.json: `_append_index_entry`/`_update_index_counts`/`_drop_index_entry` (`placement.py:489/512/528`); INDEX.md + graph regenerated from disk (`indexes.py:19/34`).
- Reserved-id guard: `_validate_placement_id` (`placement.py:395`) rejecting `community-*`.
- Parser-artifact filter: `_is_parser_artifact` (`builder.py:176`).

## Dependencies surfaced

- Upstream: `map/symbols.json` (read-only, the only cross-domain read), the call/community graph into `scaffold_features`, convention `data-access.md`.
- Downstream: `cli/features.py` (sole caller, exit-2 mapping, all I/O), the reconcile procedure + council (drive the ops; `reconcile-stamp` gates on `.pending-enrichment`), the HTML viewer (consumes `graph.json` by data contract only).
- Cycles: none. Intra-domain edges run helpers→models→{ops,placement,indexes,render,builder}→__init__; `ops` and `placement` are siblings sharing only helpers/models/errors. Single outward edge is read-only.

## Decisions promoted

- **CLI is the section-name boundary** (not the domain) — moved from Open questions to Key decisions; `write_section` accepting any slug-safe section is intentional, the gate is `_validate_section_name` (`cli/features.py:210`).
- **The two-op-family split is the architecture** — promoted to its own section so future edits respect that `ops` and `placement` must not call each other (sibling-only coupling through `helpers`/`models`/`errors`).
