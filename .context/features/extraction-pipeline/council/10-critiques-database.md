## Data integrity

- **[HIGH]** `pipeline/io/cache.py:107-121,260-282` + `pipeline/extract/generic.py:60-71,93` + `pipeline/extract/__init__.py:166-172` — the cache key is content-only, but the payload is path-bearing (`source_file = str_path` and file node id `_make_id(str(path))`), so every byte-identical sibling of a file reuses the *first* path's result, and that sibling contributes **zero** nodes, even on a cold first build (the first file saves, the second hits). The duplicate ids then collapse, and `file_status` still reports `"parsed"`.
  - Verified in this repo's committed graph: `detect` returns `dummyindex/context/output/__init__.py` and `tests/cli/__init__.py` (553 code files), but neither has a node. `output/__init__.py` has the same bytes as `context/domains/__init__.py`, and 22 of the 23 tracked empty `__init__.py` have no file node.
  - Scratch repro: identical `pkg_a/mod.py` and `pkg_b/mod.py` leave pkg_b with 0 nodes on run 1. After renaming `a.py` to `b.py`, the graph still emits `a_py` at `a.py`. After moving the repo root, the old absolute path leaks into ids and `source_file` (`normalize_extraction_paths` keeps out-of-root paths opaque).
  - `python_dispatch.py:434-437` (`file_nid not in file_node_ids: continue`) is the same root cause: there the dispatch pass skips the wrong-path payload without any warning. This bullet supersedes the prior dispatch-skip bullet.
  - Fix: key on `sha256(relative_path + "\0" + content)`. Alternatively, on a hit, treat the entry as a miss unless `_make_id(str(path))` is among the cached node ids, or store a path-free payload and rebind `source_file`/ids on load.
  - **Doc conflict (code wins):** `plan.md:57` presents `mv` survival as a design win, and `concerns.md:43` calls the shared entry "fine for reuse". It is a cache hit, but with another file's payload.
- **[HIGH on Windows]** `export/storage.py:209-225` — `_atomic_write` does a bare `temporary.replace(path)` with no `PermissionError` retry. Its two siblings do retry: `cache.py:162-171` and `context/domains/atomic_io.py:55-64`, whose docstring names this exact failure.
  - Reproduced: while a handle opened with the reader's own flags (`storage.py:107-113`) is open on `symbol-graph.json`, `write_graph_payload` raises `PermissionError [WinError 5]`, not `GraphStorageError`.
  - Any overlapping `read_graph_payload` (6 call sites, e.g. `viewer/extras.py:209`, `scan/refs.py:72`) therefore aborts the build after the shards land but before the manifest publishes (`:393-401`). The old generation stays readable, and the new shards linger until a later publish ages them past 600 s.
  - Fix: copy the 6-attempt backoff.
- **[MEDIUM]** `export/storage.py:187-206` — `_shards` packs greedily, in sorted-record order, so a single insert or delete shifts every later boundary in that family, and the reuse/repair path (`:393-398`) almost never fires.
  - Measured on this repo's graph (3 node shards, 9 link shards): dropping the first node and its links reused **0 of 12** shards; dropping one link reused 3 of 12 (only the node shards survived).
  - `symbol-graph.parts/` is committed (not in `.gitignore`), so every graph-changing rebuild adds about 11.4 MB of new blobs to git history. `23f4113` added 79 shards, and the working tree now shows `D` 79 / `??` 12 with no overlap.
  - Fix: content-defined boundaries (cut after a record whose `sha256(id)` low bits match a mask, with the byte cap as a backstop), so one edit churns about one shard per family.
- **[MEDIUM]** `pipeline/io/cache.py:296-311` — `save_cached` writes through a fixed `<hash>.tmp`, so two processes saving the same hash share one tmp file.
  - POSIX: the hazard is when the second process opens the tmp (truncating it) while the first is between `write_text` and `os.replace`. The first then renames that shared inode into `entry` while the second is still filling it, so `entry` can be short. The second's `os.replace(tmp, …)` then finds no tmp and raises `FileNotFoundError`. `except Exception: ... raise` (`:309-311`) re-raises it, and `extract` (`__init__.py:180`) does not catch it, so the build aborts.
  - Windows: the `shutil.copy2` fallback (`:307`) overwrites `entry` in place, non-atomically, so it can copy a half-written tmp. While the sibling still holds the tmp open, the `tmp.unlink` at `:308` probably raises `PermissionError`, which `:309-311` then re-raises, so this path likely aborts too. Untested: only replace-under-reader was reproduced, not writer-vs-writer.
  - Scale: this needs two cold-cache builds overlapping in one checkout, which is most likely right after a version bump wipes the cache (all 553 files miss).
  - Crash-orphaned `*.tmp` files are never swept, because scoping matches only `_ENTRY_NAME_RE` (`:29,217`).
  - Fix: use the module's own `_write_bytes_atomic` (`:144-174`).
