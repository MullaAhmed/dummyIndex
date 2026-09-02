# Critique panel — round 1 findings (verified subset)

Three critics ran in parallel against HEAD `2bb91c1` (v0.35.0). Every claim below was
**independently re-verified by the planner** against source or by execution; unverified
critic claims are not carried here.

## BLOCK-1 (decisive) — re-stamping at refresh time BLINDS the mtime drift oracle

Reproduced by the planner:

```
BEFORE fix (manifest frozen at old bytes): (DriftRow(rel_path='app/service.py', feature_id='service-loop'),)
AFTER  fix (re-stamped at new bytes):     ()
```

`drift.py:_content_unchanged` (`drift.py:400-414`) filters any file whose live bytes equal the
manifest sha. Stamping *right after observing an edit* writes the new sha, so the very change
that triggered the rebuild disappears from `DriftReport.rows` on the next run.

**Root cause — one manifest, two contradictory consumers:**

| Consumer | Wants the manifest to mean |
|---|---|
| `incremental.rebuild_changed` (`incremental.py:118`) | "bytes as of the last **refresh**" — for change detection |
| `drift.compute_drift` (`drift.py:175`) | "bytes the **docs** describe" — the staleness oracle |

They coincide only on a fresh `ingest`, where `build_all` writes deterministic artefacts **and**
scaffolds feature docs in one pass. On the enriched `--changed` path the refresh updates
deterministic artefacts but **not** curated docs, so a refresh-time stamp breaks drift's proxy.

Residual coverage measured by the critic: with a git repo + valid anchor, `drifted_features`
still catches the change (`git_delta.py:199-206`). **Off-git, no anchor, or an orphaned anchor
→ `compute_reconcile_report` returns empty (`reconcile.py:123-124`, `:141`), so those repos
lose real-modification drift entirely.**

## BLOCK-2 — the seam misses a second caller

`refresh_deterministic_artifacts` has two non-test callers:
- `dummyindex/context/build/incremental.py:150`
- `dummyindex/installer/install/project_init.py:77` — the install / `/dummyindex-update` flow,
  which has its own `status.enriched` branch and would keep decaying under a seam-A fix.

The comment drafted for T2 — *"the enriched path is the ONLY path a curated repo ever takes"* —
is contradicted by source and must not ship.

## BLOCK-3 — hash-function mismatch makes the "second run skips" claim false

Reproduced by the planner:

```
doc.md    file_hash=c2940f3a16adc051  manifest=09e1f943fa1d2060  *** MISMATCH ***
plain.md  MATCH        a.py  MATCH
```

`incremental._hash_files` → `file_hash()` (`pipeline/io/cache.py:106-126`) hashes `.md` **below
the YAML frontmatter**; `write_manifest` → `FileEntry.from_path` (`manifest.py:50-55`) hashes
**raw bytes**. Any frontmattered `.md` is reported `modified` forever, so `changes.has_changes`
never goes False on such repos. Pre-existing, but the fix amplifies it into a permanent
refresh+stamp loop. Note `drift.py:414` and `manifest.compare()` (`manifest.py:191`) also hash
raw bytes — unifying on `file_hash` requires changing all three in lockstep.

## BLOCK-4 — `read_manifest` is unguarded; corrupt manifest crashes `rebuild --changed`

Reproduced by the planner: `read_manifest` on truncated JSON → `RAISED: JSONDecodeError`.
`manifest.py:138-147` has an unguarded `json.loads` and unguarded `v["sha256"]/["size"]/["mtime"]`;
`_read_prior_fingerprints_via_manifest` (`incremental.py:363-377`) adds no guard.
`drift.py:391-397` guards the identical call. The asymmetry is the defect.

Also: `.context/cache/` is gitignored, so **absent is the default state of every fresh clone**,
and a doc-free repo then takes the early `skipped=True` return and never stamps.

## BLOCK-5 — file-set parity is provably false

`_DEFAULT_DOC_DIRS` (`domains/source_docs/discovery.py:29-38`) includes `.changeset`, which
`detect()`'s hidden-dir pruning drops. Measured by a critic on a synthetic repo:
`ONLY runner: ['.changeset/tidy-pens.md']`. On dummyindex's own tree the two sets are 530 == 530,
so a fixture modeled on this repo gives a **false green**.

## HIGH — planner errors, confirmed

1. **`symbols.json` citation is false.** `"build"` is in `_SKIP_DIRS` (`detect.py:308`), so
   `dummyindex/context/build/` is invisible to the index — 0 of 4495 symbols. The only indexed
   `write_manifest` is `domains/equip/lifecycle/manifest.py:54`, a different function with an
   incompatible signature (`(context_dir, manifest: EquipmentManifest)`). The spec's drift note
   should read **unindexed**, not "unowned".
