## Data integrity

- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** `pipeline/extract/__init__.py` — the `id_remap` pass mutated `n["id"]`/`e["source"]`/`e["target"]` IN PLACE on dicts from `load_cached`, violating the no-mutation convention.
- **Fixed:** the remap builds NEW dicts through list comprehensions: `{**n, "id": id_remap[n["id"]]}` for nodes, and a spread-merge of `source`/`target` for edges.
- Cache payloads are never aliased or mutated. The in-code comment says later passes re-consume them.
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** `pipeline/extract/__init__.py` — `global_label_to_nid` collisions. Two distinct symbols sharing a normalized label collapsed to ONE nid (last node wins).
- So `calls` edges silently resolved to the wrong target.
- **Fixed:** the build loop tracks an `ambiguous_labels` set. A second *distinct* node claiming an existing key marks that key ambiguous.
- The call-resolution loop SKIPS ambiguous callee keys. It never binds to an arbitrary node.
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`] (P2 single-read invariant)** `pipeline/extract/__init__.py` / `resolve.py`.
- On a cached re-run, the resolver re-read and re-parsed every `.py`/`.java` from disk. A file changed after its cache entry was written gave the resolver NEW bytes against STALE nodes.
- **Fixed:** all source-byte reads funnel through one `read_source_bytes(path)` seam. It covers the hash read in `cache.py` and the extractor read in `generic.py`.
- It also covers the Python rationale post-pass and the resolver re-reads in `resolve.py`. `build_read_cache()` memoizes that seam per `extract`, so every pass sees one byte-state. No stale-node/new-byte mix remains.
- _Residual (open, by design): the read cache is build-scoped and cleared on exit. A file mutated **between** builds is correctly re-read next build. This fix narrows the window to one build, not across builds._
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** `analysis/cluster.py` — committed `community` was byte-stable only if graspologic presence stayed constant. Leiden and Louvain produce different partitions.
- **Fixed (GATE strategy (b), recorded `spec.md` 2026-06-23):** the committed path (`cluster` → `_partition` → `_split_community`) calls **only** `_louvain_partition`. That is NetworkX-Louvain: pure-Python, always present, seeded.
- `_leiden_partition` is split out and never feeds committed bytes. It stays available off-path, for on-demand use.
- No new hard dependency on graspologic. Committed `community` is reproducible on any machine. Docstrings match.
- _Note: forces a one-time `community` rewrite in committed `.context/` on next rebuild. Expected, not a regression._
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** `export/graph.py` — `data["hyperedges"]` was copied by reference and never sorted.
- **Fixed:** hyperedges sort by a **total** key, `json.dumps(h, sort_keys=True)`. A single field is insufficient, because the hyperedge schema is open.
- The sort applies at **both** emission sites: top-level `data["hyperedges"]` and the `data["graph"]["hyperedges"]` copy that `node_link_data` carries over from `G.graph`.
- _Note: also a one-time committed-bytes change on next rebuild if any hyperedge exists._
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** `io/cache.py` — `save_cached` wrote `json.dumps(result)` without `sort_keys`. Cache-entry bytes depended on insertion order. The cache is not committed, so this was hygiene only.
- **Fixed:** it now writes `json.dumps(result, sort_keys=True)`.
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** `io/cache.py` — `_body_content` stripped `.md` frontmatter with `text.find("\n---", 3)`. That matched the FIRST `\n---` in the body, such as an in-prose `---hack`.
- The hashed body was silently truncated, which caused false cache hits.
- **Fixed:** the closing fence is a line-anchored regex, `_FRONTMATTER_FENCE_RE = ^---[ \t]*$` (MULTILINE), searched only after the opening fence.
- A non-bare `---hack` no longer truncates the body. A frontmatter file without a closing fence still hashes whole-file, with no regression.
- `dummyindex/context/build/communities.py:97-126` — **seed-rank byte-stability is inherited from graph insertion order, not enforced locally.**
- `_pagerank` walks `list(g)` in insertion order. Its docstring says float summation order sets the emitted `seed-rank.json` bytes.
- Today the graph always comes from `build_from_json` over sorted node-link data, so order is deterministic.
- An alternate graph construction, or a NetworkX change to node-ordering semantics, would silently churn committed bytes. Neither change touches this module.
- The 8-decimal rounding (`_SCORE_DECIMALS`) absorbs float noise, not ordering changes. A seam to watch, same spirit as the enum/str note below. Not a live bug.
- `dummyindex/pipeline/extract/python_dispatch.py:458-462` — **the dispatch post-pass silently skips a file whose cached result is keyed to another path shape.**
- The check is `file_nid not in file_node_ids`. A cache entry written under another cwd or absolute-vs-relative path triggers it.
- The design is precision-first ("no guessing"). Dispatch edges can be absent on a cached re-run but present on a cold run, if path shapes differ.
- The per-edge determinism test (`test_dispatch_edges_deterministic_across_cached_rebuilds`) covers only the same-path-shape case.
- `dummyindex/pipeline/build/structure.py:354` / `dummyindex/export/common.py:7` — `_filter_cross_edges` defaults a missing `confidence` to the `ConfidenceLevel.EXTRACTED` enum.
- Cache-roundtripped edges carry the bare string `"EXTRACTED"`. Both serialize identically. `_CONFIDENCE_SCORE_DEFAULTS.get` works under `(str,Enum)` equality.
- So this is NOT a live bug. It is a type-drift seam to watch, if the enum ever stops subclassing `str`.

## Security

- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** `cache.py` + `extract/__init__.py` — **cache poisoning and unvalidated deserialization of graph content.**
- `load_cached` returned the parsed `{hash}.json` verbatim into the committed graph, with zero schema validation.
- **Mitigated (defense in depth):** (1) **cache-dir confinement** is now the load-bearing containment. The ambient `DUMMYINDEX_CACHE_DIR` is confined under the repo root (see next item).
- An attacker can no longer redirect cache reads or writes to a poisoned out-of-tree store.
- (2) `load_cached` applies an **accept-superset schema guard** (`_is_valid_cache_payload`). It returns a MISS on a non-dict payload, a non-list `nodes`/`edges`, or a node lacking a string `id`.
- The caller re-extracts and never merges. The guard is **anti-corruption, not anti-poisoning**. A well-formed but adversarial graph still passes. The real containment is the dir confinement.
- _Residual (open, documented): in-repo self-poisoning via a SHA256-colliding file remains theoretically possible. Content addressing only prevents forging another file's result. The schema guard bounds shape, not content. Accepted per the proposal._
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** `cache.py` — **`DUMMYINDEX_CACHE_DIR` was `.resolve()`'d but otherwise unvalidated.**
- **Fixed (cache trust-channel split):** `cache_dir()` has two channels with different trust levels.
- (1) The **trusted in-process** override (`_TRUSTED_CACHE_DIR`), set by `cache_dir_override` → `set_trusted_cache_dir` in `context/build/common.py`, is honored unconditionally. It never carries untrusted input.
- It no longer flows through the env var, and no longer mutates the user's environment.
- (2) The **ambient** `DUMMYINDEX_CACHE_DIR` env var is confined to the repo root via `resolve_under_root`. An out-of-repo, `../`, or absolute-join value is **silently ignored**.
- It falls back to `<root>/.context/cache/` and never raises (`test_cache_env_var_is_restored`).
- **Opt-out policy recorded:** `DUMMYINDEX_CACHE_DIR` is **preserved, not deprecated**, but now confined.
- _Note: the original framing ("`cache_dir_override` survives via `cache_root`") was inverted. The override set the env var, which beat the threaded root. The fix moves it off the env var._
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`] (walk-time; read-time residual documented)** `extract/__init__.py` — **symlink escape outside repo root under `follow_symlinks=True`.**
- A crafted repo with `evil -> /home/user/.ssh` was walked. Its files went to extractors and `_read_text_safely`, disclosing out-of-tree content into the committed graph.
- **Fixed:** `collect_files` computes a `containment_root` (explicit `root`, else `target`) and **filters at leaf emission**.
- A leaf whose `os.path.realpath` escapes the root, via `resolve_under_root`, is dropped. This happens before either read sink (the cache-hash read in `cache.py` or the extractor read in `generic.py`) touches it.
- _Residual (open, by design): this is **walk-time** containment only. A post-enumeration symlink swap (TOCTOU) replaces a vetted leaf with an escaping symlink between emission and read. That swap is a documented residual.
- A true read-time guard would live in `generic.py` and is deferred. `is_safe_read_target` (`paths.py`) is the primitive for it. It is not yet wired into the extractor read path._
- `references.py:106-125` — **ReDoS in the single-pass matcher: NOT exploitable. The mitigation is load-bearing.**
- Every needle is `re.escape`'d. Needles are rel-paths plus fallback basenames from arbitrary repo paths.
- The alternation is wrapped only in a **zero-width lookahead** `(?=(...))`, with no outer `+`, `*`, or `{}` quantifier.
- Escaping kills attacker metacharacters. The lookahead-without-quantifier shape has no catastrophic-backtracking structure, even with hundreds of long common-prefix needles.
- Verified empirically: 500 × 200-char prefix-colliding needles over a 100 KB text scanned in ~0.1 s. Keep both the escape and the lookahead-only construction.
- `io/git.py` (whole module) — **subprocess injection: not present. This is a genuine hardening win.**
- All git "detection" is pure-filesystem. `is_git_repo`, `resolve_git_dir`, and `submodule_paths` read `.git`, `commondir`, and `.gitmodules` through configparser.
- **No `subprocess`, `os.system`, or shell call exists.** So no command-injection surface exists from crafted branch names, `gitdir:` pointers, or `.gitmodules` `path=` values.
- Residual: `resolve_git_dir` and `submodule_paths` return `.resolve()`'d paths. Attacker-controlled `gitdir:`, `commondir`, or `path` content can point **anywhere on disk**.
- Hook-scrubbing callers outside this feature consume them. A containment check belongs at that call site, not here.
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`] (re-noted, plan Open-Q)** `extract/resolve.py`.
- On a fully cached run, the Python and Java cross-file resolvers re-read and re-parsed every `.py`/`.java` from disk.
- So untrusted bytes were touched a **second** time, independent of cache state.
- **Fixed (P2):** resolver reads route through `read_source_bytes` inside the same `build_read_cache()` block as the per-file pass.
- Within one build, a file's bytes are read once and reused. The resolver no longer issues an independent disk read.
- _Residual: walk-time symlink containment (above) is the surviving boundary. The resolver adds no second untrusted-byte read._

## Product surface

- Empty repo / no source files — `extract([])` sets `root = Path(".")`, runs zero per-file work, and returns `{"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}` (`extract/__init__.py:136-137,244-249`).
- `cluster()` short-circuits on an empty graph to `{}` (`cluster.py:73`). There is no error and no "nothing to index" message.
- A caller pointing at an empty or wrong directory gets a silent empty graph, not a warning. Gap: no signal distinguishes "empty repo" from "wrong path".

- Repo with only unsupported extensions. Every path hits `extractor is None` and is `continue`d (`extract/__init__.py:161-162`).
- The result is the same silent empty graph. A caller with, say, an all-Haskell or HTML repo gets no list of skipped files. Gap: no "0 of N files were extractable" notice.

- Sub-100-file repo. Progress printing is gated on `total >= _PROGRESS_INTERVAL` (100) (`extract/__init__.py:155,171`).
- On a 60-file repo, nothing prints during the structural pass.
- This matches the prompt's "no progress on sub-100-file repos." Gap: no per-stage heartbeat for small repos.

- Huge repo. Extraction is one serial `for` loop over all paths (`extract/__init__.py:154-170`). It has no parallelism, batching, or memory cap.
- The full `all_nodes` and `all_edges` lists sit in memory. The whole graph is serialised at once (`graph.py:42-43`).
- No handler caps graph size or streams output. Gap: no degradation strategy for very large repos beyond the 100-file progress counter.
- The progress meter hints at scaling to large repos. The loop does not deliver it.

- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** graspologic-vs-Louvain partition divergence. Committed `community` was cross-machine stable only when graspologic presence stayed constant.
- **Fixed (GATE strategy (b)):** the committed path is now always NetworkX-Louvain (`_louvain_partition`, pure-Python, always present). Leiden (`_leiden_partition`) is split off-path and never feeds committed bytes.
- Two callers, with or without graspologic, now produce identical `symbol-graph.json` communities. The determinism guarantee is cross-machine, not merely per-backend.
- See the matching Data-integrity and Cross-review entries.

- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`]** `cluster()` docstring versus behavior. Docstrings claimed "Run Leiden" and "best quality", with no mention of the fallback.
- **Fixed:** the module and the `cluster`/`_partition`/`_split_community`/`_louvain_partition` docstrings now say committed `community` comes from NetworkX-Louvain only (GATE strategy (b)).
- They also say Leiden is off the committed path. Docs match code.

- Full-repo re-hash on every `--changed`. `rebuild_changed` (`dummyindex/context/build/incremental.py:64`) runs `detect()`.
- Then `_hash_files` reads every tracked code and doc file to diff against the manifest (`incremental.py:99-133,330-344`). This happens before any cache reuse.
- So even a one-line edit re-reads and SHA256s the entire repo. The per-file extraction cache skips unchanged AST work, but the hashing cost is unavoidably O(repo).
- Gap: hidden full-disk-read cost on every incremental run. "Incremental" describes the rebuild, not the change detection.

- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`] (P2)** Files were read multiple times per build. A `.py` was read for the structural pass, or served from cache.
- It was read again by `_resolve_cross_file_imports` and by the textual-reference pass. The `--changed` hash added another read. That made three or more touches.
- **Fixed:** all in-build source reads route through one `read_source_bytes` seam, memoized by `build_read_cache()`.
- `extract` threads the bytes out via `file_bytes`. The textual-reference pass (`_text_for_scan` in `references.py`) decodes those instead of re-reading.
- Each source file is now read **at most twice** across the whole build. The in-build read counts, plus the separately-counted `--changed` hash in `incremental.py`, which the in-build count excludes.
- _Residual (open, separate concern below): the `--changed` full-repo re-hash is a distinct O(repo) cost. P2 does not address it._

