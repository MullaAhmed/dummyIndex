"""Tests for Wave 3 of the symlink-single-source-install proposal: wiring
`installer/link.py`'s primitives into `install()` itself.

Covers exactly the items owned by this task (`.context/proposals/
symlink-single-source-install/plan.md`, task 4):

- The preflight admission (`install()`'s per-host symlink refusal now admits
  OURS_HEALTHY / OURS_DANGLING / MATERIALIZED family dirs, in every
  `LinkMode`, while FOREIGN and deeper companion-dir symlinks keep today's
  refusal byte-for-byte).
- The write path staying unconditional: `_install_skill_family` never writes
  through a family-dir symlink or a materialized placeholder.
- The direct-write loop consulting `classify_family_link` first, so an
  OURS_DANGLING/MATERIALIZED family reports (under `--copy`) or defers to
  `create_family_links` (under AUTO/LINK) instead of crashing.
- The pinned sequencing + AUTO/LINK/COPY dispatch after `execute_repairs`,
  including the forced-migration transcript ("migrated ->" lines) and the
  `--platform claude` narrowing's stamp-currency gate.
- Side surfaces (commands, CLAUDE.md, hooks, auto-init) still running
  unchanged under link mode.

Also covers the three Wave-3 audit findings fixed alongside this file
(`.context/proposals/symlink-single-source-install/`):

- **HIGH-1**: `_install_skill_family` now stamps `.dummyindex_version` on
  every sibling too, not just the main family dir, on both hosts; and
  `_backfill_sibling_stamps` mints the same stamp onto a pre-existing
  install's unstamped-but-real siblings (main's own value, never
  `PACKAGE_VERSION`), so a realistic migration seed (main stamped, siblings
  real and unstamped, exactly as every prior release shipped) converts all
  8 families to links instead of permanently duplicating its siblings.
- **HIGH-2**: `_is_unstamped_own_family_link` is deleted — the preflight
  admission now routes through plain `classify_family_link`/
  `verify_family_links` results only — and the direct-write loop never
  calls `_install_skill_family` through a family-dir symlink, however it
  classifies, closing the residual crash a de-stamped `.agents` target
  could still reach.
- **MEDIUM-1**: an unexpected (non-`LinkCapabilityError`) `run_link_install`
  failure still lands the deferred blank-slate Claude write before exiting
  — the "never neither" invariant (exactly one of {8 links, 8 real Claude
  dirs} at the end of every run) holds even on an unforeseen failure.

`installer/link.py`'s own primitives (classification alphabet, the safe
replacement dance, the capability pre-probe) are Wave 2 and already covered
by `tests/test_install_link_primitives.py` — this module stays focused on
the `install()` wiring, mirroring that module's own "primitives vs wiring"
split.
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
# that would also catch the equip-generated `dummyindex-verify` skill, which
# is NOT part of this family). Mirrors `tests/test_install_link_primitives.py`.
FAMILIES = ("dummyindex", *(label for _sub_name, label in _SIBLING_SKILLS))


# ----- shared fixtures ------------------------------------------------------


def _require_real_symlinks(tmp_path: Path) -> None:
    """Skip the calling test when this environment cannot create symlinks.

    Only applied to tests that create (or expect `install()` to create) a
    REAL symlink — simulated/pure-logic tests (the `_claude_narrowing_link_gate`
    / `_agents_family_stamp_state` / `_link_state_report_line` unit tests, and
    the MATERIALIZED-only tests, which never touch a real symlink) are never
    guarded, mirroring `tests/test_install_link_primitives.py`'s own rule.
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


def _write_family_dir(base: Path, *, name: str, version: str | None) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\nbody\n", encoding="utf-8"
    )
    if version is not None:
        (base / ".dummyindex_version").write_text(version, encoding="utf-8")
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
    """Main stamped, every sibling REAL and UNSTAMPED — the shape every
    release actually produced before the HIGH-1 fix
    (`_install_skill_family` stamped only the main family dir; see
    `.context/proposals/symlink-single-source-install/`). Distinct from
    `_seed_all_claude_families_real` (which stamps every sibling too) —
    that helper is intentionally kept for the OTHER tests in this module
    that need every family already provably linkable; this one is the
    realistic migration seed the HIGH-1 fix targets."""
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


# ----- pure-logic unit tests (no symlinks; never guarded) -------------------


@pytest.mark.unit
def test_install_skill_family_raises_on_symlinked_family_dir(tmp_path: Path) -> None:
    """Write path stays unconditional: never write through a family-dir
    symlink, even an OURS_HEALTHY one — link mode replaces links via the
    rename dance, it never writes through them."""
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
    """Same guard, no real symlink involved: a MATERIALIZED regular file
    occupying the family-dir slot must never be written through either —
    `mkdir(exist_ok=True)` would otherwise raise `FileExistsError` uncaught."""
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


