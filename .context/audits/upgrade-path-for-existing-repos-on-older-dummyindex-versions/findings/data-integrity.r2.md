## data-integrity — round 2

- #2 (cache-key collision) — hold — final status: confirmed, **high**. This is a product-level data-integrity defect in a file the index presents as authoritative; it is not a cosmetic gap that only matters in this repo.
  - **The harm is false data, not just missing data.** I ran `build_all` on a scratchpad copy holding two byte-identical files, `a/mod.py` and `b/mod.py`, each with `helper` and `caller`.
    - `map/symbols.json` = `[('caller','a/mod.py'), ('helper','a/mod.py')]`; b's definitions are gone.
    - `coverage.json` records `b/mod.py` as `symbols: 0, state: "file-only"` with "No AST symbols extracted". That is a positive false claim, because extraction parsed the file. The state is derived at `dummyindex/context/build/coverage.py:L52-L69`; the payload is reused at `dummyindex/pipeline/extract/__init__.py:L197-L203`.
  - **No workaround exists.** It happens on a cold cache (the first file seeds the entry, `dummyindex/pipeline/io/cache.py:L211-L230`), so deleting `cache/` does not help.
  - **Byte-identical non-trivial files are common in general repos.** Examples:
    - vendored or copied libraries, e.g. `vendor/x/` beside `third_party/x/`;
    - generated stubs per service, e.g. identical protobuf/OpenAPI clients;
    - monorepo scaffolds, e.g. identical `packages/*/index.ts` barrels, `jest.config.js`, `conftest.py`, `setup.py`;
    - copied migrations and test fixtures.
  - **What breaks for every copy after the first:** "Where is X defined?" lookups, `callers-of` / `dead-code` attribution and reconcile ownership.
  - **Correctness's medium is accurate only for this repo** (0 non-trivial duplicates). I agree the root is in `pipeline/io`, outside the upgrade topic. File it as high for the product with low impact in this repo; it should not be dropped as off-topic.

- #3 (unversioned cache) — adjust — final status: confirmed, **medium, latent** (was high). I accept correctness's evidence: `git diff --stat v0.36.0 v0.37.0 -- dummyindex/pipeline/` touches only `extract/__init__.py` (orchestration), `build/validate.py` and `io/detect.py`. The per-file extractors last changed in `664be2d` (0.29.1). So the 466 pre-tag entries are equivalent for 0.36→0.37. It stays medium because the gap still has no detection: the key and the shape check stay version-blind (`cache.py:L106-L126`, `L164-L183`), and missing fields are read as empty (`extract/__init__.py:L328-L329`). The first release that changes a per-file extractor will serve stale output silently. Over-engineering's `cache/<PACKAGE_VERSION>/` dir is an acceptable single fix for #3 and #9 together.

- #13 (NEW: curated tree.json abstracts have no guard and no backup) — add — final status: open, **medium**. Correctness's evidence (2,822 INFERRED abstracts at `cfe6a13`, 0 after squash `376e06d`) is consistent with a code path I can prove:
  - **The full build overwrites tree.json without merging.** `build_all` → `_write_all` → `write_tree` writes a fresh structure-derived tree with no carry-forward (`dummyindex/context/build/runner.py:L496-L497`, `dummyindex/context/build/tree.py:L324-L332`).
  - **The destructive-rebuild guard ignores tree.json.** It checks only `features/INDEX.json` and the feature dirs (`dummyindex/context/build/incremental.py:L305-L333`). A repo whose features are still `community-*` stubs but whose tree was `enrich-apply`'d therefore reaches `build_all` from `rebuild --changed` or `install` (`incremental.py:L162-L192`; `dummyindex/installer/install/project_init.py:L121-L128`) and loses every abstract without a warning. Only the explicit `--full` warns (`dummyindex/cli/rebuild.py:L68-L74`).
  - **No snapshot exists before overwrite.** `_doc_backups` is used only by doc-reorg (`dummyindex/context/domains/doc_reorg/safety.py:L85`).
  - **Reviewers are told to ignore the file.** tree.json is marked `linguist-generated` (`runner.py:L369-L371`) and labelled "deterministic … don't hand-edit". That is how a 2,822-abstract loss could pass review unnoticed.
  - Suggested fix:
    - count tree INFERRED nodes in `enriched_index_status`;
    - route `build_all` through the `refresh_tree` carry-forward (`dummyindex/context/build/navigation_refresh.py:L75-L158`);
    - refuse (or back up to `_doc_backups/`) any write that lowers the INFERRED-abstract count.

