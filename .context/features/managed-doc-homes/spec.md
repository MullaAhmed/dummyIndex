# Feature: Managed doc homes

Keeps internal planning artifacts (plans, specs, design docs, audits) in their **managed `.context/` homes** — `proposals/<slug>/` and `audits/<slug>/` — instead of leaking into the user-facing `docs/` tree. One **shared, location-gated classifier** backs two capabilities: a deterministic relocation command and a PreToolUse write-guard that stops the leak recurring.

## Architecture

A single source of truth — `domains/docguard/classify.py:classify_doc_path` — decides whether a `.md` path is a stray planning doc and where it belongs. Two consumers sit on top of it:

1. **Migration** (`domains/docguard/migrate.py` + `cli/migrate_docs.py`) — `dummyindex context migrate-docs` relocates existing strays under `docs/` into their managed homes, preserving git history.
2. **Write-guard** (`domains/docguard/decision.py` + `cli/guard_doc_write.py`) — `dummyindex context guard-doc-write` is a PreToolUse `Write` hook that denies a *fresh* write creating a planning doc in an unmanaged location.

A small cross-cutting **git-fact seam** (`context/git.py`) is the one place new code asks git questions, so the feature adds **zero** cross-domain private imports.

## Key components

- **`context/git.py`** — `is_git_repo` (pure-filesystem, re-exported from `pipeline/io/git.py`), `is_tracked`, `run_git(root, *args) -> CompletedProcess` (modeled on `build/git_delta.py:_run_git`). Callers branch on `is_git_repo` **first**; `is_tracked` preserves the documented non-git degradation (`True` when off-git) from `gc/delete.py`.
- **`domains/docguard/classify.py`** — `classify_doc_path(repo_root, path) -> DocClassification` (pure/lexical, no I/O) and `group_strays(repo_root, paths) -> tuple[StrayGroup, ...]`. Planning-doc signals are **location-gated**: a `.md` under `docs/` in a `plans|specs|proposals|audits` segment (incl. `docs/internal/*`, `docs/superpowers/{plans,specs}`), or a `*-design.md` / `YYYY-MM-DD-<name>.md` filename under such a dir. Excludes `.context/` (sets `in_managed_location`), `docs/{guide,reference,sources}`, root chrome, non-`.md`. Slug = `audit/workspace.py:slugify` → `proposals/store.py:validate_slug`, skip-on-fail. Pairing key is `(directory, stem)`.
- **`domains/docguard/migrate.py`** — `enumerate_strays` (filesystem walk, skips symlinks) → `plan_moves` (whole-plan transactional pre-validation: every slug valid, every source/target realpath-contained, aborts before any move) → `apply_moves` (dry-run by default). Branches `is_git_repo` first: non-git → `Path.replace`; tracked → `git mv` (history preserved); untracked → `Path.replace` + `git add`. `--force` fills only *missing* files (never clobbers a non-empty target). Audits land via `audit/workspace.py:ensure_audit`.
- **`domains/docguard/decision.py`** — pure builder mapping a `DocClassification` to the PreToolUse decision dict: a `deny` (with interpolated `suggested_home`/`spec.md|plan.md`) for a placeable stray, `{}` (allow) otherwise.
- **`cli/guard_doc_write.py`** — wire-only. `Write`-only matcher; **fail-open everywhere** (exit 0 on every path except an explicit JSON deny, **never `exit 2`**); no git/subprocess on the hot path; config-gated by `doc_guard_enabled` + a `doc_guard_allow` glob allowlist (read via the cheap `domains/config.py:read_doc_guard_settings` accessor).
- **`cli/migrate_docs.py`** — wire-only, mirrors `cli/gc.py`: `--root/--yes/--force/--json`, dry-run by default, whole-plan refusal → exit 2.
- **`domains/proposals/store.py:write_proposal_json`** — narrow writer the migration uses: writes **only** `proposal.json` (terminal status `done`, no template `spec.md`/`plan.md`/`checklist.md` to collide with the relocation), byte-identical to `ensure_proposal`.

## Config & wiring

- **`domains/config.py`** — schema `v2→3` adds typed `doc_guard_enabled: bool = True` and `doc_guard_allow: tuple[str, ...] = ()`, a value-preserving `migrate_config_in_place` step, and `read_doc_guard_settings(context_dir)` — a tolerant `(enabled, allow_globs)` accessor that never builds a full `Config` on the Write hot path and defaults to `(True, ())` on absent/malformed config (default-ON everywhere).
- **`context/hooks.py`** — a managed **PreToolUse** entry (matcher `"Write"`, command `dummyindex context guard-doc-write`) built from `_SILENT_GATE` so a global install gets the defer-check guard. Appended to `_CLAUDE_HOOKS`, so it flows through `install`/`uninstall`/`status`/`all_installed` automatically; `PreToolUse ≠ legacy PostToolUse`, so the legacy scrub leaves it alone.
- Verbs registered in `context/enums.py:ContextSubcommand` (`MIGRATE_DOCS`, `GUARD_DOC_WRITE`), the `cli` dispatcher, `cli/help.py`, `docs/guide/07-cli.md`, `HOW_TO_USE.md`, and `playbooks/migrate-stray-docs.md`.

## Concerns / invariants

- **The guard must never wedge a session.** It is `Write`-only, config-gated, and fail-open — a single bad classification can only ever *allow*, never block (never `exit 2`). An unplaceable stray (no slug-able content) deliberately fails open rather than emit a `None/spec.md` deny.
- **The guard upholds "hooks never rebuild the backbone."** Unlike the retired PostToolUse hook, it mutates nothing (pure read→classify→deny).
- **Migration is transactional and non-destructive.** Whole-plan pre-validation aborts before any move; realpath containment refuses `..`/symlink escapes (nothing moved); `--force` never clobbers a non-empty file; it never touches source code or moves outside `docs/`.
- **Migrated proposals carry terminal `status` and no template checklist**, so the context-hygiene GC won't read them as in-flight.
- **Behavioral override:** when enabled, the guard denies the superpowers `writing-plans` skill's default writes to `docs/superpowers/{plans,specs}` — intended, and a repo can exempt a published path via `doc_guard_allow`.

Implemented by proposal `enforce-managed-doc-homes` (TDD, full suite green).
