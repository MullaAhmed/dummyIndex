---
name: dummyindex
description: any input (code, docs, papers, images) → knowledge graph → clustered communities → HTML + JSON + audit report
trigger: /dummyindex
---

# /dummyindex

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Usage

```
/dummyindex                     # full pipeline on current directory
/dummyindex <path>              # full pipeline on specific path
/dummyindex <path> --update     # incremental - re-extract only new/changed files
/dummyindex <path> --no-viz     # skip visualization, just report + JSON
/dummyindex <path> --wiki       # build agent-crawlable wiki
/dummyindex query "<question>"  # BFS traversal - broad context
```

## What You Must Do When Invoked

If no path was given, use `.` (current directory). Do not ask the user for a path.

Follow these steps in order. Do not skip steps.

**All commands use `python -c "..."` syntax — no bash heredocs, no shell redirects, no `&&`/`||`. This runs correctly on Windows PowerShell and macOS/Linux alike.**

### Step 1 - Ensure dummyindex is installed

```python
python -c "import dummyindex; import sys; from pathlib import Path; Path('dummyindex-out').mkdir(exist_ok=True); Path('dummyindex-out/.dummyindex_python').write_text(sys.executable)"
```

If the import fails, install first:

```python
python -m pip install dummyindex -q
```

Then re-run the Step 1 command.

### Step 2 - Detect files

```python
python -c "
import json, sys
from dummyindex.pipeline.detect import detect
from pathlib import Path

result = detect(Path('INPUT_PATH'))
Path('dummyindex-out/.dummyindex_detect.json').write_text(json.dumps(result, indent=2))
total = result.get('total_files', 0)
words = result.get('total_words', 0)
print(f'Corpus: {total} files, ~{words} words')
for ftype, files in result.get('files', {}).items():
    if files:
        print(f'  {ftype}: {len(files)} files')
"
```

Replace `INPUT_PATH` with the actual path. Present a clean summary — do not dump the raw JSON.

- If `total_files` is 0: stop with "No supported files found in [path]."
- If `total_words` > 2,000,000 OR `total_files` > 200: warn the user and ask which subfolder to run on.
- Otherwise: proceed to Step 3.

### Step 3 - Extract entities and relationships

#### Part A - Structural extraction (AST, free, no API cost)

```python
python -c "
import json
from dummyindex.pipeline.extract import collect_files, extract
from pathlib import Path

detect = json.loads(Path('dummyindex-out/.dummyindex_detect.json').read_text())
code_files = []
for f in detect.get('files', {}).get('code', []):
    p = Path(f)
    code_files.extend(collect_files(p) if p.is_dir() else [p])

if code_files:
    result = extract(code_files)
    Path('dummyindex-out/.dummyindex_ast.json').write_text(json.dumps(result, indent=2))
    print(f'AST: {len(result[\"nodes\"])} nodes, {len(result[\"edges\"])} edges')
else:
    Path('dummyindex-out/.dummyindex_ast.json').write_text(json.dumps({'nodes':[],'edges':[],'input_tokens':0,'output_tokens':0}))
    print('No code files - skipping AST extraction')
"
```

#### Part B - Semantic extraction (AI, costs tokens)

Skip if corpus is code-only (no docs, papers, or images).

Check cache first:

```python
python -c "
import json
from dummyindex.pipeline.cache import check_semantic_cache
from pathlib import Path

detect = json.loads(Path('dummyindex-out/.dummyindex_detect.json').read_text())
all_files = [f for files in detect['files'].values() for f in files]
cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(all_files)

if cached_nodes or cached_edges:
    Path('dummyindex-out/.dummyindex_cached.json').write_text(json.dumps({'nodes': cached_nodes, 'edges': cached_edges, 'hyperedges': cached_hyperedges}))
Path('dummyindex-out/.dummyindex_uncached.txt').write_text('\n'.join(uncached))
print(f'Cache: {len(all_files)-len(uncached)} hit, {len(uncached)} need extraction')
"
```

For each chunk of uncached files (20-25 files per chunk), dispatch a subagent with this prompt:

```
You are a dummyindex extraction subagent. Read the files listed and extract a knowledge graph fragment.
Output ONLY valid JSON: {"nodes": [...], "edges": [...], "hyperedges": [...]}

Each node: {"id": "unique_id", "label": "Human Name", "file_type": "code|document|paper|image"}
Each edge: {"source": "id", "target": "id", "relation": "verb_phrase", "confidence": "EXTRACTED|INFERRED|AMBIGUOUS"}
hyperedges: [] unless you find a genuine group relationship

Files:
FILE_LIST
```

Collect all subagent responses and merge them:

