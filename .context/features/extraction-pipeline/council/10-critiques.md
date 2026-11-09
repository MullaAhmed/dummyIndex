# extraction-pipeline — raw critiques (deep mode)

<!-- critic: database -->

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

<!-- critic: security -->

## Security

_Ranges are working-tree (comment-shortened) lines, re-verified by grep this run. `plan.md`/`spec.md` ranges are pinned to `0634bfd` and are now off by ~10–30 lines. For example, `scope_cache_to_version` moved from `cache.py:225-279` to `:195-237`, and the `save_cached` tmp line from `:344` to `:297`. Probes ran in the scratchpad on Windows / Python 3.12.14._

- **[high] `dummyindex/pipeline/io/cache.py:285-311` (`save_cached`): the tmp write follows a pre-existing path.** `tmp = entry.with_suffix(".tmp")` (`:297`) is a fixed, predictable name, and `tmp.write_text(...)` (`:299`) opens it without `O_EXCL`/`O_NOFOLLOW`. A hostile repo can commit `.context/cache/<sha256-of-its-own-file>.tmp` as a link. On the victim's first build that file misses the cache, so the write truncates and overwrites the link target, which can be any user-writable file outside the repo, with extraction JSON. The Windows fallback `shutil.copy2(tmp, entry)` (`:307`) also writes through a link at `entry`. Probe: a hard link at the tmp name had its outside target overwritten. A symlink could not be tested here (WinError 1314), but POSIX git checkouts materialize committed symlinks by default. The planted file survives scoping, because `scope_cache_to_version` only deletes `<64hex>.json` (`:217`). It is also not caught by `validate_context_destination` (`context/build/scope.py:14-35`), which lstat-checks directories only. Existing mitigation: none. The plan's open question frames this as concurrency only. Fix: write through `_write_bytes_atomic(entry, …)` (`cache.py:144-174`: unique `NamedTemporaryFile` + `os.replace`, never opens an existing path), which already has the Windows retry, and delete the `copy2` fallback.

- **[high] `cache.py:195-237` + `:240-282` (`scope_cache_to_version`, `_is_valid_cache_payload`, `load_cached`): a hostile checkout can poison the cache, and the version stamp can be forged.** The confined cache dir is the repo's own `.context/cache/`, so "dir confinement is the load-bearing containment" (`plan.md` Key decisions; `concerns.md` Security item 1, marked RESOLVED) does not hold against a hostile repo. The `.context/.gitignore` `cache/` rule (`context/build/upgrade.py:29-30`) only stops accidental commits; checkout materializes tracked files anyway. The attack needs no SHA-256 collision, since the attacker authors both the file and `<sha256(file)>.json`. A committed `extraction-version` that equals the running release makes scoping delete nothing (`:209-210`). Probe: 0 deleted, planted entry survived. The entry then loads instead of a parse, so committed `symbol-graph.json` can hide real symbols or carry `label`/`source_file` strings that are not identifier-constrained into `.context/` and agent context. The guard checks only node `id`. Non-dict edges, or edges missing `source`/`target`/`relation`, crash the build at `pipeline/extract/__init__.py:209-211,296`. A `raw_calls` item without `caller_nid` crashes it at `:306`, and a non-str `label` at `:286`. `spec.md` ("foreign-shaped entry is a miss … never a partial merge") is contradicted; the code wins. `load_cached` also follows a link at `<hash>.json` with no size cap (`:272-275`). Existing mitigation: shape guard only. Fix:
  1. Bind trust to state outside the worktree: an HMAC over each entry (or over the stamp), keyed by a per-user secret in the user cache dir, so a committed stamp or entry never verifies. Alternatively, default the cache outside the worktree.
  2. Validate the edge/raw_call/label types.
  3. Check `_is_plain_file` and a byte cap before `read_text`.

