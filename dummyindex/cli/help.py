"""Help text for `dummyindex context <subcommand>`."""
from __future__ import annotations


USAGE = """\
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
  rebuild [--changed] [--full] [path] [--root DIR] [--docs PATH]...
                                    Rebuild .context/ (use --changed for
                                    incremental). On a curated/enriched index,
                                    --changed preserves the taxonomy +
                                    enrichment and only refreshes deterministic
                                    artefacts; --full forces a destructive
                                    re-cluster (discards curated taxonomy).
                                    --docs takes the same form as `init`. NOT
                                    run from a hook anymore — the SessionStart
                                    hook surfaces drift and Claude updates
                                    .context/ in-session.
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
  enrich-plan [path] [--root DIR]   Emit .context/cache/_enrich_plan.json (work-list).
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
  scaffold-feature [--root DIR] --id ID --name "..." [--summary "..."] --file PATH [--file PATH]...
                                    Atomically create a NEW features/<id>/
                                    folder for net-new files the council
                                    decided form their own feature: writes
                                    feature.json (members derived from
                                    map/symbols.json, confidence EXTRACTED),
                                    a deterministic spec.md stub, and docs.md;
                                    appends to INDEX.json and regenerates
                                    INDEX.md + graph.{json,html}. NEVER
                                    re-clusters. Rejects a duplicate id, a
                                    reserved 'community-*' id, no --file, or a
                                    file missing/outside the repo.
  assign-files [--root DIR] --feature ID --file PATH [--file PATH]...
                                    Atomically add files to an EXISTING
                                    features/<id>/feature.json (files ∪ new,
                                    members recomputed from map/symbols.json),
                                    update its INDEX.json counts, and
                                    regenerate INDEX.md + graph. PRESERVES the
                                    feature's enriched spec.md/plan.md/
                                    concerns.md. Already-assigned files are
                                    skipped (idempotent). Rejects a missing
                                    feature, no --file, or a file
                                    missing/outside the repo.
  unassign-files [--root DIR] --feature ID --file PATH [--file PATH]...
                                    Atomically REMOVE files from an existing
                                    feature (the subtractive inverse of
                                    assign-files): files minus the given set,
                                    members recomputed, INDEX counts + graph
                                    refreshed, .pending-enrichment re-set. Used
                                    when a source file was deleted or moved.
                                    Tolerates files that no longer exist on disk
                                    (the point). Idempotent on a not-owned path.
                                    Refuses to empty a feature (use
                                    features-remove). Preserves enriched docs.
  features-remove [--root DIR] --feature ID [--force]
                                    Atomically DELETE a feature whose code is
                                    gone: drop the folder (incl. enriched docs +
                                    flows), its INDEX.json entry, and its
                                    graph.json node/edges; regenerate INDEX.md.
                                    Refuses if the feature still owns files that
                                    exist on disk (it's live — unassign the dead
                                    paths instead); --force overrides.
  mark-enriched [--root DIR] --feature ID
                                    Clear a feature's .pending-enrichment
                                    marker after the council (re-)enriched it.
                                    Set by scaffold-feature/assign-files; while
                                    set, reconcile-stamp refuses to advance the
                                    anchor past the feature. Idempotent (no
                                    marker → no-op).
  reconcile [path] [--root DIR] [--json]
                                    Read-only commit-anchored drift report:
                                    diffs meta.indexed_commit..HEAD (+ working
                                    tree) and lists drifted features, removed
                                    files, unassigned new files, and features
                                    awaiting enrichment. --json emits the
                                    report for the council procedure. Writes
                                    nothing.
  reconcile-stamp [path] [--root DIR] [--force]
                                    Advance meta.indexed_commit to HEAD — the
                                    reconcile boundary, run after the council
                                    placed every unassigned file and enriched
                                    every placed/drifted feature. REFUSES
                                    (exit 1) while unassigned files or
                                    awaiting-enrichment features remain (does
                                    NOT block on drift alone); --force anchors
                                    anyway and warns what it skipped. Off-git
                                    is a no-op.
  council-log [--root DIR] --feature ID --stage N --agent NAME --status STATE [--note "..."]
                                    Append to features/<id>/council/_council-log.json.
                                    Status: started|complete|failed|skipped.
  council-batch [--root DIR] --next [--mode light|standard|deep] [--cap N] [--tree-enrich] [--json]
                                    Next parallel batch of council dispatch-units
                                    (earliest incomplete stage across features).
  memory session-start|roll|init|nudge|breadcrumb [path] [--root DIR]
                                    Session-memory store under .context/session-memory/.
                                    session-start: emit the SessionStart block
                                    (silent if the remember plugin is present).
                                    roll: relocate dated entries now→recent→archive
                                    (idempotent). init: create the store stubs.
                                    nudge: Stop-hook handoff CTA (significant
                                    sessions, once per session). breadcrumb:
                                    PreCompact deterministic now.md entry.
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
  equip [apply] [path] [--root DIR] [--dry-run] [--for-proposal S] [--specialist C] [--json]
                                    Build loop — render this repo's project-tuned
                                    toolkit into .claude/ from .context/ + preflight
                                    and record it in .context/equipment.json (v2):
                                    a <stack>-implementer + <stack>-tester agent, a
                                    <proj>-reviewer agent, and a <proj>-verify skill,
                                    each grounded in the repo's conventions; plus a
                                    PostToolUse format hook WIRED into settings.json
                                    (sentinel DUMMYINDEX_EQUIP) when a formatter is
                                    detected. A capability a template backs (db /
                                    security / performance / docs / search) is
                                    GENERATED as a real <proj>-<cap>-specialist file
                                    (marker + version + origin_hash, lifecycle-managed
                                    like the core four); a capability with NO template
                                    (e.g. frontend) is ADOPTED manifest-only (path="",
                                    a project or registry agent). --for-proposal S
                                    scopes this to the capabilities S's plan.md/
                                    checklist.md demand (RLS / tenant-isolation count
                                    as security). --specialist C also generates C.
                                    Additive + never-clobber: a user file is skipped;
                                    a hand-edited generated file (USER_MODIFIED) is
                                    preserved forever. --dry-run writes nothing.
  equip add-specialist CAPABILITY [--root DIR] [--dry-run] [--json]
                                    Generate one grounded specialist on demand
                                    (db | security | performance | docs | search) as a
                                    <proj>-CAPABILITY-specialist agent, on top of the
                                    existing toolkit. Idempotent + additive; a later
                                    plain `equip` preserves it. An unknown CAPABILITY
                                    (no template) is rejected with the valid list.
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
  audit start|show --describe "..." [--scope PATH]... [--mode light|standard|deep]
        [--model opus-4.7|sonnet-4.6|haiku-4.5] [--slug S] [--force] [--root DIR] [--json]
                                    On-demand argue-and-audit panel. `start`
                                    scaffolds .context/audits/<slug>/ (audit.json,
                                    description.md, catalog.json, findings/) and
                                    emits the persona catalog; the /dummyindex-audit
                                    skill picks a TASK-DEPENDENT panel and runs the
                                    rebuttal debate (capped at 3 rounds, stops early
                                    on agreement). `show --slug S` reports state +
                                    completed rounds + report path. --model is
                                    REQUIRED unless .context/config.json provides
                                    one (never silently defaulted). Does NOT require
                                    a full .context/ index.
  audit-log --slug S --round N --persona P --status STATE [--note "..."] [--root DIR]
                                    Append to audits/<slug>/_debate-log.json (debate
                                    resumption). Status: started|complete|failed|skipped.
"""
