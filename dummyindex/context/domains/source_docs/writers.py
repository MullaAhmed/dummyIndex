"""Write the catalog: ``source-docs/INDEX.json`` + ``source-docs/INDEX.md``."""

from __future__ import annotations

import json
from pathlib import Path

from dummyindex.context.enums import DocConfidence

from .constants import _ADVISORY_BANNER
from .models import DocCatalog, DocEntry, _confidence_breakdown


def write_catalog(context_dir: Path, catalog: DocCatalog) -> tuple[Path, Path]:
    """Write ``source-docs/INDEX.json`` and ``source-docs/INDEX.md``."""
    out_dir = context_dir / "source-docs"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "INDEX.json"
    md_path = out_dir / "INDEX.md"

    payload = catalog.to_dict()
    _atomic_write(json_path, json.dumps(payload, indent=2, sort_keys=False) + "\n")
    _atomic_write(md_path, _render_catalog_md(catalog))
    return json_path, md_path


def _render_catalog_md(catalog: DocCatalog) -> str:
    by_conf = _confidence_breakdown(catalog.docs)
    lines: list[str] = []
    lines.append("# Existing documentation (source-docs)")
    lines.append("")
    lines.append(_ADVISORY_BANNER.rstrip())
    lines.append("")
    lines.append(
        f"_{len(catalog.docs)} doc(s) — "
        f"{by_conf.get('high', 0)} high · "
        f"{by_conf.get('medium', 0)} medium · "
        f"{by_conf.get('low', 0)} low._"
    )
    lines.append("")
    if catalog.extra_doc_roots:
        lines.append("**External doc roots (passed via `--docs`):**")
        lines.append("")
        for root in catalog.extra_doc_roots:
            lines.append(f"- `{root}`")
        lines.append("")
    if not catalog.docs:
        lines.append(
            "_No documents discovered. Pass `--docs PATH` (repeatable) to "
            "point dummyindex at doc folders outside the scan root._"
        )
        lines.append("")
        return "\n".join(lines) + "\n"

    lines.append("| Doc | Type | Confidence | Broken refs | Age |")
    lines.append("|---|---|---|---|---|")
    for d in catalog.docs:
        broken = (
            f"{len(d.broken_refs)} / {d.referenced_count}"
            if d.referenced_count
            else "—"
        )
        title_part = f" — {d.title}" if d.title else ""
        lines.append(
            f"| [`{d.path}`]({_md_link_target(d)}){title_part} | "
            f"{d.doc_type} | **{d.confidence}** | {broken} | {d.age_bucket} |"
        )
    lines.append("")

    low_conf = [d for d in catalog.docs if d.confidence == DocConfidence.LOW]
    if low_conf:
        lines.append("## Low-confidence docs")
        lines.append("")
        lines.append(
            "These have broken references or are significantly older than "
            "the newest code change. Don't quote without verifying against "
            "current source."
        )
        lines.append("")
        for d in low_conf:
            lines.append(f"### `{d.path}`")
            lines.append("")
            if d.broken_refs:
                shown = list(d.broken_refs[:10])
                more = max(0, len(d.broken_refs) - len(shown))
                lines.append("**Broken references** (no longer in the AST):")
                lines.append("")
                for ref in shown:
                    lines.append(f"- `{ref}`")
                if more:
                    lines.append(f"- _… +{more} more_")
                lines.append("")
            if d.age_bucket in ("stale", "old") and d.age_delta_seconds is not None:
                days = int(d.age_delta_seconds // 86400)
                lines.append(
                    f"_Last edited {days} day(s) before the newest code change._"
                )
                lines.append("")
    return "\n".join(lines) + "\n"


def _md_link_target(entry: DocEntry) -> str:
    """Make a relative link from source-docs/INDEX.md back to the doc.

    For in-repo docs, escape up one level (we're in .context/source-docs/).
    For external docs, link via the absolute path (won't render as a click
    target on most viewers, but is at least informative).
    """
    if entry.is_external:
        return entry.abs_path
    return f"../../{entry.path}"


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
