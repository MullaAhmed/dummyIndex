# Critiques — stage 3 (feature-taxonomy)

## critic-database (data-integrity lens)

## Data integrity

- **No cross-file atomicity — only per-file atomicity.** Each op persists `feature.json`, `INDEX.json`, `INDEX.md`, `graph.{json,html}` as *independent* tmp+`replace` writes (`helpers.py:131-140`); `assign_files` does `_write_json(feature_json)` → `_write_pending_marker` → `_update_index_counts` → `_refresh_index_artifacts` as four separate replaces (`placement.py:170-182`). Validate-before-write makes a *rejected* op a clean no-op, but a crash/SIGKILL *mid-sequence* (e.g. after `feature.json` updates but before `INDEX.json`) leaves the canonical machine map permanently out of sync with the feature folder, with no journal/rollback. The plan's "atomic persistence" claim (`plan.md:23,43`) holds per-artifact, **not** across the 3-5 artifacts a single op mutates. Material for `merge_feature`, which spans section.md → feature.json → folder delete → INDEX → graph → council-log (`ops.py:226-342`) — a crash after `_rmtree(src)` (`ops.py:263`) but before the INDEX drop (`ops.py:266-299`) strands an INDEX entry pointing at a deleted folder.

- **Member derivation is deterministic but silently empties on absent/stale symbols map.** `_members_for_files` returns `()` when `map/symbols.json` is missing (`placement.py:466-468`, `indexes.py:115-116`) — so a `scaffold`/`assign`/`unassign` run before/without a maps rebuild writes `members: []` *and* `member_count: 0` into both `feature.json` and `INDEX.json`, looking authoritative. Determinism holds only relative to the symbols-map snapshot at op time; nothing re-derives members when `symbols.json` later changes (`rebuild --changed` rebuilds the map but no placement re-runs), so `members` can silently drift from the symbol set the files actually contain. Plan flags the absent-map tolerance as deliberate (`plan.md:38,55`) but not the resulting count drift in INDEX.

- **`merge_feature` does NOT re-derive members — it set-unions raw lists.** Unlike placement, merge merges target+source `members`/`files`/`entry_points` by dedup union (`ops.py:253-257`) rather than re-running `_members_for_files` over the combined file set. If source `members` were stale (derived against an older symbols map) they propagate into the target unchecked, violating the "members follow files" invariant (`plan.md:38`) for the one op that crosses two features' member sets.

- **Duplicate-id rejection covers scaffold but the INDEX can hold duplicates from a partial merge/rename.** `scaffold_feature` rejects an existing folder id (`placement.py:78-82`) and `_validate_placement_id` blocks reserved `community-*` (`placement.py:395-403`) — folder-level dedup is sound. But `_append_index_entry` blindly appends with no scan for an existing `feature_id` entry (`placement.py:489-509`); it relies on the folder-existence guard upstream. If a prior op crashed leaving a stale INDEX entry (see cross-file point), or `rename` partially completed, a subsequent scaffold of a *new* folder whose id collides with a stranded INDEX row yields two entries for one id. `_update_index_counts`/`_drop_index_entry` then update/drop *all* matching rows ambiguously (`placement.py:521-524`, `placement.py:537`).

- **`rename_feature` referential update is best-effort per-artifact, not all-or-nothing.** It updates `feature.json`, every `flows/*.json` `feature_id`, INDEX.json, INDEX.md, and graph.json as guarded independent writes (`ops.py:65-149`). Each guard is `if <file>.exists()`, so a missing graph.json silently skips graph rewiring while INDEX is updated — the folder is renamed but `graph.json` nodes/edges still carry `from_id` if graph.json was absent at a prior step then regenerated stale elsewhere. No post-condition verifies all four references converged on `to_id`.

- **Idempotency of `assign`/`unassign` is real for the file set but the pending-enrichment marker is re-dropped every call.** Re-assigning an already-owned file is a clean no-op on `files` (set union, `placement.py:163`) — good. But every call unconditionally re-writes `.pending-enrichment` (`placement.py:173`, `placement.py:248`), so a no-op-effect assign still re-flags the feature for enrichment and blocks `reconcile-stamp` (`plan.md:39,61`). Idempotent on payload, **not** on enrichment state.

- **`graph.json` regenerated from disk while `INDEX.json` is hand-edited — two divergent sync paths.** Post-mutation, `INDEX.json` is patched in place (`_append`/`_update`/`_drop`, `placement.py:489-548`) but `graph.json` is fully rebuilt by walking `features/*/feature.json` (`indexes.py:51-104`). These can disagree if a `feature.json` on disk is itself stale vs. its INDEX row (e.g. after the partial-write window above): INDEX shows old counts, graph shows current file contents. `_refresh_index_artifacts` swallows `FileNotFoundError` (`placement.py:562-563,567-568`) so a missing INDEX.md/graph leaves the op "successful" with navigation artifacts absent and no warning.

- **`_drop_index_entry` flow_count decrement trusts the INDEX row's own `flow_count`, not the folder.** It subtracts the dropped entry's recorded `flow_count` from the top-level total (`placement.py:540-546`); if that per-entry count had drifted from the actual `flows/*.json` on disk, the top-level `flow_count` becomes wrong and there is no rebuild-from-disk reconciliation for it (the plan notes "no disk-rebuild helper" for INDEX, `plan.md:36`). Same trust-the-stored-count pattern in `merge_feature` (`ops.py:275`) and `remove_flow` (`ops.py:413,418`).

## Security

