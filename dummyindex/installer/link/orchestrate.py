"""AUTO/LINK/COPY orchestration: the capability pre-probe + `run_link_install`.

See the package docstring (``link/__init__.py``) for the import law.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from ..common import LinkMode, skills_root_rel
from .classify import _parent_chain_clean, _resolves_to_target, relative_link_value
from .create import _agents_family_target_is_dir, _silently_remove, create_family_links
from .families import _CAPABILITY_HINT, _PROBE_NAME, _dotfiles_hint, _family_names
from .models import LinkCapabilityError, LinkInstallResult


def _first_real_agents_family(scope_root: Path) -> str | None:
    """The first family (main first, by `_family_names()`'s own order) whose
    ``.agents/skills/<family>`` is already a REAL, lstat-confirmed directory
    under ``scope_root`` — the resolution probe's target family.

    The pinned sequencing (`run_link_install`'s own docstring:
    ``.agents/skills/**`` is written for real before any non-COPY dispatch
    ever reaches the probe) guarantees the main family alone is already
    enough, but this walks every family — matching the spec's "the main
    dummyindex family, or any existing `.agents` family" allowance — so an
    exotic partial-family shape still finds a target. Returns ``None`` when
    no family is real yet (should not happen given the pinned sequencing;
    the probe simply skips the resolution check rather than manufacturing a
    false failure out of an unrelated precondition gap).
    """
    for family in _family_names():
        if _agents_family_target_is_dir(scope_root, family):
            return family
    return None


def _probe_symlink_capability(
    scope_root: Path,
    *,
    symlink_fn: Callable[..., None],
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> tuple[bool, str, str]:
    """Create + remove one throwaway symlink under ``.claude/skills/`` to
    test capability — AND, when a real `.agents` family already exists,
    resolution — before any family is touched.

    Same parent-chain PRECONDITION as `_link_one_family`, checked before the
    ``mkdir`` and before anything is written: a `.claude -> /victim` layout
    must never let the probe create or remove anything inside the victim
    tree. An unclean chain here is reported as a probe failure (safe: AUTO
    falls back to copy mode for the whole run, strict LINK errors — neither
    touches the victim tree).

    **Resolution check (dotfiles divergence)**: proving that *some* symlink
    can be created is not enough — a dotfiles-symlinked ``~/.claude`` (e.g.
    ``~/.claude -> ~/dotfiles/claude``) creates a literal symlink just fine,
    but the CANONICAL RELATIVE value every family link actually carries
    (``../../.agents/skills/<family>``) then resolves into
    ``~/dotfiles/.agents/...``, not the real home tree. Catching this here,
    before any per-family link is created, is what keeps AUTO from doing a
    create-then-remove dance on every run (no infinite heal churn): when a
    real ``.agents`` family already exists (`_first_real_agents_family`,
    guaranteed by the pinned sequencing for any non-COPY dispatch that
    reaches this probe), the ONE probe symlink is created with that
    family's own canonical relative value and its resolution is checked
    against the real target — a single combined capability+resolution
    probe, not two separate symlink calls. Skips the resolution half (probe
    stays capability-only, matching the pre-fix behavior) only when no real
    ``.agents`` family exists yet to test against.

    ``allowed_symlinks`` invariant (see the module docstring): every entry
    must be ``scope_root / ".claude"`` or ``scope_root / ".claude" / "skills"``
    — never derived from an environment variable.

    Returns ``(ok, detail, hint)``. ``hint`` is the DISCRIMINATED remediation
    (NEW-3, extended here for the resolution check): the parent-chain gate
    refusing, or the canonical value resolving to the wrong place (both
    most often a dotfiles-managed home directory), are NOT symlink-
    capability problems, so they get `_dotfiles_hint(scope_root)`; every
    other failure (`mkdir`/`symlink_fn` raising `OSError` — genuinely "this
    environment cannot create symlinks") gets `_CAPABILITY_HINT`. Conflating
    the two used to tell a macOS/Linux user with a dotfiles `~/.claude` to
    enable Windows Developer Mode. ``hint`` is ``""`` when ``ok`` is
    ``True``.

    The probe's temp artifact (``_PROBE_NAME``) is cleaned up on every
    return path — success, mismatch, or exception — never left behind.
    """
    claude_skills_root = scope_root / skills_root_rel("claude")
    probe_path = claude_skills_root / _PROBE_NAME
    unsafe_detail = _parent_chain_clean(
        scope_root, probe_path, allowed_symlinks=allowed_symlinks
    )
    if unsafe_detail is not None:
        return False, unsafe_detail, _dotfiles_hint(scope_root)
    try:
        claude_skills_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, str(exc), _CAPABILITY_HINT
    _silently_remove(probe_path)

    resolution_family = _first_real_agents_family(scope_root)
    probe_value = (
        relative_link_value(resolution_family)
        if resolution_family is not None
        else "probe-target"
    )
    try:
        symlink_fn(probe_value, probe_path, target_is_directory=True)
    except OSError as exc:
        _silently_remove(probe_path)
        return False, str(exc), _CAPABILITY_HINT

    if resolution_family is None:
        _silently_remove(probe_path)
        return True, "ok", ""

    resolves_ok, resolves_detail = _resolves_to_target(
        probe_path, scope_root, resolution_family
    )
    _silently_remove(probe_path)
    if not resolves_ok:
        return False, resolves_detail, _dotfiles_hint(scope_root)
    return True, "ok", ""


def run_link_install(
    scope_root: Path,
    *,
    link_mode: LinkMode = LinkMode.AUTO,
    symlink_fn: Callable[..., None] = os.symlink,
    allowed_symlinks: frozenset[Path] = frozenset(),
) -> LinkInstallResult:
    """Dispatch the Claude-side AUTO/LINK/COPY tri-state for one install run.

    **Contract for Wave 3's `install.py`** (this function's whole reason for
    living here rather than growing `install.py`, already over the repo's
    600-line split threshold): call this exactly once per invocation,
    *after* `.agents/skills/**` has been written for real and *after*
    `execute_repairs` has landed — the pinned sequencing from the proposal
    spec — so `create_family_links` never links against a stale or
    partially-written `.agents` tree. `install.py` then branches on the
    returned `LinkInstallResult`:

    - ``link_mode=LinkMode.COPY`` -> returns immediately,
      ``link_result=None``, ``fell_back_to_copy=False``. Nothing here is
      touched; the caller's existing real-tree Claude write path
      (``_install_skill_family``) runs unchanged, exactly as before this
      proposal.
    - ``LinkMode.AUTO`` / ``LinkMode.LINK`` -> runs ONE capability-AND-
      resolution pre-probe (create + remove a probe symlink under
      ``.claude/skills/`` via ``symlink_fn`` — see
      `_probe_symlink_capability`'s own docstring for the resolution half,
      which catches a dotfiles-divergent ``.claude`` before any real family
      link is created/removed) before any family is converted:
      - probe succeeds -> calls `create_family_links(scope_root,
        symlink_fn=symlink_fn)` and returns its `LinkResult`.
      - probe fails under `AUTO` -> falls back to copy mode for the WHOLE
        run: nothing is touched, ``effective_link_mode`` becomes
        ``LinkMode.COPY``, ``fell_back_to_copy=True``, and ``warnings``
        carries one line with the Windows Developer-Mode/``core.symlinks``
        hint. The caller is expected to fall through to its own copy-mode
        write path when ``fell_back_to_copy`` is true — an AUTO update must
        never brick a Windows checkout.
      - probe fails under strict `LINK` -> raises `LinkCapabilityError`
        (never falls back) so the caller can print it and exit 1.

    ``allowed_symlinks`` (API GAP fix) is the fail-closed parent-chain
    allowlist, threaded unchanged into both the capability pre-probe and
    `create_family_links` — this is the ONLY argument that lets a caller
    reach the legitimate user-scope path (a dotfiles-symlinked ``~/.claude``
    whose relative link still resolves correctly). Defaults to the empty
    frozenset, matching every other entry point in this module. **Invariant**
    (see the module docstring): every entry must be ``scope_root / ".claude"``
    or ``scope_root / ".claude" / "skills"`` — never derived from an
    environment variable. `install.py` (Wave 3) is expected to pass
    ``frozenset({base / ".claude", base / ".claude" / "skills"})`` at user
    scope and ``frozenset()`` at project scope.

    Never imports `install.py`/`repair.py`/`uninstall.py` — see the module
    docstring's import law.
    """
    if link_mode is LinkMode.COPY:
        return LinkInstallResult(
            effective_link_mode=LinkMode.COPY,
            link_result=None,
            fell_back_to_copy=False,
            warnings=(),
        )

    probe_ok, probe_detail, probe_hint = _probe_symlink_capability(
        scope_root, symlink_fn=symlink_fn, allowed_symlinks=allowed_symlinks
    )
    if not probe_ok:
        if link_mode is LinkMode.LINK:
            raise LinkCapabilityError(
                f"symlink capability probe failed ({probe_detail}) — {probe_hint}"
            )
        return LinkInstallResult(
            effective_link_mode=LinkMode.COPY,
            link_result=None,
            fell_back_to_copy=True,
            warnings=(
                f"warning: symlink creation is unavailable ({probe_detail}); "
                f"falling back to --copy for this run — {probe_hint}",
            ),
        )

    link_result = create_family_links(
        scope_root, symlink_fn=symlink_fn, allowed_symlinks=allowed_symlinks
    )
    return LinkInstallResult(
        effective_link_mode=link_mode,
        link_result=link_result,
        fell_back_to_copy=False,
        warnings=(),
    )
