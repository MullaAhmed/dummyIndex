# Spec — Enforce managed doc homes: migrate stray docs/ plans/specs/audits into .context/ and add a PreToolUse write-guard to prevent recurrence

## Intent

**Problem.** Internal planning artifacts (plans, specs, design docs, audits) keep leaking into the user-facing `docs/` tree. Root cause traced to session transcripts: the superpowers `writing-plans` skill defaults to gitignored `docs/superpowers/plans/`; a past session, wanting design docs *committed*, pattern-matched a stray tracked `docs/specs|plans` file as "the repo convention," and it became self-reinforcing across sessions. dummyindex never corrected it because its `rebuild`/`reconcile`/`gc` operate **only inside `.context/`** (no `docs/` migration) and it installs **only observe-only hooks** (no write-time guard). This repo was just cleaned by hand (16+ docs relocated in commit `0bd6d0b`); nothing stops it recurring or fixes it for other repos.

**For whom.** Any repo using dummyindex. The `.context/` index is the managed, GC-tracked home for planning artifacts (`proposals/<slug>/`, `audits/<slug>/`); `docs/` is the user-facing published tree and must stay free of internal planning docs.

**Solution — two capabilities sharing one classifier:**
1. **`dummyindex context migrate-docs`** — a deterministic, user-confirmed command that detects stray planning-doc markdown outside `.context/` and relocates each into its correct managed home, preserving git history and generating a valid `proposal.json`. Codifies exactly the manual `0bd6d0b` migration.
2. **PreToolUse write-guard** — a new managed hook (alongside the existing SessionStart/Stop/PreCompact hooks) that intercepts a `Write` creating a planning doc in an unmanaged location and **denies with guidance** pointing at the `.context/` home, so the leak can't recur.

## Contracts

### Shared git-fact seam (new top-level helper) — `context/git.py`
- `is_git_repo(root) -> bool`, `is_tracked(root, path) -> bool`, `run_git(root, *args) -> CompletedProcess`. One cross-cutting seam consumed by `docguard` (and available to `gc`) so no new code reaches across a domain boundary into `gc`'s private `_is_tracked`/`_is_git_repo`. The **git-mv subprocess precedent is `build/git_delta.py:_run_git`**, not `gc/delete.py` (which uses `shutil.rmtree`). `gc`'s existing private duplicates may later be consolidated onto this seam — out of scope here, but the seam exists so this feature adds **zero** cross-domain private imports.
- *Critical non-git semantics:* `gc/delete.py:_is_tracked` returns `True` when git is absent/not-a-repo (deliberate degradation). Migration must therefore branch on `is_git_repo(root)` **first**: in a non-git repo, move **every** file with `Path.replace` and make **no** git call.

### Config schema extension — `context/config.py`
- Add typed fields `doc_guard_enabled: bool = True` and `doc_guard_allow: tuple[str, ...] = ()` to the frozen `Config` (its `to_dict`/`from_dict`/`default_config`), bump `CONFIG_SCHEMA_VERSION` 2→3, and add a value-preserving entry to `migrate_config_in_place` (the install-surface migration path). Reading an unknown key off the strict `Config` is **not** an option — `from_dict` silently drops unknowns. The guard reads these through a **cheap, tolerant accessor** (try/except → defaults on absent/malformed config), never parsing the full `Config` (with `default_plugins`/`WiredEntry`) on the Write hot path.
- **Decision (resolved):** default **on everywhere** — `doc_guard_enabled` defaults `True` in every repo dummyindex touches (engages even before `.context/` exists). `doc_guard_allow` is a glob allowlist (e.g. `["docs/specs/**"]`) a repo sets to exempt a legitimately-published planning-doc path from the guard. A path matching any `doc_guard_allow` glob classifies as **not a stray** for guard purposes.

