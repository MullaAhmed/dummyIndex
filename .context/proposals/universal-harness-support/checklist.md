# Checklist — Universal multi-harness support: host-adaptive skill preamble + platform-agnostic install with repair of older installs

> Flat, top-to-bottom list derived from the plan tasks + the spec's
> Acceptance items. Tick `- [x]` only after verifying each item.

## Wave 1 — independent foundations

- [x] Portable-host preamble (`_PORTABLE_HOST_PREAMBLE`, 3 behavior-class
      rows + fallback sentinels) + `normalize_platform_arg` boundary helper +
      `AGENTS_SKILL_REL` alias in `dummyindex/installer/common.py`; update
      the rendered-body pins this breaks in `tests/test_install.py:225-246`
      and add render/alias/import-equality unit tests (TDD)
- [x] Host-neutral AGENTS.md block bodies with full marker byte strings
      pinned in `dummyindex/context/output/agents_md.py`; marker-pin test,
      0.33.0-era block fixture test (exactly one block after refresh, user
      bytes preserved) in `tests/context/output/test_agents_md.py`
- [x] Skill-body host-language sweep (`dummyindex/skills/**` — "portable host
      path" wording, update-skill repair-on-update section) + extend
      `test_installed_skill_frontmatter_is_agent_skills_portable` with the
      installed-dir/name match and new-wording sentinels in
      `tests/test_skills_doc_hygiene.py`

## Wave 2 — parse boundaries

- [x] Route every `--platform` parse through `normalize_platform_arg`
      (`installer/args.py`, `installer/uninstall.py` args, `__main__.py`,
      `cli/bootstrap.py`, `cli/init.py`, `cli/onboard.py`); add
      `--dedupe <user|project>` + `--force-downgrade` parsing; update
      usage/help/tuple pins (`tests/test_install.py:788`, `:842-856`,
      `parse_install_args` arity asserts) and `tests/cli/` coverage

## Wave 3 — repair core

- [x] `dummyindex/installer/repair.py`: lift `_read_skill_stamps` from
      `cli/check.py` into the single four-root scanner
      (`InstalledCopy` frozen dataclass), ownership-evidence + staleness +
      downgrade/unknown gating, orphaned-sibling reporting, symlink
      preflight, per-copy error isolation; extract
      `_remove_skill_family(base, host)` in `installer/uninstall.py` shared
      with dedupe; `cli/check.py` consumes the scanner; unit tests +
      fixtures in `tests/test_install_repair.py` + `tests/fixtures/`

## Wave 4 — wiring + docs

- [x] Wire scoped repair + `--dedupe` + `--force-downgrade` into
      `dummyindex/installer/install.py` (selected platforms × targeted root;
      report-only elsewhere with remediation hint; `--skill-only` honored;
      active Codex home printed; ownership-preserving block refresh);
      integration tests incl. repair matrix, dedupe both branches,
      home==project guard, `~/.codex/skills` sentinel, error-isolation
      branches in `tests/test_install_repair.py`
- [x] Docs: `docs/COMMANDS.md`, `README.md`, `CHANGELOG.md` (`--platform
      agents`, codex alias/deprecation, `--dedupe`, `--force-downgrade`,
      repair-on-update, Cursor-reads-`.claude/agents` note); doc-sync assert
      in `tests/cli/test_cli_doc_sync.py`

## Wave 5 — context reconcile

- [ ] Reconcile curated docs for `.context/features/codex-guidance/` and
      `.context/features/install-surface/` until reconcile reports no
      remaining delta, then stamp the anchor — via /dummyindex --recouncil

## Wave 6 — verification + acceptance

- [ ] Full suite + lint green (`uv run pytest -q`, `uv run ruff check .`),
      new tests carry explicit markers — via /dummyindex-verify
- [ ] Acceptance: fresh `--platform agents` install renders the portable
      preamble; rendered output carries no Codex-identity claim outside the
      pinned marker lines
- [ ] Acceptance: `--platform codex` is byte-identical to `agents` + exactly
      one deprecation notice; user-scope alias install still registers
      Codex guidance; uninstall still removes managed blocks
- [ ] Acceptance: preamble contains the three behavior-class rows with the
      fallback sentinels ("never write `.claude/**`", "ask the user
      directly")
- [ ] Acceptance: 0.33.0-era AGENTS.md block replaced in place — exactly one
      block, user bytes preserved, marker bytes unchanged
- [ ] Acceptance: repair matrix holds (targeted scope×platform rewritten;
      untargeted reported + byte-identical; current-stamp no-churn; newer/
      unknown stamp report-only without `--force-downgrade`)
- [ ] Acceptance: symlink refusals + `~/.codex/skills` sentinel untouched;
      dedupe removes only the named scope's family, commands + guidance
      survive
- [ ] Acceptance: installed frontmatter passes agentskills.io constraints
      incl. installed-dir/name match
- [ ] Acceptance: `docs/COMMANDS.md` doc-sync test passes; update skill
      documents the repair rerun; reconcile reports no delta for the two
      features and the anchor is stamped
