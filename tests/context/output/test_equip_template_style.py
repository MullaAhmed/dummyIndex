"""Equip templates render to STE-clean prose (spec C6).

Every shipped ``*.md.tmpl`` renders through the equip renderer and must pass
the strict STE lint. A new template joins the test through the glob.
"""

from __future__ import annotations

import pytest

from dummyindex.context.domains.docbudget.style import lint_text
from dummyindex.context.domains.equip.generate.render import (
    _TEMPLATES_DIR,
    render_template,
)

_TEMPLATE_NAMES = sorted(path.name for path in _TEMPLATES_DIR.glob("*.md.tmpl"))


def test_templates_directory_is_not_empty() -> None:
    assert len(_TEMPLATE_NAMES) == 18


@pytest.mark.parametrize("template_name", _TEMPLATE_NAMES)
def test_rendered_template_has_no_strict_style_violations(template_name: str) -> None:
    rendered = render_template(
        template_name,
        stack="python",
        proj="demo",
        conventions=(".context/conventions/naming.md",),
        context_root=".context",
        test_command="uv run pytest -q",
        lint_command="uvx ruff check",
        typecheck_command="uv run mypy .",
        format_command="uvx ruff format",
        framework="fastapi",
    )
    violations = [v for v in lint_text(rendered) if v.severity == "strict"]
    assert violations == [], f"{template_name}: {violations}"
