"""Tests for `dummyindex/installer/repair.py` (Wave 3 — repair core).

Covers the four-root scanner (`InstalledCopy`), ownership-evidence gating
(stamp / legacy heading / dir-name-only), staleness + `--force-downgrade`,
orphaned-sibling reporting, symlink safety, per-copy error isolation, the
`_remove_skill_family` extraction shared with `uninstall()`, and dedupe
(including the home==project collision guard). End-to-end install wiring
lands in Wave 4 — these stay focused on `repair.py`/`uninstall.py`/`check.py`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dummyindex.context.output.bootstrap import UnbalancedMarkersError
from dummyindex.installer import install
from dummyindex.installer.common import PACKAGE_VERSION
from dummyindex.installer.repair import (
    InstalledCopy,
    dedupe,
    describe_plan,
    execute_repairs,
    plan_repairs,
    scan_installed_copies,
)
from dummyindex.installer.uninstall import _remove_skill_family
from tests.paths import FIXTURES_DIR

_LEGACY_SKILL_MD = (FIXTURES_DIR / "legacy_skill_md" / "SKILL.md").read_text(
    encoding="utf-8"
)


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    user_home = tmp_path / "home"
    project_root.mkdir()
    user_home.mkdir()
    return project_root, user_home


def _claude_dir(root: Path) -> Path:
    return root / ".claude" / "skills" / "dummyindex"


def _codex_dir(root: Path) -> Path:
    return root / ".agents" / "skills" / "dummyindex"


def _write_stamp(skill_dir: Path, version: str) -> None:
    """A proven copy: a rendered SKILL.md plus a `.dummyindex_version` stamp."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: dummyindex\ndescription: test\n---\nbody\n", encoding="utf-8"
    )
    (skill_dir / ".dummyindex_version").write_text(version, encoding="utf-8")


def _write_plain_dir(skill_dir: Path) -> None:
    """A dir-name match with neither a stamp nor the legacy heading."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: dummyindex\n---\nunrelated content, no ownership markers\n",
        encoding="utf-8",
    )


def _write_legacy_skill(skill_dir: Path) -> None:
    """A pre-portable-host install: legacy heading, no stamp file at all."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_LEGACY_SKILL_MD, encoding="utf-8")


# ----- scanner ----------------------------------------------------------------


@pytest.mark.unit
def test_scan_installed_copies_finds_all_four_roots_and_models_installed_copy(
    tmp_path: Path,
) -> None:
    project_root, user_home = _roots(tmp_path)
    _write_stamp(_claude_dir(project_root), "0.10.0")
    _write_stamp(_codex_dir(project_root), "0.11.0")
    _write_stamp(_claude_dir(user_home), "0.12.0")
    # user/codex is deliberately left absent.

    copies = scan_installed_copies(project_root, user_home=user_home)

    assert copies == (
        InstalledCopy(
            scope="project",
            host="claude",
            path=_claude_dir(project_root),
            stamp="0.10.0",
        ),
        InstalledCopy(
            scope="project",
            host="codex",
            path=_codex_dir(project_root),
            stamp="0.11.0",
        ),
        InstalledCopy(
            scope="user", host="claude", path=_claude_dir(user_home), stamp="0.12.0"
        ),
        InstalledCopy(
            scope="user", host="codex", path=_codex_dir(user_home), stamp=None
        ),
    )


# ----- ownership evidence gating ----------------------------------------------


@pytest.mark.unit
def test_stamped_copy_older_than_package_is_a_rewrite_candidate(tmp_path: Path) -> None:
    project_root, user_home = _roots(tmp_path)
    _write_stamp(_claude_dir(project_root), "0.10.0")

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude",),
        package_version="0.20.0",
    )

    assert len(plan.to_rewrite) == 1
    candidate = plan.to_rewrite[0]
    assert candidate.copy.path == _claude_dir(project_root)
    assert "older" in candidate.reason
    assert "hand-edits" in candidate.reason
    assert plan.to_report == ()


@pytest.mark.unit
def test_legacy_heading_without_stamp_is_always_a_rewrite_candidate(
    tmp_path: Path,
) -> None:
    project_root, user_home = _roots(tmp_path)
    _write_legacy_skill(_claude_dir(project_root))

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude",),
        package_version="0.20.0",
    )

    assert len(plan.to_rewrite) == 1
    assert "legacy" in plan.to_rewrite[0].reason.lower()
    assert "Codex host compatibility" in plan.to_rewrite[0].reason