2. **"No enriched-path behaviour test exists today" is false.** Eight exist:
   `tests/context/build/test_incremental.py:420, 451, 492, 530, 563, 592, 615, 662`.
   Acceptance A3 duplicates `test_enriched_changed_rebuild_preserves_indexed_commit:530`.
   The real fixtures to reuse are `primed_repo` (`:32-38`) and `_enrich(repo)` (`:122-149`) —
   **not** the `is_enriched_index` unit tests at `:153-412`.
3. **T4/A4 already exists.** `tests/context/test_drift.py:220`
   `test_no_mtime_row_when_sha_matches_manifest` is A4 line-for-line, with its negative control
   at `:240` and back-compat control at `:260`.
4. **Two of three `-k` selectors collect nothing.** Measured:
   `-k manifest` on `test_incremental.py` → `no tests collected (33 deselected)`;
   `-k parity` on `test_manifest.py` → `no tests collected (14 deselected)`;
   `-k enriched` → 24 **pre-existing** tests, so passing it is no evidence.
5. **T6 is invalid.** `CHANGELOG.md` is machine-prepended by `scripts/release.py:208-216` from
   conventional-commit types (`release.py:63-66` maps `fix` → `Fixed`), driven by
   `.github/workflows/release.yml`. There is no Unreleased section; a hand-written entry is
   duplicated on the next release.

## MEDIUM — carried into the revision

- **Unguarded stamp.** `runner.py:272-279` wraps its `write_manifest` in `try/except` +
  `warnings.warn("manifest write failed: …; drift detection disabled")`. The drafted snippet has
  no guard, so it would turn a currently non-fatal condition into a hard crash of the enriched
  path *after* the refresh already wrote `files.json`/`symbols.json`/`meta.json`.
- **Fixed tmp filename, no locking.** `write_manifest` writes a fixed `manifest.json.tmp`
  (`manifest.py:125`) then `replace()`. `grep -rn "flock|fcntl|filelock|LOCK_EX" dummyindex/` → 0
  hits. Two concurrent runs can interleave and publish truncated JSON, which per BLOCK-4 crashes
  `rebuild --changed`. Fix: `tempfile.mkstemp` in the same dir.
- **Two detections, not one.** `rebuild_changed` calls `detect()` at `incremental.py:101`;
  `refresh_deterministic_artifacts` calls it again at `enriched_refresh.py:106`. The spec's claim
  that the TOCTOU window "is identical to `build_all`'s" is inaccurate — `build_all` has one
  window, this path has two.
- **Missing pytest markers.** `pyproject.toml:79` sets `--strict-markers`;
  `.context/conventions/testing.md:19` — "no implicit default". No planned test names a marker.
- **Missing negative controls.** `.context/conventions/testing.md:41` mandates a permanent
  negative-control fixture so a gate cannot pass vacuously. A4 and A6 as drafted are both
  vacuously green (`compute_drift` short-circuits at `drift.py:133-134` and `:141-147` unless
  `feature.json` carries a populated `files` list; and the A6 monkeypatch must target
  `dummyindex.context.build.incremental.refresh_deterministic_artifacts`, bound at import —
  patching `enriched_refresh.*` silently no-ops).
- **No CLI-level acceptance.** Every criterion asserts the library function; the field report is
  about `dummyindex context rebuild --changed` (`cli/rebuild.py:51-62`).
  `tests/cli/test_rebuild_cli.py` is the ready-made pattern.
- **No `— via <tool>` tags.** `.context/equipment.json` carries `python-implementer`,
  `python-tester`, `dummyindex-reviewer`, and the `dummyindex-verify` skill. Zero tasks tagged.

## Verified benign (checked, not assumed)

- `.context` is in `detect()`'s ignore set (`detect.py:319`) — no self-referential stamp loop.
- `write_manifest`'s **publish** is atomic (`tmp.replace()`, `manifest.py:129`). Only the write
  half is not (see concurrency above).
- `meta.indexed_commit` untouched by the refresh — `_refresh_meta` (`enriched_refresh.py:199-234`)
  passes only `file_count`/`symbol_count`/`dummyindex_version`. Model B intact.
- The three commit-anchored signals are genuinely manifest-independent
  (`reconcile.py` has one docstring mention, no read).
- Moved/re-cloned repo is benign — no consumer reads `Manifest.root`.
- `write_manifest`'s signature transcription in `spec.md` is byte-accurate (hard rule 4 passes).

## Adjacent bugs — recorded, out of scope for this proposal

1. `detect.py:308` prunes any dir named `build`, so `dummyindex/context/build/` is invisible to
   `.context/map/*` in this repo.
2. `cli/check.py:75-86` vs `runner.py:267-272` already disagree, so `dummyindex context check`
   reports hidden-dir docs (`.changeset/*.md`) as `removed` on every run.
