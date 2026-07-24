# Plan — Symlink-aware single-source skill install: one real .agents/skills tree, .claude/skills symlinked

> Ordered, file-path-naming tasks. Cite reused symbols from
> `.context/map/symbols.json` where you can reuse instead of writing new.
> Revised once after the 3-critic panel (ledger at the bottom).

## Tasks

1. **Layer hoists (no behavior change)** — `dummyindex/installer/common.py`,
   `dummyindex/installer/repair.py`, `dummyindex/installer/uninstall.py`.
   Move `_remove_owned_tree_no_follow` (`uninstall.py:169`) and the
   ownership-evidence trio `_read_stamp` / `_has_legacy_codex_heading` /
   `is_owned_copy` + `_VERSION_STAMP_NAME` / `_LEGACY_CODEX_HEADING_RE`
   (`repair.py:63-64,205-210,481-505`) into `common.py`; `repair.py` and
   `uninstall.py` re-export (existing importers — `install.py:147`, tests —
   untouched). Proof: full suite passes with zero test edits.

2. **CLI flags `--link` / `--copy` + `LinkMode` + default-both flip** —
   `dummyindex/installer/args.py` (`parse_install_args` → 11-tuple;
   **`platform` default `"claude"` → `"both"`**; `_print_install_usage`;
   **parse-time exit 2** for `--link --copy` and `--link --platform
   agents`), `dummyindex/__main__.py:289-312` (forward the resolved
   `LinkMode`), `dummyindex/installer/install.py` + `uninstall.py`
   signature defaults (`platform: str = "both"` — flagless uninstall
   removes what flagless install wrote), `tests/test_install.py` (parse
   cases: default both+AUTO, each flag, both rejections; existing
   claude-default assertions updated deliberately — this is the documented
   compatibility break, called out in CHANGELOG). `LinkMode(str, Enum)`
   AUTO/LINK/COPY lives in `installer/common.py` (task 1's layer — no new
   import edges). **Reuse**: the existing flag-loop idiom
   (`args.py:92-181`).

3. **Link primitives** — `dummyindex/installer/link.py` (new) +
   `tests/test_install_link_primitives.py` (new, `@pytest.mark.unit`).
   `FamilyLinkState(str, Enum)` (6 states incl. `MATERIALIZED`, `MISSING`),
   frozen `FamilyLinkClassification` + `LinkResult`, `classify_family_link`
   (parent-chain rule via `_first_symlink_component` (`common.py:233`);
   scope-root rule; readlink compared as `PurePath(...).parts`; fail-closed
   `OSError`/`RuntimeError` → FOREIGN; DANGLING needs positive-ENOENT),
   `family_link_target`, `relative_link_value`, `create_family_links`
   (temp-link-first → rename-aside → re-verify evidence on the renamed tree
   → rename into place → delete last; stamp-required replacement +
   hand-edits caveat; `target_is_directory=True`; per-family
   `FileExistsError` continue; EPERM abort + Windows hint + uncovered-family
   names; post-create resolution check with dotfiles hint; DI seam
   `symlink_fn=os.symlink` — call it as a parameter, never
   `Path.symlink_to`, so failure injection needs no monkeypatch),
   `verify_family_links`, `remove_dangling_family_links` (parent-chain
   re-check immediately before each unlink), `run_link_install`
   (AUTO/LINK/COPY tri-state, capability pre-probe → AUTO whole-run copy
   fallback / strict-LINK exit 1, sequencing helper so `install.py` gains
   only a dispatch call — it is 735 lines, over the >600 split threshold).
   **Import law**: `link.py` imports `common.py` ONLY. TDD matrix first:
   real dir / healthy-lexical / healthy-resolved / dangling / MISSING /
   MATERIALIZED / foreign-value / foreign-absolute / absolute-but-correct
   (normalize) / symlinked `.claude` parent / symlinked `.claude/skills`
   parent / user-scope allowlisted host root / dotfiles-divergent root /
   symlink loop / unreadable target / Windows-shaped readlink value /
   cross-scope-root rows; then creation: fresh, idempotent (LinkResult
   0/0), proven-dir replace, heading-only refusal, unproven refusal,
   Nth-call `symlink_fn` failure (survivors + uncovered names asserted),
   crash-window recovery (temp artifact + renamed-aside tree → rerun
   converges). **Reuse**: `skill_rel` / `skills_root_rel` /
   `_SIBLING_SKILLS` / `_first_symlink_component` /
   `_remove_owned_tree_no_follow` / `is_owned_copy` (all `common.py` after
   task 1).

