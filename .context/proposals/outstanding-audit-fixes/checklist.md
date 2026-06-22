# Checklist — outstanding-audit-fixes

> Worked wave-by-wave, top-to-bottom. Items in a wave are mutually independent (disjoint files) and dispatch in parallel; a wave starts only when every earlier wave is fully ticked. Tick `- [x]` only after verifying.
> **Updated after the `/dummyindex-audit` meta-audit** (`audits/audit-plan-and-results/report.md`).

## Wave 1 — shared primitives

- [ ] Create `pipeline/io/paths.py` (`resolve_under_root` — accepts already-resolved & not-yet-resolved candidates; `is_safe_read_target`) + re-export from `pipeline/io/__init__.py` + `tests/pipeline/io/test_paths.py`
- [ ] Unify the reality-check atomic writer: retire `reality_check/render.py:_atomic_write` (**3 sites** — `render.py:16-17` in-file, `confidence.py:16` import, `__init__.py:74` re-export), point `render.py` + `confidence.py` at `write_text_atomic`, drop the re-export (existing reality-check tests pass)

## Wave 2 — extraction + cli + reality-check confinement + maintainability

- [ ] Harden the cache (`pipeline/io/cache.py` + `context/build/common.py`): **re-route `cache_dir_override` off the `DUMMYINDEX_CACHE_DIR` env var** onto a trusted in-process channel, then confine the **ambient** env var (silent fallback, never raise; record the user-opt-out policy — `cache.py:47`/`CHANGELOG.md:1095`); accept-superset schema validation (node `id` only, not edges); line-anchored `.md` frontmatter (catches non-bare `---hack`); `sort_keys` on save
- [ ] Harden the extraction walk (`pipeline/extract/__init__.py`): symlink containment **at `collect_files` leaf emission** (walk-time; covers both read sinks; read-time residual documented), `global_label_to_nid` collision disambiguation, `id_remap` immutability
- [ ] Sort `hyperedges` in the graph export (`export/graph.py`) by a **total** key (e.g. `json.dumps(h, sort_keys=True)`)
- [ ] **GATE** Clustering backend determinism (`analysis/cluster.py`) — blocked on the spec Open-questions decision (strategy **(c) confirmed breaking** — `builder.py:76` reads committed `community`; **(b)'s Leiden-spy is vacuous** without graspologic — prefer **(a)**); build escalates to the main session
- [ ] Confine reality-check path resolution (`context/domains/reality_check/verify.py`, `cli/reality_check.py`): gate every `_resolve_cited_path` branch, anchor `repo_root` to the **resolved** git toplevel, reject `--feature` traversal at the CLI boundary, `is_safe_read_target` on reads
- [ ] Fix `query` arg surprises (`cli/query.py`, `cli/help.py`): route existing exit-2 sites through `usage_error`, reject unknown flags, document the no-match exit-1 (**trailing `--top-k` guard already shipped — regression-test only**)
- [ ] Deduplicate `latest_status` into `context/domains/log_scan.py` (`last_matching`); `audit/log.py` + `council.py` call it (resumption tests pass); **quote-rebut-and-remove the two "deliberately NOT extracted" NOTE blocks** (`atomic_io.py` precedent)

## Wave 3 — reality-check mutation/report + perf

- [ ] Atomic confidence mirror (`context/domains/reality_check/confidence.py`): stage-both + replace via `write_text_atomic`, mirror INDEX before popping stash (fix **both** promote `:85-94` and demote `:55-61`), surface no-match (`:108-110`), `sort_keys`; fault-injection test (monkeypatch **`Path.replace`**)
- [ ] Report the `--demote` confidence delta in the CLI (`cli/reality_check.py`) — **widen demote/promote return to `(transition, from, to) | None`** (a bare bool can't carry it) + `sort_keys` on `_reality-check.json` (`render.py`); `capsys` test for all three transitions
- [ ] P2 — read each file ≤2× per build (`pipeline/build/references.py`, `pipeline/extract/generic.py`, `context/build/incremental.py`, **`pipeline/extract/__init__.py`**, **`pipeline/build/structure.py`** — `extract()` must return bytes, `structure.py` passes them through; preserve the `re.escape`+lookahead matcher): thread extractor bytes, resolver consumes cached parse; golden byte-identical + **path-keyed** read-counter (`Path.read_bytes` is shared by all three reads) + mid-build-change test

## Wave 4 — verification + acceptance

- [ ] Run the full suite green (`python -m pytest tests/ -q`) and confirm `symbol-graph.json` rebuilds byte-identically across two post-change rebuilds — via /dummyindex-verify
- [ ] Acceptance: a reality-check citation resolving outside `repo_root` never opens the target (spy on `Path.open`) — **proof strings must be extension-bearing** (`../../secrets.env:1`, absolute `/tmp/x.json:1`); extensionless `/etc/passwd:1` is grammar-rejected (false pass) — keep one as a labelled control
- [ ] Acceptance: `reality-check --feature ../../escape` rejected at the CLI with no out-of-`features/` write
- [ ] Acceptance: an **ambient** out-of-repo `DUMMYINDEX_CACHE_DIR` silently falls back to `<root>/.context/cache/` (never raises) while `cache_dir_override` still targets its dir; a malformed cache entry is re-extracted while a valid existing entry still hits (no mass invalidation)
- [ ] Acceptance: confidence mirror — a raise before the first replace leaves both `feature.json` + `INDEX.json` unchanged; `--demote` prints the confidence delta
- [ ] Acceptance: `query "x" --bogus 5` (unknown flag) exits 2 via `usage_error`; `query "x" --top-k` (trailing, already-fixed) regression-tested; no-match exit-1 documented in USAGE
