"""Tests for wiring `installer/link.py`'s primitives into `install()`.

Covers the preflight admission (OURS_HEALTHY/OURS_DANGLING/MATERIALIZED family dirs
pass, FOREIGN and companion-dir symlinks keep the refusal), the never-write-through
write path, MISSING-state deferral, AUTO/LINK/COPY dispatch after `execute_repairs`,
sibling stamping and backfill, and the "never neither" invariant: every run ends with
exactly one of {8 links, 8 real Claude dirs}. Primitives: test_install_link_primitives.py.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path, PurePath

import pytest

from dummyindex.installer import LinkMode, install, uninstall
from dummyindex.installer.common import _SIBLING_SKILLS, PACKAGE_VERSION
from dummyindex.installer.install import (
    _agents_family_stamp_state,
    _backfill_sibling_stamps,
    _claude_narrowing_link_gate,
    _install_skill_family,
    _link_state_report_line,
)
from dummyindex.installer.link import (
    FamilyLinkClassification,
    FamilyLinkState,
    classify_family_link,
    create_family_links,
    relative_link_value,
)
from dummyindex.installer.link.orchestrate import _probe_symlink_capability
from dummyindex.installer.repair import dedupe

# The families, derived from the constant (never a `dummyindex*` glob —
# that would also catch equip's `dummyindex-verify`).
FAMILIES = ("dummyindex", *(label for _sub_name, label in _SIBLING_SKILLS))


# --- shared fixtures


def _require_real_symlinks(tmp_path: Path) -> None:
    """Skip the calling test when this environment cannot create symlinks.

    Only for tests that create (or expect `install()` to create) a REAL symlink;
    pure-logic and MATERIALIZED-only tests are never guarded.
    """
    probe = tmp_path / ".test-install-link-capability-probe"
    target = tmp_path / ".test-install-link-capability-target"
    target.mkdir(exist_ok=True)
    try:
        probe.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("this environment cannot create symlinks")
        return
    probe.unlink()


def _write_family_dir(
    base: Path, *, name: str, version: str | None = PACKAGE_VERSION
) -> Path:
    from dummyindex.installer.ownership import sync_family

    body = f"---\nname: {name}\ndescription: test\n---\nbody\n"
    sync_family(
        base,
        {"SKILL.md": body},
        family=name,
        version=version or PACKAGE_VERSION,
        force_downgrade=True,
    )
    if version is None:
        (base / ".dummyindex_version").unlink()
    return base


def _seed_agents_family(
    project_root: Path, family: str = "dummyindex", *, version: str = PACKAGE_VERSION
) -> Path:
    """A proven, stamped real `.agents/skills/<family>` — the link target."""
    return _write_family_dir(
        project_root / ".agents" / "skills" / family, name=family, version=version
    )


def _seed_claude_family_real(
    project_root: Path, family: str = "dummyindex", *, version: str = PACKAGE_VERSION
) -> Path:
    """A proven, stamped REAL directory on the Claude side (NOT_A_LINK)."""
    return _write_family_dir(
        project_root / ".claude" / "skills" / family, name=family, version=version
    )


def _seed_all_agents_families(
    project_root: Path, *, version: str = PACKAGE_VERSION
) -> None:
    for family in FAMILIES:
        _seed_agents_family(project_root, family, version=version)


def _seed_all_claude_families_real(
    project_root: Path, *, version: str = PACKAGE_VERSION
) -> None:
    for family in FAMILIES:
        _seed_claude_family_real(project_root, family, version=version)


def _seed_realistic_claude_layout(
    project_root: Path, *, version: str = PACKAGE_VERSION
) -> None:
    """Main stamped, every sibling REAL and UNSTAMPED: what older releases shipped,
    when `_install_skill_family` stamped only main. The realistic migration seed;
    `_seed_all_claude_families_real` stamps every sibling."""
    _seed_claude_family_real(project_root, "dummyindex", version=version)
    for _sub_name, label in _SIBLING_SKILLS:
        _seed_claude_family_real(project_root, label, version=None)


def _seed_realistic_agents_layout(
    project_root: Path, *, version: str = PACKAGE_VERSION
) -> None:
    """Same realistic shape as `_seed_realistic_claude_layout`, on the
    `.agents` side: main stamped, every sibling real and UNSTAMPED."""
    _seed_agents_family(project_root, "dummyindex", version=version)
    for _sub_name, label in _SIBLING_SKILLS:
        _seed_agents_family(project_root, label, version=None)


def _claude_family_dir(project_root: Path, family: str = "dummyindex") -> Path:
    return project_root / ".claude" / "skills" / family


def _agents_family_dir(project_root: Path, family: str = "dummyindex") -> Path:
    return project_root / ".agents" / "skills" / family


def _seed_dangling_claude_family(
    project_root: Path, family: str = "dummyindex"
) -> None:
    """One family linked via `create_family_links`, then its `.agents` target
    removed — the crash-recovery/heal state `OURS_DANGLING`."""
    _seed_agents_family(project_root, family)
    result = create_family_links(project_root)
    assert not result.errors, result.errors
    assert _claude_family_dir(project_root, family).is_symlink()
    _remove_tree(_agents_family_dir(project_root, family))


def _remove_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path)


def _seed_materialized_claude_family(
    project_root: Path, family: str = "dummyindex"
) -> None:
    """A regular file at the family-dir slot whose content is the exact link
    value — the `core.symlinks=false` Windows-checkout shape."""
    family_dir = _claude_family_dir(project_root, family)
    family_dir.parent.mkdir(parents=True, exist_ok=True)
    family_dir.write_text(relative_link_value(family), encoding="utf-8")


def _seed_foreign_claude_family(project_root: Path, family: str = "dummyindex") -> Path:
    """A symlink at the family-dir slot pointing somewhere unrelated —
    classifies FOREIGN (wrong value, does not resolve to the real family)."""
    target = project_root / "external-foreign-target"
    target.mkdir(parents=True, exist_ok=True)
    (target / "keep.txt").write_text("do not touch\n", encoding="utf-8")
    family_dir = _claude_family_dir(project_root, family)
    family_dir.parent.mkdir(parents=True, exist_ok=True)
    family_dir.symlink_to(target, target_is_directory=True)
    return target


def _bump_major(version: str) -> str:
    parts = [int(p) for p in version.strip().split(".")]
    parts[0] += 1
    return ".".join(str(p) for p in parts)


# --- unit tests


@pytest.mark.unit
def test_install_skill_family_raises_on_symlinked_family_dir(tmp_path: Path) -> None:
    """Never write through a family-dir symlink, even an OURS_HEALTHY one: link
    mode replaces links via the rename dance."""
    _require_real_symlinks(tmp_path)
    _seed_agents_family(tmp_path)
    result = create_family_links(tmp_path)
    assert not result.errors, result.errors
    src = tmp_path / "skill-src.md"
    src.write_text(
        "---\nname: dummyindex\ndescription: t\n---\nbody\n", encoding="utf-8"
    )

    with pytest.raises(OSError):
        _install_skill_family(tmp_path, "claude", src)


@pytest.mark.unit
def test_install_skill_family_raises_on_materialized_family_dir(tmp_path: Path) -> None:
    """Nor through a MATERIALIZED file in the family-dir slot, where
    `mkdir(exist_ok=True)` would raise an uncaught `FileExistsError`."""
    _seed_materialized_claude_family(tmp_path)
    src = tmp_path / "skill-src.md"
    src.write_text(
        "---\nname: dummyindex\ndescription: t\n---\nbody\n", encoding="utf-8"
    )

    with pytest.raises(OSError):
        _install_skill_family(tmp_path, "claude", src)


@pytest.mark.unit
def test_link_state_report_line_materialized_names_core_symlinks_remediation(
    tmp_path: Path,
) -> None:
    classification = FamilyLinkClassification(
        family="dummyindex",
        path=tmp_path / ".claude" / "skills" / "dummyindex",
        state=FamilyLinkState.MATERIALIZED,
        detail="regular file content matches the link value exactly",
    )

    line = _link_state_report_line(classification, base=tmp_path, scope="project")

    assert "materialized link placeholder" in line
    assert "core.symlinks" in line
    assert str(classification.path) in line


@pytest.mark.unit
def test_link_state_report_line_dangling_names_relink_remediation(
    tmp_path: Path,
) -> None:
    classification = FamilyLinkClassification(
        family="dummyindex",
        path=tmp_path / ".claude" / "skills" / "dummyindex",
        state=FamilyLinkState.OURS_DANGLING,
        detail="link value matches and the target is confirmed absent",
    )

    line = _link_state_report_line(classification, base=tmp_path, scope="user")

    assert "dangling dummyindex-owned symlink" in line
    assert "--scope user" in line


@pytest.mark.unit
def test_agents_family_stamp_state_matrix(tmp_path: Path) -> None:
    assert _agents_family_stamp_state(tmp_path) == "missing"

    _seed_agents_family(tmp_path, version=PACKAGE_VERSION)
    assert _agents_family_stamp_state(tmp_path) == "equal"

    _seed_agents_family(tmp_path, version="0.0.0")
    assert _agents_family_stamp_state(tmp_path) == "older"

    _seed_agents_family(tmp_path, version=_bump_major(PACKAGE_VERSION))
    assert _agents_family_stamp_state(tmp_path) == "newer"

    _seed_agents_family(tmp_path, version="not-a-version")
    assert _agents_family_stamp_state(tmp_path) == "unknown"


@pytest.mark.unit
def test_claude_narrowing_link_gate_equal_stamp_permits_every_mode(
    tmp_path: Path,
) -> None:
    _seed_agents_family(tmp_path, version=PACKAGE_VERSION)

    assert _claude_narrowing_link_gate(
        tmp_path, link_mode=LinkMode.AUTO, force_downgrade=False
    )
    assert _claude_narrowing_link_gate(
        tmp_path, link_mode=LinkMode.LINK, force_downgrade=False
    )


@pytest.mark.unit
def test_claude_narrowing_link_gate_auto_falls_back_without_exiting(
    tmp_path: Path,
) -> None:
    # No `.agents` family at all.
    assert not _claude_narrowing_link_gate(
        tmp_path, link_mode=LinkMode.AUTO, force_downgrade=False
    )


@pytest.mark.unit
def test_claude_narrowing_link_gate_strict_link_exits_naming_platform_both(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        _claude_narrowing_link_gate(
            tmp_path, link_mode=LinkMode.LINK, force_downgrade=False
        )

    assert exc.value.code == 1
    assert "--platform both" in capsys.readouterr().err


@pytest.mark.unit
def test_claude_narrowing_link_gate_strict_link_newer_stamp_names_force_downgrade(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_agents_family(tmp_path, version=_bump_major(PACKAGE_VERSION))

    with pytest.raises(SystemExit) as exc:
        _claude_narrowing_link_gate(
            tmp_path, link_mode=LinkMode.LINK, force_downgrade=False
        )

    assert exc.value.code == 1
    assert "--force-downgrade" in capsys.readouterr().err


@pytest.mark.unit
def test_claude_narrowing_link_gate_force_downgrade_bypasses_newer_stamp(
    tmp_path: Path,
) -> None:
    _seed_agents_family(tmp_path, version=_bump_major(PACKAGE_VERSION))

    assert _claude_narrowing_link_gate(
        tmp_path, link_mode=LinkMode.LINK, force_downgrade=True
    )


# --- the preflight admission


@pytest.mark.integration
@pytest.mark.parametrize("link_mode", [LinkMode.AUTO, LinkMode.LINK, LinkMode.COPY])
def test_preflight_admits_ours_healthy_family_in_every_link_mode(
    tmp_path: Path, link_mode: LinkMode
) -> None:
    """OURS_HEALTHY never trips the symlink refusal, in ANY LinkMode."""
    _require_real_symlinks(tmp_path)
    _seed_all_agents_families(tmp_path)
    result = create_family_links(tmp_path)
    assert not result.errors, result.errors

    # Must not raise SystemExit.
    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="both",
        link_mode=link_mode,
    )


@pytest.mark.integration
@pytest.mark.parametrize("link_mode", [LinkMode.AUTO, LinkMode.LINK, LinkMode.COPY])
def test_preflight_admits_ours_dangling_family_in_every_link_mode(
    tmp_path: Path, link_mode: LinkMode
) -> None:
    _require_real_symlinks(tmp_path)
    _seed_dangling_claude_family(tmp_path)

    # `--platform both` keeps the claude narrowing's stamp gate (tested below) out.
    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="both",
        link_mode=link_mode,
    )


@pytest.mark.integration
@pytest.mark.parametrize("link_mode", [LinkMode.AUTO, LinkMode.LINK, LinkMode.COPY])
def test_preflight_admits_materialized_family_in_every_link_mode(
    tmp_path: Path, link_mode: LinkMode
) -> None:
    _require_real_symlinks(tmp_path)
    _seed_materialized_claude_family(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="both",
        link_mode=link_mode,
    )


@pytest.mark.integration
def test_preflight_still_refuses_foreign_claude_family_byte_for_byte(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """FOREIGN keeps the exact existing refusal message."""
    _require_real_symlinks(tmp_path)
    foreign_target = _seed_foreign_claude_family(tmp_path)

    with pytest.raises(SystemExit) as exc:
        install(
            scope="project",
            project_dir=tmp_path,
            skill_only=True,
            platform="both",
        )

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "error: refusing to install through managed directory symlink" in err
    assert "(pass --platform agents to skip the claude side)" in err
    assert (foreign_target / "keep.txt").read_text(encoding="utf-8") == "do not touch\n"


@pytest.mark.integration
def test_preflight_still_refuses_deeper_companion_symlink_under_real_family(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A symlinked COMPANION subdir (`agents/`) under a real family is still
    refused: the admission applies only to the top-level family dir."""
    _require_real_symlinks(tmp_path)
    _seed_claude_family_real(tmp_path)
    external = tmp_path / "external-companion"
    external.mkdir()
    (_claude_family_dir(tmp_path) / "agents").symlink_to(
        external, target_is_directory=True
    )

    with pytest.raises(SystemExit) as exc:
        install(
            scope="project",
            project_dir=tmp_path,
            skill_only=True,
            platform="both",
        )

    assert exc.value.code == 1
    assert (
        "error: refusing to install through managed directory symlink"
        in capsys.readouterr().err
    )


