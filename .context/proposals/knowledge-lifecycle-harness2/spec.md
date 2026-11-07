# Spec — Knowledge lifecycle: lesson records, doc budget, reusable specialists, citation guard

## Intent

Users report: conventions never update, audit lessons rarely land, docs are
wordy, specialists are thin and not reusable, proposals get cited in durable
docs, and checklists carry live-testing steps. Root causes in code:

- `proposals/closeout.py:_learn_after_closeout` swallows every learning failure
  into an in-memory `{"status": "unavailable"}` that never reaches disk;
  `learning_reflection` is optional and shape-checked only deep inside
  `evolve_learning.prepare_learning`.
- Nothing bounds doc/skill size or says where a fact should live.
- Only 5 capabilities are template-backed (`equip/generate/specialists.py`);
  everything else is a manifest-only pointer; nothing keeps an adopted
  specialist for reuse.
- Citation of `proposals/`/`audits/` is blocked only at closeout
  (`proposals/retirement.py:durable_references`), never at write time.
- Live testing is forbidden in prose only (`skills/evolve/SKILL.md`).

Design borrowed as background (external, not cited in durable docs): a required
`cue/lesson/evidence/confidence` record, one per round; deterministic id-keyed
delta merge; per-edit verdicts preferring `confounded` over invented
attribution; reusable component beats always-on prose, and adding always-on
text means cutting some; stored specialists copied and re-verified on reuse.

Out of scope: gc sweep/classification logic (only the `gc closeout` verb's
exit code and printing change), ponytail, agent-to-agent grammar, measuring
model quality, a config schema v6.

## Contracts

1. **Lesson record** — package `dummyindex/context/domains/lesson/`
   (`models.py`, `enums.py` with `Verdict` and `Confidence`, `__init__.py`).
   `cue`, `lesson`, `evidence`, `confidence` (`low|medium|high`) all required and
   non-empty. One lesson object per closeout/event; a list is rejected. Optional
   `edits`: rows `{component, change, verdict}`, verdict in
   `helped|hurt|no_observed_effect|confounded`. `validate_lesson` is the only
   shape check; `closeout.py` and `evolve_learning.py` both call it.
2. **Delta mapping** — `lesson_to_delta(lesson, rule_id, ...)` is pure and
   returns `living_rules.plan_rule` keyword arguments; it contains no merge code.
   Op: `revise` if `rule_id` already exists in the target doc, else `add`;
   `supersede` only via an explicit `supersedes` field. A stale
   `expected_sha256` yields `blocked`/`failed`, never an overwrite.
3. **Legacy manifests** — a `learning_reflection` in the pre-change shape
   (`target, rule_id, body, expected_sha256, sources, verified, tests`, no lesson
   fields) is still accepted, flagged `legacy_shape` in the status, and warned once.
   New-shape validation applies to everything else.
4. **Learning status is persisted and never silent.** Statuses:
   `applied|evaluated|blocked|no_entry|pending|ignored|failed`. The learning
   event file (`evolve_learning._path`) carries the state; when the failure
   precedes event creation, write
   `.context/gc/learning/<kind>-<slug>.failed.json`. The receipt file bytes are
   never rewritten (its digest feeds the event id). Re-running closeout retries
   learning after `failed` and reports the stored status otherwise. Only `failed`
   exits non-zero, for `gc closeout`, `build --closeout`, and
   `cli/evolve.py:_evolve_learning`. `blocked` is printed, exit 0.
5. **Doc budget** — package `dummyindex/context/domains/docbudget/`
   (`models.py`, `constants.py` ceilings in code, `ratchet.py`). No config
   change. Scope: `.context/features/*/{spec,plan,concerns}.md`,
   `.context/PROJECT.md`, `.context/architecture/overview.md`,
   `.context/conventions/*.md`, and packaged `dummyindex/skills/**/SKILL.md`.
   Ratchet files are sorted one-line-per-doc `path<TAB>words`:
   `.context/doc-budget.txt` and `tests/data/skill-budget.txt`. Growth over the
   recorded size fails; `dummyindex context check --budget --update-ratchet`
   lowers entries and refuses to raise any. `cli/check.py` only delegates.
6. **Placement rule** — one short section in `dummyindex/skills/skill.md`:
   prefer skill/script/subagent over always-on prose; adding always-on text
   requires cutting some.
7. **Specialist library** — `equip/lifecycle/library.py` (reuses
   `lifecycle/hashing.py` and `identity.capability_identity`). Stores a specialist
   and `EXPERIENCE.md` (the validated lesson) under
   `.context/equipment/library/<capability_id>/`, tracked in
   `.context/equipment/library/library.json`, outside `equipment.json`. Status
   `ok|needs-reverify`; a changed `origin_hash`, changed grounding hash, deleted
   grounding path, or missing entry gives `needs-reverify`. CLI verb
   `dummyindex context equip reuse <capability_id>` copies the body; it refuses to
   overwrite a locally edited target unless `--force`. `SpecialistTemplate` gains
   optional `dimension` (`procedure|domain`); manifests without it stay valid.
   New templates: frontend, api, migration, ci, each a procedure and a domain half
   (8 `.tmpl` files, packaged via `pyproject` package-data). A second
   `equip apply` is idempotent.