@pytest.mark.unit
def test_dir_name_match_without_ownership_evidence_is_never_a_candidate(
    tmp_path: Path,
) -> None:
    project_root, user_home = _roots(tmp_path)
    _write_plain_dir(_claude_dir(project_root))

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude",),
        package_version="0.20.0",
    )

    assert plan.to_rewrite == ()
    assert len(plan.to_report) == 1
    report = plan.to_report[0]
    assert report.path == _claude_dir(project_root)
    assert "no ownership evidence" in report.reason


@pytest.mark.unit
def test_orphaned_sibling_is_reported_not_rewritten(tmp_path: Path) -> None:
    project_root, user_home = _roots(tmp_path)
    sibling_dir = project_root / ".claude" / "skills" / "dummyindex-plan"
    sibling_dir.mkdir(parents=True)
    (sibling_dir / "SKILL.md").write_text("orphaned sibling\n", encoding="utf-8")
    # The family's main dir (dummyindex/) is deliberately never created.

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude",),
        package_version="0.20.0",
    )

    assert plan.to_rewrite == ()
    orphan_reports = [r for r in plan.to_report if r.path == sibling_dir]
    assert len(orphan_reports) == 1
    assert "orphaned" in orphan_reports[0].reason
    assert "missing" in orphan_reports[0].reason
    assert sibling_dir.exists()  # reported, never touched
    assert (sibling_dir / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "orphaned sibling\n"


# ----- staleness / downgrade gating --------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stamp", "package_version", "force_downgrade", "expect_rewrite"),
    [
        ("0.10.0", "0.20.0", False, True),
        ("0.30.0", "0.20.0", False, False),
        ("0.30.0", "0.20.0", True, True),
        ("garbled", "0.20.0", False, False),
        ("garbled", "0.20.0", True, True),
        ("0.20.0", "0.20.0", False, False),
        ("0.20.0", "0.20.0", True, False),
    ],
    ids=[
        "older-rewrites",
        "newer-report-only",
        "newer-force-downgrade-rewrites",
        "unparseable-report-only",
        "unparseable-force-downgrade-rewrites",
        "equal-no-churn",
        "equal-force-downgrade-still-no-churn",
    ],
)
def test_staleness_gates_rewrite_unless_forced(
    tmp_path: Path,
    stamp: str,
    package_version: str,
    force_downgrade: bool,
    expect_rewrite: bool,
) -> None:
    project_root, user_home = _roots(tmp_path)
    _write_stamp(_claude_dir(project_root), stamp)

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude",),
        package_version=package_version,
        force_downgrade=force_downgrade,
    )

    assert bool(plan.to_rewrite) is expect_rewrite


@pytest.mark.unit
def test_current_stamp_copy_is_a_no_churn_negative_case(tmp_path: Path) -> None:
    project_root, user_home = _roots(tmp_path)
    _write_stamp(_claude_dir(project_root), "0.20.0")

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude",),
        package_version="0.20.0",
    )

    assert plan.to_rewrite == ()
    assert len(plan.to_report) == 1
    assert "already matches" in plan.to_report[0].reason


@pytest.mark.unit
def test_untargeted_scope_stale_copy_is_reported_and_left_byte_identical(
    tmp_path: Path,
) -> None:
    project_root, user_home = _roots(tmp_path)
    _write_stamp(_claude_dir(project_root), "0.10.0")
    before = (_claude_dir(project_root) / "SKILL.md").read_bytes()

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="user",  # this invocation targets user scope, not project
        selected_platforms=("claude",),
        package_version="0.20.0",
    )

    assert plan.to_rewrite == ()
    assert len(plan.to_report) == 1
    report = plan.to_report[0]
    assert report.path == _claude_dir(project_root)
    assert "outside this invocation" in report.reason
    assert report.remediation == (
        f"dummyindex install --platform claude --scope project --dir {project_root}"
    )

    result = execute_repairs(plan)

    assert result.repaired == ()
    assert (_claude_dir(project_root) / "SKILL.md").read_bytes() == before


# ----- symlink safety -----------------------------------------------------------


