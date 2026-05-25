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
  init [path] [--root DIR] [--no-hooks]
                                    Initialize .context/ in the enclosing
                                    repo (default scope: cwd; default root:
                                    cwd if scope is a subdir of cwd, else
                                    scope itself). --no-hooks skips installing
                                    the auto-refresh git + Claude Code hooks.
  rebuild [--changed] [path] [--root DIR]
                                    Rebuild .context/ (use --changed for
                                    incremental).
  bootstrap [path] [--root DIR]     Write/regenerate the CLAUDE.md managed
                                    block at <root>/.claude/CLAUDE.md.
  check [path] [--root DIR] [--auto-refresh] [--quiet]
                                    Drift check: compare current source
                                    hashes to .context/cache/manifest.json.
                                    --auto-refresh triggers rebuild --changed
                                    if drift is detected.
  hooks install|uninstall|status [path] [--root DIR]
                                    Manage the auto-refresh hooks (git
                                    post-commit + Claude Code PostToolUse +
                                    SessionStart). Installed automatically
                                    by `init` unless --no-hooks is passed.
  enrich-plan [path] [--root DIR]   Emit .context/_enrich_plan.json (work-list).
  enrich-apply [path] [--root DIR] --from-json FILE
                                    Merge {node_id: abstract} JSON into
                                    tree.json.
  features-rename [--root DIR] --from ID --to ID [--name "..."] [--summary "..."]
                                    Atomically rename a feature folder and
                                    update every JSON reference.
  flow-remove [--root DIR] --feature ID --flow ID
                                    Atomically drop a flow from a feature
                                    (deletes flow files, updates feature.json
                                    + INDEX.json + INDEX.md + graph.json).
  features-merge [--root DIR] --from ID --into ID --as-section NAME
                                    Absorb a trivial feature into another as a
                                    section (used during chairman consolidation
                                    of dangling features).
  section-write [--root DIR] --feature ID --section NAME --from-file PATH
                                    Atomic markdown placement into
                                    features/<id>/<section>.md.
  council-log [--root DIR] --feature ID --stage N --agent NAME --status STATE [--note "..."]
                                    Append to features/<id>/council/_council-log.json.
                                    Status: started|complete|failed|skipped.
  refresh-indexes [path] [--root DIR]
                                    Rebuild .context/INDEX.md and
                                    features/INDEX.md + features/graph.{json,html}
                                    from disk. Also migrates legacy graph/ layout.
  conventions-write [--root DIR] --section NAME --from-file PATH
                                    Atomic markdown placement into
                                    .context/conventions/<section>.md (for
                                    agent-authored docs like folder-organization,
                                    coding-practices, testing, data-access).
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


_FLAGS_TAKING_VALUE = frozenset(
    {
        "--from", "--to", "--name", "--summary", "--from-json",
        "--feature", "--flow", "--section", "--from-file",
        "--stage", "--agent", "--status", "--note",
        "--into", "--as-section",
    }
)


