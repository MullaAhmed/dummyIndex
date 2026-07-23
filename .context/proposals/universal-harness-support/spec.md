# Spec — Universal multi-harness support: host-adaptive skill preamble + platform-agnostic install with repair of older installs

> Scaffolded by `dummyindex context propose`. Flesh out the intent
> and contracts below, then keep the **Acceptance** checklist honest.

## Intent

dummyindex renders two host flavors today: Claude Code (`.claude/skills/`,
managed `CLAUDE.md` block, hooks, equipment) and Codex (`.agents/skills/` +
managed `AGENTS.md` block). The July 2026 harness survey (verified against
Codex 0.144.1 and Antigravity binaries plus current docs for ten more
harnesses) shows the ecosystem has converged on exactly the two conventions
the Codex flavor already uses: **`AGENTS.md`** as the universal project
instruction file and **`.agents/skills/*/SKILL.md`** (agentskills.io) as the
cross-harness skill store — scanned natively by Codex, Cursor, Copilot CLI,
OpenCode, Amp, Gemini CLI, Goose, Pi, and Cline.

The blocker: `render_skill()` bakes a **Codex-only preamble** ("This installed
copy is running in **Codex**…") into every `.agents/skills` copy, so any other
harness that discovers the skill receives instructions for the wrong host. The
managed `AGENTS.md` block likewise speaks Codex-only vocabulary. Installs made
by older dummyindex versions keep those stale files until something rewrites
them.

This proposal makes one indexed project work in Claude Code, Codex, Cursor,
and the other major AGENTS.md/Agent-Skills harnesses, and makes a rerun of
`dummyindex install` / the `dummyindex-update` skill **repair older installed
files to the new standard** — stale preambles, stale managed blocks, and
duplicate user+project scope copies — within strict scope and safety bounds.

For whom: anyone pointing more than one coding agent at the same repository.

## Contracts

- **Platform selector — alias at the boundary, stable core.** The public
  selector becomes `--platform claude|agents|both`; `codex` is accepted as a
  **deprecated alias**. Normalization happens in ONE shared helper in
  `installer/common.py` (`normalize_platform_arg(value) -> str`), called by
  every parse boundary (`installer/args.py`, `installer/uninstall.py` args,
  `cli/bootstrap.py`, `cli/init.py`/ingest, `cli/onboard.py`). The helper maps
  `agents` → the existing internal `"codex"` token and prints the deprecation
  notice for `codex` **once, at the parse boundary only**. Internal
  comparisons, `platforms_for()`, config-domain platform validation
  (`context/domains/config.py`), uninstall guidance removal, and onboarding
  are **unchanged** — no internal rename, no silent comparison flips.
  `CODEX_SKILL_REL` keeps its name; `AGENTS_SKILL_REL` is an equal alias.
- **Host-adaptive preamble.** The `.agents/skills` render replaces
  `_CODEX_SKILL_PREAMBLE` with `_PORTABLE_HOST_PREAMBLE`: "identify your host,
  then apply the matching row" over **three behavior-class rows** (not a
  per-product matrix): (1) Claude Code — native vocabulary, prefer the
  `.claude/skills` copy when both exist; (2) skill-native hosts that expose
  installed skills and named/generic subagents (examples: Codex, Cursor,
  Copilot CLI, OpenCode, Amp, Gemini CLI/Antigravity, Goose, Pi, Cline) —
  invoke via the host's skill mechanism, delegate to the host's native
  subagents with the persona mandate inlined; (3) **generic fallback** — use
  native file/search/shell tools, treat Claude tool names as vocabulary not
  requirements, ask the user directly instead of `AskUserQuestion`, and
  **never write `.claude/**`**. Product names appear as parenthetical
  examples only, so harness churn cannot rot the contract. Invariants from
  `render_skill()` hold: YAML frontmatter stays at byte zero; the preamble is
  inserted immediately after the frontmatter close; `__VERSION__`
  substitution unchanged.
- **Host-neutral AGENTS.md block.** Block bodies in
  `context/output/agents_md.py` drop Codex-only invocation claims and become
  host-neutral. **The full byte strings of `AGENTS_BEGIN_MARKER` /
  `AGENTS_END_MARKER` are pinned unchanged** — including the embedded
  "regenerate with `dummyindex install --platform codex`" hint — because the
  byte-preserving primitives match whole marker lines and 0.33.0-era blocks
  must keep being found, replaced in place, and removed. (The `codex` alias
  keeps that embedded remedy functional.) Marker lines are exempt from
  "no Codex-only wording" assertions. Ownership, path-boundary, budget, and
  fallback policies in `codex_guidance.py` are unchanged; block refresh goes
  through the existing ownership-aware bootstrap primitives, so auto-init
  refresh never takes ownership from an explicit project install.