@pytest.mark.unit
def test_plan_refuses_symlinked_companion_and_reports_it(tmp_path: Path) -> None:
    project_root, user_home = _roots(tmp_path)
    skill_dir = _claude_dir(project_root)
    _write_stamp(skill_dir, "0.10.0")
    external = project_root / "external-agents"
    external.mkdir()
    (skill_dir / "agents").symlink_to(external, target_is_directory=True)

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude",),
        package_version="0.20.0",
    )

    assert plan.to_rewrite == ()
    reports = [r for r in plan.to_report if r.path == skill_dir]
    assert len(reports) == 1
    assert "symlink" in reports[0].reason
    assert (skill_dir / "agents").is_symlink()  # never removed or followed


@pytest.mark.unit
def test_execute_repairs_refuses_symlink_introduced_after_planning(
    tmp_path: Path,
) -> None:
    """Defense-in-depth: the executor re-checks immediately before writing."""
    project_root, user_home = _roots(tmp_path)
    skill_dir = _claude_dir(project_root)
    _write_stamp(skill_dir, "0.10.0")

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude",),
        package_version="0.20.0",
    )
    assert len(plan.to_rewrite) == 1  # clean at plan time

    external = project_root / "external-agents"
    external.mkdir()
    (skill_dir / "agents").symlink_to(external, target_is_directory=True)

    result = execute_repairs(plan)

    assert result.repaired == ()
    assert len(result.errors) == 1
    assert "symlink" in result.errors[0].message
    assert (skill_dir / "agents").is_symlink()


@pytest.mark.integration
def test_repair_and_dedupe_never_touch_codex_skills_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    sentinel_dir = fake_home / ".codex" / "skills" / "dummyindex"
    sentinel_dir.mkdir(parents=True)
    sentinel = sentinel_dir / "SKILL.md"
    sentinel.write_text("legacy community skill — never touched\n", encoding="utf-8")

    project_root = tmp_path / "project"
    project_root.mkdir()
    install(scope="user", skill_only=True, platform="both")
    install(scope="project", project_dir=project_root, skill_only=True, platform="both")

    plan = plan_repairs(
        project_root=project_root,
        user_home=fake_home,
        target_scope="project",
        selected_platforms=("claude", "codex"),
        package_version="9999.0.0",  # force every proven copy stale
    )
    execute_repairs(plan)
    dedupe("project", project_root=project_root, user_home=fake_home)

    assert sentinel.read_text(encoding="utf-8") == (
        "legacy community skill — never touched\n"
    )


# ----- per-copy error isolation --------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "make_exc",
    [
        lambda: OSError("disk went away"),
        lambda: UnbalancedMarkersError("hand-damaged markers"),
        lambda: ValueError(
            "dummyindex's managed Codex guidance needs 40000 bytes, but "
            "project_doc_max_bytes is 32768"
        ),
    ],
    ids=["oserror", "unbalanced-markers-error", "budget-exceeded-valueerror"],
)
def test_execute_repairs_isolates_one_failing_copy_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_exc,
) -> None:
    import dummyindex.installer.repair as repair_module

    project_root, user_home = _roots(tmp_path)
    _write_stamp(_claude_dir(project_root), "0.10.0")
    _write_stamp(_codex_dir(project_root), "0.10.0")

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude", "codex"),
        package_version="0.20.0",
    )
    assert len(plan.to_rewrite) == 2

    real_install_skill_family = repair_module._install_skill_family

    def _flaky(base: Path, host: str, src: Path) -> None:
        if host == "claude":
            raise make_exc()
        real_install_skill_family(base, host, src)

    monkeypatch.setattr(repair_module, "_install_skill_family", _flaky)

    result = execute_repairs(plan)

    assert len(result.repaired) == 1
    assert result.repaired[0].host == "codex"
    assert len(result.errors) == 1
    assert result.errors[0].copy.host == "claude"
    assert result.reported == plan.to_report
    err = capsys.readouterr().err
    assert err.count("repair skipped") == 1


# ----- `_remove_skill_family` extraction ----------------------------------------


@pytest.mark.integration
def test_remove_skill_family_removes_only_named_family_and_leaves_commands(
    tmp_path: Path,
) -> None:
    install(scope="project", project_dir=tmp_path, skill_only=True, platform="claude")
    skill_dir = _claude_dir(tmp_path)
    sibling_dir = tmp_path / ".claude" / "skills" / "dummyindex-plan"
    commands_file = tmp_path / ".claude" / "commands" / "tokens.md"
    assert skill_dir.exists()
    assert sibling_dir.exists()
    assert commands_file.exists()

    removed = _remove_skill_family(tmp_path, "claude", scope="project")

    assert not skill_dir.exists()
    assert not sibling_dir.exists()
    assert commands_file.exists()  # never touched by family removal
    assert str(skill_dir / "SKILL.md") in removed
    assert str(sibling_dir) in removed