# ----- the preflight admission ----------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("link_mode", [LinkMode.AUTO, LinkMode.LINK, LinkMode.COPY])
def test_preflight_admits_ours_healthy_family_in_every_link_mode(
    tmp_path: Path, link_mode: LinkMode
) -> None:
    """OURS_HEALTHY must not trip the symlink refusal, in ANY LinkMode — the
    preflight itself never converts anything, only decides whether to
    refuse."""
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

    # `--platform both` so the `--platform claude` narrowing's separate
    # stamp-currency gate (tested on its own below) never enters into it —
    # this test is purely about the OLD preflight refusal not firing.
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
    """FOREIGN keeps today's refusal byte-for-byte — regression-asserts the
    EXACT existing message text/shape is unchanged by the admission logic."""
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
    """A real, proven main family dir with a symlinked COMPANION subdir
    (`agents/`) underneath it is still refused, byte-for-byte — the
    admission only ever applies to the top-level family dir itself."""
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


# ----- direct-write loop: no crash on OURS_DANGLING / MATERIALIZED ----------


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
    # Never healed under --copy: still a dangling link, not converted, not
    # crashed into a real directory either.
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


# ----- the AUTO matrix + forced migration -----------------------------------


@pytest.mark.integration
def test_flagless_forced_migration_of_duplicated_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE primary GATE-style scenario, seeded REALISTICALLY (spec:
    symlink-single-source-install, HIGH-1): main family stamped, every
    SIBLING real and UNSTAMPED on BOTH host trees — exactly what every
    prior release actually produced, since `_install_skill_family` stamped
    only the main family dir. BEFORE the HIGH-1 fix this reproduced
    `claude links=1/N, real-dirs-remaining=(N-1)/N` (only main converts; every
    sibling stays permanently duplicated because `create_family_links`
    requires the stamp specifically before replacing a real directory with
    a link). AFTER the fix, a flagless install backfills a stamp onto
    every `.agents`-side sibling first, then converts every proven Claude
    families to links, prints one `migrated ->` line + the hand-edits
    caveat per family, and a second run is a pure idempotent noop."""
    _require_real_symlinks(tmp_path)
    _seed_realistic_claude_layout(tmp_path)
    _seed_realistic_agents_layout(tmp_path)

    install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    out = capsys.readouterr().out
    assert out.count("claude skill migrated") == len(FAMILIES)
    assert out.count("hand-edits to this installed copy are not preserved") == len(
        FAMILIES
    )

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

    # HIGH-1: every .agents-side sibling is now stamped too, with the
    # MAIN's own pre-repair value (PACKAGE_VERSION here, since that's what
    # the realistic seed wrote for main) — never a bare PACKAGE_VERSION
    # mint blind to what the main actually carried. This is what lets the
    # sibling's Claude-side link classify OURS_HEALTHY, not FOREIGN.
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
    """A claude-only layout, seeded REALISTICALLY (spec: symlink-single-
    source-install, HIGH-1): main stamped, every sibling real and
    UNSTAMPED — today's most common install shape, no `.agents` at all. A
    flagless install writes `.agents` for real, converts EVERY `.claude`
    family (main + all 7 siblings, not just main) to a link, and writes
    AGENTS.md. Before the HIGH-1 fix only the main family converted; every
    sibling stayed a permanently duplicated real directory."""
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
def test_platform_claude_narrowing_copies_when_no_agents_family(tmp_path: Path) -> None:
    """AUTO + `--platform claude` with none: copy exactly as today — no
    `.agents` family exists to link onto, so the real Claude copy stays a
    real directory."""
    _seed_claude_family_real(tmp_path)

    install(
        scope="project",
        project_dir=tmp_path,
        skill_only=True,
        platform="claude",
        link_mode=LinkMode.AUTO,
    )

    assert not _claude_family_dir(tmp_path).is_symlink()
    assert _claude_family_dir(tmp_path).is_dir()
    assert not _agents_family_dir(tmp_path).exists()


@pytest.mark.integration
def test_strict_link_platform_claude_exits_when_no_agents_family(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_claude_family_real(tmp_path)

    with pytest.raises(SystemExit) as exc:
        install(
            scope="project",
            project_dir=tmp_path,
            skill_only=True,
            platform="claude",
            link_mode=LinkMode.LINK,
        )

    assert exc.value.code == 1
    assert "--platform both" in capsys.readouterr().err
    assert not _claude_family_dir(tmp_path).is_symlink()


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
    """AUTO + `--platform agents` never touches `.claude/**` — even a
    detected duplicated layout is left for `plan_repairs` to report, never
    converted by the link dispatch (which is never even entered)."""
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


# ----- --copy characterization ----------------------------------------------


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


# ----- side surfaces still work under link mode -----------------------------


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
    _require_real_symlinks(repo)

    install(scope="project", project_dir=repo)  # flagless

    assert (repo / ".context").is_dir()
    assert (repo / ".claude" / "CLAUDE.md").exists()
    settings = repo / ".claude" / "settings.json"
    assert settings.exists()
    assert "DUMMYINDEX_AUTO_REFRESH" in settings.read_text(encoding="utf-8")
    assert (repo / "AGENTS.md").exists()
    assert _claude_family_dir(repo).is_symlink()


# ----- MISSING-state deferral (the bug this task fixes) ---------------------
#
# Root cause this section guards against: the direct-write loop only
# special-cased OURS_DANGLING/MATERIALIZED for `host == "claude"`; a MISSING
# family dir (a fresh install) fell through to the unconditional
# `_install_skill_family` call, which writes every Claude family as real
# trees but stamps only the MAIN one. `create_family_links` then converted
# the stamped main family but refused every unstamped sibling ("no
# .dummyindex_version stamp"), permanently duplicating the family instead of
# linking it. The fix defers the MISSING-state write until it's known
# whether this run actually links; these tests are the regression guard.


@pytest.mark.integration
def test_flagless_fresh_install_all_8_families_become_claude_symlinks(
    tmp_path: Path,
) -> None:
    """THE primary regression test for this task: a completely fresh,
    flagless project install — nothing pre-existing on either side — must
    leave every enumerated family (main + `_SIBLING_SKILLS`, derived from
    the constant) as Claude-side symlinks pointing at
    `../../.agents/skills/<family>`. No enumerated family may exist as a
    real directory under `.claude/skills/`."""
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
    """AUTO whose capability pre-probe fails (a symlink-incapable host, e.g.
    Windows without Developer Mode) falls back to copy for the WHOLE run:
    every family must exist as REAL Claude directories, none dangling and
    none missing — the "never neither" invariant (never a mix of links and
    reals, and never neither at all). `install()` has no `symlink_fn` seam
    of its own, so the fake is injected via `run_link_install` (the single
    dispatch point `install.py` calls) rather than monkeypatching
    `os.symlink` — a bound default argument evaluated at import time, which
    a later `os.symlink` patch cannot reach. `importlib.import_module` (not
    `import dummyindex.installer.install as ...`) is required to reach the
    real submodule: `dummyindex/installer/__init__.py`'s own
    `from .install import install` rebinds the package's `install` attribute
    to the FUNCTION, shadowing the submodule there."""
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
    """Guards the OTHER branch the MISSING-deferral fix must not disturb: a
    family that already exists as a proven real Claude directory (NOT
    MISSING) is still converted by the forced-migration rename dance, and
    prints the `migrated ->` transcript line — a mixed layout (one real
    proven family, every sibling still MISSING) exercises both branches of
    the direct-write loop's new MISSING check in the same run."""
    _require_real_symlinks(tmp_path)
    _seed_claude_family_real(tmp_path)
    _seed_agents_family(tmp_path)

    install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    out = capsys.readouterr().out
    assert "claude skill migrated" in out
    assert "hand-edits to this installed copy are not preserved" in out
    claude_dir = _claude_family_dir(tmp_path)
    assert claude_dir.is_symlink()
    assert claude_dir.resolve() == _agents_family_dir(tmp_path).resolve()


