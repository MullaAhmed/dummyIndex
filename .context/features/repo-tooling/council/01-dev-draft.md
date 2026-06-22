# Release & test scaffolding — plan

confidence: INFERRED

## Where it lives

Nine files across three trees, with no shared module. The release driver is
`scripts/release.py` (outside `testpaths`, loaded by path in its test). Shared test
scaffolding is `tests/conftest.py` (`tmp_repo`, autouse `_no_real_plugin_install`),
`tests/paths.py` (filesystem anchors), `tests/usage/conftest.py` (the synthetic
usage corpus), and the frozen TS fixture `tests/fixtures/sample_repo/web/app.ts`.
The statusline hot-path is `dummyindex/skills/statusline/statusline.ps1`. The guard
tests are `tests/test_release_script.py`, `tests/cli/test_subcommand_help.py`, and
`tests/cli/test_update_skill_doc.py`.

## Architecture in three sentences

The release driver keeps all pure decision logic — commit-type parsing, bump
decision, version math, notes rendering (`scripts/release.py:47-115`) — separate
from the git/filesystem side effects (`scripts/release.py:121-208`) so the former is
unit-tested with plain data and the latter runs only in CI. The test scaffolding is
pure pytest convention: `tmp_path`-based isolation, importable anchors instead of
relative-path chaining, dependency injection at the boundary (a `SKIP_INSTALL_ENV`
guard, an injectable runner) over mocking, and hand-built deterministic corpora so
assertions hit exact numbers. The statusline script is a stateless one-shot that
prints a cached badge and swallows every error.

## Data model

None. These members move strings and files: conventional-commit subjects/bodies,
semver triples, changelog text, JSONL lines, and on-disk paths. No persisted entity,
schema, or store is defined here — the synthetic usage corpus is the closest thing,
and it is a throwaway `tmp_path` fixture rebuilt per test, not a model.

## Key decisions

- **Pure core, side effects in CI.** The release module owns no irreversible git
  step; commit/push/Release live in the workflow so they are visible in one place
  and the module stays testable (`scripts/release.py:7-10,118`).
- **Pre-1.0 bump policy is explicit.** Breaking changes bump minor, not major, while
  0.x — mirroring the retired release-please config
  (`scripts/release.py:12-15,56-75`).
- **Injection over mocking.** The autouse `_no_real_plugin_install` guard plus
  injectable runners keep tests off the real `claude`/`git`, per the testing
  convention (`tests/conftest.py:14-21`, `.context/conventions/testing.md`).
- **Importable anchors over relative chaining.** `tests/paths.py` centralises
  `REPO_ROOT`/`SAMPLE_REPO` so deep modules don't compute their own
  (`tests/paths.py:1-14`).
- **Deterministic corpora over recordings.** Fixed timestamps/token counts let
  usage tests assert exact aggregates (`tests/usage/conftest.py:1-8`).
- **Guard tests as executable docs-consistency contracts.** The help-guard pins
  exit-0 + no-mutation for every subcommand after a dispatcher bug let `--help`
  fall through and even mutate the repo; the skill-doc guards pin SKILL.md against
  stale/false claims (`tests/cli/test_subcommand_help.py:1-12`,
  `tests/cli/test_update_skill_doc.py:1-12`).
- **Statusline never recomputes.** It reads a hook-cached badge and exits 0 on any
  error so a shell can't be broken (`dummyindex/skills/statusline/statusline.ps1:11-20`).

## Open questions

This feature pools unrelated infrastructure; several members arguably belong to a
product feature rather than here:

- The `usage_corpus` fixture (`tests/usage/conftest.py`) exists solely to test the
  usage-reporting feature; it could live with that feature's docs.
- `test_update_skill_doc.py` and `statusline.ps1` both concern the skills/SessionStart
  freshness surface and could attach to a statusline/freshness feature.
- `test_subcommand_help.py` is a contract on the CLI dispatcher and arguably belongs
  to the CLI feature.
- The `sample_repo` TS fixture serves the extraction/ingest pipeline and could be
  documented alongside it.

Open: is the release driver's notes/changelog format covered by any
acceptance test beyond the unit tests, or only validated by eye in CI output?