# ----- duplicates + dedupe -------------------------------------------------------


@pytest.mark.integration
def test_duplicate_family_reported_with_both_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    project_root = tmp_path / "project"
    project_root.mkdir()

    install(scope="user", skill_only=True, platform="claude")
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )

    plan = plan_repairs(
        project_root=project_root,
        user_home=fake_home,
        target_scope="project",
        selected_platforms=("claude",),
    )

    assert len(plan.duplicates) == 1
    dup = plan.duplicates[0]
    assert dup.host == "claude"
    assert dup.user_copy.path == _claude_dir(fake_home)
    assert dup.project_copy.path == _claude_dir(project_root)


@pytest.mark.integration
def test_dedupe_removes_only_named_scope_and_leaves_the_other_and_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    project_root = tmp_path / "project"
    project_root.mkdir()

    install(scope="user", skill_only=True, platform="claude")
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )
    commands_file = project_root / ".claude" / "commands" / "tokens.md"
    assert commands_file.exists()

    result = dedupe("project", project_root=project_root, user_home=fake_home)

    assert not _claude_dir(project_root).exists()
    assert _claude_dir(fake_home).exists()  # the other scope survives
    assert commands_file.exists()  # dedupe never touches commands
    assert str(_claude_dir(project_root) / "SKILL.md") in result.removed
    assert result.errors == ()


@pytest.mark.integration
def test_home_equal_project_is_never_a_duplicate_and_dedupe_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    same_root = tmp_path / "home-and-project"
    same_root.mkdir()
    monkeypatch.setenv("HOME", str(same_root))

    install(scope="project", project_dir=same_root, skill_only=True, platform="claude")
    assert _claude_dir(same_root).exists()

    plan = plan_repairs(
        project_root=same_root,
        user_home=same_root,
        target_scope="project",
        selected_platforms=("claude",),
    )
    assert plan.duplicates == ()

    result = dedupe("project", project_root=same_root, user_home=same_root)

    assert result.removed == ()
    assert result.errors == ()
    assert _claude_dir(same_root).exists()  # never deleted


# ----- dedupe safety: per-family isolation, symlink preflight, fail-closed -------


@pytest.mark.unit
def test_dedupe_isolates_one_failing_family_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import dummyindex.installer.repair as repair_module

    project_root, user_home = _roots(tmp_path)
    _write_stamp(_claude_dir(project_root), "0.10.0")
    _write_stamp(_claude_dir(user_home), "0.10.0")
    _write_stamp(_codex_dir(project_root), "0.10.0")
    _write_stamp(_codex_dir(user_home), "0.10.0")

    real_remove_skill_family = repair_module._remove_skill_family

    def _flaky(base: Path, host: str, *, scope: str) -> list[str]:
        if host == "claude":
            raise OSError("disk went away")
        return real_remove_skill_family(base, host, scope=scope)

    monkeypatch.setattr(repair_module, "_remove_skill_family", _flaky)

    result = dedupe("project", project_root=project_root, user_home=user_home)

    assert len(result.errors) == 1
    assert result.errors[0].copy.host == "claude"
    assert result.errors[0].copy.path == _claude_dir(project_root)
    assert "disk went away" in result.errors[0].message
    assert (_claude_dir(project_root) / "SKILL.md").exists()  # failed family untouched
    assert str(_codex_dir(project_root) / "SKILL.md") in result.removed
    assert not _codex_dir(project_root).exists()  # the other duplicate still removed
    err = capsys.readouterr().err
    assert err.count("dedupe skipped") == 1


