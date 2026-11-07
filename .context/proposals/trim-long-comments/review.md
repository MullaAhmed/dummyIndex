# Sampled review — trim-long-comments

Two fresh reviewers (did not edit the files) read `git diff 0634bfd` for 43 files: the 2 files per unit with the most removed lines plus every `WARN` file. Questions: summary kept / contract kept / safety kept / no new false claim.

**Result:** 42 PASS, 1 REOPEN (`dummyindex/context/domains/config.py` contract: schema meaning of `reconcile_exclude` / `external_docs` was cut). **Fixed:** one line added to the `Config` docstring; ast_equiv 0 problems, `tests/context/domains/test_config.py` 123 passed. All 25 WARNs judged incidental (substrings such as "traceback"/"gracefully", file names, idioms); the gc/delete "atomically" removal was a correction (rmtree is not atomic).

## Part 1 (22 files)

# trim-long-comments: sampled review, part 1 (22 files)

Base `0634bfd`. Reviewed `git diff 0634bfd -- <file>` plus surrounding code for every new or reworded claim.
WARN files: each lost keyword was checked against the removed lines.

| file | summary | contract | safety | no-false-claim | note |
|---|---|---|---|---|---|
| dummyindex/cli/build_loop/waves.py | yes | yes | yes | yes | `_entry_for`/`_dispatchable` rewording matches code (typed pin, `fallback` = no subagent_type); GATE/via rules kept in `_entry_for` |
| dummyindex/cli/equip/dispatch.py | yes | yes | yes | yes | verb/flag synopsis dropped (verbs now point at `EquipVerb`); exit codes, no-mutate probe and manifest-merge invariant kept |
| dummyindex/context/build/git_delta.py | yes | yes | yes | yes | WARN `race` = "grace**fully**"; never-raise kept; "None (or False)" matches `commit_exists` |
| dummyindex/context/build/incremental.py | yes | yes | yes | yes | WARN `warning` -> "caller must warn" kept; destructive re-cluster and bias-to-preserve notes kept |
| dummyindex/context/build/manifest.py | yes | yes | yes | yes | WARN `never` was a stale "agent never sees a stale index" claim; "full build + reconcile-stamp write it" matches the only 2 `write_manifest` callers |
| dummyindex/context/build/reconcile.py | yes | yes | yes | yes | WARN `data-loss` reworded to "silently forgotten" (kept); `race` = "graceful"; "no anchor/git -> pending markers only" and refusal rules match code |
| dummyindex/context/default_plugins.py | yes | yes | yes | yes | git-clone/no-SHA quirk moved to `_is_legacy_sha_pin`; no-shell + approval-gate notes kept; corrected `needs_user`, `classify_wired_entry` users and install skips all match code |
| dummyindex/context/domains/audit/log.py | yes | yes | yes | yes | WARN `security` was the example persona value; atomic appends kept |
| dummyindex/context/domains/buildloop/mapping.py | yes | yes | yes | yes | "implementer wins even at score 0" and tie rules match `map_task_to_equipment` |
| dummyindex/context/domains/config.py | yes | no | yes | yes | `config.py:1` module docstring: dropping the schema block lost the only in-file meaning of `reconcile_exclude` ("fnmatch globs hidden from reconcile/drift") and `external_docs` ("doc-root strings"); fix with one line in the `Config` docstring (`:134`) |
| dummyindex/context/domains/docguard/migrate.py | yes | yes | yes | yes | symlink skip, realpath containment, py3.10 non-strict `resolve` kept; "missing or empty" matches `_is_present` |
| dummyindex/context/domains/equip/generate/adopt.py | yes | yes | yes | yes | precedence and frontend stack gate kept |
| dummyindex/context/domains/equip/generate/gaps.py | yes | yes | yes | yes | WARN `security` was a capability name in a list |
| dummyindex/context/domains/equip/generate/proposal.py | yes | yes | yes | yes | WARN `security` was a capability name; dropped "CLI does the file IO" was false (it reads files); whole-word note still at `_WORD_RE` and `_any_token_hits` |
| dummyindex/context/domains/equip/generate/specialists.py | yes | yes | yes | yes | manifest-only/origin-hash and `INVARIANT_BROKEN` canary notes kept; name stability still in `specialist_spec` |
| dummyindex/context/domains/equip/lifecycle/manifest.py | yes | yes | yes | yes | WARN `race` = "trace**back**"; removed comment described a constant that no longer exists |
| dummyindex/context/domains/equip/plugins/discover.py | yes | yes | yes | yes | WARN `security` was in the 'auth'/'author' example; whole-word rule kept; query-hit rule matches code |
| dummyindex/context/domains/features/builder.py | yes | yes | yes | yes | WARN `atomic` was a wrong section header over `_trace_flow`, now "flow tracing"; "Leiden" dropped (clustering is Louvain) |
| dummyindex/context/domains/features/ops.py | yes | yes | yes | yes | WARN `race` = "traced", `security` = a legacy section name; CLI path, `_rewrite_scan` and `write_section` corrections match code |
| dummyindex/context/domains/features/placement.py | yes | yes | yes | yes | `_live_files` guard against `_rmtree` destroying enrichment kept; pending-marker claims match lines 90/148/213; "sibling of features/" matches `features_dir.parent` |
| dummyindex/context/domains/features/scan/models.py | yes | yes | yes | yes | WARN `never` = "never set"; "slug" matches `refs.py` |
| dummyindex/context/domains/features/scan/seed.py | yes | yes | yes | yes | WARN `never` = "Calls ... never go away"; its point ("stage 4 discards most flows") kept; service/entry/calls kinds match code |