8. **Write-time citation guard** — the PreToolUse guard
   (`dummyindex/cli/guard_doc_write.py`; `hooks.py` wires it) widens its matcher to
   `Write|Edit|MultiEdit` and reads `tool_input.content`, `new_string`, and
   `edits[].new_string` (scan capped at 1 MB; any exception allows the write).
   It denies only authored markdown under `.context/features|conventions|architecture`
   and `PROJECT.md` when the new text adds a `.context/(proposals|audits)/<slug>/`
   citation absent from the existing file. `council/` docs and `*.json` are
   excluded. Re-running install rewrites the matcher. `DISPOSABLE_REF` and
   `cites_disposable(text)` get one home, `docguard/citations.py`, re-imported by
   `retirement.py` and `closeout.py`. Hosts without hooks, and existing citations,
   are covered by `context check --refs` (exit 1 if any durable doc cites).
   The stale citation in `memory/miner/__init__.py` is removed.
9. **No live-testing checklist items** — `buildloop/checklist_lint.py:live_items`
   flags unticked items matching case-insensitive
   `\b(live[- ]tests?|live testing|production (test|run|smoke|verification)|smoke[- ]tests?|manual(ly)? (test|verif\w*)|against (production|staging|a live)|real (api|account)s?)\b`.
   An item carrying `<!-- live-ok: <reason> -->` (false-positive escape) and any
   ticked item are not flagged. `waves` exits non-zero and lists flagged items. The
   checklist scaffold and `skills/plan/SKILL.md` state the rule. Closeout's
   existing handling of already-moved live items is unchanged and pinned by a test.

## Acceptance

Each criterion maps to one named test (file under `tests/`).

- [ ] `validate_lesson` rejects each missing/empty field, a list of two lessons, and a bad `confidence`/`verdict` (`tests/context/domains/test_lesson.py`).
- [ ] `lesson_to_delta` is pure and picks `revise` vs `add` by existing `rule_id`; applying the same delta twice is byte-identical; an owner edit between plan and apply is refused; text outside rule blocks is unchanged (`tests/context/domains/test_lesson.py`, `test_evolve_learning.py`).
- [ ] A parametrised test covers every status (`applied, evaluated, blocked, no_entry, pending, ignored, failed`): persisted status and exit code, with failure injected through a learner parameter, not a patch (`tests/context/domains/test_closeout.py`).
- [ ] After `failed`, the receipt file exists unchanged and a re-run retries learning (`test_closeout.py`).
- [ ] A pre-change manifest fixture with a legacy reflection closes with `legacy_shape`, not `failed` (`test_closeout.py`).
- [ ] `gc closeout`, `build --closeout` and `evolve` learning each exit non-zero on `failed` and zero on `blocked` (`tests/cli/test_closeout_exit_codes.py`).
- [ ] `docbudget` flags a grown doc (rc 1, path in output), passes unchanged/shrunk docs, and `--update-ratchet` lowers but refuses to raise (`tests/context/domains/docbudget/test_ratchet.py`, `tests/cli/test_check_budget.py`).
- [ ] `skills/skill.md` contains the placement-rule heading, `skills/plan/SKILL.md` contains the no-live-testing rule, and packaged skill word counts are within the ratchet (`tests/test_skills_doc_hygiene.py`).
- [ ] Library: store then reuse copies the body; each of changed grounding, deleted grounding and missing entry gives `needs-reverify`; an unchanged project stays `ok`; reuse refuses a locally edited target without `--force`; `EXPERIENCE.md` carries the lesson fields (`tests/context/domains/equip/test_equip_library.py`).
- [ ] `equip apply` on a fixture with frontend/api/migration/ci signals writes generated files, one procedure and one domain entry per capability; a manifest without `dimension` loads; a second apply changes nothing (`test_equip_specialists.py`, `test_equip_apply_merge.py`).
- [ ] Guard: denied for `Write`, `Edit`, `MultiEdit` payloads adding a citation to an authored doc; allowed under `.context/proposals/`, for `council/`, `*.json`, and when the file already had the citation; allowed on malformed/non-string/oversized content and on scan exceptions (`tests/cli/test_guard_doc_write.py`); Windows separators covered.
- [ ] `check --refs` on a fixture lists citing docs and exits 1; on this repo it reports zero durable-doc hits (code that handles proposal paths is not a citation) (`tests/cli/test_check_refs.py`).
- [ ] `live_items` flags 5 positive phrases and ignores 5 negatives (`live-reload`, `delivery`, `production-grade`, `live in the index`, `smoke` as a test name), honours `live-ok` and ticked items; `waves` exits non-zero on a flagged checklist (`tests/context/domains/test_checklist_lint.py`, `test_build_loop.py`).
- [ ] The whole suite passes: `python -m pytest tests/ -q`.

## Open questions

None blocking. Decisions recorded: live items are rejected, not warned;
no config schema change; legacy reflections accepted with a warning.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `managed-doc-homes`
- `proposals`
- `evolution`
- `build-loop`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
