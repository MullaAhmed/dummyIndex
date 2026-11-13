"""``equip install`` write-back of the declared plugin (``_write_back_wired``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.cli.equip.install import _write_back_wired
from dummyindex.context.domains.config import default_config, write_config

_TOML = """\
schema_version = 1

[dummyindex]
min_version = "1.0.0"

[[plugins]]
id = "a@b"
version = ">=1.0.0"
"""


def _project(tmp_path: Path) -> tuple[Path, Path]:
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True)
    write_config(ctx, default_config())
    return tmp_path, ctx


@pytest.mark.unit
def test_write_back_updates_toml_and_leaves_json_wired(tmp_path: Path) -> None:
    project, ctx = _project(tmp_path)
    (ctx / "config.toml").write_text(_TOML, encoding="utf-8")
    json_before = (ctx / "config.json").read_text(encoding="utf-8")

    _write_back_wired(project, "x@m", "1.2.0")

    toml_text = (ctx / "config.toml").read_text(encoding="utf-8")
    assert 'id = "x@m"' in toml_text
    assert 'version = ">=1.2.0"' in toml_text
    assert (ctx / "config.json").read_text(encoding="utf-8") == json_before


@pytest.mark.unit
def test_write_back_without_toml_updates_json_wired(tmp_path: Path) -> None:
    project, ctx = _project(tmp_path)

    _write_back_wired(project, "x@m", "1.2.0")

    assert not (ctx / "config.toml").exists()
    assert '"target": "x@m"' in (ctx / "config.json").read_text(encoding="utf-8")
