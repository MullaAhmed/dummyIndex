# Spec — All authored .context docs and repo docs follow ASD-STE100; dummyindex-update rewrites all context prose to STE

## Intent

dummyindex writes `.context/` docs for every repo that it indexes. The docs now use "English caveman" style. That style drops articles and words. Agents and people misread clipped text.

The user wants all `.context/` prose to follow ASD-STE100 (Simplified Technical English, STE). The rule is product-wide. Every repo that dummyindex indexes gets STE context. An upgrade rewrites all curated context prose to STE.

This repo's own docs also change to STE. That scope is `docs/guide/`, `docs/reference/`, `docs/COMMANDS.md`, `README.md` and the shipped skill markdown under `dummyindex/skills/`.

Decisions from the user (2026-11-12):

1. Scope is product-wide. Change the generator code, the skill prompts and the lint. Do not hand-edit `.context/`.
2. The upgrade path (`/dummyindex-update`) runs the full rewrite. A recouncil writes STE only for the docs that it touches.
3. A deterministic lint checks the rules that a script can detect. The LLM rewrite applies the STE dictionary. The package does not ship the ASD dictionary, because ASD owns its copyright.
4. STE replaces "English caveman" for all persisted docs. Subagent prompts keep the Chinese caveman rule. Commits, PRs and chat replies do not change.
5. A rewritten doc can have more words. The restyle path re-records its word count. A normal edit still cannot make a doc longer.
6. The full rewrite runs only when the STE rule set version changes, not on each release.

Related features: `doc-budget`, `agent-instructions`, `bootstrap`, `codex-guidance`, `install-surface`, `managed-doc-homes`, `feature-taxonomy`. The CLI consistency scan below missed them.

## Contracts

### C1. STE lint — `dummyindex/context/domains/docbudget/style.py`

`lint_text` keeps its signature and its skip rules (code fences, inline code, HTML comments, tables, headings). It also skips YAML frontmatter, because a skill `description:` is trigger text. It accepts CRLF line endings and a UTF-8 BOM. `StyleViolation.rule` gets new values. Each rule has a severity.

| Rule | Severity | Detects | STE basis (Issue 9) |
|---|---|---|---|
| `long-sentence` | strict | A sentence with more than 20 words. No change. | Rule 5.1, max 20 words. |
| `long-paragraph` | strict | A prose paragraph with more than 6 sentences. A list item is its own unit. | Section 6, max 6 sentences. |
| `contraction` | strict | `n't`, `'re`, `'ll`, `'ve`, `'d`, `'m`, and `it's`, `that's`, `there's`, `what's`. | Rule 4.2. |
| `semicolon` | strict | A `;` in prose. | Rule 8.1. |
| `filler` | strict | No change. | Plain technical text. |
| `ing-form` | advice | A word that ends in `ing` and is not in a closed allowlist (`string`, `thing`, `during`, …). | Rule 3.5. |
| `passive` | advice | A `be` form before a participle (`-ed` or a closed irregular list). | Rule 3.6. Passive is allowed in descriptive text when the agent is unknown. |

Invariants:

- Strict rules count toward the style ratchet. Advice rules print as `advice:` lines. They never count and never fail a check. A script cannot find all gerunds and allowed passives. A hard gate on these rules would block good docs.
- The lint is pure and deterministic. It adds no third-party dependency, no NLP and no POS tagger.
- Text in backticks is never flagged. Writers put technical names and identifiers in backticks.
- Some STE rules are not lint rules. These are noun clusters (rule 2.1), articles (rule 4.5), verb tenses (rule 3.2) and dictionary words. The rewrite brief and the writing standard (C3) cover them.
- `STE_RULESET_VERSION` (an integer, start at 1) in `docbudget/constants.py` names the rule set. A change to a strict rule or to the standard text (C3) increments it.
- The rule table comes from a secondary summary of Issue 9 (simplified-english.co.uk). The implementer checks each rule number against the Issue 9 text when it is available.

### C2. STE scope — `dummyindex/context/domains/docbudget/ratchet.py`

The STYLE group gets its own glob set. The CONTEXT word-budget scope does not change.

| Tier | Paths | Enforcement |
|---|---|---|
| Curated | `features/*/spec.md`, `plan.md`, `concerns.md`, `features/*/flows/*.md`, `conventions/*.md`, `playbooks/*.md`, `PROJECT.md`, `architecture/*.md` | Style ratchet. Restyle rewrites them. |
| Workspace | `proposals/*/*.md`, `audits/**/*.md` | Style ratchet. A new file has ceiling 0 for strict rules. Restyle does not rewrite them. GC deletes them. |
| Generated | `HOW_TO_USE.md`, `INDEX.md`, `conventions/naming.md`, `equipment/*.md` | Exempt from the ratchet. A unit test lints the templates (C6). |
| Memory | `session-memory/*.md` | The writing standard only. No lint, no rewrite. |