```python
python -c "
import json
from pathlib import Path

# Merge: combine AST + cached + all semantic chunk results
all_nodes, all_edges, all_hyperedges = [], [], []

ast = json.loads(Path('dummyindex-out/.dummyindex_ast.json').read_text())
all_nodes.extend(ast.get('nodes', []))
all_edges.extend(ast.get('edges', []))

cached_path = Path('dummyindex-out/.dummyindex_cached.json')
if cached_path.exists():
    cached = json.loads(cached_path.read_text())
    all_nodes.extend(cached.get('nodes', []))
    all_edges.extend(cached.get('edges', []))
    all_hyperedges.extend(cached.get('hyperedges', []))

# PASTE each subagent response here as chunk_1, chunk_2, etc.
for chunk_json in []:  # replace [] with your chunk results
    chunk = json.loads(chunk_json) if isinstance(chunk_json, str) else chunk_json
    all_nodes.extend(chunk.get('nodes', []))
    all_edges.extend(chunk.get('edges', []))
    all_hyperedges.extend(chunk.get('hyperedges', []))

merged = {'nodes': all_nodes, 'edges': all_edges, 'hyperedges': all_hyperedges, 'input_tokens': 0, 'output_tokens': 0}
Path('dummyindex-out/.dummyindex_extract.json').write_text(json.dumps(merged, indent=2))
print(f'Merged: {len(all_nodes)} nodes, {len(all_edges)} edges')
"
```

### Step 4 - Build graph and cluster

```python
python -c "
import json
from dummyindex.pipeline.build import build_from_json
from dummyindex.analysis.cluster import cluster
from dummyindex.analysis.analyze import god_nodes, surprising_connections
from pathlib import Path

extraction = json.loads(Path('dummyindex-out/.dummyindex_extract.json').read_text())
G = build_from_json(extraction)
communities = cluster(G)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)

import networkx as nx
from networkx.readwrite import json_graph
graph_data = json_graph.node_link_data(G)
Path('dummyindex-out/graph.json').write_text(json.dumps(graph_data, indent=2))
Path('dummyindex-out/.dummyindex_analysis.json').write_text(json.dumps({
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {},
    'god_nodes': gods,
    'surprises': surprises,
}, indent=2))
print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')
print(f'God nodes: {[g[\"label\"] for g in gods[:5]]}')
"
```

### Step 5 - Generate report and visualization

```python
python -c "
import json
from dummyindex.pipeline.build import build_from_json
from dummyindex.analysis.cluster import cluster
from dummyindex.analysis.analyze import god_nodes, surprising_connections
from dummyindex.analysis.report import generate
from pathlib import Path

extraction = json.loads(Path('dummyindex-out/.dummyindex_extract.json').read_text())
analysis = json.loads(Path('dummyindex-out/.dummyindex_analysis.json').read_text())

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)

report = generate(G, communities, {}, {}, gods, surprises, extraction)
Path('dummyindex-out/GRAPH_REPORT.md').write_text(report)
print('GRAPH_REPORT.md written')
"
```

```python
python -c "
import json
from dummyindex.pipeline.build import build_from_json
from dummyindex.analysis.cluster import cluster
from dummyindex.pipeline.export import to_html
from pathlib import Path

extraction = json.loads(Path('dummyindex-out/.dummyindex_extract.json').read_text())
G = build_from_json(extraction)
communities = cluster(G)

try:
    to_html(G, communities, 'dummyindex-out/graph.html')
    print('graph.html written')
except ValueError as e:
    print(f'Visualization skipped: {e}')
"
```

### Step 6a - Structure graph (always, when code files exist)

Generates a top-down collapsible graph of the codebase (folder -> file -> class -> function/method) with the original cross-edges (calls, imports, inherits, uses) overlayed. Runs independently of the main graph — does not modify `graph.json`. Skips silently if the corpus has no code files.

```python
python -c "
import json
from pathlib import Path

from dummyindex.pipeline.structure import build_structure
from dummyindex.pipeline.export import to_structure_json, to_structure_html

extraction = json.loads(Path('dummyindex-out/.dummyindex_extract.json').read_text())

code_sources = {
    n.get('source_file')
    for n in extraction.get('nodes', [])
    if n.get('file_type') == 'code' and n.get('source_file')
}
code_files = [Path(s) for s in sorted(code_sources)]

if not code_files and Path('dummyindex-out/.dummyindex_detect.json').exists():
    detect = json.loads(Path('dummyindex-out/.dummyindex_detect.json').read_text())
    code_files = [Path(f) for f in detect.get('files', {}).get('code', [])]

if not code_files:
    print('structure graph skipped (no code files)')
else:
    structure = build_structure(extraction, code_files, Path('INPUT_PATH'))
    to_structure_json(structure, 'dummyindex-out/structure_graph.json')
    to_structure_html(structure, 'dummyindex-out/structure_graph.html')
    nodes = len(structure['nodes'])
    hier = len(structure['hierarchy_edges'])
    cross = len(structure['cross_edges'])
    print(f'structure_graph.html + structure_graph.json written ({nodes} nodes, {hier} hierarchy, {cross} cross)')
"
```

