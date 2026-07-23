# Plan — Universal multi-harness support: host-adaptive skill preamble + platform-agnostic install with repair of older installs

> Ordered, file-path-naming tasks. Cite reused symbols from
> `.context/map/symbols.json` where you can reuse instead of writing new.

## Tasks

1. **Portable-host preamble + boundary alias helper** —
   `dummyindex/installer/common.py` (tests in `tests/test_install.py`).
   Replace `_CODEX_SKILL_PREAMBLE` with `_PORTABLE_HOST_PREAMBLE` (three
   behavior-class rows; product names as parenthetical examples only; fallback
   row carries the "never write `.claude/**`" / "ask the user directly"
   sentinels). Add `normalize_platform_arg(value: str) -> str` — accepts
   `claude|agents|both` plus deprecated `codex`, returns the existing internal
   token (`agents`→`"codex"`), prints the deprecation notice exactly once at
   the boundary. **`SUPPORTED_PLATFORMS`, `platforms_for()`, and all internal
   `"codex"` comparisons stay unchanged** (no internal rename — the
   config-domain platform validation in `context/domains/config.py`,
   `_register_codex_user_skill`, `_remove_codex_guidance`, and onboarding all
   keep working untouched). Keep `CODEX_SKILL_REL`; add
   `AGENTS_SKILL_REL = CODEX_SKILL_REL` (one import-equality test).
   `render_skill()` changes only the injected constant; frontmatter-at-byte-
   zero splice and `PACKAGE_VERSION` substitution are reused as-is.

2. **Host-neutral managed AGENTS.md block** —
   `dummyindex/context/output/agents_md.py` (tests in
   `tests/context/output/test_agents_md.py`).
   Rewrite project and user-global block *bodies* to host-neutral text.
   **`AGENTS_BEGIN_MARKER`/`AGENTS_END_MARKER` byte strings are pinned
   unchanged** (back-compat replace-in-place; add a pin test + a 0.33.0-era
   fixture test asserting exactly one block after refresh with user bytes
   preserved). Reuse untouched: `bootstrap_project_agents_md`,
   `bootstrap_global_agents_md`, `preflight_project_agents_md`,
   `remove_project_agents_md`, `remove_global_agents_md`, ownership
   semantics, and the marker plumbing + atomic writer in
   `dummyindex/context/output/bootstrap.py`. No change to
   `dummyindex/codex_guidance.py`.

3. **Parse boundaries** — `dummyindex/installer/args.py`,
   `dummyindex/installer/uninstall.py` (arg parsing only),
   `dummyindex/__main__.py`, `dummyindex/cli/bootstrap.py`,
   `dummyindex/cli/init.py` (ingest/init `--platform`),
   `dummyindex/cli/onboard.py` (tests in `tests/cli/`, plus the
   `parse_install_args` tuple pins in `tests/test_install.py`).
   Route every `--platform` parse through `normalize_platform_arg`; extend
   usage/help strings to `claude|agents|both`; add `--dedupe <user|project>`
   and `--force-downgrade` to install parsing. Keep the exit-code contract
   (2 = usage). Update the exact `--help` line pins and 7-tuple arity pins
   enumerated in task 6.

4. **Repair module + family-removal helper** — new
   `dummyindex/installer/repair.py`; edits in
   `dummyindex/installer/uninstall.py` and `dummyindex/cli/check.py`
   (tests in new `tests/test_install_repair.py`, fixtures under
   `tests/fixtures/`).
   Lift the four-root stamp scan from `cli/check.py` `_read_skill_stamps`
   into `repair.py` as the single scanner (frozen dataclass
   `InstalledCopy(scope, host, path, stamp)`); `check --versions` consumes
   it. Implement: ownership evidence (stamp or legacy
   `## Codex host compatibility` heading; never dir-name alone), staleness
   (parsed stamp < `PACKAGE_VERSION`; newer/unknown → report-only unless
   `--force-downgrade`), orphaned-sibling reporting, per-root symlink
   preflight (reuse `_symlinked_skill_install_directory` semantics with the
   user-scope allowlist), per-copy best-effort error isolation (one stderr
   line per failure; follows the `AgentsMdCleanupResult` precedent).
   Extract `_remove_skill_family(base, host)` from `uninstall()` (sibling
   walk + `_first_symlink_component` no-follow guards +
   `_remove_owned_tree_no_follow`) shared by `uninstall()` and dedupe;
   dedupe never calls the `uninstall()` entry point and never touches
   commands or guidance blocks. Home==project root collision guard.

5. **Wire repair into install** — `dummyindex/installer/install.py`
   (integration tests in `tests/test_install_repair.py`).
   On every `install` run: repair only the invocation's selected platforms ×
   targeted scope root by reusing `_install_skill_family` (already
   overwrites + stamps via `.dummyindex_version`, `install.py:275-278`) for
   stale-proven copies; report-only for everything else (remediation hint =
   exact install command); honor `--skill-only` semantics; refresh managed
   blocks through the existing ownership-aware bootstrap primitives; print
   the active Codex home in the repair report; `--dedupe` branch invokes
   `_remove_skill_family`.

