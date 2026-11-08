# Audit report — upgrade path for older-version repos + `.context/` bloat

Panel: correctness, data-integrity, over-engineering · mode standard · model opus · round 0 + 2 rebuttal rounds (converged: round 2 only narrowed/withdrew, no live disputes on cuts).

## Executive summary

- The upgrade path cannot retire anything an older version wrote: no versioned retired-path registry exists, and the curated install path (the one `/dummyindex-update` uses) skips even the existing layout/gitignore migrations.
- The single biggest bloat is a writer bug, not curation: `export/storage.py` never deletes superseded graph shards — 79 of 91 committed shard files (73.17 MB) are orphans.
- A product-level integrity bug surfaced beyond scope: the content-only extraction cache key drops or misattributes symbols of byte-identical files, even on a cold build.
- Install can never complete on this machine (Windows junctions read as "unproven") or for any family from ≤0.35.x (legacy catalog covers only 0.36.0).
- Chat-context bloat is real but narrower than first claimed: each host loads one static policy copy; the waste is the hand-kept per-turn reminder, a stale 138-day memory handoff, an uncapped drift report, and a 13 KB HOW_TO_USE.

## Findings — high (confirmed)

1. `dummyindex/export/storage.py:L274-L286` (+ `L239-L241`) — content-addressed shards are never pruned ("Never remove old shards", L285); the ≤1 MB plain-JSON branch orphans every shard. 91 on disk, 12 referenced, 79 orphans = 73,171,940 B, all git-tracked; 66 were already orphans in release commit `23f4113`. Evolve gate copies them twice per candidate. Write ordering is crash-safe (shards before manifest). Fix: after manifest publish, unlink `parts/*.json` not in descriptors (both branches) + one-time sweep on upgrade. — all three auditors.
2. `dummyindex/pipeline/io/cache.py:L106-L126` + `pipeline/extract/__init__.py:L197-L203` — cache key is content-only but payload is path-bound (`id`, absolute `source_file`); second byte-identical file loses its symbols, and `coverage.json` falsely records it `file-only`. Reproduced cold (a/mod.py + b/mod.py). Here: 23 of 65 `__init__.py` missing from the symbol graph. High for general repos (vendored copies, generated clients, monorepo templates); low impact in this repo. Fix: path-free payload re-bound on load, or repo-relative path in key.
3. `dummyindex/installer/legacy_fingerprints.py:L1-L8` — legacy ownership catalog covers only `0.36.0`; families from ≤0.35.x have no baselines, `SKILL.md` always differs (`__VERSION__` render), so `sync_family` preserves → `repair.py:L477-L481` → exit 1 forever. No adopt/override flag (`installer/args.py:L26-L49`). Fix: cumulative per-tag stock-hash catalog or `--adopt-stock` with backup.

## Findings — medium (confirmed)

