"""Round-trip, validation and line-level editing of ``.context/config.toml``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dummyindex.context.domains.requirements import (
    PluginRequirement,
    Requirements,
    RequirementsError,
    SkillRequirement,
    read_requirements,
    render_requirements,
    set_min_version_line,
    write_requirements,
)

SAMPLE = """\
# Required setup for every dev on this repo. Extras are allowed.
schema_version = 1
team_note = "keep me"

[dummyindex]
# floor set by the repo owner
min_version = "0.39.0"   # bump with releases

[[plugins]]
id = "superpowers@claude-plugins-official"
version = ">=7.0.0"       # optional
flavour = "extra-key"

[[skills]]
name = "dummyindex-plan"
from = "dummyindex"

[equipment]
require_native_adapters = true
"""


def _write(path, text: str, *, newline: str = "\n") -> None:
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


@pytest.mark.unit
def test_round_trip_is_stable(tmp_path):
    path = tmp_path / "config.toml"
    _write(path, SAMPLE)
    req = read_requirements(path)
    assert req is not None
    rendered = render_requirements(req)
    again = render_requirements(_parse_text(rendered, tmp_path))
    assert _parse_text(rendered, tmp_path) == req
    assert again == rendered


@pytest.mark.unit
def test_unknown_keys_are_kept_on_rewrite(tmp_path):
    path = tmp_path / "config.toml"
    _write(path, SAMPLE)
    req = read_requirements(path)
    assert req is not None
    out = render_requirements(req)
    assert 'team_note = "keep me"' in out
    assert 'flavour = "extra-key"' in out
    assert req.extra == (("team_note", "keep me"),)
    assert req.plugins[0].extra == (("flavour", "extra-key"),)


@pytest.mark.unit
def test_min_version_line_edit_keeps_comments(tmp_path):
    path = tmp_path / "config.toml"
    _write(path, SAMPLE)
    req = read_requirements(path)
    assert req is not None
    write_requirements(path, _replace(req, min_version="0.40.0"))
    expected = SAMPLE.replace(
        'min_version = "0.39.0"   # bump', 'min_version = "0.40.0"   # bump'
    )
    assert path.read_text(encoding="utf-8") == expected


@pytest.mark.unit
def test_set_min_version_line_inserts_and_removes():
    text = "[dummyindex]\n# c\n[equipment]\nrequire_native_adapters = false\n"
    inserted = set_min_version_line(text, "1.2.3")
    assert (
        inserted
        == '[dummyindex]\nmin_version = "1.2.3"\n# c\n[equipment]\nrequire_native_adapters = false\n'
    )
    assert set_min_version_line(inserted, None) == text


@pytest.mark.unit
def test_crlf_and_bom_parse_and_keep_bytes(tmp_path):
    path = tmp_path / "config.toml"
    body = SAMPLE.replace("\n", "\r\n")
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    req = read_requirements(path)
    assert req is not None and req.min_version == "0.39.0"
    write_requirements(path, _replace(req, min_version="0.41.0"))
    data = path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert b'min_version = "0.41.0"   # bump with releases\r\n' in data
    assert data.count(b"\r\n") == body.count("\r\n")


@pytest.mark.unit
def test_empty_file_gives_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    assert read_requirements(path) == Requirements()


@pytest.mark.unit
def test_missing_file_gives_none(tmp_path):
    assert read_requirements(tmp_path / "absent.toml") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad",
    [
        "schema_version = 2\n",
        '[[plugins]]\nid = "a@b"\n[[plugins]]\nid = "a@b"\n',
        '[[skills]]\nname = "x"\nfrom = "github:someone"\n',
        '[[plugins]]\nid = "a@b"\nversion = "~=1.0"\n',
        "this is not = = toml\n",
    ],
)
def test_invalid_files_raise(tmp_path, bad):
    path = tmp_path / "config.toml"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(RequirementsError):
        read_requirements(path)


@pytest.mark.unit
def test_tomli_fallback_is_used_when_tomllib_is_blocked(tmp_path, monkeypatch):
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10: tomli is the real parser
        import tomli as tomllib

    path = tmp_path / "config.toml"
    _write(path, SAMPLE)
    monkeypatch.setitem(sys.modules, "tomllib", None)
    # Stand in for tomli with the stdlib parser, so the fallback branch runs.
    monkeypatch.setitem(sys.modules, "tomli", tomllib)
    req = read_requirements(path)
    assert req is not None and req.min_version == "0.39.0"
    assert req.plugins[0].id == "superpowers@claude-plugins-official"


@pytest.mark.unit
def test_write_appends_and_deletes_blocks_keeping_comments(tmp_path):
    path = tmp_path / "config.toml"
    _write(path, SAMPLE)
    req = read_requirements(path)
    assert req is not None
    new_plugin = PluginRequirement(id="other@market", version=">=1.0.0")
    new_req = _replace(
        req,
        plugins=(new_plugin,),
        skills=(SkillRequirement(name="dummyindex-gc"),) + req.skills,
    )
    write_requirements(path, new_req)
    text = path.read_text(encoding="utf-8")
    assert "# floor set by the repo owner" in text
    assert 'team_note = "keep me"' in text
    assert "superpowers@claude-plugins-official" not in text
    assert 'id = "other@market"' in text
    back = read_requirements(path)
    assert back is not None
    assert back.plugins == new_req.plugins
    assert {s.name for s in back.skills} == {"dummyindex-gc", "dummyindex-plan"}


@pytest.mark.unit
def test_write_creates_missing_file_in_full(tmp_path):
    path = tmp_path / ".context" / "config.toml"
    req = Requirements(min_version="0.39.0")
    write_requirements(path, req)
    assert path.read_text(encoding="utf-8") == render_requirements(req)
    assert read_requirements(path) == req


def _parse_text(text: str, tmp_path) -> Requirements:
    path = tmp_path / "parse-check.toml"
    path.write_text(text, encoding="utf-8")
    parsed = read_requirements(path)
    assert parsed is not None
    return parsed


def _replace(req: Requirements, **changes) -> Requirements:
    from dataclasses import replace

    return replace(req, **changes)


@pytest.mark.unit
def test_delete_keeps_comment_above_next_block(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[dummyindex]\n\n[[plugins]]\nid = "a@x"\n\n# about b\n[[plugins]]\nid = "b@x"\n',
        encoding="utf-8",
    )
    req = read_requirements(path)
    assert req is not None
    write_requirements(path, _replace(req, plugins=(PluginRequirement(id="b@x"),)))
    text = path.read_text(encoding="utf-8")
    assert "# about b" in text
    assert 'id = "a@x"' not in text
    assert 'id = "b@x"' in text


@pytest.mark.unit
def test_write_refuses_when_edit_does_not_reach_requested_state(tmp_path, monkeypatch):
    from dummyindex.context.domains.requirements import toml_io

    path = tmp_path / "config.toml"
    _write(path, SAMPLE)
    before = path.read_bytes()
    req = read_requirements(path)
    assert req is not None
    monkeypatch.setattr(toml_io, "_apply_changes", lambda text, cur, new: text)
    with pytest.raises(RequirementsError):
        write_requirements(path, _replace(req, min_version="9.9.9"))
    assert path.read_bytes() == before


@pytest.mark.unit
@pytest.mark.parametrize("content", [b"", b"  \n\n", b"\xef\xbb\xbf"])
def test_empty_or_blank_existing_file_gets_full_render(tmp_path, content):
    path = tmp_path / "config.toml"
    path.write_bytes(content)
    req = Requirements(min_version="0.39.0")
    write_requirements(path, req)
    assert path.read_text(encoding="utf-8") == render_requirements(req)


@pytest.mark.unit
def test_bom_constant_is_escaped_in_source():
    from dummyindex.context.domains.requirements import toml_io

    source = Path(toml_io.__file__).read_bytes()
    assert b"\xef\xbb\xbf" not in source
    assert toml_io._BOM == "\ufeff"


@pytest.mark.unit
def test_directory_or_unreadable_path_raises_requirements_error(tmp_path):
    path = tmp_path / "config.toml"
    path.mkdir()
    with pytest.raises(RequirementsError):
        read_requirements(path)
    with pytest.raises(RequirementsError):
        write_requirements(path, Requirements())