`ratchet.py` gets `reseed(ratchet, root, rels, group)`. It sets each named entry to the current value, and it can raise an entry. Only restyle (C4), the ruleset transition (below) and the one-time repo rewrite (C8) call it. `update_ratchet` still never raises an entry.

Ruleset transition: the style ratchet file starts with a header line `# ruleset N`. `read_ratchet` ignores lines that start with `#`. When the header is older than `STE_RULESET_VERSION`, the new rules can make recorded docs and unrecorded workspace docs fail.

- `check --style` then prints a re-seed hint and exits 0.
- `check --style --update-ratchet` records each in-scope doc at its current count and writes the new header.
- The non-destructive install refresh (`dummyindex/context/build/enriched_refresh.py`) runs the same re-seed, so an upgraded repo does not fail `check --style`. Restyle then lowers the counts.

### C3. Writing standard — one source of truth

A new constant `STE_DOC_STANDARD` in `dummyindex/context/output/bootstrap.py` holds the short rule text. `ALWAYS_ON_OUTPUT_POLICY` uses it in place of the caveman doc sentence. `ALWAYS_ON_TURN_REMINDER` uses one short pointer ("Repo docs follow ASD-STE100"). The text names these rules:

- One topic per sentence, max 20 words per sentence, max 6 sentences per paragraph.
- Active voice and simple tenses. Keep the articles.
- No contractions, no semicolons, no `-ing` verb forms.
- Max 3 nouns in a cluster. One meaning for each word.
- Technical names go in backticks.
- The check command is `dummyindex context check --style`.

`AGENTS.md`, the managed `CLAUDE.md` block and the Codex guidance get the text through the existing renderers (`agents_md.py`, `claude_md.py`, `codex_guidance.py`). No renderer copies the text. The hand-kept copies that change are `dummyindex/skills/skill.md:59-64`, `docs/COMMANDS.md` and `docs/guide/07-cli.md`. The old pins are in `tests/cli/test_cli_doc_sync_policy_canary.py:285-315`.

### C4. Restyle loop — `dummyindex context restyle plan|begin|next|done|stamp|status`

The logic lives in a new domain package `dummyindex/context/domains/restyle/`. `dummyindex/cli/restyle.py` is wire-only. The run state reuses `dummyindex/context/domains/fleet.py` with a new `kind="restyle"`. The run folder is `.context/fleet/restyle-<ts>/`. A unit id is a feature id or the relative path of one other curated doc. Each unit has one stage, `restyle`.

- `plan` is read-only. It lists the units, the doc count and the strict and advice counts. It prints `already restyled (ruleset N)` when `meta.json` `restyled_ruleset` equals `STE_RULESET_VERSION`. On an index with no curated docs, it prints `nothing to restyle`.
- `begin` needs `--all` or `--max-units N`, as `maintain begin` does. It refuses when an unfinished restyle run exists, and it prints the resume command. For each doc it stores a snapshot. The snapshot holds the protected tokens and the original `mtime_ns`. A copy of the original text goes under `.context/cache/restyle/<run>/`. The cache folder is not committed.
- Protected tokens are `path:line` citations, inline code spans, fenced code blocks and Markdown link targets. Heading levels, the heading count and numerals are also protected.
- The snapshot also counts `not`, `no`, `never`, `only`, `must` and `cannot`. The count expands contractions first (`don't` → `do not`), so the `contraction` fix does not change it. A lost token or a lower count fails. An added token or a higher count gives a warning.
- `next` prints the next unit, its doc paths and the rewrite brief. The brief holds `STE_DOC_STANDARD` and the rule "change the words, not the facts".
- `done <unit>` compares the protected tokens with the snapshot. It refuses (exit 1) when a token is lost or changed, and it names each token. On a pass, it restores the original `mtime_ns` of each doc. Without that, the edit quiets mtime drift in `dummyindex/context/drift.py`. It prints the remaining strict violations, the advice lines and each new inline code span as warnings. These do not fail the unit.
- `stamp` needs each unit done or skipped. It writes `restyled_ruleset` into `meta.json`. It calls `reseed` for the restyled docs in the CONTEXT word ratchet and the STYLE ratchet. It never writes `features/INDEX.json`, `feature.json`, `map/`, `tree.json`, `cache/doc-basis.json` or the reconcile anchor.
- `status` prints the run progress.
- `begin --force` starts a new run when the stamp already matches.

### C5. Update skill — `dummyindex/skills/update/SKILL.md`

A new step "5. Restyle context prose" runs after step 4 verifies the version layers. It runs only on a curated index, and only when `restyle plan` does not print `already restyled`. It shows the `plan` estimate, then runs `begin --all`, one subagent per `next` unit, `done` and `stamp`.