def _parse_path_and_root(
    args: list[str],
    *,
    take_positional: bool = True,
) -> tuple[Path, Optional[Path], list[str]]:
    """Pull the positional scope + optional `--root` out of `args`.

    Returns ``(scope, explicit_root, remaining_args)`` so callers can
    parse their own flags (e.g. `--changed`, `--from-json`) from
    ``remaining_args``.

    ``take_positional=False`` for subcommands that have no leading
    path argument (``features-rename`` only takes flags) — the helper
    then leaves every non-``--root`` token in ``remaining_args``.

    Tokens that look like values for known flags (``--from value``,
    ``--name value``, etc.) are forwarded to ``remaining_args`` as a
    pair so subcommand parsers see them in the right order.
    """
    scope = Path(".")
    explicit_root: Optional[Path] = None
    remaining: list[str] = []
    i = 0
    saw_scope = False
    while i < len(args):
        a = args[i]
        if a == "--root" and i + 1 < len(args):
            explicit_root = Path(args[i + 1])
            i += 2
        elif a.startswith("--root="):
            explicit_root = Path(a.split("=", 1)[1])
            i += 1
        elif a in _FLAGS_TAKING_VALUE and i + 1 < len(args):
            # Forward the flag *and* its value untouched so the
            # subcommand parser sees them together.
            remaining.append(a)
            remaining.append(args[i + 1])
            i += 2
        elif take_positional and not a.startswith("--") and not saw_scope:
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

    # Pull --no-hooks out of args before path/root parsing.
    install_hooks = "--no-hooks" not in args
    args = [a for a in args if a != "--no-hooks"]

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

    if install_hooks:
        from dummyindex.context.hooks import install as install_hooks_fn

        hook_result = install_hooks_fn(out_root)
        if hook_result.installed:
            print(f"  hooks      ->  installed: {', '.join(hook_result.installed)}")
        elif hook_result.skipped:
            print(f"  hooks      ->  already current ({len(hook_result.skipped)})")
        if hook_result.errors:
            for name, err in hook_result.errors:
                print(f"  hooks warning ({name}): {err}", file=sys.stderr)

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
    claude_md = out_root / ".claude" / "CLAUDE.md"
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


