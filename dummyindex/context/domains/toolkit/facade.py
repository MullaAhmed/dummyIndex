"""The public entry points the CLI wires to. Each returns a JSON-ready dict.

Every function validates its arguments before it touches disk. Errors raise
:class:`ToolkitError`, which the CLI turns into the error envelope.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..equip.plugins.sources import Runner, default_runner
from .bundle import bundle_dir, launch_args, load_manifest
from .constants import SCOPES
from .errors import ToolkitError
from .host import project_layout, user_layout
from .install import apply as install_apply
from .install import preview as install_preview
from .items import ToolkitItem
from .listing import list_items
from .mutate import ACTIONS, Request, mutate
from .paths import check_out_dir, validate_terminal_id


def resolve_root(cwd: Path, explicit: Path | None) -> Path:
    """``--root`` when given; else the nearest ancestor with ``.context`` or ``.git``."""
    if explicit is not None:
        return explicit.resolve()
    here = cwd.resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".context").is_dir() or (candidate / ".git").exists():
            return candidate
    return here


def _check_scope(scope: str | None) -> None:
    if scope is not None and scope not in SCOPES:
        raise ToolkitError(
            "invalid_argument", f"--scope must be one of {', '.join(SCOPES)}"
        )


def _terminal_args(
    root: Path, terminal_id: str | None, out_dir: Path | None, scope: str | None
) -> tuple[str | None, Path | None]:
    if scope == "terminal" and terminal_id is None:
        raise ToolkitError("terminal_required", "--scope terminal needs --terminal ID")
    if terminal_id is not None:
        validate_terminal_id(terminal_id)
        if out_dir is None:
            raise ToolkitError("out_dir_required", "--terminal needs --out-dir DIR")
        check_out_dir(out_dir, root)
    return terminal_id, out_dir


def toolkit_list(
    *,
    root: Path,
    home: Path,
    kind: str | None = None,
    scope: str | None = None,
    terminal_id: str | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    _check_scope(scope)
    terminal_id, out_dir = _terminal_args(root, terminal_id, out_dir, scope)
    items = list_items(
        project=project_layout(root),
        user=user_layout(home),
        kind=kind,
        scope=scope,
        terminal_id=terminal_id,
        out_dir=out_dir,
    )
    return {"items": [i.to_dict() for i in items]}


def toolkit_show(
    name: str,
    *,
    root: Path,
    home: Path,
    kind: str | None = None,
    scope: str | None = None,
    terminal_id: str | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    _check_scope(scope)
    terminal_id, out_dir = _terminal_args(root, terminal_id, out_dir, scope)
    items = [
        i
        for i in list_items(
            project=project_layout(root),
            user=user_layout(home),
            kind=kind,
            scope=scope,
            terminal_id=terminal_id,
            out_dir=out_dir,
        )
        if i.name == name
    ]
    if not items:
        raise ToolkitError("not_found", f"no toolkit item named {name!r}")
    if len(items) > 1:
        scopes = ", ".join(sorted({i.scope for i in items}))
        raise ToolkitError(
            "ambiguous_item",
            f"{name!r} exists in several scopes ({scopes}); pass --scope or --kind",
        )
    item: ToolkitItem = items[0]
    bundle: str | None = None
    args: list[str] = []
    if item.scope == "terminal" and terminal_id is not None and out_dir is not None:
        bdir = bundle_dir(out_dir, terminal_id)
        args = launch_args(bdir, load_manifest(bdir))
        bundle = str(bdir)
    return {
        "item": item.to_dict(),
        "launch_args": args,
        "bundle_dir": bundle,
    }


def toolkit_mutate(
    action: str,
    name: str,
    *,
    root: Path,
    home: Path,
    kind: str | None = None,
    scope: str | None = None,
    terminal_id: str | None = None,
    out_dir: Path | None = None,
    config_file: Path | None = None,
    source_file: Path | None = None,
    source_dir: Path | None = None,
    mechanism: str | None = None,
    allow_project_fallback: bool = False,
) -> dict[str, Any]:
    if action not in ACTIONS:
        raise ToolkitError("usage", f"unknown action {action!r}")
    _check_scope(scope)
    effective_scope = scope or "project"
    if effective_scope == "terminal" and terminal_id is None:
        raise ToolkitError("terminal_required", "--scope terminal needs --terminal ID")
    if terminal_id is not None:
        validate_terminal_id(terminal_id)
        if out_dir is None:
            raise ToolkitError("out_dir_required", "--terminal needs --out-dir DIR")
        check_out_dir(out_dir, root)
    return mutate(
        Request(
            action=action,
            kind=kind,
            name=name,
            scope=effective_scope,
            root=root,
            layout_project=project_layout(root),
            layout_user=user_layout(home),
            out_dir=out_dir,
            terminal_id=terminal_id,
            config_file=config_file,
            source_file=source_file,
            source_dir=source_dir,
            mechanism=mechanism,
            allow_project_fallback=allow_project_fallback,
        )
    )


def toolkit_install(
    kind: str | None,
    source: str | None,
    *,
    root: Path,
    home: Path,
    scope: str | None = None,
    preview: bool = False,
    yes: bool = False,
    plan_hash: str | None = None,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Two-step install. ``runner`` is the GitHub/claude seam (tests inject one)."""
    if kind is None or source is None:
        raise ToolkitError("invalid_argument", "install needs --kind and --source")
    # Plugins are user-scope only (see install.build_plan); other kinds default to project.
    effective_scope = scope or ("user" if kind == "plugin" else "project")
    if preview and yes:
        raise ToolkitError("usage", "use either --preview or --yes, not both")
    seam = runner or default_runner
    if preview:
        return install_preview(
            kind, source, effective_scope, root=root, home=home, runner=seam
        )
    if not yes:
        raise ToolkitError(
            "confirmation_required",
            "install needs --preview first, then --yes --plan-hash <hash> to apply",
        )
    if not plan_hash:
        raise ToolkitError(
            "invalid_argument", "--yes needs --plan-hash from the preview"
        )
    return install_apply(
        kind, source, effective_scope, plan_hash, root=root, home=home, runner=seam
    )
