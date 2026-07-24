"""Boundary validation for a curated `features/graph.json`.

The seed is generated; the curated scan is *authored* — by a model, in a
session, against a spec it is holding in context alongside a few thousand
lines of source. That makes it untrusted input in the ordinary sense, and
the failure modes are the ordinary ones: an edge pointing at a node that
got renamed, a `kind` invented on the spot (`"microservice"`), a label that
blows past what the viewer can render, a fourth entry in a list capped at
three.

So this reports **every** violation in one pass, each with a JSON path and
a message naming the fix. That is what makes the authoring loop closable:
`dummyindex context scan-check` prints the list, the author fixes all of
them, and re-runs — instead of discovering one error per round trip.

Pure: takes a parsed payload, returns violations, raises nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from dummyindex.context.enums import (
    ScanEdgeKind,
    ScanEvidence,
    ScanNodeKind,
    ScanViolationSeverity,
)

from ..constants import (
    MAX_EDGE_LABEL,
    MAX_NODE_DETAIL,
    MAX_NODE_GROUP,
    MAX_NODE_LABEL,
    MAX_NODE_SOURCE_REF,
    MAX_NODE_SUB,
    MAX_NODE_SYMBOL_REF,
    MAX_PROJECT_NAME,
    MAX_PROJECT_SLUG,
    MAX_PROJECT_TAGLINE,
    MAX_SCAN_EDGES,
    MAX_SCAN_NODES,
    MAX_TOP_INTEGRATIONS,
    MAX_TOP_MODELS,
    MAX_TOP_TOOLS,
    SCAN_SCHEMA_VERSION,
)
from .refs import SymbolRefIndex

_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

_NODE_KINDS = tuple(k.value for k in ScanNodeKind)
_EDGE_KINDS = tuple(k.value for k in ScanEdgeKind)
_EVIDENCE_VALUES = tuple(e.value for e in ScanEvidence)

# Optional node text fields: (json key, cap, violation code).
_NODE_TEXT_FIELDS: tuple[tuple[str, int, str], ...] = (
    ("label", MAX_NODE_LABEL, "node_label_length"),
    ("sub", MAX_NODE_SUB, "node_sub_length"),
    ("detail", MAX_NODE_DETAIL, "node_detail_length"),
    ("sourceRef", MAX_NODE_SOURCE_REF, "node_source_ref_length"),
    ("symbolRef", MAX_NODE_SYMBOL_REF, "node_symbol_ref_length"),
    ("group", MAX_NODE_GROUP, "node_group_length"),
)

_CHIP_ROWS: tuple[tuple[str, int, str], ...] = (
    ("topModels", MAX_TOP_MODELS, "top_models_count"),
    ("topTools", MAX_TOP_TOOLS, "top_tools_count"),
    ("topIntegrations", MAX_TOP_INTEGRATIONS, "top_integrations_count"),
)


@dataclass(frozen=True)
class ScanViolation:
    """One thing wrong with a scan.

    `path` is a JSON path into the payload (`graph.nodes[3].kind`) so the
    author can go straight to the offending object instead of re-reading
    the whole file. `severity` defaults to ``ERROR`` — the exit-code
    breaking kind; ``WARNING`` marks a check that could not run (see
    `ScanViolationSeverity`).
    """

    code: str
    path: str
    message: str
    severity: str = ScanViolationSeverity.ERROR


def validate_scan(
    payload: Any, *, symbol_refs: SymbolRefIndex | None = None
) -> tuple[ScanViolation, ...]:
    """Return every violation in ``payload``, or an empty tuple if it's clean.

    ``symbol_refs`` is the cross-artifact id universe from
    `load_symbol_ref_index`. ``None`` means no extraction artifact was
    available: any `symbolRef` in the scan is then reported once as a
    warning-severity ``symbol_ref_unchecked`` violation instead of being
    resolved — the scan is unverifiable there, not wrong.
    """
    if not isinstance(payload, dict):
        return (
            ScanViolation(
                "not_an_object",
                "$",
                f"scan must be a JSON object, got {type(payload).__name__}",
            ),
        )

    out: list[ScanViolation] = []

    version = payload.get("schema_version")
    if version != SCAN_SCHEMA_VERSION:
        out.append(
            ScanViolation(
                "schema_version",
                "schema_version",
                f"expected {SCAN_SCHEMA_VERSION}, got {version!r}",
            )
        )

    out.extend(_validate_project(payload.get("project")))
    out.extend(_validate_stats(payload.get("stats")))
    for key, cap, code in _CHIP_ROWS:
        out.extend(_validate_chips(payload.get(key), key, cap, code))

    graph = payload.get("graph")
    if not isinstance(graph, dict):
        out.append(ScanViolation("graph_missing", "graph", "graph must be an object"))
        return tuple(out)

    node_violations, node_ids = _validate_nodes(graph.get("nodes"), symbol_refs)
    out.extend(node_violations)
    out.extend(_validate_edges(graph.get("edges"), node_ids))
    return tuple(out)


# ----- sections --------------------------------------------------------------


def _validate_project(project: Any) -> list[ScanViolation]:
    if not isinstance(project, dict):
        return [
            ScanViolation("project_missing", "project", "project must be an object")
        ]

    out: list[ScanViolation] = []
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        out.append(ScanViolation("project_name", "project.name", "name is required"))
    elif len(name) > MAX_PROJECT_NAME:
        out.append(
            ScanViolation(
                "project_name",
                "project.name",
                f"{len(name)} chars, max {MAX_PROJECT_NAME}",
            )
        )

    slug = project.get("slug")
    if not isinstance(slug, str) or not _is_slug(slug):
        out.append(
            ScanViolation(
                "project_slug",
                "project.slug",
                f"{slug!r} is not lowercase-dashed (e.g. 'acme-billing')",
            )
        )
    elif len(slug) > MAX_PROJECT_SLUG:
        out.append(
            ScanViolation(
                "project_slug",
                "project.slug",
                f"{len(slug)} chars, max {MAX_PROJECT_SLUG}",
            )
        )

    tagline = project.get("tagline")
    if isinstance(tagline, str) and len(tagline) > MAX_PROJECT_TAGLINE:
        out.append(
            ScanViolation(
                "project_tagline",
                "project.tagline",
                f"{len(tagline)} chars, max {MAX_PROJECT_TAGLINE}",
            )
        )

    stamp = project.get("date")
    if stamp is not None and not _is_iso_date(stamp):
        out.append(
            ScanViolation(
                "project_date", "project.date", f"{stamp!r} is not YYYY-MM-DD"
            )
        )

    out.extend(_check_domain(project.get("iconDomain"), "project.iconDomain"))
    return out


def _validate_stats(stats: Any) -> list[ScanViolation]:
    if not isinstance(stats, dict):
        return [ScanViolation("stats_missing", "stats", "stats must be an object")]
    out: list[ScanViolation] = []
    for key in ("agents", "models", "tools", "integrations"):
        value = stats.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            out.append(
                ScanViolation(
                    "stats_value",
                    f"stats.{key}",
                    f"expected a non-negative integer, got {value!r}",
                )
            )
    return out


def _validate_chips(
    chips: Any, key: str, cap: int, count_code: str
) -> list[ScanViolation]:
    if chips is None:
        return []
    if not isinstance(chips, list):
        return [ScanViolation("chip_row", key, f"{key} must be a list")]
    out: list[ScanViolation] = []
    if len(chips) > cap:
        out.append(ScanViolation(count_code, key, f"{len(chips)} entries, max {cap}"))
    for i, chip in enumerate(chips):
        at = f"{key}[{i}]"
        if not isinstance(chip, dict):
            out.append(ScanViolation("chip_shape", at, "each entry must be an object"))
            continue
        for field in ("id", "label"):
            if not isinstance(chip.get(field), str) or not chip[field].strip():
                out.append(
                    ScanViolation("chip_field", f"{at}.{field}", f"{field} is required")
                )
        out.extend(_check_domain(chip.get("domain"), f"{at}.domain"))
    return out


def _validate_nodes(
    nodes: Any, symbol_refs: SymbolRefIndex | None
) -> tuple[list[ScanViolation], set[str]]:
    if not isinstance(nodes, list):
        return (
            [ScanViolation("nodes_missing", "graph.nodes", "nodes must be a list")],
            set(),
        )

    out: list[ScanViolation] = []
    if len(nodes) > MAX_SCAN_NODES:
        out.append(
            ScanViolation(
                "node_count",
                "graph.nodes",
                f"{len(nodes)} nodes, max {MAX_SCAN_NODES} — merge or drop the "
                "ones that don't earn their place",
            )
        )

    seen: set[str] = set()
    unchecked_refs = 0
    for i, node in enumerate(nodes):
        at = f"graph.nodes[{i}]"
        if not isinstance(node, dict):
            out.append(ScanViolation("node_shape", at, "each node must be an object"))
            continue

        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            out.append(ScanViolation("node_id", f"{at}.id", "id is required"))
        elif node_id in seen:
            out.append(
                ScanViolation(
                    "duplicate_node_id", f"{at}.id", f"{node_id!r} is already used"
                )
            )
        else:
            seen.add(node_id)

        kind = node.get("kind")
        if kind not in _NODE_KINDS:
            out.append(
                ScanViolation(
                    "node_kind",
                    f"{at}.kind",
                    f"{kind!r} is not one of {', '.join(_NODE_KINDS)}",
                )
            )

        evidence = node.get("evidence")
        if evidence is not None and evidence not in _EVIDENCE_VALUES:
            out.append(
                ScanViolation(
                    "node_evidence",
                    f"{at}.evidence",
                    f"{evidence!r} is not one of {', '.join(_EVIDENCE_VALUES)}",
                )
            )

        ref = node.get("symbolRef")
        if isinstance(ref, str) and ref.strip():
            if symbol_refs is None:
                unchecked_refs += 1
            elif not symbol_refs.resolves(ref):
                out.append(
                    ScanViolation(
                        "symbol_ref_unresolved",
                        f"{at}.symbolRef",
                        f"{ref!r} is not an id in {', '.join(symbol_refs.sources)}",
                    )
                )

        for field, cap, code in _NODE_TEXT_FIELDS:
            out.extend(_check_text(node.get(field), f"{at}.{field}", cap, code))
        if not isinstance(node.get("label"), str) or not node["label"].strip():
            out.append(ScanViolation("node_label", f"{at}.label", "label is required"))

        out.extend(_check_domain(node.get("domain"), f"{at}.domain"))

    if unchecked_refs:
        # One aggregate warning, not one per node: with the artifacts absent
        # there is nothing in the scan itself for the author to fix.
        out.append(
            ScanViolation(
                "symbol_ref_unchecked",
                "graph.nodes",
                f"{unchecked_refs} node(s) carry a symbolRef but no "
                "features/symbol-graph.json (or graph-communities.json) is "
                "present to resolve them — run `dummyindex context rebuild "
                "--changed` to regenerate the extraction artifacts",
                severity=ScanViolationSeverity.WARNING,
            )
        )
    return out, seen


def _validate_edges(edges: Any, node_ids: set[str]) -> list[ScanViolation]:
    if not isinstance(edges, list):
        return [ScanViolation("edges_missing", "graph.edges", "edges must be a list")]

    out: list[ScanViolation] = []
    if len(edges) > MAX_SCAN_EDGES:
        out.append(
            ScanViolation(
                "edge_count",
                "graph.edges",
                f"{len(edges)} edges, max {MAX_SCAN_EDGES}",
            )
        )

    for i, edge in enumerate(edges):
        at = f"graph.edges[{i}]"
        if not isinstance(edge, dict):
            out.append(ScanViolation("edge_shape", at, "each edge must be an object"))
            continue

        for field in ("from", "to"):
            ref = edge.get(field)
            if not isinstance(ref, str) or not ref.strip():
                out.append(
                    ScanViolation(
                        "edge_endpoint", f"{at}.{field}", f"{field} is required"
                    )
                )
            elif ref not in node_ids:
                out.append(
                    ScanViolation(
                        "edge_endpoint",
                        f"{at}.{field}",
                        f"{ref!r} is not a node id in graph.nodes",
                    )
                )

        kind = edge.get("kind")
        if kind is not None and kind not in _EDGE_KINDS:
            out.append(
                ScanViolation(
                    "edge_kind",
                    f"{at}.kind",
                    f"{kind!r} is not one of {', '.join(_EDGE_KINDS)}",
                )
            )

        out.extend(
            _check_text(
                edge.get("label"), f"{at}.label", MAX_EDGE_LABEL, "edge_label_length"
            )
        )
    return out


# ----- field checks ----------------------------------------------------------


def _check_text(value: Any, at: str, cap: int, code: str) -> list[ScanViolation]:
    if value is None:
        return []
    if not isinstance(value, str):
        return [
            ScanViolation(code, at, f"expected a string, got {type(value).__name__}")
        ]
    if len(value) > cap:
        return [ScanViolation(code, at, f"{len(value)} chars, max {cap}")]
    return []


def _check_domain(value: Any, at: str) -> list[ScanViolation]:
    """A favicon domain is a bare host — `openai.com`, not `https://openai.com/`."""
    if value is None:
        return []
    if not isinstance(value, str) or not value.strip():
        return [ScanViolation("domain_format", at, "domain must be a non-empty string")]
    host = value.strip()
    if "://" in host or "/" in host or " " in host or "." not in host:
        return [
            ScanViolation(
                "domain_format",
                at,
                f"{value!r} must be a bare host with no scheme or path "
                "(e.g. 'openai.com')",
            )
        ]
    return []


def _is_slug(value: str) -> bool:
    return bool(_SLUG_RE.fullmatch(value))


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True
