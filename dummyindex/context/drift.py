"""Drift detection — the SessionStart "refresh" signal.

This is the engine behind ``dummyindex context plan-update``: the
SessionStart hook prints the result to stdout, Claude Code appends it
to the running session's system prompt, and the agent decides what to
reconcile.

Two complementary signals, *augmented* — neither replaces the other:

1. **mtime drift** (always on) — source files whose mtime is newer than
   the ``.context/features/<id>/`` docs describing them. Heuristic-decay:
   as soon as the agent edits ``features/<id>/plan.md`` its mtime updates
   and the signal goes quiet for that feature. No explicit stamp needed —
   file mtimes are the stamp. This is what keeps per-feature prose honest
   without forcing a council pass on every one-doc edit.
2. **commit-anchored signals** (when the index has an anchor) — the two
   things mtime structurally *cannot* see: ``unassigned_new_files`` (added
   files owned by no feature) and ``awaiting_enrichment`` (features a
   reconcile placed but didn't enrich). These come from the reconcile
   report (``meta.indexed_commit``..HEAD); off-git, ``unassigned`` is empty
   (it needs a git diff) but ``awaiting_enrichment`` still works (it scans
   committed markers). They clear only on ``reconcile-stamp``, so they nudge
   the session toward the reconcile procedure rather than a one-off doc edit.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dummyindex.context.build.manifest import read_manifest
from dummyindex.context.build.reconcile import (
    DOC_BASIS_REL,
    DOC_BASIS_VERSION,
    blob_sha,
    compute_reconcile_report,
)
from dummyindex.context.domains.drift_acks import read_acks
from dummyindex.pipeline.io.detect import detect

# Feature docs whose mtime is compared against the source mtime. If any
# of them is newer than the source, the feature is considered "fresh"
# for that file. We check the union (max mtime) — the agent may have
# updated security.md but not architecture.md; either counts.
_FEATURE_DOC_NAMES: tuple[str, ...] = (
    "spec.md",
    "plan.md",
    "concerns.md",
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
    """Result of a drift scan.

    ``rows`` is the mtime signal (stale per-feature docs) — always the
    *renderable* rows: files whose bytes match their doc-basis snapshot are
    suppressed (history-moved noise) and acked rows are dismissed, so neither
    appears here. ``unassigned_new_files`` and ``awaiting_enrichment`` are the
    commit-anchored signals (empty off-git for the former).
    ``drifted_features`` is the commit-anchored signal mtime structurally
    cannot see on an anchored repo: features owning files that were modified
    and committed since the index was reconciled (clears only on
    ``reconcile-stamp``). All four default empty, so a pre-augment
    ``DriftReport(rows=...)`` keeps comparing equal.

    The two counters are informational, never rendered as drift:
    ``suppressed_count`` counts distinct source files whose current blob sha
    equals their doc-basis entry (the stamp declared the docs fresh at those
    bytes — an mtime newer than the docs is then a git-op artefact), and
    ``acked_count`` counts rows dropped by a still-valid
    ``context drift-ack`` dismissal. Both default 0 for back-compat.
    """

    rows: tuple[DriftRow, ...]
    unassigned_new_files: tuple[str, ...] = ()
    awaiting_enrichment: tuple[str, ...] = ()
    drifted_features: tuple[str, ...] = ()
    suppressed_count: int = 0
    acked_count: int = 0

    @property
    def has_drift(self) -> bool:
        return bool(
            self.rows
            or self.unassigned_new_files
            or self.awaiting_enrichment
            or self.drifted_features
        )

    def by_feature(self) -> dict[str, tuple[str, ...]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for r in self.rows:
            grouped[r.feature_id].append(r.rel_path)
        return {fid: tuple(sorted(paths)) for fid, paths in grouped.items()}


def compute_badge(report: DriftReport) -> str:
    """Map a ``DriftReport`` to a short statusline badge string.

    Pure: no filesystem I/O, no side effects — it only renders the report's
    drift state. The badge cache is written at the CLI boundary, not here.

    Returns ``"[ctx ✓]"`` when the report shows no drift, otherwise a
    **labeled** count so users can act on what they see instead of one
    undifferentiated number: ``[ctx: E edited · A anchored]`` where ``E`` is
    the distinct edited source files and ``A`` is the anchored items — the
    unassigned new files plus awaiting-enrichment features plus committed-
    modification features. ``drifted_features`` is de-duplicated against the
    mtime ``by_feature()`` keys so a feature already named by an mtime row
    isn't counted twice. Zero segments are omitted; only-anchored renders as
    ``[ctx: N anchored]``, only-edited as ``[ctx: N edited]``.
    """
    if not report.has_drift:
        return "[ctx ✓]"
    mtime_features = set(report.by_feature())
    extra_drifted = set(report.drifted_features) - mtime_features
    edited = len({r.rel_path for r in report.rows})
    anchored = (
        len(report.unassigned_new_files)
        + len(report.awaiting_enrichment)
        + len(extra_drifted)
    )
    segments = []
    if edited:
        segments.append(f"{edited} edited")
    if anchored:
        segments.append(f"{anchored} anchored")
    if not segments:  # pragma: no cover — has_drift implies at least one
        return "[ctx ✓]"
    return f"[ctx: {' · '.join(segments)}]"


def compute_drift(project_root: Path) -> DriftReport:
    """Scan ``project_root`` for source files newer than their feature docs.

    Per-row basis classification runs before the mtime heuristic: when
    ``cache/doc-basis.json`` (written by ``reconcile-stamp``) has an entry for
    a (feature, file) pair, the sha decides — equal means the history merely
    moved under the index (suppressed, never rendered); different is a real
    edit since the docs were declared fresh. The fallback chain is basis →
    manifest sha → legacy mtime-only; absent both, the conservative direction
    wins and the row stays. Still-valid ``drift-ack`` entries drop their rows
    last. Returns an empty report when ``.context/features/`` is missing,
    when no source file is mapped to a feature, or when every feature
    doc is at least as recent as its members' source files.
    """
    project_root = project_root.resolve()
    context_dir = project_root / ".context"
    features_dir = context_dir / "features"
    if not features_dir.is_dir():
        return DriftReport(rows=())

    # Commit-anchored signals (empty off-git / no-anchor; awaiting still works
    # off-git since it scans committed markers, not a diff). Computed once.
    reconcile = compute_reconcile_report(context_dir, project_root)

    file_to_features = _build_file_feature_map(features_dir)
    if not file_to_features:
        return DriftReport(
            rows=(),
            unassigned_new_files=reconcile.unassigned_new_files,
            awaiting_enrichment=reconcile.awaiting_enrichment,
            drifted_features=reconcile.drifted_features,
        )

    detection = detect(project_root)
    files_dict = detection.get("files", {}) or {}
    source_paths: list[Path] = []
    for ftype in ("code", "document", "paper"):
        for raw in files_dict.get(ftype, []) or []:
            source_paths.append(Path(raw))

    # Content truth, tiered: a doc-basis entry (stamp-time blob sha) decides
    # for its (feature, file) pair; otherwise the manifest sha256 cross-check
    # applies; absent both, legacy mtime-only behaviour stands. Absent or
    # unreadable caches degrade to empty maps → conservative report.
    manifest_shas = _manifest_shas(context_dir)
    doc_basis = _read_doc_basis(context_dir)
    ack_entries = read_acks(context_dir)

    feature_mtime_cache: dict[str, float] = {}
    basis_sha_cache: dict[str, str | None] = {}
    src_by_rel: dict[str, Path] = {}
    rows: list[DriftRow] = []
    suppressed: set[str] = set()
    for src in source_paths:
        rel = _rel_or_none(src, project_root)
        if rel is None or rel not in file_to_features:
            continue
        try:
            src_mtime = src.stat().st_mtime
        except OSError:
            continue
        src_by_rel.setdefault(rel, src)
        owned = sorted(file_to_features[rel])
        on_basis = [fid for fid in owned if rel in doc_basis.get(fid, {})]
        fallback = [fid for fid in owned if fid not in on_basis]
        if on_basis:
            current = basis_sha_cache.get(rel)
            if rel not in basis_sha_cache:
                try:
                    current = blob_sha(src.read_bytes())
                except OSError:
                    current = None  # can't classify → conservative fallthrough
                basis_sha_cache[rel] = current
            if current is not None:
                for feature_id in on_basis:
                    if current == doc_basis[feature_id][rel]:
                        suppressed.add(rel)
                    else:
                        rows.append(DriftRow(rel_path=rel, feature_id=feature_id))
                if not fallback:
                    continue
            else:
                fallback = owned  # no readable bytes → mtime heuristic for all
        if _content_unchanged(src, manifest_shas.get(rel)):
            continue
        for feature_id in fallback:
            doc_mtime = feature_mtime_cache.get(feature_id)
            if doc_mtime is None:
                doc_mtime = _newest_doc_mtime(features_dir / feature_id)
                feature_mtime_cache[feature_id] = doc_mtime
            if src_mtime > doc_mtime:
                rows.append(DriftRow(rel_path=rel, feature_id=feature_id))

    def _ack_shas(rel: str) -> tuple[str, ...]:
        src = src_by_rel.get(rel)
        if src is None:
            return ()
        try:
            data = src.read_bytes()
        except OSError:
            return ()
        return (blob_sha(data), hashlib.sha256(data).hexdigest())

    rows, acked_count = _drop_acked_rows(rows, ack_entries, _ack_shas)

    rows.sort(key=lambda r: (r.feature_id, r.rel_path))
    return DriftReport(
        rows=tuple(rows),
        unassigned_new_files=reconcile.unassigned_new_files,
        awaiting_enrichment=reconcile.awaiting_enrichment,
        drifted_features=reconcile.drifted_features,
        suppressed_count=len(suppressed),
        acked_count=acked_count,
    )


def render_drift_summary(report: DriftReport) -> str:
    """Build the markdown body the SessionStart hook prints to stdout.

    Empty when ``report`` has no drift — caller should suppress output.
    Renders up to four sections: stale per-feature docs (mtime), net-new
    unplaced files, features awaiting enrichment, and features with committed
    modifications (the latter three from the commit anchor). Compact — one
    entry per line — so it stays cheap in tokens. ``drifted_features`` is
    de-duplicated against the mtime ``by_feature()`` keys so a feature already
    named by the mtime section isn't printed again.
    """
    if not report.has_drift:
        return ""

    extra_drifted = tuple(
        fid for fid in report.drifted_features if fid not in report.by_feature()
    )

    lines = ["## .context/ drift report", ""]
    if report.rows:
        lines.extend(_render_mtime_section(report))
    if report.unassigned_new_files:
        lines.extend(_render_unassigned_section(report.unassigned_new_files))
    if report.awaiting_enrichment:
        lines.extend(_render_awaiting_section(report.awaiting_enrichment))
    if extra_drifted:
        lines.extend(_render_drifted_features_section(extra_drifted))
    if report.unassigned_new_files or report.awaiting_enrichment or extra_drifted:
        lines.append("")
        lines.append(
            "_New/unenriched code is a commit-anchored signal — it clears only "
            "when you reconcile. Run the reconcile procedure (`/dummyindex "
            "--recouncil <feature-id>` on Claude or `$dummyindex --recouncil "
            "<feature-id>` on Codex, once per drifted feature; follow the "
            "installed dummyindex skill's reconcile procedure): place new "
            "files, (re-)enrich, then "
            "`reconcile-stamp` the anchor._"
        )
    return "\n".join(_collapse_blank_runs(lines))


def _collapse_blank_runs(lines: list[str]) -> list[str]:
    """Collapse any run of ≥2 blank lines to one.

    The header and each section contribute their own spacing, so a
    signals-only report (no mtime section between the header and the first
    subheader) would otherwise emit two consecutive blanks. Collapsing keeps
    the raw markdown the agent reads tidy regardless of which sections fire.
    """
    out: list[str] = []
    for line in lines:
        if line == "" and out and out[-1] == "":
            continue
        out.append(line)
    return out


def _render_mtime_section(report: DriftReport) -> list[str]:
    """The edited-since-docs section (mtime signal, heuristic-decay).

    The rows are the *edited* class only — basis-matched noise was already
    suppressed at scan time, so this section opens with its own header
    (``### Edited since docs``) and, when suppression fired, a one-line note
    saying how many files were held back.
    """
    grouped = report.by_feature()
    feature_count = len(grouped)
    # Count distinct files, not (feature, file) rows — a file owned by several
    # features contributes one row each and would otherwise inflate the count.
    file_count = len({r.rel_path for r in report.rows})
    # The doc list below is intentionally forward-only (v0.14 names). A
    # pre-reshape `.context/` whose legacy docs (architecture.md, …) are still
    # on disk is detected by `_FEATURE_DOC_NAMES` above; the nudge just points
    # at the names the session should be writing now.
    lines = [
        "### Edited since docs",
        "",
        (
            f"{file_count} source file{'s' if file_count != 1 else ''} "
            f"across {feature_count} feature{'s' if feature_count != 1 else ''} "
            "have been edited since the matching `.context/features/<id>/` "
            "docs were last touched. If your current task overlaps any of "
            "these features, review and update the relevant docs "
            "(`spec.md`, `plan.md`, `concerns.md`, "
            "`flows/*.md`) so `.context/` stays a reliable answer to "
            '"how does this code work?".'
        ),
        "",
    ]
    if report.suppressed_count > 0:
        n = report.suppressed_count
        lines.append(
            f"_{n} mtime-touched file{'s' if n != 1 else ''} matched their "
            "doc-basis and were suppressed._"
        )
        lines.append("")
    for feature_id in sorted(grouped):
        paths = grouped[feature_id]
        lines.append(f"- **{feature_id}** — {', '.join(paths)}")
    lines.append("")
    lines.append(
        "_Drift clears naturally: once you edit a feature doc, its mtime "
        "updates and these entries drop off._"
    )
    return lines


def _render_unassigned_section(paths: tuple[str, ...]) -> list[str]:
    """New files owned by no feature — the council decides where they go."""
    lines = [
        "",
        "### New files not yet in any feature",
        "",
        (
            f"{len(paths)} file(s) added since the index was last reconciled "
            "are owned by no feature. The reconcile procedure decides where "
            "each belongs (a new feature, or attached to an existing one)."
        ),
        "",
    ]
    lines.extend(f"- `{p}`" for p in paths)
    return lines


def _render_awaiting_section(feature_ids: tuple[str, ...]) -> list[str]:
    """Features a reconcile placed but did not finish enriching."""
    lines = [
        "",
        "### Features awaiting enrichment",
        "",
        (
            f"{len(feature_ids)} feature(s) were placed by a reconcile but not "
            "yet enriched (they carry a `.pending-enrichment` marker). Enrich "
            "them, then `dummyindex context mark-enriched --feature <id>`."
        ),
        "",
    ]
    lines.extend(f"- **{fid}**" for fid in feature_ids)
    return lines


def _render_drifted_features_section(feature_ids: tuple[str, ...]) -> list[str]:
    """Features owning files modified + committed since the last reconcile."""
    lines = [
        "",
        "### Features with committed modifications",
        "",
        (
            f"{len(feature_ids)} feature(s) own files that were modified and "
            "committed since the index was last reconciled. The reconcile "
            "procedure refreshes their docs against the committed changes; this "
            "signal clears only on `reconcile-stamp`."
        ),
        "",
    ]
    lines.extend(f"- **{fid}**" for fid in feature_ids)
    return lines


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


def _manifest_shas(context_dir: Path) -> dict[str, str]:
    """Repo-relative path → sha256 from ``cache/manifest.json``.

    Empty when the manifest is absent or unreadable — the cross-check then
    becomes a no-op (legacy mtime-only behaviour), never a crash. The manifest
    is the only content-true staleness oracle; the commit anchor tracks
    reconciliation and mtime is a heuristic nudge.
    """
    try:
        manifest = read_manifest(context_dir)
    except (OSError, json.JSONDecodeError, ValueError, KeyError):
        return {}
    if manifest is None:
        return {}
    return {rel: entry.sha256 for rel, entry in manifest.files.items()}


def _read_doc_basis(context_dir: Path) -> dict[str, dict[str, str]]:
    """Feature id → {rel_path: blob sha} from ``cache/doc-basis.json``.

    Mirrors :func:`_manifest_shas`' corrupt tolerance: absent file, bad JSON,
    wrong shape, or a ``basis_version`` this build doesn't speak all degrade
    to ``{}`` — the basis tier switches off and classification falls back to
    manifest → mtime, never a crash. Only written by ``reconcile-stamp``, so
    its absence simply means "no stamp since the feature existed".
    """
    path = context_dir / DOC_BASIS_REL
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return {}
    if not isinstance(obj, dict) or obj.get("basis_version") != DOC_BASIS_VERSION:
        return {}
    features = obj.get("features")
    if not isinstance(features, dict):
        return {}
    basis: dict[str, dict[str, str]] = {}
    for fid, files in features.items():
        if not isinstance(fid, str) or not isinstance(files, dict):
            continue
        shas = {
            rel: sha
            for rel, sha in files.items()
            if isinstance(rel, str) and isinstance(sha, str) and rel and sha
        }
        if shas:
            basis[fid] = shas
    return basis


def _drop_acked_rows(
    rows: list[DriftRow],
    ack_entries: list[dict],
    sha_resolver,
) -> tuple[list[DriftRow], int]:
    """Drop rows covered by a still-valid ack; return (kept rows, dropped count).

    An ack matches a row when the feature id matches, the entry's ``path`` is
    unset (feature-wide) or equals the row's path, and the file's current sha
    still equals ``acked_sha`` — any edit changes the sha and auto-expires the
    dismissal. On-git acks carry git blob shas, off-git ones content sha256;
    ``sha_resolver`` maps a repo-relative path to the tuple of current shas in
    both flavors (empty when the file is unreadable → never suppress).
    """
    if not rows or not ack_entries:
        return rows, 0
    kept: list[DriftRow] = []
    dropped = 0
    for row in rows:
        shas = sha_resolver(row.rel_path)
        valid = any(
            entry.get("feature_id") == row.feature_id
            and entry.get("path") in (None, row.rel_path)
            and isinstance(entry.get("acked_sha"), str)
            and entry["acked_sha"] in shas
            for entry in ack_entries
        )
        if valid:
            dropped += 1
        else:
            kept.append(row)
    return kept, dropped


def _content_unchanged(src: Path, manifest_sha: str | None) -> bool:
    """True when ``src``'s current sha256 matches its manifest entry.

    A match means the bytes are identical to the last build — an mtime newer
    than the docs is then a git-operation artefact, not real drift. Returns
    ``False`` (keep the row) when there's no manifest entry or the file can't
    be hashed, so the conservative direction (report) wins on any doubt.
    """
    if not manifest_sha:
        return False
    try:
        data = src.read_bytes()
    except OSError:
        return False
    return hashlib.sha256(data).hexdigest() == manifest_sha


def _rel_or_none(path: Path, root: Path) -> str | None:
    p = path if path.is_absolute() else (root / path)
    try:
        return p.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return None
