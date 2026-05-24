"""`dummyindex context <subcommand>` dispatch.

Wired in from `dummyindex/__main__.py`. Subcommands:

- `init`           run the full deterministic backbone build + CLAUDE.md bootstrap
- `rebuild`        re-run the backbone (use `--changed` for incremental)
- `bootstrap`      regenerate the CLAUDE.md managed block only
- `enrich-plan`    emit `.context/_enrich_plan.json` listing tree.json stub
                   nodes (the work-list for the /dummyindex skill)
- `enrich-apply`   merge a `{node_id: abstract}` JSON file into tree.json,
                   bumping each touched node's confidence to INFERRED

All path-taking commands share one rule for deciding where `.context/`
lives when scope and the enclosing repo differ: if the positional arg
resolves to a strict subdirectory of cwd, the user is operating inside
a project — output goes to cwd. Otherwise output goes to the arg itself.
`--root <path>` overrides this in either direction.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, Optional

_USAGE = """\
Usage: dummyindex context <subcommand> [args]

Subcommands:
  init [path] [--root DIR]          Initialize .context/ in the enclosing
                                    repo (default scope: cwd; default root:
                                    cwd if scope is a subdir of cwd, else
                                    scope itself).
  rebuild [--changed] [path] [--root DIR]
                                    Rebuild .context/ (use --changed for
                                    incremental).
  bootstrap [path] [--root DIR]     Write/regenerate the CLAUDE.md managed
                                    block at <root>/CLAUDE.md.
  enrich-plan [path] [--root DIR]   Emit .context/_enrich_plan.json (work-list).
  enrich-apply [path] [--root DIR] --from-json FILE
                                    Merge {node_id: abstract} JSON into
                                    tree.json.