# ----- HIGH-1: `_install_skill_family` stamps every family, on both hosts ---------


@pytest.mark.unit
def test_install_skill_family_stamps_every_family_on_both_hosts(tmp_path: Path) -> None:
    """`_install_skill_family` now stamps `.dummyindex_version` onto every
    sibling too, not just the main family dir, on BOTH hosts (HIGH-1 fix,
    spec: symlink-single-source-install) — asserted directly, no `install()`
    orchestration involved."""
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


# ----- HIGH-1: `_backfill_sibling_stamps` characterization -----------------


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
    """The minted value EQUALS the main's stamp value, never `PACKAGE_VERSION`
    blindly -- seed main at an OLD version and confirm the sibling gets
    THAT value, not the running package's."""
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
    """NO stamp minted when the main is proven only by the legacy Codex
    heading -- `is_owned_copy` would accept that, but the backfill demands
    the STAMP specifically (`_read_stamp`), the same stronger evidence
    `_has_version_stamp` requires before replacing a real directory with a
    link."""
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
    """NO stamp minted for a non-enumerated name: `dummyindex-verify` (the
    equip-generated skill, never part of this family) seeded beside a
    stamped main stays completely untouched by the backfill -- it is
    enumerated strictly from `_SIBLING_SKILLS`, never a `dummyindex*`
    glob."""
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
    """End-to-end version of the above through `install()` itself: a
    `dummyindex-verify` dir beside a realistic (main-stamped,
    siblings-unstamped) layout stays untouched AND unlinked after a
    flagless install -- never stamped, never converted to a link, because
    it is not one of the 8 enumerated families."""
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
    """NO write when the parent chain is unclean -- a symlinked `.claude`
    not present in ``allowed_symlinks`` must refuse the mint even though
    the main dir inside it is legitimately stamped."""
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

    # Empty allowlist: a project-scope symlinked `.claude` is never
    # tolerated (mirrors `claude_link_allowlist` being empty at project
    # scope in `install()`).
    _backfill_sibling_stamps(tmp_path, "claude", allowed_symlinks=frozenset())

    stamp = real_target / "skills" / "dummyindex-plan" / ".dummyindex_version"
    assert not stamp.exists()