- **[medium] `dummyindex/pipeline/extract/generic.py:96-419,447-737`: recursion depth is unbounded on the AST walk.** `walk(root)` (`:419`) and `walk_calls` (`:737`) recurse in Python per AST level and sit outside the only `try` (`:44-50`, around `parser.parse`). The 7 custom walkers have the same shape: `go.py:167`, `rust.py:135`, `julia.py:243`, `elixir.py:165`, `verilog.py:139`, `zig.py:173`, `powershell.py:199`. The call site `extract/__init__.py:173` has no handler either. Probe: one `.py` holding a 3000-deep nested list raised `RecursionError` out of `extract()` and aborted the whole batch. That contradicts `spec.md` ("never aborts the batch"); the code wins. The same escape exists for deeply nested JSON. `load_cached` catches only `JSONDecodeError`/`OSError` (`cache.py:276`), and `storage._decode` catches only `ValueError`/`UnicodeError` (`export/storage.py:133`). The probe confirmed `RecursionError` is neither. Existing mitigation: none. Fix:
  - Walk iteratively (explicit stack or `TreeCursor`), or cap the depth.
  - Catch `RecursionError`/`Exception` around `extractor(path)` and record `pending` without caching.
  - Map `RecursionError` to a miss in `load_cached` and to `GraphStorageError` in `_decode`.

- **[medium] `dummyindex/pipeline/extract/languages/dart.py:39-41,68-70`: the regex extractor backtracks quadratically.** Both patterns start with `^\s*` under `re.MULTILINE`. Because `\s` matches `\n`, every line start rescans forward across later lines. In `(?:\w+\s+)+(\w+)\s*\(` the repeated group also spans lines. Measured on the function regex: short lines with no `(` at 4/8/16 KB took 0.13/0.51/2.0 s. On the class regex: blank-line runs at 2/4/8 KB took 0.04/0.17/0.72 s. Both grow ×4 per ×2, which puts a ~1 MB file in hours, with no timeout and no size cap. `blade.py:41,67,93` rebuilds `{n["id"] for n in nodes}` on every match, which is O(matches²). The Blade regexes themselves are linear. Existing mitigation: none. Fix:
  - Use `^[ \t]*` and `[ \t]+` so matches stay on one line, and bound the repeat (`(?:\w+[ \t]+){1,6}`).
  - Add a per-file byte cap.
  - Keep a running id set in Blade.

- **[medium] `cache.py:61-77` (`read_source_bytes`) + `extract/__init__.py:123,166-182`: no source-size bound, and 9 extractors bypass the read seam.** Every file is read whole and memoized for the entire build, and its bytes are also returned in `file_bytes`. Peak memory is therefore the sum of all code bytes. `detect()` has no size filter. `pipeline/build/references.py:153,165` drops anything over 2 MB, but only after the extractor has read and parsed it. `is_safe_read_target(max_bytes=)` (`pipeline/io/paths.py:37-53`) is still unwired on this path; its only caller is `reality_check/verify.py:180`. Nine extractors read disk directly: `dart.py:21` and `blade.py:21` (`read_text`), plus `go.py:27`, `rust.py:28`, `julia.py:27`, `elixir.py:28`, `verilog.py:28`, `zig.py:27` and `powershell.py:32` (`read_bytes`). A cap or read-time guard added at the seam would not cover them, and the hash read and the extract read can see different bytes. `spec.md`'s single-seam invariant is contradicted; the code wins. Existing mitigation: none on the read itself. Fix:
  - Enforce a cap inside `read_source_bytes`: fstat the opened fd, read cap+1, then record the file as `pending`/too-large.
  - Route all 9 extractors through `read_source_bytes`.

- **[medium] `extract/__init__.py:371-379` (`collect_files`, default `follow_symlinks=False` branch): the walk is not contained.** `rglob` descends Windows junctions and yields leaf file symlinks, and nothing checks containment or regular-file status. Probe: a junction `vendor -> <outside dir>` emitted `vendor/secret.py`. The realpath check exists only in the follow branch (`:384-411`). That branch has its own gaps: `os.path.islink` (`:386`) misses junctions, only a link to an ancestor is pruned (`:389`), there is no visited set (so mutually linked dirs re-enumerate until the path limit), and escaping dirs are descended with only their leaves filtered. `spec.md`'s symlink-containment section and the prior "default rglob does not chase" claim are wrong for junctions; the code wins. Exposure: `__main__` (`:415-428`) and the public `dummyindex.collect_files` export. Builds use `detect()`, which is hardened (`pipeline/io/detect.py:524-569`: lstat plus reparse check, resolve boundary, `S_ISREG`, visited set). Existing mitigation: none on this branch. Fix: reuse detect's `safe_path` logic in both branches. Prune `dirnames` whose realpath escapes before descending, detect reparse points via `st_file_attributes`, and track visited realpaths.

