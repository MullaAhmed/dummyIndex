# Spec — Give the two fingerprint stores one role each so drift detection stops decaying

## Intent

**Problem.** On a curated/enriched `.context/`, `dummyindex context rebuild --changed` never
re-stamps `.context/cache/manifest.json`. The manifest freezes at the last *full* build and
decays forever, because the only path that stamps it is the one the CLI refuses on a curated
index.

Verified in source at HEAD `2bb91c1` (v0.35.0):

1. `dummyindex/context/build/incremental.py:144-164` — `rebuild_changed()` takes the
   `if not full and status.enriched:` branch, calls `refresh_deterministic_artifacts(...)`,
   and returns early. No `write_manifest` on that path.
2. `dummyindex/context/build/enriched_refresh.py` — no `write_manifest` reference anywhere.
3. `dummyindex/context/build/runner.py:267-279` — the only writer of `cache/manifest.json`,
   reached solely through `build_all`.
4. `dummyindex/cli/rebuild.py:78-89` — a bare `rebuild` on a curated index errors with
   `"error: curated index detected — refusing a full re-cluster."` and `return 2`.

Net: **on a curated index no supported command refreshes `cache/manifest.json`.**

**Field evidence** (BOS-Frontend, 0.35.0, curated): manifest `generated_at` frozen at
2026-06-13 against `meta.json` `updated_at` 2026-08-19 — 68 days — with
`dummyindex context plan-update` reporting **148 drifted source files across 13 features**.
The premise also reproduces in dummyindex's own repo (manifest `2026-06-17`, meta `2026-08-06`).

**Why the obvious fix is wrong.** Stamping the manifest on the refresh path *blinds the drift
oracle*. Reproduced by the planner on a curated fixture with a real, undocumented edit:

```
manifest frozen at old bytes : (DriftRow(rel_path='app/service.py', feature_id='service-loop'),)
manifest re-stamped at new   : ()
```

`drift.py:_content_unchanged` (`drift.py:400-414`) drops any file whose live bytes equal the
manifest sha. Stamping right after observing an edit writes that edit's sha, so the change
that triggered the rebuild vanishes from the next report.

**Root cause — one store, two contradictory consumers:**

| Consumer | Needs the fingerprints to mean |
|---|---|
| `incremental.rebuild_changed` (`incremental.py:118`) | "bytes as of the last **refresh**" — change detection |
| `drift.compute_drift` (`drift.py:175`) | "bytes the **docs** describe" — the staleness oracle |

They coincide only on a fresh `ingest`, where `build_all` writes deterministic artefacts *and*
scaffolds feature docs in one pass. The enriched `--changed` path refreshes artefacts but not
curated docs, so any refresh-time stamp breaks drift's proxy.

**The fix (owner decision, this session).** Stop overloading one store. The repo already has
two, and each is a natural fit for one role:

| Store | New role | Stamped by | Read by |
|---|---|---|---|
| `.context/map/files.json` | "bytes the index was built from" | every refresh — already does (`enriched_refresh.py:117`) | `rebuild_changed` |
| `.context/cache/manifest.json` | "bytes the docs describe" | `reconcile-stamp` (**new**) | `drift.compute_drift` |

This fixes both halves: phantom mtime rows disappear (a file unchanged since the last reconcile
is filtered), real undocumented edits **keep** their row until reconcile, and
`rebuild_changed`'s self-feeding stale-fingerprint loop closes.

**Not in scope.** The mtime heuristic itself, the reconcile anchor model, drift report wording,
the `rebuild` refusal on curated indexes, and the frontmatter hash mismatch (see Open
questions 1 — deferred to its own proposal by owner decision).

## Contracts

**Invariant A.** `map/files.json`'s `sha256` column is the sole change-detection fingerprint for
`rebuild_changed`. Already written on every refresh path.

