# Plan — Make context-hygiene GC useful: unblock retirement, recommend actions, draft closeouts, batch confirm

> Ordered, file-path-naming tasks. Symbols cited from `.context/map/symbols.json`.

## Rules for every task

- KISS and YAGNI. Ship only the contracts in `spec.md`.
- No long comments in code. At most one short line on a non-obvious statement. Docstrings at most 3 lines.
- Reuse before writing. Names follow `conventions/naming.md`.
- Domain modules never print. `cli/gc.py` stays wire-only (`conventions/folder-organization.md`).
- Each task ships its own tests, marked `@pytest.mark.unit` or `@pytest.mark.integration` (`--strict-markers`).
- Run `python -m pytest tests/ -q --tb=short` after each task. No task deletes a real workspace in this repo.

## Tasks

1. **Skip generated INDEX.md in durable references (C1).**
   File: `dummyindex/context/domains/proposals/retirement.py`.
   In `durable_references` (`retirement_durable_references`), skip only `parent == context_dir and name == "INDEX.md"`, beside the graph-payload skip.
   Test: `tests/context/domains/test_closeout.py` per the C1 acceptance item. Run the existing closeout tests.

2. **Enum, constants, model fields (C2, C4 scaffolding).**
   Files: `dummyindex/context/domains/gc/enums.py`, `dummyindex/context/domains/gc/constants.py`, `dummyindex/context/domains/gc/models.py`.
   - `Recommendation(str, Enum)`: `DELETE`, `CLOSE`, `REVIEW`, `KEEP`.
   - `STALE_AGE_DAYS = 30`; `PROPOSAL_KINDS` moved from `delete.py:_PROPOSAL_KINDS`.
   - `Candidate` (`models_candidate`): `recommendation: str | None = None`, `reason: str | None = None`; docstring updated.
   - `DeleteResult`: `would_delete: bool = False`.
   All new fields default, so existing constructors and equality tests hold.

3. **`recommend` (C2).** Depends on 2.
   File: `dummyindex/context/domains/gc/recommend.py` (new). Export `Recommendation`, `recommend` from `dummyindex/context/domains/gc/__init__.py` and list them in its docstring.
   Implement the C2 table, first match wins. Reuse `receipt_path` (`retirement_receipt_path`) and `PROPOSAL_KINDS`.
   Test: `tests/context/domains/gc/test_recommend.py` (new) per the C2 acceptance item, plus an import smoke test from the package.

4. **Dry-run through the guard ladder (C4).** Depends on 2.
   File: `dummyindex/context/domains/gc/delete.py`.
   `delete_workspace` (`delete_delete_workspace`) gains `dry_run: bool = False`. When set, call `_delete_workspace_locked` (`delete_delete_workspace_locked`) directly, without `project_lock`. Pass `dry_run` through; return `DeleteResult(would_delete=True)` right before `shutil.rmtree`. Use `PROPOSAL_KINDS` from constants. Fix the docstring line "The CLI's read-only dry-run never calls this operation".
   Test: `tests/context/domains/gc/test_delete.py` — dry-run leaves a deletable target on disk; receipt-less material proposal raises `GcTargetError`; dry-run works while the lock is held. Keep `test_retirement_guards_execute_under_shared_project_lock` green.

5. **Closeout draft (C5).** Depends on 1.
   File: `dummyindex/context/domains/proposals/draft.py` (new). Export from `dummyindex/context/domains/proposals/__init__.py`.
   `draft_manifest(context_dir, kind, slug) -> dict` and `write_draft(context_dir, kind, slug) -> Path`. Reuse `workspace_inventory`, `ADMIN_FILES`, `contained` (`proposals/retirement.py`), `parse_checklist` + `counts` (`checklist_parse_checklist`, `checklist_counts`), `proposal_dir` + `validate_slug` (`store_proposal_dir`), `audits_root` + `validate_slug` + `report_written` (`audit/workspace.py`), `write_text_atomic` (`atomic_io_write_text_atomic`). Raise `CloseoutError` when the draft exists or the workspace is missing.
   Test: `tests/context/domains/test_closeout_draft.py` (new) per the C5 acceptance items.

