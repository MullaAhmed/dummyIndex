"""Pure compose + item builders for sourced (adopted upstream) specialists.

A sourced body is our repo overlay followed by the upstream skill text verbatim.
Nothing here touches the filesystem or the network.
"""

from __future__ import annotations

import dataclasses
import hashlib

from ..errors import TemplateError
from ..lifecycle.hashing import content_hash
from ..models import EquipmentItem, StackProfile
from .render import render_template

SOURCED_OVERLAY_TEMPLATE = "sourced-overlay.md.tmpl"
OVERLAY_INVARIANTS = (
    "## Ground yourself first (mandatory, before any edit)",
    "Stay inside the planned scope.",
)


def render_overlay(
    *,
    profile: StackProfile,
    proj: str,
    conventions: tuple[str, ...],
    context_root: str = ".context",
) -> str:
    """Render the sourced overlay template with the repo's stack and commands."""
    # Mirror plan.py: the changed-paths placeholder is substituted for the hook var.
    format_command = (
        profile.format_command.replace('"$CLAUDE_FILE_PATHS"', "<changed-paths>")
        if profile.format_command
        else None
    )
    return render_template(
        SOURCED_OVERLAY_TEMPLATE,
        stack=profile.label,
        proj=proj,
        conventions=conventions,
        context_root=context_root,
        test_command=profile.test_command,
        lint_command=profile.lint_command,
        typecheck_command=profile.typecheck_command,
        format_command=format_command,
        framework=profile.frameworks[0] if profile.frameworks else None,
    )


def compose_body(
    *,
    overlay: str,
    name: str,
    description: str,
    repo: str,
    skill: str,
    ref: str,
    body: str,
) -> str:
    """Splice the upstream body under the overlay; the body is appended last so its own ``{{...}}`` text stays literal."""
    if "{{upstream}}" not in overlay:
        raise TemplateError("sourced overlay lacks {{upstream}}")
    # Drop the tail after the slot: the template's trailing newline.
    head = overlay.rsplit("{{upstream}}", 1)[0]
    head = head.replace("{{name}}", name).replace("{{description}}", description)
    return f"{head}## Upstream skill: {repo}/{skill}@{ref[:12]}\n\n{body}"


def sourced_description(capability: str, stack: str, repo: str, skill: str) -> str:
    """One-line frontmatter description; contains no colon so the YAML stays valid."""
    return (
        f"Sourced {capability} specialist for this {stack} repo, adapted from "
        f"upstream skill {repo}/{skill} and grounded in the .context/ spine."
    )


def sourced_item(
    template_item: EquipmentItem,
    *,
    repo: str,
    skill: str,
    ref: str,
    path: str,
    upstream_text: str,
    marketplace: str,
    content: str,
) -> EquipmentItem:
    """Return the template item with upstream origin fields set; ``upstream_text`` must be LF-normalized."""
    # package_sha256 is a bare hexdigest, matching plan.py; origin_hash keeps the sha256: prefix.
    return dataclasses.replace(
        template_item,
        origin_repo=repo,
        origin_ref=ref,
        marketplace=marketplace,
        capability_id=f"{repo}/{skill}",
        package_source=path,
        package_version=ref[:12],
        package_sha256=hashlib.sha256(upstream_text.encode("utf-8")).hexdigest(),
        invariants=OVERLAY_INVARIANTS,
        origin_hash=content_hash(content),
    )