# --- direct-write loop: no crash on OURS_DANGLING / MATERIALIZED


@pytest.mark.integration
def test_copy_mode_reports_dangling_family_instead_of_crashing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _require_real_symlinks(tmp_path)
    _seed_dangling_claude_family(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="claude",
        link_mode=LinkMode.COPY,
    )

    out = capsys.readouterr().out
    assert "dangling dummyindex-owned symlink" in out
    # Never healed under --copy: still a dangling link, not a real directory.
    assert _claude_family_dir(tmp_path).is_symlink()


@pytest.mark.integration
def test_copy_mode_reports_materialized_family_instead_of_crashing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_materialized_claude_family(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="claude",
        link_mode=LinkMode.COPY,
    )

    out = capsys.readouterr().out
    assert "materialized link placeholder" in out
    assert not _claude_family_dir(tmp_path).is_dir()
    assert not _claude_family_dir(tmp_path).is_symlink()


@pytest.mark.integration
def test_auto_mode_heals_dangling_family_via_create_family_links(
    tmp_path: Path,
) -> None:
    _require_real_symlinks(tmp_path)
    _seed_dangling_claude_family(tmp_path)
    # Re-seed the `.agents` target so there is something to heal onto.
    _seed_agents_family(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="claude",
        link_mode=LinkMode.AUTO,
    )

    classification = classify_family_link(_claude_family_dir(tmp_path), tmp_path)
    assert classification.state is FamilyLinkState.OURS_HEALTHY