- **Stored XSS via the confidence chip in `graph.html` (the one unescaped feature field).** `sub.innerHTML = chips` with `f.confidence ? \`<span class="chip">${f.confidence}</span>\` : ""` (`viewer.py:298-304`) — no `escapeHtml`, unlike every sibling sink (`viewer.py:517-583`). `confidence` is copied verbatim from `feature.json` with no enum validation (`indexes.py:66`) into graph.json by `rebuild_features_graph` during placement ops (`placement.py:565`). A `feature.json` with `confidence: "<img src=x onerror=...>"` (planted via scaffold/assign/reconcile from an untrusted index or poisoned PR) executes when anyone opens the viewer. Fix: `escapeHtml(f.confidence)` + enum-validate confidence at render.

- **`graph.html` has no CSP/SRI and runs at `file://` (or local `http.server`) origin.** `VIEWER_HTML` (`viewer.py:25-214`) loads d3 from a CDN (`viewer.py:215`) with no integrity hash and no `Content-Security-Policy`. An injected payload runs with page privileges and can `fetch` sibling `.context/` files. Fix: strict CSP meta + SRI on d3.

- **id-slug traversal is correctly closed (regression-watch).** `_validate_feature_id` strict whitelist `[a-z0-9-_]`, no `.`/`/` (`helpers.py:18-29`); `remove_feature` validates BEFORE deriving `feat_dir` so `../sibling` can't reach `_rmtree` (`placement.py:292-296`). Correct today — flag so loosening ids later doesn't reopen traversal.

- **`assign_files` containment via `.resolve()` + `relative_to(repo_root)` blocks out-of-repo writes (`placement.py:419-427`) but is path-string based, not inode-pinned** — `.resolve()` follows symlinks; a TOCTOU swap of a path to a symlink changes what `_live_files`' `is_file()` re-check sees (`placement.py:348`). Low severity (local single-user CLI).

- **`unassign_files`/`_normalize_for_removal` intentionally skips `is_file()`; containment rests solely on `relative_to` after `.resolve()` (`placement.py:447-453`).** Holds (`resolve` normalizes `..` without disk), and no write targets the named path so blast radius is a bad `feature.json` entry, not arbitrary FS write. Correct-but-load-bearing.

- **`name`/`summary` are escaped in the viewer (`escapeHtml`/`.textContent`, `viewer.py:294,312,517,521`) — only `confidence` is the live XSS sink.** Keep the fix scoped to `confidence`; in `INDEX.md` `name`/`summary` are raw Markdown (content-spoof, not script).

## Stage 3 — Product-surface critic (critic-product)

Scenario — observed behavior — gap. Operator running the `features-rename`/`features-merge`/`scaffold-feature`/`assign-files`/`unassign-files` verbs.

- **Merge drops source flows.** `merge_feature` set-unions only `members`/`files`/`entry_points` (`ops.py:253-257`); `flow_ids` is excluded and source flow files are `_rmtree`'d (`ops.py:263`), nodes dropped (`ops.py:309-314`). Flows are neither re-parented to `into_id` nor folded into prose — contrast `rename` which re-points flow `feature_id` (`ops.py:86-93`). Operator loses documented behavior with only a file-touch count reported (`cli/features.py:163-166`).

- **Merge is `supporting`-only with no operator escape hatch.** Gated against `{"supporting"}` (`ops.py:211-215`, `constants.py:48`); no `--allow-new-section` on `features-merge` (unlike `section-write`, `cli/features.py:19-29`). Docstring says widening needs a skill/source edit (`ops.py:198-200`). Confusing given the sibling flag exists elsewhere.

- **No `split` op despite "reshape the taxonomy" framing (`plan.md:23`).** Splitting requires scaffold + unassign (two ops, two `.pending-enrichment` drops, two INDEX edits) and curated prose does not follow moved files (scaffold writes a fresh stub, `placement.py:107`). Merge's dual is hinted but undelivered.

- **`assign-files` swallows already-owned + symbol-less files silently.** Set-union drops dupes (`placement.py:163`) with no new-vs-skipped count; absent/empty symbols → `members=()` (`placement.py:466-468`) so `member_count` doesn't move — mistaken for a failed assign. No CLI line distinguishes the cases.

- **`rename to=B` onto a stranded `B` INDEX row produces two `feature_id=B` rows.** INDEX loop matches `from_id OR to_id` and rewrites both to `to_id` (`ops.py:101-102`); downstream count/drop helpers touch *all* matching rows (`placement.py:521-524,:537`), double-applying. Real rename onto an occupied id is non-idempotent/corrupting.

- **`unassign` last-file refusal forces a verb branch.** Raises if removal empties the feature (`placement.py:234-238`); reconcile must pre-check file count and switch to `features-remove`. No single "remove file, delete if last" op — easy to mis-script into a mid-reconcile exit 2.

- **Graph/INDEX can publish counts that disagree with the just-edited `feature.json` when `symbols.json` is stale.** Placement derives members at op time (`placement.py:164`) but graph re-reads `symbols.json` (`indexes.py:100`); no success message warns a `rebuild --changed` is owed first. Plan flags absent-map tolerance (`plan.md:38,55`) but not the pre-op rebuild requirement.

### Cross-review note (operator impact of the stored XSS)

The Security stored-XSS (`viewer.py:302`, `concerns.md:21`) is armed by the very verbs reviewed here: every placement op + merge/rename bumps `confidence` (`ops.py:258,286`) and calls `_refresh_index_artifacts → rebuild_features_graph` (`placement.py:565`), which copies `confidence` verbatim into `graph.json` (`indexes.py:66`, no enum check). An operator running `features-merge`/`scaffold-feature` against a `.context/` folded from an untrusted PR is the one who arms the payload. Product-side mitigation beyond the `escapeHtml` fix: validate `confidence ∈ ConfidenceLevel` at op time, since every reviewed verb already rewrites that field.