- **Repair on reinstall/update — scoped, evidence-gated, symlink-safe.**
  Rerunning `dummyindex install` (directly or via the `dummyindex-update`
  skill):
  - **Scope of writes**: repair re-renders only copies belonging to the
    invocation's **selected platforms** at the invocation's **targeted scope
    root** (user scope → `$HOME`-rooted trees; project scope → the resolved
    target repo). Every other detected copy is **report-only** with a
    remediation hint (the exact install command that would repair it).
    `--skill-only` behaves as today (skills yes, project init/guidance no).
    `.claude/**` is written only when the Claude platform is selected;
    `.agents/**` only when the agents platform is selected.
  - **Detection**: reuse the four-root `.dummyindex_version` scan that
    already exists in `cli/check.py` (`_read_skill_stamps`), lifted into the
    repair module and consumed by `check --versions` so there is exactly one
    scanner.
  - **Staleness / ownership evidence**: a copy is rewritten only when the
    family shows ownership proof — a `.dummyindex_version` stamp or the
    legacy `## Codex host compatibility` heading — AND its parsed stamp is
    **older than** `PACKAGE_VERSION` (or the legacy heading is present).
    Stamp **newer** than the package, or either side unparseable/`unknown`,
    is report-only (explicit `--force-downgrade` required to write). A
    dir-name match alone never triggers a write. Orphaned siblings (family
    main dir missing) are reported, not rewritten. Installed skill copies
    are recorded as dummyindex-owned, always-overwrite-once-proven artifacts
    (unlike equip's hash-baselined files) — hand-edits to installed copies
    are not preserved, and the report says so when it rewrites.
  - **Symlink safety**: before any repair write or dedupe removal, run the
    identical preflight used by install (`_symlinked_skill_install_directory`
    with the user-scope host-root allowlist); traversal/removal uses
    uninstall's no-follow guards. On a symlinked detected copy: refuse and
    report, never write through.
  - **Atomicity & churn**: rewrite only copies that fail the staleness test
    (no mtime churn on current copies); per-file writes use the
    temp-then-`os.replace` pattern already present in
    `context/output/bootstrap.py`.
  - **Error isolation**: per-copy best-effort — a budget-exceeded block
    (`project_doc_max_bytes`), `UnbalancedMarkersError` on a hand-damaged
    AGENTS.md, or an OSError on one copy prints one stderr report line and
    never aborts the remaining repairs or the install itself.
  - **Duplicates**: same family present at both user and project scope is
    reported with both paths. Removal happens **only** with the explicit
    `--dedupe <user|project>` flag (no interactive prompt — CI-safe); it
    removes only the named scope's skill-family trees via a
    `_remove_skill_family` helper extracted from `uninstall()` (never the
    full `uninstall()` orchestration — commands and guidance blocks are
    untouched). Identical resolved user/project roots (home == project) are
    never treated as duplicates.
  - **Non-goals**: `~/.codex/skills` is never touched (dummyindex never
    wrote there). Blocks written under a *previous* `CODEX_HOME` are not
    discovered; the repair report prints the active Codex home so the gap is
    visible.
- **Skill-body host language.** Packaged skill bodies generalize the
  two-host branch to "Claude Code path" vs "**portable host path**" (the
  current Codex path's read-only guarantees, now naming the behavior
  classes). The binding `— via` gate and doc-hygiene invariants are updated,
  not dropped.
- **Frontmatter conformance.** Every **installed** SKILL.md satisfies
  agentskills.io constraints: `name` matches its installed directory label
  (per the `_SIBLING_SKILLS` mapping — source dirs like `skills/plan/` are
  install-labeled `dummyindex-plan`), name regex `^[a-z0-9]+(-[a-z0-9]+)*$`
  ≤64 chars, `description` 1–1024 chars — enforced by extending the existing
  `test_installed_skill_frontmatter_is_agent_skills_portable`, not a
  duplicate test.
- **Deliberate omissions** (recorded, not planned): no per-harness global
  instruction files beyond the existing `~/.codex/AGENTS.md` registration;
  no `.cursor/agents`/`.codex/agents` equipment rendering (Cursor already
  reads `.claude/agents/` natively — free win, documented); Gemini CLI's
  AGENTS.md-off-by-default documented as a limitation, not worked around;
  no interactive dedupe confirmation.

## Acceptance

- [ ] `dummyindex install --platform agents` installs the `.agents/skills`
      family whose rendered SKILL.md files contain the portable-host preamble
      and — outside the pinned marker lines — neither "running in **Codex**"
      nor `## Codex host compatibility` (assert on rendered output in
      `tests/test_install.py`, not only source hygiene).
- [ ] `--platform codex` renders **byte-identical** skill trees to
      `--platform agents` (install both into separate tmp trees, compare every
      rendered file) and prints exactly one deprecation notice on stderr;
      `--platform agents` still registers user-global Codex guidance on
      user-scope install, and uninstall still removes managed guidance blocks
      (alias regression tests).
- [ ] The rendered preamble contains the three behavior-class rows; the
      fallback row carries the sentinels "never write `.claude/**`" and
      "ask the user directly".
- [ ] The managed AGENTS.md block body is host-neutral while both full marker
      byte strings are unchanged; reinstalling over a 0.33.0-era block
      replaces exactly the marked region, preserves every user byte outside
      it, and leaves **exactly one** managed block (fixture test).
- [ ] Repair matrix (fixture tests, per invocation): agents-only project
      install rewrites a stale project `.agents` copy and does NOT write
      `.claude/**`; claude-only install rewrites a stale project `.claude`
      copy and does NOT write `.agents/**`; a stale copy at the untargeted
      scope is reported with a remediation hint and asserted byte-identical
      after the run; a current-stamp copy is asserted byte-identical
      (no-churn negative case).
- [ ] Downgrade/unknown safety: stamp newer than `PACKAGE_VERSION` or
      unparseable → report-only, unchanged bytes; `--force-downgrade`
      rewrites (both branches tested).
- [ ] Symlink safety: a symlinked detected copy is refused with a report and
      nothing is written through it; `--dedupe` does not follow symlinks; a
      `~/.codex/skills` sentinel file is untouched by a repair run (three
      tests mirroring the existing install/uninstall symlink suites).
- [ ] Duplicate handling: duplicates reported with both paths; nothing
      deleted without `--dedupe <scope>`; with it, only the named scope's
      skill-family trees are removed and slash commands + guidance blocks
      survive (both branches tested); home==project collision is not a
      duplicate.
- [ ] Per-copy error isolation: budget-exceeded and unbalanced-marker
      fixtures each produce one stderr report line and do not abort the
      remaining repairs (tested).
- [ ] Every installed SKILL.md passes the agentskills.io frontmatter
      constraints including the installed-dir/name match (extension of the
      existing hygiene test over a rendered install).
- [ ] Skill bodies name the portable host path; doc-hygiene tests assert the
      new wording sentinel and preserve the existing `— via` gate and
      read-only invariants under the renamed anchors.
- [ ] `docs/COMMANDS.md` and `README.md` document `--platform agents`, the
      `codex` alias/deprecation, `--dedupe`, `--force-downgrade`, and
      repair-on-update; a doc-sync test asserts `--platform agents` and
      `--dedupe` appear in `docs/COMMANDS.md`; the `dummyindex-update` skill
      text instructs the repair rerun.
- [ ] `dummyindex context reconcile` reports no remaining delta for
      `codex-guidance` and `install-surface` after the recouncil pass, and
      the reconcile anchor is stamped.
- [ ] Full suite green (`uv run pytest -q`) and lint clean
      (`uv run ruff check .`); new tests carry explicit
      `@pytest.mark.unit|integration` markers (`--strict-markers`); the
      known-breaking existing pins are updated, never weakened to green
      (see plan task 6 enumeration).

## Open questions

None blocking — decisions taken and recorded: alias normalized to the internal
`"codex"` token at parse boundaries (no internal rename); full marker byte
strings pinned; installed skill copies are always-overwrite-once-proven
(no hash baseline); flag-only dedupe; no per-harness global files; Gemini CLI
limitation documented rather than patched.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `install-surface`
- `codex-guidance`
- `tree-enrich`
- `equip`
- `agent-instructions`
- `bootstrap`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