- Cache is never garbage-collected. Entries are content-addressed `<sha256>.json` and only ever written (`cache.py:80-108`).
- Editing leaves the old hash's entry on disk forever, so `.context/cache/` grows without bound.
- Gap: no eviction or prune surface. A churny repo accumulates stale files with no cleanup command.

- Cache key ignores path. `file_hash` hashes content only, and `root` is vestigial (`cache.py:20-40`).
- Byte-identical files at different paths share one entry, which is fine for reuse.
- `.md` frontmatter is stripped before hashing (`cache.py:10-17`). So a Markdown edit that changes only frontmatter is a cache hit and a no-op, by design.
- But a caller editing frontmatter, expecting a re-index, sees "no source files changed."
- Gap: a silent no-op on frontmatter-only edits is correct by design, but surprising.

- **Test-file down-weighting in the seed rank is a filename heuristic with no knob.** `_personalization` (`dummyindex/context/build/communities.py:187-197`) weights test files at `_TEST_WEIGHT = 0.1`.
- Entry points weigh 3.0, and ordinary source weighs 1.0. Test-ness comes from the name-based `_is_test_path` (`communities.py:219-231`).
- It matches a `tests`, `test`, `__tests__`, or `testing` directory part. It also matches a `test_*`, `test-*`, `*_test`, `*-test`, `*.test`, `*.spec`, or `conftest` stem.
- This is deliberate. The bakeoff showed test nodes drown the raw degree signal.
- Yet a repo whose code lives under `testing/`, or whose stems look test-like, gets its seed rank suppressed ~10×.
- No config surface adjusts the weights or the heuristic. Misclassification is invisible. `seed-rank.json` does not record which nodes were down-weighted.