# ----- HIGH-2: the weaker classifier is gone; the residual crash is fixed --


@pytest.mark.integration
def test_sibling_healthy_link_classifies_ours_healthy_with_helper_deleted(
    tmp_path: Path,
) -> None:
    """HIGH-2 fix: with `_is_unstamped_own_family_link` deleted entirely, a
    sibling's own healthy link must classify OURS_HEALTHY through the plain,
    full-strength `classify_family_link` on its own -- the HIGH-1 backfill
    stamps its `.agents` target first, so the ownership check passes
    without any second, weaker classifier."""
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
    """HIGH-2 residual: a linked layout whose MAIN `.agents` target lost its
    ownership evidence (de-stamped -- its directory still exists, only the
    stamp file is now empty) must classify FOREIGN, and `install()` must
    never crash with an uncaught `OSError` from `_install_skill_family`'s
    own `skill_dir.is_symlink()` guard reached through the direct-write
    loop's fallback -- it must exit cleanly (`SystemExit`, a clear stderr
    line), never a raw traceback."""
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
    # The external keep-file inside the real target proves nothing was
    # torn down or written through on the way to this clean refusal.
    assert (tmp_path / ".agents" / "skills" / "dummyindex" / "SKILL.md").exists()


# ----- MEDIUM-1: an unexpected run_link_install failure never leaves ------
# ----- neither links nor real dirs -----------------------------------------


@pytest.mark.integration
def test_unexpected_run_link_install_exception_still_lands_real_claude_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """MEDIUM-1 fix (spec: symlink-single-source-install): an unexpected,
    non-`LinkCapabilityError` exception from `run_link_install` (injected
    here as a plain `RuntimeError`, simulating a bug elsewhere in
    `link.py`) must never leave the Claude side with NEITHER links nor
    real dirs on a fresh, blank-slate install -- the deferred MISSING-
    family write must still land, unconditionally, before the failure
    surfaces as a clean stderr line. Never an uncaught traceback."""
    import importlib

    install_module = importlib.import_module("dummyindex.installer.install")

    def _raising_run_link_install(*_a: object, **_k: object) -> object:
        raise RuntimeError("boom: simulated link.py bug")

    monkeypatch.setattr(install_module, "run_link_install", _raising_run_link_install)

    with pytest.raises(SystemExit) as exc:
        install(scope="project", project_dir=tmp_path, skill_only=True)  # flagless

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "link install failed unexpectedly" in err
    assert "boom: simulated link.py bug" in err

    # "Never neither": every Claude family landed as REAL directories,
    # not left in limbo (neither linked nor real).
    for family in FAMILIES:
        claude_dir = _claude_family_dir(tmp_path, family)
        assert claude_dir.is_dir(), family
        assert not claude_dir.is_symlink(), family
        assert (claude_dir / ".dummyindex_version").exists(), family


