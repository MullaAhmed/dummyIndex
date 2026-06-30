# Plan — Enforce managed doc homes: migrate stray docs/ plans/specs/audits into .context/ and add a PreToolUse write-guard to prevent recurrence

> Ordered, file-path-naming tasks; reused symbols cited from `.context/map/symbols.json`.
> New domain package `dummyindex/context/domains/docguard/` mirrors the `gc/` layout
> (`constants.py`/`enums.py`/`errors.py`/`models.py` + behavior modules). Revised after the
> critique panel (see the one-line note at the bottom).

## Tasks

### T0 — Shared git-fact seam *(Wave 1)*
- **Files:** `dummyindex/context/git.py` (new top-level helper), `tests/context/test_git.py`.
- `is_git_repo(root)`, `is_tracked(root, path)`, `run_git(root, *args)` — the single cross-cutting git seam so new code never imports `gc`'s private `_is_tracked`/`_is_git_repo`. Model `run_git` on `build/git_delta.py:_run_git` (the real subprocess precedent; `gc/delete.py` uses `shutil.rmtree`). Preserve the documented non-git semantics but expose `is_git_repo` so callers branch on it first.
- **Reuse:** `pipeline/io/git.py:is_git_repo`/`resolve_git_dir` (filesystem probe) where possible; `build/git_delta.py:_run_git` pattern for subprocess.

### T0b — Config schema extension *(Wave 1)*
- **Files:** `dummyindex/context/config.py`, `tests/.../test_config*.py`.
- Add typed `doc_guard_enabled: bool = True` **and** `doc_guard_allow: tuple[str,...] = ()` (resolved: default on everywhere + allowlist) to `Config` + `to_dict`/`from_dict`/`default_config`; bump `CONFIG_SCHEMA_VERSION` 2→3; add a value-preserving step to `migrate_config_in_place`. Add a **cheap tolerant accessor** returning `(enabled, allow_globs)` that try/excepts a missing/malformed config to the defaults — never builds a full `Config` on the hot path.
- **Reuse:** existing `Config`/`migrate_config_in_place`/`CONFIG_SCHEMA_VERSION`.

### T1 — Shared classifier *(Wave 1)*
- **Files:** `dummyindex/context/domains/docguard/{__init__,constants,enums,errors,models,classify}.py`, `tests/context/domains/docguard/{__init__,test_classify}.py`.
- `classify_doc_path` per spec: location-gated path/filename heuristics; `DocClassification` frozen dataclass (`models.py`); `DocKind` str-enum (`enums.py`, mirror `gc/enums.py`); typed errors (`errors.py`). Slug = `slugify(stem)` → `validate_slug`, skip-on-failure. Pairing key `(directory, stem)`.
- **Reuse:** `domains/proposals/store.py:validate_slug`/`proposals_root`, `domains/audit/workspace.py:slugify`/`audits_root`.
- **Tests:** full matrix incl. `docs/superpowers/plans/...`, bare-date form, negative controls (outside-`docs/`, guide/README, managed-location), pairing (paired / spec-only / plan-only / slug-collision), awkward-filename slug.

### T2 — Migration domain (+ narrow proposal.json writer) *(Wave 2)*
- **Files:** `dummyindex/context/domains/docguard/migrate.py`; **add** `write_proposal_json(context_dir, slug, title, *, status)` to `dummyindex/context/domains/proposals/store.py` (reuse `Proposal.to_dict` + `context/atomic_io.py:write_text_atomic`); `tests/context/domains/docguard/test_migrate.py`.
- `enumerate_strays` (sorted; skip symlinks via `is_symlink()`); `plan_moves` = **whole-plan pre-validation** (targets free, slugs valid, realpath-contained) aborting before any move; `apply_moves(plan,*,yes,force)`: create dir → write **only** `proposal.json` (status `done`, no template spec/plan/checklist) → relocate stray onto `spec.md`/`plan.md`. Branch on `git.is_git_repo` first: non-git → `Path.replace` all; tracked → `git.run_git("mv")`; untracked-in-repo → `Path.replace`+`git.run_git("add")`. `--force` fills only missing files. Audits → `audit/workspace.py:ensure_audit`.
- **Reuse:** T0 `context/git.py`; T1 `classify`; `proposals/store.py:proposal_dir`/`proposals_root`/new `write_proposal_json`; `audit/workspace.py:ensure_audit`/`audit_dir`; `gc/delete.py:_is_relative_to`-style realpath containment (or reuse the gc helper if promoted).
- **Tests:** tracked (`R` in index), untracked/gitignored (`A` staged), non-git, overwrite-refuse + `--force` (no clobber), `..`/symlink containment (nothing moved), source-untouched, idempotent re-run, title-from-H1 + fallback, byte-stable `proposal.json`, audit workspace valid.