- **[low] `export/storage.py:409-486,497` (`_read_manifest`, `read_graph_payload`): reader bounds are set by the manifest.** The per-shard read cap is the manifest's own `max_file_bytes` (`:414-416,463`), with no ceiling. Shard count and summed `bytes` are unbounded, all records are assembled in memory (`:481`), and a plain graph is read with no cap (`:497`). A committed hostile `.context/features/symbol-graph.json` can therefore exhaust memory in all 6 `read_graph_payload` consumers. Separately, `_prune_shards` lstat-checks `parts` (`:282`) and then scans and unlinks by path (`:290,304`), so a directory swapped in between redirects `<64hex>.json` deletions. That needs a concurrent local actor. Existing mitigation: per-entry `_is_linked`/`S_ISREG`/name/grace checks (`:294-303`) and `_plain_path`/`O_NOFOLLOW` reads (`:68-127`). Fix:
  - Clamp `max_file_bytes` to a reader-side ceiling and bound the shard count and `sum(bytes)` before reading any shard.
  - Cap the plain read.
  - On POSIX, prune through a dir fd: `os.open(parts, O_DIRECTORY|O_NOFOLLOW)`, then `os.scandir(fd)` and `os.unlink(name, dir_fd=fd)`.

- **[low] `cache.py:124-141,195-215`: link checks on the cache dir are left to callers.** Three gaps:
  - `cache_dir()` never lstat-checks its default `<root>/.context/cache`, and the trusted branch calls `.resolve()` (`:134`), which follows links.
  - `scope_cache_to_version` follows a linked dir via `is_dir()`/`scandir` (`:206,215`).
  - A relative `DUMMYINDEX_CACHE_DIR` resolves against cwd, not `root` (`:138`).

  Only `scan_root` → `validate_context_destination` (`scope.py:14-35`) protects the runner and `enriched_refresh` paths. The public `build_maps`/`build_tree` (`context/build/maps.py:104-110`, `tree.py:64-69`) and `extract()` without `cache_root` skip it. `is_safe_read_target` checks only `S_ISLNK` (`paths.py:49`), unlike `_is_plain_file` (`cache.py:185-192`) and `storage._is_linked` (`:40-45`), which also reject `FILE_ATTRIBUTE_REPARSE_POINT`. Existing mitigation: caller-side `validate_context_destination` on the 2 build paths. Fix:
  - lstat- and reparse-check the directory inside `cache_dir()` and `scope_cache_to_version()`.
  - Resolve relative env values against `root`.
  - Unify the three link predicates into one.

### Resolved since last review

Still resolved (re-verified at the new ranges):
- **Ambient `DUMMYINDEX_CACHE_DIR` out-of-repo redirect.** Confined by `resolve_under_root`; an escaping value falls back to the default (`cache.py:133-139`). The trusted channel is off the env var (`context/build/common.py:164-178`).
- **Resolver second untrusted read.** Both resolvers read through the seam (`pipeline/extract/resolve.py:74,195`).
- **`follow_symlinks=True` leaf escape.** Contained at `extract/__init__.py:384-411`. The default branch is reopened above.

Verified, not findings:
- **`scope_cache_to_version` deletion scope.** It deletes only `fullmatch` `<64hex>.json` regular non-link children (`cache.py:29,185-192,217-223`) and withholds the stamp on failure (`:234-236`).
- **Shard-prune deletion scope.** Name regex plus protected set, lstat link/regular checks, and the 600 s grace (`storage.py:276-329`).
- **`.context/cache` as a link on build paths.** Refused by `scope.py:14-35`.
- **`references.py` ReDoS.** `re.escape` plus a bare lookahead (`pipeline/build/references.py:115-116`).
- **`pipeline/io/git.py`.** Has no subprocess.
- **graspologic.** Off the committed path (`analysis/cluster.py:67-73`); Leiden (`:48-64`) only swaps `sys.stdout`/`sys.stderr`.
  - Residual: `generic.py:25` imports grammar modules by fixed name. If the `__main__` usage line (`python -m dummyindex.pipeline.extract`, `extract/__init__.py:418`) is run from an untrusted cwd, cwd goes on `sys.path`, so a repo file named like a grammar package gets imported. Suggest `-P`/`PYTHONSAFEPATH` in that usage line.

Reopened:
- **Cache poisoning** (`concerns.md` Security item 1, marked RESOLVED). Moved to the second high bullet above. The fix was a shape guard plus env confinement, which hostile repo content bypasses. The "SHA-256 collision" residual framing was wrong.