Replace INPUT_PATH with the actual path the user provided.

### Step 6a-classify - Reclassify generic `references` edges with the LLM

The structure builder emits language-agnostic `references` edges with an `offset:<n>` marker pointing at the textual mention site. Replace those generic relations with semantically meaningful, context-derived labels using subagents. No predefined vocabulary — let the model name the relation from what it sees.

The classification is informed by both the new structure graph and the main graph (community labels, god nodes) so each label reflects how the link sits in the broader codebase, not just the local snippet.

Skip this step entirely if `dummyindex-out/structure_graph.json` does not exist.

**Step 1 - Extract context windows for every generic `references` edge:**

```python
python -c "
import json
from pathlib import Path

sg_path = Path('dummyindex-out/structure_graph.json')
if not sg_path.exists():
    print('no structure_graph.json - skipping classification')
    raise SystemExit(0)

structure = json.loads(sg_path.read_text())
nodes_by_id = {n['id']: n for n in structure.get('nodes', [])}
root_input = Path('INPUT_PATH')
root_abs = root_input.resolve() if root_input.is_absolute() else (Path.cwd() / root_input).resolve()

WINDOW = 200

todo = []
for i, e in enumerate(structure.get('cross_edges', [])):
    if e.get('relation') != 'references':
        continue
    loc = e.get('source_location', '') or ''
    if not loc.startswith('offset:'):
        continue
    try:
        offset = int(loc.split(':', 1)[1])
    except (ValueError, IndexError):
        continue
    src_node = nodes_by_id.get(e['source'])
    tgt_node = nodes_by_id.get(e['target'])
    if not src_node or not tgt_node:
        continue
    src_rel = src_node.get('source_file') or e.get('source_file') or ''
    tgt_rel = tgt_node.get('source_file') or ''
    if not src_rel or not tgt_rel:
        continue
    src_path = root_abs / src_rel
    if not src_path.exists():
        continue
    try:
        text = src_path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        continue
    start = max(0, offset - WINDOW)
    end = min(len(text), offset + WINDOW)
    todo.append({
        'edge_index': i, 'source_id': e['source'], 'target_id': e['target'],
        'source_file': src_rel, 'target_file': tgt_rel, 'snippet': text[start:end],
    })

context = {'community_labels': {}, 'god_nodes': []}
labels_path = Path('dummyindex-out/.dummyindex_labels.json')
if labels_path.exists():
    try: context['community_labels'] = json.loads(labels_path.read_text())
    except Exception: pass
analysis_path = Path('dummyindex-out/.dummyindex_analysis.json')
if analysis_path.exists():
    try:
        an = json.loads(analysis_path.read_text())
        context['god_nodes'] = [g.get('label') for g in an.get('gods', [])][:20]
    except Exception: pass

Path('dummyindex-out/.dummyindex_classify_todo.json').write_text(json.dumps({'todo': todo, 'context': context}))
print(f'classify todo: {len(todo)} edges')
"
```

Replace `INPUT_PATH` with the actual path. If the printed count is `0`, skip the rest.

**Step 2 - Dispatch one subagent per batch (≤30 entries each) in parallel.** Each subagent receives `BATCH_JSON` plus the `context` dict, and writes its output to `dummyindex-out/.dummyindex_classify_<N>.json`. Use `subagent_type="general-purpose"`. The prompt is identical to the claude variant — see `skill.md` Step 6a-classify Step 2.

**Step 3 - Merge results back and re-render the HTML:**

```python
python -c "
import json, glob
from pathlib import Path
from dummyindex.pipeline.export import to_structure_html

sg_path = Path('dummyindex-out/structure_graph.json')
structure = json.loads(sg_path.read_text())
edges = structure.get('cross_edges', [])

updated = 0
for chunk_path in glob.glob('dummyindex-out/.dummyindex_classify_*.json'):
    try: chunk = json.loads(Path(chunk_path).read_text())
    except Exception: continue
    for r in chunk.get('results', []):
        idx = r.get('edge_index')
        rel = (r.get('relation') or '').strip()
        if rel and isinstance(idx, int) and 0 <= idx < len(edges):
            if edges[idx].get('relation') == 'references' and rel != 'references':
                edges[idx]['relation'] = rel
                updated += 1

edges.sort(key=lambda e: (e['source'], e['target'], e['relation'], e.get('source_location', '')))
structure['cross_edges'] = edges
sg_path.write_text(json.dumps(structure, indent=2))
to_structure_html(structure, 'dummyindex-out/structure_graph.html')
print(f'reclassified {updated} edges -> structure_graph.html re-rendered')
"
```

Then delete `dummyindex-out/.dummyindex_classify_*.json`.

