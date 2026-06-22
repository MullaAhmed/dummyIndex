# Release & test scaffolding — plan

confidence: INFERRED

## Where it lives

Nine files across three trees with **no shared module** — this is a pool, not an
architecture. Grouped only because each is repo/test machinery rather than a product
feature:

- `scripts/release.py` — the CI release driver. Outside `testpaths`, so its test loads
  it by file path.
- `tests/conftest.py` — shared fixtures (`tmp_repo`, autouse `_no_real_plugin_install`).
- `tests/paths.py` — importable filesystem anchors.
- `tests/usage/conftest.py` — the synthetic usage corpus (`usage_corpus`).
- `tests/fixtures/sample_repo/web/app.ts` — frozen TS fixture for the extractor.
- `dummyindex/skills/statusline/statusline.ps1` — PowerShell statusline hot-path.
- `tests/test_release_script.py`, `tests/cli/test_subcommand_help.py`,
  `tests/cli/test_update_skill_doc.py` — guard tests.

## What each piece supports

The only honest organising axis is *what each member props up* — they do not talk to
each other.

| Member | Supports | Coupling |
| --- | --- | --- |
| `scripts/release.py` | the CI release workflow (this feature's one product-facing surface) | none in-process |
| `conftest.py` fixtures + `paths.py` | **every other test module** in the repo | imported widely |
| `usage_corpus` | the usage-reporting feature's tests only | scoped to `tests/usage/` |
| `sample_repo/web/app.ts` | the extraction/ingest pipeline's tests | copied, never imported here |
| `statusline.ps1` | the SessionStart freshness surface (Windows shells) | reads a hook-written cache file |
| three guard tests | the CLI dispatcher and the shipped SKILL.md docs | assertions only |

So there are really two cohesive sub-groups (the **release driver** and the **shared
test backbone** `conftest`+`paths`) and four orphans that each lean on a *different*
product feature. The Open questions track the orphans.

## The one boundary worth naming: pure core vs. CI side effects

The single design line in this pool lives inside `scripts/release.py`. Pure decision
logic — commit-type parsing, bump decision, version math, notes rendering
(`scripts/release.py:47-115`) — is kept apart from git/filesystem side effects
(`scripts/release.py:121-208`), and the irreversible steps (commit, push, GitHub
Release) live in the **workflow**, not the module. That keeps the module unit-testable
with plain data and puts every destructive step in one visible place. Everything else
here is plain pytest convention — `tmp_path` isolation, importable anchors,
dependency-injection at the boundary over mocking, deterministic hand-built corpora —
and the statusline is a stateless one-shot that prints a cached badge and swallows
every error.

## Data model

None, and none is implied. These members move strings and files —
conventional-commit subjects/bodies, semver triples, changelog text, JSONL lines,
on-disk paths. The synthetic usage corpus is the closest thing to an entity and it is
a throwaway `tmp_path` fixture rebuilt per test, not a persisted store.

## Key decisions

- **Pure core, side effects in CI.** The release module owns no irreversible git step;
  commit/push/Release live in the workflow (`scripts/release.py:7-10,118`).
- **Pre-1.0 bump policy is explicit.** Breaking changes bump minor, not major, while
  0.x — mirroring the retired release-please config
  (`scripts/release.py:12-15,56-75`).
- **Injection over mocking.** The autouse `_no_real_plugin_install` guard plus
  injectable runners keep tests off the real `claude`/`git`
  (`tests/conftest.py:14-21`, `.context/conventions/testing.md`).
- **Importable anchors over relative chaining.** `tests/paths.py` centralises
  `REPO_ROOT`/`SAMPLE_REPO` so deep modules don't recompute their own
  (`tests/paths.py:1-14`).
- **Deterministic corpora over recordings.** Fixed timestamps/token counts let usage
  tests assert exact aggregates (`tests/usage/conftest.py:1-8`).
- **Guard tests as executable docs-consistency contracts.** The help-guard pins
  exit-0 + no-mutation for every subcommand after a dispatcher bug let `--help` fall
  through and mutate the repo; the skill-doc guards pin SKILL.md against stale/false
  claims (`tests/cli/test_subcommand_help.py:1-12`,
  `tests/cli/test_update_skill_doc.py:1-12`).
- **Statusline never recomputes.** It reads a hook-cached badge and exits 0 on any
  error so a shell can't be broken
  (`dummyindex/skills/statusline/statusline.ps1:11-20`).

## Open questions

This feature pools unrelated infrastructure. The release driver and the
`conftest`+`paths` test backbone genuinely belong here (the backbone is repo-wide, not
owned by any one feature). The remaining members each lean on a single *product*
feature and arguably belong with it:

- **`usage_corpus`** (`tests/usage/conftest.py`) exists solely to test usage-reporting;
  could live with that feature's docs.
- **`test_update_skill_doc.py`** and **`statusline.ps1`** both concern the
  skills/SessionStart freshness surface and could attach to a statusline/freshness
  feature.
- **`test_subcommand_help.py`** is a contract on the CLI dispatcher and arguably
  belongs to the CLI feature.
- **`sample_repo/web/app.ts`** serves the extraction/ingest pipeline and could be
  documented alongside it.

Open: is the release driver's notes/changelog format covered by any acceptance test
beyond the unit tests, or only validated by eye in CI output?