- Dispatch-idiom pass degrades silently. `_resolve_python_dispatch` returns `[]` when `tree_sitter_python` is missing.
- Per file, it skips unparseable files and path-shape-mismatched cached results (`python_dispatch.py:455-465`).
- The `extract()` wrapper logs a warning only on an outright exception (`extract/__init__.py:219-226`).
- A caller gets a graph without dispatch edges and no signal for the quiet skips. Fits the "partial graphs look complete" gap.

- Parse failure is silent per file. A file that fails to parse returns an `error` result, not cached, with no nodes or edges. The loop continues (`extract/__init__.py:167-170`).
- Cross-file resolution failures degrade to a logged WARNING (`extract/__init__.py:205-206,213-214`).
- The caller gets a silently incomplete graph, with no summary of dropped files. Gap: no end-of-run report of skipped or errored files. Partial graphs look complete.

- tree-sitter too old or missing. `_check_tree_sitter_version` raises a clear `ImportError` or `RuntimeError`.
- The error includes the exact pip command, before any work (`extract/__init__.py:61-75,132`). The one boundary that fails loud and actionable. No gap.

- Bare `rebuild` on a curated index. It refuses with exit 2 and points at `--full` / `--changed` (`rebuild.py:76-86`).
- `--full` warns that it discards taxonomy (`rebuild.py:38-45`). These are clear, scriptable guardrails. No gap.
- But the warning is stderr-only. A caller piping stdout will not see why nodes or communities changed.

