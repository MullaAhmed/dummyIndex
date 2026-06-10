"""Per-feature docs.md generation from the source-docs catalog.

`_write_feature_docs` runs after scaffold and writes
`.context/features/<id>/docs.md` for each feature whose name / files /
symbols are referenced by a catalogued doc. Docs are stored as relative
pointers; the catalog's confidence + broken-ref signals remain the
authoritative staleness source.
"""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
from dummyindex.context.enums import DOC_CONFIDENCE_ORDER

from .constants import _FEATURE_DOCS_TOP_N
from .helpers import _primary_reason_kind, _write_text
from .models import Feature

_REASON_RANK: dict[str, int] = {
    "path": 0,    # path match is the strongest signal
    "symbol": 1,
    "title": 2,
}

if TYPE_CHECKING:
    from dummyindex.context.domains.source_docs import DocCatalog, DocEntry


def _write_feature_docs(
    features_dir: Path,
    features: tuple[Feature, ...],
    catalog: "DocCatalog",
    node_by_id: dict[str, dict],
) -> tuple[str, ...]:
    """Write ``features/<id>/docs.md`` pointing at catalog entries that
    overlap with each feature's files or symbol names.

    Match heuristics (per (feature, doc) pair):

    1. **File overlap.** Doc references any file path in the feature's
       ``files`` list — counts as a strong match.
    2. **Symbol overlap.** Doc references any symbol name carried by a
       member node — strong match.
    3. **Title match.** Doc title or H1/H2 contains the feature's name or
       feature_id token — weaker match, but useful before enrichment.

    We don't embed doc *content* in ``docs.md`` — every entry is a link
    back to the catalog so confidence/broken-refs stay in one place.
    """
    written: list[str] = []

    # Pull each doc's text once so we don't re-read for every feature.
    doc_texts: dict[str, str] = {}
    for d in catalog.docs:
        try:
            doc_texts[d.path] = Path(d.abs_path).read_text(
                encoding="utf-8", errors="ignore"
            ) if Path(d.abs_path).suffix.lower() in (".md", ".mdx", ".rst", ".txt", ".html", ".htm") else ""
        except OSError:
            doc_texts[d.path] = ""

    for feat in features:
        # Member symbol names — pull from the graph nodes so we get the
        # actual identifiers, not just node IDs (which are opaque hashes).
        member_names: set[str] = set()
        for member_id in feat.members:
            node = node_by_id.get(member_id, {})
            label = node.get("label")
            if isinstance(label, str) and label:
                clean = label.rstrip("()").lstrip(".")
                if clean:
                    member_names.add(clean)

        files_set = set(feat.files)

        matches: list[tuple[str, "DocEntry", str]] = []
        for d in catalog.docs:
            reasons = _doc_matches_feature(
                d, doc_texts.get(d.path, ""), files_set, member_names, feat
            )
            if reasons:
                matches.append((d.path, d, reasons))

        if not matches:
            continue

        feat_dir = features_dir / feat.feature_id
        if not feat_dir.exists():
            continue
        target = feat_dir / "docs.md"
        _write_text(target, _render_feature_docs_md(feat, matches))
        written.append(f"features/{feat.feature_id}/docs.md")

    return tuple(written)

def _doc_matches_feature(
    doc: "DocEntry",
    text: str,
    feature_files: set[str],
    feature_symbols: set[str],
    feat: Feature,
) -> str:
    """Return a short reason string when ``doc`` matches the feature.

    Empty string means "no match". The reason is rendered into the
    feature's ``docs.md`` so a reader can see *why* dummyindex linked
    this doc here without re-deriving it.
    """
    reasons: list[str] = []

    # Whole-feature-id substring match in title — strong signal before
    # enrichment renames the feature.
    if doc.title and (feat.feature_id in doc.title.lower() or feat.name.lower() in doc.title.lower()):
        reasons.append("title")

    if text:
        # Path mentions — backtick-aware (the catalog already finds these,
        # but we re-check so docs.md can cite the matching file).
        for fp in feature_files:
            if fp in text:
                reasons.append(f"path:{fp}")
                break
        for sym in feature_symbols:
            # Require word-boundaries via backtick or whitespace to avoid
            # matching `name` inside a longer identifier.
            if f"`{sym}" in text or f"`{sym}()" in text:
                reasons.append(f"symbol:{sym}")
                break

    return ", ".join(reasons)


# Cap per-feature doc pointer lists. Repos with heavy doc-to-code
# coupling (the dummyindex repo's own brief docs touch ~every
# feature) would otherwise produce huge docs.md files. The cap is
# generous enough to keep useful context, capped enough to keep the
# council's prompt budget predictable.
def _render_feature_docs_md(
    feat: Feature,
    matches: list[tuple[str, "DocEntry", str]],
) -> str:
    """Render ``features/<id>/docs.md`` as a pointer list, not a content copy.

    Sort by (confidence, reason rank, path) so the most useful matches
    land at the top. Cap at ``_FEATURE_DOCS_TOP_N`` and surface the
    overflow count with a pointer back to the catalog.
    """
    matches_sorted = sorted(
        matches,
        key=lambda m: (
            DOC_CONFIDENCE_ORDER.get(m[1].confidence, 3),
            _REASON_RANK.get(_primary_reason_kind(m[2]), 99),
            m[0],
        ),
    )

    shown = matches_sorted[:_FEATURE_DOCS_TOP_N]
    overflow = len(matches_sorted) - len(shown)

    lines: list[str] = [
        f"# Existing docs that touch `{feat.name}`",
        "",
        (
            "_Pointer list — the canonical entries (with confidence + "
            "broken-references) live in `../../source-docs/INDEX.md`. "
            "**Treat doc claims as hypotheses; verify against "
            "`feature.json` + `../../map/symbols.json` before quoting.**_"
        ),
        "",
    ]
    for path, doc, reason in shown:
        title = f" — {doc.title}" if doc.title else ""
        # features/<id>/docs.md sits 3 levels under the repo root
        # (.context/features/<id>/docs.md), so doc links need three
        # "../" hops to land on the source file. Catalog entries are
        # repo-relative POSIX paths; external docs use their absolute
        # path because there's no relative anchor.
        target = doc.abs_path if doc.is_external else f"../../../{path}"
        lines.append(
            f"- [`{path}`]({target}) "
            f"(**{doc.confidence}**{title}) "
            f"_matched on:_ `{reason}`"
        )
        if doc.broken_refs:
            preview = list(doc.broken_refs[:3])
            extra = max(0, len(doc.broken_refs) - len(preview))
            tail = "" if not extra else f", … +{extra} more"
            lines.append(
                f"  - ⚠ broken refs: {', '.join('`'+r+'`' for r in preview)}{tail}"
            )
    if overflow > 0:
        lines.append("")
        lines.append(
            f"_… +{overflow} more in [`../../source-docs/INDEX.md`]"
            f"(../../source-docs/INDEX.md)._"
        )
    lines.append("")
    return "\n".join(lines) + "\n"