4. **Preflight admission + install() default-link + forced migration** —
   `dummyindex/installer/install.py` + `tests/test_install_link.py` (new,
   markers per module). The security-sensitive change, own tests: preflight
   (`install.py:104-146`) admits a family dir iff it classifies
   `OURS_*`/`MATERIALIZED` (every LinkMode); FOREIGN + deeper links refuse
   byte-identically (regression-assert the message). Write path stays
   unconditional: `_install_skill_family` (`install.py:264`) never writes
   when the family dir `is_symlink()`. Direct-write loop
   (`install.py:157-170`) consults `classify_family_link` first —
   `OURS_DANGLING` under COPY reports (locks out the
   `mkdir(exist_ok=True)` `FileExistsError` crash at `install.py:268`),
   under AUTO/LINK defers to `create_family_links`. Sequencing pinned:
   `plan_repairs` → direct-write → `execute_repairs` → **then**
   `run_link_install`/`create_family_links`; Claude-side
   `_install_skill_family` skipped when linking. **AUTO matrix** (both is
   now the flagless default): both → link by default + convert duplicated
   proven Claude families (`migrated ->` line + hand-edits caveat per
   family; equal-stamp copies ARE converted — that's the force) + migrate
   claude-only layouts to universal (write `.agents` real, convert
   `.claude` to links, write AGENTS.md); claude (explicit narrowing) →
   link-to-existing when a proven current `.agents` family exists, else
   copy as today; agents (explicit narrowing) → never touches
   `.claude/**`, duplicated layout reported with the flagless-install
   remediation. Strict LINK exits 1 where AUTO falls
   back (`--force-downgrade` named when stamp newer/unknown). Assert
   link-mode installs still write `/tokens`, CLAUDE.md registration,
   hooks, auto-init. `--copy` characterization test: COPY never calls
   `create_family_links` (spy via DI seam) and leaves a linked layout
   as-is. **Reuse**: `_install_skill_family`, `platforms_for`
   (`common.py:96`), `_symlinked_skill_install_directory`
   (`install.py:354`, unchanged for companion-dir depth).

5. **Repair classification + duplicates + dedupe sweep** —
   `dummyindex/installer/repair.py` + `tests/test_install_repair.py`
   (extend). `plan_repairs` (`repair.py:213`): classify Claude copies first
   — `OURS_HEALTHY` → `linked -> .agents (current)` report, never a rewrite;
   `OURS_DANGLING`/`MATERIALIZED` → report (healed by the same run under
   AUTO/LINK; remediation named under COPY); proven real Claude copy beside
   a proven `.agents` family → `migration candidate` report line;
   FOREIGN → existing path, message asserted unchanged. **Repair writes no
   links** (single write owner = `create_family_links`; no `RepairPlan`
   field, no `execute_repairs` heal branch). `_find_duplicate_families`
   (`repair.py:620`): exclude a cross-scope pair only when one side resolves
   into the other's scope root (`_same_root`-style, fail closed) — the
   user-real + project-link pair stays reported; test both directions.
   `dedupe` (`repair.py:369`): linked side → link-only removal (lock
   `uninstall.py:110-115` no-follow with a test); after removing a codex
   family, call `remove_dangling_family_links`. **Reuse**:
   `scan_installed_copies`, `_scope_root`, `_host_root_allowlist`,
   `describe_plan` line format.

6. **Uninstall sweep** — `dummyindex/installer/uninstall.py` +
   `tests/test_install.py` (extend). After codex-family removal
   (`--platform agents`/`both`), call `remove_dangling_family_links` on the
   scope root; claude-platform link removal locked with a test (existing
   `uninstall.py:110-115` behavior). Foreign links untouched (test).
   **Reuse**: `_remove_skill_family`, `remove_dangling_family_links`
   (task 3).

7. **check --versions labels** — `dummyindex/cli/check.py`
   (`_read_skill_stamps` suffix ` (linked)` / ` (materialized link)` +
   remediation line) + `tests/cli/test_check_versions.py` (extend).
   **Reuse**: `scan_installed_copies`, `verify_family_links`.

8. **Docs + help** — `dummyindex/cli/help.py` (install section:
   link-by-default, `--copy`/`--link` tri-state, the one-line "why
   .claude → .agents"), `README.md` (install docs: linked layout is the
   default, **updating dummyindex migrates duplicated repos automatically**,
   `--copy` opt-out, Windows `core.symlinks`/Developer-Mode caveat + AUTO
   copy-fallback, `MATERIALIZED` recovery), `dummyindex/skills/update/SKILL.md`
   (step-3 note: update both preserves a linked layout AND converts a
   duplicated one — expect `migrated ->` lines the first time; `--copy`
   suppresses).

9. **End-to-end lifecycle** — `tests/test_install_link.py` (extend,
   `@pytest.mark.integration`, in-process): one tmp git repo — default
   install (linked) → idempotent rerun (LinkResult 0/0) → **forced
   migration**: seed a duplicated layout (both real trees, equal stamps),
   plain rerun converts with `migrated ->` lines → stale-stamp repair
   (links untouched) → dangling heal via AUTO rerun → materialized-file
   replace → EPERM pre-probe AUTO copy-fallback (DI raiser) → dedupe →
   `uninstall --platform agents` sweep → `uninstall both` → clean tree.
   User-scope lifecycle + dotfiles-divergent fallback case. Capability
   guard (`pytest.skip` when `os.symlink` unavailable) on real-symlink
   tests only.

10. **Full verify** — run the whole suite + ruff on the branch and report
    output. — via /dummyindex-verify

11. **One-time copy-mode diff evidence** — from the merge-base commit and
    from HEAD, run `install --skill-only --scope project --dir <tmp>` (git
    worktree for the merge-base) and `diff -r` the resulting `.claude/` +
    `.agents/` trees; paste the empty diff into the PR description.

12. **GATE** Live-host verification (main session, user-visible): scratch
    git repo with the linked layout → fresh Claude Code session lists and
    invokes `/dummyindex`; fresh `codex` session lists/invokes `$dummyindex`
    from `.agents/skills` (or Cursor's picker shows the family). Record the
    observed evidence in the PR.

13. **Reconcile the docs index** — fold link mode into
    `.context/features/install-surface/spec.md`, advance the anchor
    (`dummyindex context reconcile-stamp`); observable: reconcile report
    clean for `install-surface`. — via /dummyindex

## Critique ledger (one revision, three critics)

**Folded (BLOCK/HIGH)**: preflight admission was missing entirely and owns
the linked-layout acceptance (arch BLOCK / risk BLOCK-1) → task 4;
create-then-clear crash window + TOCTOU → temp-link-first rename dance +
`MISSING` state (risk BLOCK-2/HIGH-6) → task 3; parent-chain rule in
`classify_family_link` + pre-unlink re-check (risk BLOCK-3) → task 3;
link↔uninstall import cycle → hoist to `common.py` (arch HIGH) → task 1;
repair-writes-links dropped — single write owner (arch MEDIUM / risk
MEDIUM-7); sequencing pinned so `execute_repairs` can't write through fresh
links (risk HIGH-1); direct-write dangling-link crash gated (arch HIGH /
risk HIGH-2); dotfiles-divergent resolution check + user-scope tests (arch
MEDIUM / risk HIGH-3 / test H2); `MATERIALIZED` state for
`core.symlinks=false` (risk HIGH-4); `target_is_directory` +
`FileExistsError` isolation + EPERM-only hint (risk HIGH-5); duplicates
exclusion narrowed to resolves-into-other-root (arch HIGH / risk MEDIUM-1);
dedupe sweep shared with uninstall (risk MEDIUM-2); fail-closed
classification + positive-ENOENT dangling (risk MEDIUM-3); readlink parts
comparison (risk MEDIUM-4); stamp-required replacement + caveat (risk
MEDIUM-5); scope-root rule (risk MEDIUM-6); enum + record split (arch
MEDIUM); evidence trio to common (arch MEDIUM); byte-identical criterion
replaced with suite + characterization + merge-base diff (test B1); DI
`symlink_fn` instead of monkeypatch (test H1); GATE/via items split so the
checklist parser routes them correctly (test H3); LinkResult-based
idempotency observable + capability guard (test M1); enumerated-family
assertions instead of `dummyindex*` glob — avoids the equip
`dummyindex-verify` collision (test M2); link-mode side-surface assertions
(test M3); reconcile item tagged + observable (test M4); exit-code split
2-at-parse / 1-at-runtime (arch LOW / risk LOW-1); absolute-link
normalization (risk LOW-2); `--force-downgrade` in the claude+link
remediation (risk LOW-3); Nth-call raiser (test L2); concrete codex GATE
observable (test L3); pytest markers (test L4); link orchestration hosted
in link.py to spare install.py's line budget (arch LOW).

**Deliberately not folded**: dropping `_find_duplicate_families` changes
entirely (arch HIGH suggested drop; risk MEDIUM-1's narrower
resolves-into-other-root exclusion is adopted instead — it handles the
one-physical-copy case the blanket drop would misreport); no via tags added
to tasks 1-7/9 (test L1 — automatic capability matching routes
python-implementer/python-tester; forcing via would push them main-session).

**User-directed revision (2026-07-24, after the panel)**: forced migration
+ universal-by-default. Link mode is the DEFAULT (`LinkMode.AUTO`) **and
`--platform` defaults to `both`** — the product goal is "one flagless
`dummyindex install` / `/dummyindex-update` and the repo works in Claude
Code, Codex, Cursor, Gemini CLI". A plain install/update converts
duplicated layouts automatically, including equal-stamp copies (repair
never touches equal stamps — migration deliberately does, with the
hand-edits caveat printed), and upgrades claude-only layouts to universal
(writes `.agents` real, links `.claude`, writes AGENTS.md). `--copy` opts
out per run; `--link` is the strict form (error instead of fallback);
`--platform claude|agents` become explicit narrowing. AUTO carries a
capability pre-probe so a Windows checkout falls back to copy with a
warning instead of failing the update. The panel reviewed the opt-in
draft; the post-panel deltas (equal-stamp conversion, pre-probe fallback,
agents-only reporting, default-platform flip — a documented compatibility
break) were folded consistent with the panel's evidence gates and
single-write-owner rulings but were not themselves re-paneled — flagged
for extra reviewer attention at build time on tasks 2 and 4.
