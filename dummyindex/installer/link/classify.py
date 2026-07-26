"""Classification: the read-only `classify_family_link`/`verify_family_links`
sweep, plus the parent-chain precondition every write path in this package
also shares.

See the package docstring (``link/__init__.py``) for the import law.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path, PurePath

from ..common import _first_symlink_component, is_owned_copy, skills_root_rel
from .families import _family_names
from .models import FamilyLinkClassification, FamilyLinkState


def relative_link_value(family: str) -> str:
    """The canonical relative symlink value for one family."""
    return f"../../.agents/skills/{family}"


def family_link_target(scope_root: Path, family: str) -> Path:
    """The real ``.agents/skills/<family>`` directory under ``scope_root``."""
    return scope_root / skills_root_rel("codex") / family


def _parent_chain_clean(
    scope_root: Path, path: Path, *, allowed_symlinks: frozenset[Path] = frozenset()
) -> str | None:
    """The parent-chain PRECONDITION shared by every write/classify path in
    this module. Returns a human-readable reason the chain is unsafe, or
    ``None`` when it is clean.

    **Must run before ANY read-then-act or destructive step touches**
    ``path`` — crash recovery, removal, creation, classification — never
    after (CRITICAL: a `.claude -> /victim` layout must never let recovery
    reach into the victim tree one statement before this check runs).

    Two independent checks, both fail closed:

    - ``path.parent`` must be lexically under ``scope_root``: a wrong or
      foreign ``scope_root`` must never silently disarm the symlink check
      below the way `_first_symlink_component` does on its own when called
      directly — it returns ``None`` ("chain clean") the moment
      ``relative_to`` raises `ValueError` for an out-of-tree path
      (`common.py`). A caller passing the wrong root must get FOREIGN, not a
      silently-disarmed gate.
    - No disallowed symlink component between ``scope_root`` and
      ``path.parent`` (the original parent-chain rule).
    """
    try:
        path.parent.relative_to(scope_root)
    except ValueError:
        return f"{path} is not under scope root {scope_root}"
    unsafe = _first_symlink_component(
        scope_root, path.parent, allowed_symlinks=allowed_symlinks
    )
    if unsafe is not None:
        return f"parent path component {unsafe} is a symlink"
    return None


def _readlink_parts(raw_target: str) -> tuple[str, ...]:
    """Parse a readlink() value into path components.

    Never compare raw strings — only ever compare `PurePath(...).parts`.
    This module always WRITES forward slashes; a genuine Windows readlink
    round-trip can normalize them to ``\\``, but on real Windows `PurePath`
    IS `PureWindowsPath`, which already splits on both separators — no
    special-casing is needed there. This function previously fell back to a
    forced `PureWindowsPath` reparse whenever the plain POSIX parse yielded a
    single component; that fallback fired unconditionally on POSIX, where
    backslash is a perfectly legal filename character, mis-splitting a link
    literally named ``..\\..\\.agents\\skills\\dummyindex`` into components
    it does not have. Platform-native `PurePath` parsing alone is both
    correct and sufficient.
    """
    return PurePath(raw_target).parts


def _target_exists(path: Path) -> bool | None:
    """Whether the fully-resolved ``path`` exists: True / False / ambiguous.

    ``None`` means "stat failed for a reason other than absence" (a symlink
    loop, a permission error, an unreadable intermediate component) — the
    caller must never treat that as dangling.
    """
    try:
        os.stat(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return None


def _resolves_to_target(
    family_dir: Path, scope_root: Path, family: str
) -> tuple[bool, str]:
    """Whether ``family_dir``, followed to its end, lands on the real family.

    Purely structural (non-strict `resolve()`, no existence requirement) so
    it correctly flags a divergent path (the dotfiles case) even when the
    target doesn't exist yet, and correctly passes a healthy link even
    before its target is ever statted.
    """
    try:
        resolved_link = family_dir.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        return False, f"created link could not be resolved ({exc})"
    try:
        resolved_expected = family_link_target(scope_root, family).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        return False, f"expected target could not be resolved ({exc})"
    if resolved_link != resolved_expected:
        return (
            False,
            f"resolves to {resolved_link}, expected {resolved_expected}",
        )
    return True, "resolves correctly"


def _classify_symlink(
    family_dir: Path, scope_root: Path, family: str
) -> FamilyLinkClassification:
    try:
        raw_target = os.readlink(family_dir)
    except OSError as exc:
        return FamilyLinkClassification(
            family, family_dir, FamilyLinkState.FOREIGN, f"readlink failed: {exc}"
        )

    expected_parts = PurePath(relative_link_value(family)).parts
    value_matches = _readlink_parts(raw_target) == expected_parts
    resolves_ok, resolves_detail = _resolves_to_target(family_dir, scope_root, family)

    if not value_matches and not resolves_ok:
        return FamilyLinkClassification(
            family,
            family_dir,
            FamilyLinkState.FOREIGN,
            f"unexpected link value {raw_target!r}",
        )

    if not resolves_ok:
        # The lexical value can be exactly canonical and STILL land outside
        # scope_root once an allowlisted dotfiles `.claude` hop is followed
        # (e.g. `~/.claude -> ~/dotfiles/claude` makes the `../..` land in
        # `~/dotfiles/`, not the real home) — never skip this check just
        # because the string matched.
        return FamilyLinkClassification(
            family,
            family_dir,
            FamilyLinkState.FOREIGN,
            f"link value is canonical but {resolves_detail}",
        )

    target_exists = _target_exists(family_dir)
    if target_exists is None:
        return FamilyLinkClassification(
            family,
            family_dir,
            FamilyLinkState.FOREIGN,
            "link target could not be statted for a reason other than "
            "absence (symlink loop, permission error, or similar)",
        )
    if not target_exists:
        return FamilyLinkClassification(
            family,
            family_dir,
            FamilyLinkState.OURS_DANGLING,
            "link value matches (or resolves correctly) and the target is "
            "confirmed absent",
        )

    try:
        real_target_dir = family_dir.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return FamilyLinkClassification(
            family, family_dir, FamilyLinkState.FOREIGN, f"target unresolvable: {exc}"
        )
    if not is_owned_copy(real_target_dir):
        return FamilyLinkClassification(
            family,
            family_dir,
            FamilyLinkState.FOREIGN,
            "target exists but carries no ownership evidence",
        )
    return FamilyLinkClassification(
        family,
        family_dir,
        FamilyLinkState.OURS_HEALTHY,
        "link value is correct (or resolves correctly) and the target is an owned copy",
    )


def _classify(
    family_dir: Path,
    scope_root: Path,
    family: str,
    *,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> FamilyLinkClassification:
    unsafe_detail = _parent_chain_clean(
        scope_root, family_dir, allowed_symlinks=allowed_symlinks
    )
    if unsafe_detail is not None:
        return FamilyLinkClassification(
            family, family_dir, FamilyLinkState.FOREIGN, unsafe_detail
        )

    # Explicit lstat + errno triage (never `.is_symlink()`/`.exists()`, both
    # of which swallow ENOTDIR/ELOOP/EBADF into a bare `False` on
    # py3.10-3.13): an unstatable leaf must classify FOREIGN, never MISSING
    # — MISSING is the one state the spec says needs no ownership evidence
    # ("an empty path is safe to fill"), and an unstatable path is not an
    # empty path.
    try:
        st = os.lstat(family_dir)
    except FileNotFoundError:
        return FamilyLinkClassification(
            family, family_dir, FamilyLinkState.MISSING, "path does not exist"
        )
    except OSError as exc:
        return FamilyLinkClassification(
            family,
            family_dir,
            FamilyLinkState.FOREIGN,
            f"path could not be statted for a reason other than absence ({exc})",
        )

    if stat.S_ISLNK(st.st_mode):
        return _classify_symlink(family_dir, scope_root, family)

    if stat.S_ISDIR(st.st_mode):
        return FamilyLinkClassification(
            family, family_dir, FamilyLinkState.NOT_A_LINK, "real directory"
        )

    if stat.S_ISREG(st.st_mode):
        expected_value = relative_link_value(family)
        try:
            content = family_dir.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return FamilyLinkClassification(
                family,
                family_dir,
                FamilyLinkState.FOREIGN,
                f"unreadable regular file: {exc}",
            )
        if content == expected_value:
            return FamilyLinkClassification(
                family,
                family_dir,
                FamilyLinkState.MATERIALIZED,
                "regular file content matches the link value exactly",
            )
        return FamilyLinkClassification(
            family,
            family_dir,
            FamilyLinkState.NOT_A_LINK,
            "regular file, content does not match the link value",
        )

    return FamilyLinkClassification(
        family,
        family_dir,
        FamilyLinkState.FOREIGN,
        "not a directory, symlink, or regular file",
    )


def classify_family_link(
    claude_family_dir: Path,
    scope_root: Path,
    *,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> FamilyLinkClassification:
    """Classify one family's ``.claude/skills/<family>`` path.

    ``scope_root`` must always be the copy's OWN scope root (the project
    directory being installed into, or the genuine user home) — never the
    invocation's root when they differ, and never a project root passed
    while classifying a user-scope copy or vice versa. Passing the wrong
    scope root no longer silently disarms the parent-chain gate: a
    ``family_dir`` that is not lexically under ``scope_root`` classifies
    FOREIGN (see the module's cross-scope-root and wrong-scope-root tests).

    ``allowed_symlinks`` is a keyword-only, fail-closed allowlist (default:
    empty) of parent-chain components that are tolerated symlinks — for
    example a user-scope dotfiles-managed top-level ``.claude``. This module
    never infers "user scope" from `Path.home()`/``HOME`` itself; the caller
    (``install.py``, in a later wave) is expected to pass this explicitly
    when it already knows the scope is ``"user"``. **Invariant**: every
    entry must be a host root directly under ``scope_root`` — either
    ``scope_root / ".claude"`` or ``scope_root / ".claude" / "skills"`` —
    never anything deeper and never derived from an environment variable.

    Fails closed: any `OSError`/`RuntimeError` raised anywhere during
    classification is caught here and reported as `FamilyLinkState.FOREIGN`,
    mirroring `repair.py`'s `_same_root`.
    """
    family = claude_family_dir.name
    try:
        return _classify(
            claude_family_dir, scope_root, family, allowed_symlinks=allowed_symlinks
        )
    except (OSError, RuntimeError) as exc:
        return FamilyLinkClassification(
            family,
            claude_family_dir,
            FamilyLinkState.FOREIGN,
            f"classification raised {exc!r} — treated as foreign (fail closed)",
        )


def verify_family_links(
    scope_root: Path,
    *,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> tuple[FamilyLinkClassification, ...]:
    """Read-only classification sweep over all 8 families (repair/check/uninstall
    reporting). Never writes anything.

    ``allowed_symlinks`` forwards to `classify_family_link` unchanged — see
    its docstring (including the host-root invariant); defaults to the
    fail-closed empty allowlist.
    """
    claude_skills_root = scope_root / skills_root_rel("claude")
    return tuple(
        classify_family_link(
            claude_skills_root / family, scope_root, allowed_symlinks=allowed_symlinks
        )
        for family in _family_names()
    )
