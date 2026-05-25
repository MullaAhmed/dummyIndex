"""Help text for `dummyindex context <subcommand>`."""
from __future__ import annotations


_USAGE = """\
Usage: dummyindex context <subcommand> [args]

Subcommands:
  init [path] [--root DIR] [--no-hooks] [--docs PATH]...
                                    Initialize .context/ in the enclosing
                                    repo (default scope: cwd; default root:
                                    cwd if scope is a subdir of cwd, else
                                    scope itself). --no-hooks skips installing
                                    the auto-refresh git + Claude Code hooks.
                                    --docs PATH (repeatable) adds external doc
                                    folders to the source-docs catalog;
                                    in-repo docs (README, CHANGELOG, docs/,
                                    ADR/, RFC/, ARCHITECTURE.md, SECURITY.md,
                                    BRIEF.md, plus any *.md at the repo root)
                                    are discovered automatically.
  rebuild [--changed] [path] [--root DIR] [--docs PATH]...
                                    Rebuild .context/ (use --changed for
                                    incremental). --docs takes the same form
                                    as `init`.
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
  query "..." [--root DIR] [--top-k N] [--budget N] [--json]
                                    PageIndex-style retrieval. Scores features
                                    against the query by token overlap with
                                    name/summary/files/symbols; prints the
                                    top-K with cited markdown excerpts. No
                                    LLM in the loop.
  reality-check [--root DIR] --feature ID [--demote] [--json]
                                    Post-synthesis fact-check. Pulls concrete
                                    claims ("X calls Y", "file.py:42") out of
                                    the feature's canonical docs, verifies
                                    against map/symbols.json + symbol-graph +
                                    source. Writes _reality-check.{json,md}
                                    to the feature folder. --demote flips
                                    confidence to AMBIGUOUS on contradiction.
"""