## Ownership & coverage

- `dummyindex/context/build/` was previously **feature-orphaned**: no curated feature owned its files, so drift surfaced through no reconcile.
- As of the graph-consumption upgrade (`1921bbf`), this feature owns `dummyindex/context/build/communities.py` (+ `tests/context/build/test_communities.py`).
- It consumes this feature's graph directly and shares its determinism contract.
- The wiring hosts remain unowned: `context/build/graph.py` (`build_graph` → `write_graph_artifacts`), `enriched_refresh.py`, `runner.py`, `incremental.py`, and the other `context/build/` siblings.
- They belong to no feature. Changes there keep bypassing feature-level reconcile until a feature claims them.

## Cross-review notes

- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`] Consensus (security + product): graspologic-vs-Louvain partition divergence.** Closed via GATE strategy (b).
- The committed `community` is now always NetworkX-Louvain (`_louvain_partition`). Leiden is off-path. Determinism holds regardless of graspologic presence.
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`] Consensus (database + security): unvalidated cache re-entry + unconfined `DUMMYINDEX_CACHE_DIR`.** Both halves of the agreed mitigation landed.
- `load_cached` applies an accept-superset schema guard (`_is_valid_cache_payload`) before a payload joins the graph.
- The ambient `DUMMYINDEX_CACHE_DIR` is confined under the repo root via `resolve_under_root`. The trusted in-process override is split off the env var.
- _Residual: in-repo self-poisoning via SHA256 collision remains theoretically possible. The dir confinement is the load-bearing containment. The schema guard bounds shape, not content._
- **[RESOLVED — `b157a1c`, branch `fix/outstanding-audit-fixes`] Security-only, accepted by DB on review: `follow_symlinks=True` leaf containment.** A `resolve_under_root` realpath-under-root check now filters escaping leaves at `collect_files` emission.
- _Residual: walk-time only. A post-enumeration TOCTOU swap is documented as out of scope. `is_safe_read_target` is the primitive for a future read-time guard._
- **Withdrawn / not-a-bug (recorded so it is not re-raised): the `confidence_score` enum-vs-string lookup (`dummyindex/export/common.py:7`, `dummyindex/pipeline/build/structure.py:354`).**
- The DB critic flagged it as a type-drift seam and confirmed it is **not** a live bug. `ConfidenceLevel` subclasses `str` (`pipeline/enums.py`).
- So the round-tripped string still hits the enum-keyed dict. This matches the audit finding that withdrew it. Revisit only if the enum stops subclassing `str`.
- **ReDoS in the new single-pass `references.py` matcher: actively defended, verified.** Security empirically confirmed (500×200-char prefix-colliding needles, ~0.1s) that `re.escape` + zero-width-lookahead-without-quantifier gives no catastrophic-backtracking structure.
- Keep both. Not a finding.
