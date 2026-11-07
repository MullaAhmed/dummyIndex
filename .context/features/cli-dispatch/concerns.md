## Data integrity

- **[HIGH]** `cli/refresh.py:37` → `cli/migrate.py:83-85` → `context/output/claude_md.py:202-231` — `refresh-indexes` folds CLAUDE.md without the `has_foldable_legacy_claude_md` guard (`cli/migrate.py:14-25`) that rebuild/bootstrap/installer use: creates `.claude/CLAUDE.md` on Codex-only trees, deletes a root CLAUDE.md Codex reads — gate the call; add a refresh copy of the Codex-fallback test.
- **[HIGH]** `cli/init.py:70-78` + `context/default_plugins.py:452-471,601-607,262-277` — headless init enables any custom `config.wired` plugin with no prompt and no marketplace source; nothing installs, yet key presence reads `SATISFIED`, so `wire` never revisits it (same after a failed install, `cli/wire.py:206-211`) — undeclared custom target → needs-user; classify on effective, resolvable state.
- Medium — `context/build/meta.py:104-112`, `context/domains/config.py:643-662`, `context/claude_settings.py:150-154` — fixed `<name>.tmp`, no lock or Windows retry (bypasses `context/domains/atomic_io.py:37-67`): writers collide, `reconcile-stamp` tracebacks under a Windows reader, stamp races `rebuild --changed` — `write_text_atomic` + `project_lock` around meta read-modify-write.
- Medium — `context/domains/config.py:466-475` via `cli/init.py:158-165`, `cli/reconcile.py:53-65` — `resolve_depth` parses the full config, so a bad plugin field exits 2 before the build even with `--no-default-plugins`/`--platform codex`, and blocks read-only `reconcile` — depth-only reader; keep strict parse in the plugin step.
- Low — `cli/check.py:220-228` + `context/build/meta.py:72-89` — newer-schema meta reads `unknown` so `check --versions` says "coherent"; `int(None)` raises `TypeError` past `stamp_reconciled`'s catch; `cli/reconcile.py:199-221` string-matches the error — typed `MetaSchemaError`.
- Low — `cli/wire.py:68-87` — ledger read once before blocking prompts; a stale approved entry is still enabled — re-read and match the entry before mutating.

## Security