- **[LOW-MED]** `pipeline/io/cache.py:195-237` — the version stamp is per directory, not per entry. An older-version `extract` that is still running when a newer one scopes the cache keeps writing entries after the new stamp, and those entries are then reused until the next version change.
  - This is the concurrent-writer scenario that `atomic_io.py:40-41` itself names: two Claude profiles, which may have different installs, sharing one repo-local cache.
  - It contradicts `spec.md:7` ("an upgrade never reuses an older extractor's output").
  - Fix: embed the extractor version in each payload and have `load_cached` (`:260-282`) treat a mismatch as a miss; the stamp then becomes only a fast wipe.
- **[LOW]** `export/storage.py:414-416,439-481,497` — the reader's bounds are controlled by the manifest. The top-level file is read uncapped (`_read_bytes(path)` → `:121` `handle.read()`), and `cap` is the manifest's own `max_file_bytes` (any int ≥ 1), which then bounds every shard read in the loop at `:439-481`, where `result[family].extend(records)` accumulates the records with no total ceiling.
  - Parts are committed, so a cloned repo supplies both the manifest and its shards. `plan.md:75` treats storage paths as hostile input but trusts this field.
  - Fix: use a reader-side ceiling of `min(cap, DEFAULT_MAX_FILE_BYTES)` (or a fixed constant), check `sum(descriptor["bytes"])` before opening any shard, and cap the top-level read.
- **[LOW]** `export/storage.py:288-304` vs `:401-402` — the 600 s grace is measured from shard mtime, not from supersession. With a normal rebuild cadence (more than 600 s apart), the superseded generation's shards are unlinked synchronously right after the new manifest publishes, so the grace protects only concurrent *writers*.
  - Any reader mid-assembly fails closed. A full verified read of this repo's graph takes 0.143 s (12 shards, 9,248 nodes, 26,104 links).
  - The error tells the user to run `dummyindex context rebuild --changed` (`:465-468`), although an immediate re-read would succeed. `plan.md:74` accepts failing closed, but not this false remedy.
  - Fix: in `read_graph_payload`, on a missing shard, re-read the top-level file and retry once if its bytes changed.
- **[LOW, carried forward]** `context/build/communities.py:76-113` — `_pagerank` iterates `list(g)` (`:89`) in insertion order, and its docstring (`:86-87`) makes that order load-bearing for the emitted bytes. Byte stability is inherited from `build_from_json` over sorted node-link data, not enforced locally. The 8-decimal rounding (`:44`) absorbs float noise, not reordering. This bullet was re-verified and is still true (the range moved from `97-126`).

### Resolved since last review

- All seven `b157a1c` fixes were re-verified as still in place:
  - new-dict `id_remap`: `extract/__init__.py:231-250`;
  - ambiguous-label skip: `:282-294,303-304`;
  - single read seam: `cache.py:61-77`;
  - Louvain-only committed path: `cluster.py:67-73`;
  - total-key hyperedge sort, now in the writer: `storage.py:154-164`;
  - `sort_keys`: `cache.py:299`;
  - line-anchored fence: `cache.py:25,101`.
- Shard leak: fixed by `0634bfd`. `_prune_shards` (`storage.py:276-329`) protects `keep | shard_names(live)`, skips links, non-regular files and foreign names, and only warns. A concurrent writer's reused shards survive, because `_touch` (`:395`) runs before the check.
- Dispatch path-shape skip: merged into the HIGH cache-key bullet (same root cause).
- Enum-vs-str `confidence` seam (`export/common.py:7`): stays withdrawn, as agreed in cross-review. Not re-raised.
- Audit trail (code wins): `plan.md`/`spec.md` cite pre-shortening line numbers for `cache.py` and `storage.py`. Examples: the fixed tmp is cited as `cache.py:344` but is now `:297`; `_prune_shards` as `:284-337`, now `:276-329`; the shard repair loop as `:399-406`, now `:393-398`. No catalogued prose doc was quoted.
