# Audit report — docs drift / dead code / performance / logical misses

**Panel:** correctness, maintainability, performance, architecture (+docs-drift).
**Mode:** deep — Round 0 (independent) → Round 1 (rebuttal, converged) → adversarial refutation pass (2 independent skeptics).
**Model:** opus-4.7.

## Executive summary

The codebase is structurally healthy: the stated layering invariants (`context → analysis → pipeline`, `cli` as a one-directional sink) **hold in the actual imports**, and the documented architecture spot-checks accurate. The real issues cluster in three places: **(1) two genuine determinism gaps** that can churn the committed `symbol-graph.json` between runs, **(2) stale docs in the `cli-dispatch` feature** (one undocumented verb cascading into an off-by-one member count and a false "removed" claim), and **(3) one true dead exception type** plus a handful of cold-path performance smells.

- **Confirmed:** 18 findings (2 high, 6 medium, 10 low) — all survived two adversarial skeptics with zero refutations.
- **Withdrawn/refuted in debate:** 1 substantive (a false "confidence collapses to 1.0" determinism claim — its premise was wrong) + 4 info-level near-non-issues.
- **Unresolved disputes:** none. The panel reached full agreement.
- **Headline risks:** non-deterministic community IDs + unsorted graph JSON (committed-artefact reproducibility), and `cli-dispatch` docs that misstate the command surface.

---

## Confirmed findings (ranked by severity)

### HIGH

- **C2 — non-deterministic community IDs** · `dummyindex/analysis/cluster.py:31-48, 103-104`
  `leiden(G)` is called with **no `random_seed`** (the Louvain fallback at `:48` *does* seed `42`), and the community-ID relabel `final_communities.sort(key=len, reverse=True)` (`:103`) is **length-only** — equal-size communities take partition-dependent order. The docstring promises "Community IDs are stable across runs," which the code does not deliver. Churns the `community` field of the committed `features/symbol-graph.json`.
  *Fix:* pass a fixed `random_seed` to graspologic `leiden`, and add a content tiebreak, e.g. `key=lambda c: (-len(c), sorted(c)[0])`.

- **C3 — graph JSON written with no ordering guard** · `dummyindex/export/graph.py:23-38`
  `to_json` does `json.dump(data, f, indent=2)` with **no `sort_keys`**, and `data["nodes"]`/`data["links"]` come straight from `node_link_data(G)` with no pre-sort. Any upstream reorder (incl. C2) silently rewrites the committed graph; no test catches it. Determinism is an architectural invariant here (committed `.context/` is meant to be byte-reproducible), so this compounds C2.
  *Fix:* sort `nodes` by `id` and `links` by `(source, target, relation)` before dump; pass `sort_keys=True`.
  *(Note: severity is medium per the perf/maintainability lanes but it is the enabling defect behind the high-severity C2 churn — treat C2+C3 as one determinism fix.)*

### MEDIUM

- **A1 — `cli-dispatch` docs understate the enum** · `.context/features/cli-dispatch/spec.md:56`, `plan.md:43,90`
  Docs say `ContextSubcommand` is "a `str, Enum` of 39 members"; the live enum has **40** (verified: `dummyindex/context/enums.py:47-86`). *(Round 0 mis-counted this as 43; the correct delta is 39→40.)* Same root cause as A3 — the off-by-one is the undocumented `HOOKS` verb.
  *Fix (curated doc):* update the four doc sites to "40 members" / "39 others".

- **A2 — `cli-dispatch` spec claims live modules were removed** · `.context/features/cli-dispatch/spec.md:16-18`
  Spec states `context/domains/council.py` and `dev_pick.py` "were removed from the cluster." Both exist on disk and are **actively dispatched** (`cli/__init__.py:102` `COUNCIL_LOG→council.run`, `:110` `DEV_PICK→dev_pick.run`; `cli/council.py:16`, `cli/dev_pick.py:15`). The claim is provably false against the code.
  *Fix (curated doc):* rewrite the sentence to reflect that both are present and dispatched.

