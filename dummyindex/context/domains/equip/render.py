"""Fill the shipped ``*.md.tmpl`` templates with project values.

Templates live in the equip skill package (``dummyindex/skills/equip/templates/``)
and are located package-relative so rendering works pre-install (tests) and
post-install (the copied package) alike. Each template carries three slots:

- ``{{stack}}`` — the dominant stack label (e.g. ``python``).
- ``{{conventions}}`` — a newline list of the repo's convention docs under
  ``.context/conventions/`` (so the tool's prompt cites the real spine).
- ``{{context_root}}`` — the relative path to ``.context/`` (always
  ``.context`` today; a slot so a future non-root context dir stays correct).

Rendering also stamps :data:`GENERATED_SENTINEL` so a later run recognises its
own output for the never-clobber check (see :mod:`.safety`).
"""
from __future__ import annotations

from pathlib import Path

from .errors import TemplateError
from .models import GENERATED_SENTINEL

_TEMPLATES_DIR = Path(__file__).parents[3] / "skills" / "equip" / "templates"

IMPLEMENTER_TEMPLATE = "implementer-agent.md.tmpl"
TESTER_TEMPLATE = "tester-agent.md.tmpl"
REVIEWER_TEMPLATE = "reviewer-agent.md.tmpl"
VERIFY_TEMPLATE = "verify-skill.md.tmpl"

_CONVENTIONS_REL = Path("conventions")


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
    conventions: tuple[str, ...],
    context_root: str = ".context",
) -> str:
    """Return the template's text with every slot filled.

    Raises :class:`TemplateError` if the named template is missing from the
    shipped package (an incomplete build) — equip refuses rather than writing a
    half-rendered tool.
    """
    text = _load_template(template_name)
    conventions_block = _format_conventions(conventions, context_root)
    rendered = (
        text.replace("{{stack}}", stack)
        .replace("{{conventions}}", conventions_block)
        .replace("{{context_root}}", context_root)
    )
    if GENERATED_SENTINEL not in rendered:
        # Defensive: a template that lost its in-body sentinel. Re-insert it
        # *after* the YAML frontmatter so the frontmatter stays at byte 0 —
        # Claude Code discovers agents/skills only when `---` leads the file.
        rendered = _insert_sentinel_after_frontmatter(rendered)
    return rendered


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
