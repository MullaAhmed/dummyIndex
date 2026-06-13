"""End-to-end: the full equip v2 lifecycle on a real built ``.context/``.

One integration test that walks the spec §12 e2e scenario through the CLI
boundary exactly as a user would: build the context spine, apply the toolkit
(files + settings hook + manifest), hand-edit one generated agent, observe it
become USER_MODIFIED, confirm refresh skips it, patch another item via the CLI
(PRISTINE + version bump), and uninstall — leaving the user-modified file and a
pre-existing user hook intact while removing everything that is ours.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dummyindex.cli.equip import project_slug, run as run_equip
from dummyindex.context.build.runner import build_all

pytestmark = pytest.mark.integration


def _read_manifest(root: Path) -> dict:
    return json.loads((root / ".context" / "equipment.json").read_text(encoding="utf-8"))


def _state(manifest: dict, name: str) -> dict | None:
    return next((i for i in manifest["items"] if i["name"] == name), None)


def _status_json(root: Path, capsys) -> dict:
    capsys.readouterr()  # drain
    rc = run_equip(["status", "--root", str(root), "--json"])
    assert rc == 0
    return json.loads(capsys.readouterr().out)


def test_equip_v2_full_lifecycle(tmp_path: Path, capsys) -> None:
    # --- stand up a real .context/ for a python repo -------------------------
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\n[tool.mypy]\n"
        '[project]\nname = "demo"\ndependencies = ["pytest"]\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    build_all(tmp_path, out_root=tmp_path, dummyindex_version="test")
    assert (tmp_path / ".context" / "map" / "files.json").is_file()

    # --- a pre-existing USER hook that must survive uninstall ----------------
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {"hooks": [{"type": "command", "command": "echo USER-OWN-HOOK"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    proj = project_slug(tmp_path)
    impl = tmp_path / ".claude" / "agents" / "python-implementer.md"
    tester = tmp_path / ".claude" / "agents" / "python-tester.md"

    # --- apply: full set + settings hook + manifest v2 -----------------------
    assert run_equip(["apply", str(tmp_path)]) == 0
    assert impl.is_file() and tester.is_file()
    assert (tmp_path / ".claude" / "agents" / f"{proj}-reviewer.md").is_file()
    assert (tmp_path / ".claude" / "skills" / f"{proj}-verify" / "SKILL.md").is_file()

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    post_cmds = [h["command"] for e in settings["hooks"]["PostToolUse"] for h in e["hooks"]]
    assert any("USER-OWN-HOOK" in c for c in post_cmds)        # user hook preserved
    assert any("DUMMYINDEX_EQUIP" in c for c in post_cmds)     # our hook wired
    assert any("ruff format" in c for c in post_cmds)

    manifest = _read_manifest(tmp_path)
    assert manifest["schema_version"] == 4
    assert _state(manifest, "python-implementer")["version"] == "1.0.0"

    # everything starts PRISTINE
    states = {i["name"]: i["state"] for i in _status_json(tmp_path, capsys)["items"]}
    assert states["python-implementer"] == "pristine"
    assert states["python-tester"] == "pristine"

    # --- hand-edit the implementer → USER_MODIFIED ---------------------------
    impl.write_text(impl.read_text(encoding="utf-8") + "\n<!-- HAND EDIT -->\n", encoding="utf-8")
    states = {i["name"]: i["state"] for i in _status_json(tmp_path, capsys)["items"]}
    assert states["python-implementer"] == "user-modified"

    # --- refresh skips the user-modified item --------------------------------
    capsys.readouterr()
    assert run_equip(["refresh", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "python-implementer" in out  # reported as skipped
    assert "<!-- HAND EDIT -->" in impl.read_text(encoding="utf-8")  # not clobbered

    # --- patch the tester via the CLI → PRISTINE, 1.0.1 ----------------------
    old = "## Ground yourself first"
    assert old in tester.read_text(encoding="utf-8")
    patch_file = tmp_path / "patch.json"
    patch_file.write_text(
        json.dumps({"old": old, "new": old + "\n\n<!-- learned: prefer table tests -->"}),
        encoding="utf-8",
    )
    assert (
        run_equip(
            ["patch", "--item", "python-tester", "--from-file", str(patch_file), "--root", str(tmp_path)]
        )
        == 0
    )
    assert "learned: prefer table tests" in tester.read_text(encoding="utf-8")
    assert "version: 1.0.1" in tester.read_text(encoding="utf-8")  # frontmatter synced
    states = {i["name"]: (i["state"], i["version"]) for i in _status_json(tmp_path, capsys)["items"]}
    assert states["python-tester"] == ("pristine", "1.0.1")  # re-baselined + bumped

    # --- re-apply: the sanctioned patch must SURVIVE (evolved item kept) -----
    capsys.readouterr()
    assert run_equip(["apply", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "evolved" in out                          # reported as kept-evolved
    assert "learned: prefer table tests" in tester.read_text(encoding="utf-8")
    states = {i["name"]: (i["state"], i["version"]) for i in _status_json(tmp_path, capsys)["items"]}
    assert states["python-tester"] == ("pristine", "1.0.1")  # version not regressed

    # --- refresh skips the evolved item too ----------------------------------
    capsys.readouterr()
    assert run_equip(["refresh", "--root", str(tmp_path)]) == 0
    assert "learned: prefer table tests" in tester.read_text(encoding="utf-8")

    # --- uninstall: ours gone, user-modified + user hook remain --------------
    capsys.readouterr()
    assert run_equip(["uninstall", "--root", str(tmp_path)]) == 0
    assert impl.is_file()                       # user-modified file kept
    assert "<!-- HAND EDIT -->" in impl.read_text(encoding="utf-8")
    assert not tester.is_file()                 # pristine file removed
    assert not (tmp_path / ".context" / "equipment.json").exists()  # manifest removed

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    post_cmds = [h["command"] for e in settings["hooks"].get("PostToolUse", []) for h in e["hooks"]]
    assert any("USER-OWN-HOOK" in c for c in post_cmds)        # user hook survives
    assert not any("DUMMYINDEX_EQUIP" in c for c in post_cmds)  # our hook removed
