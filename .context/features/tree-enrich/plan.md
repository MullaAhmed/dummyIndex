# Tree abstract enrichment — plan

`confidence: INFERRED`

## Where it lives

- `dummyindex/context/domains/enrich.py` — selection, batching, `tree.json` writeback.
- `dummyindex/cli/enrich.py` — `run_plan` (`:12-51`), `run_apply` (`:54-123`): validation, plan
  path, exit codes.
- Consumed, not owned: authoring (`dummyindex/skills/council/52-tree-enrich.md:49-76`),
  stage scheduling (`dummyindex/context/domains/council_batch.py:62-77`), layout migration
  (`dummyindex/context/build/upgrade.py:501-552`). Own tests: `tests/context/domains/test_enrich.py:35-296`;
  co-clustered tests are noise.

## Architecture in three sentences

`run_plan` calls `build_plan` (pre-order `_walk` selecting `EXTRACTED` or `source-stale` nodes,
`dummyindex/context/domains/enrich.py:86-173`), migrates the layout only after that succeeds, then
writes `.context/cache/_enrich_plan.json` (`dummyindex/cli/enrich.py:28-39`). The host session
authors a `{node_id: abstract}` mapping out of process; no Python model client. `run_apply`
validates it and `apply_updates` writes known IDs (abstract, `INFERRED`, `source-stale` dropped)
and reports unknown ones (`dummyindex/context/domains/enrich.py:198-218`, `:259-276`).

## Patterns named

- Two-phase plan/apply via a file hand-off (`dummyindex/context/domains/enrich.py:176-181`, `:198-218`),
  behind a table dispatcher (`dummyindex/cli/__init__.py:91-92`).
- Wire-only CLI handler (`.context/conventions/coding-practices.md:55-62`) at
  `dummyindex/cli/enrich.py:12-123`, except `json.loads` (`:100`): malformed JSON crashes (exit `1`).
- Frozen records + `to_dict()` (`dummyindex/context/domains/enrich.py:24-83`, `:184-195`);
  `range: list`/`stats: dict` break the tuple-only rule (`.context/conventions/coding-practices.md:10-12`).
- Hand-rolled tmp+`replace` with a fixed `<name>.tmp` (`dummyindex/context/domains/enrich.py:179-181`,
  `:215-217`), not the unique-temp `write_text_atomic` (`.context/conventions/data-access.md:7`); rationale unstated.

## Dependencies surfaced

- Upstream code: `ConfidenceLevel` (`dummyindex/pipeline/enums.py:13`) is the domain's sole
  first-party import.
- Upstream data: `write_tree` seeds `EXTRACTED` stubs (`dummyindex/context/build/runner.py:370`);
  `refresh_tree` keeps annotated abstracts across `rebuild --changed` and is the only
  `source-stale` producer (`dummyindex/context/build/navigation_refresh.py:133-153`).
- Downstream: `estimate_run` counts `plan.nodes` per feature, so the selection predicate drives
  fleet estimates (`dummyindex/context/domains/fleet.py:423-435`); `active_stages` appends
  `CouncilStage.TREE` in every mode unless `--no-tree-enrich`
  (`dummyindex/context/domains/council_batch.py:75-76`, `dummyindex/cli/council_batch.py:102-105`).
- Cycles: none at import level. Data cycle via `tree.json`: apply sets `INFERRED` → `refresh_tree`
  flags drift → `build_plan` reselects → apply clears the label.

- Per-file batches permit incremental authoring and application. `structure`
  contains project/directories; file heads remain in their file batches
  (`dummyindex/context/domains/enrich.py:137-164`). A host choosing skeleton-only
  work must filter node kinds, not assume every file is in `structure`.
- Apply accepts any current tree ID, not only IDs from the latest worklist.
  Unknown IDs are reported after known updates are written; the CLI exits `1`
  for that partial result. It is not an all-or-nothing rejection
  (`dummyindex/context/domains/enrich.py:217-227`,
  `dummyindex/cli/enrich.py:116-129`).
- Temp-file replacement protects each completed write from a partial-file
  publish. It does not provide a project lock or detect an intervening tree
  generation (`dummyindex/context/domains/enrich.py:185-190`,
  `dummyindex/context/domains/enrich.py:223-226`).
- Current workflow prose disagrees on light mode: the phase says on in every
  mode, while the mode table says skip. That is an unresolved orchestration
  contradiction; the mode-agnostic domain cannot settle it
  (`dummyindex/skills/skill.md:341-347`,
  `dummyindex/skills/council/52-tree-enrich.md:11-12`,
  `dummyindex/skills/council/52-tree-enrich.md:34-43`).

No database. `tree.json` node fields are read at `dummyindex/context/domains/enrich.py:109-124` and
written at `:259-273`; `_enrich_plan.json` is `SCHEMA_VERSION = 1` (`:21`; shapes in `spec.md`).
`stats.stub_nodes` includes stale nodes (`:156-160`).

## Key decisions

- Decided per-file `file_subtree` batches because partial progress must survive an interrupted
  session (`dummyindex/context/domains/enrich.py:3-5`). `structure` holds only project/dir nodes;
  file heads stay in their file batch (`:126-130`).
- Decided `source-stale` nodes re-enter at any confidence because `refresh_tree` preserves
  annotated abstracts instead of resetting them (`dummyindex/context/build/navigation_refresh.py:133-153`).
- Decided `enrich-plan` runs the full layout migration because reconcile-only repos never run a
  full build, with `package_version=None` because it does not extract; the plan is gitignored
  scratch under `cache/` (`dummyindex/cli/enrich.py:33-37`). Cost: retired paths are deleted or
  backed up (`dummyindex/context/build/upgrade.py:300-307`), and the `LayoutMigration` the build
  callers keep (`dummyindex/context/build/runner.py:126`) is discarded, so failures are silent.
- Decided unknown IDs are reported, not rejected, as likely typos (`dummyindex/context/domains/enrich.py:190-191`);
  known updates are already written when the CLI exits `1` (`dummyindex/cli/enrich.py:110-123`).
  Any tree ID is accepted.
- Decided apply is idempotent per node (`dummyindex/context/domains/enrich.py:7`, `:264-267`);
  `tree.json` is still rewritten (`:215-217`); no lock or generation check.
- Decided mode scoping is the host's, for cost control
  (`dummyindex/skills/council/52-tree-enrich.md:34-47`); the domain takes no mode.

## Open questions

- Is discarding `LayoutMigration` in `run_plan` deliberate?
- Light mode: code schedules `CouncilStage.TREE` in light, so "light skips"
  (`dummyindex/skills/skill.md:334`, `dummyindex/skills/council/52-tree-enrich.md:41`) is stale;
  which kinds light authors is undocumented. `dummyindex/skills/skill.md:334-335` also puts files in `structure`.
- Untested: `source-stale` selection/label clearing, retired-path removal via `enrich-plan`,
  malformed JSON to `enrich-apply`.
