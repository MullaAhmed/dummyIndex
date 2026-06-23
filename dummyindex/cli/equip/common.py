"""Shared plumbing for the ``equip`` subcommand's split modules.

Private to the equip subcommand pair (``equip.py`` + ``_equip_verbs.py``), the
way ``_migrate.py`` is private to init/rebuild: local flag parsing (never the
shared ``parse_path_and_root`` — its ``_FLAGS_TAKING_VALUE`` table would
mis-handle equip's flags), root resolution, and the fresh-render set the
lifecycle verbs and the apply pipeline both consume.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from dummyindex.context.domains.equip import (
    GENERATED_SENTINEL,
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

from ..common import resolve_context_root

# Grounding cited by every rendered tool (in addition to the conventions list).
_GROUNDING_BASE: tuple[str, ...] = (".context/HOW_TO_USE.md",)
_SETTINGS_REL = ".claude/settings.json"


# ----- flag parsing (local; never the shared parse_path_and_root) ----------


def pull_flag_value(rest: list[str], name: str) -> tuple[str | None, list[str]]:
    """Strip a single ``--name VALUE`` / ``--name=VALUE`` out of ``rest``.

    Mirrors ``cli.build_loop.pull_flag_value`` — local so we never route equip
    through the shared ``parse_path_and_root`` (whose ``_FLAGS_TAKING_VALUE``
    table would mis-handle equip's own ``--status``-class flags).
    """
    value: str | None = None
    out: list[str] = []
    i = 0
    long_flag = f"--{name}"
    eq_prefix = f"--{name}="
    while i < len(rest):
        a = rest[i]
        if a == long_flag and i + 1 < len(rest):
            value = rest[i + 1]
            i += 2
        elif a.startswith(eq_prefix):
            value = a.split("=", 1)[1]
            i += 1
        else:
            out.append(a)
            i += 1
    return value, out


def pull_bool_flag(rest: list[str], name: str) -> tuple[bool, list[str]]:
    """Strip every ``--name`` occurrence; return (present?, remaining)."""
    flag = f"--{name}"
    present = flag in rest
    return present, [a for a in rest if a != flag]


def pull_root(rest: list[str]) -> tuple[Path | None, list[str]]:
    value, rest = pull_flag_value(rest, "root")
    return (Path(value) if value else None), rest


def resolve_root(rest: list[str]) -> tuple[Path, list[str]]:
    """Pull ``--root`` and a single optional positional path; resolve the root."""
    explicit_root, rest = pull_root(rest)
    scope = Path(".")
    leftover: list[str] = []
    saw_scope = False
    for a in rest:
        if not a.startswith("--") and not saw_scope:
            scope = Path(a)
            saw_scope = True
        else:
            leftover.append(a)
    return resolve_context_root(scope, explicit_root=explicit_root), leftover


def pull_root_then_positional(
    rest: list[str],
) -> tuple[Path, tuple[str | None, list[str]]]:
    """Pull ``--root DIR`` then take the first positional as a NAME (not a path).

    Shared by ``equip reset NAME`` and ``equip add-specialist CAPABILITY`` — both
    take a single bare positional that is an identifier, not a scope path, so the
    root always resolves from the cwd (override with ``--root``).
    """
    explicit_root, rest = pull_root(rest)
    name: str | None = None
    leftover: list[str] = []
    for a in rest:
        if not a.startswith("--") and name is None:
            name = a
        else:
            leftover.append(a)
    root = resolve_context_root(Path("."), explicit_root=explicit_root)
    return root, (name, leftover)


def specialist_caps_from_manifest(manifest: EquipmentManifest) -> tuple[str, ...]:
    """Capabilities of already-applied generated specialists, in manifest order.

    These are carried forward as ``forced_specialist_capabilities`` so a plain
    ``equip`` re-apply (or a ``refresh``/``reset``) re-renders every specialist
    that was previously added, instead of silently dropping it. A specialist is a
    lifecycle-managed (generated, file-backed, hash-baselined) item carrying a
    capability a template backs. The core four carry only implement/test/review/
    verify — none templated — so they never appear here.
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

    A stem is dropped when it matches a prior GENERATED/VENDORED manifest item's
    name, or when its file body carries one of equip's sentinels (covers a
    generated/vendored file whose manifest record was lost). Without this gate
    a repo dir named ``frontend`` makes the generated ``frontend-reviewer`` look
    like a user-authored project agent and it gets re-adopted as a second,
    conflicting INSTALLED record. CLI-boundary helper — it reads files, so it
    stays out of the pure adopt/catalog domain.
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

    The specialist templates declare candidate ``.context/`` docs (including
    both DECISIONS locations); recording a path that does not exist plants dead
    links in the manifest's audit trail. Metadata-only: ``grounding_docs`` are
    never part of the rendered bytes, so filtering cannot shift origin hashes.
    The universal base grounding + the conventions list are already
    disk-derived and stay untouched.
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
    """Rebuild the catalog's fresh render for every generated item, by name.

    The same detect → catalog → render path apply uses, so refresh/reset compare
    and restore against exactly what a fresh apply would write today. Any
    already-applied specialist is reconstructed from the manifest (an absent
    manifest yields the core four only — specialists are strictly opt-in), so
    the lifecycle treats a generated specialist identically to the core four.

    Raises :class:`EquipError` if the manifest exists but is corrupt (an absent
    manifest is not an error — it reads as "no prior specialists"); both
    callers (``run_refresh`` / ``run_reset``) catch it and exit 1.
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
    return {item.name: content for item, _rel, content in rendered}


# ----- helpers --------------------------------------------------------------


def project_slug(project_root: Path) -> str:
    """A filesystem-safe lowercase slug from the project dir name.

    Used in the verify skill's directory name (``<proj>-verify``). Falls back to
    ``project`` when the dir name has no usable characters.
    """
    raw = project_root.name.lower()
    cleaned = "".join(ch if (ch.isalnum() or ch == "-") else "-" for ch in raw)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "project"