"""


def dispatch(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE)
        return 0
    subcmd, rest = argv[0], argv[1:]
    handler = _HANDLERS.get(subcmd)
    if handler is None:
        print(f"error: unknown context subcommand '{subcmd}'", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        return 2
    return handler(rest)


# ----- argument parsing -----------------------------------------------------


def _resolve_context_root(scope: Path, *, explicit_root: Optional[Path] = None,
                          cwd: Optional[Path] = None) -> Path:
    """Decide where `.context/` and `CLAUDE.md` live for a given scope.

    Rule:
    - If `explicit_root` is given, use it.
    - If `scope` was passed as an **absolute path**, treat it as both scan
      target and project root (the user typed a full path on purpose).
    - If `scope` was relative and resolves to a strict subdirectory of cwd,
      the user is operating inside a project — return cwd (the enclosing
      repo root).
    - Otherwise return `scope`.

    The check on absolute-vs-relative is done on the original `Path` object
    (`scope.is_absolute()`), not on its resolved form, so callers pass the
    user's raw argument rather than `.resolve()`-ing it first.
    """
    if explicit_root is not None:
        return explicit_root.resolve()
    if scope.is_absolute():
        return scope.resolve()
    cwd = (cwd or Path.cwd()).resolve()
    # Resolve relative scope against the supplied cwd, not the live process
    # cwd — keeps the helper testable and matches what the user "meant"
    # when they typed a relative path.
    scope_resolved = (cwd / scope).resolve()
    if scope_resolved == cwd:
        return cwd
    try:
        scope_resolved.relative_to(cwd)
        return cwd  # scope is under cwd → enclosing repo
    except ValueError:
        return scope_resolved


def _parse_path_and_root(
    args: list[str],
    *,
    extra_consumers: Optional[Callable[[str, list[str], int], Optional[int]]] = None,
) -> tuple[Path, Optional[Path], list[str]]:
    """Pull the positional scope + optional `--root` out of `args`.

    Returns ``(scope, explicit_root, remaining_args)`` so callers can
    parse their own flags (e.g. `--changed`, `--from-json`) from
    `remaining_args`. `extra_consumers`, if given, is called for each
    unrecognized argument and should return the new index (consumed
    something) or None (didn't consume, treat as remaining).
    """
    scope = Path(".")
    explicit_root: Optional[Path] = None
    remaining: list[str] = []
    i = 0
    saw_scope = False
    while i < len(args):
        a = args[i]
        if a in ("--root",) and i + 1 < len(args):
            explicit_root = Path(args[i + 1])
            i += 2
        elif a.startswith("--root="):
            explicit_root = Path(a.split("=", 1)[1])
            i += 1
        elif not a.startswith("--") and not saw_scope:
            scope = Path(a)
            saw_scope = True
            i += 1
        else:
            remaining.append(a)
            i += 1
    return scope, explicit_root, remaining


# ----- subcommands ----------------------------------------------------------


def _cmd_init(args: list[str]) -> int:
    from dummyindex.context.runner import build_all

    scope, explicit_root, rest = _parse_path_and_root(args)
    if rest:
        print(f"error: unknown argument(s) for `init`: {rest}", file=sys.stderr)
        return 2
    out_root = _resolve_context_root(scope, explicit_root=explicit_root)

    try:
        from importlib.metadata import version

        di_version = version("dummyindex")
    except Exception:
        di_version = "unknown"

    result = build_all(
        scope,
        out_root=out_root,
        bootstrap=True,
        dummyindex_version=di_version,
    )
    print(
        f"context init: wrote {len(result.written)} files to {result.context_dir}"
    )
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    if result.languages:
        print(f"  languages: {', '.join(result.languages)}")
    if scope.resolve() != out_root:
        print(f"  scope:  {scope.resolve()}")
        print(f"  root:   {out_root}")
    if result.bootstrapped:
        print(f"  CLAUDE.md  ->  managed block written")
    return 0


def _cmd_rebuild(args: list[str]) -> int:
    scope, explicit_root, rest = _parse_path_and_root(args)
    changed_only = "--changed" in rest
    rest = [a for a in rest if a != "--changed"]
    if rest:
        print(f"error: unknown argument(s) for `rebuild`: {rest}", file=sys.stderr)
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)

    try:
        from importlib.metadata import version

        di_version = version("dummyindex")
    except Exception:
        di_version = "unknown"

    if changed_only:
        from dummyindex.context.incremental import rebuild_changed

        result = rebuild_changed(out_root, dummyindex_version=di_version)
        if result.skipped:
            print("context rebuild: no source files changed; .context/ unchanged.")
            return 0
        ch = result.changes
        print(
            f"context rebuild: {len(ch.added)} added, {len(ch.modified)} modified, "
            f"{len(ch.removed)} removed → rebuilt {result.build_result.context_dir}"
            if result.build_result
            else "rebuild ran"
        )
        return 0

    from dummyindex.context.runner import build_all

    result = build_all(scope, out_root=out_root, dummyindex_version=di_version)
    print(
        f"context rebuild: wrote {len(result.written)} files to {result.context_dir}"
    )
    print(f"  files: {result.file_count}  symbols: {result.symbol_count}")
    return 0


def _cmd_bootstrap(args: list[str]) -> int:
    from dummyindex.context.bootstrap import (
        UnbalancedMarkersError,
        bootstrap_claude_md,
    )

    scope, explicit_root, rest = _parse_path_and_root(args)
    if rest:
        print(f"error: unknown argument(s) for `bootstrap`: {rest}", file=sys.stderr)
        return 2
    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    claude_md = out_root / "CLAUDE.md"
    try:
        bootstrap_claude_md(claude_md)
    except UnbalancedMarkersError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    print(f"CLAUDE.md  ->  managed block written: {claude_md.resolve()}")
    return 0


def _cmd_enrich_plan(args: list[str]) -> int:
    from dummyindex.context.enrich import build_plan, write_plan

    scope, explicit_root, rest = _parse_path_and_root(args)
    if rest:
        print(f"error: unknown argument(s) for `enrich-plan`: {rest}", file=sys.stderr)
        return 2
    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.exists():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest {out_root}` first.",
            file=sys.stderr,
        )
        return 2
    try:
        plan = build_plan(context_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out_path = context_dir / "_enrich_plan.json"
    write_plan(out_path, plan)
    stats = plan.stats
    try:
        rel = out_path.relative_to(Path.cwd().resolve())
        print(f"context enrich-plan: wrote {rel}")
    except ValueError:
        print(f"context enrich-plan: wrote {out_path}")
    print(
        f"  total nodes: {stats['total_nodes']}  stubs: {stats['stub_nodes']}  "
        f"by_kind: {stats['by_kind']}"
    )
    print(f"  batches: {len(plan.batches)}")
    return 0


def _cmd_enrich_apply(args: list[str]) -> int:
    from dummyindex.context.enrich import apply_updates

    scope, explicit_root, rest = _parse_path_and_root(args)

    # Pull `--from-json` out of the remaining args.
    from_json: Optional[Path] = None
    leftover: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--from-json" and i + 1 < len(rest):
            from_json = Path(rest[i + 1])
            i += 2
        elif a.startswith("--from-json="):
            from_json = Path(a.split("=", 1)[1])
            i += 1
        else:
            leftover.append(a)
            i += 1
    if leftover:
        print(f"error: unknown argument(s) for `enrich-apply`: {leftover}", file=sys.stderr)
        return 2

    if from_json is None:
        print(
            "error: --from-json FILE is required (JSON mapping {node_id: abstract})",
            file=sys.stderr,
        )
        return 2
    if not from_json.exists():
        print(f"error: {from_json} not found", file=sys.stderr)
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not (context_dir / "tree.json").exists():
        print(
            f"error: {context_dir}/tree.json not found. Run `dummyindex ingest {out_root}` first.",
            file=sys.stderr,
        )
        return 2

    payload = json.loads(from_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in payload.items()
    ):
        print(
            f"error: {from_json} must be a JSON object mapping string node_id -> string abstract",
            file=sys.stderr,
        )
        return 2

    result = apply_updates(context_dir, payload)
    print(
        f"context enrich-apply: updated {len(result.updated)} abstract(s) in "
        f"{context_dir / 'tree.json'}"
    )
    if result.unknown:
        print(
            f"  warning: {len(result.unknown)} node_id(s) not found in tree.json:",
            file=sys.stderr,
        )
        for nid in result.unknown:
            print(f"    - {nid}", file=sys.stderr)
        return 1
    return 0


_HANDLERS: dict[str, Callable[[list[str]], int]] = {
    "init": _cmd_init,
    "rebuild": _cmd_rebuild,
    "bootstrap": _cmd_bootstrap,
    "enrich-plan": _cmd_enrich_plan,
    "enrich-apply": _cmd_enrich_apply,
}