The first hard rule changes. The update still never runs the council, `reconcile` or a re-ingest, and it never changes the taxonomy. It can rewrite curated prose in place, through `restyle` only.

A restyle refusal does not undo the version layers. The final table shows `context prose  restyle pending — resume: dummyindex context restyle status`. On success the row is `context prose  restyled N doc(s) (ASD-STE100 ruleset N)`.

### C6. Generated templates

These templates write generated `.context/` docs, and they follow STE:

- `dummyindex/context/output/instructions.py` (HOW_TO_USE, overview, playbooks)
- `dummyindex/context/output/docs.py` (`generate_index_md`)
- `dummyindex/context/build/conventions.py` (`write_naming_md`)
- `dummyindex/skills/equip/templates/*.tmpl`
- `dummyindex/context/domains/proposals/store.py` (the `context propose` scaffold for `spec.md`, `plan.md` and `checklist.md`)
- `dummyindex/context/domains/audit/workspace.py` (the audit scaffold)

A new proposal or audit starts from STE text. The plan, audit and build skills then write STE (C7). A test renders them into a temporary repo. It asserts that `lint_text` returns no strict violations.

### C7. Doc-writing prompts

`dummyindex/skills/council/00-overview.md` gets a "Writing standard" section that points to C3. Each skill that writes `.context/` docs gets one line that points to that section and to `dummyindex context check --style`. These skills are plan, audit, build and remember, and the council stages 15, 20, 30, 50 and 65.

### C8. This repo's docs

`docs/guide/*.md`, `docs/reference/*.md`, `docs/COMMANDS.md`, `README.md` and `dummyindex/skills/**/*.md` get a one-time STE rewrite. The baseline on 2026-11-12 is 765 violations in 71 files under the old rules. After the rewrite, a new test `tests/test_repo_doc_style.py` lints them against the ratchet file `tests/data/repo-style-budget.txt`, with each entry at 0. A new file has ceiling 0.

`tests/test_skills_doc_hygiene.py:697-723` checks the real `tests/data/skill-budget.txt`. An item that makes a `SKILL.md` longer calls `reseed` for that file. The suite then stays green between waves. `CHANGELOG.md` is history, and it stays out of scope. The rewrite keeps each command, flag, path and pinned string that `tests/cli/test_cli_doc_sync.py` and `tests/test_skills_doc_hygiene.py` check.

### Non-goals

- Doc-reorg (Phase 5.5) keeps its house-style behavior for the docs of other repos.
- The lint does not check dictionary words, noun clusters, articles or tenses.
- The restyle does not change feature IDs, file sets, folder names, the doc basis or the reconcile anchor.

## Track B — ultrareview fixes (`feat/gui-engine-commands` → `main`)

The user added 10 review findings to this proposal on 2026-11-12. Track B does not depend on the STE work, and it touches different files. The source is the ultrareview of 2026-11-12. Each fix gets a test.

### B1. Toolkit secrets and `.gitignore` (G1a, G1b)

- `dummyindex/context/domains/toolkit/host.py:186` (`write_stash`), `WriteSession.backup` and `preserve_skill` make sure that `.context/.gitignore` ignores the toolkit folder before they write. They reuse `_ensure_managed_lines` (`dummyindex/context/build/upgrade.py:77`). The stale docstring at `host.py:9-14` changes.
- The managed pattern at `upgrade.py:33` changes from `toolkit/` to `/toolkit/`. The pattern then does not hide `.context/features/toolkit/`. An existing unanchored `toolkit/` line changes to the anchored form.

### B2. Toolkit scope resolution (G2a, G2b)

- In `toolkit/mutate.py` `_resolve_scope_and_kind` (`:437-452`), `--allow-project-fallback` uses project-layout matches only. It raises `ambiguous_item` when more than one item matches.
- An item that is live and also in the stash gives one entry. The live entry wins, and the stash entry is a leftover (`toolkit/listing.py:18-30`, `mutate.py:453-464`). `--kind` then resolves the item.

### B3. Plugin install argv (G3a, G3b)

- `toolkit/install.py:194-209` runs `claude plugin marketplace add <repo> --scope user`, then `claude plugin install <key> --scope user`. This is the same sequence as `default_plugins._install_one` (`dummyindex/context/default_plugins.py:608-629`). The argv does not use `--marketplace` or `--json`.
- The `partial_install` hint (`install.py:379-385`) includes `--scope user`. In `toolkit_install` (`toolkit/facade.py:186`), a plugin install without `--scope` uses user scope. `toolkit_mutate` (`facade.py:143`) keeps its project default, because a user-scope default there would repeat the G2a hazard. The review cited `facade.py:181` and `:343`, but the file has 205 lines.

