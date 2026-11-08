## Product surface

`dummyindex/skills/council/52-tree-enrich.md` and `dummyindex/skills/skill.md` are catalog
`low` (`.context/source-docs/INDEX.json`); every citation of them below is the shipped
instruction surface, never authority on behavior — behavior claims are checked in code.

- **Running council stage 5 for several features** — `_units_for_feature` emits one
  `dev` unit per feature at `CouncilStage.TREE`, and the loop dispatches every unit
  in one message with the `agents/dev.md` persona inlined
  (`dummyindex/context/domains/council_batch.py:213-222`,
  `dummyindex/skills/council/22-parallel-dispatch.md:10-24`, catalog `high`);
  `dummyindex/skills/agents/dev.md` has no tree-enrich, `enrich-plan` or
  `enrich-apply` instruction. `enrich-plan`/`enrich-apply` take no feature
  (`dummyindex/cli/enrich.py:12-51`, `dummyindex/cli/enrich.py:54-123`), so nothing
  assigns a unit a feature-scoped node subset. The procedure instead describes one
  architect (standard) or one dev per `file_subtree` (deep), with the conductor
  merging and applying (`52-tree-enrich.md:39-76`), and has no per-feature stage-5
  `council-log` step — no mapping between the two dispatch shapes exists. If units do
  run the verbs, each apply replaces the whole `tree.json` through a fixed
  `tree.json.tmp` (`dummyindex/context/domains/enrich.py:205-217`). At HEAD no
  `_council-log.json` holds a stage-5 entry and all 6445 nodes are `EXTRACTED`.
- **Choosing light mode** — `active_stages` appends `TREE` in every mode unless
  `--no-tree-enrich` (`dummyindex/context/domains/council_batch.py:62-77`,
  `dummyindex/cli/council_batch.py:105`), and `is_stage_complete` is `False` for a
  stage with no log entry (`dummyindex/context/domains/council.py:163-180`) — a
  conductor following "light skips" (`dummyindex/skills/skill.md:334`,
  `dummyindex/skills/council/52-tree-enrich.md:41`) without logging `skipped` per
  feature keeps receiving stage-5 units and `batch.complete` stays false. Both `low`
  docs also state the opposite (`dummyindex/skills/skill.md:339-340`,
  `dummyindex/skills/council/52-tree-enrich.md:11-12`); code and
  `22-parallel-dispatch.md:28-30` (`high`) win. Neither doc names the `skipped` status.
- **Reading exit 1 from `enrich-apply`** — exit `1` means either "known IDs written,
  `tree.json` replaced, some IDs unknown" (`dummyindex/context/domains/enrich.py:209-218`,
  `dummyindex/cli/enrich.py:110-122`) or "nothing written, `JSONDecodeError`
  traceback" (`dummyindex/cli/enrich.py:100`). The traceback path covers truncated JSON
  and a UTF-8 BOM (read as `encoding="utf-8"`; probe: `Unexpected UTF-8 BOM (decode
  using utf-8-sig)`) when the mapping is written with Windows PowerShell 5.1 `Out-File`
  (BOM by default) rather than the `Write` the procedure names (`52-tree-enrich.md:67`); a
  directory passes the `exists()` check (`:87`) and crashes in `read_text` — only the
  shape error has a message and exit `2` (`:101-108`). The unknown-ID warning cannot
  tell a typo from an ID renamed by a rebuild: apply never reads the plan or its
  `generated_at` (`dummyindex/context/domains/enrich.py:161-163`), only current-tree
  membership (`:209-211`).
- **Authoring the skeleton a retrieval walk reads first** — the `structure` batch
  holds only project/dir nodes (`dummyindex/context/domains/enrich.py:126-130`; probe:
  70 nodes) although `dummyindex/skills/skill.md:334-335` says it includes files; each
  of the 553 file heads is `node_ids[0]` of its own `file_subtree` batch
  (`dummyindex/context/domains/enrich.py:128-130`, `:147-154`). All 70
  project/dir nodes carry `evidence_files: []` because `_walk` yields no file for them
  (`dummyindex/context/domains/enrich.py:123`, `:224-233`), yet authors are told to read
  `evidence_files` and keep the stub wording when evidence is thin
  (`dummyindex/skills/council/52-tree-enrich.md:60-64`); that stub is
  `Directory at <path>/ (N immediate children).` (`dummyindex/context/build/tree.py:177-180`).
  Symbol `range` is `[start, start]` (`dummyindex/context/build/tree.py:232-233`;
  5822/5822), a start line, not a span.