6. **Orphaned anchor and scan enrichment (C6, C2 wiring).** Depends on 2, 3.
   Files: `dummyindex/context/domains/gc/anchor.py`, `dummyindex/context/domains/gc/scan.py`.
   - `should_signal` (`anchor_should_signal`): one `gc_commits_since` call; on `None`, fire only if `anchor_orphaned` (`anchor_anchor_orphaned`).
   - `anchor_orphaned`: return False when `git rev-parse --is-shallow-repository` prints `true`. Confirm `commits_since` (`build/git_delta.py`) returns `None` only for an unknown sha, no anchor, unborn HEAD or off-git.
   - `scan` (`scan_scan`): `should_signal = (commits is not None and commits >= threshold) or orphaned`; fill `recommendation` and `reason` via `recommend` with `dataclasses.replace`. Update the module docstring on the pure-threshold flag.
   Test: `tests/context/domains/gc/test_anchor.py` per the C6 acceptance item.

7. **CLI wiring and help (C3, C4, C5, C6).** Depends on 4, 5, 6.
   Files: `dummyindex/cli/gc.py`, `dummyindex/cli/help.py`.
   - `_status_payload` / `_print_status`: per-candidate `recommendation` + `reason`, `summary`, header counts, `ran, nothing to retire` line.
   - `_gc_delete`: without `--yes`, call `delete_workspace(dry_run=True)`; share result printing and exit mapping with `--yes`; print the dry-run lines when `would_delete`.
   - `_gc_closeout`: accept `--draft`; with it, skip `--manifest`, call `write_draft`, print the path; map `CloseoutError` to exit 2.
   - `_gc_signal`: when fired and `anchor_orphaned`, print the orphaned line.
   - Module docstring, `_GC_USAGE` and the unknown-verb message list `closeout`.
   - `help.py` gc block (~line 495): `closeout [--draft]`, status recommendations, dry-run guard verdict.
   Test: `tests/cli/test_gc_cli.py` per the C3, C4, C5, C6 and end-to-end acceptance items. Split `test_delete_without_yes_is_dry_run_deletes_nothing` into the three C4 cases. Widen the key sets in `test_status_json_emits_expected_shape`.

8. **Skill (C7).** Depends on 5, 7.
   File: `dummyindex/skills/gc/SKILL.md`.
   Edit steps 1–6 and add the sweep report per C7. Keep the contract line, `CONFIRM WITH THE USER`, every `non-dispatchable` / `human-decision` marker and the dogfood GATE. Every runnable `gc delete` line carries `--yes` or the word `dry-run`. Update the status key list (line ~31) and the CLI reference block (`--draft`, dry-run verdict, `recommendation`/`reason`/`summary`).
   Test: `tests/test_skills_doc_hygiene.py` — add the C7 phrase asserts; existing gc tests stay green.

9. **Curated docs.** Depends on 7, 8.
   Files: `.context/playbooks/gc-context.md`, `.context/features/gc/spec.md`.
   Playbook: recommendations, `--draft`, batch confirmation, per-item risk rows, sweep report; note `HOW_TO_USE.md` describes the older status output until its template changes. Feature spec: recommendation contract, dry-run verdict, INDEX.md exclusion, orphaned-anchor nudge, evolution seam. Cite source `path:line`, never a proposal path.

10. **Acceptance.** Run the full suite. Run the bootstrap dry-run report from `spec.md` on this repo. Delete nothing.

## Out of scope

- `dummyindex/context/output/instructions.py` (HOW_TO_USE template) — D13.
- Evolution cleanup code — C8 / D14.
- The archived-dir resolution in `signals.classify` (computes on `proposals/<slug>`, not `_archive/<slug>`). Archived rows get `review`, so it does not affect recommendations.
- INDEX.md generation, git-commit signals, config keys, a batch CLI verb, a repo-walk cache.
