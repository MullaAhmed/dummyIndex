"""Grounding sidecar: bounded, deterministic digest; template bodies stay feature-independent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.domains.equip.generate.grounding import (
    GROUNDING_HEADER,
    focus_query,
    grounding_path,
    render_grounding,
)
from dummyindex.context.domains.equip.generate.render import (
    _TEMPLATES_DIR,
    list_convention_docs,
    render_template,
)

_CONCERNS = (
    "# Concerns\n\n- **First risk.** Detail one (see code).\n- Second risk, plain.\n"
)


def _feature(
    context: Path, feature_id: str, *, summary: str, members: int, concerns: str
) -> None:
    feat = context / "features" / feature_id
    feat.mkdir(parents=True, exist_ok=True)
    (feat / "feature.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "feature_id": feature_id,
                "summary": summary,
                "files": [f"src/{feature_id}/a.py", f"src/{feature_id}/b.py"],
            }
        ),
        encoding="utf-8",
    )
    (feat / "concerns.md").write_bytes(concerns.encode("utf-8"))


def _context(root: Path, count: int, *, summary=None, concerns=_CONCERNS) -> Path:
    context = root / ".context"
    context.mkdir(parents=True)
    (context / "PROJECT.md").write_text(
        "# Demo\n\nA small demo project for grounding tests.\n\n## Next\n\nMore.\n",
        encoding="utf-8",
    )
    entries = []
    for i in range(count):
        fid = f"feat-{i:02d}"
        text = summary if summary is not None else f"Feature {i} summary."
        _feature(context, fid, summary=text, members=count - i, concerns=concerns)
        entries.append({"feature_id": fid, "summary": text, "member_count": count - i})
    index = {"features": entries}
    (context / "features").mkdir(exist_ok=True)
    (context / "features" / "INDEX.json").write_text(
        json.dumps(index), encoding="utf-8"
    )
    return context


@pytest.mark.unit
def test_sidecar_names_each_feature_and_a_concerns_citation(tmp_path: Path) -> None:
    context = _context(tmp_path, 3)

    out = render_grounding(context, capability="implement")

    assert out.startswith(GROUNDING_HEADER + "\n")
    for fid in ("feat-00", "feat-01", "feat-02"):
        assert f"`{fid}`" in out
    assert "`.context/features/feat-00/concerns.md:3`" in out
    assert "Demo" not in out  # heading is skipped, paragraph used
    assert "A small demo project" in out


@pytest.mark.unit
def test_sidecar_within_budget_cut_on_line_boundary(tmp_path: Path) -> None:
    non_ascii = (
        "résumé — 数据 " * 100
    )  # multibyte; five long lines push past 6000 bytes
    context = _context(tmp_path, 50, summary=non_ascii)

    out = render_grounding(context, capability="implement")
    full = render_grounding(context, capability="implement", budget=10**9)

    assert len(out.encode("utf-8")) <= 6000
    assert len(full.encode("utf-8")) > 6000
    assert out.endswith("\n")
    assert full.startswith(out)  # a strict prefix, so the cut is at a line end


@pytest.mark.unit
def test_two_temp_copies_are_byte_identical(tmp_path: Path) -> None:
    first = _context(tmp_path / "a", 4)
    second = _context(tmp_path / "b", 4)

    assert render_grounding(first, capability="docs") == render_grounding(
        second, capability="docs"
    )
    assert (
        render_grounding(first, capability="implement").encode()
        == render_grounding(second, capability="implement").encode()
    )


@pytest.mark.unit
def test_crlf_input_gives_the_same_bytes_as_lf(tmp_path: Path) -> None:
    lf = _context(tmp_path / "lf", 3, concerns=_CONCERNS)
    crlf = _context(tmp_path / "crlf", 3, concerns=_CONCERNS.replace("\n", "\r\n"))
    (crlf / "PROJECT.md").write_bytes(
        (lf / "PROJECT.md").read_bytes().replace(b"\n", b"\r\n")
    )

    assert (
        render_grounding(lf, capability="implement").encode()
        == render_grounding(crlf, capability="implement").encode()
    )


@pytest.mark.unit
def test_empty_context_gives_header_only(tmp_path: Path) -> None:
    context = tmp_path / ".context"
    context.mkdir()

    assert render_grounding(context, capability="database") == GROUNDING_HEADER + "\n"


@pytest.mark.unit
def test_body_bytes_do_not_change_when_feature_docs_change(tmp_path: Path) -> None:
    context = _context(tmp_path, 3)
    names = [
        p.name
        for p in sorted(_TEMPLATES_DIR.glob("*.md.tmpl"))
        if p.name != "sourced-overlay.md.tmpl"
    ]
    conventions = list_convention_docs(context)

    def bodies() -> dict[str, str]:
        return {
            n: render_template(n, stack="python", proj="demo", conventions=conventions)
            for n in names
        }

    before_body = bodies()
    before_sidecar = render_grounding(context, capability="implement")
    (context / "features" / "feat-00" / "concerns.md").write_text(
        "- A brand new risk.\n", encoding="utf-8"
    )

    assert bodies() == before_body
    assert render_grounding(context, capability="implement") != before_sidecar


@pytest.mark.unit
def test_one_liner_skips_emphasis_only_metadata_paragraph(tmp_path: Path) -> None:
    context = tmp_path / ".context"
    context.mkdir()
    (context / "PROJECT.md").write_bytes(
        b"# Demo\n\n_Version 0.37.0_\n\nThe real project description.\n"
    )

    out = render_grounding(context, capability="implement")

    assert "The real project description." in out
    assert "_Version" not in out


@pytest.mark.unit
def test_query_miss_falls_back_to_member_count_top_five(tmp_path: Path) -> None:
    context = _context(tmp_path, 7)  # member_count descends with the id

    out = render_grounding(context, capability="database")  # query has no hit here

    for fid in ("feat-00", "feat-01", "feat-02", "feat-03", "feat-04"):
        assert f"`{fid}`" in out
    assert "`feat-05`" not in out
    assert "`feat-06`" not in out


@pytest.mark.unit
@pytest.mark.parametrize("capability", ["implement", "docs"])
def test_duplicate_index_ids_yield_five_distinct_focus_lines(
    tmp_path: Path, capability: str
) -> None:
    context = _context(tmp_path, 7, summary="documentation readme guides")
    entries = [
        {"feature_id": fid, "summary": "documentation readme guides", "member_count": n}
        for fid, n in [
            ("feat-00", 7),
            ("feat-00", 7),
            ("feat-01", 6),
            ("feat-01", 6),
            ("feat-02", 5),
            ("feat-03", 4),
            ("feat-04", 3),
            ("feat-05", 2),
            ("feat-06", 1),
        ]
    ]
    (context / "features" / "INDEX.json").write_text(
        json.dumps({"features": entries}), encoding="utf-8"
    )

    out = render_grounding(context, capability=capability)

    focus = [line for line in out.split("\n") if line.startswith("- `feat-")]
    ids = [line.split("`")[1] for line in focus]
    assert len(ids) == 5
    assert len(set(ids)) == 5


@pytest.mark.unit
def test_grounding_path_and_focus_fallback() -> None:
    assert (
        grounding_path("demo-implementer")
        == ".context/equipment/grounding/demo-implementer.md"
    )
    assert focus_query("no-such-capability") == "architecture overview"


@pytest.mark.unit
def test_all_templates_render_with_and_without_framework() -> None:
    names = sorted(p.name for p in _TEMPLATES_DIR.glob("*.md.tmpl"))
    names = [n for n in names if n != "sourced-overlay.md.tmpl"]
    assert len(names) == 17

    for name in names:
        for framework in (None, "fastapi"):
            body = render_template(
                name,
                stack="python",
                proj="demo",
                conventions=(".context/conventions/naming.md",),
                framework=framework,
                focus_query="api endpoints routes handlers",
            )
            assert "{{" not in body, name
            assert "the project's stack" not in body, name
            assert 'dummyindex context query "api endpoints routes handlers"' in body, (
                name
            )
            assert "/equipment/grounding/" in body, name
            # reviewer and verify never named the framework; only the clause users show.
            if "{{framework_clause}}" not in (_TEMPLATES_DIR / name).read_text(
                encoding="utf-8"
            ):
                continue
            if framework:
                assert "(framework: fastapi)" in body, name
            else:
                assert "(framework:" not in body, name
