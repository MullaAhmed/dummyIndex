"""Flow naming pass — Feature 2.

Pure I/O glue between the deterministic flow synthesizer and an LLM
naming step. The LLM step itself is *not* invoked from Python: the skill
(``dummyindex/skills/skill*.md``) drives subagent dispatch on the todo
file written here, and writes back a results file that this module
applies.

This mirrors the Step 6a-classify pattern from Feature 1: Python
prepares + applies; the skill executes the LLM batch. The benefit is
that one body of code works across every variant (claude, codex,
copilot, droid, kiro, etc.) without needing per-platform API keys.

Public entry points:

- ``prepare_naming_todo(flows, G, out_dir)`` → writes the todo file and
  returns the in-memory todo dict.
- ``apply_named_results(flows, results, out_dir)`` → returns new flow
  dicts with ``label`` / ``description`` filled in. Updates the cache.
- ``load_cached_names(out_dir)`` / ``load_overrides(out_dir)``.

All functions return new lists; flow dicts are never mutated in place.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx


CACHE_FILENAME = ".dummyindex_flow_names.json"
TODO_FILENAME = ".dummyindex_flow_names_todo.json"
RESULTS_FILENAME = ".dummyindex_flow_names_results.json"
OVERRIDES_FILENAME = "flows.yaml"

CACHE_VERSION = "1.2"

logger = logging.getLogger("dummyindex.flow_naming")


# --------------------------------------------------------------------------- #
# Cache + override I/O.
# --------------------------------------------------------------------------- #


def load_cached_names(out_dir: str | Path) -> dict[str, dict]:
    """Return ``{flow_id: {"name": ..., "description": ..., "cache_key": ...}}``.

    Returns an empty dict when the cache is missing or schema-mismatched."""
    path = Path(out_dir) / CACHE_FILENAME
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read flow-name cache at %s: %s", path, exc)
        return {}
    if payload.get("schema_version") != CACHE_VERSION:
        return {}
    entries = payload.get("entries", {})
    return entries if isinstance(entries, dict) else {}


def write_cached_names(out_dir: str | Path, entries: dict[str, dict]) -> None:
    """Atomic-ish write — sorted keys for stable diffs."""
    path = Path(out_dir) / CACHE_FILENAME
    payload = {"schema_version": CACHE_VERSION, "entries": dict(sorted(entries.items()))}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)


def load_overrides(out_dir: str | Path) -> dict[str, dict]:
    """Read ``flows.yaml`` (if present). Returns ``{flow_id: {name, description?}}``.

    YAML is parsed with ``yaml.safe_load`` only. Missing PyYAML is treated
    as "no overrides"; we don't make YAML a hard install dep just for this."""
    path = Path(out_dir) / OVERRIDES_FILENAME
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("flows.yaml present but PyYAML is not installed; ignoring overrides")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as exc:
        logger.warning("Failed to read flow override file %s: %s", path, exc)
        return {}
    except yaml.YAMLError as exc:
        logger.warning("Invalid YAML in %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): _coerce_override_entry(v) for k, v in data.items() if v}


def _coerce_override_entry(raw: Any) -> dict:
    if isinstance(raw, str):
        return {"name": raw}
    if isinstance(raw, dict) and "name" in raw:
        out = {"name": str(raw["name"])}
        if raw.get("description"):
            out["description"] = str(raw["description"])
        return out
    return {}


# --------------------------------------------------------------------------- #
# Cache key — content hash over the inputs that determine a name.
# --------------------------------------------------------------------------- #


def cache_key_for_flow(flow: dict, G: nx.Graph) -> str:
    """Stable hash over entry kind, entry label, top participants, first
    sequence steps, and terminals. Same content → same cache key → same
    name (PRD SC-5)."""
    entry_nodes = flow.get("entry_nodes") or []
    entry_labels = [G.nodes[n].get("label", n) for n in entry_nodes if n in G.nodes]
    entry_files = [G.nodes[n].get("source_file", "") for n in entry_nodes if n in G.nodes]

    nodes = flow.get("nodes") or []
    degree_pairs = sorted(
        ((n, G.degree(n) if n in G.nodes else 0) for n in nodes),
        key=lambda p: (-p[1], p[0]),
    )
    top_participants = [G.nodes[n].get("label", n) for n, _ in degree_pairs[:3] if n in G.nodes]

    first_steps = [(s["source"], s["target"]) for s in (flow.get("sequence") or [])[:5]]
    terminals = [G.nodes[n].get("label", n) for n in (flow.get("exit_nodes") or []) if n in G.nodes]

    payload = json.dumps({
        "entry_kind": flow.get("entry_kind", ""),
        "entry_labels": entry_labels,
        "entry_files": entry_files,
        "top_participants": top_participants,
        "first_steps": first_steps,
        "terminals": terminals,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Todo / results files.
# --------------------------------------------------------------------------- #


def prepare_naming_todo(
    flows: list[dict],
    G: nx.Graph,
    out_dir: str | Path,
    *,
    god_nodes: list[dict] | None = None,
    community_labels: dict[int, str] | None = None,
) -> dict:
    """Write a todo file the skill can hand to subagents.

    Each entry contains everything an LLM needs to propose a 2–5 word name:
    entry kind/label/file/docstring, top participants, first 5 sequence
    steps, terminal labels, plus an advisory ``context`` block carrying
    god-node and community-label hints from the main graph (so flow names
    stay coherent with the broader architectural vocabulary).

    Returns the in-memory todo dict (also written to ``out_dir/.dummyindex_flow_names_todo.json``)."""
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    cached = load_cached_names(out_dir_path)
    overrides = load_overrides(out_dir_path)

    entries: list[dict] = []
    skipped_cache = 0
    skipped_override = 0
    for flow in flows:
        fid = flow["id"]
        key = cache_key_for_flow(flow, G)
        if fid in overrides:
            skipped_override += 1
            continue
        cached_entry = cached.get(fid)
        if cached_entry and cached_entry.get("cache_key") == key:
            skipped_cache += 1
            continue
        entries.append(_summarize_flow_for_naming(flow, G, key))

    todo = {
        "schema_version": CACHE_VERSION,
        "context": {
            "god_nodes": [g.get("label", g.get("id", "")) for g in (god_nodes or [])][:10],
            "community_labels": dict(sorted((community_labels or {}).items())),
        },
        "stats": {
            "total_flows": len(flows),
            "to_name": len(entries),
            "cache_hits": skipped_cache,
            "override_hits": skipped_override,
        },
        "entries": entries,
    }
    todo_path = out_dir_path / TODO_FILENAME
    with open(todo_path, "w", encoding="utf-8") as f:
        json.dump(todo, f, indent=2, sort_keys=False)
    return todo


def _summarize_flow_for_naming(flow: dict, G: nx.Graph, cache_key: str) -> dict:
    entry_id = (flow.get("entry_nodes") or [""])[0]
    entry_attrs = G.nodes[entry_id] if entry_id in G.nodes else {}

    nodes = flow.get("nodes") or []
    degree_pairs = sorted(
        ((n, G.degree(n) if n in G.nodes else 0) for n in nodes),
        key=lambda p: (-p[1], p[0]),
    )
    top_participants = []
    for nid, _ in degree_pairs[:3]:
        if nid in G.nodes:
            top_participants.append({
                "id": nid,
                "label": G.nodes[nid].get("label", nid),
                "source_file": G.nodes[nid].get("source_file", ""),
            })

    first_steps = []
    for step in (flow.get("sequence") or [])[:5]:
        first_steps.append({
            "source": step.get("source"),
            "target": step.get("target"),
            "source_label": G.nodes.get(step.get("source"), {}).get("label", step.get("source")),
            "target_label": G.nodes.get(step.get("target"), {}).get("label", step.get("target")),
        })

    terminals = []
    for nid in flow.get("exit_nodes") or []:
        if nid in G.nodes:
            terminals.append({"id": nid, "label": G.nodes[nid].get("label", nid)})

    return {
        "flow_id": flow["id"],
        "cache_key": cache_key,
        "entry_kind": flow.get("entry_kind"),
        "entry": {
            "id": entry_id,
            "label": entry_attrs.get("label", entry_id),
            "source_file": entry_attrs.get("source_file", ""),
            "docstring": entry_attrs.get("docstring", ""),
        },
        "top_participants": top_participants,
        "first_steps": first_steps,
        "terminals": terminals,
        "confidence": flow.get("confidence"),
        "salience": flow.get("salience"),
    }


def write_naming_results(out_dir: str | Path, results: list[dict]) -> Path:
    """Helper for tests / direct callers — write a results file in the
    shape the skill is expected to produce."""
    path = Path(out_dir) / RESULTS_FILENAME
    payload = {"schema_version": CACHE_VERSION, "results": results}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
    return path


def load_naming_results(out_dir: str | Path) -> list[dict]:
    path = Path(out_dir) / RESULTS_FILENAME
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read naming results at %s: %s", path, exc)
        return []
    results = payload.get("results", [])
    return results if isinstance(results, list) else []


# --------------------------------------------------------------------------- #
# Apply pass — combines cache + overrides + fresh results.
# --------------------------------------------------------------------------- #


def apply_named_results(
    flows: list[dict],
    G: nx.Graph,
    out_dir: str | Path,
    *,
    fresh_results: list[dict] | None = None,
) -> list[dict]:
    """Return a new list of flow dicts with ``label`` / ``description``
    populated. Cache is updated on disk so subsequent runs hit it.

    Resolution order: overrides > fresh results > cache > provisional ID.
    Failure to find a name keeps the provisional ID — callers can detect
    this by checking whether ``flow["label"]`` still equals ``flow["id"]``."""
    out_dir_path = Path(out_dir)
    overrides = load_overrides(out_dir_path)
    cache = load_cached_names(out_dir_path)
    fresh = _index_results(fresh_results or load_naming_results(out_dir_path))

    new_flows: list[dict] = []
    cache_updates = dict(cache)

    for flow in flows:
        fid = flow["id"]
        key = cache_key_for_flow(flow, G)
        name_entry = _resolve_name(fid, key, overrides, fresh, cache)
        new_flow = dict(flow)
        if name_entry:
            if name_entry.get("name"):
                new_flow["label"] = name_entry["name"]
            if name_entry.get("description"):
                new_flow["description"] = name_entry["description"]
            # only persist results that came from a fresh model pass — overrides
            # are user-controlled and recomputed each time we re-read the YAML.
            if fid in fresh and _is_valid_name(name_entry.get("name")):
                cache_updates[fid] = {
                    "name": name_entry["name"],
                    "description": name_entry.get("description", ""),
                    "cache_key": key,
                }
        new_flows.append(new_flow)

    write_cached_names(out_dir_path, cache_updates)
    return new_flows


def _resolve_name(
    flow_id: str,
    cache_key: str,
    overrides: dict[str, dict],
    fresh: dict[str, dict],
    cache: dict[str, dict],
) -> dict | None:
    if flow_id in overrides:
        return overrides[flow_id]
    if flow_id in fresh and _is_valid_name(fresh[flow_id].get("name")):
        return fresh[flow_id]
    cached_entry = cache.get(flow_id)
    if cached_entry and cached_entry.get("cache_key") == cache_key:
        return cached_entry
    return None


def _index_results(results: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in results:
        fid = r.get("flow_id")
        if fid:
            out[str(fid)] = r
    return out


def _is_valid_name(name: Any) -> bool:
    if not isinstance(name, str):
        return False
    stripped = name.strip()
    if not stripped:
        return False
    word_count = len(stripped.split())
    return 2 <= word_count <= 5
