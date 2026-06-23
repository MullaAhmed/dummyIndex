"""Tests for `dummyindex context preflight` — read-only setup inventory."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dummyindex.cli import dispatch
from dummyindex.context import bootstrap_claude_md
from dummyindex.context.domains.preflight import (
    ContextOwnership,
    build_preflight_report,
    context_ownership,
    render_preflight_md,
)
from dummyindex.context.hooks import install as install_hooks


def _init_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q"], cwd=str(path), check=True, capture_output=True
    )


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
    assert (
        "SessionStart" not in report.settings.user_hook_events
    )  # ours, not the user's
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
                    "SessionStart": [{"hooks": None}],  # null inner list
                    "PreToolUse": [{"hooks": [{"command": 123}]}],  # non-str command
                    "Stop": "not-a-list",  # non-list entries
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
                                {
                                    "type": "command",
                                    "command": "# DUMMYINDEX_AUTO_REFRESH\nexit 0",
                                }
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


@pytest.mark.unit
def test_submodule_git_file_reports_repo(tmp_path: Path) -> None:
    """A submodule's `.git` is a pointer *file*, not a directory — preflight
    must still report it as a git repo (the old `.is_dir()` check said False)."""
    (tmp_path / ".git").write_text(
        "gitdir: ../.git/modules/backend\n", encoding="utf-8"
    )
    report = build_preflight_report(tmp_path)
    assert report.is_git_repo is True


# ----- .context ownership ----------------------------------------------------


def _write_dummyindex_meta(context_dir: Path) -> None:
    """Minimal meta.json carrying the dummyindex ownership marker."""
    _write(
        context_dir / "meta.json",
        json.dumps({"schema_version": 1, "dummyindex_version": "0.25.0"}),
    )


@pytest.mark.unit
def test_absent_context_reports_unowned_none(tmp_path: Path) -> None:
    report = build_preflight_report(tmp_path)
    assert report.context_exists is False
    assert report.context_owned is None


@pytest.mark.unit
def test_empty_context_dir_is_safe_to_claim(tmp_path: Path) -> None:
    (tmp_path / ".context").mkdir()
    report = build_preflight_report(tmp_path)
    assert report.context_exists is True
    assert report.context_owned is None  # nothing in it — claiming loses nothing


@pytest.mark.unit
def test_foreign_context_reports_not_owned(tmp_path: Path) -> None:
    """Another tool's .context (content, no dummyindex meta.json) is FOREIGN."""
    _write(tmp_path / ".context" / "memory.md", "# someone else's agent memory\n")
    report = build_preflight_report(tmp_path)
    assert report.context_exists is True
    assert report.context_owned is False


@pytest.mark.unit
def test_foreign_meta_json_without_marker_is_not_owned(tmp_path: Path) -> None:
    _write(
        tmp_path / ".context" / "meta.json",
        json.dumps({"tool": "other-context-engine", "version": 3}),
    )
    assert build_preflight_report(tmp_path).context_owned is False


@pytest.mark.unit
def test_unparseable_meta_json_is_not_owned(tmp_path: Path) -> None:
    _write(tmp_path / ".context" / "meta.json", "{ not json")
    assert build_preflight_report(tmp_path).context_owned is False


@pytest.mark.unit
def test_non_object_meta_json_is_not_owned(tmp_path: Path) -> None:
    _write(tmp_path / ".context" / "meta.json", "[1, 2, 3]")
    assert build_preflight_report(tmp_path).context_owned is False


@pytest.mark.unit
def test_dummyindex_context_reports_owned(tmp_path: Path) -> None:
    _write_dummyindex_meta(tmp_path / ".context")
    report = build_preflight_report(tmp_path)
    assert report.context_exists is True
    assert report.context_owned is True


@pytest.mark.unit
def test_newer_schema_meta_still_reads_as_ours(tmp_path: Path) -> None:
    """An index written by a newer dummyindex must read OURS, not FOREIGN."""
    _write(
        tmp_path / ".context" / "meta.json",
        json.dumps({"schema_version": 999, "dummyindex_version": "9.0.0"}),
    )
    assert build_preflight_report(tmp_path).context_owned is True


@pytest.mark.unit
def test_context_ownership_probe_enum(tmp_path: Path) -> None:
    context_dir = tmp_path / ".context"
    assert context_ownership(context_dir) is ContextOwnership.ABSENT
    context_dir.mkdir()
    assert context_ownership(context_dir) is ContextOwnership.ABSENT
    _write(context_dir / "notes.md", "foreign\n")
    assert context_ownership(context_dir) is ContextOwnership.FOREIGN
    _write_dummyindex_meta(context_dir)
    assert context_ownership(context_dir) is ContextOwnership.OURS


# ----- git optional locks -----------------------------------------------------


@pytest.mark.unit
def test_git_status_suppresses_optional_locks(tmp_path: Path, monkeypatch) -> None:
    """Preflight's `git status` must never take index.lock: a hook killed
    mid-query would strand the lock (in a submodule, under the superproject's
    .git/modules/<name>/). GIT_OPTIONAL_LOCKS=0 makes the query lock-free."""
    (tmp_path / ".git").mkdir()  # enough for is_git_repo — no real git needed

    captured: dict = {}

    class _Result:
        returncode = 0
        stdout = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        return _Result()

    monkeypatch.setattr(
        "dummyindex.context.domains.preflight.inventory.subprocess.run", fake_run
    )
    report = build_preflight_report(tmp_path)
    assert report.git_clean is True
    env = captured["env"]
    assert env is not None
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    # The rest of the parent environment must still be passed through.
    assert len(env) > 1


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


@pytest.mark.unit
def test_render_warns_on_foreign_context(tmp_path: Path) -> None:
    """A foreign .context must surface an ownership warning and the managed
    `.context/**` claim must be withheld — not stated unconditionally."""
    _write(tmp_path / ".context" / "memory.md", "# someone else's agent memory\n")
    md = render_preflight_md(build_preflight_report(tmp_path))
    assert "Warnings" in md
    assert "not created by dummyindex" in md
    assert "WITHHELD" in md
    assert "will not be touched" in md


@pytest.mark.unit
def test_render_owned_context_has_no_ownership_warning(tmp_path: Path) -> None:
    _write_dummyindex_meta(tmp_path / ".context")
    md = render_preflight_md(build_preflight_report(tmp_path))
    assert "not created by dummyindex" not in md
    assert "WITHHELD" not in md


@pytest.mark.unit
def test_render_states_context_ownership(tmp_path: Path) -> None:
    absent_md = render_preflight_md(build_preflight_report(tmp_path))
    assert "- .context: absent" in absent_md

    _write_dummyindex_meta(tmp_path / ".context")
    owned_md = render_preflight_md(build_preflight_report(tmp_path))
    assert "- .context: present, dummyindex-owned" in owned_md


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
    assert payload["context_exists"] is False
    assert payload["context_owned"] is None


@pytest.mark.integration
def test_cli_preflight_rejects_unknown_flag(tmp_path: Path, capsys) -> None:
    rc = dispatch(["preflight", str(tmp_path), "--nope"])
    assert rc == 2