### Step 6c - Flow hypergraph (always, when code files exist)

Synthesize end-to-end execution flows (HTTP routes, CLI commands, scheduled jobs, …) and name each one via a subagent batch with main-graph community labels + god nodes as advisory context. Skip if no `calls` edges exist.

**Step 1 - Synthesize flows + prepare naming todo:**

```python
python -c "
import json
from pathlib import Path
from dummyindex.pipeline.build import build_from_json
from dummyindex.analysis.flows import synthesize_flows
from dummyindex.analysis.flow_naming import prepare_naming_todo
from dummyindex.analysis.analyze import god_nodes

extract_path = Path('dummyindex-out/.dummyindex_extract.json')
if not extract_path.exists():
    raise SystemExit(0)
extraction = json.loads(extract_path.read_text())
G = build_from_json(extraction)
flows = synthesize_flows(G)
if not flows:
    raise SystemExit(0)
labels_path = Path('dummyindex-out/.dummyindex_labels.json')
community_labels = {}
if labels_path.exists():
    try: community_labels = {int(k): v for k, v in json.loads(labels_path.read_text()).items()}
    except Exception: community_labels = {}
gods = god_nodes(G)
todo = prepare_naming_todo(flows, G, 'dummyindex-out', god_nodes=gods, community_labels=community_labels)
Path('dummyindex-out/.dummyindex_flows_pending.json').write_text(json.dumps(flows))
print(f'flows: {todo[\"stats\"]}')
"
```

If `to_name` is `0`, skip Step 2.

**Step 2 - Dispatch one subagent per batch (≤30 entries each) in parallel.** Each subagent reads its batch from `.dummyindex_flow_names_todo.json`, receives the `context` dict, and writes `{"results":[{"flow_id":"...","name":"<2-5 words>","description":"..."}, ...]}` to `dummyindex-out/.dummyindex_flow_names_<N>.json`. Use `subagent_type="general-purpose"`. The prompt is identical to the claude variant — see `skill.md` Step 6c Step 2.

**Step 3 - Merge results, write flow_graph.{json,html}, attach to graph.json:**

```python
python -c "
import json, glob
from pathlib import Path
from dummyindex.pipeline.build import build_from_json
from dummyindex.analysis.flows import overlap_index
from dummyindex.analysis.flow_naming import apply_named_results, write_naming_results
from dummyindex.pipeline.export import to_flow_json, to_flow_html, attach_hyperedges, to_json

fresh = []
for chunk in glob.glob('dummyindex-out/.dummyindex_flow_names_*.json'):
    if chunk.endswith('todo.json') or chunk.endswith('results.json') or chunk.endswith('cached_names.json'):
        continue
    try: payload = json.loads(Path(chunk).read_text())
    except Exception: continue
    fresh.extend(payload.get('results', []) if isinstance(payload, dict) else [])
write_naming_results('dummyindex-out', fresh)

flows = json.loads(Path('dummyindex-out/.dummyindex_flows_pending.json').read_text())
extraction = json.loads(Path('dummyindex-out/.dummyindex_extract.json').read_text())
G = build_from_json(extraction)
named = apply_named_results(flows, G, 'dummyindex-out', fresh_results=fresh)
attach_hyperedges(G, named)
index = overlap_index(named)
to_flow_json(named, G, 'dummyindex-out/flow_graph.json', overlap_index=index)
to_flow_html(named, G, 'dummyindex-out/flow_graph.html', overlap_index=index)
analysis = json.loads(Path('dummyindex-out/.dummyindex_analysis.json').read_text())
communities = {int(k): v for k, v in analysis['communities'].items()}
to_json(G, communities, 'dummyindex-out/graph.json')
print(f'flow_graph.html written ({len(named)} flows)')
"
```

Then delete `dummyindex-out/.dummyindex_flow_names_todo.json`, `.dummyindex_flow_names_results.json`, `.dummyindex_flow_names_*.json`, `.dummyindex_flows_pending.json`. The cache file `.dummyindex_flow_names.json` is preserved for cross-run reuse.

### After completing all steps

Print this summary:

```
dummyindex complete
  structure_graph.html — top-down collapsible code structure (start here for codebase navigation)
  structure_graph.json — folder → file → class → function with cross-edges
  graph.html           — interactive community/architectural view
  GRAPH_REPORT.md      — plain-language architecture summary (god nodes, communities)
  graph.json           — GraphRAG-ready, queryable by MCP or CLI
```

When working on this codebase later, navigate `structure_graph.json` first to find the relevant folder/file/class/function, then consult `graph.json` (or `GRAPH_REPORT.md`) for community/architectural context before reading raw files.

Read `dummyindex-out/GRAPH_REPORT.md` and share the **God Nodes** and **Surprising Connections** sections directly in the chat — do not ask the user to open the file themselves.
