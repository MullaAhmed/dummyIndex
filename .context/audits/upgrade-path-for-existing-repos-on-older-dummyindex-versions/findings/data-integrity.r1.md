## data-integrity — round 1

### My own findings (data-integrity.md)

- data-integrity.md#1 (orphan shards) — defend — over-engineering.md#1 measured the same numbers independently (79 orphans, 73,171,940 B, all tracked). The writer never sweeps orphans: `dummyindex/export/storage.py:L281-L286`. A reader holding an old manifest fails closed rather than reading corrupt data (`storage.py:L345-L348`), so pruning is safe if the previous generation is kept. — confirmed

- data-integrity.md#2 (cache-key collision) — defend — I built a concrete reproduction in a scratchpad copy: two byte-identical `a/mod.py` and `b/mod.py`, each with `helper` and `caller`, run through `extract()`.
  - Cache disabled: ids are `a_mod_py`, `b_mod_py`, and `mod_helper`/`mod_caller` once from each of a/ and b/.
  - Cache enabled, even cold on the first run: ids are `a_mod_py`, `mod_helper`, `mod_caller`, all with source a/. `b_mod_py` is gone and b's symbols are attributed to a.
  - Code path: the second file is served the first file's payload, which carries the path (`dummyindex/pipeline/extract/__init__.py:L197-L203`, `dummyindex/pipeline/io/cache.py:L211-L230`). `id_remap` cannot rebind it (`extract/__init__.py:L249-L257`). Identical records then dedupe (`dummyindex/context/build/portable_graph.py:L186-L200`).
  - The live repo shows the same: 22 of 23 empty `__init__.py` files are missing from the graph. — confirmed

- data-integrity.md#3 (cache has no version) — defend, narrowed — the mechanism is confirmed: the key is content-only (`cache.py:L106-L126`), the shape check is the only gate (`cache.py:L164-L183`), and missing fields are tolerated (`extract/__init__.py:L328-L329`). Actual stale output across versions is still unproven; the 466/537 count is exposure, not proof of a difference. — confirmed

- data-integrity.md#4 (meta stamp before graph and catalog) — defend — this is made worse by correctness.md#5: the same `_refresh_meta` call both comes first and overwrites on any difference (`dummyindex/context/build/enriched_refresh.py:L154-L163`, `L298-L301`). — confirmed

- data-integrity.md#5 (no migrations on the install path) — defend — correctness.md#8 reached the same root independently (`dummyindex/cli/refresh.py:L36-L37` is the only caller). — confirmed

- data-integrity.md#6 (format change without a version marker) — defend — verified against 0.36 source, `38c3602:dummyindex/context/domains/graph_query/load.py:L64-L71`. — confirmed

- data-integrity.md#7 (config drops unknown keys) — defend — `Config.to_dict` emits a fixed key set (`dummyindex/context/domains/config.py:L241-L260`). — confirmed (low)

- data-integrity.md#8 (no build lock, fixed tmp names) — concede in part — no in-tree concurrent writer exists, because hooks never rebuild (`dummyindex/context/hooks.py:L23-L30`). A race needs two builds started by the user or an agent on the same checkout. The fixed `.tmp` sharing itself is real (`dummyindex/context/build/maps.py:L292-L296`). — confirmed (low, narrowed)

- data-integrity.md#9 (cache never evicted) — defend — see the new interaction under over-engineering.md#3: an eviction pass must exempt any council scratch moved into `cache/`. — confirmed

- data-integrity.md#10 (evolve run dirs) — concede severity — both other personas count `gc/evolve/` as live state (correctness.md#8 "checked and excluded"; over-engineering "load-bearing"). The finding stands only as unbounded-by-design growth: 1 run, 81 KB, no current harm (`dummyindex/context/domains/evolve.py:L917-L927`). — confirmed (downgraded low → info)

- data-integrity.md#11 (equipment-evals) — defend — all three personas agree (correctness.md#8, over-engineering.md#7). — confirmed

- data-integrity.md#12 (info) — defend — `.context/dummyindex-experiment-notes/README.md:L1-L4`. — confirmed

### correctness.md