### T3 — Write-guard decision + CLI *(Wave 2)*
- **Files:** `dummyindex/context/domains/docguard/decision.py`, `dummyindex/cli/guard_doc_write.py`, `tests/cli/test_guard_doc_write_e2e.py` + a `decision.py` unit test.
- `decision.py`: pure builder `DocClassification → allow({}) | deny(dict)` with interpolated `suggested_home`/`suggested_slug`. CLI mirrors `cli/reconcile_gate.py` structure but **never returns 2**: `read_hook_stdin` → require `tool_name=="Write"` → read `(enabled, allow_globs)` (cheap accessor) → if disabled, allow → `classify_doc_path` → if the path matches any `allow_glob` (fnmatch/PurePosixPath.match), allow → else print deny JSON. Catch-all → exit 0. No subprocess.
- **Reuse:** `cli/memory.py:read_hook_stdin`; `domains/docguard/classify.py`; T0b cheap config accessor.
- **Tests (e2e subprocess, feeding `json.dumps({...})` to stdin):** deny on stray, allow on managed/user-doc; fail-open on malformed stdin / non-`Write` (incl. `Edit`/`MultiEdit`) / missing `file_path` / outside-repo path / classify-raises; never `exit 2`; no `subprocess.run`; config-off + config-absent + config-malformed.

### T4 — Migration CLI *(Wave 3)*
- **Files:** `dummyindex/cli/migrate_docs.py`, `tests/cli/test_migrate_docs_cli.py`.
- Flags `--root/--yes/--force/--json`; dry-run default; delegates to `domains/docguard/migrate.py`; mirror `cli/gc.py` dry-run/`--yes` conventions; never crash the batch on one bad stray.
- **Reuse:** `cli/common.py:print_arg_error`; `cli/gc.py` flag patterns; T2 domain.
- **Tests:** dry-run snapshot (moves nothing) + sorted listing with pinned slugs; `--yes` end-to-end; `--json` exact key sets; exit codes.

### T5 — Wire the PreToolUse guard hook *(Wave 3)*
- **Files:** `dummyindex/context/hooks.py` (extend `install`/`status`/`uninstall`/`HookStatus`/`all_installed`), `dummyindex/cli/hooks.py` (status line); **update breaking tests** in `tests/context/test_hooks.py`.
- Build a PreToolUse entry (matcher `"Write"`, command `dummyindex context guard-doc-write`) from `_SILENT_GATE` + `_MANAGED_COMMENT`/`SENTINEL` so `_guard_body` inserts the global defer-check guard; wire via `claude_settings.py:install_hook_entry(event="PreToolUse", sentinel=SENTINEL)`. Add `claude_pre_tool_use` to `HookStatus` **and** `all_installed`; surface in `status()` + `cli/hooks.py`. `install.py` already calls `hooks.install` — confirm flow, no installer edit.
- **Reuse:** `claude_settings.py:install_hook_entry`/`remove_hook_entries`; `hooks.py:SENTINEL`/`_MANAGED_COMMENT`/`_SILENT_GATE`/`_guard_body`.
- **Tests:** update the named exact-assertion tests (`test_status_false_when_absent`, `test_install_writes_stop_and_precompact_hooks`, `test_status_true_after_install_all_three`); add install/idempotent(byte-stable)/uninstall; body carries self-gate + global guard; legacy-`PostToolUse` scrub keeps the guard yet still scrubs legacy; co-located + foreign user `PreToolUse` hooks preserved.

### T6 — Register verbs + enum + help + playbook *(Wave 4)*
- **Files:** `dummyindex/context/enums.py` (add `MIGRATE_DOCS`/`GUARD_DOC_WRITE` to `ContextSubcommand`), the `context` dispatcher, `dummyindex/cli/help.py`, `.context/playbooks/migrate-stray-docs.md` (new; includes "commit the move alone so `git log --follow` survives"), a pointer line in `.context/HOW_TO_USE.md`.
- Single task because both verbs touch the **one** enum + dispatcher + help module (disjoint from T5's `hooks.py`); runs after both CLIs exist.
- **Reuse:** existing `gc`/`reconcile-gate` verb-registration pattern.
- **Tests:** extend `tests/cli/test_subcommand_help.py` (enum-parametrized help covers both verbs); playbook-exists assertion.

### T7 — Acceptance pass *(Wave 5)*
- Run the full suite (`conventions/testing.md` command); walk every spec `## Acceptance` box against real CLI output on a throwaway fixture repo; tick only on observed green.

---
**Panel revision note (one round, folded):** *BLOCK×2* — dropped `ensure_proposal` for a narrow `write_proposal_json` (template files would collide with `git mv`); T5 now explicitly updates the exact-assertion hook tests it breaks. *HIGH* — shared `context/git.py` seam (no cross-domain private imports; non-git branch-first); typed `doc_guard_enabled` config field + migration (not an unknown-key read); guard scoped to `Write`-only, never `exit 2`, body carries self-gate + global guard; whole-plan transactional pre-validation; `--force` never clobbers; default-behavior raised as an Open Question. *MEDIUM* — slugify-before-validate skip-on-fail, `(dir,stem)` pairing + collision disambiguation, symlink skip, interpolated deny reason, terminal `status` so GC won't reanimate migrated docs, `ContextSubcommand` enum entries, byte-stability/`--json` key-set/source-untouched/idempotency tests. *Deliberately left:* consolidating `gc`'s existing private git dupes onto the new seam (out of scope — this feature adds none).