@pytest.mark.integration
def test_auto_mode_replaces_materialized_placeholder(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)
    _seed_materialized_claude_family(tmp_path)
    _seed_agents_family(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="claude",
        link_mode=LinkMode.AUTO,
    )

    assert _claude_family_dir(tmp_path).is_symlink()
    classification = classify_family_link(_claude_family_dir(tmp_path), tmp_path)
    assert classification.state is FamilyLinkState.OURS_HEALTHY


# --- the AUTO matrix + forced migration


@pytest.mark.integration
def test_flagless_forced_migration_of_duplicated_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Realistic duplicated layout: main stamped, siblings real and UNSTAMPED on both
    trees. `create_family_links` needs a stamp to replace a real dir, so a flagless
    install backfills sibling stamps, links every family with one `migrated ->` line
    + hand-edits caveat each, and a rerun is a noop."""
    _require_real_symlinks(tmp_path)
    _seed_realistic_claude_layout(tmp_path)
    _seed_realistic_agents_layout(tmp_path)

    install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    out = capsys.readouterr().out
    assert out.count("claude skill migrated") == len(FAMILIES)
    assert out.count(
        "pristine installed files replaced by one shared skill reference"
    ) == len(FAMILIES)

    links = 0
    real_remaining = 0
    for family in FAMILIES:
        claude_dir = _claude_family_dir(tmp_path, family)
        if claude_dir.is_symlink():
            links += 1
            readlink_parts = PurePath(os.readlink(claude_dir)).parts
            assert readlink_parts == PurePath(f"../../.agents/skills/{family}").parts, (
                family
            )
            assert (
                claude_dir.resolve() == _agents_family_dir(tmp_path, family).resolve()
            )
        elif claude_dir.is_dir():
            real_remaining += 1
    assert links == len(FAMILIES), "not every family converted to a link"
    assert real_remaining == 0, "a sibling stayed a permanently duplicated real dir"

    # Each .agents sibling carries the MAIN's own pre-repair stamp (here
    # PACKAGE_VERSION), so its Claude link classifies OURS_HEALTHY, not FOREIGN.
    for family in FAMILIES:
        stamp = _agents_family_dir(tmp_path, family) / ".dummyindex_version"
        assert stamp.read_text(encoding="utf-8").strip() == PACKAGE_VERSION, family
        classification = classify_family_link(
            _claude_family_dir(tmp_path, family), tmp_path
        )
        assert classification.state is FamilyLinkState.OURS_HEALTHY, family

    # Idempotent: a second flagless run is a pure 0-created/0-replaced noop.
    install(scope="project", project_dir=tmp_path, skill_only=True)
    second_out = capsys.readouterr().out
    assert "claude skill migrated" not in second_out
    assert "claude skill linked" not in second_out


@pytest.mark.integration
def test_flagless_claude_only_layout_migrates_to_universal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Realistic claude-only layout (main stamped, siblings real and unstamped, no
    `.agents`): a flagless install writes `.agents`, links EVERY `.claude` family,
    not just main, and writes AGENTS.md."""
    _require_real_symlinks(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (repo / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _seed_realistic_claude_layout(repo)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    install(scope="project", project_dir=repo)  # flagless, auto-init runs

    assert (_agents_family_dir(repo) / "SKILL.md").exists()
    assert (repo / "AGENTS.md").exists()

    links = 0
    real_remaining = 0
    for family in FAMILIES:
        claude_dir = _claude_family_dir(repo, family)
        if claude_dir.is_symlink():
            links += 1
        elif claude_dir.is_dir():
            real_remaining += 1
    assert links == len(FAMILIES), "not every family converted to a link"
    assert real_remaining == 0, "a sibling stayed a permanently duplicated real dir"


@pytest.mark.integration
def test_platform_claude_narrowing_links_to_existing_current_agents_family(
    tmp_path: Path,
) -> None:
    _require_real_symlinks(tmp_path)
    _seed_all_claude_families_real(tmp_path)
    _seed_all_agents_families(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="claude",
        link_mode=LinkMode.AUTO,
    )

    assert _claude_family_dir(tmp_path).is_symlink()


@pytest.mark.integration
def test_platform_claude_prepares_shared_family_when_absent(tmp_path: Path) -> None:
    """Claude-only AUTO prepares its canonical dependency before linking."""
    _require_real_symlinks(tmp_path)
    _seed_claude_family_real(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="claude",
        link_mode=LinkMode.AUTO,
    )

    assert _claude_family_dir(tmp_path).is_symlink()
    assert _claude_family_dir(tmp_path).resolve() == _agents_family_dir(tmp_path)
    assert (_agents_family_dir(tmp_path) / "SKILL.md").exists()


@pytest.mark.integration
def test_strict_link_platform_claude_prepares_shared_family_before_link_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    from dummyindex.installer.link import LinkInstallResult

    module = importlib.import_module("dummyindex.installer.install")
    calls = []

    def capture(base, **kwargs):
        assert (_agents_family_dir(base) / "SKILL.md").is_file()
        calls.append(kwargs["link_mode"])
        return LinkInstallResult(LinkMode.LINK, None, False, ())

    monkeypatch.setattr(module, "run_link_install", capture)
    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="claude",
        link_mode=LinkMode.LINK,
    )
    assert calls == [LinkMode.LINK]


@pytest.mark.integration
def test_strict_link_platform_claude_exits_when_agents_stamp_newer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_claude_family_real(tmp_path)
    _seed_agents_family(tmp_path, version=_bump_major(PACKAGE_VERSION))

    with pytest.raises(SystemExit) as exc:
        install(
            scope="project",
            project_dir=tmp_path,
            skill_only=True,
            platform="claude",
            link_mode=LinkMode.LINK,
        )

    assert exc.value.code == 1
    assert "--force-downgrade" in capsys.readouterr().err
    assert not _claude_family_dir(tmp_path).is_symlink()


@pytest.mark.integration
def test_strict_link_platform_claude_force_downgrade_links_despite_newer_stamp(
    tmp_path: Path,
) -> None:
    _require_real_symlinks(tmp_path)
    _seed_claude_family_real(tmp_path)
    _seed_agents_family(tmp_path, version=_bump_major(PACKAGE_VERSION))

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="claude",
        link_mode=LinkMode.LINK,
        force_downgrade=True,
    )

    assert _claude_family_dir(tmp_path).is_symlink()


@pytest.mark.integration
def test_platform_agents_never_touches_claude_side(tmp_path: Path) -> None:
    """AUTO + `--platform agents` never touches `.claude/**`: a duplicated layout is
    left for `plan_repairs` to report, and the link dispatch never runs."""
    _seed_all_claude_families_real(tmp_path)
    _seed_all_agents_families(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="codex",
        link_mode=LinkMode.AUTO,
    )

    for family in FAMILIES:
        claude_dir = _claude_family_dir(tmp_path, family)
        assert claude_dir.is_dir(), family
        assert not claude_dir.is_symlink(), family


# --- --copy characterization