- correctness.md#1 (junction / ownership) — concur — the code confirms three different "is it a link" checks: `dummyindex/installer/install/family_write.py:L128` uses `is_symlink()`, while `dummyindex/installer/ownership.py:L63-L73` checks for a reparse point. With a junction, `_plain_target` returns None, so `family_is_pristine` returns False (`ownership.py:L52-L60`, `L128-L134`).
  - Content is safe: `sync_family` refuses to write through a link (`ownership.py:L167-L168`), so nothing is overwritten or lost.
  - The integrity defect is aliasing: the Claude family's version stamp is read through the junction (`dummyindex/installer/install/orchestrate.py:L212-L214`), and it is the same physical `.agents` stamp written moments earlier at `L207-L211`. The two hosts' version records are therefore not independent, and a "coherent" verdict proves nothing. — confirmed

- correctness.md#2 (single-release legacy catalog) — concur — the catalog covers one version only (`dummyindex/installer/legacy_fingerprints.py:L1-L7`; `ownership.py:L112-L116`). Content is fail-closed: the file is preserved and the stamp withheld (`ownership.py:L197-L202`, `L234-L238`). No data loss, but the family never converges and every install exits 1. — confirmed

- correctness.md#3 (sync_family leaves empty dirs) — concur, and adds a consequence — the removal loop unlinks files without any rmdir (`ownership.py:L207-L216`). `family_is_pristine` rejects a directory with no baseline child (`ownership.py:L139-L142`).
  - The new manifest drops the removed names (`ownership.py:L219-L233`), so the empty dirs belong to nothing.
  - `remove_family` only removes parents of files it deletes in the same call (`ownership.py:L282-L294`). Those dirs therefore survive even uninstall, a permanent leak. — confirmed

- correctness.md#4 (editable install reports a stale version) — concur — with `--force-downgrade`, `sync_family` would stamp 0.37 content as `0.36.0` (`ownership.py:L171-L178`, `L234-L238`), which corrupts the provenance record. — confirmed