### Shared classifier (single source of truth) — `domains/docguard/classify.py`
- `classify_doc_path(repo_root, path) -> DocClassification` (frozen dataclass): `is_planning_doc`, `kind: DocKind` (`PROPOSAL|AUDIT|NONE`), `in_managed_location`, `suggested_slug`, `suggested_home`.
- **Planning-doc signals (path-based, conservative, location-gated):** a `.md` whose repo-relative path lies **under `docs/`** in a segment named `plans|specs|proposals|audits` (incl. `docs/internal/*`, `docs/superpowers/{plans,specs}`), OR whose filename matches the planning convention (`*-design.md`, `YYYY-MM-DD-<name>.md`) **under such a dir**. A `*-design.md` *outside* `docs/` (e.g. `src/widget-design.md`) is **not** a stray (location gate). **Excluded:** `.context/` (also sets `in_managed_location=true`), `docs/guide|reference|sources/`, root README/CHANGELOG/ARCHITECTURE/SECURITY, non-`.md`.
- **Slug:** `audit/workspace.py:slugify(stem)` **then** `proposals/store.py:validate_slug` — if it still fails, the stray is **skipped + reported**, never raised out of the batch.
- **Pairing key is `(directory, stem)`:** `<stem>-design.md` (spec) pairs with `<stem>.md` (plan) **in the same directory** under one slug. Two strays resolving to the same slug are suffix-disambiguated (`<slug>-2`) and the collision reported — never silently overwritten.

