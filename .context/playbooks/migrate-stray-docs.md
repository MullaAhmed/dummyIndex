# Playbook — relocate stray planning docs (managed-doc-home migration)

Use this when internal planning artifacts — plans, specs, `*-design.md`, audit reports — have leaked into the user-facing `docs/` tree instead of their managed `.context/` homes. The managed homes are `.context/proposals/<slug>/` (a `spec.md` + `plan.md` pair under a `proposal.json`) and `.context/audits/<slug>/` (an audit workspace). `docs/` is the published tree and must stay free of internal planning docs; the `migrate-docs` verb relocates each stray into its correct home **while preserving git history**.

The order is: **`migrate-docs` (dry-run) → review the plan → `migrate-docs --yes` → commit the move alone → verify history followed.**

## 1. Survey the strays — dry-run first
- Run `dummyindex context migrate-docs` (no `--yes`). It enumerates every stray planning doc under `docs/`, groups them by slug + target home in deterministic sorted order, lists any skips, and **moves nothing** (exit 0).
- A `<stem>-design.md` pairs with `<stem>.md` in the same directory under one slug (spec + plan). Lone files pin their own slug. Two strays resolving to the same slug are disambiguated (`<slug>-2`) and the collision reported.
- A stray whose filename can't slugify to a valid value, or a symlinked stray, is **skipped + reported** — never moved, never raised. Review the skip list; nothing under `docs/guide|reference|sources/`, a root README/CHANGELOG, or already-`.context/` content is touched.

## 2. Perform the moves — `--yes`
- Run `dummyindex context migrate-docs --yes`. For each stray it creates the slug dir, writes **only** a terminal-status `proposal.json` (no template `spec.md`/`plan.md`/`checklist.md`, so the relocation can't collide), then relocates the stray onto `spec.md`/`plan.md`. Audits land in `.context/audits/<slug>/` as a well-formed workspace.
- **Tracked files move via `git mv`** so history is preserved; an untracked/gitignored stray is `Path.replace`d then `git add`ed; in a non-git repo every file moves via `Path.replace` with no git call.
- `--force` fills only *missing* files in an existing managed home — it never overwrites a non-empty `spec.md`/`plan.md`/`proposal.json`. Without `--force`, an existing slug dir is skipped + reported.

## 3. Commit the move alone
- **Commit the relocation as its own commit** — nothing else staged with it. `git mv` records a rename only when the move stands by itself; if you mix it with content edits in the same commit, git records a delete-plus-add and the rename is lost. **Commit the move alone so `git log --follow` survives** and the file's full history stays reachable at its new `.context/` path.
- After committing, confirm with `git log --follow .context/proposals/<slug>/spec.md` (or `plan.md`) — the log should reach back through the old `docs/` path.

## 4. Re-index
- The relocated docs are generated per-task workspaces under `proposals/`/`audits/` — they don't need a feature reconcile. A later `gc status` will list each migrated workspace; the terminal `status` in `proposal.json` keeps the GC from reading it as in-flight.
- A second `migrate-docs --yes` reports "nothing to migrate" and leaves the tree unchanged (idempotent).

## Common pitfalls
- **Squashing the move into a feature-work commit** — `git log --follow` then can't trace the file across the rename. Commit the move alone.
- Passing `--yes` before reviewing the dry-run plan, or assuming the dry-run moved anything (it never does).
- Expecting `migrate-docs` to touch source code or files outside `docs/` — it never does; it only relocates strays under `docs/` into `.context/`.
- Re-running with `--force` and expecting it to overwrite an existing non-empty `spec.md` — it only fills *missing* files, never clobbers.
- Forgetting that a fresh `Write` to a stray location is separately blocked by the `guard-doc-write` PreToolUse guard — `migrate-docs` cleans up the past, the guard prevents recurrence.