# =============================================================================
# Wave 5 — end-to-end lifecycle (checklist.md Wave 5; plan.md task 9)
# =============================================================================
#
# Each stage below is its own focused `@pytest.mark.integration` test, each in
# its OWN fresh `tmp_path` project, rather than one giant mutation saga
# threading all 14 stages through a single directory. Several stages need
# CONTRADICTORY starting shapes for the very same family slot (a duplicated
# real tree vs. an already-linked layout vs. a dangling link vs. a
# materialized placeholder vs. mid-crash temp artifacts vs. a symlink-
# incapable host) — forcing all of them into one continuously-evolving tree
# would make every stage's precondition fragile and hard to review, exactly
# the case plan.md task 9 itself carves out an escape hatch for ("you may
# split this into several focused integration tests... if that reads
# cleaner"). The two stages that DO compose naturally without any conflicting
# precondition — a flagless install immediately followed by an idempotent
# rerun — are threaded together in one test below; dedupe/uninstall get their
# own fresh runs so a failure in one stage's assertions never cascades into
# an unrelated one.
#
# Every test below is real-filesystem `@pytest.mark.integration`. Tests that
# create or expect a REAL symlink are guarded with `_require_real_symlinks`;
# the DI-injected-failure tests (EPERM pre-probe fallback, Nth-call mid-loop
# failure) are per this module's own established rule (see
# `_require_real_symlinks`'s docstring) — the Nth-call test is guarded
# anyway because its raiser falls through to the real `os.symlink` on every
# non-failing call (mirrors `tests/test_install_link_primitives.py`'s
# identical "TEST GAP 1" note), while the whole-run EPERM fallback test never
# calls the real `os.symlink` at all and is intentionally left unguarded.


def _init_fake_git_repo(root: Path) -> None:
    """The minimal on-disk shape `is_git_repo` accepts, so `install()`'s
    auto-init runs (CLAUDE.md/AGENTS.md registration, hooks, `.context/`
    build) — mirrors the inline pattern already used above in this module
    (e.g. `test_link_mode_still_runs_auto_init_hooks_and_agents_md`)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (root / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f'hi {name}'\n", encoding="utf-8"
    )


def _redirect_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every Wave-5 test redirects HOME to a fresh scratch dir, never the
    real one — `install()`/`uninstall()` read (and, at user scope, write)
    `Path.home()` even for a project-scope run (duplicate-detection reads
    the real user scope otherwise, making output assertions depend on
    whatever happens to be installed on the machine running the suite)."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


# ----- stage 1 + 2: flagless universal install, then an idempotent rerun ---


@pytest.mark.integration
def test_e2e_flagless_install_then_idempotent_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Wave-5 stages 1-2, chained in one project (the one pair of stages
    with no conflicting precondition).

    Stage 1: a flagless install on a fresh repo yields the universal linked
    layout — every enumerated family (derived from `_SIBLING_SKILLS`,
    never a glob) real+stamped under `.agents/skills/`, each Claude-side
    family a symlink whose `os.readlink` parts equal exactly
    `../../.agents/skills/<family>`, no enumerated family a real dir under
    `.claude/skills/`, and BOTH CLAUDE.md and AGENTS.md written.

    Stage 2: an immediate second flagless run is a pure LinkResult
    0-created/0-replaced noop — no `claude skill linked`/`claude skill
    migrated` transcript lines — and the link itself is untouched at the
    inode + `st_mtime_ns` level (the secondary, filesystem-level observable
    behind the primary LinkResult one)."""
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

        # No enumerated family is a real dir under .claude/skills/: it must
        # be a symlink, full stop (a path cannot be both at once).
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


# ----- stage 3: forced migration, duplicated (realistic) layout -------------


@pytest.mark.integration
def test_e2e_forced_migration_duplicated_layout_with_full_auto_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Wave-5 stage 3, with full auto-init (CLAUDE.md/AGENTS.md) layered on
    top of `test_flagless_forced_migration_of_duplicated_layout`'s
    skill-only coverage above: a repo with proven real families under BOTH
    `.claude/skills/` and `.agents/skills/` (equal current stamps, siblings
    realistically unstamped) — a flagless install converts every proven
    Claude family to a link, prints one `migrated ->` line + the hand-edits
    caveat per family, leaves `.agents` as the only real tree, AND still
    writes both CLAUDE.md and AGENTS.md."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    _seed_realistic_claude_layout(repo)
    _seed_realistic_agents_layout(repo)

    install(scope="project", project_dir=repo)  # flagless

    out = capsys.readouterr().out
    assert out.count("claude skill migrated") == len(FAMILIES)
    assert out.count("hand-edits to this installed copy are not preserved") == len(
        FAMILIES
    )

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


# ----- stage 4: forced migration, claude-only (realistic) layout -----------


@pytest.mark.integration
def test_e2e_forced_migration_claude_only_layout_writes_claude_md_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wave-5 stage 4, extending `test_flagless_claude_only_layout_migrates_
    to_universal`'s AGENTS.md-only coverage above with the readlink-parts
    assertion AND the CLAUDE.md registration: on a repo with only a proven
    `.claude` family (today's most common install shape, main stamped,
    siblings realistically unstamped, no `.agents` at all), a flagless
    install writes `.agents` for real, converts every `.claude` family
    (main + all 7 siblings) to a canonical relative link, and writes BOTH
    CLAUDE.md and AGENTS.md — one command makes an old repo universal."""
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


# ----- stage 5: stale-stamp repair, links untouched -------------------------


@pytest.mark.integration
def test_e2e_stale_agents_target_repaired_in_place_links_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wave-5 stage 5: an already-linked layout whose `.agents` target
    stamp is OLDER than the running package — a flagless install repairs
    the `.agents` target IN PLACE (every family's stamp bumped to the
    current package version) while the Claude-side links are entirely
    untouched: readlink parts unchanged, and the MAIN link's inode +
    `st_mtime_ns` unchanged (repair never rewrites through an OURS_HEALTHY
    link; only the codex-side real target is repaired)."""
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