**Invariant B.** `cache/manifest.json` describes the source tree as of the **last reconcile**.
Only `stamp_reconciled` advances it, in the same operation that advances
`meta.indexed_commit` — the two become one consistent "docs describe this state" pair (Model B).

**Seam 1 — `dummyindex/context/build/incremental.py:118-124`.** Today:

```python
    prior_by_path = _read_prior_fingerprints_via_manifest(context_dir)
    if prior_by_path is None:
        # First run after a pre-manifest install — fall back to the older
        # files.json fingerprints. ...
        prior_by_path = _read_prior_fingerprints(files_json)
```

Swap the precedence: `_read_prior_fingerprints(files_json)` becomes primary, the manifest
reader the fallback. **Both functions already exist**; this is a reordering, not new code.

*Hash compatibility, verified:* `_hash_files` uses `file_hash(p, root)` (`incremental.py:341`)
and `maps.py:153` writes `sha256=file_hash(p, root)` — the **same function**. The current
manifest pairing does not match (`write_manifest` → `FileEntry.from_path`, raw bytes), which is
why frontmattered `.md` files report `modified` forever. Reproduced:

```
doc.md    file_hash=c2940f3a16adc051  manifest=09e1f943fa1d2060  *** MISMATCH ***
plain.md  MATCH        a.py  MATCH
```

**Seam 1 therefore also fixes that mismatch for change detection**, because both sides become
`file_hash`. The mismatch survives only in `manifest.compare()` (`manifest.py:191`) and
`drift.py:414`, which is the deferred proposal's territory.

**Seam 2 — `dummyindex/context/build/reconcile.py:251` `stamp_reconciled(...)`.** Add the
manifest write there, after the anchor advance succeeds, so a refused or failed stamp leaves
both the anchor and the fingerprints untouched. Mirror `runner.py:272-279`'s containment
verbatim — it warns rather than raising:

```python
try:
    write_manifest(context_dir, root=out_root, files=manifest_files)
except Exception as exc:
    warnings.warn(f"manifest write failed: {exc!r}; drift detection disabled", stacklevel=2)
```

**Reused symbols** — cited from **source only**. `.context/map/symbols.json` does **not** index
`dummyindex/context/build/` at all (see § Index gaps), so an index citation would resolve to the
wrong function:

- `write_manifest` — `dummyindex/context/build/manifest.py:91-97`, signature transcribed:
  ```python
  def write_manifest(
      context_dir: Path,
      *,
      root: Path,
      files: Iterable[Path],
      now: _dt.datetime | None = None,
  ) -> Path:
  ```
  Keyword-only `root`/`files`; publishes via `tmp.replace()` (`manifest.py:129`), atomic on POSIX.
- `_read_prior_fingerprints` — `incremental.py:347-360`. Reads `{path: sha256}` from files.json,
  returns `None` on `OSError`/`JSONDecodeError`.
- `stamp_reconciled` — `dummyindex/context/build/reconcile.py:251`.
- `_content_unchanged` — `dummyindex/context/drift.py:400-414`.

**Consequence for `dummyindex context check`.** `cli/check.py:87` calls
`compare(context_dir, root=out_root, current_files=current)` against the manifest. Under
Invariant B its report changes meaning from "changed since last build" to "changed since last
reconcile". That is arguably the more useful reading, but it **is** a user-visible semantic
change and must be stated in the changelog. See Open question 2.

**Preserved explicitly.** `meta.indexed_commit`'s Model B semantics (`incremental.py:145-148`);
the curated taxonomy; `IncrementalResult`'s shape; `Manifest` `SCHEMA_VERSION = 1`
(`manifest.py:37`) — no schema change, only a different write moment. The three commit-anchored
signals stay manifest-independent (`reconcile.py` has one docstring mention of the manifest, no
read).

## Acceptance

