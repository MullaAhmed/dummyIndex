## Data integrity

- `dummyindex/context/domains/docguard/migrate.py:188-228`: `MoveResult` is built only after the loop. A mid-batch raise leaves files moved and no record. Sources: `run_git` `FileNotFoundError` (`:275`), `Path.replace` `OSError` (`:272,279,282`), `AuditExistsError` (`:245`). `cli/migrate_docs.py:83` does not catch it. Fix: accumulate moves and emit a partial result from `try/finally`. Turn per-item `OSError` into a `MoveSkip`.

- `migrate.py:193` against `:197-224`: `_ensure_head` creates the managed home before any move. If every move is skipped, an orphan `proposal.json` at `done`, or a bare audit workspace, remains. It reads as a real record. Fix: create the head lazily, on the first move that runs.

- `migrate.py:180-181`: dry-run returns before the per-file loop. A `--force --json` preview predicts moves that `--yes` then refuses. No test pins preview and apply parity. `tests/cli/test_migrate_docs_cli.py` pins only the key set. Fix: compute target presence in `plan_moves` and record those skips in the plan.

- `classify.py:236-243` with `migrate.py:127-136,197-213`: `_disambiguate` seeds `used` only from this run's slugs. Run 1 migrates `foo-2` and skips `foo`. Run 2 sees the survivor alone, assigns bare `foo`, and `--force` fills the unrelated existing proposal's empty `spec.md`. Clobber protection covers only non-empty targets, so the mix-up is silent. Fix: seed `used` from existing `proposals/` and `audits/` slugs.

- `migrate.py:280,283`: both `run_git(..., "add", ...)` calls ignore `returncode`, yet the item is recorded as `replace+add`. A failed add, for example a held `index.lock`, reports a staged move that was never staged. Fix: check the return code and record `replace` with a `MoveSkip` note.

- `classify.py:135-136`: `group_strays` drops planning docs with no slug-able stem. No `MoveSkip` or other output reports them. This contradicts `cli/migrate_docs.py:27` and the playbook, which both say skipped strays are reported. Fix: return the dropped items and map them to skips.

- `classify.py:151-152`: a bucket keeps one SPEC and one PLAN via `next(...)`. Extra members are discarded silently. This is reachable: `migrate.py:84` matches the suffix case-insensitively, so `foo.md` and `foo.MD` share a key. Fix: detect the collision and emit a skip.

- `domains/config.py:736`: `write_config` uses a fixed `config.json.tmp`, so concurrent writers can interleave. The guard reads `config.json` on every write. `read_doc_guard_settings` maps a parse error to `(True, ())`. Fix: use a unique temp name.

- `domains/config.py:571-591` against `:318-320`: `Config.from_dict` raises on `"doc_guard_enabled": "false"`. The tolerant reader silently coerces it to `True`. Other commands error, and the guard still denies. Fix: share one coercion helper.

- `migrate.py:94-120`: `plan_moves` assumes `context_dir == repo_root/".context"`. `_home_for` hardcodes `.context/` from the repo root, but `_ensure_head` writes through `context_dir`. A divergent pair splits the head from the files. The containment check then reports "escapes root" by accident. Fix: assert the relationship at the top of `plan_moves`.

## Citation guard

- Resolved: `_post_edit_text` is now called (`guard_doc_write.py:169-175`, call at `:195`). Edit checks post-edit text. Example: file text `see .context/proposals/fo`, edit `old_string` `fo`, `new_string` `foo/` now denies.

- `citations.py:12`: the pattern has no anchor. Any segment named `proposals` or `audits` followed by a slug, even under `docs/`, denies as a workspace citation. The deny text also prefixes `.context/` to every match (`guard_doc_write.py:198-209`), so the path shown may be wrong.

- `citations.py:35-57`: the durable set is hardcoded. A new authored folder, such as `.context/playbooks/`, is neither guarded nor checked by `check --refs`. Both use one predicate, so they fail together.

- `guard_doc_write.py:37,189`: input over 1 MB is allowed unscanned. The limit counts characters, not words.

- `Edit` reads the whole target file for the post-edit check (`guard_doc_write.py:192`). No size cap applies to that read, only to new text.

- `retirement.py:159` and `closeout.py:426,462`: `cites_disposable` is a substring test on evidence paths. Any repo path with a `proposals/<x>/` or `audits/<x>/` segment is rejected as closeout evidence. A source file under a directory named `proposals` cannot serve as evidence.

## Security

Threat model: a hygiene control over a semi-trusted agent, not a containment boundary. Anything that removes `dummyindex` from PATH, or the `2>/dev/null || true` and `exit 0` wrapper in `hooks.py:273-275`, already disables it.

- **[1] `cli/guard_doc_write.py:212-223` with `cli/common.py:31-34` against `domains/docguard/classify.py:174-185`**: `resolve_context_root` follows symlinks, but `_rel_posix` is lexical. Through a symlinked root, `relative_to` raises `DocPathError`, and `run` returns 0. The guard is off for every write, silently. Nothing in `tests/cli/test_guard_doc_write_e2e.py` builds a symlinked root. Fix: compare `os.path.realpath` of both sides once, in `_decide`.

