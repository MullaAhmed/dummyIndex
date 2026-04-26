"""Flow Hypergraph synthesis — Feature 2.

Pure, deterministic derivation of end-to-end execution flows from the
already-built call graph. No I/O, no LLM. The naming pass lives in
``flow_naming.py``; the renderer lives in ``pipeline.export``.

A flow is a single hyperedge: a named, ordered, end-to-end set of calls
that begins at an *entry point* (an HTTP route, CLI command, scheduled
job, event handler, test, library export, or otherwise-internal entry
function) and terminates at one or more *terminals* (a leaf, an I/O call,
the depth bound, or a cycle break).

Public entry points:

- ``synthesize_flows(G, config=None) -> list[dict]`` — run the full
  pipeline (entry detection → DFS → merge → rank) and return flow
  hyperedges ready to attach via ``pipeline.export.attach_hyperedges``.
- ``detect_entry_points(G, config=None) -> list[EntryPoint]``
- ``derive_flow(G, entry, config=None) -> dict | None``

Determinism is a hard contract (PRD SC-4). Every iteration over graph
elements is sorted by ID before traversal, every tie-break is by
``source_location`` then target ID, and every flow ID is a hash of the
canonical sequence (sorted (source, target) pairs).
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath
from typing import Callable, Iterable

import networkx as nx


SCHEMA_VERSION = "1.2"

VALID_ENTRY_KINDS = (
    "http_route", "cli_command", "scheduled_job", "event_handler",
    "test", "library_export", "internal",
)

_ENTRY_WEIGHTS: dict[str, float] = {
    "http_route": 1.0,
    "cli_command": 0.9,
    "scheduled_job": 0.8,
    "event_handler": 0.7,
    "library_export": 0.6,
    "internal": 0.5,
    "test": 0.4,
}

_DEFAULT_MAX_DEPTH = 10
_DEFAULT_FLOW_LIMIT = 100
_DEFAULT_MERGE_OVERLAP = 0.95
_DEFAULT_SALIENCE_FLOOR = 0.1


@dataclass(frozen=True)
class FlowConfig:
    """Knobs for the synthesis pipeline. Every field has a stable default."""

    max_depth: int = _DEFAULT_MAX_DEPTH
    flow_limit: int = _DEFAULT_FLOW_LIMIT
    merge_overlap_threshold: float = _DEFAULT_MERGE_OVERLAP
    salience_floor: float = _DEFAULT_SALIENCE_FLOOR
    enable_inferred_edges: bool = True


@dataclass(frozen=True)
class EntryPoint:
    """A function/method node identified as a flow start."""

    node_id: str
    label: str
    source_file: str
    entry_kind: str

    def with_kind(self, entry_kind: str) -> "EntryPoint":
        return replace(self, entry_kind=entry_kind)


# --------------------------------------------------------------------------- #
# Node classification — derived from the existing graph attrs (no node_kind).
# --------------------------------------------------------------------------- #

_METHOD_LABEL_RE = re.compile(r"^\..+\(\)$")
_FUNCTION_LABEL_RE = re.compile(r"^[A-Za-z_][\w]*\(\)$")


def _is_callable_node(G: nx.Graph, node_id: str) -> bool:
    """Function-or-method heuristic. Mirrors ``analyze._is_file_node`` logic
    in reverse: a node whose label looks like ``foo()`` or ``.bar()``."""
    attrs = G.nodes[node_id]
    label = attrs.get("label", "")
    if not isinstance(label, str) or not label:
        return False
    if _METHOD_LABEL_RE.match(label):
        return True
    if _FUNCTION_LABEL_RE.match(label):
        return True
    return False


def _is_file_node(G: nx.Graph, node_id: str) -> bool:
    attrs = G.nodes[node_id]
    label = attrs.get("label", "")
    source_file = attrs.get("source_file", "")
    if not source_file or not label:
        return False
    return label == PurePosixPath(source_file).name or label == source_file.rsplit("/", 1)[-1]


# --------------------------------------------------------------------------- #
# Entry-point detection.
# --------------------------------------------------------------------------- #

# I/O terminator detection runs over edge target labels — language-agnostic
# patterns that cover the most common cases. Per PRD §6.4 / TECHNICAL §5.3
# this is heuristic; ambiguity downgrades confidence rather than blocks.
_IO_TERMINATOR_PATTERNS = (
    # network
    r"^\.?(fetch|axios|request|requests|httpx|urllib|http|reqwest)\b",
    r"^\.?(get|post|put|delete|patch|head)\(\)$",
    # database
    r"^\.?(query|execute|exec|run|fetchall|fetchone|find_one|find_many)\(\)$",
    r"^\.?(insert|update|delete|save|commit|rollback)\(\)$",
    # logging
    r"^\.?(log|logger|logging|info|debug|warn|warning|error|critical)\b",
    r"^\.?print\(\)$",
    r"^\.?console\.",
    # filesystem / process
    r"^\.?(open|read|write|close|remove|unlink)\(\)$",
    r"^\.?(subprocess|exec|spawn|system|popen)\b",
    # message queues / cloud
    r"^\.?(publish|emit|send|consume|subscribe)\(\)$",
    r"^\.?(boto3|kafka|redis|celery)\b",
)
_IO_RE = tuple(re.compile(p) for p in _IO_TERMINATOR_PATTERNS)


def _looks_like_io(label: str) -> bool:
    if not label:
        return False
    return any(rx.match(label) for rx in _IO_RE)


# Per-language framework hint patterns. These are intentionally simple and
# match against either the label, the source_file name, or the node's
# annotations (when available). Detectors return entry_kind or None.
EntryDetector = Callable[[dict, nx.Graph], "str | None"]


def _detect_http_route(node: dict, G: nx.Graph) -> str | None:
    label = node.get("label", "")
    annotations = node.get("annotations", []) or []
    decorator_text = " ".join(str(a) for a in annotations if a)
    blob = f"{label} {decorator_text}"
    patterns = (
        r"@(app|router|blueprint|api)\.(get|post|put|delete|patch|route)",
        r"@(Get|Post|Put|Delete|Patch|RequestMapping|Controller)Mapping?",
        r"#\[(get|post|put|delete|patch)\(",
        r"http\.HandleFunc",
        r"r\.Handle",
        r"app\.(get|post|put|delete|patch)",
        r"\.route\(",
    )
    for pat in patterns:
        if re.search(pat, blob, re.IGNORECASE):
            return "http_route"
    return None


def _detect_cli_command(node: dict, G: nx.Graph) -> str | None:
    label = node.get("label", "")
    source_file = node.get("source_file", "") or ""
    annotations = node.get("annotations", []) or []
    decorator_text = " ".join(str(a) for a in annotations if a)
    blob = f"{label} {decorator_text}"
    if re.search(r"@click\.command|@cli\.command|argparse|cobra\.Command", blob, re.IGNORECASE):
        return "cli_command"
    if source_file.endswith("__main__.py") and label in ("main()", ".main()"):
        return "cli_command"
    if PurePosixPath(source_file).parent.name == "bin":
        return "cli_command"
    return None


def _detect_scheduled_job(node: dict, G: nx.Graph) -> str | None:
    annotations = node.get("annotations", []) or []
    blob = " ".join(str(a) for a in annotations if a)
    if re.search(r"@(shared_task|task|celery|cron|schedule|lambda_handler)", blob, re.IGNORECASE):
        return "scheduled_job"
    return None


def _detect_event_handler(node: dict, G: nx.Graph) -> str | None:
    label = node.get("label", "")
    annotations = node.get("annotations", []) or []
    blob = f"{label} {' '.join(str(a) for a in annotations if a)}"
    if re.search(r"addEventListener|@(EventListener|receiver|signal)", blob, re.IGNORECASE):
        return "event_handler"
    return None


def _detect_test(node: dict, G: nx.Graph) -> str | None:
    label = node.get("label", "")
    source_file = node.get("source_file", "") or ""
    name = label.lstrip(".").rstrip("()")
    if not name:
        return None
    if name.startswith("test_") or name.startswith("Test"):
        return "test"
    if "/test" in source_file or source_file.endswith("_test.go") or source_file.endswith(".test.ts"):
        if _METHOD_LABEL_RE.match(label) or _FUNCTION_LABEL_RE.match(label):
            return "test"
    return None


def _detect_library_export(node: dict, G: nx.Graph) -> str | None:
    source_file = node.get("source_file", "") or ""
    if PurePosixPath(source_file).name in ("__init__.py", "index.ts", "index.js", "lib.rs", "mod.rs"):
        return "library_export"
    return None


_DEFAULT_DETECTORS: tuple[EntryDetector, ...] = (
    _detect_http_route,
    _detect_cli_command,
    _detect_scheduled_job,
    _detect_event_handler,
    _detect_test,
    _detect_library_export,
)


def detect_entry_points(
    G: nx.Graph,
    config: FlowConfig | None = None,
    detectors: Iterable[EntryDetector] = _DEFAULT_DETECTORS,
) -> list[EntryPoint]:
    """Return entry points sorted by (entry_kind weight desc, node_id asc)."""
    config = config or FlowConfig()
    found: list[EntryPoint] = []
    for node_id in sorted(G.nodes()):
        if not _is_callable_node(G, node_id):
            continue
        attrs = dict(G.nodes[node_id])
        attrs.setdefault("id", node_id)
        kind: str | None = None
        for detector in detectors:
            kind = detector(attrs, G)
            if kind is not None:
                break
        if kind is None:
            kind = _internal_entry_fallback(G, node_id)
        if kind is None:
            continue
        found.append(EntryPoint(
            node_id=node_id,
            label=attrs.get("label", node_id),
            source_file=attrs.get("source_file", ""),
            entry_kind=kind,
        ))
    found.sort(key=lambda e: (-_ENTRY_WEIGHTS.get(e.entry_kind, 0.0), e.node_id))
    return found


def _internal_entry_fallback(G: nx.Graph, node_id: str) -> str | None:
    """A function with zero in-edges from ``calls`` is a candidate internal entry."""
    in_calls = 0
    for u, v, data in G.in_edges(node_id, data=True) if G.is_directed() else _undirected_in_edges(G, node_id):
        if data.get("relation") == "calls":
            in_calls += 1
    if in_calls > 0:
        return None
    out_calls = sum(
        1 for _, _, d in (G.out_edges(node_id, data=True) if G.is_directed() else _undirected_out_edges(G, node_id))
        if d.get("relation") == "calls"
    )
    if out_calls == 0:
        return None
    return "internal"


def _undirected_in_edges(G: nx.Graph, node_id: str):
    for u, v, d in G.edges(node_id, data=True):
        if v == node_id:
            yield u, v, d


def _undirected_out_edges(G: nx.Graph, node_id: str):
    for u, v, d in G.edges(node_id, data=True):
        if u == node_id:
            yield u, v, d


# --------------------------------------------------------------------------- #
# Flow derivation — source-order DFS.
# --------------------------------------------------------------------------- #


def _outgoing_call_edges(G: nx.Graph, node_id: str) -> list[tuple[str, str, dict]]:
    edges: list[tuple[str, str, dict]] = []
    if G.is_directed():
        iterator = G.out_edges(node_id, data=True)
    else:
        iterator = ((u, v, d) for u, v, d in G.edges(node_id, data=True) if u == node_id)
    for u, v, data in iterator:
        if data.get("relation") != "calls":
            continue
        edges.append((u, v, data))
    edges.sort(key=lambda e: (str(e[2].get("source_location") or ""), e[1]))
    return edges


def derive_flow(
    G: nx.Graph,
    entry: EntryPoint,
    config: FlowConfig | None = None,
) -> dict | None:
    """Derive a single flow hyperedge from one entry point. Returns the
    hyperedge dict (without a name yet) or ``None`` if traversal yielded
    nothing."""
    config = config or FlowConfig()
    visited: list[str] = [entry.node_id]
    visited_set: set[str] = {entry.node_id}
    sequence: list[dict] = []
    terminals: list[str] = []
    alt_paths: list[dict] = []
    confidences: list[str] = []
    max_depth_seen = 0

    def visit(node_id: str, depth: int) -> None:
        nonlocal max_depth_seen
        max_depth_seen = max(max_depth_seen, depth)
        if depth >= config.max_depth:
            terminals.append(node_id)
            return
        children = _outgoing_call_edges(G, node_id)
        if not children:
            terminals.append(node_id)
            return
        for u, v, data in children:
            confidence = data.get("confidence", "EXTRACTED")
            if not config.enable_inferred_edges and confidence != "EXTRACTED":
                continue
            confidences.append(confidence)
            step = {
                "source": u,
                "target": v,
                "relation": "calls",
                "confidence": confidence,
                "source_location": data.get("source_location", ""),
            }
            sequence.append(step)
            if v in visited_set:
                # cycle break: log alt-path metadata and continue siblings
                alt_paths.append({"step": len(sequence) - 1, "reason": "cycle", "target": v})
                continue
            visited.append(v)
            visited_set.add(v)
            child_label = G.nodes[v].get("label", "")
            if _looks_like_io(child_label):
                terminals.append(v)
                continue
            visit(v, depth + 1)

    visit(entry.node_id, 0)

    if not sequence and not terminals:
        terminals.append(entry.node_id)

    flow_confidence = _aggregate_confidence(confidences)
    salience = _compute_salience(entry.entry_kind, visited, G)

    flow_id = _flow_id(entry, sequence)

    return {
        "id": flow_id,
        "label": flow_id,  # provisional; flow_naming.py replaces with human label
        "kind": "flow",
        "entry_kind": entry.entry_kind,
        "entry_nodes": [entry.node_id],
        "exit_nodes": _dedupe(terminals),
        "nodes": _dedupe(visited),
        "sequence": sequence,
        "alt_paths": alt_paths,
        "depth": max_depth_seen,
        "salience": salience,
        "confidence": flow_confidence,
    }


def _aggregate_confidence(confidences: list[str]) -> str:
    if not confidences:
        return "EXTRACTED"
    if "AMBIGUOUS" in confidences:
        return "AMBIGUOUS"
    if "INFERRED" in confidences:
        return "INFERRED"
    return "EXTRACTED"


def _compute_salience(entry_kind: str, participants: list[str], G: nx.Graph) -> float:
    weight = _ENTRY_WEIGHTS.get(entry_kind, 0.5)
    count = max(1, len(participants))
    files = {G.nodes[n].get("source_file", "") for n in participants if n in G.nodes}
    files.discard("")
    cross_module_bonus = min(0.5, 0.1 * max(0, len(files) - 1))
    return round(weight * math.log2(1 + count) * (1.0 + cross_module_bonus), 4)


def _dedupe(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _flow_id(entry: EntryPoint, sequence: list[dict]) -> str:
    canonical = sorted((step["source"], step["target"]) for step in sequence)
    payload = "|".join([entry.entry_kind, entry.node_id] + [f"{s}>{t}" for s, t in canonical])
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"flow:{digest}"


# --------------------------------------------------------------------------- #
# Merge rules (PRD §6.6 / TECHNICAL §5.4).
# --------------------------------------------------------------------------- #


def merge_flows(flows: list[dict], threshold: float = _DEFAULT_MERGE_OVERLAP) -> list[dict]:
    """Apply full-equivalence, high-overlap, and subset-collapse merges
    iteratively until stable. Inputs are not mutated; a new list of new
    flow dicts is returned (immutability rule)."""
    pool = [_clone_flow(f) for f in flows]
    changed = True
    while changed:
        changed = False
        next_pool: list[dict] = []
        skipped: set[int] = set()
        for i, a in enumerate(pool):
            if i in skipped:
                continue
            merged = a
            for j in range(i + 1, len(pool)):
                if j in skipped:
                    continue
                b = pool[j]
                action = _merge_action(merged, b, threshold)
                if action == "equivalent":
                    merged = _merge_entries(merged, b)
                    skipped.add(j)
                    changed = True
                elif action == "high_overlap":
                    higher, lower = (merged, b) if merged["salience"] >= b["salience"] else (b, merged)
                    merged = _merge_entries(higher, lower)
                    skipped.add(j)
                    changed = True
                elif action == "subset_a_in_b":
                    merged = _merge_entries(b, merged)
                    skipped.add(j)
                    changed = True
                elif action == "subset_b_in_a":
                    merged = _merge_entries(merged, b)
                    skipped.add(j)
                    changed = True
            next_pool.append(merged)
        pool = next_pool
    return pool


def _clone_flow(flow: dict) -> dict:
    out = dict(flow)
    for key in ("entry_nodes", "exit_nodes", "nodes", "sequence", "alt_paths"):
        if key in out and out[key] is not None:
            out[key] = list(out[key])
    return out


def _merge_action(a: dict, b: dict, threshold: float) -> str | None:
    a_nodes = set(a.get("nodes", []))
    b_nodes = set(b.get("nodes", []))
    if not a_nodes or not b_nodes:
        return None
    if a_nodes == b_nodes and _sequences_equal(a.get("sequence", []), b.get("sequence", [])):
        return "equivalent"
    union = a_nodes | b_nodes
    inter = a_nodes & b_nodes
    if union and len(inter) / len(union) >= threshold:
        return "high_overlap"
    a_seq = _seq_pairs(a.get("sequence", []))
    b_seq = _seq_pairs(b.get("sequence", []))
    if a_nodes < b_nodes and _is_prefix(a_seq, b_seq):
        return "subset_a_in_b"
    if b_nodes < a_nodes and _is_prefix(b_seq, a_seq):
        return "subset_b_in_a"
    return None


def _sequences_equal(a: list[dict], b: list[dict]) -> bool:
    return _seq_pairs(a) == _seq_pairs(b)


def _seq_pairs(seq: list[dict]) -> list[tuple[str, str]]:
    return [(s["source"], s["target"]) for s in seq]


def _is_prefix(short: list, long: list) -> bool:
    return len(short) <= len(long) and long[: len(short)] == short


def _merge_entries(primary: dict, secondary: dict) -> dict:
    out = _clone_flow(primary)
    entries = list(out.get("entry_nodes") or [])
    for nid in secondary.get("entry_nodes", []) or []:
        if nid not in entries:
            entries.append(nid)
    out["entry_nodes"] = entries
    return out


# --------------------------------------------------------------------------- #
# Top-level orchestrator.
# --------------------------------------------------------------------------- #


def synthesize_flows(G: nx.Graph, config: FlowConfig | None = None) -> list[dict]:
    """End-to-end: detect entries → derive flows → merge → rank → cap.

    Returns a list of flow hyperedge dicts ready to attach to ``G`` via
    ``pipeline.export.attach_hyperedges``. Flows are sorted by salience
    descending, with flow_id as tiebreaker (PRD SC-4)."""
    config = config or FlowConfig()
    entries = detect_entry_points(G, config)
    flows: list[dict] = []
    for entry in entries:
        flow = derive_flow(G, entry, config)
        if flow is None:
            continue
        if flow["salience"] < config.salience_floor:
            continue
        flows.append(flow)
    flows = merge_flows(flows, threshold=config.merge_overlap_threshold)
    flows.sort(key=lambda f: (-f["salience"], f["id"]))
    if config.flow_limit > 0:
        flows = flows[: config.flow_limit]
    return flows


# --------------------------------------------------------------------------- #
# Helpers for downstream consumers.
# --------------------------------------------------------------------------- #


def overlap_index(flows: list[dict]) -> dict[str, list[str]]:
    """node_id -> list of flow_ids that contain it. Sorted for determinism."""
    index: dict[str, list[str]] = {}
    for flow in flows:
        fid = flow["id"]
        for nid in flow.get("nodes", []) or []:
            index.setdefault(nid, []).append(fid)
    for nid in index:
        index[nid].sort()
    return dict(sorted(index.items()))