- correctness.md#5 (`_refresh_meta` overwrites on any difference) — concur — the check is `!=` at `dummyindex/context/build/enriched_refresh.py:L298`, and the version falls back to `"unknown"` at `dummyindex/cli/rebuild.py:L61-L66`.
  - Integrity consequence is limited to provenance: the only readers are `dummyindex/cli/check.py:L244`, `dummyindex/cli/status.py:L107` and the PROJECT.md render at `dummyindex/context/output/docs.py:L189`. Nothing gates on the field, so no artifact gets corrupted.
  - An `"unknown"` overwrite does permanently erase the only record of which build last wrote the index. That is exactly the signal a version-scoped cache fix (data-integrity.md#3) would need. — confirmed (medium → low/medium)

- correctness.md#6 (update skill checks different binaries) — concur — its verify step compares stamps (`dummyindex/skills/update/SKILL.md:L161-L166`), and those stamps can lie per data-integrity.md#4 and correctness.md#5. — confirmed

- correctness.md#8 (no retirement mechanism) — concur — this is the same root as data-integrity.md#5 and #11. I endorse the "delete only git-tracked-and-clean paths" guard, because it keeps every deletion recoverable (`dummyindex/cli/migrate.py:L35-L92`). — confirmed

- correctness.md#9 (/tokens permanently unproven) — concur — the hash is over raw bytes (`ownership.py:L30-L31`), but the source is read with newline translation (`dummyindex/installer/common.py:L257-L259`), so a CRLF copy can never match. Added consequence: `remove_family` deletes the manifest only when baselines are non-empty (`ownership.py:L277-L281`). The `{"complete": false, "files": {}}` manifest therefore stays forever in the user's shared `~/.claude/commands/`. — confirmed

- correctness.md#10 (user CLAUDE.md registration) — concur, and adds an integrity issue — the code rewrites the user-owned `~/.claude/CLAUDE.md` in place with plain `write_text` (`dummyindex/installer/install/orchestrate.py:L390`), with no tmp+rename. A crash mid-write truncates the user's global instructions. `rstrip()` also alters the user's trailing bytes. — confirmed

- correctness.md#7 (PATH shadow detector) — no integrity view.

### over-engineering.md

- over-engineering.md#1 (prune shards) — concur — immediately unlinking every non-referenced shard makes a concurrent reader of the previous manifest fail closed (`dummyindex/export/storage.py:L345-L348`). It never makes it read corrupt data. Keeping only the N-1 generation preserves the reader-can-finish intent (`storage.py:L1-L5`). — confirmed

- over-engineering.md#2 (tree.json compaction) — dispute — two separate problems:
  - **Omitting default keys or deriving stub abstracts breaks the refresh classifier.** `_mechanical_abstract` treats a missing `confidence` as authored (`dummyindex/context/build/navigation_refresh.py:L36-L38`). A missing `abstract` also fails the mechanical grammar (`L56-L72`). Every stub would be treated as authored: obsolete mechanical text carried forward, plus a mass false `source-stale` label (`L133-L153`).
  - **Dropping `indent=2` hurts merges, though no code reader depends on line layout** (all readers parse JSON, `navigation_refresh.py:L30-L33`). tree.json holds authored abstracts, and the design deliberately keeps line-level diffs and merge conflicts (`dummyindex/context/build/runner.py:L362-L368`). A one-line file turns any branch merge of curated abstracts into an all-or-nothing conflict. Two writers exist (`dummyindex/context/build/tree.py:L331`, `navigation_refresh.py:L154-L158`). Changing only one makes the layout flip with every switch between the full-build and refresh paths. — disputed

- over-engineering.md#3 (council/ to cache) — dispute in part — resume reads only `_council-log.json`, `feature.json` and `.hash`, never the draft, notes or critiques (`dummyindex/skills/council/19-resume.md:L7-L12`). Moving critiques and architect notes is therefore safe, but:
  - **(i) "use `git diff` for the plan delta" loses data.** The architect rewrites `plan.md` in place within the same run, with no commit between stages (`dummyindex/skills/council/30-plan.md:L1-L9`). `01-dev-draft.md` is the only copy of the pre-architect draft.
  - **(ii) Deep cross-review would silently lose input if those files are evicted.** Cross-review reads `10-critiques.md` (`dummyindex/skills/council/40-critique.md:L66-L70`), and resume trusts the log, not whether the file exists (`19-resume.md:L36-L43`). If those files sit in an evicted `cache/`, a resumed deep run would cross-review with fewer peers and not notice.
  - `_council-log.json` is already gitignored (`runner.py:L343-L355`). It is written by `dummyindex/context/domains/council.py:L137` and `dummyindex/context/domains/features/ops.py:L325-L336`, so relocating it needs code changes, not just a doc edit. — disputed

- over-engineering.md#4 (coverage.json down to 3 keys) — dispute — the claim "only reader uses 3 of 9 keys" is wrong.
  - `refresh_ownership` reads and rewrites `files[]` to recompute `unassigned` after taxonomy edits (`dummyindex/context/build/coverage.py:L13-L32`). It is called from `dummyindex/context/domains/features/indexes.py:L124-L126`.
  - Without `files` it returns early (`coverage.py:L22-L23`), so `unassigned` (one of the 3 kept keys) goes stale.
  - `excluded`, `pending` and `identity_ambiguities` come from detection and extraction (`coverage.py:L78-L80`). They cannot be regenerated "on demand" without a full extract. — disputed

- over-engineering.md#5 (delete completed proposals) — concur — deletion goes through the guarded, user-confirmed `gc delete`, and tracked workspaces stay recoverable from git (`dummyindex/context/domains/gc/delete.py:L183`). — confirmed

- over-engineering.md#6 (docs.md / supporting.md) — split verdict:
  - **docs.md: concur.** It is a pure pointer projection (`dummyindex/context/domains/features/docs.py:L49-L50`). Its writers must also go: `dummyindex/context/domains/features/builder.py:L187` and `dummyindex/context/domains/features/placement.py:L571-L592`.
  - **supporting.md: dispute.** `merge_feature` copies the merged-away feature's full `spec.md`/`README.md` into it (`ops.py:L253-L263`) and then deletes the source dir (`ops.py:L280`). This repo has 19 "Original notes" blocks across 9 files, each the only working-tree copy of that content. Drift freshness also reads supporting.md (`dummyindex/context/drift.py:L49-L59`), and `supporting` is the only allowed merge section (`ops.py:L230-L234`), so it would simply be recreated. — disputed (supporting.md part)

- over-engineering.md#7 (retired dirs) — concur on equipment-evals; conditional on experiment-notes — those files must be moved, never deleted with `git rm` alone. The README says the source branches were deleted after saving, so these 6 files are the only copy outside git history (`.context/dummyindex-experiment-notes/README.md:L1-L4`). — confirmed (with move-only caveat)

- over-engineering.md#10 (delete .context/INDEX.md) — dispute — a reader exists: the generated docs-specialist lists `.context/INDEX.md` as a mandatory grounding doc (`dummyindex/context/domains/equip/generate/specialists.py:L156-L160`). Deleting it leaves equipped repos pointing at a missing file. No data loss. — disputed

- over-engineering.md#8, #9, #11, #12, #13 (hook, policy, HOW_TO_USE and playbook token cuts) — no integrity view. #12's "render only recent `now.md` sections" is read-only and loses nothing.