- **Reconciling after a one-line edit** — `refresh_tree` adds `source-stale` to an
  annotated node when any changed path is at or under its `path`, and the project
  node (`path "."`) matches every change (`dummyindex/context/build/navigation_refresh.py:125-132`,
  `:150-153`); symbols share their file's `path`, so one edit re-queues the file, every
  annotated symbol in it, each ancestor dir and the project. For a stale `INFERRED`
  node, `stub_abstract` carries the prior prose (`dummyindex/context/domains/enrich.py:122`);
  "keep the stub's wording" (`dummyindex/skills/council/52-tree-enrich.md:63-64`) then
  yields an identical abstract, which `_apply` skips without clearing `source-stale`
  (`dummyindex/context/domains/enrich.py:264-273`), so the node reports no update and
  every later plan reselects it (`:110-113`). A zero update count does not mean stale
  labels cleared.
- **Deep mode on this repo** — read-only `build_plan` over the working-tree
  `tree.json`: 6445 stub nodes, 554 batches (1 `structure` + 553 `file_subtree`, max
  130 nodes), 5822 symbols. Per `dummyindex/skills/council/52-tree-enrich.md:43`,
  `:72-73` that is 553 dev dispatches and 553 full read-serialize-replace cycles of
  `tree.json`, which also run for `{}` or an identical mapping
  (`dummyindex/context/domains/enrich.py:205-217`) — the doc's "no-op" is no-op in
  content only. The CLI prints `batches: 554` without splitting batch kinds
  (`dummyindex/cli/enrich.py:46-50`). `estimate_run` counts the tree stage as one unit
  per feature in every mode, counts symbol stubs in standard/light, and hardcodes
  `tree_enrich=True` (`dummyindex/context/domains/fleet.py:414-435`), so it understates
  deep fan-out and estimates stage 5 for `--no-tree-enrich` runs. Each in-file stub
  triggers a root-down DFS for its file node (`dummyindex/context/domains/enrich.py:131-136`,
  `:236-244`; probe: 2.27 s), repeated by `estimate_run` (`fleet.py:424`).
- **Duplicate node IDs and file-batch names** — the working-tree `tree.json` holds 8
  IDs twice under the same file parent (e.g. `rebuild_run`); children are built once
  per hierarchy edge without dedupe (`dummyindex/context/build/tree.py:82-87`, `:200-205`).
  `stubs: 6445` therefore covers 6437 distinct IDs (`dummyindex/context/domains/enrich.py:158`),
  and `_apply` appends per matching node: `{"rebuild_run": …}` returns
  `['rebuild_run', 'rebuild_run']` and prints `updated 2 abstract(s)`
  (`dummyindex/context/domains/enrich.py:259-276`, `dummyindex/cli/enrich.py:111-114`).
  Batch `name` is the file basename and a batch carries no path
  (`dummyindex/context/domains/enrich.py:37-43`, `:128-130`, `:147-154`): 51 names repeat
  (`__init__.py` × 64), so keying deep-mode progress or the per-file `dev-pick`
  (`dummyindex/skills/council/52-tree-enrich.md:56-58`) on batch name collides.
- **Running `enrich-plan` to check remaining work** — every call first runs
  `migrate_context_layout` (`dummyindex/cli/enrich.py:37`): merges managed
  `.gitignore`/`.gitattributes`, deletes the legacy root `_enrich_plan.json`, retires
  `equipment-evals/` and `graph/` (unedited starter suites deleted, others backed up
  under `_doc_backups/retired/<version>/`) (`dummyindex/context/build/upgrade.py:300-307`,
  `:501-552`). The returned `LayoutMigration` is discarded, though
  `format_migration_report` (`dummyindex/context/build/upgrade.py:577-615`) exists and
  `rebuild` prints it (`dummyindex/cli/rebuild.py:138-145`); help says only "Emit
  .context/cache/_enrich_plan.json (work-list)" (`dummyindex/cli/help.py:108`). Removals,
  backups and step errors go unreported, and each replan overwrites the plan file.

### Resolved since last review

- None. All five prior bullets re-verified at `0634bfd` and kept: unknown-ID partial
  success and malformed JSON merged into bullet 3, light mode into bullet 2,
  whole-tree rewrite per apply into bullet 6, identical-prose stale no-op into bullet 5.
- Audit trail (doc vs code; code wins): `plan.md`/`spec.md` line citations drifted with
  the comment-shortening pass — `dummyindex/cli/enrich.py` `run_plan` `:12-51` (cited
  `:12-54`), `run_apply` `:54-123` (`:57-126`), `json.loads` `:100` (`:103`);
  `dummyindex/context/domains/enrich.py` `build_plan` `:86-173` (`:93-182`),
  `apply_updates` `:198-218` (`:207-227`), `_apply` `:259-276` (`:268-285`);
  `migrate_context_layout` `dummyindex/context/build/upgrade.py:501-552` (`:542-593`);
  `active_stages` `dummyindex/context/domains/council_batch.py:62-77` (`:65-80`).
  `52-tree-enrich.md` and `skill.md` are catalog `low` (`.context/source-docs/INDEX.json`)
  and contradict themselves on light mode; cited above only as the instruction surface.
