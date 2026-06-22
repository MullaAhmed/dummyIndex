# Architect notes — repo-tooling (stage 2)

## What I changed

- Renamed/restructured "Where it lives" into an explicit member list that states up
  front this is a pool with **no shared module**, killing any pretense of architecture.
- Replaced the overstated "Architecture in three sentences" with two honest sections:
  a **"What each piece supports"** table (the only real organising axis — each member
  props up a *different* surface and they don't talk to each other) and **"The one
  boundary worth naming"** (pure core vs. CI side effects inside `release.py`, the
  single genuine design line in the whole pool).
- Trimmed the verbose "Data model: None" prose to a tight statement.
- Sharpened Open questions: explicitly split the members that *do* belong (release
  driver + repo-wide `conftest`/`paths` backbone) from the four orphans that lean on a
  product feature, so the honest divergence is foregrounded rather than buried.
- Cut filler throughout; kept every line:symbol citation intact.

## Patterns named

- **Pooled infra, not an architecture** — named explicitly so future readers don't
  hunt for a unifying design that isn't there.
- **Pure core vs. CI side effects** — the one cohesive boundary, localised to
  `release.py` (decision logic 47-115 vs. effects 121-208; destructive steps in the
  workflow).
- **Shared test backbone** (`conftest` + `paths`) vs. **feature-leaning orphans**
  (`usage_corpus`, `app.ts`, `statusline.ps1`, the two doc/CLI guard tests).
- Convention patterns retained: DI-at-boundary over mocking, importable anchors,
  deterministic hand-built corpora, guard-tests-as-contracts, stateless
  error-swallowing statusline.

## Dependencies surfaced

- `conftest.py` + `paths.py` are imported by **every other test module** — repo-wide,
  not owned by any feature.
- `usage_corpus` → usage-reporting tests only (scoped to `tests/usage/`).
- `sample_repo/web/app.ts` → extraction/ingest pipeline tests (copied, never imported
  by this feature).
- `statusline.ps1` → reads the SessionStart-hook-written cache at
  `.context/cache/freshness-badge`; twin of `statusline.sh`; cold path
  `dummyindex context statusline` reads the same file.
- `scripts/release.py` → loaded by file path in its test because `scripts/` is off
  `testpaths`; emits to `$GITHUB_OUTPUT` consumed by the workflow.

## Decisions promoted

- Promoted the **pure-core / side-effects-in-CI** split from a bullet to a named
  top-level section — it is the only architectural decision in the pool.
- Promoted the **belongs-here vs. orphan** distinction into the Open questions framing
  so the four cross-feature members are flagged as candidates for relocation, per the
  honesty mandate. Left spec.md untouched; invented no unifying architecture.
