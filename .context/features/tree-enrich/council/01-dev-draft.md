# Tree abstract enrichment — plan

`confidence: INFERRED`

## Where it lives

The real feature is exactly two source files; everything else in
`feature.json` is co-located cluster noise.

- **Domain (core)** — `dummyindex/context/domains/enrich.py`: `build_plan`
  (`:90`), `apply_updates` (`:202`), `write_plan` (`:180`), and the frozen DTOs
  `EnrichNode`/`EnrichBatch`/`EnrichPlan`/`ApplyResult` (`:28-199`). Pure: takes a
  `Path` + a `dict[str, str]`, never touches argv.
- **CLI boundary (core)** — `dummyindex/cli/enrich.py`: `run_plan` (`:10`),
  `run_apply` (`:58`). All argv parsing, `.context/`/`tree.json` existence
  gating, and JSON payload validation live here.
- **Dispatch wiring (shared)** — `dummyindex/cli/__init__.py:90-91` routes
  `ENRICH_PLAN`/`ENRICH_APPLY` to the two handlers. Shared with every other
  `context` verb, not owned by this feature.
- **Skill orchestration (out of repo's Python)** —
  `dummyindex/skills/skill.md:254-265` is where the plan→author→apply loop and
  its mode gating actually run; the `52-tree-enrich.md` procedure it cites is the
  detailed playbook.
- **Co-located, NOT core** — the ~30 `tests/cli/*` and
  `tests/context/domains/*` modules and `tests/fixtures/sample_repo/app.py` in
  `feature.json` `files`/`members` are end-to-end CLI tests that cluster here via
  shared test-harness call edges, not the enrich domain. Only
  `tests/context/domains/test_enrich.py` (`test_enrich_*` members) genuinely
  exercises this feature. The rest belong to audit/council/equip/hooks/placement/
  query/status features and should be reassigned in a human-reviewed placement
  pass.

## Architecture in three sentences

`run_plan` calls `build_plan` to do one pre-order walk of `tree.json["root"]`,
keeping only `EXTRACTED`-confidence nodes and partitioning them into one
`structure` batch plus one `file_subtree` batch per file, then `write_plan`
persists that `EnrichPlan` atomically to the gitignored
`.context/cache/_enrich_plan.json`. The `/dummyindex` skill authors abstracts
out of band and feeds a `{node_id: abstract}` JSON back through `run_apply`,
which validates the payload and calls `apply_updates` to merge it. The dominant
pattern is a **plan → out-of-band author → apply** loop with a pure domain
core behind a thin I/O-only CLI boundary — the same layering convention every
`context` verb follows.

## Data model

- **`_enrich_plan.json`** (`schema_version = 1`,
  `dummyindex/context/domains/enrich.py:25`) — the serialised `EnrichPlan` via
  `to_dict` (`:60-87`): `stats` (`total_nodes`, `stub_nodes`, `by_kind`),
  `batches` (`{name, kind, node_ids}`), and `nodes`
  (`{node_id, kind, title, path, range, stub_abstract, evidence_files}`). A
  transient scratch artefact under `cache/`, not a committed doc.
- **`tree.json` node merge** — `_apply` (`:261-275`) sets `node["abstract"]` to
  the authored prose and `node["confidence"]` to `INFERRED`, but only when one of
  those actually changes (`:266-272`); the `EXTRACTED → INFERRED` promotion is
  one-way (never demotes). Ids in `updates` absent from the tree are collected
  into `ApplyResult.unknown` via the `_collect_ids` membership check (`:213-215`)
  rather than applied.

## Key decisions

- **Plan is a transient scratch artefact, not a committed doc** — it lives under
  `cache/` and `run_plan` actively upgrades the managed `.gitignore` and deletes
  the pre-0.21 root copy (`dummyindex/cli/enrich.py:34-43`). Load-bearing because
  the abstracts feed retrieval (the PageIndex walk), not the council, so the
  work-list has no archival value — this is why enrichment runs in the skill
  *after* per-feature council work and before reconcile
  (`dummyindex/skills/skill.md:250-252`).
- **Confidence promotion is one-way and idempotent** — `_apply` only ever sets
  `INFERRED`, never demotes, and re-applying identical abstracts is a no-op
  (`:266-272`), so interrupted or repeated sessions converge without corrupting
  prior work.
- **Batch per file subtree, not one flat list** — each `file_subtree` batch
  (`:151-158`) is an independently-completable unit, so the session can write
  abstracts one file at a time and partial progress survives an interruption.
- **Typo'd `node_id`s surface, never silently drop** — `apply_updates` returns
  mismatches in `unknown` (`:215`) and `run_apply` exits `1`, listing them on
  stderr (`dummyindex/cli/enrich.py:116-123`); a silent drop would lose an
  authored abstract with no signal.
- **Mode gating lives in the skill, not the CLI** — the verbs always plan/apply
  the whole stub set; the skill chooses which batches to author by mode
  (`dummyindex/skills/skill.md:260-263`). Keeps the domain mode-agnostic and
  testable as a pure function.
- **Atomic temp-then-`replace` for every writer** — `write_plan` (`:182-185`)
  and the tree rewrite in `apply_updates` (`:219-221`); a crash mid-write leaves
  the prior file intact.

## Open questions

- **Membership noise (human follow-up).** `feature.json` mixes the genuine
  enrich domain (the two source files + `test_enrich.py`) with ~30 unrelated
  end-to-end CLI test modules that cluster here only via shared test-harness call
  edges. They should be reassigned during a human-reviewed placement pass; the
  spec/plan are scoped to the real domain.
- **Plan-membership validation.** Whether `enrich-apply` should require incoming
  `node_id`s to have been *planned* (present in the last `_enrich_plan.json`)
  rather than merely present in `tree.json` — today only tree membership is
  enforced (`dummyindex/context/domains/enrich.py:213-215`). Undeterminable from
  code whether this is intentional latitude or a gap.
