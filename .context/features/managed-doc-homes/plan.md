# Managed doc homes: plan

`confidence: INFERRED`

## Where it lives

**Kernel: one classifier, no I/O** (`dummyindex/context/domains/docguard/`):

| Path | Role |
|---|---|
| `classify.py:53-117` | `classify_doc_path`: lexical verdict for one path. |
| `classify.py:120-168` | `group_strays`: pairs spec and plan, disambiguates slugs. |
| `constants.py:49-57` | Closed sets: `PLANNING_SEGMENTS`, `EXCLUDED_DOCS_SUBTREES`, `ROOT_DOC_STEMS`. |
| `citations.py:12-81` | Citation pattern, durable-doc set, `added_citations`, `scan_durable`. |
| `models.py`, `enums.py`, `errors.py` | Frozen records, `DocKind`/`DocRole`, `DocGuardError` family. |

**Consumer A: migration** (batch, mutating, fail-closed):
- `migrate.py:64` `enumerate_strays`, `:94` `plan_moves`, `:165` `apply_moves`.
- `cli/migrate_docs.py`: wire-only driver with `--json`.

**Consumer B: write guard** (per tool call, read-only, fail-open):
- `decision.py:33` `decide`: classification to PreToolUse payload.
- `cli/guard_doc_write.py:49-98`: tool gate, config gate, citation check, stray check.
- `cli/guard_doc_write.py:101-172`: `_new_texts`, `_repo_rel`, `_citation_deny`.

**Consumer C: citation check** (shared predicate):
- `citations.py:30` `added_citations`, `:60` `scan_durable`, read by `cli/check.py:199-212` (`--refs`).
- `cites_disposable` is also used by `domains/proposals/closeout.py:426,462` and `retirement.py:156`.

**Shared seam and wiring:**
- `context/git.py:39-77`: `is_git_repo`, `run_git`, `is_tracked`.
- `domains/config.py:571`: `read_doc_guard_settings`, the tolerant hot-path reader.
- `context/hooks.py:245-267`: `_PRE_TOOL_USE_HOOK`, registered at `:275`.
- Verbs: `context/enums.py:159-162`, `cli/__init__.py`, `cli/help.py`.

**Tests:** `tests/context/domains/docguard/test_classify.py` (gate table), `test_migrate.py` (filesystem and git), `test_citations.py` (predicate, durable set, scan), `tests/context/test_git.py`, `tests/cli/test_migrate_docs_cli.py`, `tests/cli/test_guard_doc_write.py` (tool matrix, edits, fail-open), `tests/cli/test_guard_doc_write_e2e.py` (subprocess; no-exit-2 and no-subprocess invariants), `tests/cli/test_check_refs.py`.

## Architecture

Pure cores (`classify.py`, `decision.py`, `citations.py`) hold every judgement about a path or text. Imperative shells read stdin or disk and print or move. `migrate.py` moves files. `guard_doc_write.py` reads hook JSON and prints one decision. Shells never re-derive a rule, so the relocator and the live guard cannot disagree about what a stray is. Shells reach git and config only through narrow seams, so the feature adds no cross-domain private imports.

## Data model

Persistent state is the `.context/` layout plus two config keys. In-memory records are frozen dataclasses:

```
path -> DocClassification -> StrayGroup -> MovePlan{PlannedGroup[MoveItem], MoveSkip[]}
     -> MoveResult{moved, skipped, dry_run}
```

Migration writes `proposals/<slug>/proposal.json` (status `done`, only when absent), relocated files, and `audits/<slug>/` via `audit/workspace.py:ensure_audit`. Config v2 to v3 adds `doc_guard_enabled` and `doc_guard_allow` (`domains/config.py:228-229`).

There is no rollback. Pass 1 of `plan_moves` is the prepare step. Each move is `git mv` or `Path.replace` into a fresh directory, and re-runs are idempotent (`test_migrate.py`).

## Key decisions

**Decided: the guard never exits 2.** A PreToolUse exit 2 blocks the tool. `run` wraps everything in `except Exception: return 0` (`guard_doc_write.py:36-46`). A deny JSON is the only block. Migration fails closed (`cli/migrate_docs.py` exits 2), because it runs deliberately with `--yes`.

**Decided: stray classification is location-gated to `docs/`.** A `*-design.md` or dated filename is a stray only under `docs/` (`classify.py:88-90`). Filename-only heuristics would fire on vendored and source markdown. Accepted gap: root `PLAN.md` and `.claude/` plans are invisible.

**Decided: unplaceable strays fail open.** When a stem has no alphanumeric content, `_derive_slug` returns `None` (`classify.py:206-221`). `decide` then allows (`decision.py:45-50`). The guard blocks only when it can name the destination.

**Decided: citation check is a set difference.** Only citations absent from the existing file deny (`citations.py:30-32`). Existing debt never blocks an edit. The check runs before the stray check and ignores `doc_guard_allow`.

**Decided: `Write` creates, `Edit` and `MultiEdit` maintain.** The stray check is `Write`-only (`guard_doc_write.py:83-86`), because edits target existing files. The citation check covers all three tools.

**Decided: git is branched on first.** `is_tracked` returns `True` off-git, so `apply_moves` resolves `is_git_repo` once (`migrate.py:186`). Non-git moves use `Path.replace` with zero git calls.

**Decided: migrated proposals get `write_proposal_json`.** `ensure_proposal` would scaffold a template checklist. That reads as in-flight work to the hygiene GC.

**Decided: `--force` fills and never clobbers.** `_is_present` (`migrate.py:347-354`) treats only a non-empty file as present. Empty placeholders are filled.

**Decided: superpowers plan paths are strays.** When enabled, the guard denies `writing-plans` output under `docs/superpowers/{plans,specs}`. Repos exempt them with `doc_guard_allow` (`constants.py:49`, `:57`).

**Decided: the guard hot path runs no subprocess or git calls.** `test_no_subprocess_on_guard_path` locks this (`tests/cli/test_guard_doc_write_e2e.py:342`). The citation check reads the target file (`guard_doc_write.py:155`).

**Decided: a failed `git mv` falls back to replace plus `git add`.** `migrate.py:277-281`.

**Decided: `_derive_slug` pre-checks alphanumerics.** This avoids the `slugify` `"audit"` fallback (`classify.py:206-221`).

**Decided: `_is_within` is copied locally.** This avoids a cross-domain private import (`migrate.py:330`).

**Rejected: copying `reconcile_gate`'s `return 2` on arg errors.** The guard ignores leftover args instead (`guard_doc_write.py:175-181`).

**Decided: hook rides `_CLAUDE_HOOKS`.** Appending to `hooks.py:275` gives install, uninstall and status for free. The legacy scrub touches only `PostToolUse` (`hooks.py:281`). `_SILENT_GATE` keeps global installs quiet. stdout is kept, because the deny JSON must reach the host.

## Open questions

1. **The git seam has one consumer.** The guard never calls it, and `gc/delete.py` keeps its own `_is_tracked`. Intent for gc is not in the code.
2. **Migration does not invalidate downstream links.** `.context/architecture/overview.md` still links relocated `docs/` paths. No command triggers a rebuild or reconcile.
3. **Collision suffixes depend on the run.** `_disambiguate` (`classify.py:236-243`) sees only slugs minted in this run, not existing homes.
4. **`doc_guard_allow` glob semantics are unspecified.** `fnmatch` (`guard_doc_write.py:91`) lets `*` cross `/`.
5. **Denies are unobservable.** No `--json`, counter or log records a deny.
6. **Audit groups keep both members.** A spec member and a plan member both land in the audit workspace. Intent is not determinable from this code.