- **[HIGH]** `cli/features.py:119-160` → `context/domains/features/ops.py:193,245` — `features-merge --from ../..` (or absolute) resolves to the repo root and `_rmtree`s it, `.git` included; `features-rename --from` (`ops.py:79-96`) and `flow-remove` (`ops.py:311-335`) share it; ids come from `INDEX.json` (`skills/council/18-filter-trivial.md:74-79`) — containment-check every source id.
- **[HIGH]** `cli/features.py:214-244` + `context/domains/features/ops.py:392-423` — `section-write --feature ../../.claude --section CLAUDE` rewrites `.claude/CLAUDE.md` (existing file = permission); Windows `--section` takes `x\..\..\CLAUDE`/`C:\…`; Bash bypasses the `Write`-only doc guard (`dummyindex/context/hooks.py:203`) — contain `--feature`; reject `\`, `..`, absolute `--section`.
- **[HIGH]** `context/claude_settings.py:150-154` — predictable `settings.json.tmp`: a POSIX clone shipping it as a symlink to `~/.claude/settings.json` gets repo hooks installed globally on plain `ingest` (`cli/init.py:221-231` → `dummyindex/context/hooks.py:442-459`); a linked `.claude/` redirects plugin writes — unique exclusive temp + reject linked parents (as `cli/equip/dispatch.py:587-590,682`).
- **[HIGH]** `context/default_plugins.py:501-517,536-538`, `context/git.py:38-46`, `context/build/git_delta.py:255` — bare `claude`/`git`; Windows searches the parent cwd first, so a committed `claude.exe` runs on `ingest` (verified with a planted exe) — resolve an absolute path from filtered `PATH`, excluding cwd/repo.
- Medium — `context/default_plugins.py:96-165,305-358` — code-running defaults (`caveman`, `i-have-adhd`) are on by default and unpinned, legacy SHA pins are healed away, yet the disclosure (`:168-186`) says "reviewed" — pin to a verified ref, or make `runs_code` defaults opt-in.
- Medium — `context/default_plugins.py:78-80` → `cli/wire.py:103-136`, `cli/init.py:79-84` — `wired` targets accept any string; ESC/CSI in a target can erase or forge output, e.g. hide DI-2's silent enable; no control-char filter exists — reject non-printables in `WiredEntry.from_dict`.

## Product surface

- **[HIGH]** `cli/reconcile.py:108-143,250-261` + `context/build/reconcile.py:277-280` — orphaned anchor plus blockers: `--heal-orphaned` prints "re-baselining" to stdout, the HEAD stamp is refused, and the refusal shows only orphan advice ("`--to` or `--force`"), no blockers; `--to` loops back; `reconcile` text hides blockers (`cli/reconcile.py:318-327`) — list blockers whenever blocked; print heal only on success, with a machine-readable marker.
- Medium — `cli/init.py:79-84,242`, `cli/wire.py:130-143`, `cli/rebuild.py:91-94` + `context/build/upgrade.py:611` — exit 0 after reported partial failure (plugin warnings, `could not wire`, `rebuild --changed` "stamp not advanced" on stdout), passed on by `cli/check.py:120-124` — distinct documented code or persisted pending marker.
- Medium — `cli/wire.py:126-132,206-211` — `wired:` for `deferred`/empty `skipped`; failure reasons dropped; marketplace conflict (`context/default_plugins.py:459-461`) re-prompts and fails each run; non-TTY lists skills as `would prompt` (`:103-104`) — return reasons; render installed/deferred/needs-user apart.
- Medium — `cli/init.py:26-27,233-234` — a successful `--no-default-plugins` or Codex-only run prints nothing about plugins, same as a phase that never ran — one `plugins -> skipped for this run` line.
- Medium-low — `context/default_plugins.py:251-252,449-451` — an `enabledPlugins=false` tombstone renders `already enabled (left as-is)` — separate `already disabled` bucket.
- Low — `cli/help.py:242-243` vs `cli/scan.py:62-88` (warnings exit 0, `severity` undocumented); stray `gc signal` lines under `maintain` (`cli/help.py:538-542`); undocumented `reconcile --depth`, `query --max-bytes`; unknown verb dumps 694-line `USAGE` (`cli/__init__.py:146-149`) — fix slices; nearest-match hint via `usage_error`.

## Cross-review notes

- Paths are under `dummyindex/` unless prefixed; lines @`7a70cf4` (post comment-trim). DI/SEC/PS-n = nth bullet above.
- Merged: plugin cluster (DB 2–3, Sec 6, Prod 2–3) → DI-2; symlink write (Sec 2 + prior DB/Prod) → SEC-3; config gate (DB 5, Prod 6) → DI-4; exit-0 (DB 6, Prod 4) → PS-2.
- Severity split: DB/Product rate DI-2 High, Security Medium (a repo could commit `settings.json` directly). Kept HIGH for integrity (no repair path). Prod 2's deferred half is Medium: Claude Code installs on next session.
- Conflict: slug-validating source ids (SEC-1/2) would make legacy non-slug folders un-renameable (`_validate_feature_id` also lowercases) — containment for sources, slug only for destinations.
- Conflict: DB's "require `installed`, roll back on failure" must not treat `deferred` (no CLI, `DUMMYINDEX_SKIP_PLUGIN_INSTALL`) as failure — roll back on `errors` only.
- Conflict: Prod's "stop labelling reviewed defaults untrusted" (`cli/wire.py:170,185`) vs SEC-5 (unpinned latest isn't reviewed); SEC-5's opt-in also breaks this repo's CLAUDE.md reliance on caveman/i-have-adhd — pin first, then relax the label.
- Conflict: non-zero partial exits (PS-2) vs plan "post-build failures are warnings": `check --auto-refresh` (SessionStart) forwards `rebuild`'s code — hooks must map the new code to a warning.
- Overlap: DI-3's `write_text_atomic` closes only the `.tmp` link; a linked `.claude/` still needs SEC-3's parent check. SEC-4: `shutil.which` also searches cwd on Windows — pass a filtered `path=`.
- Retracted from the prior review: "thin sink, little genuine risk"; "`hooks install` settings mutation genuinely safe" (SEC-3); "pins non-official refs to full SHAs" (SEC-5). Unconfined `--root` stays an accepted local-CLI choice; it doesn't cover feature-id escapes.
- Doc vs code (code wins): `plan.md:7-9` "persists nothing" (migrate/debt/plan_update write); `cli/wire.py:3`, `cli/help.py:662-665`, `docs/guide/07-cli.md:754` (low confidence) say headless init never enables unprompted. Unlisted Low: statusline badge stale after a stamp (`cli/plan_update.py:32-41`, `cli/statusline.py:37-47`).

## Rule-copy canary

- `tests/cli/test_cli_doc_sync_policy_canary.py:50-67,223` — invariant rows are hand-written and `_POLICY_CONSTANT_HASH` forces a re-read, not a coverage check; a new policy clause needs no new row — add a clause-coverage check when the policy grows.
- `test-anchor:policy-*` markers ship in `skills/skill.md` (stripped by `dummyindex/installer/common.py:36`); keep them outside `dummyindex:*`.