- over-engineering.md#2 (tree.json compaction) — dispute held; conditional concur — #13 makes tree.json a curated-data carrier, which strengthens the dispute. Over-engineering's r1 claim "behaviour-neutral" is refuted: a missing `confidence` makes `_mechanical_abstract` return False (`navigation_refresh.py:L36-L38`), so every stub is treated as authored and carried forward or `source-stale`-labelled (`L133-L153`). I concur when all three of these hold:
  - (a) `abstract` and `confidence` are always emitted, or `_mechanical_abstract` defaults a missing `confidence` to `EXTRACTED` and a missing abstract to mechanical;
  - (b) both writers change together (`tree.py:L331`, `navigation_refresh.py:L154-L158`);
  - (c) either the layout stays one node per line, or #13's INFERRED-count guard ships first.
  - Dropping the null keys `overview_ref`/`detail_ref` and the empty `labels`/`evidence` is safe under (a): carry-forward copies only keys present (`L142`).

- over-engineering.md#3 (council/ to cache) — conditional concur — I concur with r1's amended version when all three of these hold:
  - (a) the move happens only after the log records stage 3 complete for that feature;
  - (b) `01-dev-draft.md` stays a file snapshot and is never replaced by `git diff`, because the architect rewrites `plan.md` in place with no commit between stages (`dummyindex/skills/council/30-plan.md:L1-L9`);
  - (c) the scratch lives outside any version-scoped or evicted extraction-cache subtree (#3/#9), because resume trusts the log, not file presence (`dummyindex/skills/council/19-resume.md:L36-L43`).
  - `_council-log.json` relocation is excluded unless `dummyindex/context/domains/council.py:L137` and `dummyindex/context/domains/features/ops.py:L325-L336` move with it.

- over-engineering.md#4 (coverage.json) — conditional concur — two parts are safe now: compacting both writers (`coverage.py:L32`, `L84`) and dropping the static `graph_aggregation` string (`coverage.py:L81`). Dropping `files[]` is not safe: `refresh_ownership` needs it to recompute `unassigned` (`coverage.py:L13-L32`, called from `dummyindex/context/domains/features/indexes.py:L124-L126`). Dropping `excluded`/`pending`/`identity_ambiguities` is not safe either: they come only from detection and extraction (`coverage.py:L78-L80`). Correctness also found the HOW_TO_USE contract reader (`dummyindex/context/output/instructions.py:L53`). Final: disputed beyond those two parts.

- over-engineering.md#6b (supporting.md) — conditional concur — of the 19 "Original notes" blocks here, 16 are deterministic stubs, but 3 are INFERRED specs (≈26.6 KB) whose source feature dirs were deleted at merge (`ops.py:L253-L263`, `L280`): `equip` ← `community-7` and `community-14`, `session-memory` ← `community-8`. I concur when:
  - the cut strips only blocks whose notes carry the `Deterministic stub` marker, or `merge_feature` stops copying stub specs from now on;
  - INFERRED blocks are kept;
  - the file is kept wherever a block remains, since drift freshness reads it (`dummyindex/context/drift.py:L49-L59`).
  - Final: disputed for whole-file deletion, confirmed for stub-only stripping.

- over-engineering.md#6a / #10 (docs.md shrink, INDEX.md shrink) — concur — both amended to "shrink" in r1, and no curated data is lost. — confirmed