4. Retired-artifact gap — `dummyindex/cli/migrate.py:L35-L92`, `dummyindex/context/build/enriched_refresh.py:L106-L110`. No `RETIRED_CONTEXT_PATHS` registry; `migrate_legacy_layout`, `ensure_context_gitignore`, `remove_legacy_enrich_plan` never run on the curated install path. `.context/equipment-evals/` (9 files) survives 0.36→0.37 with zero readers. GC can only reach proposals/audits. Constraint: removal must hash-match generated renders — `tests/cli/equip/test_shared_preparation.py:L54-L60` preserves user suites. (merges correctness#8, data-integrity#5/#11, over-engineering#7)
5. Junction link detection — `installer/install/family_write.py:L122-L144`, `installer/link/classify.py:L230-L249`, `installer/ownership.py:L63-L73`. Three divergent "is link" predicates; Windows junctions `~/.claude/skills/dummyindex*` → `~/.agents/skills` read as real unproven dirs for all 10 families → every install exits partial. Junctions were not created by dummyindex (external script, Nov 5) but the inconsistency is dummyindex's. `check --versions` "coherent" after exit 1 and a false "source differs" warning follow (`cli/check.py:L267-L269`, `orchestrate.py:L325-L361`). Fix: one shared predicate incl. `IO_REPARSE_TAG_MOUNT_POINT`.
6. Stamp-before-artifacts — `context/build/enriched_refresh.py:L154-L195`, `context/build/runner.py:L487-L489`. `meta.json` version/`indexed_commit` advance before catalog/graph writes whose failures are swallowed; update verification then passes on a partial refresh.
7. Graph format changed without a schema bump — `export/storage.py:L260-L268`, `context/build/meta.py:L14`. A 0.36 client reading 0.37 `.context/` hard-fails or reads every symbolRef as dangling; a 0.36 refresh orphans all shards.
8. Editable-install version skew — `installer/common.py:L11-L16`. `.venv` dist-info frozen at 0.36.0 while `pyproject.toml:L7` = 0.37.0 → false skew/"source differs", and a venv-run install would treat 0.37 stamps as newer.
9. Update skill uses three different binaries — `skills/update/SKILL.md:L39-L118`. Measures PATH CLI, reinstalls first of uv/pipx/pip, verifies with bare `dummyindex` → never converges or stops early when PATH ≠ updated tool (this machine).
10. PATH-shadow detector — `cli/check.py:L149-L166`, `L311-L344`. Reports a binary shadowing itself (`.exe` suffix), inverts labels, misses the real case.
11. `sync_family` leaves emptied dirs — `installer/ownership.py:L207-L216` vs `L139-L142`. After a full→reference conversion the family is permanently unproven. Reproduced.
12. Unversioned extraction cache (latent) — `pipeline/io/cache.py:L186-L208`. No extractor/package version in key; missing newer fields read as empty. No extractor changed 0.36→0.37, so no wrong output today.
13. `_refresh_meta` overwrites on any difference — `context/build/enriched_refresh.py:L269-L299` (correctness medium / data-integrity low-medium). A stale CLI running the prescribed `rebuild --changed` downgrades the stamp, or writes `"unknown"`.

## Findings — low (confirmed)

14. Curated `tree.json` abstracts can be wiped silently — `context/build/incremental.py:L305-L333`, `context/build/runner.py:L496`. Preserve guard checks features only; `build_all` rewrites the tree with no carry-forward or backup. 2,822 INFERRED abstracts at `cfe6a13` → 0 at squash `376e06d` (event itself unattributable). Severity split: data-integrity medium, correctness low.
15. Config migration drops unknown keys — `context/domains/config.py:L614-L638`.
16. No build lock; fixed `<name>.tmp` siblings — `context/build/maps.py:L292-L296` (+ meta/tree/conventions/config/cache). Contradicts `conventions/data-access.md` line 7 ("unique NamedTemporaryFile").
17. Cache never evicted — 760 entries / 24 MB, 223 dead (`pipeline/io/cache.py:L211-L240`).
18. `/tokens` command permanently unproven despite byte-identical stock — `installer/common.py:L233-L265` (CRLF bytes vs LF-normalized hash, no legacy entry).
19. `~/.claude/CLAUDE.md` registration unmarked, never refreshed or uninstalled — `installer/install/orchestrate.py:L383-L395`; AGENTS.md workflow list omits `dummyindex-fleet`/`dummyindex-evolve` (`context/output/agents_md.py:L44-L46`). Over-engineering prefers deleting the registration outright.
- info: `gc/evolve/<run>/` dirs never removed (`context/domains/evolve.py:L917-L927`); 81 KB today.

## Bloat cuts (confirmed, narrowed in debate)

| # | Cut | Source | Saving |
|---|---|---|---|
| B1 | Prune orphan shards (= finding 1) | `export/storage.py:L285` | −73.2 MB tracked |
| B2 | `tree.json`: omit null `overview_ref`/`detail_ref` + empty `labels`/`evidence`; `indent=0` at both writers; **keep** `abstract`+`confidence` | `context/build/tree.py:L331`, `navigation_refresh.py:L154-L158` | 5.27 → 2.23 MB |
| B3 | Gitignore `features/*/council/*.md` in place; `git rm --cached` 94 files (no relocation) | `context/build/runner.py:L343-L355` | −758 KB tracked |
| B4 | Generate the per-turn reminder from the canonical policy (copies already diverged: "cap lists at five") | `context/output/bootstrap.py:L78-L91`, `context/hooks.py:L110-L143` | drift removed; ~−700 chars/turn if shortened |
| B5 | Memory SessionStart re-injects a 138-day-old `now.md` entry; drift report has no row cap | `context/domains/memory/emit.py:L33-L61`, `context/drift.py:L364-L366` | ~−1K tokens/session |
| B6 | HOW_TO_USE 13 KB → ~6 KB question→path table; HOW_TO_NAVIGATE describes 0 existing flows | `context/output/instructions.py:L87-L135` | ~−2.2K tokens/read |
| B7 | 8 of 12 proposals fully checked, 7 still `planned` (closeout never ran) → `/dummyindex-gc` | `context/domains/proposals/closeout.py:L469` | −123 KB |
| B8 | `docs.md`: drop generic-name matches (`symbol:run` ×42); `INDEX.md`: cap to described entries; `supporting.md`: skip deterministic-stub blocks (keep 3 curated, only copies); `coverage.json` `indent=0`; emit playbooks only on matching dirs | `context/domains/features/docs.py:L131-L136`, `context/output/docs.py:L49-L127`, `context/domains/features/helpers.py:L36-L64`, `context/build/coverage.py:L32`, `context/build/runner.py:L527-L530` | ~−100 KB |

Withdrawn/refuted in debate: 3× static policy duplication (each host loads one copy — Codex reads `AGENTS.md`, `codex_guidance.py:L21-L24`); council → `git diff`/cache relocation; coverage.json key trim (`refresh_ownership` reads `files[]`); `supporting.md` deletion; omitting `confidence`/`abstract` from tree nodes (`navigation_refresh.py:L36-L58`); deleting `dummyindex-experiment-notes/` (user-authored).

## Unresolved disagreements

- Finding 14 severity: data-integrity medium (curated data, no backup, `linguist-generated` hides it in review) vs correctness low (needs enriched-tree + unenriched-features state).
- `coverage.json` `graph_aggregation` key: data-integrity says safe to drop; over-engineering kept only the whitespace cut.

## Conductor notes on the user's proposed fix

- Retired-artifact registry: confirmed and needed, but must (a) run on the curated install path, (b) delete only hash-matched generated content or clean git-tracked paths, (c) include the orphan-shard sweep, (d) report rather than delete anything unproven.
- "Remove `.claude/` and `AGENTS.md`": not supported. Per-repo wiring at `--scope user` is the documented contract (`installer/args.py:L12-L19`), and `AGENTS.md` changed only line endings.

## Lessons

- Applied candidate: tree-node stub contract (see closeout).
- Deferred, convention drift: `conventions/data-access.md` line 17 presents the content-only cache key as a feature (contradicted by finding 2); line 7 claims every writer uses unique tmp siblings (contradicted by finding 16). Owner text left unchanged; needs a curated rewrite.
