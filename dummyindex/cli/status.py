"""`dummyindex context status` — a single read-only overview, never mutates.

The read-only building blocks already exist per-domain (enriched-index verdict,
commit-anchored drift, equipment manifest, proposal checklists, the version
stamp). Nothing composed them into one glance, so models improvised flags like
``--status`` and ``status``. This verb reuses those helpers verbatim and prints
a markdown summary (or ``--json``); it exits 0 even on an un-indexed repo
(reporting ``not initialized``), per the read-only contract. It writes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .common import parse_path_and_root, resolve_context_root


def run(args: list[str]) -> int:
    scope, explicit_root, rest = parse_path_and_root(args)
    as_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]
    if rest:
        print(f"error: unknown argument(s) for `status`: {rest}", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    summary = _collect(out_root)

    if as_json:
        print(json.dumps(summary, indent=2))
    else:
        _print_markdown(summary)
    return 0


def _collect(out_root: Path) -> dict[str, Any]:
    """Assemble the read-only summary. Each probe is best-effort and never
    raises — a missing or corrupt layer reads as absent, not an error."""
    context_dir = out_root / ".context"
    initialized = context_dir.is_dir()

    summary: dict[str, Any] = {
        "root": str(out_root),
        "initialized": initialized,
        "enriched": False,
        "version": {"meta": None, "cli": _cli_version()},
        "indexed_commit": None,
        "head": None,
        "drift": _empty_drift(),
        "equipment": {"present": False, "items": 0, "schema_version": None},
        "proposals": [],
        "session_memory": (context_dir / "session-memory").is_dir(),
    }
    if not initialized:
        return summary

    summary["enriched"] = _is_enriched(context_dir)
    summary["version"]["meta"] = _meta_version(context_dir)
    summary["indexed_commit"], summary["head"], summary["drift"] = _drift(
        context_dir, out_root
    )
    summary["equipment"] = _equipment(context_dir)
    summary["proposals"] = _proposals(context_dir)
    return summary


def _cli_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("dummyindex")
    except Exception:
        return None


def _is_enriched(context_dir: Path) -> bool:
    try:
        from dummyindex.context.build import is_enriched_index

        return is_enriched_index(context_dir)
    except Exception:
        return False


def _meta_version(context_dir: Path) -> str | None:
    try:
        from dummyindex.context.build.meta import read_meta

        return read_meta(context_dir / "meta.json").dummyindex_version
    except Exception:
        return None


def _empty_drift() -> dict[str, Any]:
    return {
        "in_sync": True,
        "drifted_features": 0,
        "removed_files": 0,
        "unassigned_new_files": 0,
        "awaiting_enrichment": 0,
        "anchor_broken": False,
    }


def _drift(context_dir: Path, out_root: Path) -> tuple[str | None, str | None, dict[str, Any]]:
    try:
        from dummyindex.context.build import compute_reconcile_report
        from dummyindex.context.build.git_delta import head_commit

        report = compute_reconcile_report(context_dir, out_root)
        head = head_commit(out_root)
        drift = {
            "in_sync": not report.has_drift,
            "drifted_features": len(report.drifted_features),
            "removed_files": len(report.removed_files),
            "unassigned_new_files": len(report.unassigned_new_files),
            "awaiting_enrichment": len(report.awaiting_enrichment),
            "anchor_broken": report.anchor_broken,
        }
        return report.indexed_commit, head, drift
    except Exception:
        return None, None, _empty_drift()


def _equipment(context_dir: Path) -> dict[str, Any]:
    try:
        from dummyindex.context.domains.equip import read_manifest

        if not (context_dir / "equipment.json").is_file():
            return {"present": False, "items": 0, "schema_version": None}
        manifest = read_manifest(context_dir)
        return {
            "present": True,
            "items": len(manifest.items),
            "schema_version": manifest.schema_version,
        }
    except Exception:
        return {"present": False, "items": 0, "schema_version": None}


def _proposals(context_dir: Path) -> list[dict[str, Any]]:
    proposals_dir = context_dir / "proposals"
    if not proposals_dir.is_dir():
        return []
    try:
        from dummyindex.context.domains.buildloop import counts, parse_checklist
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    for entry in sorted(proposals_dir.iterdir()):
        checklist = entry / "checklist.md"
        if not checklist.is_file():
            continue
        try:
            done, total = counts(parse_checklist(checklist))
        except Exception:
            continue
        out.append({"slug": entry.name, "done": done, "total": total})
    return out


def _print_markdown(s: dict[str, Any]) -> None:
    print(f"dummyindex status @ {s['root']}")
    if not s["initialized"]:
        print("  index:      not initialized (run `dummyindex ingest`)")
        if s["version"]["cli"]:
            print(f"  CLI:        {s['version']['cli']}")
        return

    enriched = "enriched" if s["enriched"] else "deterministic-only"
    print(f"  index:      present ({enriched})")
    meta_v = s["version"]["meta"] or "unknown"
    cli_v = s["version"]["cli"] or "unknown"
    skew = "" if meta_v == cli_v else "  ⚠ skew — run /dummyindex-update"
    print(f"  version:    .context stamp {meta_v} / CLI {cli_v}{skew}")

    anchor = (s["indexed_commit"] or "—")[:12]
    head = (s["head"] or "—")[:12]
    print(f"  anchor:     {anchor}  (HEAD {head})")

    d = s["drift"]
    if d["anchor_broken"]:
        print("  drift:      anchor orphaned — cannot compute (re-baseline)")
    elif d["in_sync"]:
        print("  drift:      in sync")
    else:
        print(
            f"  drift:      {d['drifted_features']} drifted, "
            f"{d['unassigned_new_files']} unassigned, "
            f"{d['awaiting_enrichment']} awaiting enrichment, "
            f"{d['removed_files']} removed"
        )

    eq = s["equipment"]
    if eq["present"]:
        print(
            f"  equipment:  {eq['items']} item(s) "
            f"(schema v{eq['schema_version']})"
        )
    else:
        print("  equipment:  none (run `dummyindex context equip apply`)")

    if s["proposals"]:
        print("  proposals:")
        for p in s["proposals"]:
            print(f"    - {p['slug']}: {p['done']}/{p['total']} done")
    print(f"  session-memory: {'present' if s['session_memory'] else 'absent'}")