# ----- stage 6: dangling heal --------------------------------------------


@pytest.mark.integration
def test_e2e_dangling_link_heals_once_agents_target_is_restored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wave-5 stage 6: removing a family's `.agents` target dangles its
    Claude-side link (`OURS_DANGLING`, confirmed before the rerun below); a
    single flagless AUTO install — with the `.agents` target restored, the
    real-world trigger being a plain `dummyindex install`/`/dummyindex-
    update` reinstall that rewrites `.agents/skills/**` for real before ever
    reaching the link dispatch — re-resolves the link back to
    `OURS_HEALTHY` with the exact canonical readlink value, never requiring
    the family to be recreated by hand a second time."""
    _redirect_home(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _init_fake_git_repo(repo)
    _require_real_symlinks(repo)
    for family in FAMILIES:
        _seed_agents_family(repo, family)
    result = create_family_links(repo)
    assert not result.errors, result.errors

    # MAIN specifically: `install()`'s per-host direct-write loop only
    # rewrites `.agents` for real when the MAIN family itself is missing or
    # unproven (`skill_rel(host)` always resolves to the main family path) —
    # dangling a SIBLING's `.agents` target alone would never get it
    # recreated by a plain rerun at all, since main still looks fine and the
    # whole per-host write is skipped. Dangling MAIN reproduces the
    # real-world trigger: a plain reinstall rewrites `.agents/skills/**` for
    # real (main + every sibling) before ever reaching the link dispatch.
    family = "dummyindex"
    _remove_tree(_agents_family_dir(repo, family))
    dangling_before = classify_family_link(_claude_family_dir(repo, family), repo)
    assert dangling_before.state is FamilyLinkState.OURS_DANGLING  # precondition

    install(scope="project", project_dir=repo, skill_only=True)  # flagless AUTO rerun

    healed = classify_family_link(_claude_family_dir(repo, family), repo)
    assert healed.state is FamilyLinkState.OURS_HEALTHY
    readlink_parts = PurePath(os.readlink(_claude_family_dir(repo, family))).parts
    assert readlink_parts == PurePath(f"../../.agents/skills/{family}").parts


# ----- stage 7: materialized replace ----------------------------------------


@pytest.mark.integration
def test_e2e_materialized_placeholder_replaced_by_flagless_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Wave-5 stage 7: a regular file at the family-dir slot whose content
    is the exact link value (the `core.symlinks=false` Windows-checkout
    shape) is REPLACED with a real symlink by a flagless AUTO install —
    unlike the OS-transparent dangling-heal above, this is a genuine write
    (`create_family_links`'s `replace_materialized` plan): the transcript
    prints `claude skill migrated` + the hand-edits caveat, and the family
    ends up a canonical, healthy link."""
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
    assert "hand-edits to this installed copy are not preserved" in out
    assert family_dir.is_symlink()
    classification = classify_family_link(family_dir, repo)
    assert classification.state is FamilyLinkState.OURS_HEALTHY


# ----- stage 8: EPERM pre-probe -> whole-run AUTO copy-fallback -------------


