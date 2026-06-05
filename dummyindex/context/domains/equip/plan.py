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

from ._hash import content_hash
from .enums import EquipmentKind, EquipmentSource
from .models import EquipmentItem, GenerateSpec, StackProfile
from .render import render_template

_INITIAL_VERSION = "1.0.0"


def render_generated_set(
    *,
    profile: StackProfile,
    specs: tuple[GenerateSpec, ...],
    conventions: tuple[str, ...],
    grounding: tuple[str, ...],
    context_root: str = ".context",
) -> tuple[tuple[EquipmentItem, str, str], ...]:
    """Render each generated spec into a ``(item, rel_path, content)`` triple.

    Toolchain slots come from ``profile``; the framework slot uses the dominant
    (first) detected framework, or ``None`` (a readable placeholder) when none.
    Agents carry ``subagent_type`` (their own name, the build skill's dispatch
    target); skills/commands leave it ``None``. Every artifact is versioned at
    ``1.0.0`` and baselined with ``origin_hash`` so the lifecycle can classify it.
    """
    framework = profile.frameworks[0] if profile.frameworks else None
    out: list[tuple[EquipmentItem, str, str]] = []
    for spec in specs:
        content = render_template(
            spec.template,
            stack=profile.label,
            conventions=conventions,
            context_root=context_root,
            test_command=profile.test_command,
            lint_command=profile.lint_command,
            typecheck_command=profile.typecheck_command,
            framework=framework,
        )
        is_agent = spec.kind is EquipmentKind.AGENT
        item = EquipmentItem(
            kind=spec.kind,
            name=spec.name,
            path=spec.rel_path,
            source=EquipmentSource.GENERATED,
            capabilities=spec.capabilities,
            grounded_in=grounding,
            subagent_type=spec.name if is_agent else None,
            version=_INITIAL_VERSION,
            origin_hash=content_hash(content),
        )
        out.append((item, spec.rel_path, content))
    return tuple(out)