Every criterion names the exact new test function, because measured `-k` selectors on existing
names collect the wrong set (`-k manifest` → 0 collected; `-k enriched` → 24 pre-existing tests).
All new tests carry `@pytest.mark.integration` per `.context/conventions/testing.md:19` with
`--strict-markers` (`pyproject.toml:79`). **Fixtures must contain no frontmattered `.md`** —
Open question 1's mismatch would otherwise produce a false red.

- [ ] A1 — `rebuild_changed` reads files.json first.
      `tests/context/build/test_incremental.py::test_changed_rebuild_uses_files_json_fingerprints`:
      on a curated `primed_repo` + `_enrich()`, delete `cache/manifest.json` entirely, edit one
      `.py` file's bytes → `skipped is False` and `preserved_enriched is True`.
      Negative control in the same test: with no edit → `skipped is True`.
      Observed by: `uv run pytest tests/context/build/test_incremental.py -k test_changed_rebuild_uses_files_json_fingerprints`
- [ ] A2 — the self-feeding loop is closed.
      `...::test_consecutive_changed_rebuilds_reach_steady_state`: two consecutive
      `rebuild_changed` calls with no intervening edit → the second returns `skipped is True`.
      Observed by: `uv run pytest tests/context/build/test_incremental.py -k test_consecutive_changed_rebuilds_reach_steady_state`
- [ ] A3 — `reconcile-stamp` writes the manifest.
      `tests/context/build/test_reconcile.py::test_stamp_reconciled_restamps_manifest`: after
      `stamp_reconciled(...)` succeeds, `cache/manifest.json` exists and the tracked file's
      `sha256` equals `hashlib.sha256(path.read_bytes()).hexdigest()`.
      Pre-state `generated_at` is overwritten with the sentinel `"2000-01-01T00:00:00+00:00"`
      first, because `write_manifest` stamps `timespec="seconds"` (`manifest.py:117-119`) and a
      same-second run would compare equal.
      Observed by: `uv run pytest tests/context/build/test_reconcile.py -k test_stamp_reconciled_restamps_manifest`
- [ ] A4 — a refused/failed stamp leaves the manifest untouched.
      `...::test_refused_stamp_does_not_touch_manifest`: drive `stamp_reconciled` to its refusal
      path, assert `cache/manifest.json` bytes are byte-identical.
      Observed by: `uv run pytest tests/context/build/test_reconcile.py -k test_refused_stamp_does_not_touch_manifest`
- [ ] A5 — **the criterion this proposal exists for.** A real undocumented edit keeps its drift
      row across a `rebuild --changed`, and clears on `reconcile-stamp`.
      `tests/context/test_drift.py::test_mtime_row_survives_changed_rebuild_and_clears_on_stamp`:
      curated fixture via `_make_feature` (`test_drift.py:53-80`) + `_write_manifest_for`
      (`:208-216`) + `_touch` (`:83-87`); edit source bytes; assert `compute_drift(root).rows`
      is **non-empty** after `rebuild_changed`, then `stamp_reconciled`, then assert `rows == ()`.
      The non-empty half is the mandatory negative control per
      `.context/conventions/testing.md:41` — without it the assertion passes vacuously
      (`compute_drift` short-circuits at `drift.py:133-134` and `:141-147` when no
      `feature.json` carries a populated `files` list).
      Observed by: `uv run pytest tests/context/test_drift.py -k test_mtime_row_survives_changed_rebuild_and_clears_on_stamp`
- [ ] A6 — CLI surface, the one the field report actually exercised.
      `tests/cli/test_rebuild_cli.py::test_changed_rebuild_on_curated_repo_succeeds`: on a
      curated repo with one modified file, `rebuild.run([str(repo), "--changed"])` returns 0 and
      prints `"enriched index preserved"`. Model on that file's existing `primed_repo` (`:24-29`)
      and `_curate` (`:32-44`).
      Observed by: `uv run pytest tests/cli/test_rebuild_cli.py -k test_changed_rebuild_on_curated_repo_succeeds`
- [ ] A7 — full suite green on the CI command, which `.context/conventions/testing.md:9` names as
      the source of truth: `python -m pytest tests/ -q --tb=short` exits 0.