<!-- critic: product -->

## Product surface

_Line refs are `0634bfd` and match `map/symbols.json`. The working tree has trimmed comments, which shifts them (`extract` is `:130` at HEAD and `:111` on disk). Measurements come from this repo on Windows with Python 3.12, using a scratch cache dir. Probes ran in the scratchpad and wrote nothing to the repo._

- **1. A warm cache returns another path's symbols.** Scenario: the developer moves or renames the checkout dir with its gitignored `.context/cache/` intact (or uses one checkout from both WSL and Windows, or restores the cache in CI), `git mv`s a file, or keeps two byte-identical files. Observed: `file_hash` keys on content only (`pipeline/io/cache.py:116-136`). A hit is appended verbatim, carrying the writer's `source_file` and file-node id (`pipeline/extract/__init__.py:197-203`), and `id_remap` rewrites only the current path's slug (`:249-257`).
  - Probe, copied repo rebuilt in its new dir: `map/symbols.json` holds 0 symbols, every file is `file-only` in `coverage.json`, and `symbol-graph.json` cites the old absolute paths.
  - Probe, `mv pkg/util.py pkg/moved.py` then rebuild: `Alpha`/`run` drop out of `symbols.json`, the graph keeps them at the deleted `pkg/util.py`, and `pkg/moved.py` reads `file-only`, 0 symbols.
  - This repo's graph: 23 of 553 code files have no node. They are 22 empty `tests/**/__init__.py` files plus `dummyindex/context/output/__init__.py`, whose bytes equal `context/domains/__init__.py`. The dispatch pass also drops such files silently (`python_dispatch.py:459-462`).
  - Gap: `cache.py:123` promises "Cache survives `mv` / repository moves without manual rebuild", and `spec.md:12` and `plan.md:57` repeat the claim. The code does the opposite, so code wins and the spec and plan conflict with it. No verb clears the cache (`rebuild --full` reuses it). Recovery means deleting `.context/cache/` by hand or bumping the package version.

- **2. One vanished or unreadable file aborts the whole build.** Scenario: a code file is deleted between `detect` and `extract` (a branch switch or generated-file cleanup), or it is unreadable. Detect checks only `lstat` (`pipeline/io/detect.py:534-556`), and `count_words` swallows the read error (`:284-295`), so the file stays in the code list. Observed: `_extract_generic` returns an `error` and the state becomes `pending` (`extract/__init__.py:204-209`). Then the unguarded `file_bytes[str(path)] = read_source_bytes(path)` (`:213`) raises. Probe (vanished case): `FileNotFoundError` escapes `extract()`. The unreadable case reaches the same line by code path and raises `PermissionError`. `build_all` has no handler around it (`context/build/runner.py:146`). Gap: `spec.md:11` says an errored result "never aborts the batch". The user gets a traceback and no index, not one `pending` row.

- **3. Unsupported languages produce an empty map with no trace.** Scenario: a Haskell, OCaml, shell, SQL or Terraform repo. Observed: `classify_file` returns `None` for unknown suffixes (`detect.py:140-163`), and the leaf is dropped without a `record_excluded` entry (`:658-673`). It appears in neither `coverage.json` `files` nor `excluded`. `context init` prints `files: 0  symbols: 0` (`cli/init.py:198-199`), the same output as a dir that holds no code at all. Gaps exist inside the supported set too:
  - Detect lowercases the suffix (`detect.py:142-145`), but `_DISPATCH.get(path.suffix)` is case-exact (`extract/__init__.py:185-188`). `Upper.PY` comes out `unsupported` with "No AST extractor for .PY" (probed).
  - `.ejs` counts as code for detect (`detect.py:32`) but has no extractor (`extract/__init__.py:90-125`).
  - `collect_files._EXTENSIONS` (`:370-395`) lacks `.jsx .mjs .ex .exs .jl .vue .svelte .dart .v .sv`. `python -m dummyindex.pipeline.extract <dir>` (`:452-462`) on a Vue, Svelte, Dart, Elixir, Julia or Verilog tree emits empty `nodes`.
  - Gap: the surfaces the user reads show no count or list of skipped files.

