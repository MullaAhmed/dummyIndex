"""Drift detection — find source files whose mtime is newer than the
mtime of the `.context/features/<id>/` documents that describe them.

This is the engine behind ``dummyindex context plan-update``: the
SessionStart hook prints the result to stdout, Claude Code appends it
to the running session's system prompt, and the agent decides which
feature docs to refresh.

The "newer than" check is a heuristic-decay design: as soon as the
agent edits ``features/<id>/architecture.md``, its mtime updates and
the drift signal naturally goes quiet for that feature. No explicit
``mark-updated`` command is needed — file mtimes are the stamp.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dummyindex.pipeline.io.detect import detect


# Feature docs whose mtime is compared against the source mtime. If any
# of them is newer than the source, the feature is considered "fresh"
# for that file. We check the union (max mtime) — the agent may have
# updated security.md but not architecture.md; either counts.
_FEATURE_DOC_NAMES: tuple[str, ...] = (
    "architecture.md",
    "data-model.md",
    "implementation.md",
    "product.md",
    "security.md",
    "supporting.md",
)


@dataclass(frozen=True)
class DriftRow:
    """One source file that's newer than the feature docs describing it."""

    rel_path: str
    feature_id: str


@dataclass(frozen=True)
class DriftReport:
    """Result of a drift scan; ``rows`` is empty when nothing is stale."""

    rows: tuple[DriftRow, ...]

    @property
    def has_drift(self) -> bool:
        return bool(self.rows)

    def by_feature(self) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for r in self.rows:
            grouped[r.feature_id].append(r.rel_path)
        return {fid: tuple(sorted(paths)) for fid, paths in grouped.items()}


def compute_drift(project_root: Path) -> DriftReport:
    """Scan ``project_root`` for source files newer than their feature docs.

    Returns an empty report when ``.context/features/`` is missing,
    when no source file is mapped to a feature, or when every feature
    doc is at least as recent as its members' source files.
    """
    project_root = project_root.resolve()
    context_dir = project_root / ".context"
    features_dir = context_dir / "features"
    if not features_dir.is_dir():
        return DriftReport(rows=())

    file_to_features = _build_file_feature_map(features_dir)
    if not file_to_features:
        return DriftReport(rows=())

    detection = detect(project_root)
    files_dict = detection.get("files", {}) or {}
    source_paths: list[Path] = []
    for ftype in ("code", "document", "paper"):
        for raw in files_dict.get(ftype, []) or []:
            source_paths.append(Path(raw))

    feature_mtime_cache: dict[str, float] = {}
    rows: list[DriftRow] = []
    for src in source_paths:
        rel = _rel_or_none(src, project_root)
        if rel is None or rel not in file_to_features:
            continue
        try:
            src_mtime = src.stat().st_mtime
        except OSError:
            continue
        for feature_id in sorted(file_to_features[rel]):
            doc_mtime = feature_mtime_cache.get(feature_id)
            if doc_mtime is None:
                doc_mtime = _newest_doc_mtime(features_dir / feature_id)
                feature_mtime_cache[feature_id] = doc_mtime
            if src_mtime > doc_mtime:
                rows.append(DriftRow(rel_path=rel, feature_id=feature_id))

    rows.sort(key=lambda r: (r.feature_id, r.rel_path))
    return DriftReport(rows=tuple(rows))


def render_drift_summary(report: DriftReport) -> str:
    """Build the markdown body the SessionStart hook prints to stdout.

    Empty when ``report`` has no drift — caller should suppress output.
    Compact format: one feature per line with its stale files, so the
    addendum stays cheap in token cost even on a large repo.
    """
    if not report.has_drift:
        return ""

    grouped = report.by_feature()
    feature_count = len(grouped)
    file_count = len(report.rows)
    lines = [
        "## .context/ drift report",
        "",
        (
            f"{file_count} source file{'s' if file_count != 1 else ''} "
            f"across {feature_count} feature{'s' if feature_count != 1 else ''} "
            "have been edited since the matching `.context/features/<id>/` "
            "docs were last touched. If your current task overlaps any of "
            "these features, review and update the relevant docs "
            "(`architecture.md`, `data-model.md`, `security.md`, "
            "`product.md`, `supporting.md`, `implementation.md`, "
            "`flows/*.md`) so `.context/` stays a reliable answer to "
            "\"how does this code work?\"."
        ),
        "",
    ]
    for feature_id in sorted(grouped):
        paths = grouped[feature_id]
        lines.append(f"- **{feature_id}** — {', '.join(paths)}")
    lines.append("")
    lines.append(
        "_Drift clears naturally: once you edit a feature doc, its mtime "
        "updates and these entries drop off._"
    )
    return "\n".join(lines)


def _build_file_feature_map(features_dir: Path) -> dict[str, set[str]]:
    """Read every ``features/<id>/feature.json`` and invert files → features."""
    mapping: dict[str, set[str]] = defaultdict(set)
    for child in sorted(features_dir.iterdir()):
        if not child.is_dir():
            continue
        feature_json = child / "feature.json"
        if not feature_json.is_file():
            continue
        try:
            payload = json.loads(feature_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        feature_id = payload.get("feature_id") or child.name
        for path in _iter_feature_files(payload):
            mapping[path].add(feature_id)
    return mapping


def _iter_feature_files(payload: dict) -> Iterable[str]:
    raw = payload.get("files")
    if not isinstance(raw, list):
        return
    for f in raw:
        if isinstance(f, str) and f:
            yield f


def _newest_doc_mtime(feature_dir: Path) -> float:
    """Return the max mtime across the feature's prose docs.

    Returns 0 when the feature folder has no scaffolded docs yet — in
    that state every source change is drift, which is the correct
    signal: the feature hasn't been authored.
    """
    newest = 0.0
    for name in _FEATURE_DOC_NAMES:
        candidate = feature_dir / name
        try:
            newest = max(newest, candidate.stat().st_mtime)
        except OSError:
            continue
    return newest


def _rel_or_none(path: Path, root: Path) -> str | None:
    p = path if path.is_absolute() else (root / path)
    try:
        return p.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return None