@pytest.mark.integration
def test_e2e_eperm_preprobe_falls_back_to_copy_with_exactly_one_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Wave-5 stage 8: a DI-injected `symlink_fn` that always raises EPERM
    (never monkeypatching `os.symlink` itself, which `Path.symlink_to` does
    not route through on py3.10) makes the capability pre-probe fail before
    anything is destroyed. The WHOLE run falls back to copy mode: every
    families land as REAL Claude directories (none dangling, none missing —
    the "never neither" invariant), the install still succeeds (no
    `SystemExit`), and EXACTLY ONE warning line is printed — never one per
    family. Never guarded by `_require_real_symlinks`: the raiser never
    calls the real `os.symlink` at all."""
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
    assert "falling back to --copy for this run" in warning_lines[0]

    for family in FAMILIES:
        claude_dir = _claude_family_dir(repo, family)
        agents_dir = _agents_family_dir(repo, family)
        assert claude_dir.is_dir(), family
        assert not claude_dir.is_symlink(), family
        assert agents_dir.is_dir(), family
        assert not agents_dir.is_symlink(), family


# ----- stage 9: Nth-call mid-loop failure -----------------------------------


@pytest.mark.integration
def test_e2e_nth_call_symlink_failure_preserves_survivors_names_uncovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Wave-5 stage 9: a `symlink_fn` that raises an EPERM-shaped `OSError`
    on the Nth REAL family conversion (the one-time capability pre-probe
    itself is never made to fail — it is identified by its throwaway probe
    path and always allowed through) aborts every family from the Nth
    onward: already-created links from earlier in the same run SURVIVE, and
    every uncovered family is named in the printed `link error` lines.
    Guarded despite being a DI test: the raiser falls through to the real
    `os.symlink` on every non-failing call (mirrors
    `tests/test_install_link_primitives.py`'s identical "TEST GAP 1")."""
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

    install(scope="project", project_dir=repo, skill_only=True)  # flagless

    survivors = FAMILIES[: fail_at - 1]
    failed_family = FAMILIES[fail_at - 1]
    uncovered = FAMILIES[fail_at:]

    for family in survivors:
        claude_dir = _claude_family_dir(repo, family)
        assert claude_dir.is_symlink(), family
        assert claude_dir.resolve() == _agents_family_dir(repo, family).resolve()
    for family in (failed_family, *uncovered):
        claude_dir = _claude_family_dir(repo, family)
        assert not claude_dir.exists() and not claude_dir.is_symlink(), family

    err = capsys.readouterr().err
    for family in (failed_family, *uncovered):
        assert f"{family}:" in err, family
    # `.agents` stays valid throughout — the failure is entirely on the
    # Claude-linking side, never the real tree link()`.
    for family in FAMILIES:
        assert _agents_family_dir(repo, family).is_dir(), family

    # A rerun (nothing further injected) converges every remaining family.
    install(scope="project", project_dir=repo, skill_only=True)
    for family in FAMILIES:
        classification = classify_family_link(_claude_family_dir(repo, family), repo)
        assert classification.state is FamilyLinkState.OURS_HEALTHY, family


# ----- stage 10: crash-window recovery --------------------------------------


@pytest.mark.integration
def test_e2e_crash_window_temp_artifacts_converge_on_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wave-5 stage 10: leaving BOTH an unpromoted temp link
    (`.<family>.dummyindex-link.tmp`) AND a renamed-aside real tree
    (`.<family>.dummyindex-old.tmp`) behind — simulating a process kill
    partway through the safe-replacement dance, with the family's own slot
    itself still MISSING — a single flagless AUTO rerun converges to a
    healthy canonical link for that family, with both temp artifacts
    cleaned up, and every other (never-touched) family still lands
    correctly too."""
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
    (tmp_old / "SKILL.md").write_text(
        f"---\nname: {family}\ndescription: t\n---\nbody\n", encoding="utf-8"
    )
    (tmp_old / ".dummyindex_version").write_text(PACKAGE_VERSION, encoding="utf-8")

    install(scope="project", project_dir=repo, skill_only=True)  # flagless AUTO rerun

    assert not tmp_link.exists() and not tmp_link.is_symlink()
    assert not tmp_old.exists()
    for check_family in FAMILIES:
        claude_dir = _claude_family_dir(repo, check_family)
        assert claude_dir.is_symlink(), check_family
        assert claude_dir.resolve() == _agents_family_dir(repo, check_family).resolve()


# ----- stage 11: dedupe -- link-only removal, never the .agents target -----


@pytest.mark.integration
def test_e2e_dedupe_removes_linked_side_only_never_the_agents_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wave-5 stage 11 (per checklist.md: "use the existing repair/dedupe
    entry" — the same `dedupe()` call shape `tests/test_install_repair.py`
    already establishes, not a new pattern): a family universally installed
    at BOTH project and user scope is a genuine duplicate at each; deduping
    the user scope's `claude` copy — itself a LINK, since a flagless
    user-scope install links too — removes ONLY that link. The user scope's
    real `.agents` target (the thing the removed link pointed at) survives
    completely untouched."""
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


# ----- stage 12: uninstall --platform agents sweep --------------------------


