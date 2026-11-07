# Spec — Three-way language policy: ADHD-minimal human replies, English caveman persistent docs, concise-Chinese agent-to-agent prompts

## Intent

dummyindex-managed projects get one language policy with three audiences.

1. **Human-facing replies.** i-have-adhd shape at minimum verbosity. Caveman always-on chat is off by default.
2. **Persistent docs.** Every doc dummyindex creates uses English caveman style. This overrides caveman's own "persisted text uses plain prose" rule.
3. **Agent-to-agent text.** Orchestrator prompts to subagents use concise Chinese plus caveman rules. Code, commits, PRs, docs, and final reports stay English.

No token saving is claimed. Upstream caveman says savings are "small and noisy; never claim them". A measurement spec is authored; running it is a follow-up.

Extends the policy canary from proposal `repo-adoptions-ponytail-headroom` Item 2. Supersedes no proposal.

## Decisions

Decided under KISS/YAGNI. The user was away; none of these is open.

- **D1 Caveman chat default.** Write project-root `.caveman.json` as `{"defaultMode": "manual"}` when wiring the caveman default plugin. `manual` starts inactive; `/caveman` still works. `off` would block explicit `/caveman`.
- **D2 Never clobber.** Skip when `.caveman.json` or `.caveman/config.json` already exists, in any shape. Skip when `project_root` is the user home. Codex-only installs write nothing; caveman is a Claude plugin. `CAVEMAN_DEFAULT_MODE` env still wins; document it, no code.
- **D3 One carrier, no companion.** The three-way rule lives inside `ALWAYS_ON_OUTPUT_POLICY`. One short clause joins `ALWAYS_ON_TURN_REMINDER`. Both hosts and every skill inherit it. No companion doc and no per-skill pointer lines: the constant already reaches every skill.
- **D4 Agent-facing scope.** Chinese applies to Agent/Task `prompt` and SendMessage `message` bodies. Subagent handback reports stay English. Skill source files stay English.
- **D5 Language hook.** Widen the existing PreToolUse matcher to `Write|Edit|MultiEdit|Agent|Task|SendMessage`. The language branch runs first in `guard_doc_write._decide`. It ignores the doc-guard config switch. Warn only, via `hookSpecificOutput.additionalContext`. Never deny. Fail open.
- **D6 Language threshold.** Strip fenced code, inline code, URLs, and path-like tokens first. Return `None` below 200 characters after stripping. Warn when CJK chars / (CJK chars + Latin words) < 0.5. CJK means U+4E00–U+9FFF plus U+3400–U+4DBF. No config switch, no per-session memo.
- **D7 Style lint.** New `docbudget/style.py`. Rules: sentence over 20 words; filler phrase from a fixed list. Enforcement reuses the ratchet: per-file violation count in `.context/style-budget.txt`, unrecorded ceiling 0.
- **D8 Style scope = authored scope.** STYLE scans `_CONTEXT_GLOBS` minus `conventions/naming.md`. That equals the `is_durable_doc` set. Generated docs stay out: `docs.md`, `flows/*.md`, `HOW_TO_USE.md`, `INDEX.md`, `naming.md`. A rebuild rewrites them, so a ratchet would churn. Proposals, audits, session-memory, and `council/` notes stay out too.
- **D9 Missing ratchet = report only.** Without `.context/style-budget.txt`, `check --style` prints violations plus a seed hint and exits 0. User repos never go red on upgrade.
- **D10 One-time compression scope.** Compress the 4 authored conventions plus the `bootstrap` and `managed-doc-homes` feature docs: 10 files. Compress the HOW_TO_USE template. The other 40 features wait for a follow-up after the fleet merges. Seeding freezes their counts now.
- **D11 Templates.** Compress only `generate_how_to_use_md` prose; a unit test lints its output. Sync `.context/HOW_TO_USE.md` by writing the generator output. Never run `rebuild`.
- **D12 Reconcile guard.** One line in `dummyindex/skills/council/65-reconcile.md`: run `check --style` and fix flagged lines before `reconcile-stamp`.
- **D13 Envelopes.** `buildloop/envelopes.py` stays unchanged. Its free text is model-authored. The 8192-byte cap already counts UTF-8 bytes.
- **D14 Code comments.** New code carries no long comments. One-line docstrings and short inline notes only.

## Contracts

### Human-facing policy (`dummyindex/context/output/bootstrap.py`)

`ALWAYS_ON_OUTPUT_POLICY` states these rules self-contained:

- First line is the action or the result.
- Fewest steps. At most 5 items per group. End with one next action when work remains.
- No preamble, recap, pleasantries, tangents, or empty hedges.
- Prefer a list or table over prose.
- Keep technical and safety detail, identifiers, commands, and errors verbatim.
- Exceptions: "explain" or "walk me through" gets fuller prose. Destructive actions get a full-sentence confirmation. Real ambiguity gets one clarifying question.
- Caveman chat voice is not the reply style here.
- Subagent prompts and SendMessage bodies use concise Chinese with caveman rules. Code, commits, PRs, docs, and final reports use English. Payload stays verbatim.
- Docs written into the repo use English caveman style, 20 words or fewer per sentence. This overrides caveman's plain-prose rule for persisted text.

Kept from today: whole-session persistence, the unsure-means-applies tiebreaker, the user/safety yield, and the opt-out phrases. Every sentence of both constants passes `lint_text`.

### Caveman manual default (`dummyindex/context/default_plugins.py`)