@pytest.mark.unit
def test_dedupe_refuses_symlinked_scope_root_and_reports_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project_root, user_home = _roots(tmp_path)
    skill_dir = _claude_dir(project_root)
    _write_stamp(skill_dir, "0.10.0")
    _write_stamp(_claude_dir(user_home), "0.10.0")
    external = project_root / "external-agents"
    external.mkdir()
    (skill_dir / "agents").symlink_to(external, target_is_directory=True)

    result = dedupe("project", project_root=project_root, user_home=user_home)

    assert result.removed == ()
    assert len(result.errors) == 1
    assert result.errors[0].copy.path == skill_dir
    assert "symlink" in result.errors[0].message
    assert skill_dir.exists()  # never removed through it
    assert (skill_dir / "agents").is_symlink()  # never followed or removed
    err = capsys.readouterr().err
    assert err.count("dedupe skipped") == 1


@pytest.mark.unit
def test_same_root_resolve_failure_fails_closed_and_dedupe_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    same_root = tmp_path / "home-and-project"
    same_root.mkdir()
    _write_stamp(_claude_dir(same_root), "0.10.0")

    real_resolve = Path.resolve

    def _flaky_resolve(self: Path, *args, **kwargs):
        if self == same_root:
            raise OSError("ELOOP: too many levels of symbolic links")
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", _flaky_resolve, raising=True)

    result = dedupe("project", project_root=same_root, user_home=same_root)

    assert result.removed == ()
    assert result.errors == ()
    assert _claude_dir(same_root).exists()  # never selected as a duplicate to remove


# ----- input validation + reporting ----------------------------------------------


@pytest.mark.unit
def test_plan_repairs_rejects_invalid_target_scope(tmp_path: Path) -> None:
    project_root, user_home = _roots(tmp_path)
    with pytest.raises(ValueError):
        plan_repairs(
            project_root=project_root,
            user_home=user_home,
            target_scope="bogus",
            selected_platforms=("claude",),
        )


@pytest.mark.unit
def test_dedupe_rejects_invalid_scope(tmp_path: Path) -> None:
    project_root, user_home = _roots(tmp_path)
    with pytest.raises(ValueError):
        dedupe("bogus", project_root=project_root, user_home=user_home)


@pytest.mark.unit
def test_describe_plan_prints_active_codex_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    project_root, user_home = _roots(tmp_path)

    # Codex selected -> the line always prints, even on an otherwise-empty
    # plan (see `test_describe_plan_prints_nothing_when_empty_and_claude_only`
    # for the suppressed, claude-only case).
    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude", "codex"),
    )

    lines = describe_plan(plan)
    assert any(str(user_home / ".codex") in line for line in lines)


@pytest.mark.unit
def test_describe_plan_prints_nothing_when_empty_and_claude_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan with no rewrite/report/duplicate findings and no Codex among
    the selected platforms has nothing to say — `describe_plan` prints
    nothing rather than a lone "active Codex home" line."""
    monkeypatch.delenv("CODEX_HOME", raising=False)
    project_root, user_home = _roots(tmp_path)

    plan = plan_repairs(
        project_root=project_root,
        user_home=user_home,
        target_scope="project",
        selected_platforms=("claude",),
    )

    assert plan.to_rewrite == ()
    assert plan.to_report == ()
    assert plan.duplicates == ()
    assert describe_plan(plan) == ()


# ================================================================================
# Wave 4 — `install()` wiring (integration): every plain `install()` run plans
# and executes a repair pass scoped to this invocation's selected platforms at
# its targeted scope root, prints the report, and honors `--dedupe` /
# `--force-downgrade`. These drive real `install()` calls end-to-end rather
# than calling `plan_repairs`/`execute_repairs`/`dedupe` directly (Wave 3,
# above, already covers those functions' own contracts exhaustively).
# ================================================================================


def _make_git_repo(target: Path) -> None:
    """Minimal git repo — enough for auto-init's `is_git_repo` check to fire."""
    target.mkdir(parents=True, exist_ok=True)
    (target / ".git").mkdir()
    (target / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")


def _stamp(skill_dir: Path) -> Path:
    return skill_dir / ".dummyindex_version"


# ----- repair matrix: platform isolation --------------------------------------


@pytest.mark.integration
def test_install_agents_only_rewrites_stale_project_copy_and_skips_claude(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="codex"
    )
    skill_dir = _codex_dir(project_root)
    _stamp(skill_dir).write_text("0.1.0", encoding="utf-8")

    install(
        scope="project", project_dir=project_root, skill_only=True, platform="codex"
    )

    assert _stamp(skill_dir).read_text(encoding="utf-8").strip() == PACKAGE_VERSION
    assert not (project_root / ".claude").exists()


@pytest.mark.integration
def test_install_claude_only_rewrites_stale_project_copy_and_skips_agents(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )
    skill_dir = _claude_dir(project_root)
    _stamp(skill_dir).write_text("0.1.0", encoding="utf-8")

    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )

    assert _stamp(skill_dir).read_text(encoding="utf-8").strip() == PACKAGE_VERSION
    assert not (project_root / ".agents").exists()


