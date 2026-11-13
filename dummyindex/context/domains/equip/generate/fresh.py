"""Fresh-render helpers: what a fresh apply would write today, by item name.

Moved out of ``cli/equip/common.py`` so the domain never imports ``cli/``
(``conventions/folder-organization.md``). The CLI re-exports these names.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from dummyindex.context.domains.equip import (
    GENERATED_SENTINEL,
    EquipmentItem,
    EquipmentManifest,
    EquipmentSource,
    GenerateSpec,
    build_catalog,
    detect_stack,
    is_lifecycle_managed,
    list_convention_docs,
    read_manifest,
    render_generated_set,
    templated_capabilities,
)
from dummyindex.context.domains.equip.constants import VENDORED_SENTINEL

# Grounding cited by every rendered tool (in addition to the conventions list).
_GROUNDING_BASE: tuple[str, ...] = (".context/HOW_TO_USE.md",)


def specialist_caps_from_manifest(manifest: EquipmentManifest) -> tuple[str, ...]:
    """Capabilities of already-applied generated specialists, in manifest order.

    Carried forward as ``forced_specialist_capabilities`` so a re-apply,
    ``refresh`` or ``reset`` never silently drops a specialist (a lifecycle-managed
    item with a templated capability; the core four have none, so never appear).
    """
    templated = templated_capabilities()
    seen: list[str] = []
    for item in manifest.items:
        if not is_lifecycle_managed(item):
            continue
        for capability in item.capabilities:
            if capability in templated and capability not in seen:
                seen.append(capability)
    return tuple(seen)


def drop_generated_stems(
    project_root: Path, prior: EquipmentManifest, stems: tuple[str, ...]
) -> tuple[str, ...]:
    """Filter equip's own output out of the preflight's project-agent stems.

    Drops a stem naming a prior GENERATED/VENDORED item, or whose
    ``.claude/agents/<stem>.md`` carries an equip sentinel (a lost manifest
    record). A missing or unreadable file is kept. Otherwise e.g. the generated
    ``frontend-reviewer`` would be re-adopted as a conflicting INSTALLED record.
    """
    own_names = {
        i.name
        for i in prior.items
        if i.source in (EquipmentSource.GENERATED, EquipmentSource.VENDORED)
    }
    kept: list[str] = []
    for stem in stems:
        if stem in own_names:
            continue
        path = project_root / ".claude" / "agents" / f"{stem}.md"
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            body = ""
        if GENERATED_SENTINEL in body or VENDORED_SENTINEL in body:
            continue
        kept.append(stem)
    return tuple(kept)


def filter_grounding_docs(
    project_root: Path, specs: tuple[GenerateSpec, ...]
) -> tuple[GenerateSpec, ...]:
    """Drop capability grounding docs that do not exist on disk.

    Templates declare candidate ``.context/`` docs (both DECISIONS locations); a
    missing one would plant dead links in the manifest. ``grounding_docs`` are
    never part of the rendered bytes, so filtering cannot shift origin hashes.
    """
    out: list[GenerateSpec] = []
    for spec in specs:
        kept = tuple(d for d in spec.grounding_docs if (project_root / d).is_file())
        out.append(
            dataclasses.replace(spec, grounding_docs=kept)
            if kept != spec.grounding_docs
            else spec
        )
    return tuple(out)


def fresh_renders(project_root: Path, context_dir: Path) -> dict[str, str]:
    return {
        item.name: content
        for item, _rel, content in fresh_rendered(project_root, context_dir)
    }


def fresh_rendered(
    project_root: Path, context_dir: Path
) -> tuple[tuple[EquipmentItem, str, str], ...]:
    """Rebuild the catalog's fresh render for every generated item, by name.

    Apply's own detect → catalog → render path, so refresh/reset compare against
    what a fresh apply writes today. Applied specialists are rebuilt from the
    manifest so their order, and so their hash-baselined identity, is preserved.
    Raises :class:`EquipError` on a corrupt manifest (absent means no prior
    specialists); ``run_refresh`` / ``run_reset`` catch it and exit 1.
    """
    from dummyindex.context.domains.preflight import build_preflight_report

    manifest = read_manifest(context_dir)
    report = build_preflight_report(project_root)
    report = dataclasses.replace(
        report,
        project_agents=drop_generated_stems(
            project_root, manifest, report.project_agents
        ),
    )
    profile = detect_stack(context_dir)
    conventions = list_convention_docs(context_dir)
    grounding = _GROUNDING_BASE + conventions
    proj = project_slug(project_root)
    forced = specialist_caps_from_manifest(manifest)
    decision = build_catalog(
        profile=profile,
        conventions=conventions,
        preflight=report,
        proj=proj,
        forced_specialist_capabilities=forced,
    )
    rendered = render_generated_set(
        profile=profile,
        specs=filter_grounding_docs(project_root, decision.generate),
        conventions=conventions,
        grounding=grounding,
        proj=proj,
    )
    return rendered


# --- helpers


def project_slug(project_root: Path) -> str:
    """A filesystem-safe lowercase slug from the project dir name.

    Used in the verify skill's directory name (``<proj>-verify``). Falls back to
    ``project`` when the dir name has no usable characters.
    """
    raw = project_root.name.lower()
    cleaned = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in raw)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "project"
