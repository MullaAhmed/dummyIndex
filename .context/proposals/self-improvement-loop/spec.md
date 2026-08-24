# Spec — dummyindex evolve: harvest session evidence, gate candidate harness edits through evals, keep a decision history

## Intent

dummyindex babysits well but never improves itself. The raw materials already exist and
are harvested *by hand*: GC runs fold learnings into DECISIONS/CONVENTIONS/BACKLOG via
ad-hoc "harvest walkers" (2026-08-08); audit findings get manually pasted into
conventions ("log your findings ... so that these issues never happen again", 08-12);
session memory records what went wrong; equipment-evals suites check trigger routing but
never improve it. The 2026 research frontier (AHE, Meta-Harness/Harness Forge,
Microsoft SkillOpt-Sleep, Tencent SkillHone, skill-evolver) converges on one loop:
**evidence -> cited diagnosis -> bounded candidate edit -> validation gate ->
adopt-or-rollback -> append-only decision history.** This proposal closes that loop
inside dummyindex's existing artifacts.

## Contracts

- New context subcommand `context evolve` (registered in `ContextSubcommand`,
  `cli/__init__.py::_HANDLERS`, and `cli/help.py` usage tables — thin CLI over a
  deterministic domain):
  - `evolve harvest [--since <ref|date>] [--sleep]` - collect evidence items with
    `path:line` citations: open findings parsed from `.context/audits/<slug>/report.md`,
    correction notes from `.context/session-memory/{now,recent}.md`, reconcile deltas (named fields from `ReconcileReport`: drifted_features,
    unassigned_new_files, awaiting_enrichment), and context-adoption misses via a NEW
    content scanner that reuses only the file-discovery helpers of
    `dummyindex/usage/transcripts.py` (`default_projects_root`, `find_main_transcript`,
    `load_session`, `iter_all_turns`) — those helpers expose token counts, not message
    content, so the adoption detector is net-new. GC-learnings harvesting is out of
    scope v1 (no structured learnings store exists yet). `--sleep`: batch mode, exit 0 when nothing new (fleet-runner drives this
    overnight, SkillOpt-Sleep style).
  - `evolve diagnose [--json]` - host-side LLM step (skill procedure): read harvest
    report, emit at most 5 candidates, each `{target_file, diagnosis, evidence[],
    change_sketch, prediction}` where target is limited to curated `.context/`
    conventions/playbooks/equipment docs, packaged `dummyindex/skills/**` guidance, or
    equipment-eval cases. CLI validates structure and citation existence only.
  - `evolve apply --candidate N --run DIR` - stage candidate under
    `.context/gc/evolve/<id>/`, run gate: (a) trigger suites scored deterministically via
    `domains/equip/eval.py::score_run` over an observations file the host skill
    produces while testing the candidate (the CLI never judges triggers itself);
    (b) targeted pytest subset; (c) `ruff check` on touched py. Gate verdict
    semantics: any stage that errors or cannot run (missing/partial/duplicated/
    mismatched observations — `score_run` raises on all but absent) yields overall
    verdict `blocked`, never pass; `promote` of a blocked candidate requires an
    explicit `--override "<reason>"` recorded in evolution.jsonl. Absent suite match
    records `(a) not_applicable` honestly.
  - `evolve promote|rollback|discard --candidate N --run DIR` - adopt (git-revertable)
    or drop.
  - Every transition appends one line to `.context/gc/evolution.jsonl`
    (committed, append-only; extends the gc/ layout — HOW_TO_USE.md's gc/ section and
    `playbooks/gc-context.md` are amended in the same landing): `{id, ts, kind: harvest|diagnosis|gate|promote|rollback,
    evidence[], target, prediction?, gate?, outcome?}`.
- Run artifacts pinned: `<run>/harvest.json` (report), `<run>/candidates.jsonl`
  (one candidate per line; `--candidate N` = 0-based line index). Both validated by the
  CLI at read.
- Evidence citations for transcript hits store projects-root-relative session slugs,
  never absolute `$HOME` paths (repo-portable, no username leakage).
- Scope guard additionally denies `.context/gc/evolution.jsonl` and
  `gc/state.json`; a candidate may target at most 5 files (validation-enforced).
- Falsification hook: promoted edits carry predictions; later harvests re-check open
  predictions against current evidence and flag flipped ones for rollback proposals.
- Scope guard enforced in apply validation: targets may never be source code
  (`dummyindex/**/*.py`) nor `features/<id>/spec.md` bodies (those go through normal
  plans/reconcile). Transcript scanning reads machine-local host logs read-only and
  stores no personal data beyond counts + citations.
- Invariants: deterministic CLI, no in-process LLM; all evolve state committed under
  `.context/gc/`; corrupt JSONL lines skipped with warning, never fatal.

## Acceptance

- [ ] pytest `tests/context/domains/test_evolve.py`: fixture audits/session-memory/
      usage parsed with citations intact; malformed candidates rejected with errors.
- [ ] pytest `tests/cli/test_evolve_cli.py`: lifecycle on temp repo - harvest,
      diagnose(fixture), apply+gate(fail) then rollback; apply+gate(pass) then promote;
      evolution.jsonl has one line per transition.
- [ ] Prediction re-check: stored prediction falsified by fixtures gets flagged next
      harvest.
- [ ] Scope guard rejects a candidate targeting `dummyindex/context/drift.py`.
- [ ] Sleep contract: `evolve harvest --sleep` with nothing new exits 0 writing nothing.
- [ ] Full suite green: `python -m pytest tests/ -q --tb=short`.

## Open questions

- Q1 (GATE): default gate set when target touches packaged skills - which pytest subset
  is "targeted"? Planned: tests matching changed path segments; confirm at build.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `session-memory`
- `install-surface`
- `equip`
- `tree-enrich`
- `usage-report`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