# ----- repair matrix: scope isolation + no-churn ------------------------------


@pytest.mark.integration
def test_install_reports_untargeted_scope_stale_copy_and_leaves_it_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    project_root = tmp_path / "project"

    # A stale copy at USER scope; this run targets PROJECT scope only.
    install(scope="user", skill_only=True, platform="claude")
    stale_dir = _claude_dir(fake_home)
    _stamp(stale_dir).write_text("0.1.0", encoding="utf-8")
    before = (stale_dir / "SKILL.md").read_bytes()
    before_stamp = _stamp(stale_dir).read_bytes()
    capsys.readouterr()

    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )

    assert (stale_dir / "SKILL.md").read_bytes() == before
    assert _stamp(stale_dir).read_bytes() == before_stamp
    out = capsys.readouterr().out
    assert "outside this invocation" in out
    assert "dummyindex install --platform claude --scope user" in out


@pytest.mark.integration
def test_install_self_heals_interrupted_install_missing_only_the_stamp(
    tmp_path: Path,
) -> None:
    """An install interrupted after SKILL.md but before `.dummyindex_version`
    (written last) leaves an existing-but-unprovable family dir at this
    invocation's own target scope×platform. `plan_repairs` never treats a
    bare dir-name match as a rewrite candidate, so without the direct-write
    loop's self-heal branch a rerun would leave it report-only forever. This
    asserts the rerun completes it instead."""
    project_root = tmp_path / "project"
    skill_dir = _claude_dir(project_root)
    _write_plain_dir(skill_dir)  # SKILL.md present, no stamp, no legacy heading
    assert not _stamp(skill_dir).exists()

    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )

    assert _stamp(skill_dir).exists()
    assert _stamp(skill_dir).read_text(encoding="utf-8").strip() == PACKAGE_VERSION
    rendered = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "unrelated content, no ownership markers" not in rendered


@pytest.mark.integration
def test_install_current_stamp_copy_stays_byte_identical(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )
    skill_dir = _claude_dir(project_root)
    before = (skill_dir / "SKILL.md").read_bytes()
    before_stamp = _stamp(skill_dir).read_bytes()

    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )

    assert (skill_dir / "SKILL.md").read_bytes() == before
    assert _stamp(skill_dir).read_bytes() == before_stamp


# ----- downgrade / unknown safety ---------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("bad_stamp", ["9999.0.0", "garbled"], ids=["newer", "unknown"])
def test_install_reports_downgrade_risk_and_leaves_bytes_unchanged(
    tmp_path: Path, bad_stamp: str
) -> None:
    project_root = tmp_path / "project"
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )
    skill_dir = _claude_dir(project_root)
    _stamp(skill_dir).write_text(bad_stamp, encoding="utf-8")
    before = (skill_dir / "SKILL.md").read_bytes()

    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )

    assert (skill_dir / "SKILL.md").read_bytes() == before
    assert _stamp(skill_dir).read_text(encoding="utf-8").strip() == bad_stamp


@pytest.mark.integration
@pytest.mark.parametrize("bad_stamp", ["9999.0.0", "garbled"], ids=["newer", "unknown"])
def test_install_force_downgrade_rewrites_newer_or_unknown_stamp(
    tmp_path: Path, bad_stamp: str
) -> None:
    project_root = tmp_path / "project"
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )
    skill_dir = _claude_dir(project_root)
    _stamp(skill_dir).write_text(bad_stamp, encoding="utf-8")

    install(
        scope="project",
        project_dir=project_root,
        skill_only=True,
        platform="claude",
        force_downgrade=True,
    )

    assert _stamp(skill_dir).read_text(encoding="utf-8").strip() == PACKAGE_VERSION


# ----- symlink safety, via the wiring -----------------------------------------


