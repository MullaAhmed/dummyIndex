"""Tests for `dummyindex context preflight` — read-only setup inventory."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context import bootstrap_claude_md
from dummyindex.context.domains.preflight import (
    build_preflight_report,
    render_preflight_md,
)
from dummyindex.context.hooks import install as install_hooks


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True, capture_output=True)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ----- inventory ------------------------------------------------------------


@pytest.mark.unit
def test_empty_repo_reports_safe_defaults(tmp_path: Path) -> None:
    report = build_preflight_report(tmp_path)
    assert report.rule_files == ()
    assert report.project_agents == ()
    assert report.claude_md_exists is False
    assert report.claude_md_has_managed_block is False
    assert report.settings.exists is False
    assert report.settings.parseable is True
    assert report.settings.user_hook_events == ()
    assert report.is_git_repo is False
    assert report.git_clean is None


@pytest.mark.unit
def test_inventories_rules_and_agents(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "rules" / "python" / "style.md", "# style")
    _write(tmp_path / ".claude" / "rules" / "testing.md", "# testing")
    _write(tmp_path / ".claude" / "agents" / "Backend Architect.md", "# agent")
    _write(tmp_path / ".claude" / "agents" / "Data Engineer.md", "# agent")

    report = build_preflight_report(tmp_path)

    assert report.rule_files == (
        ".claude/rules/python/style.md",
        ".claude/rules/testing.md",
    )
    assert report.project_agents == ("Backend Architect", "Data Engineer")


@pytest.mark.unit
def test_detects_managed_block_in_claude_md(tmp_path: Path) -> None:
    claude_md = tmp_path / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_claude_md(claude_md)
    report = build_preflight_report(tmp_path)
    assert report.claude_md_exists is True
    assert report.claude_md_has_managed_block is True


@pytest.mark.unit
def test_claude_md_without_managed_block(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "CLAUDE.md", "# my own notes\nno markers here\n")
    report = build_preflight_report(tmp_path)
    assert report.claude_md_exists is True
    assert report.claude_md_has_managed_block is False


@pytest.mark.unit
def test_classifies_user_vs_dummyindex_hooks(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    _write(
        settings_path,
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "Edit",
                            "hooks": [{"type": "command", "command": "echo mine"}],
                        }
                    ]
                }
            }
        ),
    )
    # Now add dummyindex's own SessionStart hook on top.
    install_hooks(tmp_path)

    report = build_preflight_report(tmp_path)
    assert report.settings.exists is True
    assert report.settings.parseable is True
    assert "PostToolUse" in report.settings.user_hook_events
    assert "SessionStart" not in report.settings.user_hook_events  # ours, not the user's
    assert report.settings.dummyindex_hook_present is True


@pytest.mark.unit
def test_malformed_settings_flagged_not_parseable(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "settings.json", "{ not valid json")
    report = build_preflight_report(tmp_path)
    assert report.settings.exists is True
    assert report.settings.parseable is False


@pytest.mark.unit
def test_non_object_settings_flagged_not_parseable(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "settings.json", "[1, 2, 3]")
    report = build_preflight_report(tmp_path)
    assert report.settings.parseable is False


@pytest.mark.unit
def test_weird_hook_shapes_do_not_crash(tmp_path: Path) -> None:
    """Null inner hooks and non-string commands must classify, never throw."""
    _write(
        tmp_path / ".claude" / "settings.json",
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [{"hooks": None}],          # null inner list
                    "PreToolUse": [{"hooks": [{"command": 123}]}],  # non-str command
                    "Stop": "not-a-list",                        # non-list entries
                }
            }
        ),
    )
    report = build_preflight_report(tmp_path)  # must not raise
    assert report.settings.parseable is True
    # The integer command is truthy-but-not-our-sentinel → counts as a user hook.
    assert "PreToolUse" in report.settings.user_hook_events


@pytest.mark.unit
def test_legacy_sentinel_only_is_not_installed(tmp_path: Path) -> None:
    """A leftover legacy PostToolUse sentinel (no SessionStart) reads as NOT
    installed — install() will scrub it and add a fresh SessionStart hook."""
    _write(
        tmp_path / ".claude" / "settings.json",
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "matcher": "Edit",
                            "hooks": [
                                {"type": "command", "command": "# DUMMYINDEX_AUTO_REFRESH\nexit 0"}
                            ],
                        }
                    ]
                }
            }
        ),
    )
    report = build_preflight_report(tmp_path)
    assert report.settings.dummyindex_hook_present is False
    # The legacy sentinel entry is ours, not the user's — so PostToolUse must
    # not show up as a user-authored hook event either.
    assert "PostToolUse" not in report.settings.user_hook_events


@pytest.mark.integration
def test_git_clean_detection(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    clean = build_preflight_report(tmp_path)
    assert clean.is_git_repo is True
    assert clean.git_clean is True

    (tmp_path / "new_file.txt").write_text("hi", encoding="utf-8")
    dirty = build_preflight_report(tmp_path)
    assert dirty.git_clean is False


# ----- render ---------------------------------------------------------------


@pytest.mark.unit
def test_render_lists_managed_and_untouched(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "rules" / "style.md", "# style")
    report = build_preflight_report(tmp_path)
    md = render_preflight_md(report)
    assert "Will write / manage" in md
    assert "Will leave untouched" in md
    assert ".claude/rules/" in md
    assert ".context/**" in md


@pytest.mark.unit
def test_render_warns_on_unparseable_settings(tmp_path: Path) -> None:
    _write(tmp_path / ".claude" / "settings.json", "{ broken")
    report = build_preflight_report(tmp_path)
    md = render_preflight_md(report)
    assert "Warnings" in md
    assert "not valid JSON" in md


# ----- CLI ------------------------------------------------------------------


@pytest.mark.integration
def test_cli_preflight_prints_markdown(tmp_path: Path, capsys) -> None:
    rc = dispatch(["preflight", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dummyindex preflight" in out


@pytest.mark.integration
def test_cli_preflight_json(tmp_path: Path, capsys) -> None:
    rc = dispatch(["preflight", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["project_root"] == str(tmp_path.resolve())
    assert "settings" in payload


@pytest.mark.integration
def test_cli_preflight_rejects_unknown_flag(tmp_path: Path, capsys) -> None:
    rc = dispatch(["preflight", str(tmp_path), "--nope"])
    assert rc == 2