- **4. `file_status` names mislead the user and the agent.**
  - `"parsed"` is set before the cache lookup (`extract/__init__.py:196`). It therefore covers stale hits (bullet 1) and zero-node results. Coverage then relabels by symbol count (`context/build/coverage.py:61-69`), so an empty `__init__.py`, a renamed file and a duplicate all read the same: `file-only`, "No AST symbols extracted".
  - `"pending"` means the extractor failed: a missing grammar (`generic.py:45-46`), a language-load error (`:47-48`) or a parse exception (`:55-56`). Errors are never cached (`extract/__init__.py:210-211`), so every build repeats the attempt and the failure, and nothing is actually queued.
  - `pipeline/extract/` has no `has_error` check. A file with a syntax error reports `parsed` and then `indexed`, with partial symbols.
  - `context status` prints only files, symbols and unassigned (`cli/status.py:78,317`). Agent guidance describes `coverage.json` without `pending` or `unsupported` (`context/output/instructions.py:53`).
  - Gap: no state means "extraction failed" or "stale payload", and the CLI shows no count of either.

- **5. A shard error tells a concurrent reader to rebuild.** Scenario: an agent runs `context graph` while another process publishes a sharded graph. Observed: the grace window keys off shard mtime (`export/storage.py:306-311`), so shards last written more than 600 s before the publish are deleted at once. A reader still holding the old manifest gets `graph shard missing: …; run \`dummyindex context rebuild --changed\`` (`:470-476`), behavior asserted at `tests/export/test_graph_storage.py:315-326`. Re-reading `symbol-graph.json` succeeds. A rebuild republishes and sets up the same race for the next reader.
  - Every other reader error (`hash/size mismatch`, `assembled graph payload hash mismatch`, `unsupported graph storage version`, `invalid graph manifest …`, `:420-493`) names no remedy. Each reaches the agent wrapped as `unreadable: …` (`context/domains/graph_query/load.py:63-67`). The likeliest causes are git merges or partial checkouts of committed shards.
  - `feature.json` still lists the member `test_graph_storage_test_reader_holding_previous_manifest_can_finish_after_publication`. The test is now `test_superseded_manifest_fails_closed_after_publication`.

- **6. A warm re-run costs nearly as much as a cold one.** Measured on 553 code files (4,921,180 bytes): cold `extract` takes 5.73 s and a fully warm one 5.16 s. The warm profile records 1,053 `Parser.parse` calls. `_resolve_python_dispatch` (2.18 s, `python_dispatch.py:464-466`) and `_resolve_cross_file_imports` (1.23 s, `resolve.py:84-85`; Java at `:205-206`) re-parse every `.py` file regardless of the cache. Progress prints only for the per-file pass, and only at 100 or more files (`extract/__init__.py:180-184,214-215`). A warm run prints `100%` and then spends about 85% of its profiled time in silence. Other costs:
  - `--changed` re-hashes every code and doc file before it decides anything (`context/build/incremental.py:111-126,356-370`).
  - `file_bytes` keeps every parsed file's bytes in memory for the whole build (`extract/__init__.py:151,202,213`, held until `runner.py:293-295`). The per-file loop is serial (`:179`).
  - The cache holds 530 entries, 12,974,805 bytes, for 4.9 MB of source. Any package-version change deletes all of it (`cache.py:225-279` via `upgrade.py:580-587`), and the only report is `cache: N stale extraction entries`. Within one version, dead entries and fixed-name `<hash>.tmp` files (`cache.py:344`) are never swept.
  - Gap: `spec.md:7` ("re-parses only what changed") and `spec.md:95` ("no file is re-parsed") contradict the code, and code wins. On Python-heavy repos the cache saves about 10%. Repos in other languages lack these cross-file re-parses, so the per-file pass is their main cost and the per-release wipe repeats all of it.

- **7. The committed sharded graph is rewritten almost whole on each rebuild.** Between `0634bfd` and the working tree, whose only change is trimmed comments, 0 of 12 shards are reused. That adds 11,552,782 bytes of new blobs under `features/symbol-graph.parts/`, for 9,248 nodes and 26,104 links from 553 files. Observed: shards are packed greedily by byte count over sorted records (`export/storage.py:195-214`), so one inserted or resized record shifts every later shard boundary. Reuse needs byte-identical shards (`:399-406`). Node records also carry `source_location` and a size-ranked `community` id, which any partition change renumbers (`analysis/cluster.py:139-140`). Gap: "content-addressed shards" and "touching any it reuses" (`spec.md:19`) suggest incremental storage. In practice each `.context/` commit adds roughly the full graph size to git history.