- **A3 — `hooks` subcommand entirely undocumented** · `dummyindex/cli/__init__.py:88`, `dummyindex/context/enums.py:51`
  `ContextSubcommand.HOOKS` (handler `cli/hooks.py`, an install/uninstall/status/defer-check verb) is a real member of the CLI alphabet but appears nowhere in `cli-dispatch` spec/plan prose or examples. This is exactly what the SessionStart drift hook flagged on `cli/hooks.py`.
  *Fix (curated doc):* add `hooks` to the spec's enum/handler description and an example line.

- **M1 — `WireError` is a dead exception type** · `dummyindex/context/domains/equip/errors.py:33`
  Defined and re-exported (`equip/__init__.py:42,161`) but **never raised or caught** anywhere in `dummyindex/` or `tests/` — confirmed by repo-wide grep incl. dynamic `getattr`/`importlib` and the `skills/*.md`. A maintainer will write `except WireError` handlers that can never fire; the `equip/wiring/*` path it was meant to cover raises nothing.
  *Fix:* delete it (and the re-export), or wire it into the wiring-failure path it was designed for.

- **P1 — O(F²) textual-reference scan per full build** · `dummyindex/pipeline/build/references.py:54-79`
  For every effective file it loops over every *other* file's rel-path doing `text.find(tgt_rel)` (F×F), with a basename fallback. Called unconditionally at `structure.py:120` on every `build_all` / enriched refresh. *Correctly does NOT run on the frequent `--changed` no-op path* (`incremental.py:135-136` returns `skipped=True` first), which is why it's medium not high — but this tool indexes arbitrary repos that may have thousands of files.
  *Fix:* build one combined automaton (Aho-Corasick / regex alternation) of all rel-paths+basenames and scan each file once (O(F·text)). *Trade-off flagged by maintainability:* a trie is harder to read than `tgt in text` — gate the rewrite behind golden-output tests so `source_location` offsets/precedence don't shift.

