# Release & test scaffolding — spec

confidence: INFERRED

## Intent

This is cross-cutting repo plumbing, not a product domain. It pools the
infrastructure that lets `dummyindex` *ship and test itself*: a conventional-commit
release driver, the shared pytest fixtures and filesystem anchors every test leans
on, a frozen TypeScript fixture that the extraction pipeline parses, a PowerShell
twin of the statusline hot-path, and a handful of docs-consistency guard tests.
The members share no business logic and no data model — they are grouped only
because each is repo/test machinery rather than a feature of the product. Document
honestly as infrastructure.

## User-visible behavior

**Release driver (`scripts/release.py`).** Run on a push to `main` by CI, it
replaces release-please. It reads commits since the last `vX.Y.Z` tag, derives a
semver bump from their conventional-commit types (`scripts/release.py:189-208`),
and — only when a release is warranted — rewrites the `version` line in
`pyproject.toml`, prepends a dated section to `CHANGELOG.md`, writes
`release-notes.md`, and emits `released`/`version` to `$GITHUB_OUTPUT`. The
irreversible git steps (commit, push, GitHub Release) deliberately live in the
workflow, not here, so the module stays pure and unit-testable
(`scripts/release.py:1-18`). Version policy mirrors the old release-please config,
pre-1.0: `feat` or any breaking change → minor (breaking stays in 0.x), `fix` →
patch, everything else alone → no release (`scripts/release.py:56-75`).

**Statusline (`dummyindex/skills/statusline/statusline.ps1`).** A per-prompt hot
path with no Python. It echoes the pre-computed freshness badge that the
SessionStart hook caches at `.context/cache/freshness-badge`, reading one tiny
gitignored file and never recomputing drift. Contract: print the badge if the
cache exists, otherwise print nothing, and exit 0 no matter what — every error is
swallowed so it can never crash a user's shell
(`dummyindex/skills/statusline/statusline.ps1:11-20`). It is the PowerShell twin
of `statusline.sh` and the cold-path fallback `dummyindex context statusline`
reads the same path.

## Contracts

Shared test scaffolding (the contract every other test module depends on):

- `tmp_repo` — thin alias for pytest's `tmp_path`, for filesystem isolation
  (`tests/conftest.py:9-11`).
- `_no_real_plugin_install` — autouse fixture that sets `SKIP_INSTALL_ENV=1` so no
  test ever shells out to the real `claude` CLI by accident; unit tests that inject
  a runner bypass it (`tests/conftest.py:14-21`).
- Filesystem anchors `TESTS_DIR` / `REPO_ROOT` / `FIXTURES_DIR` / `SAMPLE_REPO` —
  import these instead of chaining `Path(__file__).parent.parent`, so deep modules
  stay correct (`tests/paths.py:11-14`).
- `usage_corpus` — builds a synthetic `~/.claude/projects/` JSONL corpus under
  `tmp_path/projects` with fixed timestamps and token counts, exercising every hard
  path (cross-file duplicate turn, `<synthetic>` placeholder, non-assistant line,
  subagent turns, two sessions/projects/days, and a >5h idle gap forcing block
  splitting) so usage tests assert exact numbers
  (`tests/usage/conftest.py:50-145`).
- `tests/fixtures/sample_repo/web/app.ts` — a frozen TS entry (`WebApp`,
  `startWebApp`) the extraction pipeline parses; copied, never mutated in place
  (`tests/fixtures/sample_repo/web/app.ts:3-15`).

Guard tests (executable docs-consistency contracts, all `@pytest.mark.unit`):

- Every `context` subcommand answers `-h`/`--help` with exit 0, a non-empty usage
  block naming the subcommand, and zero writes to cwd
  (`tests/cli/test_subcommand_help.py:26-53`); top-level `install`/`ingest --help`
  exit 0 with no side effects (`tests/cli/test_subcommand_help.py:73-99`).
- The shipped `/dummyindex-update` SKILL.md must not reference the non-existent
  `.context/cache/_meta.json`, must reference the real `.context/meta.json`, and
  must drop the false non-destructive `build_all(bootstrap=True)` claim in favour
  of "curated"-preservation language (`tests/cli/test_update_skill_doc.py:17-41`).

## Examples

- `decide_bump(["feat: a", "chore: b"], ["", ""]) == "minor"`;
  `decide_bump(["fix(api)!: drop field"], [""]) == "minor"` (breaking stays minor
  pre-1.0); a body trailer `BREAKING CHANGE:` also forces minor
  (`tests/test_release_script.py:45-68`).
- `describe("feat(plan): annotate tasks") == "**plan:** annotate tasks"`;
  non-conventional subjects pass through verbatim
  (`tests/test_release_script.py:104-116`).
- `render_notes(...)` groups subjects into `### Added`/`### Fixed`/… in render
  order and drops hidden types; an all-hidden set renders `"Maintenance release."`
  (`tests/test_release_script.py:119-140`).
- `scripts/release.py` is loaded by file path in tests because `scripts/` isn't on
  `testpaths` (`tests/test_release_script.py:1-19`).
