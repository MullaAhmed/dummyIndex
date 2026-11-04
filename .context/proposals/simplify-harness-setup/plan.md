# Plan — Shared host workflow, removal of equipment-eval, and exact candidate verification

## Tasks

1. Shared capability preparation: reuse `build_catalog`, `render_generated_set`,
   `classify_item` and `content_hash` in `context/domains/equip/generate/`;
   put generated mandates under `.context/equipment/`, add thin owned native
   references, and expose mandate paths through `cli/build_loop/waves.py`.
   Unify `skills/{equip,plan,build}/SKILL.md` and their focused tests.
2. Remove equipment-eval: delete its CLI/domain/test-only implementation, remove
   dispatch/seeding/status/export coupling in `cli/equip/` and equip lifecycle,
   and update help/public docs. Gate native hooks/wrappers by explicit platform;
   preserve safe target ownership during path migration.
3. Repair qualification/promotion in `context/domains/evolve.py`, evolve-only
   helpers and `cli/evolve.py`, with evolve tests. Reuse scoped candidate validation,
   atomic writes, existing history/backups and ordinary pytest. Add `--tests PATH`
   for an explicit existing project check; keep acceptance outside editable files.
4. Review integration and failure cases; update durable feature docs in place.
   Run focused tests, applicable full-suite checks and lint. Do not add durable
   links to this disposable proposal.

Review: Astra identified exact-candidate execution, inert Python lint, missing-check
success, baseline identity and migration ownership as required fixes. Parallel
source reviewers confirmed installer linking already exists and found basename
aliasing, empty target acceptance and canonical-target overwrite hazards.

## Implementation result

All implementation and verification items are complete. Latest isolated Linux
snapshot: 3,437 passed, 3 optional/paid skips. Focused Windows: 551 passed,
3 symlink-privilege skips; additional adapter/home isolation checks passed.
Lint and changed-Python formatting pass. No model workloads were run.

Read-only reconcile found pre-existing anchor `f951b90dd48940c4307df2f0a09281419f1c04dc`
missing from this clone. The old index also describes a different scope. Curated
equipment/build docs were updated; a full index repair remains separate work.
Do not stamp this stale index as reconciled.
