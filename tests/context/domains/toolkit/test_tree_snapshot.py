"""Tree snapshots before and after each write path.

A toolkit call may change only: ``.context/`` (project stash), ``--out-dir``
(terminal bundles), or host config files plus their timestamped backups. Each
test compares the complete file set and content before and after the call.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dummyindex.context.domains.toolkit import toolkit_install, toolkit_mutate
from tests.context.domains.toolkit.helpers import SHA_A, SKILL_TEXT, FakeGh, snapshot

pytestmark = pytest.mark.unit


def _changed(before: dict[str, bytes], after: dict[str, bytes]) -> set[str]:
    keys = set(before) | set(after)
    return {k for k in keys if before.get(k) != after.get(k)}


def _is_backup(rel: str) -> bool:
    return ".bak-" in rel.rsplit("/", 1)[-1]


def _config_or_backup(rel: str, base_names: tuple[str, ...]) -> bool:
    """True when ``rel`` is a host config file, or the timestamped backup of one."""
    original = rel.split(".bak-", 1)[0] if _is_backup(rel) else rel
    return original in base_names


def _server(tmp_path: Path) -> Path:
    cfg = tmp_path / "srv.json"
    cfg.write_text(
        '{"type": "http", "url": "https://example.test/mcp"}', encoding="utf-8"
    )
    return cfg


def test_project_session_writes_only_host_config_stash_and_backups(
    root: Path, home: Path, tmp_path: Path
) -> None:
    cfg = _server(tmp_path)
    src = tmp_path / "SKILL.md"
    src.write_text(SKILL_TEXT, encoding="utf-8")
    (root / ".mcp.json").write_text(
        '{"mcpServers": {"keep": {"command": "x"}}}', encoding="utf-8"
    )
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_text(
        '{"enabledPlugins": {"a@b": true}}', encoding="utf-8"
    )
    before_root = snapshot(root)
    before_home = snapshot(home)

    kw = {"root": root, "home": home, "scope": "project"}
    toolkit_mutate("add", "srv", kind="mcp", config_file=cfg, **kw)
    toolkit_mutate("disable", "keep", kind="mcp", **kw)
    toolkit_mutate("add", "demo", kind="skill", source_file=src, **kw)
    toolkit_mutate("disable", "demo", kind="skill", **kw)
    toolkit_mutate("enable", "a@b", kind="plugin", **kw)
    toolkit_mutate("disable", "a@b", kind="plugin", **kw)

    changed = _changed(before_root, snapshot(root))
    allowed = {".mcp.json", ".claude/settings.json", ".claude/skills/demo/SKILL.md"}
    assert changed, "the session should have changed something"
    for rel in changed:
        if rel.startswith(".context/toolkit/"):
            continue
        assert (
            _config_or_backup(rel, (".mcp.json", ".claude/settings.json"))
            or rel in allowed
        ), rel
    assert snapshot(home) == before_home, "project scope must not touch home"


def test_backups_hold_the_exact_pre_write_bytes(
    root: Path, home: Path, tmp_path: Path
) -> None:
    cfg = _server(tmp_path)
    original = b'{"mcpServers": {"keep": {"command": "x"}}}'
    (root / ".mcp.json").write_bytes(original)
    toolkit_mutate(
        "add", "srv", root=root, home=home, kind="mcp", scope="project", config_file=cfg
    )
    backups = sorted((root).glob(".mcp.json.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original


def test_terminal_session_writes_only_under_out_dir(
    root: Path, home: Path, out_dir: Path, tmp_path: Path
) -> None:
    before_root = snapshot(root)
    before_home = snapshot(home)
    before_out = snapshot(out_dir)
    cfg = _server(tmp_path)
    kw = {
        "root": root,
        "home": home,
        "scope": "terminal",
        "terminal_id": "t-1",
        "out_dir": out_dir,
    }

    toolkit_mutate(
        "add", "srv", kind="mcp", config_file=cfg, mechanism="mcp_exclusive", **kw
    )
    toolkit_mutate("add", "codex@openai-codex", kind="plugin", **kw)
    toolkit_mutate("disable", "codex@openai-codex", kind="plugin", **kw)

    assert snapshot(root) == before_root
    assert snapshot(home) == before_home
    changed = _changed(before_out, snapshot(out_dir))
    assert changed
    assert all(rel.startswith("t-1/") for rel in changed), changed


def test_user_session_writes_only_under_home(
    root: Path, home: Path, tmp_path: Path
) -> None:
    before_root = snapshot(root)
    cfg = _server(tmp_path)
    toolkit_mutate(
        "add", "srv", root=root, home=home, kind="mcp", scope="user", config_file=cfg
    )
    toolkit_mutate("disable", "srv", root=root, home=home, kind="mcp", scope="user")
    assert snapshot(root) == before_root
    changed = _changed({}, snapshot(home))
    assert ".claude.json" in changed
    assert ".claude/toolkit/disabled.json" in changed


def test_install_apply_writes_only_the_stash(root: Path, home: Path) -> None:
    gh = FakeGh(
        contents={"owner/repo": {"skills/demo/SKILL.md": SKILL_TEXT}}, commit_sha=SHA_A
    )
    src = "github:owner/repo/skills/demo"
    before_home = snapshot(home)
    prev = toolkit_install(
        "skill", src, root=root, home=home, scope="project", preview=True, runner=gh
    )
    before = snapshot(root)
    toolkit_install(
        "skill",
        src,
        root=root,
        home=home,
        scope="project",
        yes=True,
        plan_hash=prev["plan_hash"],
        runner=gh,
    )
    changed = _changed(before, snapshot(root))
    assert changed == {".context/toolkit/disabled.json"}
    assert snapshot(home) == before_home