- **[2] `domains/docguard/classify.py:88-102`**: the location gate reads un-normalized parts. `src/../docs/plans/x.md` is allowed, though it lands in `docs/plans/`. `docs/plans/../guide/x.md` is denied, though it lands in an excluded subtree. This assumes Claude Code normalizes `file_path`, which nothing pins. Fix: `os.path.normpath` in `_rel_posix`.

- **[3] Spec wording fixed**: the spec says the guard denies one call and never exits 2. Stderr echo of the deny is still not done.

- **[6] `cli/guard_doc_write.py:97`, `fnmatch` imported at `:28`**: `fnmatch` normcases both sides. `doc_guard_allow` globs are case-sensitive on POSIX and case-insensitive on Windows. One config exempts different paths per host. Fix: use `fnmatchcase`.

- **[4] `domains/docguard/classify.py:81,85` against `:89,94,98`**: suffix and root stem are case-folded, but directory segments are compared exactly. `Docs/specs/x.md` escapes the gate on case-insensitive filesystems (macOS, Windows). Fix: case-fold segment comparisons.

- **[5] `cli/guard_doc_write.py:70-97` with `domains/config.py:571-591`**: the hook is installed globally. Its enable bit and allowlist come from the open repo's `.context/config.json`. A cloned repo with `doc_guard_enabled: false`, or `doc_guard_allow: ["*"]`, silently turns protection off. Config reads are bounded: two keys, type-checked, never raising. The citation check is also disabled by `doc_guard_enabled` (`guard_doc_write.py:70-74`). Fix: surface "guard disabled by repo config" once per session.

- **Verified sound**: migration validates containment with `resolve()` on both sides before pass 2 (`migrate.py:115-120`). A planted symlink at `proposal.json` or `spec.md` cannot be written through (`atomic_io` and `Path.replace` both rename). `run_git` takes an argument list with no shell (`git.py:65-74`). The guard reads `file_path` and never prints document bodies.

## Product surface

- **Global hook, repo without dummyindex**: `_SILENT_GATE` (`hooks.py:104`) checks only the binary. `read_doc_guard_settings` on a missing config returns `(True, ())`. No per-repo off switch exists, so uninstalling the hook is the only exit.

- **Remediation fails in the same repo**: `migrate-docs` exits 2 with "`.context` not found" (`cli/migrate_docs.py:203-209`). The guard is live while its cleanup cannot run.

- **Every matched call pays the hook**: about 1.0 s per call. This includes `Edit`, `MultiEdit`, and language-tool calls that find nothing to do (`guard_doc_write.py:56-61`). The gate short-circuits only on a missing binary. No filename pre-filter exists in shell.

- **Same stem in two directories**: `docs/plans/api.md` and `docs/internal/plans/api.md` both map to `.context/proposals/<slug>/plan.md`. `classify_doc_path` has no `used` set. An agent that follows both denies overwrites the first file. The migration path is protected. The live guard is not.

- **Agent obeys a deny**: the file lands in a home with no `proposal.json`. `gc status` lists it as `untracked` with no status, so it has less GC protection than `ensure_proposal` output. The deny reason names a directory but no command that creates a valid head. `write_proposal_json` is reachable only from migration.

- **Published `docs/` content matches the shape**: dated posts, ADRs and `*-design.md` files are denied. `EXCLUDED_DOCS_SUBTREES` is `{guide, reference, sources}` only (`constants.py:57`). The deny text never mentions `doc_guard_allow`.

- **Allowlist blast radius**: matching is `fnmatch` (`guard_doc_write.py:97`), where `*` crosses `/`. `docs/*` exempts the whole tree. No dry run or glob validation exists.

- **Setting the knobs**: no CLI verb writes `doc_guard_enabled` or `doc_guard_allow`. Users hand-edit `config.json`, which the tool otherwise rewrites through `migrate_config_in_place`.

- **Deny is invisible**: the hook prints one payload and nothing else. False-positive regimes cannot be seen from a session or measured later.

- **`migrate-docs` dry run over symlinked or unslug-able strays**: output is "nothing to migrate", and `--json` shows empty `groups` and `skipped`. The playbook says such strays are "skipped + reported". They are not. A reviewer concludes `docs/` is clean when it is not.

- **`--json` counts a move that did not happen.** With a non-empty `plan.md` already present, `--yes --force` lists the move in `groups[].moves` with empty `method`, and also in `skipped`. The `--force` dry run predicts one move and zero skips.

- **After migration**: `_print_migrate` (`cli/migrate_docs.py:142-181`) reports moves and skips only. Inbound links to relocated `docs/` paths, in `.context/architecture/overview.md` and any doc-site nav, are not rewritten or flagged.

- **Leak through other tools**: `cat > docs/plans/x.md` through `Bash`, or `touch` followed by `Edit`, bypasses the stray check (`hooks.py:260`). The `Write`-only scope is deliberate. The stray guard stops one route only, so frame it as advisory.

## Language hint

- **Warn only**: Chinese prompts depend on agent compliance.

- **`SendMessage` is not in the official hook docs**: if it never fires, the hint is silent for it. Harmless.