@pytest.mark.integration
def test_install_wiring_never_touches_legacy_codex_skills_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain `install()` run — no direct `plan_repairs`/`execute_repairs`/
    `dedupe` call — must still never discover or touch the legacy
    `~/.codex/skills` community location (dummyindex never wrote there)."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    sentinel_dir = fake_home / ".codex" / "skills" / "dummyindex"
    sentinel_dir.mkdir(parents=True)
    sentinel = sentinel_dir / "SKILL.md"
    sentinel.write_text("legacy community skill — never touched\n", encoding="utf-8")

    project_root = tmp_path / "project"
    install(scope="user", skill_only=True, platform="both")
    install(scope="project", project_dir=project_root, skill_only=True, platform="both")

    assert sentinel.read_text(encoding="utf-8") == (
        "legacy community skill — never touched\n"
    )


@pytest.mark.integration
def test_install_dedupe_flag_refuses_symlinked_duplicate_and_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    project_root = tmp_path / "project"

    install(scope="user", skill_only=True, platform="claude")
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )
    skill_dir = _claude_dir(project_root)
    external = project_root / "external-agents"
    external.mkdir()
    shutil.rmtree(skill_dir / "agents")  # a real install() already wrote this
    (skill_dir / "agents").symlink_to(external, target_is_directory=True)

    # Target THIS invocation at user scope — untouched by the project-side
    # symlink — while asking it to dedupe the PROJECT scope's duplicate. This
    # exercises `dedupe`'s own no-follow preflight from inside the wiring,
    # independent of `install()`'s separate pre-existing target-scope guard.
    # `project_dir` must still be passed: repair's `project_root` argument is
    # `project_dir or cwd` regardless of `scope`, never the install's own
    # `base` (which is `Path.home()` here).
    install(
        scope="user",
        project_dir=project_root,
        skill_only=True,
        platform="claude",
        dedupe="project",
    )

    err = capsys.readouterr().err
    assert "symlink" in err
    assert skill_dir.exists()
    assert (skill_dir / "agents").is_symlink()  # never followed or removed


# ----- duplicates + dedupe, via the wiring ------------------------------------


@pytest.mark.integration
def test_install_reports_duplicate_family_with_both_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    project_root = tmp_path / "project"

    install(scope="user", skill_only=True, platform="claude")
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )
    capsys.readouterr()

    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )

    out = capsys.readouterr().out
    assert str(_claude_dir(fake_home)) in out
    assert str(_claude_dir(project_root)) in out
    assert "--dedupe <user|project>" in out


@pytest.mark.integration
@pytest.mark.parametrize("dedupe_scope", ["project", "user"])
def test_install_dedupe_flag_removes_only_named_scope_and_preserves_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dedupe_scope: str
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    project_root = tmp_path / "project"

    install(scope="user", skill_only=True, platform="claude")
    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )
    commands_file = project_root / ".claude" / "commands" / "tokens.md"
    assert commands_file.exists()

    install(
        scope="project",
        project_dir=project_root,
        skill_only=True,
        platform="claude",
        dedupe=dedupe_scope,
    )

    if dedupe_scope == "project":
        assert not _claude_dir(project_root).exists()
        assert _claude_dir(fake_home).exists()
    else:
        assert not _claude_dir(fake_home).exists()
        assert _claude_dir(project_root).exists()
    assert commands_file.exists()  # dedupe never touches commands


