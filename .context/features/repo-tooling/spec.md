# Release & test scaffolding — spec

confidence: INFERRED

## Intent

This is cross-cutting repo plumbing, not a product domain. It pools the infrastructure that lets `dummyindex` *ship and test itself*:

- a conventional-commit release driver
- shared pytest fixtures and filesystem anchors every test leans on
- a frozen TypeScript fixture that the extraction pipeline parses
- a PowerShell twin of the statusline hot-path
- docs-consistency guard tests

The members share no business logic and no data model. They are grouped only because each is repo/test machinery rather than a feature of the product.

## User-visible behavior

**Release driver (`scripts/release.py`).** Run on push to `main` by CI, it replaces release-please. It reads commits since the last `vX.Y.Z` tag. It derives semver bump from their conventional-commit types (`scripts/release.py:189-208`).

It acts only when a release is warranted. It rewrites the `version` line in `pyproject.toml`, prepends a dated section to `CHANGELOG.md`, writes `release-notes.md`, and emits `released`/`version` to `$GITHUB_OUTPUT`.

The irreversible git steps (commit, push, GitHub Release) deliberately live in the workflow, not here. This is so the module stays pure and unit-testable (`scripts/release.py:1-18`).

Version policy mirrors the old release-please config, pre-1.0. `feat` or any breaking change → minor (breaking stays in 0.x). `fix` → patch. Everything else alone → no release (`scripts/release.py:56-75`).

**Statusline (`dummyindex/skills/statusline/statusline.ps1`).** Per-prompt hot path with no Python.

It echoes the pre-computed freshness badge that the SessionStart hook caches at `.context/cache/freshness-badge`. It reads one tiny gitignored file, never recomputing drift.

Contract: print the badge if the cache exists, otherwise print nothing. It exits 0 no matter what. Every error is swallowed, so it can never crash a user's shell (`dummyindex/skills/statusline/statusline.ps1:11-20`).

It is the PowerShell twin of `statusline.sh`. The cold-path fallback `dummyindex context statusline` reads the same path.

## Contracts

Shared test scaffolding (the contract every other test module depends on):

- `.gitattributes` keeps shipped shell scripts in LF form.
- Explicit filesystem capability fixtures skip only tests that require unavailable real symlinks or POSIX permission bits. Portable fallback checks remain active.
- `tmp_repo`: thin alias for pytest's `tmp_path`, for filesystem isolation (`tests/conftest.py:9-11`).
- `_no_real_plugin_install`: autouse fixture that sets `SKIP_INSTALL_ENV=1`, so no test ever shells out to the real `claude` CLI by accident. Unit tests that inject a runner bypass it (`tests/conftest.py:14-21`).
- Filesystem anchors `TESTS_DIR`, `REPO_ROOT`, `FIXTURES_DIR`, `SAMPLE_REPO`:
  import these instead of chaining `Path(__file__).parent.parent`, so deep modules stay correct (`tests/paths.py:11-14`).
- `usage_corpus`: builds a synthetic `~/.claude/projects/` JSONL corpus under `tmp_path/projects` with fixed timestamps and token counts. It exercises every hard path:
  - cross-file duplicate turn
  - `<synthetic>` placeholder
  - non-assistant line
  - subagent turns
  - two sessions/projects/days
  - a >5h idle gap forcing block splitting

  So usage tests assert exact numbers (`tests/usage/conftest.py:50-145`).
- `tests/fixtures/sample_repo/web/app.ts`: frozen TS entry (`WebApp`, `startWebApp`) the extraction pipeline parses; copied, never mutated in place (`tests/fixtures/sample_repo/web/app.ts:3-15`).

Guard tests (executable docs-consistency contracts, all `@pytest.mark.unit`):

- Every `context` subcommand answers `-h`/`--help` with exit 0 and a non-empty usage block naming it. Zero writes to cwd (`tests/cli/test_subcommand_help.py:26-53`).
- Top-level `install`/`ingest --help` exit 0 with no side effects (`tests/cli/test_subcommand_help.py:73-99`).
- The shipped `/dummyindex-update` SKILL.md must not reference the non-existent `.context/cache/_meta.json`. It must reference the real `.context/meta.json`.
- It must drop the false non-destructive `build_all(bootstrap=True)` claim in favour of "curated"-preservation language (`tests/cli/test_update_skill_doc.py:17-41`).

## Examples

- `decide_bump(["feat: a", "chore: b"], ["", ""]) == "minor"`.
- `decide_bump(["fix(api)!: drop field"], [""]) == "minor"`. Breaking stays minor pre-1.0.
- A body trailer `BREAKING CHANGE:` also forces minor (`tests/test_release_script.py:45-68`).
- `describe("feat(plan): annotate tasks") == "**plan:** annotate tasks"`. Non-conventional subjects pass through verbatim (`tests/test_release_script.py:104-116`).
- `render_notes(...)` groups subjects into `### Added`/`### Fixed`/… in render order and drops hidden types. An all-hidden set renders `"Maintenance release."` (`tests/test_release_script.py:119-140`).
- `scripts/release.py` is loaded by file path in tests because `scripts/` isn't on `testpaths` (`tests/test_release_script.py:1-19`).

## Third-party attribution (`NOTICE`)

`dummyindex` is MIT (`LICENSE`, © 2026 Ahmed Mulla). The repo-root `NOTICE` exists to carry attribution that a third-party license requires.

The file holds one entry, for `headroomlabs-ai/headroom` (Apache-2.0). The `dummyindex/context/domains/memory/miner/` module is derived from that project's `learn/` technique.

The entry is deliberately worded as "derived from, with short verbatim spans" rather than "independent reimplementation". An earlier package docstring claimed the latter and used it to argue Apache-2.0 §4's notice requirement did not attach. A token-overlap measurement found 43-token contiguous runs against `learn/loops.py`, so the premise was false. Carrying the notice costs nothing and arguing it away cost credibility.

Convention for future entries: state the upstream, its license, and the exact attribution text the license asks to be preserved. State which `dummyindex` module incorporates it, and how close the resemblance runs.