- `ensure_caveman_manual(project_root) -> bool`. True only when it wrote the file.
- Called from `wire_default_plugins` for `caveman@caveman` when `_effective_enabled` is not `False`.
- Write errors land in `PluginWireResult.errors`; never raised. `enabled=False` writes nothing.

### Style lint (`dummyindex/context/domains/docbudget/style.py`)

- `lint_text(text) -> tuple[StyleViolation, ...]`, pure. `StyleViolation(line, rule, excerpt)`; `rule` is `long-sentence` or `filler`.
- Input normalization: strip a leading BOM; split with `splitlines()`. CRLF and LF give identical results.
- Skips fenced code, HTML comments, table rows, and headings. Each inline code span becomes one word before any rule runs.
- Strips `*` characters and `_` emphasis markers before splitting. So `**Bold.** Next` splits after `Bold.`.
- Units: each list item, and each sentence inside a paragraph. A sentence ends at `.`, `!`, or `?` followed by whitespace and an uppercase letter, or by end of unit.
- Filler match is case-insensitive and whole-word: `in summary`, `in conclusion`, `to summarize`, `it is important to note`, `it's worth noting`, `as mentioned`, `basically`, `simply`, `just`, `really`, `actually`, `let me`, `hope this helps`, `feel free`.
- `count_violations(path) -> int` reads UTF-8; an unreadable file counts 0.

### Language share (`dummyindex/context/domains/docguard/language.py`)

- `cjk_share(text) -> float | None` implements D6. Pure.

### Ratchet and CLI

- `BudgetGroup.STYLE`. `scan(root, STYLE)` maps `_CONTEXT_GLOBS` minus `naming.md` to violation counts. `check` and `update_ratchet` work unchanged.
- `dummyindex context check --style` prints `path:line: rule: excerpt` for each flagged file. rc 1 on growth or an unrecorded file over 0; D9 otherwise.
- `--update-ratchet` needs `--budget` or `--style`. It updates only the named groups. Alone it exits 2.

### Language guard (`dummyindex/cli/guard_doc_write.py`)

- Agent/Task: read `tool_input.prompt`. SendMessage: read `tool_input.message`. A missing or non-string field means silence.
- Low share prints one JSON line: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": ...}}`. No `permissionDecision`.
- Always rc 0. Write/Edit/MultiEdit behavior is unchanged.

## Acceptance

- [ ] `pytest -q` passes.
- [ ] A test asserts `lint_text` returns `()` for `ALWAYS_ON_OUTPUT_POLICY`, `ALWAYS_ON_TURN_REMINDER`, and `generate_how_to_use_md()`.
- [ ] A canary row pins "at most 5 items per group" in the constant and all three restatement regions.
- [ ] Repo `AGENTS.md` equals the `dummyindex context bootstrap --platform agents` output.
- [ ] Caveman tests: first call writes `{"defaultMode": "manual"}` and returns True. A second call returns False. An existing `.caveman.json` or `.caveman/config.json` stays byte-identical. `enabled=False` writes nothing.
- [ ] Style tests cover: 20 words pass, 21 fail; fenced code, comment, table, and heading skipped; inline code counts one word; `just` inside inline code not flagged; `justify` not flagged; CRLF+BOM equals LF.
- [ ] `cjk_share` tests cover: 199 stripped chars gives `None`; 0.5 gives no warning; 0.49 warns; a code-only prompt gives `None`.
- [ ] Guard tests, for each of Agent, Task, SendMessage: English text emits exactly one JSON line with `additionalContext` and no `permissionDecision`. Chinese text emits nothing. Malformed stdin emits nothing. rc is always 0.
- [ ] `tests/context/test_hooks.py` asserts matcher `Write|Edit|MultiEdit|Agent|Task|SendMessage`. Re-install over an old `Write|Edit|MultiEdit` entry leaves one entry.
- [ ] `check` flag tests: `--update-ratchet` alone exits 2. `--budget --update-ratchet` leaves `style-budget.txt` byte-identical. `--style --update-ratchet` leaves `doc-budget.txt` byte-identical. Missing style ratchet exits 0.
- [ ] A fixture test: one 21-word sentence added to a recorded doc makes `check --style` exit 1.
- [ ] On the repo: `dummyindex context check --style`, `--budget`, and `--refs` each exit 0.
- [ ] `.context/style-budget.txt` records 0 for each of the 10 compressed files.
- [ ] `.context/HOW_TO_USE.md` equals `generate_how_to_use_md()` output byte for byte.

## Risks

- **Fleet serialization.** `docs/COMMANDS.md`, `docs/guide/07-cli.md`, and `dummyindex/context/hooks.py` likely intersect sibling `member_files`. Merge this unit last.
- **Sibling merges.** Before merge, rebase and re-seed `style-budget.txt` on latest main. On a ratchet-file conflict, take main's version and rerun `--update-ratchet`. Never raise an entry by hand.
- **Closeout reconcile.** Council re-enrichment may write long sentences. D12 makes the reconcile procedure fix them before stamping.
- **Behavior-gate baseline.** `tests/eval/behavior_arms.py` imports the constant. Old two-arm results stop being comparable.
- **Matcher name.** Hook docs do not list `SendMessage`. If it never fires, the hook stays harmless. Older CLIs ignore unknown tool names.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `bootstrap`
- `behavior-gate`
- `managed-doc-homes`
- `install-surface`
- `cli-dispatch`
- `agent-instructions`
- `session-memory`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
