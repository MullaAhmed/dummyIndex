"""Upgrade of an existing ``.context/`` to the installed CLI: contained, retried, quiet."""

from __future__ import annotations

import dataclasses
import os
import subprocess
import time
from pathlib import Path

import pytest

from dummyindex.context.build import context_upgrade
from dummyindex.context.build.context_upgrade import (
    GITIGNORE_WARNING,
    _contained,
    is_stale,
    upgrade_project,
)
from dummyindex.context.build.enriched_refresh import RefreshResult
from dummyindex.context.build.meta import new_meta, read_meta, write_meta
from dummyindex.context.domains.config import default_config, write_config
from dummyindex.context.domains.equip.enums import (
    EquipmentKind,
    EquipmentSource,
    RequestedBy,
)
from dummyindex.context.domains.equip.generate import fresh as equip_fresh
from dummyindex.context.domains.equip.lifecycle import status as equip_status
from dummyindex.context.domains.equip.lifecycle.hashing import content_hash
from dummyindex.context.domains.equip.lifecycle.manifest import (
    read_manifest,
    write_manifest,
)
from dummyindex.context.domains.equip.models import EquipmentItem, EquipmentManifest

CLI = "0.40.0"
BODY = (
    "---\nname: db\ndescription: Database specialist\nversion: 1.0.0\n---\n"
    "# db\n\nKeep the schema in sync.\n"
)


def _runner(ignored: bool):
    calls: list[tuple[str, ...]] = []

    def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0 if ignored else 1, "", "")

    run.calls = calls  # type: ignore[attr-defined]
    return run


def _project(root: Path, *, stamp: str = "0.30.0", config_json: bool = True) -> Path:
    context_dir = root / ".context"
    context_dir.mkdir(parents=True)
    write_meta(context_dir / "meta.json", new_meta(root, stamp))
    if config_json:
        write_config(context_dir, default_config(platform="claude"))
    (context_dir / "features").mkdir()
    (context_dir / "features" / "INDEX.json").write_text(
        '{"features": []}\n', encoding="utf-8"
    )
    return context_dir


def _pristine_db(root: Path, context_dir: Path, *, requested_by=None) -> EquipmentItem:
    body_path = context_dir / "equipment" / "db.md"
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_text(BODY, encoding="utf-8")
    item = EquipmentItem(
        kind=EquipmentKind.AGENT,
        name="db",
        path=".context/equipment/db.md",
        source=EquipmentSource.GENERATED,
        capabilities=("database",),
        version="1.0.0",
        origin_hash=content_hash(BODY),
        requested_by=requested_by,
    )
    write_manifest(context_dir, EquipmentManifest(schema_version=4, items=(item,)))
    return item


def _stub_fresh(monkeypatch: pytest.MonkeyPatch, renders: dict[str, str]) -> None:
    monkeypatch.setattr(equip_fresh, "fresh_renders", lambda root, ctx: dict(renders))


def _refresh(context_dir: Path) -> RefreshResult:
    return RefreshResult(context_dir=context_dir, written=())


@pytest.mark.unit
def test_legacy_specialist_is_backfilled_and_keeps_body_and_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    _pristine_db(tmp_path, context_dir)
    _stub_fresh(monkeypatch, {"db": BODY})
    adapter = tmp_path / ".claude" / "agents" / "db.md"

    report = upgrade_project(
        tmp_path,
        package_version=CLI,
        refresh=_refresh(context_dir),
        runner=_runner(ignored=False),
    )

    item = read_manifest(context_dir).items[0]
    assert item.requested_by is RequestedBy.LEGACY
    assert (context_dir / "equipment" / "db.md").read_text(encoding="utf-8") == BODY
    assert adapter.is_file()
    assert "Database specialist" in adapter.read_text(encoding="utf-8")
    assert "specialist without evidence: db (see dummyindex-gc)" in report.warnings
    assert "agents/db.md" in report.adapters_written[0]


