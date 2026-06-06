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
  check [path] [--root DIR] [--docs PATH]... [--auto-refresh] [--quiet]
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
  memory session-start|roll|init [path] [--root DIR]
                                    Session-memory store under .context/session-memory/.
                                    session-start: emit the SessionStart block
                                    (silent if the remember plugin is present).
                                    roll: relocate dated entries now→recent→archive
                                    (idempotent). init: create the store stubs.
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
  onboard [path] [--root DIR] --model opus-4.7|sonnet-4.6|haiku-4.5
          [--scope repo|subdir|explicit] [--scope-path PATH]
          [--mode light|standard|deep] [--hook|--no-hook] [--doc PATH]...
          [--defaults]
                                    Persist the user's council preferences to
                                    .context/config.json (choices only, never
                                    API keys). The interactive 5-question flow
                                    lives in the skill; this is the persistence
                                    surface it calls. --model is REQUIRED unless
                                    --defaults is passed (model is never silently
                                    defaulted). --defaults / --no-onboarding write
                                    a default .context/config.json non-interactively
                                    (CI/scripted) — repo/standard/sonnet-4.6/hook on,
                                    ignoring other flags.
  config show [path] [--root DIR]   Print .context/config.json. Exit 1 when no
                                    config exists yet. (get/set reserved for a
                                    future release.)
  preflight [path] [--root DIR] [--json]
                                    Read-only inventory of the repo's existing
                                    Claude Code setup BEFORE any write: existing
                                    .claude/settings.json validity + user hooks,
                                    .claude/rules/, .claude/agents/, CLAUDE.md
                                    managed-block state, and git-clean status.
                                    Prints a "what I'll touch vs leave alone"
                                    summary (markdown, or --json). Touches nothing.
  doc-reorg guard|list|backup|restore [path] [--root DIR] [--json]
                                    Safety net for the DESTRUCTIVE in-place doc
                                    reorg (the rewrites themselves happen in the
                                    session via Edit, with per-file confirm):
                                      guard   - exit 0 if the tree is clean, else 1
                                      list    - the in-repo docs a reorg considers
                                      backup  - snapshot every doc under
                                                .context/_doc_backups/<utc>/
                                      restore - `--from <backup-dir>`; restores
                                                content and reports reorg-created
                                                files to drop with `git clean`.
  propose --slug S --title "..." [--root DIR] [--force]
                                    Build loop — grounded planning. Scaffolds
                                    .context/proposals/<slug>/ (proposal.json +
                                    spec.md / plan.md / checklist.md), then runs a
                                    deterministic consistency scan (reuses `query`,
                                    no LLM) recording related features + conventions
                                    into proposal.json + a `## Consistency` block in
                                    spec.md. --force overwrites an existing proposal.
  equip [apply] [path] [--root DIR] [--dry-run] [--for-proposal S] [--json]
                                    Build loop — render this repo's project-tuned
                                    toolkit into .claude/ from .context/ + preflight
                                    and record it in .context/equipment.json (v2):
                                    a <stack>-implementer + <stack>-tester agent, a
                                    <proj>-reviewer agent, and a <proj>-verify skill,
                                    each grounded in the repo's conventions; plus a
                                    PostToolUse format hook WIRED into settings.json
                                    (sentinel DUMMYINDEX_EQUIP) when a formatter is
                                    detected, and registry/project specialists ADOPTED
                                    (manifest-only) to cover capability gaps.
                                    --for-proposal S scopes adoption to the
                                    capabilities S's plan.md/checklist.md demand.
                                    Additive + never-clobber: a user file is skipped;
                                    a hand-edited generated file (USER_MODIFIED) is
                                    preserved forever. --dry-run writes nothing.
  equip status [--root DIR] [--json]
                                    Classify every generated item against its
                                    origin-hash baseline: pristine / user-modified /
                                    missing, with each item's version.
  equip refresh [--root DIR] [--dry-run]
                                    Re-render PRISTINE-and-stale items, re-baseline +
                                    minor-bump. USER_MODIFIED is skipped forever.
  equip reset NAME [--root DIR]     Restore one generated item to its pristine
                                    render (the escape hatch), re-baseline + bump.
  equip uninstall [--root DIR] [--dry-run]
                                    Remove PRISTINE generated files + the
                                    DUMMYINDEX_EQUIP hook + the manifest;
                                    USER_MODIFIED files are kept and reported.
  equip patch --item NAME --from-file F [--root DIR]
                                    Sanctioned evolution: apply an exact-once
                                    old→new patch (F is JSON {"old","new"}) to a
                                    generated item, re-baseline + patch-bump so it
                                    stays PRISTINE.
  build --proposal S (--next | --check "<item>" | --status) [--json]
                                    Build loop — drive a proposal's checklist.md
                                    (deterministic state; the dummyindex-build skill
                                    orchestrates dispatch). --next prints the first
                                    unchecked item + its mapped equipment agent (or
                                    general-purpose fallback) + grounding paths;
                                    --check flips an item to - [x] (idempotent);
                                    --status reports done/total and, when complete,
                                    prints `dummyindex context rebuild --changed`.
"""
