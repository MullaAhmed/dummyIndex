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
                                    the SessionStart drift hook.
                                    --docs PATH (repeatable) adds external doc
                                    folders to the source-docs catalog;
                                    in-repo docs (README, CHANGELOG, docs/,
                                    ADR/, RFC/, ARCHITECTURE.md, SECURITY.md,
                                    BRIEF.md, plus any *.md at the repo root)
                                    are discovered automatically.
  rebuild [--changed] [path] [--root DIR] [--docs PATH]...
                                    Rebuild .context/ (use --changed for
                                    incremental). --docs takes the same form
                                    as `init`. NOT run from a hook anymore —
                                    the SessionStart hook surfaces drift and
                                    Claude updates .context/ in-session.
  bootstrap [path] [--root DIR]     Write/regenerate the CLAUDE.md managed
                                    block at <root>/.claude/CLAUDE.md.
  check [path] [--root DIR] [--auto-refresh] [--quiet]
                                    Drift check: compare current source
                                    hashes to .context/cache/manifest.json.
                                    --auto-refresh triggers rebuild --changed
                                    if drift is detected. Manual only.
  plan-update [path] [--root DIR]   Drift report for the SessionStart hook.
                                    Prints a markdown summary (to stdout) of
                                    features whose source files have been
                                    edited since the matching .context/
                                    feature docs were last touched. Output
                                    is empty when nothing is stale. Drift
                                    clears naturally when the agent updates
                                    a feature doc (its mtime advances past
                                    the source's).
  hooks install|uninstall|status [path] [--root DIR]
                                    Manage the SessionStart drift hook
                                    (.claude/settings.json). Installed
                                    automatically by `init` unless --no-hooks
                                    is passed. `install` also scrubs the
                                    legacy git/post-commit + Claude/PostToolUse
                                    entries from pre-0.13.5 installs.
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
  features-merge [--root DIR] --from ID --into ID [--as-section NAME]
                                    [--note "rationale"]
                                    Absorb a trivial feature into another as a
                                    section (used during architect consolidation
                                    of dangling features). --as-section must be
                                    in the allowlist (currently: 'supporting'),
                                    default 'supporting'. Auto-appends a stage-0
                                    architect entry to the target's council-log;
                                    --note overrides the default "merged-from:"
                                    rationale.
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
  dev-pick [path] [--root DIR] --feature ID
                                    Resolve which stack-specialist "dev"
                                    persona should author a feature's docs.
                                    First-match-wins over the feature's file
                                    list + dependency tokens harvested from
                                    repo manifests. Prints {persona_id,
                                    subagent_type, framework} as JSON to
                                    stdout. Deterministic, no LLM.
"""
