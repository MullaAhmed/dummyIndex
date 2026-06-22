# Extraction & graph backbone — spec

confidence: INFERRED

## Intent

Turn a set of source files into a deterministic structural graph — nodes for files / classes / functions and edges for `contains`, `method`, `inherits`/`extends`/`implements`, `imports`, `calls`, and the framework-aware relations (`uses_config`, `bound_to`, `references_constant`, `uses_static_prop`, `listened_by`) — without an LLM. Extraction is tree-sitter-only, content-addressable cached, and feeds community detection and graph-to-JSON rendering. This is the backbone the rest of `.context/` is built on: every other feature consumes the nodes/edges this pipeline emits.

## User-visible behavior

Running the pipeline on a target (file or directory) produces:

- **An in-memory graph payload** — `extract(paths)` returns `{"nodes": [...], "edges": [...], "input_tokens": 0, "output_tokens": 0}` (`dummyindex/pipeline/extract/__init__.py:244-249`). Each node carries `id`, `label`, `file_type`, `source_file`, `source_location` (`generic.py:59-65`); each edge carries `source`, `target`, `relation`, `confidence`, `source_file`, `source_location`, `weight` (`generic.py:69-77`).
- **A per-file cache** under `<root>/.context/cache/{sha256}.json`, keyed on file *content* (path-independent), so re-runs skip unchanged files (`cache.py:20-40`, `__init__.py:163-169`). Markdown caches hash only the body below YAML frontmatter (`cache.py:10-17,39`).
- **Community assignments** — `cluster(G)` returns `{community_id: [node_id, ...]}`, IDs stable and size-descending (`cluster.py:59-104`), feeding the `community-N` feature taxonomy.
- **`symbol-graph.json`** — `to_json(G, communities, path)` writes a NetworkX node-link document with each node tagged `community` and `norm_label`, and each link backfilled with a numeric `confidence_score` (`graph.py:23-38`).

`collect_files(target)` enumerates supported source files, skipping dotted dirs and `.dummyindexignore` matches (`__init__.py:252-293`). `extract` runs CLI-style via `python -m dummyindex.pipeline.extract <path>...` (`__init__.py:296-306`).

## Contracts

Public functions (names verified against `.context/map/symbols.json`):

- `extract(paths: list[Path], cache_root: Path | None = None) -> dict` — `__init__.py:118-249`. Two-pass: per-file structural extraction (cache-aware), then cross-file Python/Java import resolution and a global raw-call resolution pass. Re-homes node/edge ids from absolute to root-relative when a common prefix exists (`__init__.py:180-197`).
- `collect_files(target: Path, *, follow_symlinks: bool = False, root: Path | None = None) -> list[Path]` — `__init__.py:252-293`.
- `_extract_generic(path: Path, config: LanguageConfig) -> dict` — `generic.py:23-650`. The parametric driver; ~12 languages delegate via `languages/wrappers.py`. Custom-walk languages (Go, Rust, Julia, etc.) bypass it. Returns `{"nodes", "edges", "raw_calls"}` or `{"nodes": [], "edges": [], "error": ...}` on parse/import failure (`generic.py:33-46`).
- `LanguageConfig` (`@dataclass`) — `config.py:12-47`. Declares grammar quirks: node-type frozensets, name/body fields, call-accessor fields, and optional `import_handler` / `resolve_function_name_fn` callables.
- `_make_id(*parts: str) -> str` — `common.py:12-16`. Stable, lowercased, non-alnum-collapsed node id.
- `_resolve_cross_file_imports(per_file, paths) -> list[dict]` — `resolve.py:17-146` (Python); `_resolve_cross_file_java_imports` — `resolve.py:149-231`. Upgrade file-level imports into class-level edges (Python `uses` INFERRED w=0.8; Java `imports` EXTRACTED).
- `cluster(G: nx.Graph) -> dict[int, list[str]]` — `cluster.py:59-104`. Leiden (graspologic) with Louvain fallback (`_partition`, `cluster.py:21-52`); splits communities > 25% of nodes (min 10) via `_split_community` (`cluster.py:107-122`).
- `to_json(G, communities, output_path) -> None` — `graph.py:23-38`.
- `load_cached(path, root) -> dict | None` / `save_cached(path, result, root) -> None` / `file_hash(path, root) -> str` / `cache_dir(root) -> Path` — `cache.py:43-108`.
- `is_git_repo(root) -> bool` / `resolve_git_dir(root) -> Path | None` — `git.py:24-59`. Pure-filesystem repo detection (submodule/worktree aware), never raises on malformed input.

## Examples

```python
from pathlib import Path
from dummyindex.pipeline.extract import collect_files, extract

paths = collect_files(Path("src"))
graph = extract(paths, cache_root=Path("."))
# graph["nodes"] -> [{"id": "auth_digestauth", "label": "DigestAuth", ...}, ...]
# graph["edges"] -> [{"source": "...", "target": "...", "relation": "uses",
#                     "confidence": "INFERRED", "weight": 0.8, ...}, ...]
```

```python
import networkx as nx
from dummyindex.analysis.cluster import cluster
from dummyindex.export.graph import to_json

communities = cluster(G)                       # {0: [...largest...], 1: [...], ...}
to_json(G, communities, "features/symbol-graph.json")
```