@pytest.mark.unit
def test_upgrade_moves_stamp_last_and_second_run_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    _pristine_db(tmp_path, context_dir)
    _stub_fresh(monkeypatch, {"db": BODY})
    index_before = (context_dir / "features" / "INDEX.json").read_bytes()
    runner = _runner(ignored=True)

    first = upgrade_project(
        tmp_path, package_version=CLI, refresh=_refresh(context_dir), runner=runner
    )

    assert first.stamp_advanced
    assert first.changed
    assert read_meta(context_dir / "meta.json").dummyindex_version == CLI
    assert (context_dir / "config.toml").is_file()
    assert (context_dir / "equipment" / "grounding" / "db.md").is_file()
    assert (tmp_path / ".claude" / "agents" / "db.md").is_file()
    assert first.warnings.count(GITIGNORE_WARNING) == 1
    assert (context_dir / "features" / "INDEX.json").read_bytes() == index_before

    second = upgrade_project(
        tmp_path, package_version=CLI, refresh=_refresh(context_dir), runner=runner
    )

    assert not second.changed
    assert not second.stamp_advanced
    assert second.adapters_written == ()
    assert GITIGNORE_WARNING not in second.warnings
    assert (context_dir / "features" / "INDEX.json").read_bytes() == index_before


@pytest.mark.unit
def test_failed_step_holds_the_stamp_and_next_run_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    _pristine_db(tmp_path, context_dir)
    _stub_fresh(monkeypatch, {"db": BODY})
    real_refresh = equip_status.refresh

    def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(equip_status, "refresh", broken)
    failed = upgrade_project(
        tmp_path,
        package_version=CLI,
        refresh=_refresh(context_dir),
        runner=_runner(False),
    )
    assert any(err.startswith("equipment:") for err in failed.errors)
    assert not failed.stamp_advanced
    assert read_meta(context_dir / "meta.json").dummyindex_version == "0.30.0"

    monkeypatch.setattr(equip_status, "refresh", real_refresh)
    retried = upgrade_project(
        tmp_path,
        package_version=CLI,
        refresh=_refresh(context_dir),
        runner=_runner(False),
    )
    assert retried.errors == ()
    assert retried.stamp_advanced
    assert read_meta(context_dir / "meta.json").dummyindex_version == CLI


@pytest.mark.unit
def test_newer_stamp_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    context_dir = _project(tmp_path, stamp="0.50.0")
    _pristine_db(tmp_path, context_dir)
    _stub_fresh(monkeypatch, {"db": BODY})

    report = upgrade_project(
        tmp_path,
        package_version=CLI,
        refresh=_refresh(context_dir),
        runner=_runner(True),
    )

    assert report.warnings == ("stamp newer than CLI",)
    assert not report.changed
    assert not (context_dir / "config.toml").exists()
    assert read_meta(context_dir / "meta.json").dummyindex_version == "0.50.0"


@pytest.mark.unit
def test_path_outside_allowed_roots_is_skipped_and_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    outside = tmp_path / "src" / "evil.md"
    outside.parent.mkdir()
    outside.write_text("keep me\n", encoding="utf-8")
    write_manifest(
        context_dir,
        EquipmentManifest(
            schema_version=4,
            items=(
                EquipmentItem(
                    kind=EquipmentKind.SKILL,
                    name="evil",
                    path="src/evil.md",
                    source=EquipmentSource.GENERATED,
                    version="1.0.0",
                    origin_hash=content_hash("keep me\n"),
                ),
            ),
        ),
    )
    _stub_fresh(monkeypatch, {"evil": "overwritten\n"})

    report = upgrade_project(
        tmp_path,
        package_version=CLI,
        refresh=_refresh(context_dir),
        runner=_runner(False),
    )

    assert "src/evil.md" in report.skipped_paths
    assert outside.read_text(encoding="utf-8") == "keep me\n"


@pytest.mark.unit
def test_held_lock_reports_in_progress_and_nested_run_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    lock = context_dir / "cache" / "upgrade.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("held\n", encoding="utf-8")

    report = upgrade_project(
        tmp_path,
        package_version=CLI,
        refresh=_refresh(context_dir),
        runner=_runner(False),
    )

    assert report.warnings == ("upgrade in progress",)
    assert not (context_dir / "config.toml").exists()
    assert lock.is_file()  # someone else's lock is never removed


