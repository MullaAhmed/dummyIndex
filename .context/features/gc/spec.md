# Context-hygiene GC — spec

confidence: INFERRED

## Intent

Retire generated `.context/` workspaces before they mislead AI agents. Proposals
(`proposals/<slug>/`) and audits (`audits/<slug>/`) accumulate — orphan scaffolds,
superseded plans, done audits — and an agent navigating `.context/` reads a
retired `plan.md` or a fixed audit's findings as *current intent*. The `gc`
feature is the **deterministic plumbing** for a commit-throttled hygiene sweep:
enumerate candidates, gather objective signals, throttle a SessionStart nudge
against a committed commit anchor, and execute **bounded, guarded deletion** of
whole doc workspaces. The reasoning half — judging *what* is stale / superseded /
dead, session-contextually, and confirming with the user — lives in the
`/dummyindex-gc` skill (LLM), exactly mirroring the `audit-panel` (plumbing) +
`/dummyindex-audit` (council) split. The CLI never reasons and never deletes
without an explicit target + `--yes`.

## User-visible behavior

CLI: `dummyindex context gc <verb>` (`cli/gc.py`, wire-only — parses its own
flag alphabet and sub-dispatches, like `cli/audit.py`). Registered as
`ContextSubcommand.GC` in `context/enums.py` + mapped in `cli/__init__.py`.

- **`gc status [--json]`** — enumerate every candidate generated doc with its
  signal tags + the commit-throttle state (`anchor`, `commits_since`, `threshold`,
  `should_signal`, `anchor_orphaned`). Read-only; it never consumes the
  per-session memo. `should_signal` here is the pure threshold check
  (`commits_since >= threshold`).
- **`gc delete --kind proposal|audit (--slug S | --path P) [--yes] [--allow-untracked] [--force-partial]`**
  — delete one workspace dir behind a fixed guard ladder. Without `--yes` it is a
  dry-run (prints the target, removes nothing). Guard order: slug-validate →
  sentinel-reject → realpath-containment → liveness → recoverability → `rmtree`.
- **`gc stamp [--to SHA]`** — advance the committed GC anchor to HEAD (or `--to`);
  off-git no-op. Resets the throttle counter. Modeled on `reconcile-stamp`.
- **`gc signal [--json]`** — the SessionStart throttle probe (wired into the hook
  alongside `plan-update` + `memory session-start`): prints a one-line nudge iff
  `commits_since >= threshold` AND this session hasn't already been signalled.
  Resolves the session id via `memory.transcript.resolve_session_id`
  (`CLAUDE_CODE_SESSION_ID`); no session id → emit-when-over-threshold (never
  silent-forever). Always exit 0; silent under threshold / off-git / already-signalled.

## Contracts

Public surface (re-exported from `domains/gc/__init__.py`):

- `enumerate_candidates(context_dir) -> tuple[Candidate, ...]` — `enumerate.py`.
  Walks `proposals_root`/`audits_root` children; skips every `_`-prefixed
  sentinel container but surfaces `_archive/*` children as `ARCHIVED`; fills
  structural fields (kind, slug, rel_path, status from `proposal.json`, git
  `tracked`, git-commit-date `age_days`); `signals=()`. Does **not** import
  `signals`.
- `classify(candidate, context_dir, root) -> tuple[str, ...]` — `signals.py`.
  Pure signal tags: `status:<v>`, `orphan-empty` (`plan.md`+`checklist.md`
  byte-equal the scaffold templates — `spec.md` is **excluded** because
  `apply_consistency` rewrites it), `checklist-complete`/`checklist-partial`
  (via `buildloop.parse_checklist`+`counts`), `report-written` (via the audit
  domain's `report_written`), `untracked`, `age-<n>d`. No verdict. Does **not**
  import `enumerate`.
- `read_gc_anchor`/`write_gc_anchor`, `gc_commits_since`, `anchor_orphaned`,
  `should_signal`, `stamp_gc` — `anchor.py`. The committed anchor lives in
  `.context/gc/state.json` (`{"anchor": sha}`, atomic, corrupt→`None` like
  `nudge._load_state`); the per-session fire-once memo lives in **gitignored**
  `.context/cache/gc-nudge-state.json` (pattern of `nudge.already_nudged`/
  `mark_nudged`, 100-entry cap). `stamp_gc` off-git no-op.
- `delete_workspace(context_dir, *, kind, slug=None, path=None, allow_untracked=False, force_partial=False) -> DeleteResult`
  — `delete.py`. The only `rmtree` in the codebase. Guard ladder:
  1. **slug-validate** — the kind's `validate_slug` (raises `ProposalSlugError`/
     `AuditSlugError` for `../../x` before any path work).
  2. **sentinel-reject** — `_archive`, leading-`_`, `.`/`..`, empty → `GcTargetError`
     (`_archive` is charset-valid and resolves inside the root, so the realpath
     guard cannot catch it — this guard must).
  3. **realpath-containment** — `resolve()` (follows symlinks) + `is_relative_to`
     the resolved kind-root → `GcPathError` on escape (reachable only via
     `--path`/symlink).
  4. **liveness** — an `in_progress` or `checklist-partial` proposal is refused
     unless `force_partial` (structural backstop against deleting a plan a
     `/dummyindex-build` is mid-flight on).
  5. **recoverability** — a git-untracked target is refused unless
     `allow_untracked` (deletion would be permanent). Off-git ⇒ treated as tracked.
  A missing target is an idempotent no-op (`deleted=False, refused=False`).
- `scan(context_dir, root) -> SweepReport` — `scan.py`. Composes
  `enumerate_candidates` + `classify`-enrich (`dataclasses.replace`) + anchor
  state into the read-only `gc status` payload (no memo consumption).
- `commits_since(root, anchor) -> int | None` — `build/git_delta.py` (added).
  `git rev-list --count anchor..HEAD`; `None` off-git / unborn-HEAD / `anchor is
  None` / unknown sha (validated via `commit_exists`).

Frozen dataclasses (`models.py`): `Candidate(kind, slug, rel_path, status,
signals, tracked, age_days)`, `SweepReport(candidates, anchor, commits_since,
threshold, should_signal, anchor_orphaned)`, `DeleteResult(deleted, refused,
reason, untracked)`. Enums (`enums.py`): `Disposition`, `CandidateKind`.
Errors (`errors.py`): `GcError` base + `GcPathError` + `GcTargetError`.
Constant `DEFAULT_COMMIT_THRESHOLD = 10` (`constants.py`).

Invariants: never delete outside `.context/{proposals,audits}/`; deletion is
`--yes`-gated and untracked deletion needs a second `--allow-untracked`; GC never
edits/removes source code (the skill routes code through implementer+tester or a
new proposal); off-git/orphaned-anchor degrades to a graceful no-op; the
committed anchor (`gc/state.json`) and the gitignored memo (`cache/`) are
separate files; `session-memory` is out of scope.

## Examples

```
$ dummyindex context gc status
context gc status: 4 candidate(s)
  proposal  config-depth-wired-ux   proposals/config-depth-wired-ux  [status:planned, checklist-complete, age-3d]
  ...
  anchor=(unset) commits_since=n/a threshold=10 should_signal=False

$ dummyindex context gc delete --kind audit --slug old-audit          # dry-run, removes nothing
$ dummyindex context gc delete --kind audit --slug old-audit --yes    # removed
$ dummyindex context gc delete --kind proposal --slug _archive --yes  # GcTargetError (sentinel), exit 2
```