### Capability 1 — migration — `domains/docguard/migrate.py` + `cli/migrate_docs.py`
- `enumerate_strays(repo_root, context_dir) -> tuple[StrayGroup, ...]` (deterministic, sorted; skips symlinked strays via `is_symlink()`); `plan_moves(...) -> MovePlan`; `apply_moves(plan, *, yes, force) -> MoveResult`.
- **Transactional:** `plan_moves` pre-validates the **entire** plan (every target free, every slug valid, every source/target realpath-contained under `docs/`→`.context/`) and aborts the whole plan on the first failure **before any move executes**. Dry-run by default (`yes=False` → prints plan, moves nothing).
- **Move mechanics:** create the slug dir; write **only** `proposal.json` (via new `proposals/store.py:write_proposal_json`, status `done`, **no template `spec.md`/`plan.md`/`checklist.md`** — so the subsequent move doesn't collide); then relocate the stray onto `spec.md`/`plan.md`. Tracked → `run_git(root,"mv",...)` (history preserved); untracked-in-git-repo → `Path.replace` + `run_git(root,"add",...)`; non-git repo → `Path.replace` only. Audits → `.context/audits/<slug>/` via reused `audit/workspace.py:ensure_audit`.
- **`--force` fills only *missing* files** in an existing `proposals/<slug>` — it never overwrites a non-empty existing `spec.md`/`plan.md`/`proposal.json` (no data loss). Without `--force`, an existing slug dir is skipped + reported.
- **Never** touches source code; **never** moves outside `docs/`.
- CLI: `dummyindex context migrate-docs [--root DIR] [--yes] [--force] [--json]`.

### Capability 2 — write-guard — `cli/guard_doc_write.py` + `domains/docguard/decision.py`
- Wire-only CLI: reads PreToolUse JSON from stdin via reused `cli/memory.py:read_hook_stdin`, extracts `tool_name` and `tool_input.file_path`.
- **Matcher is `Write` only.** `Edit`/`MultiEdit` require the file to pre-exist, so they can only *maintain* an existing doc, never *create* a new leak — guarding them produces pure false positives and can loop the agent. Wave the matcher to `Write`.
- If `Write`'s target classifies as a planning doc in an unmanaged location → emit a **deny** with an **interpolated** reason naming the actual `suggested_home`/`suggested_slug`: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"<path> is an internal planning doc; write it to .context/proposals/<suggested_slug>/<spec.md|plan.md> instead of docs/."}}`. (No `migrate-docs` suggestion in a fresh-write deny — that command only relocates *existing* files.) Otherwise allow (exit 0, no output).
- **Fail-open, exit 0 on every path except an explicit JSON deny.** It must **never `exit 2`** (PreToolUse exit-2 = block) — do not inherit `reconcile_gate.py`'s `return 2` arg-error branch. Malformed/empty stdin, non-`Write` tool, missing `file_path`, a path the classifier can't make repo-relative, or any internal exception → exit 0, empty stdout. **No git, no network, no subprocess** on this path.
- **Config-gated** by `doc_guard_enabled` (cheap tolerant read above).

### Hook wiring — `context/hooks.py` + `cli/hooks.py`
- Add a PreToolUse entry (matcher `"Write"`, command `dummyindex context guard-doc-write`) built from `_SILENT_GATE` + `_MANAGED_COMMENT`/`SENTINEL` **so `_guard_body` inserts the global defer-check guard** (a body with no recognized gate gets none, and would fire the guard in *every* repo on a global-scope install). Extend `HookStatus` with `claude_pre_tool_use`, **update `all_installed` to include it**, surface it in `status()` + the `cli/hooks.py` status print, and remove it in `uninstall`. `install.py` already calls `hooks.install` → flows through every `dummyindex install`, idempotent.
- **Architectural note (stated honestly).** PreToolUse hooks were retired pre-0.13.5 because the old one **mutated `.context/`** (re-ran scaffolding, clobbered enrichment); this guard mutates **nothing** (pure read→classify→deny), so it upholds the "hooks never rebuild the backbone" invariant. *But* its blast radius is larger than the Stop reconcile-gate precedent (which blocks session-exit once per session): this denies on every `Write` for the whole session. That is why it is **config-gated**, **`Write`-only**, and (pending the open question) potentially **off-by-default** — a single bad classification must not be able to wedge a session.
- **Behavioral-override callout:** the classifier treats `docs/superpowers/{plans,specs}` as planning homes, so when enabled the guard **denies the superpowers `writing-plans` skill's default writes** — that is the intent, but it is a deliberate, documented override of another installed tool.

## Open questions

1. **Write-guard default + false-positive policy — RESOLVED (user, 2026-06-30): default *on everywhere* + `doc_guard_allow` allowlist, `Write`-only.** The guard ships `doc_guard_enabled=true` in every repo (engages even before `.context/` exists); a repo exempts a legitimately-published planning path (e.g. `docs/specs/`) by adding a glob to `doc_guard_allow`. Strongest recurrence-prevention; false-positive risk mitigated by the allowlist escape.

## Acceptance

**Classifier (`classify_doc_path`)**
- [ ] Fixture matrix labels correctly: `docs/specs/2026-06-08-x-design.md`→planning(PROPOSAL); `docs/plans/2026-06-08-x.md`→planning(PROPOSAL); `docs/superpowers/plans/2026-06-08-x.md`→planning(PROPOSAL); `docs/internal/audits/...REPORT.md`→planning(AUDIT); **negative controls** `src/widget-design.md`→NONE (outside `docs/`), `docs/guide/01-x.md`/`README.md`→NONE; `.context/proposals/foo/spec.md`→NONE + `in_managed_location=true`.
- [ ] Pairing: a dir with both `x-design.md` and `x.md` → exactly **one** `StrayGroup`/slug, two moves (`spec.md`+`plan.md`), one `proposal.json`; lone `x-design.md` (spec-only) and lone `x.md` (plan-only) each pin their slug+files; two same-slug strays in different dirs → disambiguated `<slug>`/`<slug>-2`, collision reported.
- [ ] A date-prefixed/awkward filename slugifies to a value that passes `validate_slug`; a filename that can't → skipped + reported (no raise).

**Migration (`migrate-docs`)**
- [ ] Dry-run (`--root <fixture>`): lists every stray grouped by slug+target home in **deterministic sorted order**, tree snapshot `before == after` (moved nothing), exit 0.
- [ ] `--yes` tracked path: `git status --porcelain` shows `R  docs/old → .context/.../spec.md` (rename **in index**, distinguishing `git mv` from delete+create); `proposal.json` round-trips through `proposals/store.py` reader, `validate_slug` passes, output byte-stable (`indent=2`+trailing `\n`); audit lands in `.context/audits/<slug>/` as a well-formed workspace; `gc status` then lists each migrated workspace; migrated proposal carries terminal `status` and **no unchecked template checklist** (so `gc/_checklist_partial` doesn't read it as in-flight).
- [ ] `--yes` untracked/gitignored path (the root-cause case): a `.gitignore`'d stray ends up physically at the target and `git status --porcelain` shows it staged (`A`) at the new path, source gone.
- [ ] `--yes` in a **non-git** repo: all strays moved via `Path.replace`, no git invoked, exit 0.
- [ ] Overwrite-refusal: existing `proposals/<slug>` → skipped + reported (exit 0); `--force` fills only *missing* files and leaves a non-empty existing `spec.md` byte-identical.
- [ ] Containment: `plan_moves`/`apply_moves` refuse a source/target escaping `docs/`→`.context/` via `..`/symlink, asserting **nothing moved** (mirrors gc realpath guard); symlinked strays skipped + reported.
- [ ] Source untouched: `src/*.py` + `docs/guide/*.md` byte-identical and unmoved after `--yes`.
- [ ] Idempotent: a second `--yes` reports "nothing to migrate," tree unchanged.
- [ ] `--json` pins exact top-level + per-group key sets (gc precedent).
- [ ] Title from doc H1; defined fallback when no H1.

**Write-guard (`guard-doc-write`)**
- [ ] `decision.py` unit: builds deny dict (interpolated home/slug) from a planning `DocClassification`, allow (empty) otherwise.
- [ ] e2e subprocess (`tests/cli/test_guard_doc_write_e2e.py`, stdin fed like `test_reconcile_gate_e2e`): `Write`→`docs/specs/x-design.md` ⇒ stdout has `permissionDecision":"deny"` naming the `.context/` home, exit 0; `Write`→`.context/proposals/foo/spec.md` or `docs/guide/x.md` ⇒ empty stdout, exit 0.
- [ ] Fail-open (all exit 0, empty stdout): malformed/empty stdin; `tool_name` not `Write` (incl. `Edit`/`MultiEdit`); missing `file_path`; `file_path` outside `repo_root`; `classify_doc_path` monkeypatched to raise.
- [ ] Never `exit 2` on any input. Guard path invokes **no** `subprocess.run` (monkeypatch to raise → still decides).
- [ ] Config gate: `doc_guard_enabled=false` ⇒ allow everything; **absent** config ⇒ guard **engaged** (default-on); **malformed** config ⇒ pinned fail-open behavior asserted.
- [ ] Allowlist: a `Write` to a path matching a `doc_guard_allow` glob (e.g. `docs/specs/**`) ⇒ allow (exit 0), proving a repo can exempt a legitimately-published `docs/specs/`.

**Hook wiring (`hooks.py`)**
- [ ] `install` wires the PreToolUse `Write` entry carrying `SENTINEL`; the body opens with `_SILENT_GATE` and `_guard_body` inserts the global defer-check guard (assert both present). `command -v dummyindex` self-gate present.
- [ ] `HookStatus` gains `claude_pre_tool_use`; `all_installed` includes it; **existing exact-assertion tests updated**: `test_status_false_when_absent`, `test_install_writes_stop_and_precompact_hooks` (`installed` set now 4-element), `test_status_true_after_install_all_three`.
- [ ] Idempotent re-install: guard entry count exactly 1, settings.json `before == after` bytes. `uninstall` removes the guard.
- [ ] Legacy-`PostToolUse` scrub still removes a legacy entry **and does not remove** the new `PreToolUse` guard; a co-located **and** a separate foreign user `PreToolUse` hook are both preserved byte-untouched across install/uninstall.

**Integration**
- [ ] `ContextSubcommand` enum gains `MIGRATE_DOCS`/`GUARD_DOC_WRITE` (not bare strings); both appear in `cli/help.py` and dispatch; `test_subcommand_help.py`'s enum-parametrized help test covers both (no mutation on `--help`).
- [ ] `.context/playbooks/migrate-stray-docs.md` exists/non-empty (incl. a "commit the move alone so `git log --follow` survives" note) and `HOW_TO_USE.md` carries a pointer line.
- [ ] Full suite green per `conventions/testing.md`.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `tree-enrich`
- `equip`
- `source-docs`
- `session-memory`
- `install-surface`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