@pytest.mark.unit
def test_concurrent_run_reports_in_progress_while_first_run_holds_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    _pristine_db(tmp_path, context_dir)
    inner: list[object] = []

    def renders_then_race(root, ctx):
        inner.append(
            upgrade_project(
                tmp_path,
                package_version=CLI,
                refresh=_refresh(context_dir),
                runner=_runner(False),
            )
        )
        return {"db": BODY}

    monkeypatch.setattr(equip_fresh, "fresh_renders", renders_then_race)

    outer = upgrade_project(
        tmp_path,
        package_version=CLI,
        refresh=_refresh(context_dir),
        runner=_runner(False),
    )

    assert inner[0].warnings == ("upgrade in progress",)
    assert outer.stamp_advanced
    assert not (context_dir / "cache" / "upgrade.lock").exists()


@pytest.mark.unit
def test_stale_lock_is_reclaimed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    context_dir = _project(tmp_path)
    lock = context_dir / "cache" / "upgrade.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("dead\n", encoding="utf-8")
    old = time.time() - (context_upgrade.LOCK_STALE_SECONDS + 60)
    os.utime(lock, (old, old))
    _stub_fresh(monkeypatch, {})

    report = upgrade_project(
        tmp_path,
        package_version=CLI,
        refresh=_refresh(context_dir),
        runner=_runner(False),
    )

    assert report.stamp_advanced
    assert "upgrade in progress" not in report.warnings


@pytest.mark.unit
def test_malformed_config_json_creates_no_config_toml_and_keeps_its_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path, config_json=False)
    raw = b'{"schema_version": 5, "scope": '
    (context_dir / "config.json").write_bytes(raw)
    _stub_fresh(monkeypatch, {})

    upgrade_project(
        tmp_path,
        package_version=CLI,
        refresh=_refresh(context_dir),
        runner=_runner(False),
    )

    assert not (context_dir / "config.toml").exists()
    assert (context_dir / "config.json").read_bytes() == raw


@pytest.mark.unit
def test_gitignore_warning_only_when_claude_settings_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    _stub_fresh(monkeypatch, {})
    runner = _runner(ignored=False)

    report = upgrade_project(
        tmp_path, package_version=CLI, refresh=_refresh(context_dir), runner=runner
    )

    assert runner.calls == [("check-ignore", "-q", ".claude/settings.json")]
    assert GITIGNORE_WARNING not in report.warnings


@pytest.mark.unit
def test_is_stale_compares_stamp_with_cli(tmp_path: Path):
    context_dir = _project(tmp_path, stamp="0.30.0")
    assert is_stale(context_dir, CLI)
    assert not is_stale(context_dir, "0.30.0")
    assert not is_stale(context_dir, "0.20.0")
    assert not is_stale(tmp_path / "missing", CLI)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rel", "allowed"),
    [
        (".context/equipment/db.md", True),
        (".claude/agents/db.md", True),
        (".claude/skills/db/SKILL.md", True),
        (".context/equipment", False),
        (".claude/settings.json", False),
        ("src/app.py", False),
        ("../escape.md", False),
        (".context/equipment/../../src/app.py", False),
    ],
)
def test_contained_only_allows_equipment_and_claude_roots(
    tmp_path: Path, rel: str, allowed: bool
):
    assert (_contained(tmp_path, rel) is not None) is allowed


@pytest.mark.unit
def test_no_meta_means_nothing_to_upgrade(tmp_path: Path):
    (tmp_path / ".context").mkdir()
    report = upgrade_project(
        tmp_path, package_version=CLI, refresh=None, runner=_runner(False)
    )
    assert report.warnings == ("no .context/meta.json: nothing to upgrade",)
    assert not (tmp_path / ".context" / "config.toml").exists()


@pytest.mark.unit
def test_dataclass_report_is_frozen():
    report = context_upgrade.UpgradeReport()
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.changed = True  # type: ignore[misc]


