# Tree abstract enrichment — plan

`confidence: INFERRED`

## Bounded context

The CORE enrichment domain is exactly two source files; everything else co-listed
in `feature.json` is cluster noise that crossed the boundary.

- **Domain (CORE)** — `dummyindex/context/domains/enrich.py`: `build_plan`
  (`:90`), `apply_updates` (`:202`), `write_plan` (`:180`), and the frozen DTOs
  `EnrichNode` (`:29`), `EnrichBatch` (`:42`), `EnrichPlan` (`:51`),
  `ApplyResult` (`:189`). Pure: takes a `Path` + a `dict[str, str]`, never reads
  argv, never sees a run mode. Internals `_walk` (`:228`), `_apply` (`:261`),
  `_collect_ids` (`:253`), `_file_id_for_path` (`:238`), `_count_nodes` (`:249`).
- **CLI boundary (CORE)** — `dummyindex/cli/enrich.py`: `run_plan` (`:10`),
  `run_apply` (`:58`). All argv parsing, `.context/`/`tree.json` existence
  gating, `--from-json` validation, and exit-code mapping live here — the domain
  stays I/O-clean.
- **Dispatch wiring (SHARED, not owned)** — `dummyindex/cli/__init__.py:90-91`
  maps `ENRICH_PLAN -> run_plan` / `ENRICH_APPLY -> run_apply` inside the one
  `dispatch` table (`:129`) every `context` verb shares. The feature consumes
  this seam; it does not own it.
- **Orchestration (out of the Python boundary)** — the plan->author->apply loop
  and its mode gating run in `dummyindex/skills/skill.md:246-263` (Phase 4.5),
  with the detailed playbook in `council/52-tree-enrich.md`. This is where
  "which batches get authored" is decided — never in the CLI verbs.

### Co-located test noise — boundary call

`feature.json` `files`/`members` mixes the genuine domain with ~30 end-to-end
CLI test modules (`tests/cli/*`, `tests/context/domains/*`) and
`tests/fixtures/sample_repo/app.py`. They cluster here via shared
test-harness call edges (a common CLI runner fixture), **not** the enrich domain.
Only `tests/context/domains/test_enrich.py` (the `test_enrich_*` members,
`feature.json:121-138`) genuinely exercises this feature. The rest belong to
audit/council/equip/hooks/placement/query/status and must be reassigned in a
human-reviewed placement pass (`enrich_walk`/`enrich_apply` here are the domain;
`app_*`, `init_dispatch`, every `test_<other-domain>_*` are not). The spec and
this plan are scoped to the two CORE files plus `test_enrich.py`.

## Architecture in three sentences

`run_plan` calls `build_plan` to do one pre-order `_walk` of `tree.json["root"]`
(`:228-235`), keeping only stub (`EXTRACTED`) nodes and partitioning them into one
`structure` batch plus one `file_subtree` batch per file, then `write_plan`
persists that `EnrichPlan` atomically to the gitignored
`.context/cache/_enrich_plan.json`. The `/dummyindex` skill authors abstracts
out of band and feeds a `{node_id: abstract}` JSON back through `run_apply`,
which validates the payload and calls `apply_updates` to merge it. The dominant
pattern is a **two-phase plan -> out-of-band author -> apply** loop with a pure
domain core behind a thin I/O-only CLI boundary — the layering convention every
`context` verb follows.

## Patterns (named, with their home)

- **Plan/apply two-phase with an out-of-band author** — `build_plan`+`write_plan`
  emit a work-list (`enrich.py:90`, `:180`); a human/LLM step authors prose; then
  `apply_updates` writes it back (`:202`). The author step is deliberately
  *outside* the domain — the CLI never calls an LLM.
- **Stub -> INFERRED confidence flip (one-way, idempotent)** — `_apply`
  (`enrich.py:261-275`) sets `node["abstract"]` + `node["confidence"] =
  INFERRED`, but only when one actually differs (`:266-272`). Never demotes; never
  re-walks an already-`INFERRED` node into a plan (`build_plan` keeps only
  `EXTRACTED`).
- **Mode-gated fan-out owned by the orchestrator** — the verbs always plan/apply
  the *whole* stub set; the skill chooses which batches to author by run mode
  (`skill.md:260-263`): light skips, standard authors `structure` via one
  architect, deep additionally fans a dev per `file_subtree` batch. The domain
  never branches on mode.
