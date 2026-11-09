"""Render a catalog decision into ``(item, rel_path, content)`` triples.

:func:`render_generated_set` is the single render path for the whole lifecycle:
apply writes from it, refresh rebuilds its fresh-render map from it, and reset
picks the matching artifact out of it. Each artifact is stamped with ``version``
(``1.0.0``), ``origin_hash`` (sha256 of the rendered bytes) and, for agents, its
``subagent_type``.
"""

from __future__ import annotations

import hashlib
import re

from ..enums import EquipmentKind, EquipmentSource
from ..lifecycle.hashing import content_hash
from ..models import EquipmentItem, GenerateSpec, StackProfile
from .render import _load_template, render_template
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

    The framework slot is the first detected framework or ``None``. ``proj``
    fills the reviewer/verify ``{{proj}}`` slot so each frontmatter ``name:``
    matches its filename and ``subagent_type``. ``grounded_in`` and canary
    ``invariants`` are manifest metadata only, never rendered, so
    ``origin_hash`` (sha256 of ``content``) is unaffected.
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
            format_command=(
                profile.format_command.replace(
                    '"$CLAUDE_FILE_PATHS"', "<changed-paths>"
                )
                if profile.format_command
                else None
            ),
            framework=framework,
        )
        # Tool permissions belong to native adapters, not a shared mandate.
        content = re.sub(r"(?m)^allowed-tools:[^\n]*\n", "", content, count=1)
        is_agent = spec.kind is EquipmentKind.AGENT
        package_digest = hashlib.sha256(
            _load_template(spec.template).encode("utf-8")
        ).hexdigest()
        commands = {
            name: getattr(profile, name)
            for name in (
                "test_command",
                "lint_command",
                "typecheck_command",
                "format_command",
            )
        }
        if commands["format_command"]:
            commands["format_command"] = commands["format_command"].replace(
                '"$CLAUDE_FILE_PATHS"', "<changed-paths>"
            )
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
            invariants=invariants_for(spec.capabilities, spec.dimension),
            dimension=spec.dimension,
            subagent_type=spec.name if is_agent else None,
            version=_INITIAL_VERSION,
            origin_hash=content_hash(content),
            capability_id="dummyindex/" + spec.template.removesuffix(".md.tmpl"),
            package_version=package_digest[:12],
            package_source="dummyindex/skills/equip/templates/" + spec.template,
            package_sha256=package_digest,
            required_tools=tuple(
                dict.fromkeys(
                    tool
                    for tool in (
                        profile.test_runner,
                        profile.linter,
                        profile.type_checker,
                        profile.formatter,
                    )
                    if tool
                )
            ),
            triggers=spec.capabilities,
            project_binding=dict(
                project=proj,
                stack=profile.label,
                frameworks=list(profile.frameworks),
                conventions=list(conventions),
                commands=commands,
            ),
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