- **8. Community and rank artifacts misdescribe how they are made.**
  - The committed partition is Louvain-only (`analysis/cluster.py:77-84`), and `_leiden_partition` (`:54-74`) has no caller under `dummyindex/`. Still, `pyproject.toml:46-49` presents the `[leiden]` extra as "Higher-quality community detection" (it is also in `all` at `:56` and the `leiden` keyword at `:12`). Installing graspologic changes no committed byte.
  - User-facing text still says Leiden: `context/output/docs.py:33` (emitted at `.context/INDEX.md:286`), `domains/features/render.py:100`, the `graph community` docstring (`domains/graph_query/verbs.py:385`), `analysis/__init__.py:1`, `context/build/graph.py:52`, this feature's `feature.json` summary, and `docs/guide/04-data-model.md:60,170`. That doc is medium confidence; code wins, and the conflict is flagged here.
  - `cluster.py:1` says the module "Returns cohesion scores", but `cluster` returns `dict[int, list[str]]`.
  - Seed rank gives test paths a 0.1 personalization weight through a name heuristic (`context/build/communities.py:46-48,63,222-234`), with no knob. `seed-rank.json` rows carry only `id` and `score` (`:143-145`). A repo whose real code lives under `testing/` has its teleport weight cut 10x, and nothing records it.

### Resolved since last review

- graspologic-vs-Louvain partition divergence is resolved (`b157a1c`): the committed path is Louvain-only (`cluster.py:77-84`). The naming residue is in bullet 8.
- The `cluster()` docstring is fixed (`cluster.py:91-102`). Stale wording elsewhere is in bullet 8.
- Files read multiple times per build: reads now collapse to one per path (`cache.py:47-84`, `extract/__init__.py:178`). The re-parse residue is in bullet 6.
- Parse failures and unsupported-only repos are no longer fully silent: `file_status` and `coverage.json.pending` record both (`extract/__init__.py:189-209`, `coverage.py:50-79`). The residue is in bullets 3 and 4.
- Empty repo: `context init` now prints the counts (`cli/init.py:198-199`), and `scan_root` rejects a nonexistent path. An existing dir whose files are all unknown types still reads as empty (bullet 3).
- "Cache is never GC'd" is narrowed by version scoping (`cache.py:225-279`). Within-version growth remains in bullet 6.
- The prior verdict that a path-blind cache key is "fine for reuse" is reversed; it is now bullet 1. Frontmatter stripping never reaches extraction, because `_DISPATCH` has no `.md`. It affects only the `--changed` doc fingerprints (`cache.py:98-113`, `incremental.py:367`).
- Still true but merged above: the dispatch pass's silent skips (bullet 1), the lack of progress output under 100 files, the serial loop and the full `--changed` re-hash (bullet 6), and test-file down-weighting (bullet 8).
- Dropped as not gaps: the tree-sitter version check, and the bare-`rebuild` guard, which belongs to `cli-dispatch`.
- Ownership & coverage (wiring hosts unowned) is resolved: `index-lifecycle` now owns `context/build/{graph,runner,enriched_refresh,incremental,coverage,portable_graph}.py` and `pipeline/build/references.py`.

## Cross-review

Each critic's findings re-checked against current working-tree code (post-`0634bfd` comment trim) and a scratch probe (`extract()` against throwaway repos, scratch cache via `set_trusted_cache_dir`; nothing written to the repo).

### Confirmed HIGHs
1. **Identical files share one cache entry** — `pipeline/io/cache.py:107-121,260-282`, `extract/generic.py:68,93`, `extract/__init__.py:165-172`. Probe: identical `pkg_a/mod.py` + `pkg_b/mod.py` → `pkg_b` 0 nodes, both `parsed`. Mechanism also explains `python_dispatch.py:436-437` silent skip.
2. **Fixed tmp follows a planted link** — `pipeline/io/cache.py:296-311` (`:297`, `:299`, `copy2` at `:307`). Probe: hard link at `<hash>.tmp` → outside `victim.txt` overwritten with extraction JSON. Symlink variant untestable here (no privilege); POSIX git materializes committed symlinks.
3. **Committed entry + forged stamp poisons the graph** — `pipeline/io/cache.py:195-282` (`:209-210` stamp equality, `:240-257` id-only guard). Probe: stamp = installed version → `scope_cache_to_version` deleted 0; planted label `IGNORE PREVIOUS INSTRUCTIONS\n…` loaded, state `parsed`. Marginal capability over committing a poisoned `symbol-graph.json` directly: it survives `rebuild --full` and admits non-identifier text.
4. **Repo move empties `symbols.json`; rename drops symbols** — same root cause as 1. Probe: `a.py` → `b.py` rebuild still emits `source_file` `a.py`. Move confirmed by mechanism: `build_all` resolves `scope` so `detect` paths are absolute (`context/build/runner.py:109-131`), and `normalize_extraction_paths` leaves out-of-root paths opaque; Product's probe showed 0 symbols.
5. **One vanished file aborts the build** — `extract/__init__.py:173-182` (unguarded `read_source_bytes` at `:182`), no handler at `context/build/runner.py:131`. Probe: `FileNotFoundError` escapes `extract()`. Custom extractors (e.g. `go.py:24-31`) catch their own read, so every language reaches `:182`.