def _generated(name: str, capability: str, requested_by=None) -> EquipmentItem:
    return EquipmentItem(
        kind=EquipmentKind.AGENT,
        name=name,
        path=f".context/equipment/{name}.md",
        source=EquipmentSource.GENERATED,
        capabilities=(capability,),
        version="1.0.0",
        origin_hash=content_hash(f"{name}\n"),
        requested_by=requested_by,
    )


def _with_items(context_dir: Path, *items: EquipmentItem) -> None:
    write_manifest(context_dir, EquipmentManifest(schema_version=4, items=items))


def _stack(monkeypatch: pytest.MonkeyPatch, **evidence: tuple[str, ...]) -> None:
    from dummyindex.context.domains.equip.generate import detect as equip_detect
    from dummyindex.context.domains.equip.models import StackProfile

    profile = StackProfile(label="python", **evidence)
    monkeypatch.setattr(equip_detect, "detect_stack", lambda ctx: profile)


def _run_once(root: Path, context_dir: Path) -> context_upgrade.UpgradeReport:
    return upgrade_project(
        root, package_version=CLI, refresh=_refresh(context_dir), runner=_runner(False)
    )


@pytest.mark.unit
def test_legacy_db_backed_by_stack_evidence_is_not_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    _with_items(context_dir, _generated("db", "database"))
    _stack(monkeypatch, data_stores=("sqlalchemy",))
    _stub_fresh(monkeypatch, {})

    report = _run_once(tmp_path, context_dir)

    assert read_manifest(context_dir).items[0].requested_by is RequestedBy.LEGACY
    assert not any(w.startswith("specialist without evidence") for w in report.warnings)


@pytest.mark.unit
def test_always_on_specialist_is_never_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    _with_items(context_dir, _generated("security", "security"))
    _stub_fresh(monkeypatch, {})

    report = _run_once(tmp_path, context_dir)

    assert read_manifest(context_dir).items[0].requested_by is RequestedBy.LEGACY
    assert not any(w.startswith("specialist without evidence") for w in report.warnings)


@pytest.mark.unit
def test_add_specialist_db_without_evidence_is_not_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    _with_items(
        context_dir,
        _generated("db", "database", requested_by=RequestedBy.ADD_SPECIALIST),
    )
    _stub_fresh(monkeypatch, {})

    report = _run_once(tmp_path, context_dir)

    assert (
        read_manifest(context_dir).items[0].requested_by is RequestedBy.ADD_SPECIALIST
    )
    assert not any(w.startswith("specialist without evidence") for w in report.warnings)


@pytest.mark.unit
def test_core_agent_is_never_backfilled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    context_dir = _project(tmp_path)
    _with_items(context_dir, _generated("implementer", "implement"))
    _stub_fresh(monkeypatch, {})

    _run_once(tmp_path, context_dir)

    assert read_manifest(context_dir).items[0].requested_by is None


@pytest.mark.unit
def test_two_threads_one_holds_the_lock_and_the_other_reports_in_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import threading

    from dummyindex.context.domains.requirements import read_requirements

    context_dir = _project(tmp_path)
    holding = threading.Event()
    release = threading.Event()

    def slow_renders(root, ctx):
        holding.set()
        release.wait(timeout=10)
        return {}

    monkeypatch.setattr(equip_fresh, "fresh_renders", slow_renders)
    results: dict[str, context_upgrade.UpgradeReport] = {}

    def run(key: str) -> None:
        results[key] = _run_once(tmp_path, context_dir)

    holder = threading.Thread(target=run, args=("holder",))
    holder.start()
    assert holding.wait(timeout=10)
    contender = threading.Thread(target=run, args=("contender",))
    contender.start()
    contender.join(timeout=10)
    release.set()
    holder.join(timeout=10)

    assert results["contender"].warnings == ("upgrade in progress",)
    assert results["holder"].stamp_advanced
    assert read_meta(context_dir / "meta.json").dummyindex_version == CLI
    assert read_requirements(context_dir / "config.toml") is not None
    assert not (context_dir / "cache" / "upgrade.lock").exists()