@pytest.mark.integration
def test_copy_mode_never_calls_create_family_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--copy` NEVER calls `create_family_links` (spy via the DI seam) and
    leaves an existing linked layout as-is."""
    _require_real_symlinks(tmp_path)
    _seed_all_agents_families(tmp_path)
    seed_result = create_family_links(tmp_path)
    assert not seed_result.errors, seed_result.errors
    assert _claude_family_dir(tmp_path).is_symlink()

    import dummyindex.installer.link as link_module

    calls: list[object] = []
    real_create_family_links = link_module.create_family_links

    def _spy(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return real_create_family_links(*args, **kwargs)

    monkeypatch.setattr(link_module, "create_family_links", _spy)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="both",
        link_mode=LinkMode.COPY,
    )

    assert calls == []
    assert _claude_family_dir(tmp_path).is_symlink()


@pytest.mark.integration
def test_copy_mode_leaves_duplicated_layout_unconverted(tmp_path: Path) -> None:
    """`--copy` regression: a duplicated layout (both real, equal stamps) is
    left exactly as today — no conversion to links."""
    _seed_all_claude_families_real(tmp_path)
    _seed_all_agents_families(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="both",
        link_mode=LinkMode.COPY,
    )

    for family in FAMILIES:
        claude_dir = _claude_family_dir(tmp_path, family)
        assert claude_dir.is_dir(), family
        assert not claude_dir.is_symlink(), family


# --- side surfaces still work under link mode


@pytest.mark.integration
def test_link_mode_still_writes_tokens_command(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)

    install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    assert (tmp_path / ".claude" / "commands" / "tokens.md").is_file()
    assert _claude_family_dir(tmp_path).is_symlink()


@pytest.mark.integration
def test_link_mode_still_registers_claude_md_at_user_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_real_symlinks(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    install(scope="user", skill_only=True)  # flagless

    claude_md = fake_home / ".claude" / "CLAUDE.md"
    assert claude_md.exists()
    assert "**dummyindex** (" in claude_md.read_text(encoding="utf-8")
    assert (fake_home / ".claude" / "skills" / "dummyindex").is_symlink()


@pytest.mark.integration
def test_link_mode_still_runs_auto_init_hooks_and_agents_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (repo / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n", encoding="utf-8"
    )
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    _require_real_symlinks(repo)

    install(scope="project", project_dir=repo)  # flagless

    assert (repo / ".context").is_dir()
    assert (repo / ".claude" / "CLAUDE.md").exists()
    settings = repo / ".claude" / "settings.json"
    assert settings.exists()
    assert "DUMMYINDEX_AUTO_REFRESH" in settings.read_text(encoding="utf-8")
    assert (repo / "AGENTS.md").exists()
    assert _claude_family_dir(repo).is_symlink()


# --- MISSING-state deferral
# Regression guard: a MISSING family dir once got an eager real write (main-only
# stamp), so `create_family_links` refused every sibling. The write now waits
# until the run knows whether it links.


@pytest.mark.integration
def test_flagless_fresh_install_all_8_families_become_claude_symlinks(
    tmp_path: Path,
) -> None:
    """A fresh flagless project install must
    leave every enumerated family (main + `_SIBLING_SKILLS`, derived from
    the constant) as a Claude-side symlink to `../../.agents/skills/<family>`."""
    _require_real_symlinks(tmp_path)

    install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    for family in FAMILIES:
        claude_dir = _claude_family_dir(tmp_path, family)
        assert claude_dir.is_symlink(), family
        assert not claude_dir.is_dir() or claude_dir.is_symlink(), family
        readlink_parts = PurePath(os.readlink(claude_dir)).parts
        assert readlink_parts == PurePath(f"../../.agents/skills/{family}").parts, (
            family
        )
        assert claude_dir.resolve() == _agents_family_dir(tmp_path, family).resolve()

    stamp = _agents_family_dir(tmp_path) / ".dummyindex_version"
    assert stamp.read_text(encoding="utf-8").strip() == PACKAGE_VERSION


@pytest.mark.integration
def test_auto_capability_fallback_writes_real_claude_dirs_never_neither(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed AUTO capability pre-probe (e.g. Windows without Developer Mode) falls
    back to copy for the WHOLE run: every family is a REAL Claude dir ("never neither").

    The fake goes through `run_link_install`: `install()` has no `symlink_fn` seam and
    `os.symlink` is a default bound at import time. `importlib` reaches the submodule,
    since the package's `install` attribute is the function."""
    import importlib

    from dummyindex.installer.link import run_link_install as real_run_link_install

    install_module = importlib.import_module("dummyindex.installer.install")

    def _raising_symlink_fn(*_a: object, **_k: object) -> None:
        raise OSError(errno.EPERM, "Operation not permitted")

    def _fake_run_link_install(*args: object, **kwargs: object) -> object:
        kwargs["symlink_fn"] = _raising_symlink_fn
        return real_run_link_install(*args, **kwargs)

    monkeypatch.setattr(install_module, "run_link_install", _fake_run_link_install)

    install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    for family in FAMILIES:
        claude_dir = _claude_family_dir(tmp_path, family)
        assert claude_dir.is_dir(), family
        assert not claude_dir.is_symlink(), family
        agents_dir = _agents_family_dir(tmp_path, family)
        assert agents_dir.is_dir(), family
        assert not agents_dir.is_symlink(), family


@pytest.mark.integration
def test_already_real_proven_claude_family_migration_still_converts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The non-MISSING branch: a proven real Claude family is still converted by
    the rename dance and prints `migrated ->`. One real family plus MISSING
    siblings exercises both branches of the MISSING check in one run."""
    _require_real_symlinks(tmp_path)
    _seed_claude_family_real(tmp_path)
    _seed_agents_family(tmp_path)

    install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    out = capsys.readouterr().out
    assert "claude skill migrated" in out
    assert "pristine installed files replaced by one shared skill reference" in out
    claude_dir = _claude_family_dir(tmp_path)
    assert claude_dir.is_symlink()
    assert claude_dir.resolve() == _agents_family_dir(tmp_path).resolve()


# --- HIGH-1: `_install_skill_family` stamps every family, on both hosts


@pytest.mark.unit
def test_install_skill_family_stamps_every_family_on_both_hosts(tmp_path: Path) -> None:
    """`_install_skill_family` stamps `.dummyindex_version` on every family, not
    just main, on BOTH hosts."""
    src = tmp_path / "skill-src.md"
    src.write_text(
        "---\nname: dummyindex\ndescription: t\n---\nbody\n", encoding="utf-8"
    )

    _install_skill_family(tmp_path, "claude", src)
    _install_skill_family(tmp_path, "codex", src)

    for root_name, host in ((".claude", "claude"), (".agents", "codex")):
        for family in FAMILIES:
            stamp = tmp_path / root_name / "skills" / family / ".dummyindex_version"
            assert stamp.is_file(), (host, family)
            assert stamp.read_text(encoding="utf-8").strip() == PACKAGE_VERSION, (
                host,
                family,
            )


# --- HIGH-1: `_backfill_sibling_stamps` characterization


@pytest.mark.unit
def test_backfill_mints_sibling_stamp_from_stamped_main(tmp_path: Path) -> None:
    """The bread-and-butter case: main stamped, sibling real and unstamped
    -> the sibling is minted the MAIN's own value."""
    _seed_claude_family_real(tmp_path, "dummyindex", version=PACKAGE_VERSION)
    _seed_claude_family_real(tmp_path, "dummyindex-plan", version=None)

    _backfill_sibling_stamps(tmp_path, "claude")

    stamp = tmp_path / ".claude" / "skills" / "dummyindex-plan" / ".dummyindex_version"
    assert stamp.read_text(encoding="utf-8").strip() == PACKAGE_VERSION


@pytest.mark.unit
def test_backfill_mints_the_mains_value_not_package_version(tmp_path: Path) -> None:
    """The minted value is the main's own (old) stamp, never `PACKAGE_VERSION`."""
    old_version = "0.1.0"
    assert old_version != PACKAGE_VERSION  # precondition: the two must differ
    _seed_claude_family_real(tmp_path, "dummyindex", version=old_version)
    _seed_claude_family_real(tmp_path, "dummyindex-plan", version=None)

    _backfill_sibling_stamps(tmp_path, "claude")

    stamp = tmp_path / ".claude" / "skills" / "dummyindex-plan" / ".dummyindex_version"
    assert stamp.read_text(encoding="utf-8").strip() == old_version


@pytest.mark.unit
def test_backfill_mints_nothing_when_main_is_unstamped(tmp_path: Path) -> None:
    """NO stamp minted when the main carries no stamp at all."""
    _seed_claude_family_real(tmp_path, "dummyindex", version=None)
    _seed_claude_family_real(tmp_path, "dummyindex-plan", version=None)

    _backfill_sibling_stamps(tmp_path, "claude")

    stamp = tmp_path / ".claude" / "skills" / "dummyindex-plan" / ".dummyindex_version"
    assert not stamp.exists()


@pytest.mark.unit
def test_backfill_mints_nothing_when_main_is_heading_only(tmp_path: Path) -> None:
    """NO stamp minted when main is proven only by the legacy Codex heading: the
    backfill demands the STAMP, as replacing a real dir with a link does."""
    main_dir = tmp_path / ".claude" / "skills" / "dummyindex"
    main_dir.mkdir(parents=True)
    (main_dir / "SKILL.md").write_text(
        "---\nname: dummyindex\ndescription: t\n---\n"
        "## Codex host compatibility\nlegacy heading\n",
        encoding="utf-8",
    )
    _seed_claude_family_real(tmp_path, "dummyindex-plan", version=None)

    _backfill_sibling_stamps(tmp_path, "claude")

    stamp = tmp_path / ".claude" / "skills" / "dummyindex-plan" / ".dummyindex_version"
    assert not stamp.exists()


@pytest.mark.unit
def test_backfill_never_mints_for_a_non_enumerated_sibling_name(
    tmp_path: Path,
) -> None:
    """NO stamp minted for equip's `dummyindex-verify`: the backfill enumerates
    `_SIBLING_SKILLS`, never a `dummyindex*` glob."""
    _seed_claude_family_real(tmp_path, "dummyindex", version=PACKAGE_VERSION)
    _seed_claude_family_real(tmp_path, "dummyindex-verify", version=None)

    _backfill_sibling_stamps(tmp_path, "claude")

    stamp = (
        tmp_path / ".claude" / "skills" / "dummyindex-verify" / ".dummyindex_version"
    )
    assert not stamp.exists()


@pytest.mark.integration
def test_backfill_leaves_non_enumerated_sibling_untouched_and_unlinked(
    tmp_path: Path,
) -> None:
    """The same through `install()`: a flagless install leaves `dummyindex-verify`
    unstamped and unlinked, since it is not one of the 8 families."""
    _require_real_symlinks(tmp_path)
    _seed_realistic_claude_layout(tmp_path)
    _seed_realistic_agents_layout(tmp_path)
    _seed_claude_family_real(tmp_path, "dummyindex-verify", version=None)

    install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    verify_dir = tmp_path / ".claude" / "skills" / "dummyindex-verify"
    assert verify_dir.is_dir()
    assert not verify_dir.is_symlink()
    assert not (verify_dir / ".dummyindex_version").exists()


@pytest.mark.unit
def test_backfill_never_writes_through_a_sibling_that_is_itself_a_symlink(
    tmp_path: Path,
) -> None:
    """NO write when the sibling slot is itself a symlink (already
    converted, or foreign) -- `lstat` must never be followed."""
    _require_real_symlinks(tmp_path)
    _seed_claude_family_real(tmp_path, "dummyindex", version=PACKAGE_VERSION)
    external = tmp_path / "external-plan-target"
    external.mkdir()
    sibling_dir = tmp_path / ".claude" / "skills" / "dummyindex-plan"
    sibling_dir.symlink_to(external, target_is_directory=True)

    _backfill_sibling_stamps(tmp_path, "claude")

    assert not (external / ".dummyindex_version").exists()
    assert not (sibling_dir / ".dummyindex_version").exists()


@pytest.mark.unit
def test_backfill_never_writes_through_a_symlinked_claude_parent(
    tmp_path: Path,
) -> None:
    """NO write through a symlinked `.claude` absent from ``allowed_symlinks``,
    even when the main inside it is legitimately stamped."""
    _require_real_symlinks(tmp_path)
    real_target = tmp_path / "real-claude-target"
    real_target.mkdir()
    (real_target / "skills" / "dummyindex").mkdir(parents=True)
    (real_target / "skills" / "dummyindex" / "SKILL.md").write_text(
        "---\nname: dummyindex\ndescription: t\n---\nbody\n", encoding="utf-8"
    )
    (real_target / "skills" / "dummyindex" / ".dummyindex_version").write_text(
        PACKAGE_VERSION, encoding="utf-8"
    )
    (real_target / "skills" / "dummyindex-plan").mkdir(parents=True)
    (real_target / "skills" / "dummyindex-plan" / "SKILL.md").write_text(
        "---\nname: dummyindex-plan\ndescription: t\n---\nbody\n", encoding="utf-8"
    )
    (tmp_path / ".claude").symlink_to(real_target, target_is_directory=True)

    # Empty allowlist, as `install()` uses at project scope.
    _backfill_sibling_stamps(tmp_path, "claude", allowed_symlinks=frozenset())

    stamp = real_target / "skills" / "dummyindex-plan" / ".dummyindex_version"
    assert not stamp.exists()


# --- HIGH-2: the weaker classifier is gone; the residual crash is fixed


@pytest.mark.integration
def test_sibling_healthy_link_classifies_ours_healthy_with_helper_deleted(
    tmp_path: Path,
) -> None:
    """With `_is_unstamped_own_family_link` gone, a sibling's healthy link classifies
    OURS_HEALTHY via plain `classify_family_link`: the backfill stamps its target."""
    import dummyindex.installer.install as install_module

    assert not hasattr(install_module, "_is_unstamped_own_family_link")

    _require_real_symlinks(tmp_path)
    _seed_realistic_claude_layout(tmp_path)
    _seed_realistic_agents_layout(tmp_path)

    install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    for sibling in ("dummyindex-plan", "dummyindex-audit"):
        classification = classify_family_link(
            _claude_family_dir(tmp_path, sibling), tmp_path
        )
        assert classification.state is FamilyLinkState.OURS_HEALTHY, sibling


@pytest.mark.integration
def test_destamped_target_linked_layout_exits_cleanly_not_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A linked layout whose MAIN `.agents` target has an empty stamp classifies
    FOREIGN; `install()` exits cleanly (`SystemExit`, one stderr line), never with
    a raw `OSError` from `_install_skill_family`'s symlink guard."""
    _require_real_symlinks(tmp_path)
    _seed_all_agents_families(tmp_path)
    result = create_family_links(tmp_path)
    assert not result.errors, result.errors

    (tmp_path / ".agents" / "skills" / "dummyindex" / ".dummyindex_version").write_text(
        "", encoding="utf-8"
    )
    classification = classify_family_link(_claude_family_dir(tmp_path), tmp_path)
    assert classification.state is FamilyLinkState.FOREIGN  # precondition

    with pytest.raises(SystemExit) as exc:
        install(scope="project", project_dir=tmp_path, skill_only=True, platform="both")

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "error: refusing to install through managed directory symlink" in err
    # The real target's SKILL.md survives: nothing was torn down or written through.
    assert (tmp_path / ".agents" / "skills" / "dummyindex" / "SKILL.md").exists()


# --- MEDIUM-1: an unexpected run_link_install failure never leaves
# --- neither links nor real dirs


@pytest.mark.integration
def test_unexpected_run_link_install_exception_still_lands_real_claude_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unexpected (non-`LinkCapabilityError`) `run_link_install` failure on a fresh
    install still lands the deferred MISSING-family write, so the Claude side never
    has NEITHER links nor real dirs; it exits 1 with a clean stderr line."""
    import importlib

    install_module = importlib.import_module("dummyindex.installer.install")

    def _raising_run_link_install(*_a: object, **_k: object) -> object:
        raise RuntimeError("boom: simulated link.py bug")

    monkeypatch.setattr(install_module, "run_link_install", _raising_run_link_install)

    with pytest.raises(SystemExit) as exc:
        install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "link install failed" in err
    assert "boom: simulated link.py bug" in err

    # "Never neither": every Claude family landed as a REAL, stamped directory.
    for family in FAMILIES:
        claude_dir = _claude_family_dir(tmp_path, family)
        assert claude_dir.is_dir(), family
        assert not claude_dir.is_symlink(), family
        assert (claude_dir / ".dummyindex_version").exists(), family


# End-to-end lifecycle. Each stage gets its own fresh project, since stages need
# contradictory starting shapes for the same family slot; only install and its
# idempotent rerun are chained, so one stage's failure never cascades.


def _init_fake_git_repo(root: Path) -> None:
    """The minimal on-disk shape `is_git_repo` accepts, so auto-init runs."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (root / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n", encoding="utf-8"
    )


def _redirect_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect HOME to a scratch dir: `install()`/`uninstall()` read `Path.home()`
    even at project scope, so duplicate detection would see the real machine."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    return fake_home


# --- stage 1 + 2: flagless universal install, then an idempotent rerun


@pytest.mark.integration
def test_e2e_flagless_install_then_idempotent_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stages 1-2, chained. Stage 1: a flagless install yields the universal linked
    layout — every enumerated family (derived from `_SIBLING_SKILLS`,
    never a glob) real+stamped in `.agents/skills/`, linked from `.claude/skills/`
    as `../../.agents/skills/<family>`, plus CLAUDE.md and AGENTS.md. Stage 2: a
    rerun prints no linked/migrated lines and keeps the link's inode and mtime."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)

    install(scope="project", project_dir=repo)  # flagless, auto-init runs
    capsys.readouterr()  # drain stage-1 transcript; only the rerun's matters below

    for family in FAMILIES:
        claude_dir = _claude_family_dir(repo, family)
        agents_dir = _agents_family_dir(repo, family)
        assert agents_dir.is_dir(), family
        assert not agents_dir.is_symlink(), family
        assert (agents_dir / ".dummyindex_version").read_text(
            encoding="utf-8"
        ).strip() == PACKAGE_VERSION, family

        # Every enumerated Claude family is a symlink, never a real dir.
        assert claude_dir.is_symlink(), family
        readlink_parts = PurePath(os.readlink(claude_dir)).parts
        assert readlink_parts == PurePath(f"../../.agents/skills/{family}").parts, (
            family
        )
        assert claude_dir.resolve() == agents_dir.resolve()

    assert (repo / ".claude" / "CLAUDE.md").exists()
    assert (repo / "AGENTS.md").exists()

    main_link = _claude_family_dir(repo)
    before = main_link.lstat()

    install(scope="project", project_dir=repo)  # stage 2: identical flagless rerun

    rerun_out = capsys.readouterr().out
    assert "claude skill linked" not in rerun_out
    assert "claude skill migrated" not in rerun_out
    after = main_link.lstat()
    assert before.st_ino == after.st_ino
    assert before.st_mtime_ns == after.st_mtime_ns
    assert (
        PurePath(os.readlink(main_link)).parts
        == PurePath("../../.agents/skills/dummyindex").parts
    )


# --- stage 3: forced migration, duplicated (realistic) layout


@pytest.mark.integration
def test_e2e_forced_migration_duplicated_layout_with_full_auto_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stage 3: the duplicated-layout migration above, with full auto-init: every
    Claude family becomes a link with a `migrated ->` line + caveat, `.agents` stays
    the only real tree, and both CLAUDE.md and AGENTS.md are written."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    _seed_realistic_claude_layout(repo)
    _seed_realistic_agents_layout(repo)

    install(scope="project", project_dir=repo)  # flagless

    out = capsys.readouterr().out
    assert out.count("claude skill migrated") == len(FAMILIES)
    assert out.count(
        "pristine installed files replaced by one shared skill reference"
    ) == len(FAMILIES)

    for family in FAMILIES:
        claude_dir = _claude_family_dir(repo, family)
        agents_dir = _agents_family_dir(repo, family)
        assert claude_dir.is_symlink(), family
        assert not agents_dir.is_symlink() and agents_dir.is_dir(), family
        readlink_parts = PurePath(os.readlink(claude_dir)).parts
        assert readlink_parts == PurePath(f"../../.agents/skills/{family}").parts, (
            family
        )

    assert (repo / ".claude" / "CLAUDE.md").exists()
    assert (repo / "AGENTS.md").exists()


# --- stage 4: forced migration, claude-only (realistic) layout


@pytest.mark.integration
def test_e2e_forced_migration_claude_only_layout_writes_claude_md_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage 4: the claude-only migration above, plus readlink parts and CLAUDE.md:
    a flagless install writes `.agents`, links every `.claude` family canonically
    and writes both CLAUDE.md and AGENTS.md."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    _seed_realistic_claude_layout(repo)

    install(scope="project", project_dir=repo)  # flagless, auto-init runs

    assert (repo / ".claude" / "CLAUDE.md").exists()
    assert (repo / "AGENTS.md").exists()

    for family in FAMILIES:
        claude_dir = _claude_family_dir(repo, family)
        agents_dir = _agents_family_dir(repo, family)
        assert agents_dir.is_dir() and not agents_dir.is_symlink(), family
        assert claude_dir.is_symlink(), family
        readlink_parts = PurePath(os.readlink(claude_dir)).parts
        assert readlink_parts == PurePath(f"../../.agents/skills/{family}").parts, (
            family
        )
        assert claude_dir.resolve() == agents_dir.resolve()


# --- stage 5: stale-stamp repair, links untouched


@pytest.mark.integration
def test_e2e_stale_agents_target_repaired_in_place_links_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage 5: a linked layout with stale `.agents` stamps is repaired in place (all
    stamps bumped) while the Claude links stay untouched, down to the MAIN link's
    inode and mtime: repair never rewrites through an OURS_HEALTHY link."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    old_version = "0.1.0"
    assert old_version != PACKAGE_VERSION  # precondition: genuinely stale
    for family in FAMILIES:
        _seed_agents_family(repo, family, version=old_version)
    result = create_family_links(repo)
    assert not result.errors, result.errors

    main_link = _claude_family_dir(repo)
    before = main_link.lstat()
    before_readlink = os.readlink(main_link)

    install(scope="project", project_dir=repo, skill_only=True)  # flagless AUTO

    after = main_link.lstat()
    assert before.st_ino == after.st_ino
    assert before.st_mtime_ns == after.st_mtime_ns
    assert os.readlink(main_link) == before_readlink

    for family in FAMILIES:
        stamp = _agents_family_dir(repo, family) / ".dummyindex_version"
        assert stamp.read_text(encoding="utf-8").strip() == PACKAGE_VERSION, family
        classification = classify_family_link(_claude_family_dir(repo, family), repo)
        assert classification.state is FamilyLinkState.OURS_HEALTHY, family


# --- stage 6: dangling heal


@pytest.mark.integration
def test_e2e_dangling_link_heals_once_agents_target_is_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage 6: a dangling Claude link (`.agents` target removed) heals to OURS_HEALTHY
    with the canonical readlink value after one flagless reinstall, which rewrites
    `.agents/skills/**` before the link dispatch."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    for family in FAMILIES:
        _seed_agents_family(repo, family)
    result = create_family_links(repo)
    assert not result.errors, result.errors

    # Dangle MAIN: the direct-write loop rewrites `.agents` only when the main family
    # is missing or unproven, so a dangled sibling alone would never be recreated.
    family = "dummyindex"
    _remove_tree(_agents_family_dir(repo, family))
    dangling_before = classify_family_link(_claude_family_dir(repo, family), repo)
    assert dangling_before.state is FamilyLinkState.OURS_DANGLING  # precondition

    install(scope="project", project_dir=repo, skill_only=True)  # flagless AUTO rerun

    healed = classify_family_link(_claude_family_dir(repo, family), repo)
    assert healed.state is FamilyLinkState.OURS_HEALTHY
    readlink_parts = PurePath(os.readlink(_claude_family_dir(repo, family))).parts
    assert readlink_parts == PurePath(f"../../.agents/skills/{family}").parts


# --- stage 7: materialized replace


@pytest.mark.integration
def test_e2e_materialized_placeholder_replaced_by_flagless_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stage 7: a MATERIALIZED placeholder (the `core.symlinks=false` Windows-checkout
    shape) is REPLACED with a real link, a genuine write unlike the dangling heal: it
    prints `claude skill migrated` + the caveat and ends OURS_HEALTHY."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    for family in FAMILIES:
        _seed_agents_family(repo, family)
    _seed_materialized_claude_family(repo)
    family_dir = _claude_family_dir(repo)
    assert family_dir.read_text(encoding="utf-8") == relative_link_value(
        "dummyindex"
    )  # precondition

    install(scope="project", project_dir=repo, skill_only=True)  # flagless AUTO

    out = capsys.readouterr().out
    assert "claude skill migrated" in out
    assert "pristine installed files replaced by one shared skill reference" in out
    assert family_dir.is_symlink()
    classification = classify_family_link(family_dir, repo)
    assert classification.state is FamilyLinkState.OURS_HEALTHY


# --- stage 8: EPERM pre-probe -> whole-run AUTO copy-fallback


@pytest.mark.integration
def test_e2e_eperm_preprobe_falls_back_to_copy_with_exactly_one_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stage 8: an injected `symlink_fn` that always raises EPERM fails the pre-probe
    before anything is destroyed (patching `os.symlink` misses `Path.symlink_to` on
    py3.10). The WHOLE run falls back to copy: every family a REAL Claude dir, no
    `SystemExit`, EXACTLY ONE warning. Unguarded: the real `os.symlink` never runs."""
    import errno
    import importlib

    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)

    from dummyindex.installer.link import run_link_install as real_run_link_install

    install_module = importlib.import_module("dummyindex.installer.install")

    def _raising_symlink_fn(*_a: object, **_k: object) -> None:
        raise OSError(errno.EPERM, "Operation not permitted")

    def _fake_run_link_install(*args: object, **kwargs: object) -> object:
        kwargs["symlink_fn"] = _raising_symlink_fn
        return real_run_link_install(*args, **kwargs)

    monkeypatch.setattr(install_module, "run_link_install", _fake_run_link_install)

    install(scope="project", project_dir=repo, skill_only=True)  # flagless, no raise

    err = capsys.readouterr().err
    warning_lines = [line for line in err.splitlines() if "warning:" in line]
    assert len(warning_lines) == 1, warning_lines
    assert "using thin Claude references" in warning_lines[0]

    for family in FAMILIES:
        claude_dir = _claude_family_dir(repo, family)
        agents_dir = _agents_family_dir(repo, family)
        assert claude_dir.is_dir(), family
        assert not claude_dir.is_symlink(), family
        assert agents_dir.is_dir(), family
        assert not agents_dir.is_symlink(), family


# --- stage 9: Nth-call mid-loop failure


@pytest.mark.integration
def test_e2e_nth_call_symlink_failure_preserves_survivors_names_uncovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stage 9: a `symlink_fn` failing on the Nth real conversion (the pre-probe always
    passes) aborts from the Nth onward; earlier links SURVIVE and every uncovered
    family is named in `link error` lines. Guarded: other calls hit the real `os.symlink`."""
    import errno
    import importlib

    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)

    from dummyindex.installer.link import run_link_install as real_run_link_install

    install_module = importlib.import_module("dummyindex.installer.install")

    fail_at = 4
    calls = {"n": 0}

    def _counting_raiser(
        src: object, dst: Path, *, target_is_directory: bool = False
    ) -> None:
        if "dummyindex-symlink-probe" in str(dst):
            os.symlink(src, dst, target_is_directory=target_is_directory)
            return
        calls["n"] += 1
        if calls["n"] == fail_at:
            raise OSError(errno.EPERM, "Operation not permitted")
        os.symlink(src, dst, target_is_directory=target_is_directory)

    def _fake_run_link_install(*args: object, **kwargs: object) -> object:
        kwargs["symlink_fn"] = _counting_raiser
        return real_run_link_install(*args, **kwargs)

    monkeypatch.setattr(install_module, "run_link_install", _fake_run_link_install)

    with pytest.raises(SystemExit) as stopped:
        install(scope="project", project_dir=repo, skill_only=True)  # flagless
    assert stopped.value.code == 1

    survivors = FAMILIES[: fail_at - 1]
    failed_family = FAMILIES[fail_at - 1]
    uncovered = FAMILIES[fail_at:]

    for family in survivors:
        claude_dir = _claude_family_dir(repo, family)
        assert claude_dir.is_symlink(), family
        assert claude_dir.resolve() == _agents_family_dir(repo, family).resolve()
    for family in (failed_family, *uncovered):
        claude_dir = _claude_family_dir(repo, family)
        assert claude_dir.is_dir() and not claude_dir.is_symlink(), family
        reference = (claude_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "<!-- dummyindex:skill-reference -->" in reference
        assert f".agents/skills/{family}/SKILL.md" in reference

    err = capsys.readouterr().err
    for family in (failed_family, *uncovered):
        assert f"{family}:" in err, family
    # `.agents` stays valid: the failure is only on the Claude-linking side.
    for family in FAMILIES:
        assert _agents_family_dir(repo, family).is_dir(), family

    # A rerun (nothing further injected) converges every remaining family.
    install(scope="project", project_dir=repo, skill_only=True)
    for family in FAMILIES:
        classification = classify_family_link(_claude_family_dir(repo, family), repo)
        assert classification.state is FamilyLinkState.OURS_HEALTHY, family


# --- stage 10: crash-window recovery


@pytest.mark.integration
def test_e2e_crash_window_temp_artifacts_converge_on_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage 10: crash-window leftovers (temp link `.<family>.dummyindex-link.tmp`,
    renamed-aside `.<family>.dummyindex-old.tmp`, slot MISSING) converge on one
    flagless rerun: a healthy link, both temps gone, every other family linked."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    for family in FAMILIES:
        _seed_agents_family(repo, family)

    claude_skills_root = repo / ".claude" / "skills"
    claude_skills_root.mkdir(parents=True, exist_ok=True)
    family = "dummyindex"
    tmp_link = claude_skills_root / f".{family}.dummyindex-link.tmp"
    tmp_link.symlink_to("stale-crash-artifact", target_is_directory=True)
    tmp_old = claude_skills_root / f".{family}.dummyindex-old.tmp"
    tmp_old.mkdir(parents=True, exist_ok=True)
    _write_family_dir(tmp_old, name=family)

    install(scope="project", project_dir=repo, skill_only=True)  # flagless AUTO rerun

    assert not tmp_link.exists() and not tmp_link.is_symlink()
    assert not tmp_old.exists()
    for check_family in FAMILIES:
        claude_dir = _claude_family_dir(repo, check_family)
        assert claude_dir.is_symlink(), check_family
        assert claude_dir.resolve() == _agents_family_dir(repo, check_family).resolve()


# --- stage 11: dedupe -- link-only removal, never the .agents target


@pytest.mark.integration
def test_e2e_dedupe_removes_linked_side_only_never_the_agents_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage 11: with the family installed at both scopes, deduping the user `claude`
    copy (itself a LINK) removes only the link; its real `.agents` target survives."""
    fake_home = _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)

    install(scope="project", project_dir=repo, skill_only=True)  # universal @ project
    install(scope="user", skill_only=True)  # universal @ user (fake_home)

    user_claude_dir = fake_home / ".claude" / "skills" / "dummyindex"
    user_agents_dir = fake_home / ".agents" / "skills" / "dummyindex"
    assert user_claude_dir.is_symlink()  # precondition
    assert user_agents_dir.is_dir()  # precondition

    result = dedupe(
        "user", project_root=repo, user_home=fake_home, selected_platforms=("claude",)
    )

    assert str(user_claude_dir) in result.removed
    assert not user_claude_dir.exists() and not user_claude_dir.is_symlink()
    # The link's OWN target is never touched by a link-only removal.
    assert user_agents_dir.is_dir() and not user_agents_dir.is_symlink()
    assert (user_agents_dir / "SKILL.md").exists()
    assert (user_agents_dir / ".dummyindex_version").exists()


# --- stage 12: uninstall --platform agents sweep


@pytest.mark.integration
def test_e2e_uninstall_agents_sweep_removes_dangling_links_spares_foreign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stage 12: `uninstall --platform agents` removes `.agents` and every now-dangling
    owned Claude link; an unrelated FOREIGN link survives. The narrowing warning goes
    to stderr and its recovery command to stdout."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    install(scope="project", project_dir=repo, skill_only=True)  # flagless universal

    foreign_target = repo / "external-foreign-target"
    foreign_target.mkdir(parents=True, exist_ok=True)
    (foreign_target / "keep.txt").write_text("do not touch\n", encoding="utf-8")
    foreign_link = repo / ".claude" / "skills" / "totally-not-ours"
    foreign_link.symlink_to(foreign_target, target_is_directory=True)

    uninstall(scope="project", project_dir=repo, platform="agents")

    captured = capsys.readouterr()
    assert not (repo / ".agents").exists()
    for family in FAMILIES:
        claude_dir = _claude_family_dir(repo, family)
        assert not claude_dir.exists() and not claude_dir.is_symlink(), family
    assert foreign_link.is_symlink()
    assert foreign_link.resolve() == foreign_target.resolve()
    assert (foreign_target / "keep.txt").read_text(encoding="utf-8") == "do not touch\n"
    assert "removed the only real skill tree" in captured.err
    assert f"{len(FAMILIES)} Claude-side references" in captured.err
    # The recovery command is a plain `print`, so it lands on stdout.
    assert "restore Claude Code without Codex: dummyindex install" in captured.out
    assert "--platform claude" in captured.out


# --- stage 13: flagless uninstall (both) -> clean tree


@pytest.mark.integration
def test_e2e_flagless_uninstall_both_leaves_clean_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage 13: a flagless uninstall of a linked, auto-inited project leaves no links
    or families on either host and removes `tokens.md` and the managed AGENTS.md block."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    install(scope="project", project_dir=repo)  # flagless, auto-init runs

    assert (repo / "AGENTS.md").exists()  # precondition
    assert (repo / ".claude" / "commands" / "tokens.md").exists()  # precondition

    uninstall(scope="project", project_dir=repo)  # flagless: platform="both"

    assert not (repo / ".agents").exists()
    for family in FAMILIES:
        claude_dir = _claude_family_dir(repo, family)
        assert not claude_dir.exists() and not claude_dir.is_symlink(), family
    assert not (repo / ".claude" / "commands" / "tokens.md").exists()
    if (repo / "AGENTS.md").exists():
        # If AGENTS.md survives for another reason, the dummyindex block is gone.
        assert (
            "dummyindex" not in (repo / "AGENTS.md").read_text(encoding="utf-8").lower()
        )


# --- stage 14: user-scope leg + dotfiles-divergent fallback


@pytest.mark.integration
def test_e2e_user_scope_flagless_auto_lifecycle_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage 14a: the universal linked layout lands at user scope too (HOME
    redirected), and a flagless uninstall cleans it up."""
    fake_home = _redirect_home(tmp_path, monkeypatch)
    _require_real_symlinks(fake_home)

    install(scope="user", skill_only=True)  # flagless

    for family in FAMILIES:
        claude_dir = fake_home / ".claude" / "skills" / family
        agents_dir = fake_home / ".agents" / "skills" / family
        assert claude_dir.is_symlink(), family
        assert agents_dir.is_dir() and not agents_dir.is_symlink(), family
        assert claude_dir.resolve() == agents_dir.resolve()
    claude_md = fake_home / ".claude" / "CLAUDE.md"
    assert claude_md.exists()
    assert "**dummyindex** (" in claude_md.read_text(encoding="utf-8")

    uninstall(scope="user")  # flagless: platform="both"

    assert not (fake_home / ".agents").exists()
    for family in FAMILIES:
        claude_dir = fake_home / ".claude" / "skills" / family
        assert not claude_dir.exists() and not claude_dir.is_symlink(), family


@pytest.mark.integration
@pytest.mark.usefixtures("real_symlinks")
def test_e2e_user_scope_dotfiles_divergent_link_falls_back_to_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stage 14b: with `~/.claude` symlinked to a dir outside home, the relative link
    value resolves outside the real home, so a flagless user-scope AUTO install falls
    back to copy (real Claude dirs, never neither) with one dotfiles warning and no
    `link error` lines: `_probe_symlink_capability` checks the canonical value
    resolves before any link is made. A second run stays copy and rewrites nothing."""
    fake_home = _redirect_home(tmp_path, monkeypatch)
    dotfiles_target = tmp_path / "dotfiles-claude"
    dotfiles_target.mkdir()
    (fake_home / ".claude").symlink_to(dotfiles_target, target_is_directory=True)
    _require_real_symlinks(fake_home)

    install(scope="user", skill_only=True)  # flagless, run 1

    out, err = capsys.readouterr()
    for family in FAMILIES:
        # A real dir per family: the relative value can't reach `.agents` from
        # inside the dotfiles target.
        claude_dir = dotfiles_target / "skills" / family
        assert claude_dir.is_dir(), family
        assert not claude_dir.is_symlink(), family
        assert (claude_dir / ".dummyindex_version").read_text(
            encoding="utf-8"
        ).strip() == PACKAGE_VERSION, family

    assert "link error" not in out
    assert "link error" not in err
    assert out.count("claude skill linked") == 0
    assert out.count("claude skill migrated") == 0
    warning_lines = [line for line in err.splitlines() if line.strip()]
    assert len(warning_lines) == 1, warning_lines
    assert "dotfiles" in warning_lines[0]
    assert "Developer Mode" not in warning_lines[0]
    assert "core.symlinks" not in warning_lines[0]

    main_family_dir = dotfiles_target / "skills" / "dummyindex"
    before = main_family_dir.lstat()

    install(scope="user", skill_only=True)  # flagless, run 2 (idempotency)

    out2, err2 = capsys.readouterr()
    after = main_family_dir.lstat()
    assert before.st_ino == after.st_ino
    assert before.st_mtime_ns == after.st_mtime_ns
    assert "link error" not in out2
    assert "link error" not in err2
    for family in FAMILIES:
        claude_dir = dotfiles_target / "skills" / family
        assert claude_dir.is_dir(), family
        assert not claude_dir.is_symlink(), family
    warning_lines2 = [line for line in err2.splitlines() if line.strip()]
    assert len(warning_lines2) == 1, warning_lines2
    assert "dotfiles" in warning_lines2[0]


# --- focused unit tests: `_probe_symlink_capability`'s resolution check


@pytest.mark.unit
def test_probe_symlink_capability_succeeds_on_normal_non_dotfiles_layout(
    tmp_path: Path,
) -> None:
    """The capability + resolution probe still passes on an ordinary layout."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)

    ok, detail, hint = _probe_symlink_capability(scope_root, symlink_fn=os.symlink)

    assert ok is True
    assert detail == "ok"
    assert hint == ""
    claude_skills_root = scope_root / ".claude" / "skills"
    assert list(claude_skills_root.glob("*.tmp")) == []


@pytest.mark.unit
def test_probe_symlink_capability_detects_dotfiles_divergent_resolution(
    tmp_path: Path,
) -> None:
    """A `.claude` whose relative link resolves OUTSIDE the scope root fails with a
    dotfiles hint, never the Windows capability hint, and leaves no temp file."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "home"
    scope_root.mkdir()
    dotfiles_target = tmp_path / "dotfiles-claude"
    dotfiles_target.mkdir()
    (scope_root / ".claude").symlink_to(dotfiles_target, target_is_directory=True)
    _seed_all_agents_families(scope_root)

    ok, detail, hint = _probe_symlink_capability(
        scope_root,
        symlink_fn=os.symlink,
        allowed_symlinks=frozenset({scope_root / ".claude"}),
    )

    assert ok is False
    assert "resolves to" in detail
    assert "dotfiles" in hint
    assert "Developer Mode" not in hint
    assert "core.symlinks" not in hint
    assert list((dotfiles_target / "skills").glob("*.tmp")) == []


@pytest.mark.unit
def test_probe_symlink_capability_skips_resolution_check_when_no_real_agents_family(
    tmp_path: Path,
) -> None:
    """With no real `.agents` family (sequencing should prevent it), the probe stays
    capability-only rather than manufacture a false failure."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"

    ok, detail, hint = _probe_symlink_capability(scope_root, symlink_fn=os.symlink)

    assert ok is True
    assert detail == "ok"
    assert hint == ""
