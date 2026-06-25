# Plan — Context-hygiene GC (detect & delete stale/superseded/dead docs + trivially-dead code)

> Ordered, file-path-naming tasks. Cite reused symbols from
> `.context/map/symbols.json`. TDD: each domain/CLI task writes its test first
> (RED) then the implementation (GREEN). `— via <tool>` tags name the executor
> where an installed tool is the right one; untagged tasks route to the repo's
> generated specialists (implement/test/review/docs/security) by keyword.
> Revised once after the critique panel — see the inline "(panel)" notes.

## Tasks

### Foundations (no cross-dependencies)

1. **`commits_since` git helper.** Add `commits_since(root: Path, anchor: str | None) -> int | None`
   to `dummyindex/context/build/git_delta.py` — `git rev-list --count <anchor>..HEAD`
   via the existing `_run_git`; `None` off-git, on **unborn HEAD**, when `anchor`
   is `None`, or when `anchor` is unknown to the repo (validate via
   `commit_exists`). Mirror the tri-state style of `head_commit`. Test
   `tests/context/build/test_git_delta.py` (real git fixture): commit+count,
   off-git → `None`, unborn-HEAD → `None`, unknown-sha → `None`. *(panel: add the
   unborn-HEAD case.)*

2. **`ProposalStatus.SUPERSEDED`.** Extend the closed enum in
   `dummyindex/context/domains/proposals/enums.py` with `SUPERSEDED = "superseded"`.
   Confirm `Proposal.to_dict`/`from_dict` (`domains/proposals/models.py:30-52`)
   round-trip it and that an existing `planned`/`in_progress`/`done` `proposal.json`
   still loads. Test in `tests/context/domains/test_propose.py`.

3. **`report_written` extraction (small refactor, enables reuse).** Move the inline
   `(workspace / "report.md").exists()` probe (`cli/audit.py:157`) into a
   `report_written(context_dir, slug) -> bool` in
   `dummyindex/context/domains/audit/workspace.py`, re-export it from the audit
   `__init__.py`, and call it from `cli/audit.py`. *(panel BLOCK: the probe is
   CLI-layer today, not a reusable domain symbol — extract once, two callers.)*
   Test: existing audit tests still green + a `report_written` unit case.

4. **`gc` domain skeleton.** Create `dummyindex/context/domains/gc/` with the
   canonical concern split (`conventions/folder-organization.md`) — **no leading
   underscore on filenames**:
   - `enums.py` — `Disposition` (`KEEP`/`DELETE_DOC`/`DELETE_CODE`/`ROUTE_TO_PROPOSAL`),
     `CandidateKind` (`PROPOSAL`/`AUDIT`/`ORPHAN_SCAFFOLD`/`ARCHIVED`).
   - `constants.py` — `DEFAULT_COMMIT_THRESHOLD = 10`; generated-doc root rel-paths;
     the `_archive` sentinel name; committed anchor rel-path `gc/state.json`;
     gitignored memo rel-path `cache/gc-nudge-state.json`.
   - `errors.py` — `GcError(Exception)` base + `GcPathError` (realpath escape) +
     `GcTargetError` (missing/ambiguous/sentinel target). Mirror
     `proposals/errors.py`.
   - `models.py` — frozen `Candidate(kind, slug, rel_path, status, signals,
     tracked, age_days)`, `SweepReport(candidates, anchor, commits_since,
     threshold, should_signal, anchor_orphaned)`, `DeleteResult(deleted, refused,
     reason, untracked)`.

### Domain logic (depends on §4 + foundations)

5. **Enumeration.** `dummyindex/context/domains/gc/enumerate.py` —
   `enumerate_candidates(context_dir) -> tuple[Candidate, ...]`. Walk only the
   children of `proposals_root` (`domains/proposals/store.py:54`) and `audits_root`
   (`domains/audit/workspace.py:75`); **skip every `_`-prefixed entry as a sentinel
   container** (covers `_archive` and any future `_doc_backups`-style scratch) but
   surface `_archive/*` *children* as `ARCHIVED`; never enumerate `session-memory`.
   Test `tests/context/domains/gc/test_enumerate.py`: `_`-sentinel skipping, an
   `_archive` child surfaces, a `_doc_backups` dir is NOT surfaced, kinds correct.