def _cmd_features_rename(args: list[str]) -> int:
    from dummyindex.context.features import FeatureRenameError, rename_feature

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)

    from_id: Optional[str] = None
    to_id: Optional[str] = None
    new_name: Optional[str] = None
    new_summary: Optional[str] = None
    leftover: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--from" and i + 1 < len(rest):
            from_id = rest[i + 1]
            i += 2
        elif a.startswith("--from="):
            from_id = a.split("=", 1)[1]
            i += 1
        elif a == "--to" and i + 1 < len(rest):
            to_id = rest[i + 1]
            i += 2
        elif a.startswith("--to="):
            to_id = a.split("=", 1)[1]
            i += 1
        elif a == "--name" and i + 1 < len(rest):
            new_name = rest[i + 1]
            i += 2
        elif a.startswith("--name="):
            new_name = a.split("=", 1)[1]
            i += 1
        elif a == "--summary" and i + 1 < len(rest):
            new_summary = rest[i + 1]
            i += 2
        elif a.startswith("--summary="):
            new_summary = a.split("=", 1)[1]
            i += 1
        else:
            leftover.append(a)
            i += 1
    if leftover:
        print(
            f"error: unknown argument(s) for `features-rename`: {leftover}",
            file=sys.stderr,
        )
        return 2
    if not from_id or not to_id:
        print(
            "error: --from <id> and --to <id> are both required",
            file=sys.stderr,
        )
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        result = rename_feature(
            features_dir,
            from_id=from_id,
            to_id=to_id,
            new_name=new_name,
            new_summary=new_summary,
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.from_id == result.to_id:
        print(f"context features-rename: updated metadata for {result.to_id}")
    else:
        print(
            f"context features-rename: {result.from_id}  →  {result.to_id}"
        )
    if result.new_name or result.new_summary:
        if result.new_name:
            print(f"  name:    {result.new_name}")
        if result.new_summary:
            print(f"  summary: {result.new_summary}")
    if result.files_touched:
        print(f"  touched: {len(result.files_touched)} file(s)")
    return 0


def _cmd_refresh_indexes(args: list[str]) -> int:
    from dummyindex.context.bootstrap import bootstrap_claude_md
    from dummyindex.context.docs import refresh_index_md
    from dummyindex.context.features import (
        rebuild_features_graph,
        refresh_features_index_md,
    )

    scope, explicit_root, rest = _parse_path_and_root(args)
    if rest:
        print(
            f"error: unknown argument(s) for `refresh-indexes`: {rest}",
            file=sys.stderr,
        )
        return 2
    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    # ----- v0.6+ migration: old `.context/graph/` and oversized CLAUDE.md ---
    _migrate_legacy_layout(context_dir, out_root)

    rels = refresh_index_md(context_dir)
    print(
        f"context refresh-indexes: regenerated {context_dir / 'INDEX.md'} "
        f"({len(rels)} entries)"
    )

    features_dir = context_dir / "features"
    if features_dir.is_dir():
        try:
            refresh_features_index_md(features_dir)
            print(f"  + regenerated {features_dir / 'INDEX.md'}")
        except FileNotFoundError:
            # features/INDEX.json missing — nothing to refresh.
            pass
        try:
            graph_json, graph_html = rebuild_features_graph(features_dir)
            print(f"  + rebuilt    {graph_json} (folder · file · feature · flow)")
            print(f"  + rebuilt    {graph_html}")
        except FileNotFoundError:
            pass
    return 0


def _migrate_legacy_layout(context_dir: Path, out_root: Path) -> None:
    """One-shot migrations for projects that were ingested by pre-v0.6 dummyindex.

    - `.context/graph/` (pyvis HTML + graph.json + GRAPH_REPORT.md) is gone.
      Move what's salvageable into `.context/features/` and delete the folder.
    - CLAUDE.md managed block was 40+ lines; shrink to the v0.6 3-line pointer.
    """
    legacy_graph = context_dir / "graph"
    if legacy_graph.is_dir():
        features_dir = context_dir / "features"
        features_dir.mkdir(parents=True, exist_ok=True)

        # Migrate legacy graph.json → features/symbol-graph.json. If the new
        # location is already populated (a v0.7 rebuild ran first), the
        # legacy file is just stale — delete it.
        old_json = legacy_graph / "graph.json"
        new_json = features_dir / "symbol-graph.json"
        if old_json.exists():
            if new_json.exists():
                old_json.unlink()
            else:
                old_json.replace(new_json)

        # Migrate legacy GRAPH_REPORT.md → features/COMMUNITIES.md. Same rule.
        old_report = legacy_graph / "GRAPH_REPORT.md"
        new_report = features_dir / "COMMUNITIES.md"
        if old_report.exists():
            if new_report.exists():
                old_report.unlink()
            else:
                old_report.replace(new_report)

        # Drop the pyvis HTML — it's the hairball v0.6 dropped.
        legacy_html = legacy_graph / "graph.html"
        if legacy_html.exists():
            legacy_html.unlink()

        # Remove the folder if it's empty now.
        try:
            for leftover in legacy_graph.iterdir():
                print(
                    f"  migration: leaving unexpected file in legacy graph/: "
                    f"{leftover.name}",
                    file=sys.stderr,
                )
                break
            else:
                legacy_graph.rmdir()
                print(
                    f"  migration: dropped legacy {legacy_graph} "
                    f"(symbol-graph + COMMUNITIES moved to features/)"
                )
        except OSError as exc:
            print(f"  migration warning: {exc}", file=sys.stderr)

    # Shrink an oversized CLAUDE.md managed block and relocate the file from
    # the project root (pre-v0.7.2) to .claude/CLAUDE.md (current).
    _migrate_claude_md_location(out_root)


def _migrate_claude_md_location(out_root: Path) -> None:
    """Relocate the managed block from <root>/CLAUDE.md to <root>/.claude/CLAUDE.md.

    Pre-v0.7.2 installs wrote the managed block to ``<root>/CLAUDE.md``.
    Newer installs keep CLAUDE.md inside ``.claude/`` so the project root
    stays clean. This helper:

    1. Always (re)writes ``.claude/CLAUDE.md`` with a current managed block.
    2. Strips the legacy managed block from ``<root>/CLAUDE.md`` if present.
    3. Deletes ``<root>/CLAUDE.md`` if stripping leaves it effectively empty
       (no user content beyond whitespace).
    """
    from dummyindex.context.bootstrap import (
        BEGIN_MARKER,
        END_MARKER,
        bootstrap_claude_md,
    )

    new_path = out_root / ".claude" / "CLAUDE.md"
    legacy_path = out_root / "CLAUDE.md"

    legacy_had_managed_block = False
    legacy_residue: Optional[str] = None
    if legacy_path.exists():
        try:
            legacy_text = legacy_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"  migration warning: cannot read {legacy_path}: {exc}", file=sys.stderr)
            return
        if BEGIN_MARKER in legacy_text and END_MARKER in legacy_text:
            legacy_had_managed_block = True
            begin = legacy_text.index(BEGIN_MARKER)
            end = legacy_text.index(END_MARKER) + len(END_MARKER)
            legacy_residue = (legacy_text[:begin] + legacy_text[end:]).strip()

    if not legacy_had_managed_block and new_path.exists():
        # Nothing to migrate; .claude/CLAUDE.md already exists. Skip the
        # bootstrap call so we don't churn its mtime on every refresh.
        return

    try:
        bootstrap_claude_md(new_path)
    except Exception as exc:
        print(f"  migration warning: writing {new_path} failed: {exc}", file=sys.stderr)
        return

    if not legacy_had_managed_block:
        print(f"  migration: wrote {new_path.relative_to(out_root)}")
        return

    try:
        if legacy_residue:
            legacy_path.write_text(legacy_residue + "\n", encoding="utf-8")
            print(
                f"  migration: relocated CLAUDE.md managed block to "
                f"{new_path.relative_to(out_root)} (user content preserved at "
                f"{legacy_path.relative_to(out_root)})"
            )
        else:
            legacy_path.unlink()
            print(
                f"  migration: relocated CLAUDE.md to "
                f"{new_path.relative_to(out_root)} (removed empty root file)"
            )
    except OSError as exc:
        print(f"  migration warning: cleaning {legacy_path} failed: {exc}", file=sys.stderr)


