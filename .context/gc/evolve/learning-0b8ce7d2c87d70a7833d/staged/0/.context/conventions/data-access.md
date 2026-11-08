# Data access

**No relational DB / ORM — persistence is JSON + markdown artifacts on the filesystem.** dummyindex's "data layer" reads source code (via tree-sitter, in `dummyindex/pipeline/`) and persists *derived* artifacts under `.context/`: deterministic maps/trees as JSON, curated docs as markdown, and a per-file extraction cache. There are no tables, no migrations, no query language. The patterns below are the equivalent disciplines for that filesystem store.

## Atomic writes (the one mandatory rule)

Every persisted artifact is written **tmp-file + `replace`**, never opened-and-truncated in place. The canonical helper is `write_text_atomic` backed by `_replace_bytes` (`dummyindex/context/domains/atomic_io.py:11-33`): `mkdir(parents=True)`, write to a **unique** `NamedTemporaryFile` sibling (`.{name}.*.tmp` — unique because hooks from two Claude profiles can update the same repo-local cache concurrently), then `tmp_path.replace(path)` (atomic on POSIX) with the tmp unlinked on failure. Every other writer reimplements the same shape — `write_meta` (`build/meta.py:91-97`), `write_manifest` (`build/manifest.py:121-123`), `write_tree`, the maps writer, and the convention-section placer (`build/conventions.py:228-230`). The cache writer adds a Windows `PermissionError` fallback to copy-then-delete (`pipeline/io/cache.py:98-105`). Rationale: a concurrent reader (e.g. the statusline badge, `cli/plan_update.py:45-50`) must never observe a half-written file.

`write_text_atomic` is **byte-faithful by contract** — it never normalizes the string, because equip's lifecycle hash-baseline fingerprints the in-memory text and any silent rewrite would make a generated file look user-edited (`atomic_io.py:14-19`). Callers wanting pre-commit-clean EOF run `normalize_eof_newline` *after* the write (`atomic_io.py:27-46`).

## Schema versioning & stable serialization

Every JSON artifact is a frozen dataclass carrying an integer `schema_version` and a `to_dict()` (see `Manifest`/`FileEntry`, `build/manifest.py:39-69`; `FilesMap`/`SymbolsMap`, `build/maps.py:82-88`). Readers validate it: `meta.py:60-66` raises if `schema_version` is newer than the build supports and rejects payloads missing required fields. Serialization is deterministic — `json.dumps(payload, indent=2)` with a trailing `"\n"`; `meta.py:96` adds `sort_keys=True`. Entries are emitted in sorted order (`maps.py:134`, `manifest.py:189`) so a re-run is byte-identical.

## Repo-relative paths — no absolute-path leakage

Paths stored in committed artifacts are always **POSIX, repo-relative**. `_rel_posix` (`maps.py:211-216`) resolves against `root` and `.relative_to(root).as_posix()`, returning `None` (skip) when a file falls outside the repo. `write_manifest` does the same and silently drops out-of-tree files (`manifest.py:105-107`). The cache key deliberately excludes the path entirely — `file_hash` is content-addressable (`pipeline/io/cache.py:20-40`), so re-runs from a different cwd, post-`mv`, or with absolute-vs-relative `source_file` all hit the same entry.

## Drift / staleness (the "cache layer")

`.context/cache/manifest.json` is a per-file SHA-256 manifest (`build/manifest.py`). `compare()` (`manifest.py:145-194`) re-hashes a file only when size or mtime differ, then classifies `added`/`modified`/`removed` — this is how the SessionStart hook reports drift and `rebuild --changed` finds work. `cache/` is **per-machine and gitignored**; never reference it from committed code or docs.

## Layering & pitfalls

- **Keep I/O at the boundary.** `cli/*` prints/formats and calls writers; `build/*` + `domains/*` own the serialization. Don't scatter `json.dump` into business logic — route through the dataclass `to_dict()` + an atomic writer.
- **Never hand-edit a generated artifact** (`map/`, `tree.json`, `manifest.json`) — `rebuild --changed` overwrites it. Curated markdown (this doc, feature specs) is the editable layer.
- **Don't bypass `write_text_atomic`** with a plain `open(...,"w")` — you lose atomicity *and* break hash-baselining.
- **Don't leak absolute paths or unsorted dicts** into a committed JSON; both break byte-identical re-runs. Always go through `_rel_posix` and sorted/stable emission.
- New convention sections must be registered in `CONVENTION_SECTIONS` (`build/conventions.py:26`) or the placer rejects them (`conventions.py:217-221`).

<!-- dummyindex:rule {"evidence":[".context/gc/closeouts/audit-upgrade-path-for-existing-repos-on-older-dummyindex-versions.json"],"evidence_sha256":{".context/gc/closeouts/audit-upgrade-path-for-existing-repos-on-older-dummyindex-versions.json":"6ff11bd64d849a1a2166dc45a921d26fc6ce9af75aebba248a980e3824feed4c"},"id":"tree-node-stub-contract","sources":{"dummyindex/context/build/navigation_refresh.py":"09995de8f193ae5862b4aaad5f5a4e0311862c7ac3919efb8e969a5b22f482d9","tests/context/build/test_index_repair.py":"37aa82eb4fe27ece607b4fdea9d96a2cd94243192a7a49f21a56d3871f4baf45"},"supersedes":[]} -->
Every tree.json node writer must always emit `abstract` and `confidence`. Refresh treats a node as a regenerable stub only when `confidence == "EXTRACTED"` and `abstract` matches the mechanical template (dummyindex/context/build/navigation_refresh.py:L36-L72); a node missing either key is classified as authored, so its stale template text is carried forward and labelled `source-stale` instead of regenerated. Null/empty `overview_ref`/`detail_ref`/`labels`/`evidence` may be omitted (carry-forward copies only keys present). Behaviour pinned by tests/context/build/test_index_repair.py:L230-L257.
<!-- dummyindex:rule:end tree-node-stub-contract -->
