"""Tests for the `dummyindex/installer/link` primitives, in isolation.

Covers `classify_family_link`'s 6-state alphabet (with the security-sensitive
parent-chain rule and fail-closed OSError/RuntimeError handling), the safe-replacement
dance of `create_family_links` (create, rerun, proven-dir replace, evidence gating,
error isolation, crash recovery), `remove_dangling_family_links` and
`run_link_install`'s AUTO/LINK/COPY orchestration + capability pre-probe.
"""

from __future__ import annotations

import errno
import os
from dataclasses import FrozenInstanceError
from pathlib import Path, PurePath

import pytest

from dummyindex.installer.common import _SIBLING_SKILLS, PACKAGE_VERSION, LinkMode
from dummyindex.installer.link import (
    FamilyLinkClassification,
    FamilyLinkState,
    LinkCapabilityError,
    LinkResult,
    _readlink_parts,
    classify_family_link,
    create_family_links,
    family_link_target,
    relative_link_value,
    remove_dangling_family_links,
    run_link_install,
    verify_family_links,
)
from tests.paths import FIXTURES_DIR

pytestmark = pytest.mark.unit

_LEGACY_SKILL_MD = (FIXTURES_DIR / "legacy_skill_md" / "SKILL.md").read_text(
    encoding="utf-8"
)

# The families, derived from the constant (never a `dummyindex*` glob —
# that would also catch equip's `dummyindex-verify`).
FAMILIES = ("dummyindex", *(label for _sub_name, label in _SIBLING_SKILLS))


# --- shared fixtures


def _require_real_symlinks(tmp_path: Path) -> None:
    """Skip the calling test when this environment cannot create symlinks.

    Only for tests that create REAL symlinks; simulated-failure tests (DI raisers)
    run everywhere.
    """
    probe = tmp_path / ".link-primitive-capability-probe"
    target = tmp_path / ".link-primitive-capability-target"
    target.mkdir(exist_ok=True)
    try:
        probe.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("this environment cannot create symlinks")
        return
    probe.unlink()


def _claude_skills_root(scope_root: Path) -> Path:
    return scope_root / ".claude" / "skills"


def _agents_skills_root(scope_root: Path) -> Path:
    return scope_root / ".agents" / "skills"


def _write_owned_dir(base: Path, version: str = PACKAGE_VERSION) -> Path:
    from dummyindex.installer.ownership import sync_family

    sync_family(
        base,
        {"SKILL.md": "---\nname: dummyindex\ndescription: test\n---\nbody\n"},
        family=base.name,
        version=version,
        force_downgrade=True,
    )
    return base


def _write_owned_agents_family(
    scope_root: Path, family: str, version: str = PACKAGE_VERSION
) -> Path:
    """The real `.agents/skills/<family>` link target — always the source
    of ownership truth a Claude-side link points at."""
    return _write_owned_dir(_agents_skills_root(scope_root) / family, version)


def _seed_all_agents_families(scope_root: Path) -> None:
    for family in FAMILIES:
        _write_owned_agents_family(scope_root, family)


def _write_owned_claude_family(scope_root: Path, family: str) -> Path:
    """A proven, stamped REAL directory on the Claude side (NOT_A_LINK)."""
    return _write_owned_dir(_claude_skills_root(scope_root) / family)


def _write_legacy_heading_claude_family(scope_root: Path, family: str) -> Path:
    """A pre-portable-host install: legacy heading, no stamp at all."""
    family_dir = _claude_skills_root(scope_root) / family
    family_dir.mkdir(parents=True, exist_ok=True)
    (family_dir / "SKILL.md").write_text(_LEGACY_SKILL_MD, encoding="utf-8")
    return family_dir


def _write_unproven_claude_family(scope_root: Path, family: str) -> Path:
    """A dir-name match with neither a stamp nor the legacy heading."""
    family_dir = _claude_skills_root(scope_root) / family
    family_dir.mkdir(parents=True, exist_ok=True)
    (family_dir / "SKILL.md").write_text(
        "---\nname: dummyindex\n---\nunrelated content\n", encoding="utf-8"
    )
    return family_dir


def _symlink_claude_family(
    scope_root: Path, family: str, value: str | None = None
) -> Path:
    """A real symlink at the Claude side; defaults to the canonical value."""
    family_dir = _claude_skills_root(scope_root) / family
    family_dir.parent.mkdir(parents=True, exist_ok=True)
    family_dir.symlink_to(
        value if value is not None else relative_link_value(family),
        target_is_directory=True,
    )
    return family_dir


# classify_family_link


def test_classify_real_directory_is_not_a_link(tmp_path: Path) -> None:
    scope_root = tmp_path / "project"
    family = "dummyindex"
    _write_owned_claude_family(scope_root, family)

    result = classify_family_link(_claude_skills_root(scope_root) / family, scope_root)

    assert result == FamilyLinkClassification(
        family=family,
        path=_claude_skills_root(scope_root) / family,
        state=FamilyLinkState.NOT_A_LINK,
        detail=result.detail,
    )
    assert result.state is FamilyLinkState.NOT_A_LINK


