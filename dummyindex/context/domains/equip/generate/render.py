"""Fill the shipped ``*.md.tmpl`` templates with project values.

Templates resolve package-relative (``dummyindex/skills/equip/templates/``) so
rendering works pre- and post-install. Slots: ``{{stack}}``, ``{{proj}}``,
``{{conventions}}``, ``{{context_root}}``, the four ``{{*_command}}`` slots and
``{{framework}}``. Rendering stamps :data:`GENERATED_SENTINEL` so a later run
recognises its own output for the never-clobber check (see :mod:`.safety`).
"""

from __future__ import annotations

import re
from pathlib import Path

from dummyindex import skills as _skills_pkg

from ..errors import TemplateError
from ..models import GENERATED_SENTINEL

# Anchored on the skills package, not a parents[N] chain, so moving this
# module can't silently break template resolution.
_TEMPLATES_DIR = Path(_skills_pkg.__file__).resolve().parent / "equip" / "templates"

IMPLEMENTER_TEMPLATE = "implementer-agent.md.tmpl"
TESTER_TEMPLATE = "tester-agent.md.tmpl"
REVIEWER_TEMPLATE = "reviewer-agent.md.tmpl"
VERIFY_TEMPLATE = "verify-skill.md.tmpl"

_CONVENTIONS_REL = Path("conventions")

# Fallbacks for unfilled toolchain slots, so a rendered tool never carries a
# dangling ``{{...}}`` and the prose stays readable on a fresh/untooled repo.
_NO_COMMAND = "(no command detected — discover the project's own and run it)"
_NO_FRAMEWORK = "the project's stack"


def list_convention_docs(context_dir: Path) -> tuple[str, ...]:
    """Repo-context-relative paths of every ``conventions/*.md`` doc.

    Returns paths like ``.context/conventions/naming.md`` so the rendered
    grounding slot cites them exactly as a reader would open them. Empty when
    the conventions dir is absent (a fresh repo before Phase 1.5).
    """
    conventions_dir = context_dir / _CONVENTIONS_REL
    if not conventions_dir.is_dir():
        return ()
    root_name = context_dir.name  # ".context"
    docs = sorted(
        f"{root_name}/conventions/{path.name}"
        for path in conventions_dir.glob("*.md")
        if path.is_file()
    )
    return tuple(docs)


def render_template(
    template_name: str,
    *,
    stack: str,
    proj: str,
    conventions: tuple[str, ...],
    context_root: str = ".context",
    test_command: str | None = None,
    lint_command: str | None = None,
    typecheck_command: str | None = None,
    format_command: str | None = None,
    framework: str | None = None,
) -> str:
    """Return the template's text with every slot filled.

    ``stack`` drives the implementer/tester identifiers and all prose; ``proj``
    the reviewer/verify ``name:`` + H1, so they match the filename and
    ``subagent_type``. ``None`` toolchain slots get a readable placeholder (no
    dangling ``{{...}}``). Raises :class:`TemplateError` when the template is
    missing or unreadable, rather than write a half-rendered tool.
    """
    text = _load_template(template_name)
    conventions_block = _format_conventions(conventions, context_root)
    rendered = (
        text.replace("{{stack}}", stack)
        .replace("{{proj}}", proj)
        .replace("{{conventions}}", conventions_block)
        .replace("{{context_root}}", context_root)
        .replace("{{test_command}}", test_command or _NO_COMMAND)
        .replace("{{lint_command}}", lint_command or _NO_COMMAND)
        .replace("{{typecheck_command}}", typecheck_command or _NO_COMMAND)
        .replace("{{format_command}}", format_command or _NO_COMMAND)
        .replace("{{framework}}", framework or _NO_FRAMEWORK)
    )
    if GENERATED_SENTINEL not in rendered:
        # Defensive: a template that lost its in-body sentinel. Re-insert it
        # *after* the YAML frontmatter so the frontmatter stays at byte 0 —
        # Claude Code discovers agents/skills only when `---` leads the file.
        rendered = _insert_sentinel_after_frontmatter(rendered)
    return rendered


def set_frontmatter_version(text: str, version: str) -> str:
    """Sync the version line inside a leading YAML frontmatter block.

    The manifest is the version source of truth (spec §7). Agent templates keep
    a top-level ``version``; Agent Skills nest it at ``metadata.version``. Only
    the first version line inside the leading ``---`` block is rewritten, never
    one in the body. Text without frontmatter or a version line is unchanged.
    """
    if not text.startswith("---\n"):
        return text
    close = text.find("\n---", 4)
    if close == -1:
        return text
    head, tail = text[: close + 1], text[close + 1 :]
    new_head, replaced = re.subn(
        r"(?m)^(?P<indent>[ \t]*)version:[^\n]*$",
        lambda match: f"{match.group('indent')}version: {version}",
        head,
        count=1,
    )
    return (new_head + tail) if replaced else text


def _insert_sentinel_after_frontmatter(text: str) -> str:
    """Place the sentinel just after a leading ``---``-delimited YAML block.

    Falls back to prepending only when there is no frontmatter to protect.
    """
    if text.startswith("---\n"):
        close = text.find("\n---", 4)
        if close != -1:
            end = text.find("\n", close + 1)
            if end != -1:
                head, tail = text[: end + 1], text[end + 1 :]
                return f"{head}{GENERATED_SENTINEL}\n{tail}"
    return f"{GENERATED_SENTINEL}\n{text}"


def _load_template(template_name: str) -> str:
    path = _TEMPLATES_DIR / template_name
    if not path.is_file():
        raise TemplateError(f"equip template not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive
        raise TemplateError(f"could not read equip template {path}: {exc}") from exc


def _format_conventions(conventions: tuple[str, ...], context_root: str) -> str:
    """Render the convention docs as a markdown bullet list.

    Falls back to a single pointer at the context root when no convention docs
    were discovered, so the slot is never empty and the prompt always grounds.
    """
    if not conventions:
        return f"- `{context_root}/HOW_TO_USE.md` (no convention docs yet)"
    return "\n".join(f"- `{conv}`" for conv in conventions)