6. **Skill-body host-language sweep** — `dummyindex/skills/skill.md`,
   `dummyindex/skills/{plan,build,equip,audit,gc,memory,update}/SKILL.md`,
   companions under `dummyindex/skills/{agents,council,retrieval}/` that
   mention the Codex branch (tests in `tests/test_skills_doc_hygiene.py`).
   Rename the "Codex path" to "portable host path" keeping read-only
   guarantees and `— via` binding-tag semantics; the update skill documents
   repair-on-update. Extend
   `test_installed_skill_frontmatter_is_agent_skills_portable` with the
   installed-dir/name match via the `_SIBLING_SKILLS` mapping (no duplicate
   test). Known-breaking pins to update (never weaken-to-green):
   `tests/test_install.py:225-246` (pins `## Codex host compatibility` and
   `--platform codex` in rendered bodies), `:788` (usage string), `:842-856`
   (exact `--help` lines), every `parse_install_args` tuple-arity assert;
   `tests/test_skills_doc_hygiene.py:335/:363` (`**Codex:**` split anchors —
   preserve their invariant intent under the new anchors).

7. **Docs + doc-sync** — `docs/COMMANDS.md`, `README.md`, `CHANGELOG.md`
   (doc-sync assertion beside the existing idiom in
   `tests/cli/test_cli_doc_sync.py`).
   Document `--platform agents`, the `codex` alias/deprecation, `--dedupe`,
   `--force-downgrade`, repair-on-update, and the free-win note that Cursor
   reads `.claude/agents/` natively. Doc-sync test asserts
   `--platform agents` and `--dedupe` appear in `docs/COMMANDS.md`.

8. **Context reconcile** — curated docs for
   `.context/features/codex-guidance/` and
   `.context/features/install-surface/` via the read-only reconcile →
   recouncil → `reconcile-stamp` procedure (content update only; feature ids
   unchanged; done criterion: reconcile reports no remaining delta for the
   two features). — via /dummyindex --recouncil

9. **Verification** — full suite + lint per project conventions
   (`uv run pytest -q`, `uv run ruff check .`); confirm the repair matrix and
   alias byte-identity acceptance items pass as tests (the end-to-end
   scenarios live as integration tests in `tests/test_install_repair.py`,
   not inside the verify skill). — via /dummyindex-verify

## Tooling map (Claude Code host)

Generated equipment covers the work: `python-implementer` (tasks 1–5),
`python-tester` (task 6 test work and TDD pairing throughout),
`dummyindex-reviewer` (post-implementation review),
`dummyindex-docs-specialist` (task 7) — all `.claude/agents/` generated
agents, so those tasks stay untagged per policy. Task 8 is bound to
`/dummyindex --recouncil` (main-session reconcile procedure); task 9 to the
installed `/dummyindex-verify` skill (suite + lint — exactly its charter).
No uncovered capability; no new plugin discovery needed.

## Critique fold (one round, three critics)

Adopted: boundary-alias direction reversed (arch BLOCK/risk BLOCK-1); repair
scope = selected platforms × targeted root, report-only elsewhere,
`--skill-only` honored (risk BLOCK-2 / arch 2 / testability 2); symlink
preflight + no-follow dedupe + `~/.codex/skills` sentinel test (risk BLOCK-3
/ testability 3); `_remove_skill_family` extraction (arch 3 / risk HIGH-1);
single stamp scanner lifted from `cli/check.py` (arch 4); downgrade/unknown
report-only + `--force-downgrade` (risk HIGH-2); ownership-evidence gating +
orphaned-sibling reporting + always-overwrite decision recorded (risk
HIGH-3); staleness-gated rewrites + atomic writes (risk MEDIUM-4); per-copy
error isolation (risk MEDIUM-1); ownership-preserving block refresh (risk
MEDIUM-2); CODEX_HOME gap reported (risk MEDIUM-3); flag-only dedupe
(risk MEDIUM-6 / testability 6); 3-row behavior-class preamble (arch 8);
full marker byte pins + marker-line exemption + exactly-one-block fixture
(arch 6 / risk LOW-1); installed-label frontmatter check extending the
existing hygiene test (testability BLOCK / arch 5 / risk MEDIUM-5); rendered-
output assertions (testability 5); byte-identity alias test (testability 4);
alias regression tests for guidance registration/removal (risk BLOCK-1
mitigations); breaking-pin enumeration (testability 13); flat
`tests/test_install_repair.py` + explicit markers + `tests/fixtures/` home
(arch 9 / testability 14); docs-specialist named in tooling map
(testability 8); reconcile done-criterion (testability 10); consistency
block gains `codex-guidance` (arch 10). Deliberately left: platform StrEnum
(moot once no internal rename — arch 7); skipping temp CODEX_HOME global
refresh (optional polish); `tests/installer/` package (flat file chosen).