### Downgraded
- DB `[HIGH on Windows]` `export/storage.py:209-225` (`_atomic_write`, bare `replace` at `:222`): defect confirmed by code (no retry, unlike `cache.py:162-171`), severity → MEDIUM. The conflicting window is one manifest open/read/close, the prior generation stays readable, and a rerun recovers.

### Refuted / stale at HEAD
- Product #8: `analysis/cluster.py:1` no longer claims "cohesion scores"; Leiden wording is gone from `context/build/graph.py` and `context/domains/graph_query/verbs.py`. Residue that survives: `analysis/__init__.py:1`, `features/render.py:100`, `output/docs.py:33`, `pyproject.toml:12,47-49`, `feature.json` summary.
- Prior `concerns.md` "Ownership & coverage — wiring hosts unowned": `index-lifecycle` now owns every `context/build/` file except `communities.py` (this feature) plus `pipeline/build/references.py`.
- Prior Security item 1 "SHA-256 collision" residual: wrong framing — the attacker authors both file and entry; no collision needed (Security, confirmed).
- Prior "cache key ignores path — fine for reuse": reversed (HIGH 1).

### Merged (deduped)
- DB cache-key HIGH + Product #1 + prior dispatch path-shape skip → one Data-integrity HIGH, with a Product line for the user-visible symptom.
- DB MEDIUM fixed-tmp race + Security HIGH link-follow → one Security HIGH (same line, same fix).
- Security MEDIUM `RecursionError` (`generic.py:419,737` outside the `:44-50` try) → folded into the abort HIGH (same missing per-file boundary).
- DB MEDIUM shard packing + Product #7 → one Data-integrity MEDIUM.
- DB LOW grace-from-mtime + Product #5 false remedy → one Product LOW.
- DB LOW + Security LOW manifest-controlled reader bounds → one Security LOW (cache-dir link checks folded in).
- DB LOW-MED per-dir stamp kept separate (benign two-install case) but tied to the HMAC fix.
- Product seed-rank test weight folded into the carried-forward `_pagerank` LOW.

### Fix conflicts flagged
- (a) Cache key: repo-relative path in the entry name keeps repo-move hits (`cache_root=out_root`) but loses rename/duplicate reuse; rebind-on-load keeps reuse but must rewrite stem-based symbol ids (`generic.py:117`), not just `source_file`; verify-on-hit ping-pongs one `<hash>.json` across duplicates every build and multiplies same-hash concurrent saves. Do not change `file_hash` itself — `incremental.py:304` reuses it for `--changed` fingerprints.
- (b) DB's per-entry version field is forgeable by the same hostile repo, so it does not fix Security HIGH 3; an HMAC over (version, relative path, content hash, payload) keyed outside the worktree fixes poisoning, stale-version reuse and the path collision at once.
- (c) Security's "default the cache outside the worktree" collides with the `.context/cache/` pin (`runner.py:118-128`), the in-repo `DUMMYINDEX_CACHE_DIR` confinement (`cache.py:133-139`) and `upgrade.py:541-542` scoping; prefer the HMAC.
- (d) DB's content-defined shard boundaries alone won't stop Product #7's churn: size-ranked community ids (`cluster.py:124-125`) renumber node records on any partition change.

### Line-ref drift
- Product critique and `plan.md` cite `0634bfd` lines; merged `concerns.md` cites the working tree (e.g. `cache.py:344` → `:297`, `extract/__init__.py:213` → `:182`, `python_dispatch.py:459-462` → `:436-437`, `cluster.py:139-140` → `:124-125`).