- **P2 — same files read & decoded 3× per build** · `dummyindex/pipeline/build/references.py:99-111`, `pipeline/extract/generic.py:42`, `context/build/incremental.py:330-344`
  In one `build_all`, each source file is read three times: `load_cached`→`file_hash`→`read_bytes` (`io/cache.py:38`), the AST extractor `read_bytes` (`generic.py:42`), and the reference scan `read_text` (`references.py:109`). On the `--changed` path `_hash_files` adds a **4th** read. None is short-circuited. *(Citation nuance: on a cold full build read #1 is `load_cached`'s hash, not `incremental._hash_files`.)*
  *Fix:* thread the bytes read during extraction into the reference pass / hash from already-loaded bytes — but honor each consumer's size cap and `errors="ignore"` decode mode (correctness caveat).

### LOW

- **C4 — trailing `--top-k`/`--budget` with no value is silently swallowed** · `dummyindex/cli/query.py:32-62` — falls through to `else: leftover.append(a)` and gets joined into the query string instead of raising a usage error; inconsistent with the explicit integer-validation error when a value *is* present. *Fix:* add a catch-all that emits `usage_error`/exit 2 for a missing value.
- **C5 — dead constant `_SELF_GATE_LINE`** · `dummyindex/context/hooks.py:184` — `_SELF_GATE_LINE = _SILENT_GATE` is the sole occurrence; the live logic uses `_GATE_VARIANTS`. *Fix:* remove.
- **M2 — `require_clean_tree` dead wrapper** · `dummyindex/context/domains/doc_reorg/safety.py:57-78` — advertised as THE dirty-tree gate but the CLI `guard` re-implements the check inline with `git_is_clean` (`cli/doc_reorg.py:51-60`); only tests call the wrapper. Two paths over one primitive can drift. *Fix:* call `require_clean_tree` from the CLI, or drop it.
- **M3 — `superproject_root` test-only** · `dummyindex/pipeline/io/git.py:87-105` — implemented + 6 tests, zero production callers. *Fix:* wire into the submodule path it was built for, or remove.
- **M5 — duplicated `latest_status` log-scan** · `dummyindex/context/domains/audit/log.py:166-172` & `council.py:332-340` — identical last-write-wins loops differing only in key fields; the council copy is load-bearing for resumption. *Fix (optional):* extract a shared `last_matching` helper.
- **M6 — three files exceed the stated 600-line "must split" threshold** · `reality_check.py` (695), `pipeline/extract/generic.py` (650), `output/viewer.py` (637) — the repo's own table (`docs/reference/01-conventions.md:331-337`) makes >600 a hard "must split", >800 only a soft smell, so all three are true deviations. `reality_check.py` (4 concerns: extract/verify/render/promote-demote) is the strongest split candidate; `viewer.py` is mostly an HTML/JS template string (lower real risk). *Fix:* split `reality_check.py` along its seams.
- **P3 — `query` re-parses `map/symbols.json` per top-K match** · `dummyindex/context/domains/query.py:386-466` — K full loads/scans per query. Downgraded to low: at default `top_k=3` the in-code comment is a deliberate "wins small at K=3" trade, not stale. *Fix (optional):* parse once in `query()` and pass down.
- **P4 — `_score_feature` symbol-hit loop** · `query.py:296-305` — O(features×symbols×tokens), cold per-invocation path, small magnitudes. *Fix:* none unless counts grow 10×.
- **P5 — quadratic tree assembly** · `dummyindex/context/build/tree.py:139-146` — filters the full `dir_paths`/`file_id_by_path` per directory node (~O(dirs×(dirs+files))), cold path, tiny constant today. *Fix:* pre-bucket by immediate parent.
- **P6 — full-repo rehash on `--changed` no-op** · `dummyindex/context/build/incremental.py:330-344` — SHA256s every file even when nothing changed. *Fix (optional):* mtime/size pre-filter, hash only movers.
- **A8 — leaky private-name sibling import** · `dummyindex/cli/reconcile_gate.py:12` — imports two **underscore-private** names (`_read_hook_stdin`, `_resolve_transcript`) from a sibling, unlike the three documented public-entrypoint sibling imports. *Fix:* promote the two helpers to a public name (e.g. in `cli/common.py`) if the reuse is intended.

---

## Withdrawn / refuted in debate (recorded so they aren't re-raised)

- **C1 (was high) — WITHDRAWN.** Claimed a cache-hit collapses every edge `confidence_score` to `1.0` because a JSON-round-tripped string misses the enum-keyed dict. **Premise is false:** `ConfidenceLevel` is a `(str, Enum)` (`pipeline/enums.py`), so the string `"AMBIGUOUS"` still hits the enum key and returns the correct `0.2`. The "confirmed in concerns.md" citation was a stale-doc echo. *(C2's docstring-over-promise sub-point survives as part of C2.)*
- **C6 / C7 (info) — not actioned.** Tab-in-path truncation (`git_delta.py:225`) is exotic; `read_manifest` KeyError (`manifest.py:133`) only triggers on a hand-corrupted gitignored cache file and merely aborts a rebuild.
- **P7 / P8 (info) — correct as-is.** The two-phase AST re-walk is cache-shielded; the 2 git subprocesses per reconcile are the correct cheap choice.
- **A5 (info) — benign.** The `tree-enrich` drift flag on `tests/cli/test_hooks_cli.py` is the already-documented test-cluster membership noise, not real doc-vs-code divergence.
- **A6 / A7 / A9 (info) — verified healthy.** Layering invariants hold (no lower→higher imports; `cli` never imported by `context/domains`), and every `path:range` citation in the `cli-dispatch` docs verifies. Good news, recorded.

---

## Suggested follow-up (separate plan → build cycle; this audit is read-only)

1. **Determinism fix (C2+C3)** — seed Leiden + content tiebreak + sorted graph JSON, guarded by a golden-output test. Highest value: protects the committed-artefact reproducibility contract.
2. **`cli-dispatch` doc reconcile (A1+A2+A3+A4)** — single curated-doc edit pass (the `HOOKS` verb is the root cause of A1+A3). Use the reconcile procedure, then `reconcile-stamp`.
3. **Remove dead code (M1, C5)** — delete `WireError` + re-export and `_SELF_GATE_LINE`; decide M2/M3 (wire-in or remove).
4. **Performance (P1, P2)** — automaton-based reference scan + shared byte cache, behind golden-output tests.
5. **Split `reality_check.py` (M6).**
