# Plan — Give the two fingerprint stores one role each so drift detection stops decaying

> Revised once after the critique panel (see `panel-findings.md`). Every path below was opened.
> **Reused symbols are cited from source only** — `.context/map/symbols.json` does not index
> `dummyindex/context/build/` (`detect.py:308` prunes it), and the indexed `write_manifest`
> homonym is a different function. Tooling tags follow `.context/equipment.json`.

## Tasks

### T1 — Swap the change-detection fingerprint source to `map/files.json`

**Files:** `dummyindex/context/build/incremental.py`

At `incremental.py:118-124`, invert the precedence so `_read_prior_fingerprints(files_json)` is
primary and `_read_prior_fingerprints_via_manifest(context_dir)` is the fallback. Update the
comment: files.json is refresh-time state and is git-tracked, while `cache/` is gitignored
(`.gitignore:19`, `.context/.gitignore:3`) and therefore absent on every fresh clone.

Both readers already exist — `_read_prior_fingerprints` at `incremental.py:347-360`,
`_read_prior_fingerprints_via_manifest` at `:363-377`. **No new function.**

*Why this is also a correctness fix:* `_hash_files` uses `file_hash(p, root)`
(`incremental.py:341`) and `maps.py:153` writes `sha256=file_hash(p, root)` — the same function,
so both sides of `_diff` finally agree. The current manifest pairing does not (raw bytes vs
frontmatter-stripped), which is why frontmattered `.md` files report `modified` forever.

**Also harden the fallback reader.** `_read_prior_fingerprints_via_manifest` calls
`read_manifest`, whose `json.loads` and `v["sha256"]/["size"]/["mtime"]` are unguarded
(`manifest.py:138-147`). Reproduced: truncated JSON → `RAISED: JSONDecodeError`, which crashes
`rebuild --changed`. `drift.py:391-397` guards the identical call; mirror that guard
(`except (OSError, json.JSONDecodeError, ValueError, KeyError): return None`) so a corrupt
manifest degrades to the files.json path instead of aborting.

Honors `conventions/coding-practices.md`.

### T2 — Stamp the manifest inside `stamp_reconciled`

**Files:** `dummyindex/context/build/reconcile.py`

In `stamp_reconciled(...)` (`reconcile.py:251`), after the anchor advance succeeds and before
returning, write the manifest so it records the tree the docs now describe:

```python
        # cache/manifest.json means "bytes the docs describe", so it advances
        # with the anchor, not with a refresh. drift.py:_content_unchanged reads
        # it to filter mtime rows a git op minted; stamping it on the refresh
        # path instead would erase the very edit that triggered the rebuild.
        try:
            write_manifest(context_dir, root=out_root, files=manifest_files)
        except Exception as exc:
            warnings.warn(
                f"manifest write failed: {exc!r}; drift detection disabled", stacklevel=2
            )
```

Containment copied verbatim from `runner.py:272-279` — a read-only FS or full disk must warn,
not abort a stamp whose anchor already advanced. Import `write_manifest` at module level:
`runner.py:27` does exactly that and `manifest.py:27-35` imports stdlib only, so there is no
cycle to dodge.

Derive `manifest_files` the same way `runner.py:267-270` does, so the two writers agree. **Do
not** reuse `incremental.py`'s detect-shaped set: `_DEFAULT_DOC_DIRS`
(`domains/source_docs/discovery.py:29-38`) includes `.changeset`, which `detect()`'s hidden-dir
pruning drops — measured divergence `ONLY runner: ['.changeset/tidy-pens.md']`.

**Reused:** `write_manifest` — `dummyindex/context/build/manifest.py:91-97`, signature in
`spec.md` § Contracts.

### T3 — Tests for the fingerprint swap

**Files:** `tests/context/build/test_incremental.py`

Two tests, `@pytest.mark.integration`, matching acceptance A1 + A2. Reuse the **real** fixtures:
the `primed_repo` fixture at `test_incremental.py:32-38` and the `_enrich(repo)` helper at
`:122-149` (it returns the renamed feature id and stamps the spec/tree sentinels).

**Do not** model on the `is_enriched_index` tests at `:153-412` — those are pure `@pytest.mark.unit`
tests over hand-built `tmp_path` dirs that never call `rebuild_changed`, so they are unusable as
a rebuild fixture. Eight enriched-path behaviour tests already exist (`:420, 451, 492, 530, 563,
592, 615, 662`); add to that block, and do **not** duplicate
`test_enriched_changed_rebuild_preserves_indexed_commit:530`.

Fixtures must contain **no frontmattered `.md`** (spec Open question 1).

### T4 — Tests for the reconcile-time stamp

**Files:** `tests/context/build/test_reconcile.py`