def _cmd_check(args: list[str]) -> int:
    """Drift detection. Compare current source hashes to the stored manifest."""
    from dummyindex.context.manifest import compare
    from dummyindex.pipeline.detect import detect

    scope, explicit_root, rest = _parse_path_and_root(args)
    auto_refresh = False
    quiet = False
    leftover: list[str] = []
    for a in rest:
        if a == "--auto-refresh":
            auto_refresh = True
        elif a == "--quiet":
            quiet = True
        else:
            leftover.append(a)
    if leftover:
        print(f"error: unknown argument(s) for `check`: {leftover}", file=sys.stderr)
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        if not quiet:
            print(
                f"error: {context_dir} not found. Run `dummyindex ingest` first.",
                file=sys.stderr,
            )
        return 2

    # Detect current source files. Use scope for the scan (matches build_all).
    detection = detect(scope.resolve() if scope.is_absolute() else (Path.cwd() / scope).resolve())
    current = [Path(p) for p in detection.get("files", {}).get("code", [])]

    drift = compare(context_dir, root=out_root, current_files=current)

    if drift.is_clean:
        if not quiet:
            print("context check: clean (no drift)")
        return 0

    if not quiet:
        print(
            f"context check: drift detected — "
            f"{len(drift.added)} added, {len(drift.modified)} modified, "
            f"{len(drift.removed)} removed"
        )
        # Don't dump every file when there's a lot — first 5 of each.
        for label, paths in (("added", drift.added), ("modified", drift.modified), ("removed", drift.removed)):
            if not paths:
                continue
            sample = paths[:5]
            print(f"  {label}:")
            for p in sample:
                print(f"    - {p}")
            if len(paths) > len(sample):
                print(f"    ... +{len(paths) - len(sample)} more")

    if not auto_refresh:
        # Exit code 1 signals drift exists (useful for shell scripts).
        return 1

    # Auto-refresh: run rebuild --changed.
    if not quiet:
        print("context check: auto-refreshing…")
    rc = _cmd_rebuild(["--changed", str(scope)] + (["--root", str(explicit_root)] if explicit_root else []))
    return rc


