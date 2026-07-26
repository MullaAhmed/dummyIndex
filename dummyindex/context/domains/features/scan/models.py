"""Frozen dataclasses for the curated codebase scan (`features/graph.json`).

Data only, `to_dict()` next to the class, tuples for collections — the same
contract as `features/models.py`.

Two wire-shape rules the serializers exist to enforce:

- **Optional means absent.** A field that was never set is omitted from the
  JSON rather than emitted as `null`. The scan is read by a model (which
  pays for every token) and by the viewer (which branches on presence), so
  a node with nothing but the required trio is exactly three keys wide.
- **camelCase on the wire, snake_case in Python.** `source_ref` →
  `sourceRef`, `from_id` → `from`, `top_models` → `topModels`. `from` is a
  Python keyword and can't be a field name at all, which is what forces the
  split; the rest follow it for consistency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dummyindex.pipeline.enums import ConfidenceLevel

from ..constants import SCAN_SCHEMA_VERSION


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    """Set ``key`` only when ``value`` is meaningfully present.

    Empty strings are dropped alongside ``None``: a curated `sub: ""` is
    noise the viewer would reserve a line for.
    """
    if value is None or value == "":
        return
    target[key] = str(value)


@dataclass(frozen=True)
class ScanChip:
    """One entry in `topModels` / `topTools` / `topIntegrations`.

    A chip is a headline, not a graph node — it answers "what does this
    codebase use?" above the map. The same thing usually also appears as a
    node; that duplication is deliberate.
    """

    id: str
    label: str
    domain: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "label": self.label}
        _put(out, "domain", self.domain)
        return out


@dataclass(frozen=True)
class ScanNode:
    """One box on the map.

    `sub` is the one-line qualifier under the label (`/api/chat`,
    `streamText`, `12 near-identical scrapers`). `detail` is the sentence
    revealed on click. `source_ref` is `path` or `path:line` so a teammate
    can jump to the code — set it on everything the repo owns.

    `symbol_ref` (wire: `symbolRef`) pins the box to the extraction layer:
    a `features/symbol-graph.json` node id or a `graph-communities.json`
    community id, checked for referential integrity by `validate_scan`.
    `evidence` is a `ScanEvidence` value — `EXTRACTED` if the node survived
    from the seed verbatim, `INFERRED` if the authoring stage added or
    reshaped it. Both are optional so pre-extension scans stay valid.
    """

    id: str
    label: str
    kind: str
    sub: str | None = None
    group: str | None = None
    domain: str | None = None
    detail: str | None = None
    source_ref: str | None = None
    symbol_ref: str | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "kind": str(self.kind),
        }
        _put(out, "sub", self.sub)
        _put(out, "group", self.group)
        _put(out, "domain", self.domain)
        _put(out, "detail", self.detail)
        _put(out, "sourceRef", self.source_ref)
        _put(out, "symbolRef", self.symbol_ref)
        _put(out, "evidence", self.evidence)
        return out


@dataclass(frozen=True)
class ScanEdge:
    """One connection. `kind` is the verb; `label` is the specific phrase.

    Set `kind` on everything — the viewer reveals it when a flow is traced.
    Add `label` only when a phrase says more than the verb does ("charges on
    trial end"), because labels are always visible and a map where every
    edge is labelled is a map nobody reads.
    """

    from_id: str
    to_id: str
    kind: str | None = None
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"from": self.from_id, "to": self.to_id}
        _put(out, "kind", self.kind)
        _put(out, "label", self.label)
        return out


@dataclass(frozen=True)
class ScanStats:
    """Headline counts. Judgment, not extraction — the seed leaves these at 0."""

    agents: int = 0
    models: int = 0
    tools: int = 0
    integrations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agents": self.agents,
            "models": self.models,
            "tools": self.tools,
            "integrations": self.integrations,
        }


@dataclass(frozen=True)
class ScanProject:
    """Who this scan is of.

    `date` is deliberately optional and deliberately unset by the seed: a
    rebuilt backbone that stamped today's date would rewrite `graph.json`
    on every run and turn a deterministic artifact into git noise. The
    authoring stage sets it, because a curated scan really is a snapshot.
    """

    name: str
    slug: str
    tagline: str | None = None
    icon_domain: str | None = None
    date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "slug": self.slug}
        _put(out, "tagline", self.tagline)
        _put(out, "iconDomain", self.icon_domain)
        _put(out, "date", self.date)
        return out


@dataclass(frozen=True)
class Scan:
    """The whole artifact — one map holding AI flows *and* business logic.

    `confidence` is what makes the seed/curate split safe: `EXTRACTED` is a
    deterministic backbone a rebuild may freely overwrite, `INFERRED` is
    human/model judgment a rebuild must preserve. Same contract as
    `spec.md` and feature names.
    """

    project: ScanProject
    stats: ScanStats
    nodes: tuple[ScanNode, ...]
    edges: tuple[ScanEdge, ...]
    top_models: tuple[ScanChip, ...] = ()
    top_tools: tuple[ScanChip, ...] = ()
    top_integrations: tuple[ScanChip, ...] = ()
    confidence: str = ConfidenceLevel.EXTRACTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCAN_SCHEMA_VERSION,
            "project": self.project.to_dict(),
            "stats": self.stats.to_dict(),
            "topModels": [c.to_dict() for c in self.top_models],
            "topTools": [c.to_dict() for c in self.top_tools],
            "topIntegrations": [c.to_dict() for c in self.top_integrations],
            "graph": {
                "nodes": [n.to_dict() for n in self.nodes],
                "edges": [e.to_dict() for e in self.edges],
            },
            # Emitted raw, like `Feature.to_dict` — `ConfidenceLevel` is a
            # `(str, Enum)` that json serializes to its value, and unlike
            # `ScanNodeKind` it does not pin `__str__`, so `str()` here would
            # write "ConfidenceLevel.EXTRACTED" into the artifact.
            "confidence": self.confidence,
        }