### B4. Features list drops valid features (G4a, G4b)

- `features_list.py:18` takes `CONFIDENCE_VALUES` from `dummyindex.pipeline.enums.ConfidenceLevel`, so `AMBIGUOUS` features stay in the list. The contract enum in `tests/fixtures/contract/features-list.json` adds `AMBIGUOUS`.
- `features_list.py:19` uses the same id rule as `_validate_feature_id` (`dummyindex/context/domains/features/helpers.py:19-33`), so an id with `_` stays in the list.

### B5. Toolkit robustness (G5a, G5b)

- `toolkit/paths.py:108-120` `safe_target` checks symlink containment only for write targets. The read accessors in `host.py:46-53` do not refuse a symlinked `settings.json`.
- 5 sites raise `ToolkitError("malformed_config", …)` and do not crash. `dummyindex/cli/toolkit.py:178-184` then prints the envelope.
  - `host.py:158`: `UnicodeDecodeError`.
  - `mutate.py:98`: a non-UTF-8 file.
  - `mutate.py:179`: a stash entry without `definition`.
  - `bundle.py:61`: a bad item shape.
  - `mutate.py:431`: an item without `name`.

## Acceptance

- [ ] A unit test gives `lint_text` one sample for each new strict rule. Each sample gives one violation of its rule. The same words in backticks give no violation.
- [ ] A unit test shows that `ing-form` and `passive` samples print `advice:` lines and leave the `check --style` exit code at 0.
- [ ] A `lint_text` test with CRLF line endings and a BOM gives the same result as the LF version. A long `description:` line in YAML frontmatter gives no violation.
- [ ] A fixture repo with a `# ruleset 0` style ratchet passes `check --style` with a re-seed hint. After `check --style --update-ratchet`, the header is `# ruleset 1`.
- [ ] A test shows that the enriched refresh re-stamp keeps `restyled_ruleset` in `meta.json`.
- [ ] A test shows that `restyle done` passes when a doc changes `don't` to `do not`.
- [ ] A new `context propose` scaffold and a new audit scaffold give no strict violations.
- [ ] `dummyindex context check --style` on a fixture repo scans `features/*/flows/*.md`, `playbooks/*.md`, `proposals/*/*.md` and `audits/**/*.md`. It skips `HOW_TO_USE.md`, `INDEX.md`, `naming.md` and `equipment/*.md`.
- [ ] The rendered `AGENTS.md` block, the managed `CLAUDE.md` block and the Codex guidance contain `ASD-STE100` and do not contain `caveman style`. The policy canary test asserts both.
- [ ] `restyle done` exits 1 and names the token when a fixture doc loses a `path:line` citation, a numeral or a `not`.
- [ ] After `restyle done`, the doc `mtime_ns` equals the snapshot value.
- [ ] `restyle begin` exits non-zero when an unfinished restyle run exists.
- [ ] `restyle stamp` writes `restyled_ruleset`. Then `restyle plan` prints `already restyled`.
- [ ] A test shows that `restyle stamp` leaves `features/INDEX.json`, `cache/doc-basis.json` and the reconcile anchor byte-identical.
- [ ] A test shows that `reseed` raises a word-ratchet entry and `update_ratchet` does not.
- [ ] A `state.json` from an old maintain run, without a `kind` field, loads as a maintain run.
- [ ] The generated-template test passes with no strict violations.
- [ ] A hygiene test asserts that `update/SKILL.md` names `context restyle` in a step after the verify step.
- [ ] `tests/test_repo_doc_style.py` passes, and each entry in `tests/data/repo-style-budget.txt` is 0.
- [ ] B1: A test writes the toolkit stash in a repo whose `.context/.gitignore` has no toolkit line. After the write, the file contains `/toolkit/`. `git check-ignore` does not match `.context/features/toolkit/spec.md`.
- [ ] B2: A test sends a terminal-scope request with `--allow-project-fallback`. Only a user-scope item matches. The result is `not_found` or `scope_not_proven`, and no user-scope file changes. A test with one item that is live and in the stash resolves it with `--kind`.
- [ ] B3: A test asserts the exact install argv sequence (`marketplace add`, then `install`, no `--marketplace`). The `partial_install` hint contains `--scope user`. A plugin `--preview` without `--scope` does not give `unsupported_scope`. A `toolkit_mutate` call without `--scope` still uses project scope.
- [ ] B4: A fixture INDEX.json with an `AMBIGUOUS` feature and an `auth_flow` feature lists both, and `skipped` is 0.
- [ ] B5: `settings.json` is a symlink outside the scope folder, and `toolkit list --json` exits 0. The test skips when the OS cannot make a symlink. A UTF-16 `.mcp.json` gives a `malformed_config` envelope, not a traceback.
- [ ] The full test suite passes.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `equip`
- `session-memory`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