def _parse_kv_flags(rest: list[str]) -> tuple[dict[str, str], list[str]]:
    """Tiny --key value parser for the council subcommands.

    Returns (parsed, leftover). Recognized keys come from
    _FLAGS_TAKING_VALUE. Boolean flags / unknown args go to leftover.
    """
    parsed: dict[str, str] = {}
    leftover: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in _FLAGS_TAKING_VALUE and i + 1 < len(rest):
            parsed[a.lstrip("-")] = rest[i + 1]
            i += 2
        elif "=" in a and a.startswith("--") and a.split("=", 1)[0] in _FLAGS_TAKING_VALUE:
            k, v = a.split("=", 1)
            parsed[k.lstrip("-")] = v
            i += 1
        else:
            leftover.append(a)
            i += 1
    return parsed, leftover


def _cmd_features_merge(args: list[str]) -> int:
    """Atomically merge a trivial feature into another as a section."""
    from dummyindex.context.features import FeatureRenameError, merge_feature

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)
    parsed, leftover = _parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `features-merge`: {leftover}",
            file=sys.stderr,
        )
        return 2
    from_id = parsed.get("from")
    into_id = parsed.get("into")
    as_section = parsed.get("as-section", "supporting")
    if not from_id or not into_id:
        print(
            "error: --from <id> and --into <id> are both required "
            "(optional: --as-section NAME, default 'supporting')",
            file=sys.stderr,
        )
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        result = merge_feature(
            features_dir,
            from_id=from_id,
            into_id=into_id,
            as_section=as_section,
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context features-merge: {result.from_id}  →  {result.to_id} "
        f"(as `{result.section}`, {len(result.files_touched)} files touched)"
    )
    return 0


def _cmd_flow_remove(args: list[str]) -> int:
    """Atomically remove a flow from a feature."""
    from dummyindex.context.features import FeatureRenameError, remove_flow

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)
    parsed, leftover = _parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `flow-remove`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    flow_id = parsed.get("flow")
    if not feature_id or not flow_id:
        print(
            "error: --feature <id> and --flow <id> are both required",
            file=sys.stderr,
        )
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        result = remove_flow(features_dir, feature_id=feature_id, flow_id=flow_id)
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.files_touched:
        print(
            f"context flow-remove: dropped {flow_id} from {feature_id} "
            f"({len(result.files_touched)} file(s) touched)"
        )
    else:
        print(f"context flow-remove: no-op (flow {flow_id} not present)")
    return 0


def _cmd_section_write(args: list[str]) -> int:
    """Atomic placement of a markdown into a feature's section."""
    from dummyindex.context.features import FeatureRenameError, write_section

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)
    parsed, leftover = _parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `section-write`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    section = parsed.get("section")
    from_file = parsed.get("from-file")
    if not all((feature_id, section, from_file)):
        print(
            "error: --feature <id>, --section <name>, --from-file <path> are all required",
            file=sys.stderr,
        )
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        target = write_section(
            features_dir,
            feature_id=feature_id,
            section=section,
            source_file=Path(from_file),
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"context section-write: {target}")
    return 0


def _cmd_conventions_write(args: list[str]) -> int:
    """Atomic placement of an agent-authored markdown into conventions/."""
    from dummyindex.context.conventions import (
        ConventionSectionError,
        write_convention_section,
    )

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)
    parsed, leftover = _parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `conventions-write`: {leftover}",
            file=sys.stderr,
        )
        return 2
    section = parsed.get("section")
    from_file = parsed.get("from-file")
    if not section or not from_file:
        print(
            "error: --section <name> and --from-file <path> are both required",
            file=sys.stderr,
        )
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        target = write_convention_section(
            context_dir, section=section, source_file=Path(from_file)
        )
    except ConventionSectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"context conventions-write: {target}")
    return 0


