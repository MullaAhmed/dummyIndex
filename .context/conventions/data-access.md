# Data access

**No relational DB or ORM. Persistence is JSON and markdown artifacts on the filesystem.** dummyindex's "data layer" reads source via tree-sitter in `dummyindex/pipeline/`. It writes *derived* artifacts under `.context/`: deterministic maps and trees as JSON, curated docs as markdown, per-file extraction cache. No tables, no migrations, no query language. Patterns below are the filesystem-store equivalents.

## Atomic writes (the one mandatory rule)

Every persisted artifact is written **tmp-file + `replace`**. Never open and truncate in place.

Canonical helper: `write_text_atomic`, backed by `_replace_bytes` (`dummyindex/context/domains/atomic_io.py:11-33`). It runs `mkdir(parents=True)`. It writes to a **unique** `NamedTemporaryFile` sibling (`.{name}.*.tmp`). Unique because hooks from two Claude profiles can update the same repo-local cache concurrently. Then `tmp_path.replace(path)`, atomic on POSIX. The tmp file is unlinked on failure.

Every other writer copies the same shape. Examples: `write_meta` (`build/meta.py:91-97`), `write_manifest` (`build/manifest.py:121-123`), `write_tree`, the maps writer, the convention-section placer (`build/conventions.py:228-230`).

Cache writer adds a Windows `PermissionError` fallback: copy, then delete (`pipeline/io/cache.py:98-105`). Why: a concurrent reader must never see a half-written file. Example reader: the statusline badge (`cli/plan_update.py:45-50`).

`write_text_atomic` is **byte-faithful by contract**. It never normalizes the string. Equip's lifecycle hash-baseline fingerprints the in-memory text. Any silent rewrite makes a generated file look user-edited (`atomic_io.py:14-19`). Callers wanting pre-commit-clean EOF run `normalize_eof_newline` *after* the write (`atomic_io.py:27-46`).

## Schema versioning & stable serialization

Every JSON artifact is a frozen dataclass. It carries an integer `schema_version` and a `to_dict()`. See `Manifest`/`FileEntry` (`build/manifest.py:39-69`) and `FilesMap`/`SymbolsMap` (`build/maps.py:82-88`).

Readers validate it. `meta.py:60-66` raises if `schema_version` is newer than the build supports. It also rejects payloads missing required fields.

Serialization is deterministic. Uses `json.dumps(payload, indent=2)` with a trailing `"\n"`. `meta.py:96` adds `sort_keys=True`.

Entries are emitted in sorted order (`maps.py:134`, `manifest.py:189`). So a re-run is byte-identical.

## Repo-relative paths — no absolute-path leakage

Paths in committed artifacts are always **POSIX, repo-relative**. `_rel_posix` (`maps.py:211-216`) resolves against `root`, using `.relative_to(root).as_posix()`. It returns `None` (skip) for files outside the repo. `write_manifest` does the same and silently drops out-of-tree files (`manifest.py:105-107`).

Cache key excludes the path on purpose. `file_hash` is content-addressable (`pipeline/io/cache.py:20-40`). So re-runs from a different cwd, after `mv`, or with absolute vs relative `source_file` hit the same entry.

## Drift / staleness (the "cache layer")

`.context/cache/manifest.json` is a per-file SHA-256 manifest (`build/manifest.py`). `compare()` (`manifest.py:145-194`) re-hashes a file only when size or mtime differ. It classifies `added`/`modified`/`removed`. The SessionStart hook uses this to report drift. `rebuild --changed` uses it to find work.

`cache/` is **per-machine and gitignored**. Never reference it from committed code or docs.

## Layering & pitfalls

- **Keep I/O at the boundary.** `cli/*` prints and formats. It calls writers. `build/*` and `domains/*` own serialization. Don't scatter `json.dump` into business logic. Route through dataclass `to_dict()` and an atomic writer.
- **Never hand-edit a generated artifact** (`map/`, `tree.json`, `manifest.json`). `rebuild --changed` overwrites it. Curated markdown is the editable layer: this doc, feature specs.
- **Don't bypass `write_text_atomic`** with plain `open(...,"w")`. You lose atomicity *and* break hash-baselining.
- **Don't leak absolute paths or unsorted dicts** into committed JSON. Both break byte-identical re-runs. Always go through `_rel_posix` and sorted, stable emission.
- New convention sections must be registered in `CONVENTION_SECTIONS` (`build/conventions.py:26`). Otherwise the placer rejects them (`conventions.py:217-221`).
