"""Render a catalog decision into ``(item, rel_path, content)`` triples.

:func:`render_generated_set` is the single render path shared by the whole
lifecycle: apply renders + writes from it, refresh rebuilds the fresh-render map
from it, and reset picks the one matching artifact out of it. Given a
:class:`StackProfile` and the catalog's :class:`GenerateSpec` list, it fills the
toolchain slots (test/lint/typecheck commands + the dominant framework) and
stamps each generated artifact with its ``version`` (``1.0.0``), ``origin_hash``
(sha256 of the rendered bytes), and — for agents — its ``subagent_type``.

The CLI boundary wires this together; domain logic lives here so it is testable
in isolation without parsing args.
"""

from __future__ import annotations

from ..enums import EquipmentKind, EquipmentSource
from ..lifecycle.hashing import content_hash
from ..models import EquipmentItem, GenerateSpec, StackProfile
from .render import render_template
from .specialists import invariants_for

_INITIAL_VERSION = "1.0.0"


def render_generated_set(
    *,
    profile: StackProfile,
    specs: tuple[GenerateSpec, ...],
    conventions: tuple[str, ...],
    grounding: tuple[str, ...],
    proj: str,
    context_root: str = ".context",
) -> tuple[tuple[EquipmentItem, str, str], ...]:
    """Render each generated spec into a ``(item, rel_path, content)`` triple.

    Toolchain slots come from ``profile``; the framework slot uses the dominant
    (first) detected framework, or ``None`` (a readable placeholder) when none.
    ``proj`` is the project slug threaded into every render so the reviewer/verify
    templates fill their ``{{proj}}`` identifier (the implementer/tester ignore
    it); this keeps each artifact's frontmatter ``name:`` equal to its filename
    and manifest ``subagent_type``. Agents carry ``subagent_type`` (their own
    name, the build skill's dispatch target); skills/commands leave it ``None``.
    Every artifact is versioned at ``1.0.0`` and baselined with ``origin_hash``
    so the lifecycle can classify it.

    ``grounding`` is the base grounding shared by every artifact (the universal
    ``HOW_TO_USE`` pointer + the convention docs). A generated *specialist*
    additionally records its capability-specific docs (``spec.grounding_docs``)
    in ``grounded_in`` — metadata only, deduped and order-preserving, and never
    part of the rendered bytes, so it cannot shift the origin-hash baseline.

    A generated *specialist* also records its canary ``invariants`` — the
    load-bearing convention substrings its template emits verbatim (looked up by
    capability via :func:`invariants_for`). Like ``grounded_in`` these are
    **manifest metadata only** (D4): stamped onto the item, never injected into
    the rendered bytes, so the ``origin_hash`` (sha256 of ``content`` alone) is
    unaffected. The core four have no templated capability, so their invariants
    are ``()`` and their manifest entries stay byte-identical (back-compat).
    """
    framework = profile.frameworks[0] if profile.frameworks else None
    out: list[tuple[EquipmentItem, str, str]] = []
    for spec in specs:
        content = render_template(
            spec.template,
            stack=profile.label,
            proj=proj,
            conventions=conventions,
            context_root=context_root,
            test_command=profile.test_command,
            lint_command=profile.lint_command,
            typecheck_command=profile.typecheck_command,
            format_command=profile.format_command,
            framework=framework,
        )
        is_agent = spec.kind is EquipmentKind.AGENT
        item = EquipmentItem(
            kind=spec.kind,
            name=spec.name,
            path=spec.rel_path,
            source=EquipmentSource.GENERATED,
            capabilities=spec.capabilities,
            grounded_in=_merge_grounding(grounding, spec.grounding_docs),
            # Canary metadata (D4) — assembled exactly like grounded_in above:
            # stamped on the item, never part of `content`, so origin_hash (the
            # sha256 of the rendered bytes alone) is unchanged. Empty for the
            # core four (no templated capability), so their entries stay v3-byte-
            # identical and the canary stays dormant for them.
            invariants=invariants_for(spec.capabilities),
            subagent_type=spec.name if is_agent else None,
            version=_INITIAL_VERSION,
            origin_hash=content_hash(content),
        )
        out.append((item, spec.rel_path, content))
    return tuple(out)


def _merge_grounding(base: tuple[str, ...], extra: tuple[str, ...]) -> tuple[str, ...]:
    """Append ``extra`` grounding docs to ``base``, preserving order, no dupes."""
    merged = list(base)
    for doc in extra:
        if doc not in merged:
            merged.append(doc)
    return tuple(merged)
