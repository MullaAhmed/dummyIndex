# validate extraction JSON against the dummyindex schema before graph assembly
from __future__ import annotations

from ..enums import ConfidenceLevel

SCHEMA_VERSION = "1.3"

VALID_FILE_TYPES = {"code", "document", "paper", "image", "rationale"}
VALID_CONFIDENCES: frozenset[str] = frozenset(
    c.value for c in (
        ConfidenceLevel.EXTRACTED,
        ConfidenceLevel.INFERRED,
        ConfidenceLevel.AMBIGUOUS,
    )
)
VALID_HYPEREDGE_KINDS = {"flow", "feature", "generic"}
VALID_ENTRY_KINDS = {
    "http_route", "cli_command", "scheduled_job", "event_handler",
    "test", "library_export", "internal",
}
VALID_FEATURE_ROLES = {"core", "entry", "terminal", "shared", "rationale", "data"}
REQUIRED_NODE_FIELDS = {"id", "label", "file_type", "source_file"}
REQUIRED_EDGE_FIELDS = {"source", "target", "relation", "confidence", "source_file"}
REQUIRED_HYPEREDGE_FIELDS = {"id", "label", "nodes"}


def validate_extraction(data: dict) -> list[str]:
    """
    Validate an extraction JSON dict against the dummyindex schema.
    Returns a list of error strings - empty list means valid.
    """
    if not isinstance(data, dict):
        return ["Extraction must be a JSON object"]

    errors: list[str] = []

    # Nodes
    if "nodes" not in data:
        errors.append("Missing required key 'nodes'")
    elif not isinstance(data["nodes"], list):
        errors.append("'nodes' must be a list")
    else:
        for i, node in enumerate(data["nodes"]):
            if not isinstance(node, dict):
                errors.append(f"Node {i} must be an object")
                continue
            for field in REQUIRED_NODE_FIELDS:
                if field not in node:
                    errors.append(f"Node {i} (id={node.get('id', '?')!r}) missing required field '{field}'")
            if "file_type" in node and node["file_type"] not in VALID_FILE_TYPES:
                errors.append(
                    f"Node {i} (id={node.get('id', '?')!r}) has invalid file_type "
                    f"'{node['file_type']}' - must be one of {sorted(VALID_FILE_TYPES)}"
                )

    # Edges - accept "links" (NetworkX <= 3.1) as fallback for "edges"
    edge_list = data.get("edges") if "edges" in data else data.get("links")
    if edge_list is None:
        errors.append("Missing required key 'edges'")
    elif not isinstance(edge_list, list):
        errors.append("'edges' must be a list")
    else:
        node_ids = {n["id"] for n in data.get("nodes", []) if isinstance(n, dict) and "id" in n}
        for i, edge in enumerate(edge_list):
            if not isinstance(edge, dict):
                errors.append(f"Edge {i} must be an object")
                continue
            for field in REQUIRED_EDGE_FIELDS:
                if field not in edge:
                    errors.append(f"Edge {i} missing required field '{field}'")
            if "confidence" in edge and edge["confidence"] not in VALID_CONFIDENCES:
                errors.append(
                    f"Edge {i} has invalid confidence '{edge['confidence']}' "
                    f"- must be one of {sorted(VALID_CONFIDENCES)}"
                )
            if "source" in edge and node_ids and edge["source"] not in node_ids:
                errors.append(f"Edge {i} source '{edge['source']}' does not match any node id")
            if "target" in edge and node_ids and edge["target"] not in node_ids:
                errors.append(f"Edge {i} target '{edge['target']}' does not match any node id")

    # Hyperedges (optional). Schema 1.2 introduces flow hyperedges with extra
    # fields; legacy hyperedges remain valid because all extras are optional.
    hyperedges = data.get("hyperedges")
    if hyperedges is not None:
        if not isinstance(hyperedges, list):
            errors.append("'hyperedges' must be a list")
        else:
            node_ids = {n["id"] for n in data.get("nodes", []) if isinstance(n, dict) and "id" in n}
            errors.extend(_validate_hyperedges(hyperedges, node_ids))

    return errors


def _validate_hyperedges(hyperedges: list, node_ids: set[str]) -> list[str]:
    errors: list[str] = []
    for i, h in enumerate(hyperedges):
        if not isinstance(h, dict):
            errors.append(f"Hyperedge {i} must be an object")
            continue
        for field in REQUIRED_HYPEREDGE_FIELDS:
            if field not in h:
                errors.append(f"Hyperedge {i} (id={h.get('id', '?')!r}) missing required field '{field}'")
        if "kind" in h and h["kind"] not in VALID_HYPEREDGE_KINDS:
            errors.append(
                f"Hyperedge {i} (id={h.get('id', '?')!r}) has invalid kind "
                f"'{h['kind']}' - must be one of {sorted(VALID_HYPEREDGE_KINDS)}"
            )
        if "entry_kind" in h and h["entry_kind"] not in VALID_ENTRY_KINDS:
            errors.append(
                f"Hyperedge {i} (id={h.get('id', '?')!r}) has invalid entry_kind "
                f"'{h['entry_kind']}' - must be one of {sorted(VALID_ENTRY_KINDS)}"
            )
        if "confidence" in h and h["confidence"] not in VALID_CONFIDENCES:
            errors.append(
                f"Hyperedge {i} (id={h.get('id', '?')!r}) has invalid confidence "
                f"'{h['confidence']}' - must be one of {sorted(VALID_CONFIDENCES)}"
            )
        if isinstance(h.get("nodes"), list) and node_ids:
            for nid in h["nodes"]:
                if nid not in node_ids:
                    errors.append(
                        f"Hyperedge {i} (id={h.get('id', '?')!r}) references unknown node '{nid}'"
                    )
                    break
        if "sequence" in h:
            if not isinstance(h["sequence"], list):
                errors.append(f"Hyperedge {i} 'sequence' must be a list")
            else:
                for j, step in enumerate(h["sequence"]):
                    if not isinstance(step, dict):
                        errors.append(f"Hyperedge {i} sequence[{j}] must be an object")
                        continue
                    if "source" not in step or "target" not in step:
                        errors.append(f"Hyperedge {i} sequence[{j}] missing 'source' or 'target'")
        # Feature-specific: members[].role must be a known role.
        if h.get("kind") == "feature" and "members" in h:
            if not isinstance(h["members"], list):
                errors.append(f"Hyperedge {i} 'members' must be a list")
            else:
                for j, m in enumerate(h["members"]):
                    if not isinstance(m, dict):
                        errors.append(f"Hyperedge {i} members[{j}] must be an object")
                        continue
                    if "node_id" not in m:
                        errors.append(f"Hyperedge {i} members[{j}] missing 'node_id'")
                    if "role" in m and m["role"] not in VALID_FEATURE_ROLES:
                        errors.append(
                            f"Hyperedge {i} members[{j}] has invalid role "
                            f"'{m['role']}' - must be one of {sorted(VALID_FEATURE_ROLES)}"
                        )
                    if "weight" in m:
                        try:
                            w = float(m["weight"])
                            if not (0.0 < w <= 1.0):
                                errors.append(f"Hyperedge {i} members[{j}] weight {w} out of (0,1]")
                        except (TypeError, ValueError):
                            errors.append(f"Hyperedge {i} members[{j}] weight is not a number")
    return errors