Minor items, none a "no":
- `features/ops.py` `merge_feature` no longer says that a missing source raises. The module docstring still covers it ("missing sources"), and the code raises at line 206.
- `features/builder.py`'s module docstring says that each community becomes a feature. It doesn't mention the parser-artifact drop, which base didn't mention either and which is documented inline at line 103.
- No line added in these 22 files is over 100 characters.
- `config.py` (the only "no"): the rest of the rewording is correct. The no-secrets note is kept, and `default_config`, `read_doc_guard_settings` and `reconcile_default_plugins` match the code. `reconcile.py:476-486` still documents the glob semantics, but config.py, which owns the schema, no longer does.
- `scan/seed.py`: checked that `evidence`/`symbolRef` are set only when `rank` is present (`_service_node`, `_entry_node`).

REOPEN: dummyindex/context/domains/config.py


## Part 2 (21 files)

# trim-long-comments — sampled quality review, part 2 (21 files)

Base `0634bfd`. Each file: `git diff 0634bfd -- <file>` read in full; every new or reworded factual claim checked against the code.

| file | summary | contract | safety | no-false-claim | note |
|---|---|---|---|---|---|
| dummyindex/context/domains/fleetrun.py | yes | yes | yes | yes | WARN `traversal` was "deterministic/stable tie traversal" (sort order), not path traversal. New "existing run dir" (`target.exists()`) and "gated unit refuses a status-less checkpoint" (raises `FleetUnitError`) match the code. |
| dummyindex/context/domains/gc/delete.py | yes | yes | yes | yes | WARN `atomic`: the dropped "atomically" was false (`shutil.rmtree`); the lock is still documented on `delete_workspace`. The raises map (guard 3 → `GcPathError`; 2/4/6 → `GcTargetError`) and `done < total` / empty-checklist match the code. |
| dummyindex/context/domains/graph_query/__init__.py | yes | yes | yes | yes | WARN `never`: the dead-code "structural relations never count" rule still lives at `verbs.py:7`, and the undirected/`_src`/`_tgt` wire note at `load.py:4-6`. |
| dummyindex/context/domains/reality_check/confidence.py | yes | yes | yes | yes | Kept "best-effort, not crash-atomic" and "a raise before the first replace loses nothing". "Valid prior, unless already stashed", "iff matched" and "INDEX tmp already staged" all match the code. |
| dummyindex/context/domains/source_docs/__init__.py | yes | yes | yes | yes | WARN `security` was only the filename `SECURITY.md` in a list; root `*.md` discovery still covers it. `__all__` exists as stated. |
| dummyindex/context/domains/source_docs/writers.py | yes | yes | yes | yes | WARN `escape`: the old "escape up one level" was wrong. The new "climb two levels" matches `f"../../{entry.path}"`. |
| dummyindex/context/hooks.py | yes | yes | yes | yes | Untrusted-input and stdout-not-muted notes survive, as do the legacy SENTINEL and never-clobber notes. New: `PostToolUse` scrub runs at both scopes and only local removes git post-commit (matches `install`). The SessionStart list matches the 4 commands. |
| dummyindex/installer/link/create.py | yes | yes | yes | yes | Gate corrected to `family_is_pristine` (verified at `common.py:338`). The `allowed_symlinks` entry rule points to the package invariant (`link/__init__.py:7-12`). The py3.10 `Path.symlink_to` and Windows `winerror` notes are kept. |
| dummyindex/installer/repair.py | yes | yes | yes | yes | Symlink preflight, no-follow unlink, fail-closed resolve and per-copy isolation are all kept. `skill_only` rationale moved into the `plan_repairs` docstring. The new `_host_root_allowlist` summary matches the code. |
| dummyindex/pipeline/extract/__init__.py | yes | yes | yes | yes | Added `file_status` to the return dict (it is returned). Pass list (dispatch, Py/Java imports, raw calls) matches. Removed the duplicate ambiguity comment; the rationale remains at `:280-281`. TOCTOU residual kept. |
| dummyindex/pipeline/io/cache.py | yes | yes | yes | yes | Trusted-override vs confined-env trust boundary kept, as is "anti-corruption, not anti-poisoning". New `IsADirectoryError` raise and "whole file returned" both match the code. |
| tests/cli/test_cli_doc_sync_policy_canary.py | yes | yes | yes | yes | MIT `© 2026 DietrichGebert` lines unchanged; SCOPE and COUPLING HOLE kept. The new `_PolicyInvariant` docstring omits the `region` field (self-evident from the name). |
| tests/context/build/test_incremental.py | yes | yes | yes | yes | WARN `lock` was the substring in "BLOCK 2", not a lock note. Data-loss rationale for `indexed_commit` kept. |
| tests/context/domains/equip/test_equip_lifecycle.py | yes | yes | yes | yes | WARN `race` was the substring in "traceback". Lifecycle states and uninstall scope kept. |
| tests/context/domains/test_build_loop.py | yes | yes | yes | yes | Only redundant test-name restatements removed. "defaults to implementer, not fallback" matches `fallback is False`. |
| tests/context/domains/test_source_docs.py | yes | yes | yes | yes | WARN `escape` was "../ hops to escape back"; the off-by-one rationale is kept. Py<=3.10 / >=3.11 `Enum.__format__` quirk kept. "drops to LOW" matches the assert. |
| tests/test_install_link.py | yes | yes | yes | yes | WARN `escape` was "escape hatch" in plan prose. Kept: Windows Developer Mode, `core.symlinks=false`, the py3.10 patch quirk and the guarded/unguarded reasons. New "exits 1", "stamped" and "one dotfiles warning" all match asserts. |
| tests/test_install_link_primitives.py | yes | yes | yes | yes | SECURITY docstrings kept: HOME spoof, wrong scope_root, parent-chain before `mkdir`, squatted temp. py3.10-3.13 ENOTDIR and POSIX backslash / Windows `target_is_directory` quirks kept. |
| tests/test_install_repair.py | yes | yes | yes | yes | WARN `must not` was test-expectation phrasing, and those expectations are still asserted. The summary now says the file covers `install()` wiring, which its integration section does. "exit code 1" matches the assert. |
| tests/test_packaging_hygiene.py | yes | yes | yes | yes | WARN `never`: the "only tracked dirs fail; filesystem presence must not" rationale survives inline at `tests/test_packaging_hygiene.py:49`. |
| tests/test_skills_doc_hygiene.py | yes | yes | yes | yes | WARN `trust` was "rather than trusting the prose". New "frontmatter only name+description" matches `fields == {"name","description"}`. |

PASS