@pytest.mark.integration
def test_install_dedupe_flag_only_removes_selected_platform_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--dedupe` is a stricter form of write and must obey the same
    platform×scope model as repair: with both claude AND codex families
    duplicated at user + project scope, `--platform claude --dedupe project`
    removes ONLY the project `.claude` family — the project `.agents` family
    survives byte-identical and stays in the (unfiltered) duplicate report."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    project_root = tmp_path / "project"

    install(scope="user", skill_only=True, platform="both")
    install(scope="project", project_dir=project_root, skill_only=True, platform="both")
    codex_before = (_codex_dir(project_root) / "SKILL.md").read_bytes()
    capsys.readouterr()

    install(
        scope="project",
        project_dir=project_root,
        skill_only=True,
        platform="claude",
        dedupe="project",
    )

    out = capsys.readouterr().out
    # Only the claude family was removed at project scope.
    assert not _claude_dir(project_root).exists()
    assert _claude_dir(fake_home).exists()
    # The codex family is untouched at both scopes, byte-identical.
    assert _codex_dir(project_root).exists()
    assert _codex_dir(fake_home).exists()
    assert (_codex_dir(project_root) / "SKILL.md").read_bytes() == codex_before
    # The duplicate REPORT stays informational/unfiltered: codex is still
    # listed even though this invocation never selected it for removal.
    assert str(_codex_dir(fake_home)) in out
    assert str(_codex_dir(project_root)) in out
    assert "--dedupe <user|project>" in out


@pytest.mark.integration
def test_install_dedupe_flag_preserves_project_guidance_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    repo = tmp_path / "repo"
    _make_git_repo(repo)

    install(scope="user", skill_only=True, platform="claude")
    install(scope="project", project_dir=repo, platform="claude")  # auto-init runs

    claude_md = repo / ".claude" / "CLAUDE.md"
    assert claude_md.exists()
    guidance_before = claude_md.read_text(encoding="utf-8")
    commands_file = repo / ".claude" / "commands" / "tokens.md"
    assert commands_file.exists()

    install(
        scope="project",
        project_dir=repo,
        skill_only=True,
        platform="claude",
        dedupe="project",
    )

    assert not _claude_dir(repo).exists()
    assert _claude_dir(fake_home).exists()
    assert commands_file.exists()
    assert claude_md.read_text(encoding="utf-8") == guidance_before


@pytest.mark.integration
def test_install_dedupe_flag_is_noop_when_home_equals_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    same_root = tmp_path / "home-and-project"
    same_root.mkdir()
    monkeypatch.setenv("HOME", str(same_root))

    install(scope="project", project_dir=same_root, skill_only=True, platform="claude")
    assert _claude_dir(same_root).exists()

    install(
        scope="project",
        project_dir=same_root,
        skill_only=True,
        platform="claude",
        dedupe="project",
    )

    assert _claude_dir(same_root).exists()  # never deleted


# ----- per-copy error isolation, via the wiring -------------------------------


@pytest.mark.integration
@pytest.mark.parametrize(
    "make_exc",
    [
        lambda: UnbalancedMarkersError("hand-damaged markers"),
        lambda: ValueError(
            "dummyindex's managed Codex guidance needs 40000 bytes, but "
            "project_doc_max_bytes is 32768"
        ),
    ],
    ids=["unbalanced-markers-error", "budget-exceeded-valueerror"],
)
def test_install_wiring_isolates_one_failing_repair_and_does_not_abort_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    make_exc,
) -> None:
    import dummyindex.installer.repair as repair_module

    project_root = tmp_path / "project"
    install(scope="project", project_dir=project_root, skill_only=True, platform="both")
    claude_stamp = _stamp(_claude_dir(project_root))
    claude_stamp.write_text("0.1.0", encoding="utf-8")
    codex_stamp = _stamp(_codex_dir(project_root))
    codex_stamp.write_text("0.1.0", encoding="utf-8")

    real_install_skill_family = repair_module._install_skill_family

    def _flaky(base: Path, host: str, src: Path) -> None:
        if host == "claude":
            raise make_exc()
        real_install_skill_family(base, host, src)

    monkeypatch.setattr(repair_module, "_install_skill_family", _flaky)

    install(scope="project", project_dir=project_root, skill_only=True, platform="both")

    err = capsys.readouterr().err
    assert err.count("repair skipped") == 1
    assert claude_stamp.read_text(encoding="utf-8").strip() == "0.1.0"  # untouched
    assert codex_stamp.read_text(encoding="utf-8").strip() == PACKAGE_VERSION


# ----- reporting ---------------------------------------------------------------


@pytest.mark.integration
def test_install_prints_active_codex_home_in_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Codex among the selected platforms is always a real report — the
    active Codex home line prints even on a fresh install with nothing
    stale (see `test_install_claude_only_fresh_install_prints_no_repair_report`
    for the claude-only, nothing-to-say negative case)."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    project_root = tmp_path / "project"

    install(scope="project", project_dir=project_root, skill_only=True, platform="both")

    out = capsys.readouterr().out
    assert f"active Codex home: {fake_home / '.codex'}" in out


@pytest.mark.integration
def test_install_claude_only_fresh_install_prints_no_repair_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clean Claude-only install with nothing to repair, report, or dedupe
    prints no repair-report noise at all — Codex isn't involved and there is
    nothing to say."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    project_root = tmp_path / "project"

    install(
        scope="project", project_dir=project_root, skill_only=True, platform="claude"
    )

    out = capsys.readouterr().out
    assert "repair report" not in out
    assert "active Codex home" not in out