def test_classify_healthy_lexical_relative_link(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    family = "dummyindex"
    _write_owned_agents_family(scope_root, family)
    claude_dir = _symlink_claude_family(scope_root, family)

    result = classify_family_link(claude_dir, scope_root)

    assert result.state is FamilyLinkState.OURS_HEALTHY


def test_classify_healthy_resolved_absolute_link(tmp_path: Path) -> None:
    """An absolute link that RESOLVES to the real family (not the canonical
    relative string) is still OURS_HEALTHY — `create_family_links` is what
    normalizes its form, classification just recognizes it as ours."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    family = "dummyindex"
    agents_dir = _write_owned_agents_family(scope_root, family)
    claude_dir = _symlink_claude_family(scope_root, family, value=str(agents_dir))

    result = classify_family_link(claude_dir, scope_root)

    assert result.state is FamilyLinkState.OURS_HEALTHY


def test_classify_dangling_link_target_confirmed_absent(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    family = "dummyindex"
    # Deliberately no `.agents/skills/dummyindex` at all.
    claude_dir = _symlink_claude_family(scope_root, family)

    result = classify_family_link(claude_dir, scope_root)

    assert result.state is FamilyLinkState.OURS_DANGLING


def test_classify_missing_path(tmp_path: Path) -> None:
    scope_root = tmp_path / "project"
    family = "dummyindex"

    result = classify_family_link(_claude_skills_root(scope_root) / family, scope_root)

    assert result.state is FamilyLinkState.MISSING


def test_classify_materialized_file_matches_link_value_exactly(tmp_path: Path) -> None:
    scope_root = tmp_path / "project"
    family = "dummyindex"
    family_path = _claude_skills_root(scope_root) / family
    family_path.parent.mkdir(parents=True, exist_ok=True)
    family_path.write_text(relative_link_value(family), encoding="utf-8")

    result = classify_family_link(family_path, scope_root)

    assert result.state is FamilyLinkState.MATERIALIZED


def test_classify_regular_file_with_wrong_content_is_not_a_link(tmp_path: Path) -> None:
    scope_root = tmp_path / "project"
    family = "dummyindex"
    family_path = _claude_skills_root(scope_root) / family
    family_path.parent.mkdir(parents=True, exist_ok=True)
    family_path.write_text("not a link value\n", encoding="utf-8")

    result = classify_family_link(family_path, scope_root)

    assert result.state is FamilyLinkState.NOT_A_LINK


def test_classify_unstatable_leaf_is_foreign_not_missing(tmp_path: Path) -> None:
    """An unstatable leaf (ENOTDIR: `.claude/skills` is a regular file) is FOREIGN,
    never MISSING. `.is_symlink()`/`.exists()` swallow ENOTDIR/ELOOP/EBADF into `False`
    on py3.10-3.13, and MISSING needs no ownership evidence ("an empty path is safe
    to fill"), so an unstatable path must never pass as empty."""
    scope_root = tmp_path / "project"
    scope_root.mkdir()
    claude_dir = scope_root / ".claude"
    claude_dir.mkdir()
    (claude_dir / "skills").write_text("not a directory\n", encoding="utf-8")
    family = "dummyindex"

    result = classify_family_link(claude_dir / "skills" / family, scope_root)

    assert result.state is FamilyLinkState.FOREIGN
    assert result.state is not FamilyLinkState.MISSING


def test_classify_foreign_link_value(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    family = "dummyindex"
    _write_owned_agents_family(scope_root, family)
    claude_dir = _symlink_claude_family(scope_root, family, value="../elsewhere")

    result = classify_family_link(claude_dir, scope_root)

    assert result.state is FamilyLinkState.FOREIGN


def test_classify_foreign_absolute_link_that_does_not_resolve_to_target(
    tmp_path: Path,
) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    family = "dummyindex"
    _write_owned_agents_family(scope_root, family)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    claude_dir = _symlink_claude_family(scope_root, family, value=str(unrelated))

    result = classify_family_link(claude_dir, scope_root)

    assert result.state is FamilyLinkState.FOREIGN


def test_classify_symlinked_claude_parent_forces_foreign_at_project_scope(
    tmp_path: Path,
) -> None:
    """SECURITY: a symlinked `.claude` at PROJECT scope forces FOREIGN even
    though the leaf link looks perfect — otherwise a `.claude -> /victim`
    layout would make heal/sweep unlink inside the victim tree."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    scope_root.mkdir()
    victim = tmp_path / "victim"
    (victim / "skills" / "dummyindex").mkdir(parents=True)
    (scope_root / ".claude").symlink_to(victim, target_is_directory=True)
    family = "dummyindex"
    _write_owned_agents_family(scope_root, family)
    # Reached through the symlinked `.claude`, the leaf looks like a healthy link.
    (victim / "skills" / "dummyindex").rmdir()
    (victim / "skills" / "dummyindex").symlink_to(
        relative_link_value(family), target_is_directory=True
    )

    result = classify_family_link(_claude_skills_root(scope_root) / family, scope_root)

    assert result.state is FamilyLinkState.FOREIGN
    assert "symlink" in result.detail


def test_classify_symlinked_claude_skills_parent_forces_foreign(
    tmp_path: Path,
) -> None:
    """A symlinked `.claude/skills` (one level deeper) is FOREIGN: a call with no
    allowlist always refuses it."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    scope_root.mkdir()
    (scope_root / ".claude").mkdir()
    victim = tmp_path / "victim-skills"
    victim.mkdir()
    (scope_root / ".claude" / "skills").symlink_to(victim, target_is_directory=True)
    family = "dummyindex"
    _write_owned_agents_family(scope_root, family)

    result = classify_family_link(_claude_skills_root(scope_root) / family, scope_root)

    assert result.state is FamilyLinkState.FOREIGN


def test_classify_explicit_allowlisted_host_root_permits_healthy(
    tmp_path: Path,
) -> None:
    """The dotfiles allowance is an EXPLICIT caller-passed `allowed_symlinks`, never
    inferred from `HOME`; an allowlisted top-level `.claude` passes the parent-chain
    rule (the resolution check separately catches real divergence)."""
    _require_real_symlinks(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    dotfiles_target = tmp_path / "dotfiles-claude"
    dotfiles_target.mkdir()
    (home / ".claude").symlink_to(dotfiles_target, target_is_directory=True)
    family = "dummyindex"
    agents_dir = _write_owned_agents_family(home, family)
    # An absolute value straight at the real target isolates the PARENT-CHAIN
    # allowance; the dotfiles-DIVERGENT relative case is its own test below.
    claude_dir = _symlink_claude_family(home, family, value=str(agents_dir))

    result = classify_family_link(
        claude_dir, home, allowed_symlinks=frozenset({home / ".claude"})
    )

    assert result.state is FamilyLinkState.OURS_HEALTHY


def test_classify_home_spoof_does_not_flip_foreign_to_ours_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SECURITY: with the fail-closed default (no `allowed_symlinks`), a symlinked
    `.claude` at PROJECT scope stays FOREIGN whatever `HOME` says, so a spoofed `HOME`
    (CI, containers, wrappers) can't admit it. The module never reads `HOME`, so this
    also covers the non-spoofed case."""
    _require_real_symlinks(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    dotfiles_target = tmp_path / "dotfiles-claude"
    dotfiles_target.mkdir()
    (project / ".claude").symlink_to(dotfiles_target, target_is_directory=True)
    family = "dummyindex"
    _write_owned_agents_family(project, family)

    # HOME-spoof: HOME at the project root must NOT allowlist the symlink.
    monkeypatch.setenv("HOME", str(project))
    monkeypatch.setenv("USERPROFILE", str(project))

    result = classify_family_link(_claude_skills_root(project) / family, project)

    assert result.state is FamilyLinkState.FOREIGN


def test_classify_dotfiles_divergent_lexically_canonical_link_is_foreign(
    tmp_path: Path,
) -> None:
    """An ALLOWLISTED dotfiles `.claude` hop with a lexically canonical value is still
    resolution-checked: from inside the dotfiles repo `../..` never reaches home's
    `.agents`, so it is FOREIGN; as OURS_* the sweep would unlink a dotfiles file."""
    _require_real_symlinks(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    dotfiles_target = tmp_path / "dotfiles-claude"
    (dotfiles_target / "skills").mkdir(parents=True)
    (home / ".claude").symlink_to(dotfiles_target, target_is_directory=True)
    family = "dummyindex"
    leaf = dotfiles_target / "skills" / family
    leaf.symlink_to(relative_link_value(family), target_is_directory=True)
    _write_owned_agents_family(home, family)

    result = classify_family_link(
        home / ".claude" / "skills" / family,
        home,
        allowed_symlinks=frozenset({home / ".claude"}),
    )

    assert result.state is FamilyLinkState.FOREIGN


def test_classify_symlink_loop_is_foreign_never_dangling(tmp_path: Path) -> None:
    """A symlink loop must never be misread as DANGLING (positively-absent) —
    `_target_exists` returns ambiguous (None) for ELOOP, and ambiguous is
    always FOREIGN."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    scope_root.mkdir()
    family = "dummyindex"
    claude_dir = _symlink_claude_family(scope_root, family)
    # Loop the .agents side back into the .claude side so following it raises ELOOP.
    agents_dir = _agents_skills_root(scope_root) / family
    agents_dir.parent.mkdir(parents=True, exist_ok=True)
    agents_dir.symlink_to(claude_dir, target_is_directory=True)

    result = classify_family_link(claude_dir, scope_root)

    assert result.state is FamilyLinkState.FOREIGN
    assert result.state is not FamilyLinkState.OURS_DANGLING


def test_classify_target_unstatable_for_other_reason_is_never_dangling(
    tmp_path: Path,
) -> None:
    """A target that exists but can't be statted for a reason OTHER than
    absence (permission denied on an ancestor) must never be DANGLING."""
    _require_real_symlinks(tmp_path)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("chmod 0o000 does not deny root")
    scope_root = tmp_path / "project"
    family = "dummyindex"
    _write_owned_agents_family(scope_root, family)
    claude_dir = _symlink_claude_family(scope_root, family)
    agents_skills_root = _agents_skills_root(scope_root)
    os.chmod(agents_skills_root, 0o000)
    try:
        result = classify_family_link(claude_dir, scope_root)
    finally:
        os.chmod(agents_skills_root, 0o755)

    assert result.state is FamilyLinkState.FOREIGN
    assert result.state is not FamilyLinkState.OURS_DANGLING


def test_classify_fails_closed_on_unexpected_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any OSError/RuntimeError raised during classification is caught and
    reported as FOREIGN (mirrors `repair.py`'s `_same_root`)."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    family = "dummyindex"
    _write_owned_agents_family(scope_root, family)
    claude_dir = _symlink_claude_family(scope_root, family)

    def _boom(*_a, **_k):
        raise RuntimeError("simulated classification blowup")

    monkeypatch.setattr(os, "readlink", _boom)

    result = classify_family_link(claude_dir, scope_root)

    assert result.state is FamilyLinkState.FOREIGN
    assert "simulated classification blowup" in result.detail


def test_classify_cross_scope_root_is_scope_sensitive(tmp_path: Path) -> None:
    """SECURITY-adjacent: classification uses the copy's OWN scope root. The same
    absolute link is OURS_HEALTHY there and FOREIGN against another root, so a caller
    must never substitute the invocation's root."""
    _require_real_symlinks(tmp_path)
    scope_a = tmp_path / "project-a"
    scope_b = tmp_path / "project-b"
    family = "dummyindex"
    agents_a = _write_owned_agents_family(scope_a, family)
    _write_owned_agents_family(scope_b, family)
    claude_dir = _symlink_claude_family(scope_a, family, value=str(agents_a))

    correct = classify_family_link(claude_dir, scope_a)
    wrong = classify_family_link(claude_dir, scope_b)

    assert correct.state is FamilyLinkState.OURS_HEALTHY
    assert wrong.state is FamilyLinkState.FOREIGN


def test_classify_wrong_scope_root_does_not_disarm_parent_chain_check(
    tmp_path: Path,
) -> None:
    """SECURITY: a WRONG `scope_root` must never disarm the parent-chain check.
    `_first_symlink_component` fails OPEN (`None`, "chain clean") when `relative_to`
    raises for an out-of-tree path, so a `.claude -> /victim` layout must be FOREIGN
    against both its own root and a foreign one."""
    _require_real_symlinks(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (project / ".claude").symlink_to(victim, target_is_directory=True)
    family = "dummyindex"
    _write_owned_agents_family(project, family)
    wrong_root = tmp_path / "unrelated"
    wrong_root.mkdir()

    against_own_root = classify_family_link(
        _claude_skills_root(project) / family, project
    )
    against_wrong_root = classify_family_link(
        _claude_skills_root(project) / family, wrong_root
    )

    assert against_own_root.state is FamilyLinkState.FOREIGN
    assert against_wrong_root.state is FamilyLinkState.FOREIGN


def test_readlink_parts_posix_value_splits_on_forward_slash() -> None:
    raw = "../../.agents/skills/dummyindex"
    assert _readlink_parts(raw) == ("..", "..", ".agents", "skills", "dummyindex")


def test_readlink_parts_posix_never_reinterprets_backslash_as_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On POSIX a backslash is a legal filename character, so the value
    `..\\..\\.agents\\skills\\dummyindex` stays ONE opaque component, never re-split
    via `PureWindowsPath`."""
    monkeypatch.setattr(os, "name", "posix")
    raw = "..\\..\\.agents\\skills\\dummyindex"
    assert _readlink_parts(raw) == (raw,)


def test_readlink_parts_windows_round_trip_splits_natively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On Windows `PurePath` IS `PureWindowsPath` (picked off `os.name`), so a
    readlink value normalized to `\\` splits natively, with no special-casing."""
    monkeypatch.setattr(os, "name", "nt")
    raw = "..\\..\\.agents\\skills\\dummyindex"
    assert _readlink_parts(raw) == ("..", "..", ".agents", "skills", "dummyindex")


def test_family_link_target_and_relative_link_value() -> None:
    scope_root = Path("/scope")
    assert relative_link_value("dummyindex") == "../../.agents/skills/dummyindex"
    assert family_link_target(scope_root, "dummyindex") == (
        scope_root / ".agents" / "skills" / "dummyindex"
    )


def test_verify_family_links_sweeps_every_family_read_only(
    tmp_path: Path,
) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    for family in FAMILIES:
        _symlink_claude_family(scope_root, family)

    results = verify_family_links(scope_root)

    assert len(results) == len(FAMILIES)
    assert {r.family for r in results} == set(FAMILIES)
    assert all(r.state is FamilyLinkState.OURS_HEALTHY for r in results)


# create_family_links — the safe replacement dance


def test_create_family_links_fresh_create_every_family(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)

    result = create_family_links(scope_root)

    assert set(result.created) == set(FAMILIES)
    assert result.replaced == ()
    assert result.skipped == ()
    assert result.errors == ()
    for family in FAMILIES:
        family_dir = _claude_skills_root(scope_root) / family
        assert family_dir.is_symlink()
        raw = os.readlink(family_dir)
        assert PurePath(raw).parts == PurePath(relative_link_value(family)).parts
        assert (
            family_dir.resolve() == (_agents_skills_root(scope_root) / family).resolve()
        )


def test_create_family_links_idempotent_rerun_is_zero_zero(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    create_family_links(scope_root)
    family_dir = _claude_skills_root(scope_root) / "dummyindex"
    before_ino = family_dir.lstat().st_ino

    result = create_family_links(scope_root)

    assert result == LinkResult(created=(), replaced=(), skipped=(), errors=())
    assert family_dir.lstat().st_ino == before_ino  # untouched, not recreated


def test_create_family_links_replaces_proven_real_directory(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_dir = _write_owned_claude_family(scope_root, family)
    assert claude_dir.is_dir() and not claude_dir.is_symlink()

    result = create_family_links(scope_root)

    assert family in result.replaced
    assert family not in result.created
    assert claude_dir.is_symlink()
    assert claude_dir.resolve() == (_agents_skills_root(scope_root) / family).resolve()
    # The old real tree is gone — no temp artifact left behind.
    leftovers = list(_claude_skills_root(scope_root).glob(f".{family}.dummyindex-*"))
    assert leftovers == []


def test_create_family_links_refuses_heading_only_real_directory(
    tmp_path: Path,
) -> None:
    """Replacement evidence is the STAMP, not the heading: a legacy-heading
    real dir (no `.dummyindex_version`) is reported, never destroyed."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_dir = _write_legacy_heading_claude_family(scope_root, family)
    before = (claude_dir / "SKILL.md").read_text(encoding="utf-8")

    result = create_family_links(scope_root)

    assert family not in result.replaced
    assert family not in result.created
    assert any(s.startswith(f"{family}:") for s in result.skipped)
    assert claude_dir.is_dir() and not claude_dir.is_symlink()
    assert (claude_dir / "SKILL.md").read_text(encoding="utf-8") == before


def test_create_family_links_refuses_unproven_real_directory(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_dir = _write_unproven_claude_family(scope_root, family)
    before = (claude_dir / "SKILL.md").read_text(encoding="utf-8")

    result = create_family_links(scope_root)

    assert family not in result.replaced
    assert family not in result.created
    assert any(s.startswith(f"{family}:") for s in result.skipped)
    assert claude_dir.is_dir() and not claude_dir.is_symlink()
    assert (claude_dir / "SKILL.md").read_text(encoding="utf-8") == before


def test_create_family_links_replaces_materialized_file(tmp_path: Path) -> None:
    """The `core.symlinks=false` Windows checkout shape: a regular file
    whose exact content is the link value. AUTO/LINK replaces it."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    materialized = _claude_skills_root(scope_root) / family
    materialized.parent.mkdir(parents=True, exist_ok=True)
    materialized.write_text(relative_link_value(family), encoding="utf-8")

    result = create_family_links(scope_root)

    assert family in result.replaced
    assert materialized.is_symlink()
    assert (
        materialized.resolve() == (_agents_skills_root(scope_root) / family).resolve()
    )


def test_create_family_links_normalizes_absolute_but_correct_link(
    tmp_path: Path,
) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    agents_dir = _agents_skills_root(scope_root) / family
    claude_dir = _symlink_claude_family(scope_root, family, value=str(agents_dir))

    result = create_family_links(scope_root)

    assert family in result.replaced
    assert family not in result.created
    raw = os.readlink(claude_dir)
    assert PurePath(raw).parts == PurePath(relative_link_value(family)).parts


def test_create_family_links_heals_a_dangling_link_once_target_exists(
    tmp_path: Path,
) -> None:
    """Acceptance: 'an AUTO rerun heals a dangling link via
    create_family_links'."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    scope_root.mkdir()
    family = "dummyindex"
    claude_dir = _symlink_claude_family(scope_root, family)
    assert (
        classify_family_link(claude_dir, scope_root).state
        is FamilyLinkState.OURS_DANGLING
    )
    _write_owned_agents_family(scope_root, family)

    create_family_links(scope_root)

    assert (
        classify_family_link(claude_dir, scope_root).state
        is FamilyLinkState.OURS_HEALTHY
    )


def test_create_family_links_detects_dotfiles_divergent_root_and_removes_bad_link(
    tmp_path: Path,
) -> None:
    """With `~/.claude` symlinked outside home, the relative `../..` misses the real
    home: the created link is verified, found to diverge, removed and reported, never
    left broken. `allowed_symlinks` is explicit; nothing is inferred from `HOME`."""
    _require_real_symlinks(tmp_path)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    dotfiles_target = tmp_path / "dotfiles-claude"
    dotfiles_target.mkdir()
    (fake_home / ".claude").symlink_to(dotfiles_target, target_is_directory=True)
    _seed_all_agents_families(fake_home)

    result = create_family_links(
        fake_home, allowed_symlinks=frozenset({fake_home / ".claude"})
    )

    family = "dummyindex"
    claude_family_dir = fake_home / ".claude" / "skills" / family
    assert not claude_family_dir.exists()
    assert not claude_family_dir.is_symlink()
    assert any(e.startswith(f"{family}:") for e in result.errors)
    assert any("dotfiles" in e for e in result.errors)
    assert family not in result.created
    assert family not in result.replaced


def test_create_family_links_file_exists_error_reclassifies_and_retries(
    tmp_path: Path,
) -> None:
    """`FileExistsError` creating the temp link re-classifies and
    replaces-or-reports the family, then continues — never a hard abort.

    Guarded although simulated: `_flaky_symlink` falls through to the REAL
    `os.symlink` after its first call, so an incapable host must skip, not fail."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    calls = {"n": 0}

    def _flaky_symlink(src, dst, *, target_is_directory=False):
        calls["n"] += 1
        if calls["n"] == 1:
            raise FileExistsError(errno.EEXIST, "File exists")
        os.symlink(src, dst, target_is_directory=target_is_directory)

    result = create_family_links(scope_root, symlink_fn=_flaky_symlink)

    assert family in result.created
    assert calls["n"] >= 2
    assert result.errors == ()


def test_create_family_links_nth_call_capability_failure_aborts_remaining(
    tmp_path: Path,
) -> None:
    """An EPERM/winerror-shaped OSError on the Nth family aborts every
    REMAINING family (already-created links stay) and names every family
    left uncovered.

    Guarded although simulated: `_counting_raiser` calls the REAL `os.symlink` on
    every non-failing call, so an incapable host must skip, not fail."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    fail_at = 4
    calls = {"n": 0}

    def _counting_raiser(src, dst, *, target_is_directory=False):
        calls["n"] += 1
        if calls["n"] == fail_at:
            raise OSError(errno.EPERM, "Operation not permitted")
        os.symlink(src, dst, target_is_directory=target_is_directory)

    result = create_family_links(scope_root, symlink_fn=_counting_raiser)

    survivors = FAMILIES[: fail_at - 1]
    failed_family = FAMILIES[fail_at - 1]
    uncovered = FAMILIES[fail_at:]

    assert set(result.created) == set(survivors)
    assert result.replaced == ()
    assert any(e.startswith(f"{failed_family}:") for e in result.errors)
    for name in uncovered:
        assert any(e.startswith(f"{name}:") for e in result.errors)
    assert len(result.errors) == 1 + len(uncovered)
    # Survivors' links are real and untouched by the abort.
    for family in survivors:
        assert (_claude_skills_root(scope_root) / family).is_symlink()
    for family in (failed_family, *uncovered):
        assert not (_claude_skills_root(scope_root) / family).exists()


def test_create_family_links_crash_recovery_cleans_unpromoted_temp_link(
    tmp_path: Path,
) -> None:
    """A crash between "create the temp link" and "promote it" leaves only
    the disposable temp artifact. A rerun cleans it and fills MISSING."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_skills_root = _claude_skills_root(scope_root)
    claude_skills_root.mkdir(parents=True, exist_ok=True)
    tmp_link = claude_skills_root / f".{family}.dummyindex-link.tmp"
    tmp_link.symlink_to("stale-crash-artifact", target_is_directory=True)

    result = create_family_links(scope_root)

    assert not tmp_link.exists() and not tmp_link.is_symlink()
    assert family in result.created
    family_dir = claude_skills_root / family
    assert family_dir.is_symlink()
    assert family_dir.resolve() == (_agents_skills_root(scope_root) / family).resolve()


def test_create_family_links_crash_recovery_restores_renamed_aside_tree(
    tmp_path: Path,
) -> None:
    """A crash between "rename the real copy aside" and "promote the link"
    leaves the renamed-aside tree with an empty family path. A rerun moves
    it straight back and redoes the replace dance from a clean state."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_skills_root = _claude_skills_root(scope_root)
    tmp_old = claude_skills_root / f".{family}.dummyindex-old.tmp"
    _write_owned_dir(tmp_old)
    # family_dir is absent: the rename-aside completed, promotion never landed.

    result = create_family_links(scope_root)

    assert not tmp_old.exists()
    family_dir = claude_skills_root / family
    assert family_dir.is_symlink()
    assert family in result.replaced


def test_create_family_links_crash_recovery_finishes_deferred_delete(
    tmp_path: Path,
) -> None:
    """A crash between "promote the link" and "delete the renamed-aside
    tree" leaves a healthy link AND a leftover renamed-aside tree. A rerun
    finishes the deferred delete without touching the already-healthy link."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_skills_root = _claude_skills_root(scope_root)
    family_dir = _symlink_claude_family(scope_root, family)
    tmp_old = claude_skills_root / f".{family}.dummyindex-old.tmp"
    _write_owned_dir(tmp_old)
    before_ino = family_dir.lstat().st_ino

    result = create_family_links(scope_root)

    assert not tmp_old.exists()
    assert family_dir.is_symlink()
    assert family_dir.lstat().st_ino == before_ino  # never touched
    assert family not in result.created
    assert family not in result.replaced


def test_create_family_links_refuses_to_touch_through_symlinked_claude_parent(
    tmp_path: Path,
) -> None:
    """SECURITY: through a symlinked `.claude` (family path OCCUPIED in the victim),
    the run refuses on one parent-chain check before `mkdir`: every family lands in
    `errors` and nothing under `victim` is touched. The UNOCCUPIED variant below is
    the one that pins gate ordering."""
    _require_real_symlinks(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    victim = tmp_path / "victim"
    victim_skills = victim / "skills"
    victim_skills.mkdir(parents=True)
    (project / ".claude").symlink_to(victim, target_is_directory=True)

    family = "dummyindex"
    # A leftover stamped temp-old tree under the victim, with a payload NOT ours.
    tmp_old = victim_skills / f".{family}.dummyindex-old.tmp"
    _write_owned_dir(tmp_old)
    (tmp_old / "USER_DATA.txt").write_text("not ours\n", encoding="utf-8")
    # The family path itself is occupied inside the victim tree too.
    occupied = victim_skills / family
    occupied.mkdir()
    (occupied / "OCCUPANT.txt").write_text("victim's own data\n", encoding="utf-8")

    _write_owned_agents_family(project, family)

    result = create_family_links(project)

    assert (tmp_old / "USER_DATA.txt").exists()
    assert (occupied / "OCCUPANT.txt").exists()
    assert tmp_old.exists()
    assert occupied.exists()
    assert any(s.startswith(f"{family}:") for s in result.errors)
    assert family not in result.created
    assert family not in result.replaced


def test_create_family_links_refuses_recovery_rename_through_symlinked_claude_parent(
    tmp_path: Path,
) -> None:
    """SECURITY: family path UNOCCUPIED, the variant that pins gate ordering: the
    victim's leftover `tmp_old` must never be renamed into the family path. The run
    refuses before `mkdir` and every family is reported in `errors`."""
    _require_real_symlinks(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    victim = tmp_path / "victim"
    victim_skills = victim / "skills"
    victim_skills.mkdir(parents=True)
    (project / ".claude").symlink_to(victim, target_is_directory=True)

    family = "dummyindex"
    tmp_old = victim_skills / f".{family}.dummyindex-old.tmp"
    _write_owned_dir(tmp_old)
    (tmp_old / "USER_DATA.txt").write_text("not ours\n", encoding="utf-8")
    # Family path itself deliberately absent this time.

    _write_owned_agents_family(project, family)

    result = create_family_links(project)

    assert tmp_old.exists()
    assert (tmp_old / "USER_DATA.txt").exists()
    assert not (victim_skills / family).exists()
    assert any(s.startswith(f"{family}:") for s in result.errors)


def test_create_family_links_squatted_temp_link_directory_is_reported_not_deleted(
    tmp_path: Path,
) -> None:
    """`_silently_remove` never recurses into a directory: `is_dir()` is not
    ownership evidence. A directory squatting the temp-link name, with a payload,
    is reported and never deleted."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_skills_root = _claude_skills_root(scope_root)
    claude_skills_root.mkdir(parents=True, exist_ok=True)
    squatted = claude_skills_root / f".{family}.dummyindex-link.tmp"
    squatted.mkdir()
    (squatted / "NOT_OURS.txt").write_text("payload\n", encoding="utf-8")

    result = create_family_links(scope_root)

    assert squatted.is_dir()
    assert (squatted / "NOT_OURS.txt").exists()
    assert (squatted / "NOT_OURS.txt").read_text(encoding="utf-8") == "payload\n"
    assert family not in result.created
    assert family not in result.replaced
    assert any(e.startswith(f"{family}:") for e in result.errors)


def test_create_family_links_permission_error_during_removal_does_not_abort_others(
    tmp_path: Path,
) -> None:
    """A `PermissionError` deleting one family's renamed-aside tree never aborts the
    other 7. The link IS promoted, so it reports `replaced` plus a named warning,
    not an opaque `error`: only cleanup failed."""
    _require_real_symlinks(tmp_path)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ignores directory permission bits")
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_dir = _write_owned_claude_family(scope_root, family)
    locked = claude_dir / "locked"
    locked.mkdir()
    (locked / "file.txt").write_text("x", encoding="utf-8")
    from dummyindex.installer.ownership import sync_family

    sync_family(
        claude_dir,
        {
            "SKILL.md": (claude_dir / "SKILL.md").read_text(encoding="utf-8"),
            "locked/file.txt": "x",
        },
        family=family,
        version=PACKAGE_VERSION,
    )
    os.chmod(locked, 0o500)  # no write perm on the dir -> unlink(child) fails

    try:
        result = create_family_links(scope_root)
    finally:
        # The delete fails on the RENAMED-ASIDE tree, so `locked` may have moved:
        # restore write permission wherever it ended up so pytest can clean up.
        for locked_dir in _claude_skills_root(scope_root).rglob("locked"):
            os.chmod(locked_dir, 0o700)

    assert result.errors == ()
    assert family in result.replaced
    assert any(s.startswith(f"{family}:") for s in result.skipped)
    for other in FAMILIES:
        if other == family:
            continue
        assert (_claude_skills_root(scope_root) / other).is_symlink()


def test_create_family_links_claude_skills_as_regular_file_reports_errors_not_crash(
    tmp_path: Path,
) -> None:
    """HIGH-3: `.claude/skills` being a regular file makes `mkdir` raise
    before any family is attempted — must degrade to reported errors (one
    per family), never escape as an uncaught exception."""
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    claude_dir = scope_root / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "skills").write_text("not a directory\n", encoding="utf-8")

    result = create_family_links(scope_root)

    assert len(result.errors) == len(FAMILIES)
    assert result.created == ()
    assert result.replaced == ()


def test_create_family_links_refuses_mkdir_through_symlinked_claude_parent(
    tmp_path: Path,
) -> None:
    """SECURITY: `create_family_links` gates its `mkdir` on the parent chain, so a
    `project/.claude -> ../victim` layout never gets `victim/skills` created: even a
    non-destructive write through an attacker-placed symlink is forbidden. Only this
    public entry reaches it; `run_link_install`'s probe gates first."""
    _require_real_symlinks(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (project / ".claude").symlink_to(victim, target_is_directory=True)
    _seed_all_agents_families(project)

    result = create_family_links(project)

    assert not (victim / "skills").exists()
    assert len(result.errors) == len(FAMILIES)
    assert result.created == ()
    assert result.replaced == ()
    assert all("symlink" in e for e in result.errors)


def test_create_family_links_reverify_after_rename_requires_stamp_not_heading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The POST-rename re-verify is never looser than the classify-time gate: if the
    stamp vanishes between check and rename (TOCTOU), leaving only the legacy heading
    `is_owned_copy` accepts, the renamed-aside tree is restored, never destroyed."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_dir = _write_owned_claude_family(scope_root, family)

    real_rename = Path.rename

    def _rename_then_strip_stamp(self: Path, target: object) -> object:
        result = real_rename(self, target)
        if self == claude_dir:
            stamp = Path(target) / ".dummyindex_version"
            if stamp.exists():
                stamp.unlink()
                (Path(target) / "SKILL.md").write_text(
                    _LEGACY_SKILL_MD, encoding="utf-8"
                )
        return result

    monkeypatch.setattr(Path, "rename", _rename_then_strip_stamp)

    result = create_family_links(scope_root)

    assert family not in result.replaced
    assert any(e.startswith(f"{family}:") for e in result.errors)
    assert claude_dir.is_dir() and not claude_dir.is_symlink()
    assert not (claude_dir / ".dummyindex_version").exists()
    assert "Codex host compatibility" in (claude_dir / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_create_family_links_refuses_to_create_when_agents_family_missing(
    tmp_path: Path,
) -> None:
    """With no real `.agents/skills/<family>` to link to, nothing is `created`: the
    post-create check (`resolve(strict=False)`) is lexical and can't see a missing target."""
    scope_root = tmp_path / "project"

    result = create_family_links(scope_root)

    assert result.created == ()
    assert result.replaced == ()
    assert all("no .agents family to link to" in s for s in result.skipped)
    for family in FAMILIES:
        assert not (_claude_skills_root(scope_root) / family).exists()


def test_recover_leftover_temp_old_not_deleted_when_family_dir_is_foreign(
    tmp_path: Path,
) -> None:
    """Mere occupancy of `family_dir` never triggers finish-delete of a leftover
    `.dummyindex-old.tmp`; only an OURS_HEALTHY `family_dir` (our promotion) does."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_skills_root = _claude_skills_root(scope_root)
    tmp_old = claude_skills_root / f".{family}.dummyindex-old.tmp"
    _write_owned_dir(tmp_old)
    family_dir = claude_skills_root / family
    outside = tmp_path / "outside"
    outside.mkdir()
    family_dir.symlink_to(outside, target_is_directory=True)

    create_family_links(scope_root)

    assert tmp_old.exists()  # never finish-deleted
    assert family_dir.is_symlink()
    assert os.readlink(family_dir) == str(outside)  # untouched


def test_recover_leftover_temp_old_not_relocated_when_unproven(tmp_path: Path) -> None:
    """A foreign dir squatting our reserved `tmp_old` name is never relocated into the
    family path, where it would silently block conversion: the rename requires
    `is_owned_copy(tmp_old)`. It is reported, and the missing link is still created."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_skills_root = _claude_skills_root(scope_root)
    tmp_old = claude_skills_root / f".{family}.dummyindex-old.tmp"
    tmp_old.mkdir(parents=True)
    (tmp_old / "NOT_OURS.txt").write_text("foreign\n", encoding="utf-8")
    family_dir = claude_skills_root / family

    result = create_family_links(scope_root)

    # The foreign squat must never have been relocated into family_dir.
    assert tmp_old.is_dir()
    assert (tmp_old / "NOT_OURS.txt").exists()
    # The family's own new link is still created normally alongside it.
    assert family_dir.is_symlink()
    assert family in result.created
    assert any(family in s and str(tmp_old) in s for s in result.skipped)


def test_create_family_links_partial_delete_leaves_stranded_tmp_old_named_on_every_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_remove_owned_tree_no_follow` is non-atomic and deletes in `iterdir()` order, so
    it can destroy `.dummyindex_version`/SKILL.md before failing on a locked subdir
    (`chmod 0500 sub`), stranding user data at `.dummyindex-old.tmp` with no ownership
    evidence. Run 1 reports `replaced` + a named warning; every later run, even with a
    healthy link and nothing else to do, still NAMES the stranded path."""
    _require_real_symlinks(tmp_path)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ignores directory permission bits")
    # `iterdir()` order isn't guaranteed; sorted() pins the "evidence destroyed
    # first" order (`.dummyindex_version` sorts ahead of `sub`).
    real_iterdir = Path.iterdir
    monkeypatch.setattr(Path, "iterdir", lambda self: iter(sorted(real_iterdir(self))))
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_dir = _write_owned_claude_family(scope_root, family)
    sub = claude_dir / "sub"
    sub.mkdir()
    from dummyindex.installer.ownership import sync_family

    sync_family(
        claude_dir,
        {
            "SKILL.md": (claude_dir / "SKILL.md").read_text(encoding="utf-8"),
            "sub/USER_DATA.txt": "owned fixture data\n",
        },
        family=family,
        version=PACKAGE_VERSION,
    )
    os.chmod(sub, 0o500)  # no write perm -> unlink(child) fails partway through

    claude_family_dir = _claude_skills_root(scope_root) / family
    tmp_old = _claude_skills_root(scope_root) / f".{family}.dummyindex-old.tmp"

    try:
        # --- Run 1: the link promotes, but deleting the renamed-aside copy
        # fails partway, after destroying its ownership evidence.
        result_1 = create_family_links(scope_root)

        assert (
            classify_family_link(claude_family_dir, scope_root).state
            is FamilyLinkState.OURS_HEALTHY
        )
        assert family in result_1.replaced
        assert not any(e.startswith(f"{family}:") for e in result_1.errors)
        assert tmp_old.exists()
        assert not (tmp_old / ".dummyindex_version").exists()  # evidence gone
        assert (tmp_old / "sub" / "USER_DATA.txt").exists()  # user data survives
        assert any(family in s and str(tmp_old) in s for s in result_1.skipped)

        # --- Run 2 (still locked): a healthy link must not hide the stranded tmp_old.
        result_2 = create_family_links(scope_root)

        assert tmp_old.exists()
        assert result_2.skipped != ()
        assert any(family in s and str(tmp_old) in s for s in result_2.skipped)
        assert (
            classify_family_link(claude_family_dir, scope_root).state
            is FamilyLinkState.OURS_HEALTHY
        )

        # --- Run 3 (permissions fixed): never auto-deleted without ownership
        # evidence, but still reported every time. `sub` now lives under `tmp_old`.
        os.chmod(tmp_old / "sub", 0o700)
        result_3 = create_family_links(scope_root)

        assert tmp_old.exists()
        assert any(family in s and str(tmp_old) in s for s in result_3.skipped)
    finally:
        for locked in (sub, tmp_old / "sub"):
            if locked.exists():
                os.chmod(locked, 0o700)


def test_finish_replace_real_reports_stranded_original_when_restore_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the promote (`os.replace`) AND the restoring rename both fail, the only
    real copy is stranded at `.dummyindex-old.tmp`: reported by path, never swallowed."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_dir = _write_owned_claude_family(scope_root, family)
    claude_skills_root = _claude_skills_root(scope_root)
    tmp_old = claude_skills_root / f".{family}.dummyindex-old.tmp"

    real_rename = Path.rename

    def _flaky_rename(self: Path, target: object) -> object:
        if self == claude_dir and Path(target) == tmp_old:
            return real_rename(self, target)  # the initial rename-aside: allow
        raise OSError("simulated restore failure")

    monkeypatch.setattr(Path, "rename", _flaky_rename)

    real_replace = os.replace

    def _failing_replace(src: object, dst: object) -> object:
        if Path(dst) == claude_dir:
            raise OSError("simulated promote failure")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _failing_replace)

    result = create_family_links(scope_root)

    assert tmp_old.exists()
    assert (tmp_old / ".dummyindex_version").exists()
    assert any("stranded" in e and str(tmp_old) in e for e in result.errors)


def test_create_family_links_prints_hand_edits_caveat_after_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The hand-edits caveat prints once the promotion has succeeded."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    _write_owned_claude_family(scope_root, family)

    result = create_family_links(scope_root)

    assert family in result.replaced
    out = capsys.readouterr().out
    assert "pristine installed files replaced by one shared skill reference" in out


def test_create_family_links_does_not_print_caveat_when_promotion_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When the promote fails, the hand-edits caveat never prints."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    family = "dummyindex"
    claude_dir = _write_owned_claude_family(scope_root, family)

    real_replace = os.replace

    def _failing_replace(src: object, dst: object) -> object:
        if Path(dst) == claude_dir:
            raise OSError("simulated promote failure")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _failing_replace)

    result = create_family_links(scope_root)

    assert any(e.startswith(f"{family}:") for e in result.errors)
    out = capsys.readouterr().out
    assert "hand-edits" not in out


def test_create_family_links_passes_target_is_directory_true(tmp_path: Path) -> None:
    """The Windows-specific contract: `target_is_directory=True` is actually PASSED
    to `symlink_fn`, not merely accepted as a keyword default."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    seen_kwargs: list[dict] = []

    def _recording_symlink(src: str, dst: Path, **kwargs: object) -> None:
        seen_kwargs.append(kwargs)
        os.symlink(src, dst, **kwargs)

    create_family_links(scope_root, symlink_fn=_recording_symlink)

    assert seen_kwargs
    assert all(kwargs.get("target_is_directory") is True for kwargs in seen_kwargs)


# remove_dangling_family_links


def test_remove_dangling_family_links_removes_only_dangling_not_foreign(
    tmp_path: Path,
) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    claude_skills_root = _claude_skills_root(scope_root)
    claude_skills_root.mkdir(parents=True)

    dangling_family = "dummyindex"
    dangling_dir = _symlink_claude_family(scope_root, dangling_family)

    foreign_family = "dummyindex-plan"
    external = tmp_path / "external"
    external.mkdir()
    foreign_dir = _symlink_claude_family(
        scope_root, foreign_family, value=str(external)
    )

    removed = remove_dangling_family_links(scope_root)

    assert removed == (dangling_dir,)
    assert not dangling_dir.exists() and not dangling_dir.is_symlink()
    assert foreign_dir.is_symlink()  # untouched, never followed


def test_remove_dangling_family_links_rechecks_immediately_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirrors `execute_repairs`'s re-preflight: the parent-chain check runs
    again immediately before each unlink, catching a state change between
    the scan and the act."""
    _require_real_symlinks(tmp_path)
    import dummyindex.installer.link as link_module

    scope_root = tmp_path / "project"
    family = "dummyindex"
    family_dir = _symlink_claude_family(scope_root, family)
    real_classify = link_module.classify_family_link
    calls = {"n": 0}

    def _fake_classify(
        path: Path, root: Path, **kwargs: object
    ) -> FamilyLinkClassification:
        if path == family_dir:
            calls["n"] += 1
            if calls["n"] == 2:
                return FamilyLinkClassification(
                    family, path, FamilyLinkState.FOREIGN, "changed mid-sweep"
                )
        return real_classify(path, root, **kwargs)

    monkeypatch.setattr(link_module, "classify_family_link", _fake_classify)

    removed = remove_dangling_family_links(scope_root)

    assert removed == ()
    assert family_dir.is_symlink()  # the recheck caught it before unlinking


def test_remove_dangling_family_links_refuses_symlinked_claude_parent(
    tmp_path: Path,
) -> None:
    """CRITICAL-1: the sweep must refuse to touch anything reached through a
    symlinked `.claude` — a dangling-looking leaf inside a victim tree stays
    untouched."""
    _require_real_symlinks(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    victim = tmp_path / "victim"
    victim_skills = victim / "skills"
    victim_skills.mkdir(parents=True)
    (project / ".claude").symlink_to(victim, target_is_directory=True)
    family = "dummyindex"
    dangling = victim_skills / family
    dangling.symlink_to(relative_link_value(family), target_is_directory=True)

    removed = remove_dangling_family_links(project)

    assert removed == ()
    assert dangling.is_symlink()


# run_link_install — AUTO/LINK/COPY orchestration


class _SpySymlink:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, src, dst, *, target_is_directory: bool = False) -> None:
        self.calls += 1
        os.symlink(src, dst, target_is_directory=target_is_directory)


def _raising_symlink_fn(*_a, **_k):
    raise OSError(errno.EPERM, "Operation not permitted")


def test_run_link_install_copy_mode_never_touches_the_filesystem(
    tmp_path: Path,
) -> None:
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    spy = _SpySymlink()

    result = run_link_install(scope_root, link_mode=LinkMode.COPY, symlink_fn=spy)

    assert result.effective_link_mode is LinkMode.COPY
    assert result.link_result is None
    assert result.fell_back_to_copy is False
    assert result.warnings == ()
    assert spy.calls == 0
    assert not (scope_root / ".claude").exists()


def test_run_link_install_auto_links_when_capable(tmp_path: Path) -> None:
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    spy = _SpySymlink()

    result = run_link_install(scope_root, link_mode=LinkMode.AUTO, symlink_fn=spy)

    assert result.effective_link_mode is LinkMode.AUTO
    assert result.fell_back_to_copy is False
    assert result.warnings == ()
    assert result.link_result is not None
    assert set(result.link_result.created) == set(FAMILIES)
    assert spy.calls == len(FAMILIES) + 1  # + 1 capability probe


def test_run_link_install_auto_falls_back_to_copy_on_capability_failure(
    tmp_path: Path,
) -> None:
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)

    result = run_link_install(
        scope_root, link_mode=LinkMode.AUTO, symlink_fn=_raising_symlink_fn
    )

    assert result.effective_link_mode is LinkMode.COPY
    assert result.fell_back_to_copy is True
    assert result.link_result is None
    assert len(result.warnings) == 1
    assert (
        "core.symlinks" in result.warnings[0] or "Developer Mode" in result.warnings[0]
    )
    for family in FAMILIES:
        assert not (_claude_skills_root(scope_root) / family).exists()


def test_run_link_install_strict_link_raises_on_capability_failure(
    tmp_path: Path,
) -> None:
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)

    with pytest.raises(LinkCapabilityError):
        run_link_install(
            scope_root, link_mode=LinkMode.LINK, symlink_fn=_raising_symlink_fn
        )

    for family in FAMILIES:
        assert not (_claude_skills_root(scope_root) / family).exists()


def test_run_link_install_strict_link_success_path(tmp_path: Path) -> None:
    """Test gap: no strict-`LinkMode.LINK` SUCCESS-path test existed —
    `LINK` was only ever exercised on the capability-failure branch."""
    _require_real_symlinks(tmp_path)
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)

    result = run_link_install(scope_root, link_mode=LinkMode.LINK)

    assert result.effective_link_mode is LinkMode.LINK
    assert result.fell_back_to_copy is False
    assert result.warnings == ()
    assert result.link_result is not None
    assert set(result.link_result.created) == set(FAMILIES)
    for family in FAMILIES:
        assert (_claude_skills_root(scope_root) / family).is_symlink()


def test_run_link_install_squatted_probe_directory_is_reported_not_deleted(
    tmp_path: Path,
) -> None:
    """CRITICAL-2: a directory squatting the probe name, holding a payload
    file, must be reported (probe failure -> AUTO falls back to copy),
    never deleted — mirrors the temp-link squat repro at the probe name."""
    scope_root = tmp_path / "project"
    _seed_all_agents_families(scope_root)
    claude_skills_root = _claude_skills_root(scope_root)
    claude_skills_root.mkdir(parents=True, exist_ok=True)
    squatted = claude_skills_root / ".dummyindex-symlink-probe.tmp"
    squatted.mkdir()
    (squatted / "PAYLOAD.txt").write_text("payload\n", encoding="utf-8")

    result = run_link_install(scope_root, link_mode=LinkMode.AUTO)

    assert squatted.is_dir()
    assert (squatted / "PAYLOAD.txt").exists()
    assert result.fell_back_to_copy is True


def test_run_link_install_refuses_probe_through_symlinked_claude_parent(
    tmp_path: Path,
) -> None:
    """CRITICAL-1: the capability probe must apply the same parent-chain
    precondition as `_link_one_family` — a `.claude -> victim` layout must
    never let the probe create/remove anything inside the victim tree."""
    _require_real_symlinks(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (project / ".claude").symlink_to(victim, target_is_directory=True)
    _seed_all_agents_families(project)

    result = run_link_install(project, link_mode=LinkMode.AUTO)

    assert result.fell_back_to_copy is True
    assert not (victim / "skills").exists()


def test_run_link_install_auto_parent_chain_refusal_uses_dotfiles_hint(
    tmp_path: Path,
) -> None:
    """A parent-chain refusal (a symlinked, usually dotfiles-managed `.claude`) is
    NOT a capability problem: the AUTO warning carries the dotfiles remediation,
    never the Windows Developer-Mode / `core.symlinks` hint."""
    _require_real_symlinks(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (project / ".claude").symlink_to(victim, target_is_directory=True)
    _seed_all_agents_families(project)

    result = run_link_install(project, link_mode=LinkMode.AUTO)

    assert result.fell_back_to_copy is True
    assert len(result.warnings) == 1
    assert "dotfiles" in result.warnings[0]
    assert "Developer Mode" not in result.warnings[0]
    assert "core.symlinks" not in result.warnings[0]


def test_run_link_install_strict_link_parent_chain_refusal_uses_dotfiles_hint(
    tmp_path: Path,
) -> None:
    """Strict `LinkMode.LINK`'s raised error carries the same dotfiles remediation."""
    _require_real_symlinks(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (project / ".claude").symlink_to(victim, target_is_directory=True)
    _seed_all_agents_families(project)

    with pytest.raises(LinkCapabilityError) as excinfo:
        run_link_install(project, link_mode=LinkMode.LINK)

    message = str(excinfo.value)
    assert "dotfiles" in message
    assert "Developer Mode" not in message
    assert "core.symlinks" not in message


def test_run_link_install_threads_allowed_symlinks_to_probe_and_create(
    tmp_path: Path,
) -> None:
    """`allowed_symlinks` reaches the probe and `create_family_links`: a `~/.claude ->
    ~/localclaude` link (relative value resolves correctly) falls back to copy
    without it, and links every family with it."""
    _require_real_symlinks(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    localclaude = home / "localclaude"
    localclaude.mkdir()
    (home / ".claude").symlink_to(localclaude, target_is_directory=True)
    _seed_all_agents_families(home)

    without_allowlist = run_link_install(home, link_mode=LinkMode.AUTO)
    assert without_allowlist.fell_back_to_copy is True

    result = run_link_install(
        home, link_mode=LinkMode.AUTO, allowed_symlinks=frozenset({home / ".claude"})
    )

    assert result.fell_back_to_copy is False
    assert result.warnings == ()
    assert result.link_result is not None
    assert set(result.link_result.created) == set(FAMILIES)
    for family in FAMILIES:
        assert (localclaude / "skills" / family).is_symlink()
        assert (
            classify_family_link(
                home / ".claude" / "skills" / family,
                home,
                allowed_symlinks=frozenset({home / ".claude"}),
            ).state
            is FamilyLinkState.OURS_HEALTHY
        )


def test_link_result_is_frozen() -> None:
    result = LinkResult(created=(), replaced=(), skipped=(), errors=())
    with pytest.raises(FrozenInstanceError):
        result.created = ("x",)  # type: ignore[misc]


def test_family_link_classification_is_frozen(tmp_path: Path) -> None:
    classification = FamilyLinkClassification(
        family="dummyindex",
        path=tmp_path / "x",
        state=FamilyLinkState.MISSING,
        detail="path does not exist",
    )
    with pytest.raises(FrozenInstanceError):
        classification.detail = "changed"  # type: ignore[misc]
