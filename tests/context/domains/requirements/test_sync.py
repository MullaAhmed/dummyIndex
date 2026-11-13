"""Sync restores local setup from the manifest. Every runner here is a fake."""

from __future__ import annotations

import json
from pathlib import Path

from dummyindex.context.default_plugins import RunResult
from dummyindex.context.domains.equip.enums import (
    EquipmentKind,
    EquipmentScope,
    EquipmentSource,
)
from dummyindex.context.domains.equip.lifecycle.manifest import write_manifest
from dummyindex.context.domains.equip.models import EquipmentItem, EquipmentManifest
from dummyindex.context.domains.requirements import (
    PluginRequirement,
    Requirements,
    SkillRequirement,
)
from dummyindex.context.domains.requirements.sync import sync_requirements

CAVEMAN = "caveman@caveman"
CAVEMAN_REPO = ("repo", "JuliusBrussee/caveman")
UNTRUSTED = "foo@evil-market"


class FakeRunner:
    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.returncode = returncode

    def __call__(self, argv: list[str], cwd: Path) -> RunResult:
        self.calls.append(list(argv))
        return RunResult(returncode=self.returncode, stdout="", stderr="")

    def plugin_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call[:1] == ["claude"]]


def _write_settings(root: Path, enabled: dict) -> Path:
    path = root / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabledPlugins": enabled}), encoding="utf-8")
    return path


def _agent_fixture(root: Path) -> EquipmentItem:
    """A generated project agent whose canonical body carries a description."""
    body = root / ".context" / "equipment" / "reviewer.md"
    body.parent.mkdir(parents=True, exist_ok=True)
    body.write_text(
        "---\nname: reviewer\ndescription: Reviews diffs for convention drift\n---\n"
        "# Reviewer\n\nBody text.\n",
        encoding="utf-8",
    )
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="reviewer",
        path=".context/equipment/reviewer.md",
        source=EquipmentSource.GENERATED,
        scope=EquipmentScope.PROJECT,
    )
    write_manifest(
        root / ".context", EquipmentManifest(schema_version=4, items=(item,))
    )
    return item


def _requirements(
    *,
    plugins: tuple[PluginRequirement, ...] = (),
    skills: tuple[SkillRequirement, ...] = (),
    native: bool = False,
) -> Requirements:
    return Requirements(plugins=plugins, skills=skills, require_native_adapters=native)


def _sync(root: Path, req: Requirements, runner: FakeRunner, **kwargs):
    options = {"approve": False, "local_only": False, "confirm": None}
    options.update(kwargs)
    return sync_requirements(root, req, runner=runner, **options)


def test_deleted_native_adapter_is_restored(tmp_path: Path) -> None:
    _agent_fixture(tmp_path)
    req = _requirements(native=True)
    runner = FakeRunner()

    first = _sync(tmp_path, req, runner)
    adapter = tmp_path / ".claude" / "agents" / "reviewer.md"
    assert adapter.is_file()
    assert "Reviews diffs for convention drift" in adapter.read_text(encoding="utf-8")
    assert first.adapters == (".claude/agents/reviewer.md",)

    adapter.unlink()
    _sync(tmp_path, req, runner)

    assert adapter.is_file()
    assert "Reviews diffs for convention drift" in adapter.read_text(encoding="utf-8")


def test_trusted_plugin_installs_through_fake_runner(tmp_path: Path) -> None:
    runner = FakeRunner()
    req = _requirements(plugins=(PluginRequirement(id=CAVEMAN, extra=(CAVEMAN_REPO,)),))

    report = _sync(tmp_path, req, runner)

    assert report.installed == (CAVEMAN,)
    assert report.errors == ()
    assert ["claude", "plugin", "install", CAVEMAN, "--scope", "project"] in (
        runner.calls
    )


def test_untrusted_plugin_is_skipped_without_tty_or_yes(tmp_path: Path) -> None:
    runner = FakeRunner()
    req = _requirements(
        plugins=(PluginRequirement(id=UNTRUSTED, extra=(("repo", "evil/foo"),)),)
    )

    report = _sync(tmp_path, req, runner, confirm=None, approve=False)

    assert report.installed == ()
    assert [target for target, _ in report.skipped] == [UNTRUSTED]
    assert runner.plugin_calls() == []


def test_untrusted_plugin_installs_with_yes(tmp_path: Path) -> None:
    runner = FakeRunner()
    req = _requirements(
        plugins=(PluginRequirement(id=UNTRUSTED, extra=(("repo", "evil/foo"),)),)
    )

    report = _sync(tmp_path, req, runner, approve=True)

    assert report.installed == (UNTRUSTED,)
    assert ["claude", "plugin", "install", UNTRUSTED, "--scope", "project"] in (
        runner.calls
    )


def test_untrusted_plugin_follows_tty_answer(tmp_path: Path) -> None:
    prompts: list[str] = []

    def decline(prompt: str) -> bool:
        prompts.append(prompt)
        return False

    runner = FakeRunner()
    req = _requirements(
        plugins=(PluginRequirement(id=UNTRUSTED, extra=(("repo", "evil/foo"),)),)
    )

    report = _sync(tmp_path, req, runner, confirm=decline)

    assert prompts == [f"Install untrusted plugin {UNTRUSTED}? [y/N] "]
    assert report.installed == ()
    assert runner.plugin_calls() == []


def test_official_name_with_different_repo_is_untrusted(tmp_path: Path) -> None:
    runner = FakeRunner()
    req = _requirements(
        plugins=(
            PluginRequirement(
                id="superpowers@claude-plugins-official",
                extra=(("repo", "evil/superpowers"),),
            ),
        )
    )

    report = _sync(tmp_path, req, runner, confirm=None, approve=False)

    assert report.installed == ()
    assert [target for target, _ in report.skipped] == [
        "superpowers@claude-plugins-official"
    ]
    assert runner.plugin_calls() == []


def test_local_only_makes_no_plugin_runner_calls(tmp_path: Path) -> None:
    runner = FakeRunner()
    req = _requirements(
        plugins=(PluginRequirement(id=CAVEMAN, extra=(CAVEMAN_REPO,)),),
        skills=(SkillRequirement(name="dummyindex-plan"),),
    )

    report = _sync(tmp_path, req, runner, local_only=True, approve=True)

    assert report.installed == ()
    assert runner.plugin_calls() == []
    assert runner.calls == [
        ["dummyindex", "install", "--scope", "user", "--skill-only"]
    ]


def test_skill_family_runs_through_runner(tmp_path: Path) -> None:
    runner = FakeRunner(returncode=2)
    req = _requirements(skills=(SkillRequirement(name="dummyindex-plan"),))

    report = _sync(tmp_path, req, runner)

    assert report.skill_family_ran is True
    assert runner.calls == [
        ["dummyindex", "install", "--scope", "user", "--skill-only"]
    ]
    assert report.errors and report.errors[0][0].startswith("dummyindex install")


def test_explicitly_disabled_plugin_is_left_alone(tmp_path: Path) -> None:
    settings = _write_settings(tmp_path, {CAVEMAN: False})
    before = settings.read_text(encoding="utf-8")
    runner = FakeRunner()
    req = _requirements(plugins=(PluginRequirement(id=CAVEMAN, extra=(CAVEMAN_REPO,)),))

    report = _sync(tmp_path, req, runner, approve=True)

    assert report.installed == ()
    assert report.skipped == ((CAVEMAN, "disabled by you"),)
    assert runner.plugin_calls() == []
    assert settings.read_text(encoding="utf-8") == before
