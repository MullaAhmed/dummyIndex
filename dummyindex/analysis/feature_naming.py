"""Feature naming + override pass — Feature 3 Stage B.

Mirrors the ``flow_naming.py`` pattern: Python prepares a todo file, the
skill drives a subagent batch, Python applies results back. Keeps every
LLM call out of Python so the same code works across every platform variant
(claude, codex, copilot, droid, kiro, ...).

Adds one capability flow_naming doesn't have: a ``features.yaml`` override
file with a richer schema (``pin``, ``exclude``, ``merge_with``,
``features_new``) — humans win, the Stage A/B output is a first draft.

Public entry points:

- ``prepare_feature_naming_todo(features, signal_pack, out_dir, ...)``
  → writes the todo file the skill hands to subagents.
- ``apply_feature_named_results(features, G, out_dir, fresh_results=...)``
  → returns new features with ``label`` / ``description`` populated.
- ``apply_feature_overrides(features, G, out_dir)``
  → returns new features after ``features.yaml`` is applied (pin / exclude /
    merge_with / features_new + name/description). Always wins.
- ``write_features_yaml_starter`` / ``load_features_yaml`` for tooling.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx

from dummyindex.analysis.features import (
    SignalPack,
    canonical_hash,
)


CACHE_FILENAME = ".dummyindex_feature_names.json"
TODO_FILENAME = ".dummyindex_feature_names_todo.json"
RESULTS_FILENAME = ".dummyindex_feature_names_results.json"
OVERRIDES_FILENAME = "features.yaml"
DIFF_FILENAME = ".dummyindex_feature_diff.md"

CACHE_VERSION = "1.3"

logger = logging.getLogger("dummyindex.feature_naming")


# --------------------------------------------------------------------------- #
# Cache I/O.
# --------------------------------------------------------------------------- #


def load_cached_names(out_dir: str | Path) -> dict[str, dict]:
    path = Path(out_dir) / CACHE_FILENAME
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read feature-name cache at %s: %s", path, exc)
        return {}
    if payload.get("schema_version") != CACHE_VERSION:
        return {}
    entries = payload.get("entries", {})
    return entries if isinstance(entries, dict) else {}


def write_cached_names(out_dir: str | Path, entries: dict[str, dict]) -> None:
    path = Path(out_dir) / CACHE_FILENAME
    payload = {"schema_version": CACHE_VERSION, "entries": dict(sorted(entries.items()))}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Cache key — deterministic over a feature's input signals.
# --------------------------------------------------------------------------- #


def feature_cache_key(feature: dict, G: nx.Graph) -> str:
    nodes = feature.get("nodes") or []
    payload = json.dumps({
        "communities": sorted(feature.get("communities") or []),
        "node_count": len(nodes),
        "top_labels": sorted(
            G.nodes[n].get("label", n) for n in nodes if n in G.nodes
        )[:8],
        "flow_ids": sorted(feature.get("flows") or []),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Todo / results files.
# --------------------------------------------------------------------------- #


def prepare_feature_naming_todo(
    features: list[dict],
    G: nx.Graph,
    out_dir: str | Path,
    *,
    signal_pack: SignalPack | None = None,
    god_nodes: list[dict] | None = None,
    community_labels: dict[int, str] | None = None,
) -> dict:
    """Write the todo file for the skill's subagent dispatch.

    Each entry contains the inputs the LLM needs to propose name +
    description: top labels, communities touched, flow ids, role counts.
    The ``context`` block carries community labels + god-node names from
    the broader graph so feature names align with the codebase vocabulary."""
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    cached = load_cached_names(out_dir_path)
    overrides_yaml = load_features_yaml(out_dir_path)
    override_ids = {entry.get("id") for entry in overrides_yaml.get("features", []) if entry.get("name")}

    entries: list[dict] = []
    skipped_cache = 0
    skipped_override = 0
    for feature in features:
        fid = feature["id"]
        key = feature_cache_key(feature, G)
        if fid in override_ids:
            skipped_override += 1
            continue
        cached_entry = cached.get(fid)
        if cached_entry and cached_entry.get("cache_key") == key:
            skipped_cache += 1
            continue
        entries.append(_summarize_feature(feature, G, key))

    todo = {
        "schema_version": CACHE_VERSION,
        "context": {
            "god_nodes": [g.get("label", g.get("id", "")) for g in (god_nodes or [])][:10],
            "community_labels": dict(sorted((community_labels or {}).items())),
            "project_summary": (signal_pack.folder_summary.keys() if signal_pack else []) and
                                sorted(set(signal_pack.folder_summary.keys()))[:10] or [],
        },
        "stats": {
            "total_features": len(features),
            "to_name": len(entries),
            "cache_hits": skipped_cache,
            "override_hits": skipped_override,
        },
        "entries": entries,
    }
    (out_dir_path / TODO_FILENAME).write_text(json.dumps(todo, indent=2), encoding="utf-8")
    return todo


def _summarize_feature(feature: dict, G: nx.Graph, cache_key: str) -> dict:
    nodes = feature.get("nodes") or []
    deg_pairs = sorted(
        ((n, G.degree(n) if n in G.nodes else 0) for n in nodes),
        key=lambda p: (-p[1], p[0]),
    )
    top_members = []
    for nid, deg in deg_pairs[:8]:
        if nid in G.nodes:
            top_members.append({
                "id": nid,
                "label": G.nodes[nid].get("label", nid),
                "source_file": G.nodes[nid].get("source_file", ""),
                "degree": deg,
            })
    return {
        "feature_id": feature["id"],
        "cache_key": cache_key,
        "current_label": feature.get("label", feature["id"]),
        "communities": feature.get("communities", []),
        "flows": feature.get("flows", []),
        "node_count": len(nodes),
        "roles": feature.get("roles", {}),
        "top_members": top_members,
        "evidence": {
            "community_ids": (feature.get("evidence") or {}).get("community_ids", []),
            "doc_node_ids": (feature.get("evidence") or {}).get("doc_node_ids", []),
            "representative_nodes": (feature.get("evidence") or {}).get("representative_nodes", []),
        },
    }


def write_naming_results(out_dir: str | Path, results: list[dict]) -> Path:
    path = Path(out_dir) / RESULTS_FILENAME
    payload = {"schema_version": CACHE_VERSION, "results": results}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_naming_results(out_dir: str | Path) -> list[dict]:
    path = Path(out_dir) / RESULTS_FILENAME
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read feature-naming results at %s: %s", path, exc)
        return []
    return payload.get("results", []) or []


# --------------------------------------------------------------------------- #
# Apply LLM names. Returns new features (immutable).
# --------------------------------------------------------------------------- #


def apply_feature_named_results(
    features: list[dict],
    G: nx.Graph,
    out_dir: str | Path,
    *,
    fresh_results: list[dict] | None = None,
) -> list[dict]:
    """Resolve names: overrides > fresh > cache > provisional. Persist
    valid fresh names to cache."""
    out_dir_path = Path(out_dir)
    cache = load_cached_names(out_dir_path)
    fresh_idx = _index_results(fresh_results or load_naming_results(out_dir_path))

    cache_updates = dict(cache)
    new_features: list[dict] = []
    for f in features:
        fid = f["id"]
        key = feature_cache_key(f, G)
        new_f = dict(f)

        # fresh wins over cache
        entry = fresh_idx.get(fid)
        if entry and _is_valid_name(entry.get("name")):
            new_f["label"] = entry["name"]
            if entry.get("description"):
                new_f["description"] = entry["description"]
            cache_updates[fid] = {
                "name": entry["name"],
                "description": entry.get("description", ""),
                "cache_key": key,
            }
        else:
            cached_entry = cache.get(fid)
            if cached_entry and cached_entry.get("cache_key") == key:
                new_f["label"] = cached_entry.get("name", new_f["label"])
                if cached_entry.get("description"):
                    new_f["description"] = cached_entry["description"]

        # canonical hash always recomputed for override anchoring
        new_f["canonical_hash"] = canonical_hash(new_f)
        new_features.append(new_f)

    write_cached_names(out_dir_path, cache_updates)
    return new_features


def _index_results(results: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in results:
        fid = r.get("feature_id") or r.get("flow_id")
        if fid:
            out[str(fid)] = r
    return out


def _is_valid_name(name: Any) -> bool:
    if not isinstance(name, str):
        return False
    s = name.strip()
    if not s:
        return False
    word_count = len(s.split())
    return 2 <= word_count <= 5


# --------------------------------------------------------------------------- #
# features.yaml override protocol.
# --------------------------------------------------------------------------- #


def load_features_yaml(out_dir: str | Path) -> dict:
    """Load and lightly-validate ``features.yaml``. Returns ``{}`` if missing
    or PyYAML is not installed (treated as "no overrides")."""
    path = Path(out_dir) / OVERRIDES_FILENAME
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("features.yaml present but PyYAML is not installed; ignoring overrides")
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return {}
    except yaml.YAMLError as exc:
        # The override file is authoritative; raise loudly so the user sees it.
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        return {}
    return data


def apply_feature_overrides(
    features: list[dict],
    G: nx.Graph,
    out_dir: str | Path,
) -> tuple[list[dict], list[str]]:
    """Apply ``features.yaml`` directives in documented order.

    Returns ``(new_features, diff_lines)``. The diff is human-readable text
    written to ``.dummyindex_feature_diff.md`` by the caller for audit."""
    overrides = load_features_yaml(out_dir)
    if not overrides:
        return [dict(f) for f in features], []

    # Index by id and by canonical_hash so renames don't break overrides.
    by_id = {f["id"]: dict(f) for f in features}
    by_hash = {f.get("canonical_hash") or canonical_hash(f): f["id"] for f in features}
    diff: list[str] = []
    valid_node_ids = set(G.nodes())

    # 1. features_new — user-defined features take precedence in id namespace.
    for entry in overrides.get("features_new", []) or []:
        fid = entry.get("id")
        nodes = entry.get("nodes") or []
        if not fid or not nodes:
            continue
        valid_nodes = [n for n in nodes if n in valid_node_ids]
        skipped = [n for n in nodes if n not in valid_node_ids]
        new_feature = {
            "id": fid,
            "label": entry.get("name", fid),
            "kind": "feature",
            "nodes": sorted(set(valid_nodes)),
            "communities": entry.get("communities") or [],
            "flows": entry.get("flows") or [],
            "members": [],
            "roles": {},
            "evidence": {
                "community_ids": entry.get("communities") or [],
                "representative_nodes": valid_nodes[:5],
                "doc_node_ids": [],
                "flow_ids": entry.get("flows") or [],
                "override_applied": True,
                "llm_reasoning": "user-defined via features.yaml",
            },
            "description": entry.get("description", ""),
            "confidence": "EXTRACTED",  # user-asserted
        }
        new_feature["canonical_hash"] = canonical_hash(new_feature)
        by_id[fid] = new_feature
        diff.append(f"+ NEW {fid} ({len(valid_nodes)} nodes from features_new)")
        if skipped:
            diff.append(f"  WARNING features_new[{fid}] skipped {len(skipped)} unknown nodes")

    # 2/3/4. pin / exclude / merge_with on existing features.
    for entry in overrides.get("features", []) or []:
        fid = entry.get("id")
        if not fid:
            continue
        # Resolve via canonical_hash if id has drifted.
        if fid not in by_id:
            target_hash = entry.get("canonical_hash")
            if target_hash and target_hash in by_hash:
                fid = by_hash[target_hash]
                diff.append(f"  resolved override id {entry['id']!r} -> {fid!r} via canonical_hash")
            else:
                diff.append(f"  WARNING override targets unknown feature id {entry.get('id')!r}; skipped")
                continue
        target = by_id[fid]
        target = dict(target)
        target.setdefault("evidence", {})
        target["evidence"]["override_applied"] = True

        # name + description override
        if entry.get("name"):
            target["label"] = entry["name"]
        if entry.get("description"):
            target["description"] = entry["description"]

        members = set(target.get("nodes") or [])
        # pin
        for nid in entry.get("pin") or []:
            if nid not in valid_node_ids:
                diff.append(f"  WARNING pin {nid!r} unknown — skipped")
                continue
            members.add(nid)
        # exclude
        for nid in entry.get("exclude") or []:
            if nid in members:
                members.remove(nid)
            else:
                diff.append(f"  NOTE exclude {nid!r} was already absent from {fid}")
        target["nodes"] = sorted(members)
        if not target["nodes"]:
            diff.append(f"  WARNING {fid} is empty after exclude; dropping")
            del by_id[fid]
            continue
        # merge_with
        for other_id in entry.get("merge_with") or []:
            other = by_id.get(other_id)
            if not other:
                diff.append(f"  WARNING merge_with target {other_id!r} unknown — skipped")
                continue
            target["nodes"] = sorted(set(target["nodes"]) | set(other.get("nodes") or []))
            target["communities"] = sorted(set(target.get("communities", [])) | set(other.get("communities", [])))
            target["flows"] = sorted(set(target.get("flows", [])) | set(other.get("flows", [])))
            del by_id[other_id]
            diff.append(f"  merged {other_id} into {fid} (now {len(target['nodes'])} nodes)")
        target["canonical_hash"] = canonical_hash(target)
        by_id[fid] = target
        diff.append(f"~ {fid}: pinned/excluded → {len(target['nodes'])} nodes")

    return list(by_id.values()), diff


def write_features_yaml_starter(features: list[dict], out_dir: str | Path) -> Path | None:
    """Write a starter ``features.yaml`` if the file doesn't already exist.

    The starter is commented and contains every emitted feature. Users edit
    in place; subsequent runs honor it as authoritative."""
    out_dir_path = Path(out_dir)
    path = out_dir_path / OVERRIDES_FILENAME
    if path.exists():
        return None
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("PyYAML not installed; skipping features.yaml starter write")
        return None
    payload = {
        "features": [
            {
                "id": f["id"],
                "name": f.get("label", ""),
                "description": f.get("description", ""),
                "canonical_hash": f.get("canonical_hash") or canonical_hash(f),
                "pin": [],
                "exclude": [],
                "merge_with": [],
            }
            for f in features
        ],
        "features_new": [],
    }
    body = (
        "# dummyindex feature overrides — edit and re-run /dummyindex --update.\n"
        "# pin: add these node ids to the feature.\n"
        "# exclude: remove these node ids.\n"
        "# merge_with: list of other feature ids to absorb into this one.\n"
        "# features_new: user-defined features from scratch (id + nodes required).\n\n"
    )
    body += yaml.safe_dump(payload, sort_keys=False)
    path.write_text(body, encoding="utf-8")
    return path