6. **Signals.** `dummyindex/context/domains/gc/signals.py` —
   `classify(candidate, context_dir, root) -> tuple[str, ...]` (signals only, no
   verdict). `orphan-empty` = `spec.md`/`plan.md`/`checklist.md` byte-equal the
   scaffold templates (`domains/proposals/store.py:_spec_template/_plan_template/
   _checklist_template`). Proposals: `status:<v>` + checklist completion via
   `domains/buildloop/checklist.py:parse_checklist`+`counts`
   (`checklist-complete`/`checklist-partial`). Audits: `report-written` via the §3
   `report_written`. Cross-cutting: `untracked` (git ls-files miss); `age-<n>d`
   from `git log -1 --format=%ct <path>` only — omit/`None` off-git or untracked
   (**no mtime fallback** — panel HIGH: fresh clone resets mtime). Test
   `tests/context/domains/gc/test_signals.py`.

7. **GC anchor + throttle.** `dummyindex/context/domains/gc/anchor.py`:
   - `read_gc_anchor(context_dir)`/`write_gc_anchor(context_dir, sha)` over the
     **committed** `.context/gc/state.json` (`{"anchor": sha}`), atomic via
     `context/domains/atomic_io.py:write_text_atomic`. Reader copies the
     corrupt-tolerance shape of `memory/nudge.py:_load_state` (missing/`JSONDecodeError`/
     non-dict/bad-key → `None`).
   - `gc_commits_since(context_dir, root)` wrapping §1; expose `anchor_orphaned`
     (anchor recorded + git present + `commits_since is None`).
   - `should_signal(context_dir, root, session_id, *, threshold=DEFAULT_COMMIT_THRESHOLD)`
     combining `commits_since >= threshold` with a per-session fire-once memo in
     **gitignored** `.context/cache/gc-nudge-state.json` (pattern of
     `memory/nudge.py:already_nudged`/`mark_nudged`, 100-entry cap, best-effort).
   - `stamp_gc(context_dir, root, *, to=None)` advancing the anchor to HEAD
     (off-git no-op), modeled on `build/reconcile.py:stamp_reconciled` +
     `build/git_delta.py:head_commit`.
   Test `tests/context/domains/gc/test_anchor.py`: threshold edge, fire-once with a
   fixed session id, env-unset always-emit, off-git no-op, corrupt-state → `None`,
   committed-vs-gitignored path assertion, orphaned-anchor flag.