- [ ] A8 — the landing commit subject uses the `fix:` conventional type, so
      `scripts/release.py:63-66` emits the entry under `### Fixed` automatically. **No hand-edit
      of `CHANGELOG.md`** — it is machine-prepended by `scripts/release.py:208-216` from
      `.github/workflows/release.yml`, and there is no Unreleased section. The commit body must
      name the `dummyindex context check` semantic change from § Contracts.

## Open questions

1. **Frontmatter hash mismatch — deferred to its own proposal (owner decision, this session).**
   `_hash_files` → `file_hash` strips YAML frontmatter (`pipeline/io/cache.py:115-116, 125`);
   `write_manifest` → `FileEntry.from_path` hashes raw bytes (`manifest.py:50-55`). Seam 1
   removes this from the change-detection path, but it survives in `manifest.compare()`
   (`manifest.py:191`, used by `dummyindex context check`) and `drift.py:414`. Unifying requires
   changing all three in lockstep. **Blocker-linked follow-up; every fixture here stays
   frontmatter-free so it cannot mask the issue.**
2. **Is `check`'s new "since last reconcile" reading wanted?** It follows from Invariant B and
   needs no code change, but it is user-visible. **Recommend: accept and document.** Confirm
   before the changelog wording is written.
3. **Should `stamp_reconciled` stamp when it has no git anchor?** `compute_reconcile_report`
   returns empty off-git (`reconcile.py:123-124`, `:141`) and `run_stamp` refuses without a HEAD
   (`cli/reconcile.py:121`). Off-git repos would then never get a manifest at all, and drift
   falls back to pure mtime (`_manifest_shas` returns `{}` → legacy behaviour, `drift.py:391-397`).
   **Recommend: accept the fallback** — it is the documented pre-manifest behaviour, not a
   regression.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `install-surface`
- `tree-enrich`
- `equip`
- `feature-taxonomy`
- `session-memory`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->

## Index gaps found while planning (hard rule 3 — code wins)

**`dummyindex/context/build/` is not indexed at all.** `"build"` is in `_SKIP_DIRS`
(`dummyindex/pipeline/io/detect.py:308`), so the package is pruned as a build-artefact
directory. Measured: 0 of 4495 entries in `.context/map/symbols.json` come from
`context/build/`, and `incremental.py`, `manifest.py`, `runner.py`, `enriched_refresh.py` are
absent from `.context/map/files.json` (464 files). The only indexed `write_manifest` is
`dummyindex/context/domains/equip/lifecycle/manifest.py:54` — a **different** function,
signature `(context_dir, manifest: EquipmentManifest)`. A builder resolving the name through
the index would import the wrong one; hence every citation in this spec is source-only.

The `propose` consistency scan's five related features are a downstream symptom — none owns
the files this change touches:

| File | Owning feature |
|---|---|
| `dummyindex/cli/rebuild.py` | `cli-dispatch` |
| `dummyindex/context/drift.py` | `session-memory` |
| `dummyindex/context/build/*.py` | **none — unindexed** |

Recorded only. Repairing it belongs to reconcile and to a separate `detect.py:308` proposal,
not here.

Also noted: `dummyindex context check --versions` reports `.context` stamped **0.34.0** against
a **0.35.0** CLI. Pre-existing skew, unrelated; resolved by `/dummyindex-update`.

## Adjacent bugs — recorded, out of scope

1. `detect.py:308` prunes any directory named `build`, hiding `context/build/` from the index.
2. `cli/check.py:75-86` and `runner.py:267-272` already build different file sets, so
   `dummyindex context check` reports hidden-dir docs (`.changeset/*.md`) as `removed` on every
   run. `_DEFAULT_DOC_DIRS` (`domains/source_docs/discovery.py:29-38`) includes `.changeset`,
   which `detect()`'s hidden-dir pruning drops.
