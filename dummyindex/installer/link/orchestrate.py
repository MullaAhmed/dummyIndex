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
    """The first family, in `_family_names()` order, whose ``.agents/skills/<family>``
    is a real (lstat-confirmed) directory: the resolution probe's target.

    Walks every family so a partial ``.agents`` tree still finds a target.
    ``None`` when none is real yet; the probe then skips its resolution check
    rather than report a false failure.
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
    """Probe symlink capability, and resolution when possible, before any family.

    Creates and removes one probe link under ``.claude/skills/``, checking the
    parent chain before ``mkdir`` so a ``.claude -> /victim`` layout never gets the
    probe written into the victim. With a real ``.agents`` family present, the
    probe carries its canonical relative value and must resolve to it: under a
    dotfiles ``~/.claude -> ~/dotfiles/claude``, ``../../.agents/...`` lands in
    ``~/dotfiles/``, and catching it here stops AUTO churning links every run.
    ``allowed_symlinks``: fail closed, never derived from an environment variable.

    Returns ``(ok, detail, hint)``: `_dotfiles_hint` for a parent-chain refusal or
    wrong resolution (not a Windows Developer Mode problem), `_CAPABILITY_HINT` for
    a ``mkdir``/``symlink_fn`` `OSError`, ``""`` when ok. The probe link is
    removed on every return path.
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
        symlink_fn(str(Path(probe_value)), probe_path, target_is_directory=True)
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
    """Dispatch the Claude-side AUTO/LINK/COPY mode for one install run.

    Call once, after ``.agents/skills/**`` is written and `execute_repairs` has
    run, so links never target a stale or partial tree. ``COPY`` returns at once
    with ``link_result=None``. ``AUTO``/``LINK`` run `_probe_symlink_capability`
    first; on success this returns `create_family_links`'s result. On probe
    failure ``AUTO`` touches nothing and reports ``COPY`` with
    ``fell_back_to_copy=True`` and one hint warning (an AUTO update must never
    brick a Windows checkout); strict ``LINK`` raises `LinkCapabilityError`.

    ``allowed_symlinks`` reaches the probe and `create_family_links`; it is the
    only way to admit a dotfiles ``~/.claude``. Fail closed, never derived from an
    environment variable (package invariant).
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
                f"using thin Claude references to the shared .agents family — {probe_hint}",
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
