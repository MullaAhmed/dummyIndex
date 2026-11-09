# Playbook — relocate stray planning docs (managed-doc-home migration)

Use this when internal planning artifacts (plans, specs, `*-design.md`, audit reports) leak into `docs/` instead of their managed `.context/` homes. Their managed homes are `.context/proposals/<slug>/` (a `spec.md` + `plan.md` pair under a `proposal.json`) and `.context/audits/<slug>/` (an audit workspace). `docs/` is the published tree and must stay free of internal planning docs. The `migrate-docs` verb relocates each stray into its correct home **while preserving git history**.

The order is: **`migrate-docs` (dry-run) → review the plan → `migrate-docs --yes` → commit the move alone → verify history followed.**

## 1. Survey the strays — dry-run first
- Run `dummyindex context migrate-docs` (no `--yes`). It enumerates every stray planning doc under `docs/`. It groups them by slug and target home in deterministic sorted order, lists any skips, and **moves nothing** (exit 0).
- A `<stem>-design.md` pairs with `<stem>.md` in the same directory under one slug (spec + plan). Lone files pin their own slug. Two strays resolving to the same slug are disambiguated (`<slug>-2`), and the collision is reported.
- A stray whose filename cannot slugify to a valid value, or a symlinked stray, is **skipped and reported**. It is never moved and never raised. Review the skip list. Nothing under `docs/guide|reference|sources/`, a root README/CHANGELOG, or already-`.context/` content is touched.

## 2. Perform the moves — `--yes`
- Run `dummyindex context migrate-docs --yes`. For each stray it creates the slug dir. It writes **only** a terminal-status `proposal.json`, with no template `spec.md`, `plan.md`, or `checklist.md`, so the relocation cannot collide. Then it relocates the stray onto `spec.md`/`plan.md`. Audits land in `.context/audits/<slug>/` as a well-formed workspace.
- **Tracked files move via `git mv`** so history is preserved. An untracked or gitignored stray is `Path.replace`d, then `git add`ed. In a non-git repo, every file moves via `Path.replace` with no git call.
- `--force` fills only *missing* files in an existing managed home. It never overwrites a non-empty `spec.md`, `plan.md`, or `proposal.json`. Without `--force`, an existing slug dir is skipped and reported.

## 3. Commit the move alone
- **Commit the relocation as its own commit.** Nothing else staged with it. `git mv` records a rename only when the move stands alone. If you mix it with content edits in the same commit, git records a delete-plus-add, and the rename is lost. **Commit the move alone so `git log --follow` survives.** Full history then stays reachable at its new `.context/` path.
- After committing, confirm with `git log --follow .context/proposals/<slug>/spec.md` (or `plan.md`). The log should reach back through the old `docs/` path.

## 4. Re-index
- The relocated docs are generated per-task workspaces under `proposals/`/`audits/`. They do not need a feature reconcile. A later `gc status` lists each migrated workspace. The terminal `status` in `proposal.json` keeps GC from reading it as in-flight.
- A second `migrate-docs --yes` reports "nothing to migrate" and leaves the tree unchanged. Idempotent.

## Common pitfalls
- **Squashing the move into a feature-work commit.** `git log --follow` then cannot trace the file across the rename. Commit the move alone.
- Passing `--yes` before reviewing the dry-run plan. Or assuming the dry-run moved anything. It never does.
- Expecting `migrate-docs` to touch source code or files outside `docs/`. It never does. It only relocates strays under `docs/` into `.context/`.
- Re-running with `--force` and expecting it to overwrite an existing non-empty `spec.md`. It only fills *missing* files and never clobbers.
- Forgetting that a fresh `Write` to a stray location is separately blocked by the `guard-doc-write` PreToolUse guard. `migrate-docs` cleans up the past. The guard prevents recurrence.