- **Atomic temp-then-`replace` for every writer** — `write_plan`
  (`enrich.py:182-185`) and the tree rewrite in `apply_updates` (`:219-221`); a
  crash mid-write leaves the prior file intact.

## Data model

- **`_enrich_plan.json`** (`schema_version = 1`, `enrich.py:25`) — the serialised
  `EnrichPlan` via `to_dict` (`:60-87`): `stats` (`total_nodes`, `stub_nodes`,
  `by_kind`), `batches` (`{name, kind, node_ids}`), `nodes`
  (`{node_id, kind, title, path, range, stub_abstract, evidence_files}`). A
  transient scratch artefact under `cache/`, not a committed doc.
- **`tree.json` node merge** — `_apply` (`enrich.py:261-275`) is the only writer
  of the enriched fields; the `EXTRACTED -> INFERRED` promotion is one-way. Ids in
  `updates` absent from the tree are collected into `ApplyResult.unknown` by the
  pre-`_apply` `_collect_ids` membership check (`apply_updates:213-215`) rather
  than applied.

## Dependencies

- **Upstream — `tree.json` from the deterministic backbone.** `build_plan` reads
  `<context_dir>/tree.json` and raises `FileNotFoundError` if absent
  (`enrich.py:90-92`); the stub `abstract`/`EXTRACTED confidence` it filters on
  are seeded by the backbone build, not by this feature (`skill.md:248-249`). No
  tree -> no plan.
- **Downstream — future-session PageIndex retrieval.** The whole point of the
  flip is that a later session's PageIndex-style tree walk reads real prose at
  step 6 of the retrieval procedure (`skills/retrieval/00-overview.md:28-29`,
  DocConfidence.HIGH). Nothing in *this* session consumes the abstracts — the
  council personas never read them (`skill.md:251`).
- **Sibling — reconcile.** Enrichment runs as Phase 4.5, strictly before the
  Phase 5 reconcile/refresh-indexes step (`skill.md:246-271`).

## Key decisions

- **Decided enrichment is retrieval-facing and runs after per-feature council
  work — because the personas never read node abstracts.** The abstracts feed a
  *future* session's PageIndex walk, not the *current* council
  (`skill.md:250-252`, DocConfidence.HIGH). That placement is why the work-list is
  a throwaway: it has no council audience and no archival value, so it lives under
  `cache/` and `run_plan` actively upgrades the managed `.gitignore` + deletes the
  pre-0.21 root copy (`enrich.py:40-41`).
- **Decided mode gating is an orchestration concern, not a CLI concern — because
  it keeps the domain a pure, testable function.** If the verbs took a `--mode`
  flag the domain would branch on policy; instead they always plan/apply the full
  stub set and the skill scopes *which* batches it authors (`skill.md:260-263`).
  Trade-off: the CLI cannot itself enforce "standard skips symbol batches" — that
  invariant lives only in the orchestrator's dispatch choice, untested by the CLI
  suite.
- **Decided confidence promotion is one-way and idempotent — so interrupted or
  repeated sessions converge.** `_apply` only ever sets `INFERRED`, never demotes,
  and re-applying identical abstracts is a no-op (`enrich.py:266-272`); replaying a
  partially-applied `--from-json` corrupts nothing.
- **Decided to batch per file subtree, not one flat list — so partial progress
  survives an interruption.** Each `file_subtree` batch is an
  independently-completable unit, so a session can author + apply one file at a
  time. Trade-off: more batches (one per file) and a separate `structure` batch
  vs. a single dispatch.
- **Decided typo'd `node_id`s surface, never silently drop.** `apply_updates`
  returns mismatches in `unknown` via the membership check
  (`enrich.py:213-215`) and `run_apply` exits `1`, listing them on stderr
  (`cli/enrich.py:116-123`); a silent drop would lose an authored abstract with no
  signal.

## Open questions

- **Membership noise (human follow-up).** The ~30 unrelated end-to-end CLI test
  modules in `feature.json` should be reassigned during a human-reviewed placement
  pass; only the two CORE files + `test_enrich.py` are this feature.
- **Plan-membership validation.** Whether `enrich-apply` should require incoming
  `node_id`s to have been *planned* (present in the last `_enrich_plan.json`)
  rather than merely present in `tree.json` — today only tree membership is
  enforced (`enrich.py:213-215`). Undeterminable from code whether this is
  intentional latitude or a gap.
