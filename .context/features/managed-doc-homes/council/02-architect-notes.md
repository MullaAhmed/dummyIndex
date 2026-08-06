# Architect notes — Managed doc homes

## What I changed

Authored `plan.md` from scratch (no prior plan existed). Grounding per section:

- **Where it lives** — the 17 paths in `feature.json:153-171`, each opened and cited at
  real line ranges from the source, not from `spec.md`. Test files included because the
  guard's two hard invariants are only expressed as tests
  (`tests/cli/test_guard_doc_write_e2e.py:255-258`, `:342-367`).
- **Architecture in three sentences** — read of `classify.py`, `decision.py`, `migrate.py`,
  `guard_doc_write.py`, `migrate_docs.py`, `git.py`. Named the functional-core /
  imperative-shell split that `spec.md` describes only as "pure/lexical, no I/O".
- **Data model** — `models.py:21-149` for the record chain, `migrate.py:243-257` for
  persisted artifacts, `config.py:182-183, 270-276, 497-521` for the v2→v3 schema.
  Called out the absent rollback explicitly rather than letting "transactional" in
  `spec.md` imply one.
- **Key decisions** — every rationale traced to a code site. Where the code states its own
  reason in a docstring I compressed rather than restated; where it stated *what* but not
  *why* I promoted the *why* (see "Decisions promoted").
- **Open questions** — six, all verified as genuinely undeterminable from the source
  (three of them are live inconsistencies I confirmed on disk).

Left `spec.md` and all source untouched.

## Patterns named

- **Shared kernel (single classifier, two consumers)** at
  `dummyindex/context/domains/docguard/classify.py:53-168` — one `classify_doc_path` /
  `group_strays` pair backs both the batch relocator and the live guard, so they cannot
  drift into disagreeing on what a stray is.
- **Functional core / imperative shell** at `classify.py:174-185` + `decision.py:33-63`
  (pure, filesystem-free) versus `migrate.py:64-228` + `cli/*.py` (all I/O) — the reason
  the classifier is cheap enough for a per-`Write` hook and exhaustively table-testable.
- **Plan/apply with whole-batch pre-validation** at `migrate.py:115-120` — pass 1 validates
  every slug and every source/target containment and raises before pass 2 constructs a
  single move.
- **Wire-only CLI adapter** at `cli/migrate_docs.py:56-62` and `cli/guard_doc_write.py:61,67-68`
  — domain imports live *inside* `run`, matching the repo's stated CLI/domain split
  (`.context/conventions/folder-organization.md:30-36`).
- **Extracted cross-cutting seam (facade)** at `dummyindex/context/git.py:39-110` — the one
  place `context/` code asks git anything; placed top-level, not in a domain, per the
  cross-cutting test at `folder-organization.md:69-73`.
- **Fail-open guard / fail-closed batch** at `cli/guard_doc_write.py:39-42` versus
  `cli/migrate_docs.py:83-88` — deliberately asymmetric error policy across the two
  consumers of the same kernel.
- **Frozen-record pipeline with `dataclasses.replace`** at `models.py:21-149` and
  `migrate.py:226` — the executed `method` is stamped by copy, never by mutation.

## Dependencies surfaced

- **Upstream (docguard depends on):** `domains/audit/workspace.py` (`slugify`,
  `validate_slug`, `ensure_audit`, `AUDITS_REL`), `domains/proposals/store.py`
  (`validate_slug`, `write_proposal_json`, `PROPOSALS_REL`), `domains/proposals/errors.py`,
  `domains/config.py` (`CouncilMode`, `ModelChoice`, `read_doc_guard_settings`),
  `context/git.py` → `pipeline/io/git.py:is_git_repo`, and on the CLI side
  `cli/common.py` (`parse_path_and_root`, `resolve_context_root`, `usage_error`) and
  `cli/memory.py:read_hook_stdin`. Every one is a *public* name — the zero-cross-domain-
  private-imports claim in `spec.md:12` verifies.
- **Downstream (depends on docguard):** `cli/__init__.py:135-136` dispatcher,
  `context/enums.py:159-160`, `cli/help.py:531,542`, `context/hooks.py:245-278` (the
  installed PreToolUse entry), `docs/guide/07-cli.md:592,598`, `.context/HOW_TO_USE.md:24`,
  and the `playbooks/migrate-stray-docs.md` playbook.
- **Cycles:** none. Verified by grep — nothing under `domains/audit/`, `domains/proposals/`,
  or `domains/gc/` references `docguard`. The dependency edges all point out of the domain.
- **Under-used seam:** `context/git.py` has exactly **one** importer today
  (`docguard/migrate.py:38`). Its own docstring (`git.py:11-20`) names the write-guard and
  `gc` as consumers, but the guard deliberately never calls it and `gc/delete.py:224` still
  owns a private `_is_tracked`. Recorded as open question 1, not as a defect.

