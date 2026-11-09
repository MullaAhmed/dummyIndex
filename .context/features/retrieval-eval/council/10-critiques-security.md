## Security

- `tests/eval/test_retrieval_eval.py:60-67`, `tests/conftest.py:10-20`, `tests/conftest.py:28-35`. The module-scoped `indexed_repo` is set up before the function-scoped autouse `_isolate_user_config` and `_no_real_plugin_install`. `pytest --setup-plan` prints `SETUP M indexed_repo` ahead of `SETUP F _isolate_user_config`. So `build_all` runs with the developer's real `HOME`/`USERPROFILE`/`CODEX_HOME`/`CLAUDE_CONFIG_DIR` and without `SKIP_INSTALL_ENV`, while every other test in the suite is sandboxed. Today the only real-profile read is git's global config, through the subprocess in the next bullet. If a later change to `build_all` reads or writes user config, this gate will touch the real profile without any test failing. Existing mitigation is incidental:
  - `:66` passes only `cache_root`, so the gate depends on the `bootstrap=False` default (`dummyindex/context/build/runner.py:97`), which skips `reconcile_claude_md` (`runner.py:325-332`). A default protects less than an explicit argument would.
  - `install_default_plugins` has no caller under `context/build/`; its only callers are `dummyindex/cli/init.py:74`, `dummyindex/cli/wire.py:243` and `dummyindex/installer/install/project_init.py:372`.
  - A grep of `dummyindex/context/build/` and `domains/features/` finds no `Path.home()` call and no import of `hooks`, `claude_plugins`, `default_plugins`, `usage` or `installer`.

  None of this isolates the fixture, because the conftest sandbox does not cover module scope.
- `tests/eval/test_retrieval_eval.py:66` → `dummyindex/context/build/runner.py:172` → `dummyindex/context/build/git_delta.py:56-66`, `:289-312`. Every gate run spawns `git -C <copy> rev-parse HEAD`. The copy has no `.git`, so git searches upward from the pytest basetemp. Under a `--basetemp` inside a checkout, or a home directory that is itself a git repo, git reads that enclosing repo's `.git` and config and stamps an unrelated HEAD into the throwaway `meta.json` `indexed_commit`. Nothing is written to the enclosing repo, and `query` never reads `indexed_commit`, so gated metrics are unaffected. Existing mitigation:
  - an argv list with no shell and `capture_output`;
  - a non-zero exit, `FileNotFoundError` or `OSError` maps to `None`;
  - the default basetemp lies outside any repo: verified on this host (`%LOCALAPPDATA%\Temp` and `%USERPROFILE%` both exit 128), and CI `.github/workflows/tests.yml:33` passes no `--basetemp`.

  No mitigation stops the upward search itself, because `GIT_CEILING_DIRECTORIES` is never set. The record and the code disagree here. The prior `concerns.md:13` blamed only the deleted benchmark for voiding the "no-subprocess" verdict, but the code shows the gate itself is not subprocess-free. `plan.md:22-25` is accurate about the imports; it just does not mention this subprocess.
- `tests/eval/test_retrieval_eval.py:65`, `tests/paths.py:14`. `shutil.copytree(SAMPLE_REPO, dest)` keeps the default `symlinks=False`, so it copies the working tree, untracked files included, and follows links. A symlink added to the fixture would pull content from outside the repo into the indexed copy, where its names can reach citations and the printed failure messages. The fixture is shared with 29 modules, and a stray `tests/fixtures/sample_repo/.context/` is not gitignored (`git check-ignore` gives no match). Per feature, scaffolding rewrites `feature.json`, `spec.md` and `flows/` (`dummyindex/context/domains/features/builder.py:257-274`) plus `docs.md` (`dummyindex/context/domains/features/docs.py:88`), and it never clears the folder first: `_rmtree` is called only from `placement.py:275` and `ops.py:245`. A leftover `features/community-N/plan.md` or `concerns.md` would therefore survive and could feed `_excerpt_from_feature` (`dummyindex/context/domains/query.py:723-754`). That shifts excerpts and the ungated `total_estimated_tokens`; no impact on hit@3 or MRR is shown. Existing mitigation: none in code. The tree is clean today: 3 tracked files, no links (`find -type l` is empty, no mode-120000 entries) and no `.context/`. A stray `.context/` would show as untracked in `git status`.

### Resolved since last review

- `benchmarks/retrieval/run_eval.py:27-88`: networked Git/Python subprocesses with pinned checkouts. Resolved by deletion in `404654a`; the orphaned tests were dropped in `ddcb605`. Only untracked `benchmarks/__pycache__` residue remains, and `benchmarks/retrieval/` is gone. The frozen-gate half of that bullet still holds and was re-verified:
  - the gate writes only into a fresh pytest copy (`tests/eval/test_retrieval_eval.py:63-66`), with `cache_root=base / "cache"`;
  - the trusted cache override is restored in `finally` (`dummyindex/context/build/common.py:185-190`);
  - `query.py` has no write calls;
  - nothing on the build path uses the network.

  The "no-subprocess" verdict does not return; see the git bullet above.
- `benchmarks/retrieval/run_eval.py:51-88`: a reused `.git` destination was force-rebuilt. Resolved by deletion.
