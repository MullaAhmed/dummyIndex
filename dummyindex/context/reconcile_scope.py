"""Attribute reconciliation only to paths actually edited by this session."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .build.reconcile import is_non_source_path
from .drift import DriftReport


def partition_session_drift(
    stale: list[tuple[Path, DriftReport]],
    edited_paths: tuple[str, ...],
    *,
    base: Path,
    context_roots: tuple[Path, ...],
) -> tuple[list[tuple[Path, DriftReport]], list[tuple[Path, DriftReport]]]:
    owned: dict[Path, set[str]] = {}
    for raw in edited_paths:
        path = Path(raw)
        path = (path if path.is_absolute() else base / path).resolve()
        roots = [root for root in context_roots if path.is_relative_to(root)]
        if not roots:
            continue
        owner = max(roots, key=lambda root: len(root.parts))
        relative = path.relative_to(owner).as_posix()
        if not is_non_source_path(relative, project_root=owner):
            owned.setdefault(owner, set()).add(relative)
    relevant, unrelated = [], []
    for root, report in stale:
        paths = owned.get(root, set())
        rows = tuple(row for row in report.rows if row.rel_path in paths)
        features = {row.feature_id for row in rows}
        for feature in (*report.awaiting_enrichment, *report.drifted_features):
            location = root / ".context/features" / feature / "feature.json"
            try:
                files = json.loads(location.read_text(encoding="utf-8")).get(
                    "files", []
                )
            except (OSError, ValueError, AttributeError):
                continue
            if paths.intersection(files):
                features.add(feature)
        current = replace(
            report,
            rows=rows,
            unassigned_new_files=tuple(
                path for path in report.unassigned_new_files if path in paths
            ),
            awaiting_enrichment=tuple(
                f for f in report.awaiting_enrichment if f in features
            ),
            drifted_features=tuple(f for f in report.drifted_features if f in features),
        )
        rest = replace(
            report,
            rows=tuple(row for row in report.rows if row not in current.rows),
            unassigned_new_files=tuple(
                path
                for path in report.unassigned_new_files
                if path not in current.unassigned_new_files
            ),
            awaiting_enrichment=tuple(
                f
                for f in report.awaiting_enrichment
                if f not in current.awaiting_enrichment
            ),
            drifted_features=tuple(
                f for f in report.drifted_features if f not in current.drifted_features
            ),
        )
        if current.has_drift:
            relevant.append((root, current))
        if rest.has_drift:
            unrelated.append((root, rest))
    return relevant, unrelated


def unrelated_summary(stale: list[tuple[Path, DriftReport]], *, base: Path) -> str:
    lines = [
        "Unrelated context drift remains advisory; this session does not own its reconciliation:"
    ]
    for root, report in stale[:8]:
        label = root.relative_to(base).as_posix() or "."
        count = (
            len(report.rows)
            + len(report.unassigned_new_files)
            + len(report.awaiting_enrichment)
            + len(report.drifted_features)
        )
        lines.append(
            f"- {label}: {count} drift signals; inspect with dummyindex context plan-update --root {label}"
        )
    if len(stale) > 8:
        lines.append(f"- {len(stale) - 8} additional roots omitted from this advisory")
    return "\n".join(lines)