def _cmd_council_log(args: list[str]) -> int:
    """Append a council-log entry for a (feature, stage, agent) triple."""
    from dummyindex.context.council import CouncilLogError, append_log

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)
    parsed, leftover = _parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `council-log`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    stage = parsed.get("stage")
    agent = parsed.get("agent")
    log_status = parsed.get("status")
    note = parsed.get("note")
    if not all((feature_id, stage, agent, log_status)):
        print(
            "error: --feature <id>, --stage <n>, --agent <name>, --status <state> are all required",
            file=sys.stderr,
        )
        return 2

    try:
        stage_int = int(stage)
    except ValueError:
        print(f"error: --stage must be an integer, got {stage!r}", file=sys.stderr)
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        entry = append_log(
            features_dir,
            feature_id=feature_id,
            stage=stage_int,
            agent=agent,
            status=log_status,
            note=note,
        )
    except CouncilLogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context council-log: {feature_id} stage={entry.stage} "
        f"agent={entry.agent} status={entry.status}"
    )
    return 0


def _cmd_hooks(args: list[str]) -> int:
    """Manage auto-refresh hooks: install | uninstall | status."""
    from dummyindex.context.hooks import (
        install as hooks_install,
        status as hooks_status,
        uninstall as hooks_uninstall,
    )

    if not args:
        print("error: usage: dummyindex context hooks install|uninstall|status", file=sys.stderr)
        return 2

    verb, rest = args[0], args[1:]
    if verb not in ("install", "uninstall", "status"):
        print(f"error: unknown hooks verb {verb!r}", file=sys.stderr)
        return 2

    scope, explicit_root, leftover = _parse_path_and_root(rest)
    if leftover:
        print(f"error: unknown argument(s): {leftover}", file=sys.stderr)
        return 2

    project_root = _resolve_context_root(scope, explicit_root=explicit_root)

    if verb == "install":
        result = hooks_install(project_root)
        if result.installed:
            print(f"hooks install: installed {', '.join(result.installed)}")
        if result.skipped:
            print(f"hooks install: skipped (already current): {', '.join(result.skipped)}")
        for name, err in result.errors:
            print(f"  error ({name}): {err}", file=sys.stderr)
        return 0 if not result.errors else 1
    if verb == "uninstall":
        result = hooks_uninstall(project_root)
        if result.removed:
            print(f"hooks uninstall: removed {', '.join(result.removed)}")
        if result.skipped:
            print(f"hooks uninstall: skipped: {', '.join(result.skipped)}")
        for name, err in result.errors:
            print(f"  error ({name}): {err}", file=sys.stderr)
        return 0 if not result.errors else 1
    # status
    s = hooks_status(project_root)
    print(f"hooks status @ {project_root}")
    print(f"  git/post-commit       {'✓' if s.git_post_commit else '✗'}")
    print(f"  claude/PostToolUse    {'✓' if s.claude_post_tool_use else '✗'}")
    print(f"  claude/SessionStart   {'✓' if s.claude_session_start else '✗'}")
    return 0 if s.all_installed else 1


_HANDLERS: dict[str, Callable[[list[str]], int]] = {
    "init": _cmd_init,
    "rebuild": _cmd_rebuild,
    "bootstrap": _cmd_bootstrap,
    "check": _cmd_check,
    "hooks": _cmd_hooks,
    "enrich-plan": _cmd_enrich_plan,
    "enrich-apply": _cmd_enrich_apply,
    "features-rename": _cmd_features_rename,
    "features-merge": _cmd_features_merge,
    "flow-remove": _cmd_flow_remove,
    "section-write": _cmd_section_write,
    "council-log": _cmd_council_log,
    "conventions-write": _cmd_conventions_write,
    "refresh-indexes": _cmd_refresh_indexes,
}