## Decisions promoted

- decided **the guard signals only through JSON and never exits non-zero** because a
  PreToolUse non-zero exit blocks the tool, so one classifier false positive would wedge a
  session with no user escape (was implicit at `cli/guard_doc_write.py:39-42` and enforced
  only by `tests/cli/test_guard_doc_write_e2e.py:255-258`).
- decided **the error policy is deliberately asymmetric across the two consumers** — guard
  fails open, migration exits 2 — because one runs unattended on every write and the other
  runs deliberately behind `--yes` (was never stated; inferred from
  `guard_doc_write.py:39-42` versus `migrate_docs.py:83-88`).
- decided **classification is location-gated to `docs/`** because filename-shape-only
  heuristics would fire on source-adjacent and vendored markdown — accepting a real
  false-negative surface at repo-root `PLAN.md`, root `specs/`, and `.claude/` (gate at
  `classify.py:88-90`; the accepted cost was nowhere written down).
- decided **`slugify`'s `"audit"` fallback is treated as failure, not a value**, because it
  would silently collapse every symbol-only filename onto a single shared home (was
  implicit in the `_ALNUM` pre-check at `classify.py:216-217`).
- decided **`is_git_repo` gates every git call, resolved once per batch**, because
  `is_tracked` degrades to `True` off-git and so cannot distinguish "untracked in a repo"
  from "no repo at all" (contract at `git.py:85-92`, consumed at `migrate.py:186,271-274`).
- decided **realpath containment is duplicated rather than imported from `gc`**, trading
  ~10 duplicated lines for the zero-private-cross-domain-import invariant — and, by
  contrast, git access was *extracted* into a seam because it needed three call shapes plus
  a documented degradation contract (duplication at `migrate.py:330-344`; the contrast with
  `context/git.py` was implicit).
- decided **migrated proposals use `write_proposal_json`, not `ensure_proposal`**, because
  template `spec.md`/`plan.md` would collide with the files being relocated and a template
  `checklist.md` would make the hygiene GC read a finished artifact as in-flight (implicit
  at `migrate.py:254-257`).
- decided **`--force` fills but never clobbers**, encoded as the non-empty-file predicate
  `_is_present` — an empty placeholder is fillable, a non-empty target is skipped and
  reported (was a bare predicate at `migrate.py:347-354` with the policy unnamed).
- decided **the guard matches `Write` only**, halving blast radius, because `Edit`/
  `MultiEdit` require a pre-existing target and so can only maintain an existing doc, never
  create a fresh leak (stated at `hooks.py:246-248`, re-asserted at `guard_doc_write.py:49-52`;
  promoted to a decision because it is a scoping choice, not an implementation detail).
- decided **the deny message omits a `migrate-docs` pointer** because the guard fires on a
  *fresh* write while `migrate-docs` relocates *existing* files (buried in the module
  docstring at `decision.py:17-19`).
- decided **the hook rides `_CLAUDE_HOOKS` rather than a bespoke installer**, inheriting
  install/uninstall/status/`all_installed` for free and — because `_LEGACY_CLAUDE_EVENTS`
  is `("PostToolUse",)` — surviving the legacy scrub untouched (mechanism at
  `hooks.py:275,281`; the reuse rationale was unstated).

## Conflicts flagged (code wins)

- `.context/architecture/overview.md:23-37` lists `docs/specs/…`, `docs/internal/specs/…`,
  and `docs/superpowers/specs/…` as the repo's documented-architecture sources. I checked
  the filesystem: those paths are **gone** — this very feature's migration relocated them
  into `.context/proposals/`, and `.context/source-docs/INDEX.json` no longer indexes any
  of them (grep count 0). The overview's doc list is stale generated output. Recorded as
  open question 2 in `plan.md` because it exposes a real missing edge: nothing triggers a
  rebuild/reconcile after `migrate-docs` mutates the doc tree.
- `.context/conventions/folder-organization.md:9-12` explicitly grades
  `docs/reference/01-conventions.md` **low confidence**, so I used it only as historical
  context and cited the convention doc's own verified `path:range` claims instead. The
  overview doc's `DocConfidence.HIGH`/`MEDIUM` prose entries were not quoted at all, since
  every one of the paths I would have quoted from no longer exists.
- All identifiers I cite (`classify_doc_path`, `group_strays`, `decide`, `enumerate_strays`,
  `plan_moves`, `apply_moves`, `read_doc_guard_settings`, `run_git`, `is_tracked`,
  `is_git_repo`, `write_proposal_json`, `ensure_audit`, `slugify`, `validate_slug`) were
  spot-checked against `.context/map/symbols.json` and resolve to the expected paths. Note
  that this index carries `null` start/end lines for every symbol — line ranges in `plan.md`
  come from my own reads of the source, not from the index.