8. **Bounded delete.** `dummyindex/context/domains/gc/delete.py` —
   `delete_workspace(context_dir, *, kind, slug=None, path=None, allow_untracked=False, force_partial=False) -> DeleteResult`,
   implementing guards in order: (1) `validate_slug` (the kind's validator); (2)
   **sentinel reject** — `_archive`, leading-`_`, `.`/`..`, empty → `GcTargetError`
   (panel BLOCK: `_archive` is charset-valid and resolves *inside* the root, so the
   traversal guard cannot catch it); (3) realpath containment via `Path.resolve()` +
   `is_relative_to` (raises `GcPathError`, reachable only via `--path`/symlink);
   (4) **liveness** — refuse `in_progress`/`checklist-partial` proposals without
   `force_partial`; (5) **recoverability** — refuse untracked without
   `allow_untracked`, warn it's permanent; then `shutil.rmtree`. Missing dir = exit-0
   no-op. Never touches code. Test `tests/context/domains/gc/test_delete.py`: happy
   path, `../../etc` → slug error, `_archive`/`_` → `GcTargetError`, symlink escape
   → `GcPathError`, partial/in_progress refusal, untracked refusal + two-flag
   override, missing-dir no-op. **Security-sensitive — flagged for the security
   specialist (irreversible delete, traversal, untracked-data loss).**

9. **Domain public surface.** `dummyindex/context/domains/gc/__init__.py` —
   re-export the public functions + dataclasses + errors (mirror
   `domains/proposals/__init__.py:35-50` `__all__`).

### CLI (depends on domain)

10. **`cli/gc.py` (wire-only) + registration.** `run(args)` sub-dispatching
    `status|delete|stamp|signal`, parsing its own flag alphabet like
    `cli/audit.py` (`--kind`/`--slug`/`--path`/`--yes`/`--allow-untracked`/
    `--force-partial`/`--json`/`--to`/`--root`). Read-only `status`/`signal`;
    `delete` enforces the §8 guards + `--yes` (else dry-run); `stamp` advances the
    anchor. `signal` resolves the session id via
    `domains/memory/transcript.py:resolve_session_id` (env `CLAUDE_CODE_SESSION_ID`).
    Lazy-import the gc domain inside `run` (layering). **Register in THREE places**
    (panel LOW): add `GC = "gc"` to `dummyindex/context/enums.py` (`ContextSubcommand`),
    map it in `dummyindex/cli/__init__.py`, and add a help block in
    `dummyindex/cli/help.py`. Test `tests/cli/test_gc_cli.py`: every verb, exit
    codes (2 on guard violation), `--json`, dry-run vs `--yes`, the missing-dir
    exit-0 case; help-text test in `tests/cli/test_subcommand_help.py`.

### Hook wiring (depends on §10 `signal`)

11. **SessionStart throttle signal.** Add `dummyindex context gc signal` to the
    SessionStart hook command set in `dummyindex/context/hooks.py` +
    `dummyindex/context/claude_settings.py`, **coexisting** with the existing
    `plan-update` and `memory session-start` commands (do not displace either).
    Test `tests/context/test_hooks.py` (extend): SessionStart contains all three
    commands; combined over-threshold stdout has the drift report AND the gc nudge.
    **Verify the wired hook end-to-end — via /dummyindex-verify.**

### Skill + docs (depend on the CLI surface existing)

12. **`/dummyindex-gc` skill.** Author `dummyindex/skills/gc/SKILL.md` — the LLM
    council orchestration: (1) `gc status --json` → candidates; (2) fan out parallel
    subagents that walk docs PageIndex-style (`dummyindex context query`) + read the
    current session's work, each returning a per-candidate verdict
    {keep/stale/superseded/dead} + evidence; (3) synthesize a delete-list separating
    **dead docs**, **trivially-dead code** (0-caller private symbol that passes ALL
    exclusion guards in spec §"Trivially-dead-code exclusion guards", evidenced from
    `features/symbol-graph.json`), and **broader dead code**; (4) **confirm with the
    user**; (5) execute — `gc delete --yes` (+ flags) for docs, dispatch
    implementer+tester for trivially-dead code (remove only if the full suite stays
    green), `context propose` for broader dead code; (6) `gc stamp`; (7) reconcile
    `.context/` if code changed. The skill never shows `gc delete` without `--yes`
    and marks the confirm step + dogfood GATE non-dispatchable.

13. **Skill registration (3 places).** Register `dummyindex-gc` in the install
    tuple (`dummyindex/installer/install.py:110-115`), the uninstall sibling list
    (`dummyindex/installer/uninstall.py:46-53`), and the
    `test_install_copies_sibling_skills` parametrize roster
    (`tests/test_install.py:713-722`). *(panel HIGH: install/uninstall/test are
    three separate touch-points; missing one leaks on uninstall with no failing
    test.)*

14. **Doc-hygiene assertions for the skill.** Extend
    `tests/test_skills_doc_hygiene.py` with gc-skill cases (panel HIGH — the suite
    has no auto-discovery): assert `skills/gc/SKILL.md` (a) marks the user-confirm
    step + dogfood GATE non-dispatchable; (b) documents the ordered contract
    `gc status → PageIndex walk → user-confirm → gc delete / implementer+tester /
    new proposal → gc stamp → reconcile-if-code`; (c) never shows `gc delete`
    without `--yes`.

15. **Docs.** Update `.context/HOW_TO_USE.md` (hygiene-lifecycle section: generated
    docs are GC'd/deleted, not archived; `.context/gc/` named in the canonical
    layout), add `.context/playbooks/gc-context.md` (names the `gc status → confirm
    → gc delete → gc stamp` order), extend the `cli/help.py` `gc` block (all four
    verbs), and add a line to the bootstrap/CLAUDE.md managed note
    (`dummyindex/context/output/bootstrap.py`). Grep-asserted by the doc-hygiene
    test (§14). Untagged → docs specialist.

### Integration + acceptance (last)

16. **Full verification.** Run the complete suite + lint and confirm new code is
    green on 3.10 + 3.12, no `print` in `domains/gc/`, gc dataclasses `frozen=True`,
    gc errors subclass `GcError` (extend the existing convention-lint test).
    **— via /dummyindex-verify.**

17. **Convention review of the diff.** A focused review of the whole gc diff against
    the repo's conventions + per-feature concerns (routes to `dummyindex-reviewer`).
    *(panel: split out from verification as its own step.)*

18. **Dogfood on this repo (GATE).** Run `/dummyindex-gc` against this repo and read
    the orphan/superseded candidates from a **live `gc status`** run (not a
    hard-coded slug list — panel: the repo's contents have already shifted).
    **GATE** — actual deletion is the user's explicit confirm, not automatic.
