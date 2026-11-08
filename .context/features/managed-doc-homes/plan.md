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
| `language.py` | `cjk_share`, `needs_warning`: prompt language share. |
| `models.py`, `enums.py`, `errors.py` | Frozen records, `DocKind`/`DocRole`, `DocGuardError` family. |

**Consumer A: migration** (batch, mutating, fail-closed):
- `migrate.py:64` `enumerate_strays`, `:94` `plan_moves`, `:165` `apply_moves`.
- `cli/migrate_docs.py`: wire-only driver with `--json`.

**Consumer B: write guard** (per tool call, read-only, fail-open):
- `decision.py:33` `decide`: classification to PreToolUse payload.
- `cli/guard_doc_write.py:53-104` `_decide`: language hint, tool gate, config gate, citation check, stray check.
- `cli/guard_doc_write.py:107-135` `_language_hint`.
- `cli/guard_doc_write.py:138-209`: `_new_texts`, `_repo_rel`, `_post_edit_text`, `_citation_deny`.

**Consumer C: citation check** (shared predicate):
- `citations.py:30` `added_citations`, `:60` `scan_durable`, read by `cli/check.py:263-273` (`--refs`).
- `cites_disposable` is also used by `domains/proposals/closeout.py:426,462` and `retirement.py:159`.

**Shared seam and wiring:**
- `context/git.py:39-77`: `is_git_repo`, `run_git`, `is_tracked`.
- `domains/config.py:571`: `read_doc_guard_settings`, the tolerant hot-path reader.
- `context/hooks.py:258-279`: `_PRE_TOOL_USE_HOOK`, registered at `:287`.
- Verbs: `context/enums.py:159-162`, `cli/__init__.py`, `cli/help.py`.

**Tests:**
- `tests/context/domains/docguard/test_classify.py` (gate table), `test_migrate.py`, `test_citations.py`, `test_language.py` (CJK share).
- `tests/context/test_git.py`, `tests/cli/test_migrate_docs_cli.py`, `tests/cli/test_check_refs.py`.
- `tests/cli/test_guard_doc_write.py`: tool matrix, edits, language hint, fail-open.
- `tests/cli/test_guard_doc_write_e2e.py`: subprocess, no-exit-2 and no-subprocess invariants.

## Architecture

Pure cores (`classify.py`, `decision.py`, `citations.py`, `language.py`) hold every judgement about a path or text. Imperative shells read stdin or disk and print or move. `migrate.py` moves files. `guard_doc_write.py` reads hook JSON and prints one decision or nothing. Shells never re-derive a rule, so the relocator and guard agree on strays. Shells reach git and config only through narrow seams, so the feature adds no cross-domain private imports.

## Data model

State lives in `.context/`. In-memory records are frozen dataclasses:

```
path -> DocClassification -> StrayGroup -> MovePlan{PlannedGroup[MoveItem], MoveSkip[]}
     -> MoveResult{moved, skipped, dry_run}
```

Migration writes `proposals/<slug>/proposal.json` (status `done`, only when absent), relocated files, and `audits/<slug>/` via `audit/workspace.py:ensure_audit`. Config v2 to v3 adds `doc_guard_enabled` and `doc_guard_allow` (`domains/config.py:228-229`).

No rollback exists. `plan_moves` pass 1 is the prepare step. Moves use `git mv` or `Path.replace`. Re-runs are idempotent (`test_migrate.py`).

## Key decisions

**Decided: the guard never exits 2.** A PreToolUse exit 2 blocks the tool. `run` wraps everything in `except Exception: return 0` (`guard_doc_write.py:40-50`). A deny JSON is the only block. Migration fails closed (`cli/migrate_docs.py` exits 2) since it runs with `--yes`.

**Decided: stray classification is location-gated to `docs/`.** A `*-design.md` or dated filename is a stray only under `docs/` (`classify.py:88-90`). Filename-only heuristics would fire on vendored and source markdown. Accepted gap: root `PLAN.md` and `.claude/` plans are invisible.

**Decided: unplaceable strays fail open.** A stem with no alphanumerics makes `_derive_slug` return `None` (`classify.py:206-221`), avoiding the `slugify` `"audit"` fallback. `decide` then allows (`decision.py:45-50`).

**Decided: citation check is a set difference.** Only citations absent from the existing file deny (`citations.py:30-32`). The check runs before the stray check and ignores `doc_guard_allow`.

**Decided: `Write` creates, `Edit` and `MultiEdit` maintain.** The stray check is `Write`-only (`guard_doc_write.py:89-92`) because edits target existing files. The citation check covers all three tools.

**Decided: git is branched on first.** `is_tracked` returns `True` off-git, so `apply_moves` resolves `is_git_repo` once (`migrate.py:186`). Non-git moves use `Path.replace`.

**Decided: migrated proposals get `write_proposal_json`.** `ensure_proposal` scaffolds a template checklist, which reads as in-flight work to the hygiene GC.

**Decided: `--force` fills and never clobbers.** `_is_present` (`migrate.py:347-354`) treats only a non-empty file as present.

**Decided: superpowers plan paths are strays.** When enabled, the guard denies `writing-plans` output under `docs/superpowers/{plans,specs}`. Repos exempt them with `doc_guard_allow` (`constants.py:49`, `:57`).

**Decided: the guard hot path runs no subprocess or git calls.** `test_no_subprocess_on_guard_path` locks this (`tests/cli/test_guard_doc_write_e2e.py:342`). The citation check reads the target file (`guard_doc_write.py:192`).

**Decided: a failed `git mv` falls back to replace plus `git add`.** `migrate.py:277-281`.

**Decided: `_is_within` is copied locally.** This avoids a cross-domain private import (`migrate.py:330`).

**Rejected: copying `reconcile_gate`'s `return 2` on arg errors.** The guard ignores leftover args instead (`guard_doc_write.py:212-223`).

**Decided: hook rides `_CLAUDE_HOOKS`.** Appending to `hooks.py:287` gives install, uninstall and status for free. The legacy scrub touches only `PostToolUse` (`hooks.py:293`). `_SILENT_GATE` keeps global installs quiet. stdout is kept because the deny JSON must reach the host.

**Decided: the language hint warns, never denies.** It runs before the `doc_guard_enabled` gate and emits only `additionalContext`.

## Open questions

1. **The git seam has one consumer.** The guard never calls it, and `gc/delete.py` keeps its own `_is_tracked`. Intent for gc is not in the code.
2. **Migration does not invalidate downstream links.** `.context/architecture/overview.md` still links relocated `docs/` paths. No command rebuilds or reconciles.
3. **Collision suffixes depend on the run.** `_disambiguate` (`classify.py:236-243`) sees only slugs minted in this run, not existing homes.
4. **`doc_guard_allow` glob semantics are unspecified.** `fnmatch` (`guard_doc_write.py:97`) lets `*` cross `/`.
5. **Denies are unobservable.** No `--json`, counter or log records a deny.
6. **Audit groups keep both members.** A spec member and a plan member both land in the audit workspace. Intent is not determinable from this code.
7. **`SendMessage` is not in the official hook docs.** If it never fires, the hint stays silent.