@pytest.mark.integration
def test_e2e_uninstall_agents_sweep_removes_dangling_links_spares_foreign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Wave-5 stage 12: `uninstall --platform agents` on a fully-linked
    project removes the real `.agents` tree AND every now-dangling
    dummyindex-owned Claude-side link (`remove_dangling_family_links`); a
    separately-planted FOREIGN link (unrelated name, unrelated target)
    survives completely untouched; and — since the narrowing left the
    Claude Code surface with nothing to show — the agents-narrowing warning
    plus its exact recovery command print to stderr."""
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
    assert f"{len(FAMILIES)} Claude-side links" in captured.err
    # The recovery command itself prints to stdout (uninstall.py's own
    # unconditional `print(...)`, no `file=sys.stderr`), right after the
    # stderr warning naming the collateral.
    assert "restore Claude Code without Codex: dummyindex install" in captured.out
    assert "--platform claude" in captured.out


# ----- stage 13: flagless uninstall (both) -> clean tree --------------------


@pytest.mark.integration
def test_e2e_flagless_uninstall_both_leaves_clean_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wave-5 stage 13: a flagless `uninstall` (matching install()'s own
    `platform="both"` default) on a fully-linked, fully-auto-inited project
    leaves neither links nor real families on either host, removes
    `.claude/commands/tokens.md`, and removes the managed AGENTS.md block —
    a genuinely clean tree, symmetric with the flagless install that
    created it."""
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
        # The managed dummyindex block specifically must be gone even if the
        # file survives for some other, non-dummyindex reason.
        assert (
            "dummyindex" not in (repo / "AGENTS.md").read_text(encoding="utf-8").lower()
        )


# ----- stage 14: user-scope leg + dotfiles-divergent fallback ---------------


@pytest.mark.integration
def test_e2e_user_scope_flagless_auto_lifecycle_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wave-5 stage 14 (first leg): a plain user-scope AUTO install/
    uninstall lifecycle passes cleanly with HOME redirected to a scratch
    dir (never the real one) — the universal linked layout lands at user
    scope exactly as it does at project scope, and a flagless uninstall
    cleans it back up."""
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
def test_e2e_user_scope_dotfiles_divergent_link_falls_back_to_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Wave-5 stage 14 (second leg): a dotfiles-symlinked `~/.claude` whose
    RELATIVE link resolution diverges (`~/.claude -> ~/dotfiles-claude`, one
    level OUTSIDE home, so `../../.agents/skills/<family>` computed from
    inside `~/dotfiles-claude/skills/<family>` lands in `~/dotfiles/`, not
    the real home) is the exact shape
    `tests/test_install_link_primitives.py::
    test_create_family_links_detects_dotfiles_divergent_root_and_removes_bad_link`
    already covers at the `create_family_links` layer. Per the spec's own
    Acceptance wording, a flagless user-scope AUTO install against this
    layout falls back to copy mode for the run (a real, working Claude-side
    tree) rather than leaving the user with NEITHER a link nor a real
    directory for any of the families.

    Root-cause fix: `_probe_symlink_capability` now probes the CANONICAL
    RELATIVE value against a real `.agents` family and checks it resolves
    correctly, BEFORE any per-family link is created — so AUTO falls back
    to copy before anything is created/removed, never after an N-created-
    then-8-removed dance (no `link error` transcript lines here, unlike the
    `create_family_links`-layer test above). A second identical run must
    also stay copy with no new link errors and no rewrite of the already-
    real families (no infinite heal churn, per the spec's own wording)."""
    fake_home = _redirect_home(tmp_path, monkeypatch)
    dotfiles_target = tmp_path / "dotfiles-claude"
    dotfiles_target.mkdir()
    (fake_home / ".claude").symlink_to(dotfiles_target, target_is_directory=True)
    _require_real_symlinks(fake_home)

    install(scope="user", skill_only=True)  # flagless, run 1

    out, err = capsys.readouterr()
    for family in FAMILIES:
        # Every family is a real, working Claude-side directory — never a
        # link (the relative value cannot reach the real .agents tree from
        # inside the dotfiles target), and never neither.
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


# ----- focused unit tests: `_probe_symlink_capability`'s resolution check ---


@pytest.mark.unit
def test_probe_symlink_capability_succeeds_on_normal_non_dotfiles_layout(
    tmp_path: Path,
) -> None:
    """The extended probe (capability + resolution) still passes on a
    perfectly ordinary layout — no dotfiles divergence — so this fix never
    regresses the healthy path."""
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
    """The resolution half of the probe: a dotfiles-symlinked `.claude`
    whose relative link value resolves OUTSIDE the real scope root fails the
    probe with a dotfiles-discriminated reason — never the Windows
    capability hint — and cleans up its own temp artifact either way."""
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
    """No real `.agents` family exists yet (should not happen given the
    pinned sequencing that guarantees one before any non-COPY dispatch
    reaches this probe, but must never manufacture a false failure out of
    an unrelated precondition gap): the probe stays capability-only,
    exactly the pre-fix behavior."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"

    ok, detail, hint = _probe_symlink_capability(scope_root, symlink_fn=os.symlink)

    assert ok is True
    assert detail == "ok"
    assert hint == ""
