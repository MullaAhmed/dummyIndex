"""Wiring marketplaces + enabledPlugins into .claude/settings.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.context.claude_plugins import (
    add_marketplace,
    disable_plugin,
    enable_plugin,
    remove_marketplace,
)
from dummyindex.context.claude_settings import MalformedSettingsError

pytestmark = pytest.mark.unit


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_add_marketplace_then_enable_plugin(tmp_path: Path) -> None:
    s = tmp_path / "settings.json"
    assert (
        add_marketplace(s, name="community", repo="anthropics/claude-plugins-community")
        is True
    )
    assert enable_plugin(s, plugin="rag-search", marketplace="community") is True
    data = _read(s)
    assert (
        data["extraKnownMarketplaces"]["community"]["source"]["repo"]
        == "anthropics/claude-plugins-community"
    )
    assert data["enabledPlugins"]["rag-search@community"] is True


def test_add_marketplace_with_ref_pins_exact_source(tmp_path: Path) -> None:
    s = tmp_path / "settings.json"
    ref = "0d95a81d35a9f2d123a5e9430d1cfc43d55f1bb0"
    add_marketplace(s, name="caveman", repo="JuliusBrussee/caveman", ref=ref)
    assert _read(s)["extraKnownMarketplaces"]["caveman"] == {
        "source": {
            "source": "github",
            "repo": "JuliusBrussee/caveman",
            "ref": ref,
        }
    }


def test_add_marketplace_is_byte_idempotent(tmp_path: Path) -> None:
    s = tmp_path / "settings.json"
    add_marketplace(s, name="community", repo="anthropics/claude-plugins-community")
    before = s.read_bytes()
    assert (
        add_marketplace(s, name="community", repo="anthropics/claude-plugins-community")
        is False
    )
    assert s.read_bytes() == before


def test_preserves_unrelated_keys(tmp_path: Path) -> None:
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}))
    enable_plugin(s, plugin="p", marketplace="m")
    assert _read(s)["permissions"]["allow"] == ["Bash"]


def test_refuses_malformed_settings(tmp_path: Path) -> None:
    s = tmp_path / "settings.json"
    s.write_text("{not json")
    with pytest.raises(MalformedSettingsError):
        enable_plugin(s, plugin="p", marketplace="m")


def test_remove_and_disable(tmp_path: Path) -> None:
    s = tmp_path / "settings.json"
    add_marketplace(s, name="m", repo="o/r")
    enable_plugin(s, plugin="p", marketplace="m")
    assert disable_plugin(s, plugin="p", marketplace="m") is True
    assert remove_marketplace(s, name="m") is True
    data = _read(s)
    assert "p@m" not in data.get("enabledPlugins", {})
    assert "m" not in data.get("extraKnownMarketplaces", {})


def test_remove_absent_is_false(tmp_path: Path) -> None:
    s = tmp_path / "settings.json"
    assert remove_marketplace(s, name="nope") is False
    assert disable_plugin(s, plugin="p", marketplace="m") is False


# ----- read side: marketplaces Claude Code already knows (audit C4-P0) -------


def test_list_marketplaces_reads_declarations(tmp_path: Path) -> None:
    from dummyindex.context.claude_plugins import DeclaredMarketplace, list_marketplaces

    s = tmp_path / "settings.json"
    add_marketplace(s, name="community", repo="anthropics/claude-plugins-community")
    declared = list_marketplaces(s)
    assert declared == (
        DeclaredMarketplace(
            name="community", repo="anthropics/claude-plugins-community"
        ),
    )


def test_list_marketplaces_tolerates_absent_and_malformed(tmp_path: Path) -> None:
    from dummyindex.context.claude_plugins import list_marketplaces

    assert list_marketplaces(tmp_path / "nope.json") == ()
    bad = tmp_path / "settings.json"
    bad.write_text("{not json", encoding="utf-8")
    assert list_marketplaces(bad) == ()  # read side never raises


def test_list_marketplaces_skips_repo_less_entries(tmp_path: Path) -> None:
    from dummyindex.context.claude_plugins import list_marketplaces

    s = tmp_path / "settings.json"
    s.write_text(
        json.dumps(
            {
                "extraKnownMarketplaces": {
                    "ok": {"source": {"source": "github", "repo": "o/r"}},
                    "no-repo": {"source": {"source": "github"}},
                    "weird": "not-an-object",
                }
            }
        ),
        encoding="utf-8",
    )
    assert [d.name for d in list_marketplaces(s)] == ["ok"]


def test_list_known_marketplaces_reads_native_registry(tmp_path: Path) -> None:
    from dummyindex.context.claude_plugins import list_known_marketplaces

    known = tmp_path / ".claude" / "plugins" / "known_marketplaces.json"
    known.parent.mkdir(parents=True)
    known.write_text(
        json.dumps(
            {
                "mkt": {
                    "source": {"source": "github", "repo": "o/r"},
                    "installLocation": "/somewhere/mkt",
                    "lastUpdated": "2026-06-12T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    declared = list_known_marketplaces(tmp_path)
    assert len(declared) == 1
    assert declared[0].repo == "o/r"
    assert declared[0].install_location == "/somewhere/mkt"
    assert declared[0].last_updated == "2026-06-12T00:00:00Z"


def test_list_known_marketplaces_absent_is_empty(tmp_path: Path) -> None:
    from dummyindex.context.claude_plugins import list_known_marketplaces

    assert list_known_marketplaces(tmp_path) == ()