Two tests, `@pytest.mark.integration`, matching acceptance A3 + A4: the successful stamp writes
the manifest with correct raw-byte shas; the refusal path leaves it byte-identical. Overwrite
`generated_at` with the sentinel `"2000-01-01T00:00:00+00:00"` before the call — `write_manifest`
stamps `timespec="seconds"` (`manifest.py:117-119`), so a same-second run compares equal and the
test would be intermittently red for no reason.

### T5 — The end-to-end drift test this proposal exists for

**Files:** `tests/context/test_drift.py`

One `@pytest.mark.integration` test, acceptance A5: a real undocumented edit **keeps** its
`DriftRow` across `rebuild_changed`, then clears on `stamp_reconciled`. Reuse `_make_feature`
(`test_drift.py:53-80`), `_touch` (`:83-87`), `_write_manifest_for` (`:208-216`).

The non-empty assertion is the mandatory negative control (`conventions/testing.md:41`) —
`compute_drift` returns `rows=()` unconditionally when `features_dir` is absent
(`drift.py:133-134`) or the file→feature map is empty (`:141-147`), so without it the test
passes vacuously.

Do **not** add the old A4 idea (`rows == ()` after a matching stamp) — that already exists as
`test_no_mtime_row_when_sha_matches_manifest` (`test_drift.py:220`), with its negative control
at `:240` and the back-compat control at `:260`.

### T6 — CLI-level regression

**Files:** `tests/cli/test_rebuild_cli.py`

One `@pytest.mark.integration` test, acceptance A6, on the surface the field report actually
exercised (`cli/rebuild.py:51-62`). Reuse that file's own `primed_repo` (`:24-29`) and `_curate`
(`:32-44`); assert rc 0 and the `"enriched index preserved"` line via `capsys`.

### T7 — **GATE** — confirm the `check` semantic change before landing

`dummyindex context check` (`cli/check.py:87`) reads the manifest, so under Invariant B its
report changes from "changed since last build" to "changed since last reconcile". No code
change, but it is user-visible and must be named in the landing commit body (spec Open
question 2). Main-session item — escalate to the owner, do not dispatch.

### T8 — Verification pass — via dummyindex-verify

Run acceptance A1–A8. A7 uses the CI command `python -m pytest tests/ -q --tb=short`
(`.context/conventions/testing.md:9`, `.github/workflows/tests.yml:30`). **No `CHANGELOG.md`
edit** — `scripts/release.py:208-216` machine-prepends it from the conventional-commit type, and
`scripts/release.py` has no CLI flags, so do not prescribe a dry-run.

## Wave disjointness

File → task, per wave:

| Wave | Item | Writes |
|---|---|---|
| 1 | T1 | `dummyindex/context/build/incremental.py` |
| 1 | T2 | `dummyindex/context/build/reconcile.py` |
| 2 | T3 | `tests/context/build/test_incremental.py` |
| 2 | T4 | `tests/context/build/test_reconcile.py` |
| 2 | T5 | `tests/context/test_drift.py` |
| 2 | T6 | `tests/cli/test_rebuild_cli.py` |
| 3 | T7 | (GATE — no writes) |
| 4 | T8 | (verification — no writes) |

Inverse map, collisions checked **within** each wave:

- `incremental.py` → {T1} — wave 1 only.
- `reconcile.py` → {T2} — wave 1 only. T1 and T2 touch disjoint modules and neither reads the
  other's output: T1 changes which fingerprint file `rebuild_changed` reads; T2 changes when the
  manifest is written. Independent.
- `test_incremental.py` → {T3}, `test_reconcile.py` → {T4}, `test_drift.py` → {T5},
  `test_rebuild_cli.py` → {T6} — four distinct files, one task each, wave 2.
- Waves 3 and 4 write nothing.

Read-write hazards: every wave-2 test *reads* `incremental.py` and `reconcile.py`, which wave 1
*rewrites* — hence the strict wave boundary. T5 reads both seams (it exercises `rebuild_changed`
**and** `stamp_reconciled`), which is why no test sits in wave 1.

No file appears twice inside any single wave. Grouping proven.

## Tooling map

`.context/equipment.json` carries `python-implementer`, `python-tester`, `dummyindex-reviewer`,
and the `dummyindex-verify` skill.

**T1–T6 and the review item are deliberately UNTAGGED.** Those are generated agents that
already cover ordinary implementation, test, and review work, and the build CLI classifies any
`— via` item as `dispatch: main-session` — tagging them would serialize the whole plan into the
conductor session and destroy the wave parallelism. Verified: untagged, `--next-wave` reports
`2 parallel items (dispatch concurrently)` and auto-resolves `subagent_type: python-implementer`;
tagged, the same wave reported `2 main-session (handle in THIS session — never dispatch)`.

Tagged on purpose: the A1–A8 acceptance items carry `— via dummyindex-verify` (a skill, not an
agent — its `SKILL.md:38` prescribes `uv run pytest -q`), and T7 carries `**GATE**`. Both are
correctly main-session. No capability gap; nothing contradicts a *When NOT to use*.
