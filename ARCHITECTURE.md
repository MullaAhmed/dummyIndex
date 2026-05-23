# Architecture

dummyindex is a Python CLI and packaged assistant skill for turning a folder of
code, documents, papers, images, and media into graph artifacts under
`dummyindex-out/`.

## Runtime Shape

The CLI entry point is `dummyindex.__main__:main`. It handles three groups of
commands:

- Skill installation: `install --platform ...`, plus platform subcommands such
  as `codex install`, `gemini install`, and `cursor install`.
- Graph navigation: `query`, `path`, `explain`, `benchmark`, and MCP serving.
- Maintenance: `update`, `watch`, `cluster-only`, `hook`, `add`, and
  `save-result`.

The assistant skill markdown in `dummyindex/skills/` orchestrates the full
agent-assisted pipeline. The terminal CLI focuses on deterministic local
operations and graph navigation.

## Pipeline

1. `dummyindex.pipeline.detect` walks the target tree, applies
   `.dummyindexignore`, classifies files, skips sensitive files, converts Office
   files when optional dependencies are installed, and writes detection stats.
2. `dummyindex.runtime.transcribe` turns video/audio into cached transcripts
   when the video extra is installed.
3. `dummyindex.pipeline.extract` runs tree-sitter based AST extraction for code
   files and caches per-file results.
4. Assistant subagents extract semantic nodes and relationships from non-code
   inputs. The skill markdown writes those chunk results into `dummyindex-out/`.
5. `dummyindex.pipeline.build` merges AST and semantic extraction dictionaries
   into a NetworkX graph while normalizing legacy schemas and compatible node
   IDs.
6. `dummyindex.analysis.cluster`, `analyze`, and `report` derive communities,
   god nodes, surprising connections, suggested questions, cohesion, and
   `GRAPH_REPORT.md`.
7. `dummyindex.pipeline.export` writes `graph.json`, `graph.html`, Obsidian,
   Canvas, SVG, GraphML, Cypher, structure, flow, and feature artifacts.
8. `dummyindex.runtime.run_log` aggregates useful run statistics into
   `run_log.json`; `cost.json` remains only as a backward-compatible pointer.

## Module Responsibilities

- `dummyindex/pipeline/detect.py`: file discovery, type classification, corpus
  sizing, ignore rules, and document conversion.
- `dummyindex/pipeline/extract.py`: language-specific AST extractors,
  cross-file call/import resolution, rationale extraction, and code cache use.
- `dummyindex/pipeline/build.py`: schema compatibility, graph construction, and
  edge endpoint normalization.
- `dummyindex/pipeline/structure.py`: deterministic folder/file/class/function
  structure graph plus textual cross-reference edges.
- `dummyindex/pipeline/export.py`: all serialized artifacts and HTML viewers.
- `dummyindex/analysis/*.py`: clustering, graph analysis, flow synthesis,
  feature synthesis, naming helpers, reports, wiki output, and benchmarking.
- `dummyindex/runtime/*.py`: CLI runtime support: hooks, watching, MCP serving,
  URL ingest, security guards, transcripts, and run logs.
- `dummyindex/skills/*.md`: assistant-facing orchestration instructions.

## Data Contracts

Extraction dictionaries use:

- `nodes`: each node needs `id`, `label`, `file_type`, and optional source
  metadata.
- `edges`: each edge needs `source`, `target`, `relation`, and `confidence`.
  Legacy `from`/`to` keys are normalized during build.
- `hyperedges`: optional grouped relationships such as flows and features.

`graph.json` is NetworkX node-link JSON. Newer NetworkX versions write edges as
`links`; the code accepts both `links` and `edges` where compatibility matters.

Confidence values are semantic:

- `EXTRACTED`: directly observed in source or deterministic parsing.
- `INFERRED`: model- or heuristic-derived relationship.
- `AMBIGUOUS`: uncertain relationship that should be reviewed.

## Installation Model

Global skill installation and project always-on configuration are separate:

- `dummyindex install --platform <name>` copies a slash-command skill into the
  assistant's global skill directory.
- `dummyindex <platform> install` writes project-local context files and hooks.

The package includes `skill.md` and `skill-codex.md`. Installers resolve missing
platform-specific skill templates to the generic skill body, which keeps older
platform commands working even when a dedicated template is not packaged.

## Adding a Language

1. Add the extension in `dummyindex.pipeline.detect.CODE_EXTENSIONS`.
2. Add or configure a parser in `dummyindex.pipeline.extract`.
3. Emit stable IDs with `_make_id()` and include `source_file` and
   `source_location`.
4. Emit `contains`, `imports`/`imports_from`, and `calls`/`uses` edges where
   the grammar supports them.
5. Add cross-file resolution if the language has import or call syntax that can
   be linked after all files are parsed.
6. Verify with a small fixture through `extract()` and `build_from_json()`.

## Local Verification

The repository currently has no checked-in test suite. Use these checks before
shipping changes:

```bash
python3 -m compileall -q dummyindex
uvx ruff check .
python3 -m dummyindex --help
```

For install-path changes, test with an isolated home directory:

```bash
tmp=$(mktemp -d)
HOME="$tmp/home" PYTHONPATH="$PWD" python3 -m dummyindex install --platform codex
rm -rf "$tmp"
```
