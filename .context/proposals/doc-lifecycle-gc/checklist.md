# Checklist — Context-hygiene GC (doc-lifecycle-gc)

> Work wave-by-wave, top-to-bottom. Items in one wave are mutually independent
> (disjoint files) and may be dispatched in parallel; a wave starts only when
> every earlier wave is fully ticked. Tick `- [x]` only after verifying.

## Wave 1 — foundations (independent, disjoint files)
- [x] Add `commits_since(root, anchor)` to `dummyindex/context/build/git_delta.py` + git-fixture test in `tests/context/build/test_git_delta.py` (count, off-git→None, unborn-HEAD→None, unknown-sha→None)
- [x] Add `ProposalStatus.SUPERSEDED` to `dummyindex/context/domains/proposals/enums.py`; round-trip test in `tests/context/domains/test_propose.py` (existing values still load)
- [x] Extract `report_written(context_dir, slug)` into `dummyindex/context/domains/audit/workspace.py` (re-export from audit `__init__.py`), call it from `cli/audit.py:157`; unit + existing audit tests green
- [x] Scaffold `dummyindex/context/domains/gc/` skeleton: `enums.py` (Disposition, CandidateKind), `constants.py` (DEFAULT_COMMIT_THRESHOLD=10, roots, sentinel, anchor/memo rel-paths), `errors.py` (GcError/GcPathError/GcTargetError), `models.py` (Candidate, SweepReport, DeleteResult — frozen)

## Wave 2 — gc domain logic (independent, disjoint files)
- [x] `dummyindex/context/domains/gc/enumerate.py` — `enumerate_candidates` (skip `_`-prefixed sentinels, surface `_archive/*` children as ARCHIVED, exclude session-memory) + `tests/context/domains/gc/test_enumerate.py`
- [x] `dummyindex/context/domains/gc/signals.py` — `classify` (orphan-empty = templates byte-equal; checklist completion via buildloop counts; report-written; untracked; age via git commit date only) + `tests/context/domains/gc/test_signals.py`
- [x] `dummyindex/context/domains/gc/anchor.py` — committed `gc/state.json` anchor (corrupt→None), gitignored `cache/` fire-once memo, `should_signal`, `stamp_gc`, `anchor_orphaned` + `tests/context/domains/gc/test_anchor.py`
- [x] `dummyindex/context/domains/gc/delete.py` — `delete_workspace` guard ladder (slug→sentinel→realpath→liveness→recoverability→rmtree) + `tests/context/domains/gc/test_delete.py` (`_archive`→GcTargetError, symlink→GcPathError, partial/untracked refusals, missing-dir no-op)

## Wave 3 — domain public surface
- [x] `dummyindex/context/domains/gc/__init__.py` — re-export public functions + dataclasses + errors (`__all__`, mirroring `proposals/__init__.py`)

## Wave 4 — CLI surface + registration
- [x] `dummyindex/cli/gc.py` (wire-only) sub-dispatching `status|delete|stamp|signal`; add `GC` to `dummyindex/context/enums.py`, map in `dummyindex/cli/__init__.py`, help block in `dummyindex/cli/help.py`; `tests/cli/test_gc_cli.py` + help-text test in `tests/cli/test_subcommand_help.py`

## Wave 5 — skill, docs, hook (independent, disjoint files)
- [x] Author `dummyindex/skills/gc/SKILL.md` — the council orchestration (gc status → PageIndex walk → user-confirm → gc delete / implementer+tester / new proposal → gc stamp → reconcile); never shows `gc delete` without `--yes`; confirm + dogfood marked non-dispatchable
- [x] Docs: `.context/HOW_TO_USE.md` hygiene-lifecycle section + `.context/gc/` in canonical layout, new `.context/playbooks/gc-context.md`, `cli/help.py` gc verbs, bootstrap note in `dummyindex/context/output/bootstrap.py`
- [x] Wire `gc signal` into the SessionStart hook in `dummyindex/context/hooks.py` + `dummyindex/context/claude_settings.py` (coexists with `plan-update` + `memory session-start`); extend `tests/context/test_hooks.py`

## Wave 6 — skill registration + doc-hygiene (depend on Wave 5)
- [x] Register `dummyindex-gc` in `dummyindex/installer/install.py`, `dummyindex/installer/uninstall.py`, and the `test_install_copies_sibling_skills` roster in `tests/test_install.py` (install→uninstall leaves no `dummyindex-gc/`)
- [x] Extend `tests/test_skills_doc_hygiene.py` with gc-skill cases (non-dispatchable confirm+GATE; ordered contract documented; no `gc delete` without `--yes`)

## Wave 7 — verification
- [x] Full suite green on 3.10 + 3.12 (`python -m pytest tests/ -q`), no `print` in `domains/gc/`, gc dataclasses frozen, gc errors subclass `GcError`; confirm the synthetic-fixture `gc status` + the full delete-guard matrix + SessionStart coexistence acceptance criteria all hold — via /dummyindex-verify

## Wave 8 — review + acceptance
- [x] Convention review of the whole gc diff against the repo's conventions + per-feature concerns (routes to `dummyindex-reviewer`)
- [x] **GATE** Dogfood `/dummyindex-gc` on this repo: confirm `gc status` surfaces the live orphan/superseded candidates (read from `gc status`, not a hard-coded list); actual deletion is the user's explicit confirm
