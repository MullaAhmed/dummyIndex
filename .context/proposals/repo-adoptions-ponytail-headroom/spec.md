# Spec — Repo adoptions R2: ponytail behavior-gate + rule-copy canary, headroom failure-miner re-eval

## Intent

Round 2 of the external-repo adoption survey. R1
(`.context/proposals/external-repo-adoptions/`, branch `external-repo-addition`,
commit `59f197c`, 2026-07-13) evaluated 10 sources. This round adds
`DietrichGebert/ponytail` — never surveyed — and **re-evaluates**
`headroomlabs-ai/headroom`, whose R1 row is 15 days and 50 upstream commits
stale.

The round is driven by a concrete defect found this session: the always-on
output policy in managed project guidance *named* the `i-have-adhd` skill
instead of stating its rules, and because that skill ships
`disable-model-invocation: true`, the ADHD half of the policy was inert in every
managed repo. Nothing detected it — not the test suite, not the doc-sync guard.
dummyindex can carry behavior text and verify the text is present, but has no
gate proving the text *produces* the behavior. Both sources in this round speak
directly to that gap.

## Sources evaluated

Both were shallow-cloned (`--depth 50`) into the session scratchpad on
2026-07-28. **Grounding is uneven and the table says which is which** — the
scratchpad has since been wiped, so upgrading a partial row means re-cloning.
The headroom row was re-cloned on 2026-07-29 at HEAD `1588f5e`
(committer date 2026-07-28 15:33:08 -0700) specifically to upgrade item 5's
grounding from filenames to contents. The ponytail row was likewise re-cloned
on 2026-07-29, at HEAD `16f2980` (committer date 2026-07-15 23:32:15 +0200),
specifically to upgrade items 1 and 3 from `behavior.yaml`-inference to
`behavior.js`/`arms/*.js` contents — this supersedes the 2026-07-28 pin for
the ponytail row. Item 4's two subsequent correction passes (2026-07-29 and
2026-07-30) both re-read this same `16f2980` clone rather than re-cloning
again; see the Risks section for why that is still safe to trust.

| Source | License | Grounding | Outcome |
|---|---|---|---|
| `DietrichGebert/ponytail` | MIT (© 2026 DietrichGebert, `LICENSE` read) | **contents read (2026-07-29, HEAD `16f2980`):** `scripts/check-rule-copies.js`, `benchmarks/behavior.yaml`, `benchmarks/robustness-audit.js`, `README.md`, `benchmarks/behavior.js`, `benchmarks/arms/baseline.js`, `benchmarks/arms/caveman.js`, `benchmarks/arms/ponytail.js`, `benchmarks/loc.js`, `benchmarks/correctness.js`, `opencode.json`, `gemini-extension.json`, `plugin.yaml`, `pi-extension/package.json`, `pi-extension/index.js`, `hooks/claude-codex-hooks.json`, `hooks/copilot-hooks.json`, `hooks/qoder-hooks.json`, `.qoder/rules/ponytail.md`, `.kiro/steering/ponytail.md`, `.windsurf/rules/ponytail.md`, `.cursor/rules/ponytail.mdc`, `.clinerules/ponytail.md`, `.agents/rules/ponytail.md`, `.github/copilot-instructions.md`, plus a same-day correction-pass addendum (same clone, same HEAD, after an audit found the first pass incomplete): `skills/ponytail*/SKILL.md` (6 files), root `commands/*.toml` (6 files), `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`, `.devin-plugin/plugin.json`, `.qoder-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `.github/plugin/plugin.json`, `.github/plugin/marketplace.json`, `.openclaw/skills/*/SKILL.md` (6 files), `.opencode/command/*.md` (6 files), `.opencode/plugins/ponytail.mjs`, `.opencode/plugins/ponytail-frontmatter.cjs`, `ponytail-mcp/index.js`, `ponytail-mcp/package.json`, `hooks/ponytail-statusline.sh`, `hooks/ponytail-statusline.ps1`; plus a second correction-pass addendum (2026-07-30, same clone, same HEAD, after audit round 2 found the first correction pass still incomplete): root `AGENTS.md` (ponytail's canonical rule source — the file the other 7 rule-file copies are byte-compared against), `hooks/ponytail-activate.js`, `hooks/ponytail-config.js`, `hooks/ponytail-instructions.js`, `hooks/ponytail-mode-tracker.js`, `hooks/ponytail-runtime.js`, `hooks/ponytail-subagent.js` (the 6 payload scripts the three hook JSONs invoke), root `package.json` (its `pi`/`main`/`exports` host-registration keys), root `__init__.py` (the Hermes plugin implementation `plugin.yaml` declares), `after-install.md`, `scripts/uninstall.js` — 22 host surfaces classified in total, all read in full (see Item 4 below for the grounded classification of every one; this table cell does not re-enumerate them all a second time) | ADOPT (behavior gate) / ADAPT (rule-copy canary, selftest-before-spend) / PILOT (host coverage) / DONE (loc+correctness, already ported) |
| `headroomlabs-ai/headroom` | Apache-2.0 (`LICENSE` read, `NOTICE` present) | **read:** `LICENSE`, `git log --since=2026-07-13` (50 commits). **contents read (2026-07-29, HEAD `1588f5e`):** `headroom/learn/scanner.py`, `loops.py`, `writer.py`, `base.py`, `_shared.py`, `registry.py`, `plugins/claude.py`, `plugins/opencode.py`, `analyzer.py`. **partially read:** `models.py` (`Recommendation` / `AnalysisResult` fields), `memory/traffic_learner.py` (`_patterns_to_recommendations`). **listing only:** `verbosity.py`, `fixtures.py`, `plugins/{codex,gemini,grok}.py`, `crates/headroom-parity/`. Re-eval of the R1 row | DONE (sentinels — shipped since R1) / PILOT (failure-miner, re-confirmed, now grounded in contents) / SKIP (rest) |

Consequence for the backlog: items 1–3 rest on file contents that were read and
quoted. **Item 5 now rests on file contents too** — `scanner.py`, `loops.py`,
`writer.py`, `base.py`, `_shared.py`, `registry.py`, and the `claude`/`opencode`
plugin readers were opened and cited (see Item 5 below). The rejection of
`headroom/learn/analyzer.py` is no longer carried forward on R1's word either —
it was opened and re-verified this round, and the verdict held (see Explicit
SKIPs). Only the deterministic scanner/loop-detector is in scope.

### Re-evaluation deltas against R1

Three R1 conclusions no longer hold. Recording them matters more than the new
rows, because two of them would otherwise cause duplicate work.

1. **headroom item 4 — managed-region sentinels (was ADAPT) is now DONE.**
   dummyindex shipped the own-a-region idiom: `dummyindex/context/domains/docguard/`
   (`classify.py`, `decision.py`, `migrate.py`), `dummyindex/cli/guard_doc_write.py`
   wired at `dummyindex/cli/__init__.py:136`, and the `BEGIN_MARKER`/`END_MARKER`
   pair with balanced-marker validation at
   `dummyindex/context/output/bootstrap.py:14-18`. No adoption work remains.
2. **headroom item 9 — deterministic failure-miner stays PILOT, now grounded in
   contents, not just filenames.**
   Upstream `headroom/learn/` has matured into a plugin architecture:
   `scanner.py` is now a backwards-compat re-export shim over
   `learn/plugins/{claude,codex,gemini}.py`, which implement the
   `ConversationScanner`/`LearnPlugin` ABCs declared in `base.py`. `loops.py`
   adds measured (not LLM-guessed) loop detection (`detect_loops`,
   `LoopPattern`), and `writer.py` writes marker-delimited sections into each
   host's own memory file (`CLAUDE.local.md`, `AGENTS.md`, `GEMINI.md`,
   `GROK.md`) through per-host `ContextWriter` subclasses. Full citations are
   in Item 5 below. R1's caution holds verbatim: `learn/analyzer.py` is still
   an LLM analyzer and is still rejected — only the deterministic
   scanner/loop-detector is in scope. That rejection was re-verified against
   this round's clone rather than carried on R1's word; the citations are in
   Explicit SKIPs.
3. **ponytail's measurement harness is already harvested — do not re-adopt.**
   Re-checked against the real `loc.js` and `correctness.js` this round; the
   `tests/eval/test_retrieval_eval.py:11` credit line — "What it does,
   mirroring ponytail's `loc.js` + `correctness.js`" — is accurate as far as it
   goes, but what was ported is the **design idiom**, not the JS itself: a
   measurement metric that always records and never blocks (ponytail's `loc`
   score, `benchmarks/loc.js:14`; dummyindex's MRR/hit-rate@3/mean
   tokens-to-answer, always printed per
   `tests/eval/test_retrieval_eval.py:158-163`) kept separate from a pass/fail
   gate (ponytail's `correct` score — a flat boolean→`{1,0}` map with no floor,
   `benchmarks/correctness.js:281-285`; dummyindex's
   `hit_rate_at_3 >= T_HIT and MRR >= T_MRR`, where the numeric floors are its
   own addition). Two things were
   **not** carried over, because dummyindex's eval is retrieval-quality, not
   code-generation: (a) `loc.js`'s actual line-counting algorithm — it
   *extracts* fenced blocks and counts their contents (falling back to the whole
   text when unfenced, `benchmarks/loc.js:6`), then strips `/* … */` block
   comments (`:9`) and `//`/`#`/`*` comment lines before counting what is left
   (`:13`) — has no analogue in a retrieval eval, there is no
   code to count; (b) `correctness.js`'s fenced-code extraction plus
   per-task execution harnesses (`benchmarks/correctness.js:20-27`,
   `:73-264` — three of the five `CHECKS` spawn a real subprocess: `email` →
   python `:125-126`, `debounce` → node `:170-171`, `csv` → python `:219-220`;
   `countdown` `:227-246` and `ratelimit` `:247-263` are regex/structure checks
   with no execution) likewise has no analogue — `test_retrieval_eval.py` gates on
   `query()`'s deterministic ranking, not on executing generated code. The
   `tests/eval/BASELINE.md` margin-below-baseline discipline for the gate
   floors is dummyindex's own addition; it is not a technique present in
   `correctness.js`, which is a flat pass/fail with no baseline margin. The
   DONE verdict stands — the parts of ponytail's harness that *do* map to a
   retrieval eval (record-then-gate separation) are already ported and
   credited; the parts that don't map (code counting, code execution) have
   nothing to port. R1 never listed ponytail, so this prior art was uncredited
   in the survey.

## Ranked backlog

| # | Item | Call | Seam | Effort |
|---|---|---|---|---|
| 1 | Behavior gate: prove managed guidance *produces* behavior, not just carries it | **ADOPT** | new behavior arm in `tests/eval/`, beside `test_retrieval_eval.py` | M |
| 2 | Rule-copy canary: invariant-phrase equality across restated guidance surfaces | **ADAPT** | `tests/cli/test_cli_doc_sync.py` | S |
| 3 | Selftest-before-spend: prove the grader at zero API cost before any paid run | **ADAPT** | same harness as item 1 | S |
| 4 | Host coverage gap list (22 surfaces classified this round: 2 covered, 7 partial, 9 gap, 4 out-of-scope — see Item 4) | **PILOT** | `dummyindex/installer/common.py` (host constants, `.agents/skills` copy, `_install_commands`) — `families.py` is satisfied only nominally: it enumerates the 8 *skill families*, not hosts, so the grounding correctly pivots to `common.py` | M |
| 5 | Deterministic failure-miner → session memory (re-confirmed from R1) | **PILOT** | session-memory feeder over host transcript stores | M |
| — | headroom managed-region sentinels · headroom LLM analyzer · headroom Rust/Python parity harness · headroom proxy + compressor stack · ponytail `loc.js`/`correctness.js` | **DONE / SKIP** | — | — |

### Item 1 — behavior gate (ADOPT)

Source: `benchmarks/behavior.yaml`, `benchmarks/behavior.js`,
`benchmarks/arms/baseline.js`, `benchmarks/arms/ponytail.js`.

**How the two-arm run is structured.** The two arms are promptfoo "prompts",
not separate scripts. `arms/baseline.js` (`arms/baseline.js:1-2`) is a one-line
control: it returns only the user's task, no system message. `arms/ponytail.js`
(`arms/ponytail.js:1-8`) reads the repo's own `skills/ponytail/SKILL.md` off
disk at eval time (`fs.readFileSync(path.join(__dirname, '..', '..', 'skills',
'ponytail', 'SKILL.md'), 'utf8')`, `arms/ponytail.js:4`) and sends it as the
system message ahead of the same task — so the literal file that ships to
users is the thing under test, not a paraphrase of it. `behavior.yaml` wires
one provider (`anthropic:messages:claude-opus-4-8`, `behavior.yaml:16-17`),
lists the two arms as `prompts` labeled `"baseline (no skill)"` and
`"ponytail"` (`behavior.yaml:19-23`), and defines 3 `tests`, each carrying a
`vars.probe` id (`hardware` / `explanation` / `onecheck`) and a `vars.task`
prompt (`behavior.yaml:31-40`) — e.g. the `hardware` probe's task asks for a
Python thermistor-read function, `onecheck`'s asks for a duration-string
parser. The header comment's reproduction command runs this as a 2-arm × 3-probe
grid, `--repeat 10` per cell (`behavior.yaml:5`).

**How the grader scores a response.** `defaultTest` attaches one `javascript`
assertion, `behavior.js`, under the metric name `behavior`
(`behavior.yaml:25-29`). `behavior.js`'s `module.exports(output, context)`
(`behavior.js:48-54`) reads `context.vars.probe` (`:49`) and dispatches to the
matching entry in `CHECKS` (`:50`); an unrecognized probe auto-passes with
`score: 1` (`:51`) — only the three named probes are actually gated. Each
`CHECKS` entry is a heuristic, not an LLM judge: `hardware`
(`behavior.js:20-26`) regex-tests the raw output for calibration/drift
vocabulary (`drift`, `per-unit`, `tare`, `trim`, `calibration offset/constant/
param/knob`, …); `explanation` (`behavior.js:29-36`) requires **both** a
fence-stripped prose word count `>= 45` (via `proseOf()`, `:13-15`) **and**
either a numbered/bulleted list — matched against the **raw** output, not the
stripped prose (`:32`) — or a causal word (`because`, `why`, `renamed`, …); `onecheck` (`behavior.js:39-45`) regexes for a runnable-check
construct (`assert`, `def test_`, `if __name__`, `unittest`, `pytest`,
`expect(`, `describe(`, `it(`). The exported result maps `pass` straight to
`score: 1`/`0` (`:52-53`), with the check's `reason` string carried through for
the promptfoo report.

**Pass/fail gates.** There is no separate numeric threshold layered on top —
the gate *is* the per-cell heuristic verdict: a cell passes iff its `CHECKS`
function returns `pass: true` for that (arm, probe) combination.

**How the delta is computed.** No script anywhere in ponytail *asserts* a
delta. `behavior.yaml:11-12`'s comment ("baseline ... should mostly FAIL these gates,
the ponytail arm should pass them. That delta is the point") states the intent,
but the arithmetic is left to promptfoo itself: because both arms run against
the same `defaultTest` assertion over the same 3 probes, promptfoo's own
per-prompt-label aggregation (surfaced via `npx promptfoo@latest view`) reports
each arm's pass rate across the `--repeat` runs side by side, labeled by the
`baseline (no skill)` / `ponytail` prompt labels above — a human (or a CI step)
reads the two rows and expects them to diverge. A dummyindex port of this idiom
would need to decide explicitly whether to keep that eyeballed-diff behavior or
add a script that asserts the delta numerically; ponytail itself does not
assert it. Two places do put arms side by side programmatically and are worth
naming so a later reader does not mistake them for a counter-example:
`robustness-audit.js:194-203` flags `p.pass < b.pass` as `<-- PONYTAIL
REGRESSION` and prints a "ponytail holes" section, and
`benchmarks/agentic/run.py:341` aggregates by `(task, arm, model)` and prints
baseline/ponytail/caveman rows in one table. Both **print**; neither computes an
arm-to-arm difference nor exits non-zero on one.

For dummyindex the subject under test is `ALWAYS_ON_OUTPUT_POLICY`
(`dummyindex/context/output/bootstrap.py:32-52`). Probes assert observable output
shape: outcome-or-next-action first, numbered multi-step work, specific
quantities over vague ones, one concrete closing action. A no-guidance arm should
fail those; a managed-guidance arm should pass.

### Item 2 — rule-copy canary (ADAPT)

Source: `scripts/check-rule-copies.js`.

ponytail keeps one canonical body (`AGENTS.md`) and byte-compares it against
seven per-host copies (`.cursor/rules/`, `.windsurf/rules/`, `.clinerules/`,
`.agents/rules/`, `.qoder/rules/`, `.github/copilot-instructions.md`,
`.kiro/steering/`), normalizing away host-specific frontmatter. Where byte
equality is impossible — its `SKILL.md` is longer than the compact copies — it
falls back to an `INVARIANTS` list asserting each load-bearing phrase survives
verbatim, with a stated upgrade path to generation if the canary ever misses a
real drift.

dummyindex has the same hazard and a weaker guard. `ALWAYS_ON_OUTPUT_POLICY` is
one Python constant shared by import
(`dummyindex/context/output/agents_md.py:18`), so the *rendered* Claude and Codex
blocks cannot drift. But three shipped docs **restate** the policy in English
prose — `docs/COMMANDS.md`, `docs/guide/07-cli.md`,
`dummyindex/skills/skill.md` — and `tests/cli/test_cli_doc_sync.py:122-138` only
asserts token *presence* (`assert not missing`). A restatement can contradict the
constant while every pinned token is still present. This session proved it:
fixing the constant required three hand edits that no test demanded.

The adaptation is invariant-phrase assertions tying those restatements to the
constant — not byte comparison, since the prose is deliberately different.

### Item 3 — selftest-before-spend (ADAPT)

Source: `benchmarks/robustness-audit.js:1-5` — re-checked against the file
directly this round; the citation holds verbatim. Lines 1-5 read: a comment
identifying this as an "issue #65 follow-up", stating each task "has a
known-good and a known-lazy-wrong reference so the instrument is verified
before any API spend", then the two invocation forms — `--selftest` ("no API:
prove every check is correct") and the unflagged paid run ("baseline vs
ponytail, gpt-5.4-mini, n=20"). `benchmarks/behavior.yaml:8-9` applies the same
discipline: the grader is proven by a separate test that needs no API key.

**What the selftest actually asserts.** Each entry in `TASKS` (defined at
`robustness-audit.js:35-118`, one object per task with `good` and `bad`
reference solutions as inline source strings) is checked twice when
`--selftest` is passed (`robustness-audit.js:168-178`): `checkPy(t.good, t)`
must evaluate to `true` and `checkPy(t.bad, t)` must evaluate to `false`
(`:171-172`); a task where the good reference fails or the lazy-wrong
reference accidentally passes prints as `XX` instead of `ok` (`:173`) and the
process exits non-zero (`:177`), so a broken instrument fails the selftest
before it is ever pointed at a paid API. `checkPy` (`robustness-audit.js:127-153`)
builds a small Python harness that embeds the candidate source, resolves the
target function by trying each name in `task.names` (`:131-134`), then runs
`task.cases` as `input -> expected` assertions inside that same subprocess
(`:142-146`) — mismatches, exceptions, and an unresolvable function name all
count as failure (`:141`, `:144-146`). This mirrors `correctness.js`'s spawn-and-assert
technique but generalizes it: one dynamic name/arity resolver instead of one
hand-written check per task. One grounding-precision note found in passing but
not a spec claim to correct: the file's own header comment says "12 tasks"
(`robustness-audit.js:2`) while `TASKS` actually holds 16 entries
(`robustness-audit.js:35-118`) — a drift in ponytail's own comment, not in
anything this spec asserted.

dummyindex's `tests/eval/` is deterministic today. Item 1 introduces the first
model-dependent gate, so this discipline should land with it, not after.

### Item 4 — host coverage gap list (PILOT)

**Correction pass 1, 2026-07-29, same clone (ponytail HEAD `16f2980`).** An
audit failed the first pass on two grounds: it was incomplete (12+ surfaces —
including two entire hosts, Devin CLI and OpenClaw, and a whole mechanism, the
MCP server — were never opened), and the incompleteness produced
under-claiming, because the three surfaces dummyindex most unambiguously
covers (`skills/`, root `commands/`, the statusline hook pair) were exactly
the ones left out. That pass opened and classified 21 host surfaces total,
against the same clone and HEAD as the original pass (the defects were
reasoning errors, not staleness, so no re-clone was needed).

**Correction pass 2, 2026-07-30, same clone and HEAD again.** A second audit
failed pass 1 on 7 further grounds: root `AGENTS.md` — ponytail's own
canonical rule source — was still unlisted and unclassified even though it is
the single surface dummyindex has the most existing reach into (it already
writes the same file, see its row below); the statusline
COVERED row's evidence pointed at the wrong installed value; the `commands/`
row was misclassified as covered when the spec's own rule makes it partial;
three PARTIAL rows overstated "every install" without naming the gate that
makes it conditional; two counts were arithmetically wrong; and one
parenthetical still carried a stale date. This pass adds the `AGENTS.md` row,
fixes the mislabeled/misworded rows, and recounts every number that changed.
22 host surfaces are now classified in total, all read in full, against the
same clone and HEAD as both prior passes (again reasoning/arithmetic errors,
not staleness). Classification is **covered** / **partial** / **gap** /
**out-of-scope**, matching the discipline of the Explicit SKIPs section. No
host is added here.

**Verdict rule.** *Covered* = dummyindex ships the identical mechanism (same
file shape, same integration point). *Partial* = dummyindex already reaches
the host today through a different, narrower channel than the one ponytail's
surface provides (most often the shared `AGENTS.md` block, mechanism 3
below) — real coverage exists, just not the specific always-on/hook layer
this surface adds. *Gap* = dummyindex has a comparable technique (skill
files, rule-file-style prose, per-host rendering) but hasn't pointed it at
this host yet. *Out-of-scope* = the surface uses a technique or distribution
domain (an LLM-gateway hook, a running MCP server, a marketplace packaging
manifest, an IDE chat-panel extension) that has no dummyindex analogue
anywhere, the same class of reasoning as this proposal's headroom SKIPs.

**What dummyindex's own host-reach actually is, grounded in code.**
`SUPPORTED_PLATFORMS = ("claude", "codex", "both")` (`dummyindex/installer/common.py:21`)
— dummyindex only ever writes for two first-class hosts, both through the
8-family enumeration (`_family_names()`, `dummyindex/installer/link/families.py:23-24`:
the main `dummyindex` family + the 7 `_SIBLING_SKILLS` labels). (Line numbers
below into `dummyindex/installer/common.py` cite the **working tree**, which
carries a concurrent, uncommitted insertion from another in-flight task
(`_TEST_ANCHOR_LINE_RE` and its docstring) — against the committed `HEAD` they
are off by −17. The citations below were checked against the working tree as
it stands now.)

1. **Claude Code** — `.claude/skills/<family>/SKILL.md` (`SKILL_REL`,
   `common.py:69`), `.claude/commands/*.md` (`_install_commands`,
   `common.py:231-264`, fed by `_COMMAND_FILES`/`COMMANDS_REL`, `common.py:84-85`),
   a `CLAUDE.md` registration block
   (`_register_claude_user_skill`, `dummyindex/installer/install/orchestrate.py:534-546`),
   four managed Claude Code hooks — `SessionStart`, `Stop`, `PreCompact`,
   `PreToolUse` (`_CLAUDE_HOOKS`, `dummyindex/context/hooks.py:207-211`;
   `CURRENT_CLAUDE_EVENTS`, `hooks.py:216`) — written into
   `.claude/settings.json`'s `hooks` key (`install()`, `hooks.py:402`), and a
   `statusLine` entry (`install_statusline`, `hooks.py:282`) whose installed
   value is `{"type": "command", "command": "dummyindex context statusline"}`
   (`_STATUSLINE_VALUE`, `hooks.py:247-251`) — the **Python CLI cold path**,
   not the shipped `statusline.sh`/`statusline.ps1` wrappers. Those wrappers
   ship as package data under `SCRIPT_DIR` (`dummyindex/cli/statusline.py:34`)
   and the module's own docstring names them the faster "hot path"
   (`statusline.py:3-6`), but no installer code wires them; see the
   statusline row below for the corrected covered/not-covered split.
2. **Codex / "agents"** (the public `--platform agents` alias for the internal
   `"codex"` token, `normalize_platform_arg`, `common.py:157-181`) —
   `.agents/skills/<family>/SKILL.md` (`CODEX_SKILL_REL`, `common.py:74`,
   aliased `AGENTS_SKILL_REL`, `common.py:80`), rendered with a
   `## Portable host compatibility` preamble
   (`_PORTABLE_HOST_PREAMBLE`, `common.py:111-138`; inserted by `render_skill`,
   `common.py:197-224`) whenever the target platform is `"codex"`. That
   preamble is dummyindex's own explicit claim, shipped inside the installed
   file itself, that "every host that discovers `.agents/skills`" — named
   examples: Cursor, Copilot CLI, OpenCode, Amp, Gemini CLI/Antigravity,
   Goose, Pi, Cline (`common.py:76-79`, `:122-125`) — can read this copy.
   **This is dummyindex's own assertion, not independently verified against
   any of those hosts' source** — every row below states explicitly whether a
   surface's host is on this named list.
3. A managed block in the active `AGENTS.md`/`AGENTS.override.md`
   (`CODEX_INSTRUCTION_PRECEDENCE`, `dummyindex/codex_guidance.py:21-24`) at
   project root (`bootstrap_project_agents_md`,
   `dummyindex/context/output/agents_md.py:112-131`, wired at
   `project_init.py:103,140`) and at user scope
   (`bootstrap_global_agents_md`, `agents_md.py:166-182`,
   wired from `_register_codex_user_skill`, `orchestrate.py:549-558`) — this
   is the "AGENTS.md universal-harness path" the task names: prose guidance
   text, not a skill or a hook. **This is gated, not unconditional**: both
   project-scope call sites sit behind `if use_codex:` (`project_init.py:101,138`),
   so an explicit `--platform claude` writes no `AGENTS.md`/`AGENTS.override.md`
   at all; project init itself only runs when the target `is_git_repo` and
   `--skill-only` was not passed (`orchestrate.py:479-488`). The default
   `platform="both"` includes Codex, so the gate is open on a plain install —
   every row below that says this channel reaches "every install" means every
   install that keeps this default (or picks `codex`/`agents`/`both`
   explicitly), not literally every invocation of the installer. **This
   channel's reach is broader than Codex alone**, and the first pass under-used
   that fact: per ponytail's own
   README, Qoder auto-loads root `AGENTS.md` as always-on context with zero
   setup (`README.md:193`); OpenCode "also auto-loads this repo's `AGENTS.md`,
   so the rules hold even without the plugin" (`README.md:178`); Amp
   (Sourcegraph) "reads `AGENTS.md` from the working directory and parent
   directories up to `$HOME`" (`README.md:267`); and GitHub Copilot CLI's
   documented fallback "reads `AGENTS.md` and `.github/copilot-instructions.md`
   in a project" when no plugin hooks are installed (`README.md:261`). Every
   row below that touches one of those hosts states this channel's coverage
   explicitly, rather than treating mechanism 3 as Codex-only.

No other host manifest, extension, or hook-registration mechanism exists in
dummyindex today: no OpenCode/Gemini/Hermes-style JSON manifest, no
non-Claude hook writer, no `GEMINI.md`/`.cursor`/`.windsurf`/`.clinerules`/
`.qoder`/`.kiro` writer of any kind, and no marketplace-plugin packaging
manifest of any kind (see the plugin-manifest row below).

**Supporting files opened this pass but not given their own row.** Each was
read in full; none changes a verdict or adds a new surface, so they are
folded into the row of the mechanism they implement or package rather than
double-counted: the 6 payload scripts the three hook JSONs all invoke —
`hooks/ponytail-activate.js`, `ponytail-config.js`, `ponytail-instructions.js`,
`ponytail-mode-tracker.js`, `ponytail-runtime.js`, `ponytail-subagent.js` (the
`claude-codex-hooks.json` rows below wire `ponytail-activate.js`,
`ponytail-subagent.js`, `ponytail-mode-tracker.js`; `copilot-hooks.json` wires
`ponytail-activate.js` + `ponytail-mode-tracker.js`; `qoder-hooks.json` wires
`ponytail-mode-tracker.js` + `ponytail-subagent.js`; the rest are shared
`require()`d helpers) — are the shared implementation behind those three
hook-JSON rows, not a fourth surface. Root `package.json`'s `"pi":
{"extensions": ["./pi-extension/index.js"], "skills": ["./skills"]}` key and
its `"main"`/`"exports"` pointer at `./.opencode/plugins/ponytail.mjs` are the
npm packaging path for the `pi-extension/` row and the `opencode.json` row
below respectively — not new surfaces. Root `__init__.py` (the actual Hermes
plugin implementation `plugin.yaml` declares, written in Python) and
`after-install.md` (Hermes's post-install command reference) are read and
scoped out under the same reasoning as the `plugin.yaml` row below: the
domain (a Hermes LLM-gateway plugin) has no dummyindex analogue regardless of
the implementation language.

**Classification.**

| ponytail surface | What it declares (read in full) | Verdict | Reason / what's needed |
|---|---|---|---|
| root `AGENTS.md` — ponytail's canonical rule source | A 32-line always-on ruleset that `scripts/check-rule-copies.js` treats as ground truth: `const agents = read('AGENTS.md')` (`check-rule-copies.js:19`), then byte-compared (frontmatter stripped) against the 7 per-host rule-file copies (`check-rule-copies.js:20` onward). README documents 8 hosts that auto-load this exact file with zero setup — OpenCode (`README.md:178`), Qoder (`:193`), Swival (`:229`), Copilot CLI (`:261`), the VS Code Codex extension (`:263`), JetBrains Junie (`:265`), Amp (`:267`), Jules (`:269`) — plus Gemini CLI/Antigravity, which reaches it indirectly via `gemini-extension.json`'s `"contextFileName": "AGENTS.md"` redirect (`gemini-extension.json:5`) rather than reading it natively. | **PARTIAL** | dummyindex writes into the identical root-level target — `AGENTS.md`, or `AGENTS.override.md` when Codex's own precedence picks it (`CODEX_INSTRUCTION_PRECEDENCE`, `codex_guidance.py:21-24`) — via `bootstrap_project_agents_md` (`agents_md.py:112-131`, wired at `project_init.py:103,140`, gated behind `if use_codex:` at `project_init.py:101,138` — see the mechanism-3 gate note above; not written under an explicit `--platform claude`). Same filename, same project-root integration point, same "many hosts auto-load this with zero setup" purpose the 8-host list above documents. But it is not the identical mechanism the spec's own COVERED rule requires: dummyindex writes a managed **block** merged into whatever the file already contains, never full-file ownership the way ponytail's `AGENTS.md` is (the whole file *is* the ruleset, which is what makes it usable as `check-rule-copies.js`'s comparison ground truth) — the same class of vehicle/format narrowing that keeps the `commands/*.toml` row below at partial rather than covered. The content also differs entirely: dummyindex's block is its own context-engine guidance, not ponytail's ruleset, so there is no text to port. And dummyindex's `AGENTS.md` plays no canonical-canary role — nothing else in dummyindex byte-compares against it; that gap is already Item 2 (rule-copy canary, ADAPT) above, not reopened here as a second one. |
| `skills/ponytail*/SKILL.md` (6 files: `ponytail`, `-audit`, `-debt`, `-gain`, `-help`, `-review`) | Each `skills/<name>/SKILL.md` is YAML frontmatter (`name`, `description`, `license: MIT`, optional `argument-hint`) plus a Markdown body — the open Agent Skills convention. Auto-discovered by Claude Code's plugin loader (no explicit `skills` field needed in `.claude-plugin/plugin.json`) and explicitly declared via `"skills": "./skills/"` in `.codex-plugin/plugin.json`, `.qoder-plugin/plugin.json`, and `.github/plugin/plugin.json`. | **COVERED** | Mechanism-identical to dummyindex's own skill install: `.claude/skills/<family>/SKILL.md` (`SKILL_REL`, `common.py:69`) and `.agents/skills/<family>/SKILL.md` (`CODEX_SKILL_REL`, `common.py:74`) — same filename, same frontmatter-plus-Markdown shape, same per-family directory convention. dummyindex ships 8 families (main + 7 `_SIBLING_SKILLS`, `families.py:23-24`) the same way ponytail ships 6. Nothing to build; recorded to show the seam already exists at comparable scale. |
| root `commands/*.toml` (6 files) | Flat `description`/`prompt` TOML pairs. Auto-discovered by Claude Code's plugin loader from a plugin-bundled `commands/` directory (no manifest key needed for Claude). Of the three plugin manifests, only `.github/plugin/plugin.json` (Copilot CLI's form) names `"commands": "commands/"` explicitly; `.claude-plugin/plugin.json` declares no `commands` key at all, and `.codex-plugin/plugin.json` declares only `"skills": "./skills/"` — no `commands` key either. Per `README.md:296`, Codex exposes these commands as **skills**, invoked with `@` (`@ponytail-review`), through that `skills/` manifest key — not through a `commands/` one. | **PARTIAL** | Same installation *idiom* as dummyindex's own — "drop files into a `commands/` directory the host auto-discovers as slash commands" — but not the identical mechanism the spec's own COVERED rule requires (same file shape, same integration point): `.toml` ≠ dummyindex's Markdown `tokens.md`, and ponytail's vehicle is a plugin-bundled `commands/` directory referenced from a plugin manifest, never a direct write into `<base>/.claude/commands/*.md` the way `_install_commands` performs it (`common.py:231-264`, fed by `_COMMAND_FILES`/`COMMANDS_REL`, `common.py:84-85`). Format (TOML vs. Markdown) and count (6 vs. 1) are a further content difference on top of that vehicle gap. Same class of downgrade as the Claude Code half of `hooks/claude-codex-hooks.json` below (identical schema, different file/vehicle → partial, not covered). |
| `hooks/ponytail-statusline.{sh,ps1}` | A Bash + PowerShell pair that reads a state flag (`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/.ponytail-active`) and prints a short ANSI-colored `[PONYTAIL]`/`[PONYTAIL:MODE]` badge. Not written by the plugin directly: `hooks/ponytail-activate.js`'s `SessionStart` hook detects a missing `statusLine` and emits a one-time nudge (`ponytail-activate.js:44-89`) containing the exact `"statusLine": {"type": "command", "command": ...}` snippet pointing at the shell/PowerShell script; a user has to accept it. `scripts/uninstall.js` (`:12,35`) removes that entry later only if it still points at ponytail's own script, leaving a user's own statusline untouched (`README.md:283`). | **COVERED** | Re-judged: COVERED survives, but only at the `statusLine`-key mechanism level, not at the "identical script pair" level the first-pass row claimed. dummyindex's `install_statusline` (`hooks.py:282`) writes the same native integration point — a `{"type": "command", "command": ...}` entry under `.claude/settings.json`'s `statusLine` key, write-if-absent and never clobbering an existing value (mirroring ponytail's own "a statusline you set up yourself is left untouched" discipline, `README.md:283`). What the first-pass row got backwards: the value actually installed is `_STATUSLINE_VALUE = {"type": "command", "command": "dummyindex context statusline"}` (`hooks.py:247-251`) — the **Python CLI cold path** (`dummyindex/cli/statusline.py:3-6` names it exactly that: "the cold-path fallback... the per-prompt hot path is a shipped shell/PowerShell wrapper... under `SCRIPT_DIR`", `statusline.py:34`) — not the shipped `statusline.sh`/`statusline.ps1` wrappers. Those wrappers ship as package data (exported via `pyproject`'s `package-data`) but no installer code references them anywhere (`grep -rn statusline.sh dummyindex/**/*.py` finds only that one docstring). So the mechanism (settings key, JSON shape, non-destructive write) is genuinely shared; the vehicle is not — ponytail's nudge, once accepted, invokes its shell pair, dummyindex's direct write invokes a Python subprocess, and dummyindex's own faster shell path sits unwired. |
| `opencode.json` (+ `.opencode/command/*.md` ×6, `.opencode/plugins/ponytail.mjs`, `.opencode/plugins/ponytail-frontmatter.cjs`) | Registers an OpenCode **plugin**: `{"plugin": ["./.opencode/plugins/ponytail.mjs"]}` (also installable as `@dietrichgebert/ponytail` from npm). `ponytail.mjs` injects the ruleset into every chat's system prompt at the active intensity and persists `/ponytail` mode switches; `.opencode/command/*.md` are OpenCode's own slash-command format, parsed via the sibling `ponytail-frontmatter.cjs` helper. | **PARTIAL** | OpenCode is on the `.agents/skills` host list (skill claimed reachable) **and**, per ponytail's own README, "OpenCode also auto-loads this repo's `AGENTS.md`, so the rules hold even without the plugin" (`README.md:178`) — dummyindex already writes that exact file (or `AGENTS.override.md`) every install that reaches this channel (the `if use_codex:` gate the `AGENTS.md` row and mechanism 3 above state — not under an explicit `--platform claude`; `agents_md.py:112-131`). So always-on guidance genuinely reaches OpenCode today through the shared `AGENTS.md` channel; the residual gap is narrower than "dummyindex's reach is an *invokable* skill, never an unconditional injection" claimed: only the runtime mode-switcher/every-turn-injection layer and the `/ponytail*` native commands have no analogue. Needed: an OpenCode plugin + command files, if the mode-switcher UX is wanted — not a bare content gap. |
| `gemini-extension.json` | `{"name": "ponytail", "version": "4.8.4", "description": "...", "contextFileName": "AGENTS.md"}` — a Gemini CLI extension manifest whose `contextFileName` field **redirects** Gemini's default context file from `GEMINI.md` to the shared `AGENTS.md`. | **GAP** | dummyindex already writes the `AGENTS.md` content Gemini would read once redirected (`agents_md.py:112-131`), but ships no extension manifest and no `GEMINI.md`. Absent that manifest, a real Gemini CLI install reads its default `GEMINI.md` — which dummyindex never writes — so the guidance dummyindex already produces is silently unreachable for Gemini CLI specifically. Needed: a `gemini-extension.json` (or a `GEMINI.md` writer). |
| `plugin.yaml` | A "Hermes Agent" plugin manifest: `provides_hooks: [pre_llm_call, pre_gateway_dispatch]`, plus `provides_commands`/`provides_skills` lists (install: `hermes plugins install ... --enable`, injecting the active mode "before each LLM turn"). | **OUT-OF-SCOPE** | Hermes Agent is not named anywhere in dummyindex — not in `SUPPORTED_PLATFORMS`, not on the `.agents/skills` host list, not in any doc. Its hook points (`pre_llm_call`, `pre_gateway_dispatch`) are LLM-**gateway**-level interception, a different technique from dummyindex's host-session-lifecycle hooks (`SessionStart`/`Stop`/`PreCompact`/`PreToolUse`, `hooks.py:207-211`) — there is no gateway layer in dummyindex to hook into. Same class of reasoning as headroom's proxy+compressor SKIP: not a to-do against a stated ambition, a new domain. |
| `pi-extension/` (`package.json` + `index.js`) | A Pi CLI extension: registers `/ponytail*` slash commands and installs `pi.on("before_agent_start", ...)` (`index.js:204-209`). The handler is **mode-gated** — it returns immediately when `currentMode` is falsy or `"off"` (`:205`) — and, when active, **appends** `getPonytailInstructions(currentMode)` after the host's existing system prompt rather than prepending (`base = event?.systemPrompt ? … : ""`, then `${base}${getPonytailInstructions(currentMode)}`, `:208-209`), so the injected text is the mode-filtered ruleset for whichever level is active, not a fixed ruleset. | **GAP** | Pi is on the `.agents/skills` host list (skill claimed reachable as an invocable skill), but nothing in dummyindex performs Pi's mode-gated, append-on-activation system-prompt injection — the gap is that always-on (mode-dependent) hook, not an unconditional prepend to every prompt as an earlier draft of this row mis-described it. Needed: a Pi extension hooking `before_agent_start`, gated the same way dummyindex would gate its own equivalent. |
| `hooks/claude-codex-hooks.json` (Claude Code half) | Real Claude Code hook JSON — `SessionStart` (`matcher: "startup\|resume\|clear\|compact"`), `SubagentStart`, `UserPromptSubmit` (neither of the latter two carries a `matcher`), each a `{"hooks": [{"type": "command", "command", "commandWindows", "timeout", "statusMessage"}]}` entry. This file is **not** `.claude/settings.json` — it is a plugin-bundled hooks file referenced by `.claude-plugin/plugin.json`'s `"hooks": "./hooks/claude-codex-hooks.json"` key (identically by `.codex-plugin/plugin.json`), loaded by Claude Code's plugin system when the ponytail plugin is installed. | **PARTIAL** | dummyindex writes into the same JSON **schema** (`{matcher, hooks: [{type, command, …}]}`) but into a different **file and delivery vehicle**: `.claude/settings.json`'s own `hooks` key (`install()`, `hooks.py:402`), never a plugin-bundled file referenced from a `plugin.json` manifest — dummyindex has no `.claude-plugin/plugin.json` of its own (see the plugin-manifest row below). Event overlap is 1 of 3: dummyindex installs `SessionStart` (`_CLAUDE_HOOKS`, `hooks.py:207-211`; `CURRENT_CLAUDE_EVENTS`, `hooks.py:216`) alongside `Stop`/`PreCompact`/`PreToolUse` — `SubagentStart` and `UserPromptSubmit` have no dummyindex analogue at all. Mechanism-level "covered" (same schema) is defensible; "writes into this exact schema and file" is not — downgraded from covered to partial. |
| `hooks/claude-codex-hooks.json` (Codex half, per the filename and `.codex-plugin/plugin.json`) | The same file is named for Codex too: `.codex-plugin/plugin.json` declares `"hooks": "./hooks/claude-codex-hooks.json"` — identical to the Claude manifest, so the Codex-side vehicle is a plugin manifest reusing the identical Claude-shaped hook JSON, not a separate Codex hook schema. | **GAP** | Resolved, not unconfirmed: dummyindex's Codex integration deliberately ships zero hooks. `.context/features/install-surface/plan.md:100` says so directly — "Codex-only remains free of Claude settings and hooks" — but that generated doc itself cites `dummyindex/installer/install.py:439-534`, a path that no longer exists post-split (the installer was later split into `dummyindex/installer/install/{orchestrate,project_init}.py`); the plan doc is stale scaffolding, not re-verified evidence on its own. The conclusion is independently true in the current code: `project_init.py`'s `_auto_init_project` only ever calls `_install_pkg._install_project_hooks` inside `if use_claude:` blocks (`project_init.py:110-111,148-149`), never under `use_codex`, so dummyindex's only Codex-side mechanisms remain the `.agents/skills` copy (mechanism 2) and the `AGENTS.md` block (mechanism 3). A known, deliberate absence, confirmed against live code — not leaned on from the stale doc alone. |
| `hooks/copilot-hooks.json` | GitHub Copilot CLI hook schema: `sessionStart`/`userPromptSubmitted`, each `{"type": "command", "bash", "powershell", "timeoutSec"}`. Referenced from `.github/plugin/plugin.json`'s `"hooks": "hooks/copilot-hooks.json"`. | **PARTIAL** | Copilot CLI is on the `.agents/skills` host list (skill claimed reachable) **and** has a documented two-file fallback: "GitHub Copilot CLI fallback (instruction-only mode): it reads `AGENTS.md` and `.github/copilot-instructions.md` in a project" (`README.md:261`). dummyindex writes only the first half of that fallback, and only for installs that reach the `AGENTS.md` channel (the `if use_codex:` gate stated in the `AGENTS.md` row above — not under an explicit `--platform claude`); `.github/copilot-instructions.md` itself is never written by dummyindex at all, so half of Copilot CLI's own documented fallback is a real, un-booked gap, not full reach. So Copilot CLI — like Qoder/OpenCode below — has partial always-on reach today via the `AGENTS.md` half of the shared channel; the residual gap is two things, not one: the hooks-driven mode-switching plugin tier, and the missing `.github/copilot-instructions.md` half of the fallback. |
| `.cursor/rules/ponytail.mdc` | Byte-identical ruleset body (confirmed by direct read against the other 6 copies) with Cursor-specific frontmatter (`description`, `globs`, `alwaysApply: true`) stripped by `check-rule-copies.js`'s `stripFrontmatter`. | **GAP** | Cursor is on the `.agents/skills` host list (skill claimed reachable as an invocable skill), but `.cursor/rules/*.mdc` with `alwaysApply: true` is Cursor's own always-on project-rule convention — a different, unconditional mechanism dummyindex does not write. |
| `.windsurf/rules/ponytail.md` | Same byte-identical body, no frontmatter. | **GAP** | Windsurf is **not** on the `.agents/skills` host list, and README names no `AGENTS.md`-style fallback for it — no partial coverage at all. |
| `.clinerules/ponytail.md` | Same byte-identical body. | **GAP** | Cline is on the `.agents/skills` host list (skill claimed reachable), but `.clinerules/` is Cline's own always-on rule-file convention, unwritten by dummyindex. |
| `.agents/rules/ponytail.md` | Same byte-identical body, under a `.agents/rules/` sibling of `.agents/skills/`. | **GAP** | dummyindex writes to `.agents/skills/` (`skills_root_rel("codex")`, `common.py:193-194`) but never to `.agents/rules/` — a directory it does not currently create. **Flagged as the cheapest of these gaps**: `.agents/` is already a directory dummyindex owns and writes into every install; a rules file there would reuse the already-written `AGENTS.md` body with no new host integration to build. Not fixed here per the task's scope. |
| `.qoder/rules/ponytail.md` | Same byte-identical body, with Qoder-specific frontmatter stripped. | **PARTIAL** | Qoder auto-loads root `AGENTS.md` as always-on context with zero setup (`README.md:193`) — dummyindex writes a managed block into project-root `AGENTS.md` (or `AGENTS.override.md`) every install that reaches this channel (the `if use_codex:` gate stated in the `AGENTS.md` row above; `project_init.py:103,140` → `bootstrap_project_agents_md`, `agents_md.py:112-131`). So this content already reaches Qoder through that shared channel; it is not "no partial coverage exists, not even claimed skill discovery" as the first pass asserted. The residual gap is the dedicated `.qoder/rules/` copy (a Qoder-native location dummyindex does not write) and Qoder's separate Skill-system reach via `.qoder-plugin/plugin.json`'s `skills: "./skills/"` (see the plugin-manifest row) — that skill-system claim is Qoder's own, not independently verified, since Qoder is not on dummyindex's own named host list. |
| `hooks/qoder-hooks.json` | A template (its own `_comment` says "copy the 'hooks' object into your `.qoder/settings.json`"): `UserPromptSubmit` + `PreToolUse` (matcher `task\|Task`) entries. | **PARTIAL** | Same `AGENTS.md`-fallback logic as the `.qoder/rules/` row above — Qoder already gets always-on content through the shared `AGENTS.md` channel dummyindex writes. The plugin-tier automatic mode activation + subagent injection this hooks file adds is the real residual gap, not "no partial coverage exists at all." |
| `.kiro/steering/ponytail.md` | Same byte-identical body, with Kiro-specific frontmatter (`title`, `inclusion: always`) stripped by `check-rule-copies.js`'s `stripFrontmatter`. | **GAP** | Kiro is not on the host list, and README's Kiro section (`README.md:259`) names no `AGENTS.md` fallback for it either — no partial coverage. |
| `.github/copilot-instructions.md` | Same byte-identical body, no frontmatter. | **OUT-OF-SCOPE** | Per `README.md:257`, this convention's primary targets are "Cursor, Windsurf, Cline, GitHub Copilot **Chat** (the VS Code, JetBrains, and Visual Studio editor extension, not the standalone Copilot CLI…), Aider, Kiro, Zed, CodeWhale, Swival, Qoder" — an instruction-only IDE-extension editor class dummyindex has never served (`SUPPORTED_PLATFORMS` and the `.agents/skills` scanners target agent CLIs/skill hosts, never chat-panel editor extensions like Copilot Chat, Aider, or Zed). Moved from gap to out-of-scope: a domain dummyindex has never entered, not an unmet promise. *(The file is also one of Copilot CLI's two fallback-read paths, `README.md:261`; that angle is booked as a residual gap in the `hooks/copilot-hooks.json` row above, not glossed over — dummyindex writes the `AGENTS.md` half of the fallback but never this file. This row's own verdict is about the separate, broader Copilot-Chat/Aider/Zed instruction-only-editor convention, which is genuinely out-of-scope.)* |
| `.openclaw/skills/*/SKILL.md` (6 files) | Generated from the canonical `skills/` via `scripts/build-openclaw-skills.js` (`README.md:307`); installable from ClawHub (`clawhub install ponytail`) or by copying into `~/.openclaw/skills/` (`README.md:241-247`). | **GAP** | OpenClaw is not named anywhere in dummyindex — not in `SUPPORTED_PLATFORMS`, not on the `.agents/skills` host list. But the underlying technique — rendering a per-host copy of the SKILL.md body into a host-specific directory — is exactly what dummyindex already does for Codex (`.agents/skills/<family>/SKILL.md` with a host-specific preamble, `common.py:74`, `:111-138`). A third rendered copy for a third host reuses an existing seam; a new-host gap, not a new-technique one. |
| Plugin marketplace manifests — `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`, `.devin-plugin/plugin.json`, `.qoder-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `.github/plugin/plugin.json`, `.github/plugin/marketplace.json` (8 files, 6 host-facing conventions: Claude, Codex, Devin, Qoder, generic-agents, Copilot CLI) | Packaging manifests: Claude Code Plugin Marketplace listing (`plugin.json` + its own `marketplace.json`); Codex plugin manifest (`hooks`/`skills`/`capabilities: ["Instructions", "Lifecycle hooks"]`); Devin's is bare identity metadata only (no `hooks`/`skills`/`rules` fields at all); Qoder's declares `skills`/`rules`/`hooks`; a generic agents-marketplace listing with an install `policy`; Copilot CLI's plugin (`commands`/`skills`/`hooks`) plus its own separate `marketplace.json` twin. | **OUT-OF-SCOPE** | Not "no dummyindex analogue anywhere" in the pure sense the other three OUT-OF-SCOPE rows use — dummyindex does have marketplace-consumer machinery: `dummyindex/context/domains/equip/plugins/marketplace.py` parses a fetched `.claude-plugin/marketplace.json` into `SeedMarketplace`-shaped frozen dataclasses (`CATALOG_PATH = ".claude-plugin/marketplace.json"`, `plugins/sources.py:21`), and `equip install <plugin>@<marketplace>`, `add_marketplace`, and `wire_default_plugins` all operate on that schema. The honest framing: dummyindex is a marketplace **consumer, never a producer** — it reads other repos' `.claude-plugin/marketplace.json` to install their plugins, but is never itself distributed as a listed plugin, so it has no reason to author any of these 8 manifests for itself. That is still a packaging/distribution-channel gap, not a host-reach one: the skill and command *content* these manifests point at is already covered by the `skills/` and `commands/` rows above, and the Claude/Codex hook pointer inside `.codex-plugin/plugin.json` is covered by the `hooks/claude-codex-hooks.json` (Codex half) row. Splitting this into 8 per-file or 6 per-convention rows would misrepresent one product-level packaging decision (never being a listed plugin) as several separate host gaps. |
| `ponytail-mcp/` (`index.js`, `package.json`) | A Model Context Protocol server (`@modelcontextprotocol/sdk`) serving the ruleset over stdio as both a `ponytail` prompt and a `ponytail_instructions` tool — explicitly "the clean option for hosts whose only injection point is the prompt menu" (`index.js:1-5`). | **OUT-OF-SCOPE** | dummyindex has no running-server component of any kind — every mechanism it has (skill files, command files, hooks, `AGENTS.md` blocks, statusline wrappers) is a static file written by a one-shot CLI install, never a long-lived process a host connects to over stdio/HTTP. Standing up and maintaining an MCP server is a different technical domain — same class of reasoning as headroom's proxy+compressor SKIP. |

**Net finding (recounted this pass; every number below states rows or files
explicitly, never mixes the two).** 22 **rows** are classified in total: 9
upgraded from listing-only to contents-read in the first correction pass, 13
opened as their own classified row for the first time (12 in the first
correction pass, plus root `AGENTS.md` newly rowed in this second pass —
9 + 13 = 22). By verdict, in **rows**: 2 covered, 7 partial, 9 gap, 4
out-of-scope (2 + 7 + 9 + 4 = 22).

- **Covered — 2 rows, 8 files.** `skills/ponytail*/SKILL.md` (6 files) and
  `hooks/ponytail-statusline.{sh,ps1}` (2 files). Root `commands/*.toml` moved
  out of this bucket this pass (see its row above): 6 files, now partial.
- **Partial — 7 rows, 20 files.** Root `AGENTS.md` (1), root `commands/*.toml`
  (6, moved in from covered this pass), the `opencode.json` cluster (9:
  `opencode.json` + 6 `.opencode/command/*.md` + 2 plugin `.mjs`/`.cjs`
  files), `hooks/copilot-hooks.json` (1), `.qoder/rules/ponytail.md` (1),
  `hooks/qoder-hooks.json` (1), and the Claude Code half of
  `hooks/claude-codex-hooks.json` (1). By **row** (not file) count, the
  reasoning splits three ways: 5 of the 7 rows (`AGENTS.md`, `opencode.json`,
  `hooks/copilot-hooks.json`, `.qoder/rules/`, `hooks/qoder-hooks.json`) rest
  on the shared `AGENTS.md`-channel argument and its `if use_codex:` gate
  (stated once in the `AGENTS.md` row and cross-referenced from the other
  four); 1 row (the Claude Code half of `hooks/claude-codex-hooks.json`)
  rests on an identical hook *schema* living in a different file/vehicle, not
  the `AGENTS.md` channel; 1 row (`commands/*.toml`) rests on a narrower
  packaging vehicle (plugin-bundled directory vs. a direct file write),
  unrelated to either argument.
- **Gap — 9 rows, 15 files.** Against a host or technique dummyindex already
  claims some reach into: `gemini-extension.json` (1), `pi-extension/`
  (2: `package.json` + `index.js`), the Codex half of
  `hooks/claude-codex-hooks.json` (1 file — the *same physical file* already
  counted once in the partial bucket above, split by hook-event ownership,
  not by a second copy on disk), `.cursor/rules/` (1), `.windsurf/rules/` (1),
  `.clinerules/` (1), `.agents/rules/` (1), `.kiro/steering/` (1), and
  `.openclaw/skills/*/SKILL.md` (6).
- **Out-of-scope — 4 rows, 12 files** (corrected this pass from a prior "9" —
  the plugin-marketplace cluster is 8 files, not 7): Hermes' `plugin.yaml` (1
  file; `__init__.py` and `after-install.md` were also read and confirmed to
  implement/document this same Hermes surface, not counted as separate
  files), the Copilot-Chat/Aider/Zed side of `.github/copilot-instructions.md`
  (1), the plugin-marketplace-manifest cluster (8:
  `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
  `.codex-plugin/plugin.json`, `.devin-plugin/plugin.json`,
  `.qoder-plugin/plugin.json`, `.agents/plugins/marketplace.json`,
  `.github/plugin/plugin.json`, `.github/plugin/marketplace.json`), and
  `ponytail-mcp/` (2: `index.js` + `package.json`). 1 + 1 + 8 + 2 = 12.

Summed naively across all four buckets' file-citation counts: 8 + 20 + 15 +
12 = 55; net of the one file (`hooks/claude-codex-hooks.json`) cited in two
rows by event-ownership split rather than physically duplicated, 54 distinct
files on disk are cited across the 22 rows. No host platform is added by this
proposal; every entry above
is a gap or scope statement, not a task.

### Item 5 — deterministic failure-miner (PILOT, carried from R1)

Unchanged in intent from R1 item 9. Re-grounded against a fresh clone (HEAD
`1588f5e`, committer date 2026-07-28, read 2026-07-29 — this supersedes the
2026-07-28 pin note above for this row only; ponytail's own rows are pinned
separately, to 2026-07-29 at HEAD `16f2980`, per the Sources table and the
Risks section below). Mine host transcript stores for repeated tool-error and loop
signatures and feed `.context/session-memory/`. Deterministic scanner only;
`learn/analyzer.py` was opened and re-verified this round (see Explicit SKIPs
below) — it is a digest-and-parse wrapper around a hosted-API or
CLI-subprocess model call with no deterministic analysis path of its own —
and stays out of scope.

**What the files actually do**, read start to finish:

- `headroom/learn/scanner.py` is no longer a scanner implementation — it is a
  backwards-compatibility re-export shim (`scanner.py:19-26`) aliasing
  `ClaudeCodeScanner` / `CodexScanner` / `GeminiScanner` to classes that moved
  to `headroom/learn/plugins/{claude,codex,gemini}.py`. The real scan contract
  is the `ConversationScanner` ABC (`base.py:15-32`, abstract
  `discover_projects()` / `scan_project()`), bundled together with
  identity/detection/write-target selection into a per-host `LearnPlugin` ABC
  (`base.py:35-129`). `ClaudeCodePlugin` (`plugins/claude.py:27-58`) walks
  JSONL files under a `projects/` directory in its `discover_projects()`
  method (`plugins/claude.py:61-97`, the glob itself at `:95`), decoding each
  project's filesystem-escaped directory name back into a real path via
  `_decode_project_path` / `_greedy_path_decode` (`plugins/claude.py:410-449`,
  `:462-499`). `OpenCodePlugin` (`plugins/opencode.py:60-135`) instead opens a
  SQLite database and queries its `project`/`session` tables
  (`plugins/opencode.py:106-118`) — a structurally different discovery path,
  which is why the miner must go through the plugin abstraction rather than
  assume one file layout.
- `headroom/learn/loops.py` implements loop detection, not error-only
  scanning. `detect_loops()` (`loops.py:110-159`) groups each session's tool
  calls by a canonical signature (`_canonical_signature`, `loops.py:89-101`),
  but the pagination-stripping and bare-integer collapsing are bash/shell-only:
  `loops.py:97` gates both behind `tc.name.lower() in ("bash", "shell")`, so
  only for those two tool names does `grep foo | head -50` and
  `grep foo | head -100` land in one group (`_PAGINATION_RE`,
  `loops.py:48-59`); every other tool falls through to the unconditional
  whitespace-normalize-and-lowercase step at `loops.py:100` with no
  pagination/integer collapsing, so a dummyindex miner over Read/Grep/Edit
  calls would need that gate extended before it could group re-fetch variants
  of those tools the same way. A group meeting `DEFAULT_MIN_OCCURRENCES` (3,
  `loops.py:38`) becomes a `LoopPattern` (`loops.py:67-86`), which classifies
  itself `error-loop` or `rtk-refetch-loop` at its `kind` property
  (`loops.py:86`) based on the `is_error_loop` verdict decided in
  `detect_loops()` (`loops.py:136`), with `wasted_tokens` measured from real
  output byte counts (a 4-bytes/token estimate, `loops.py:42,104-107`) rather
  than an LLM guess. `apply_loop_weighting()` (`loops.py:197-225`) then raises
  a recommendation's `estimated_tokens_saved` to the loop's measured floor
  when the recommendation text overlaps a *majority* of the loop's salient
  signature tokens (`overlap >= max(1, (n+1)//2)`, `loops.py:219`), not mere
  overlap.
- `headroom/learn/writer.py` writes recommendations back into each host's own
  memory file inside a marker-delimited block (`_MARKER_START` /
  `_MARKER_END`, `writer.py:22-27`), built by `_build_section()`
  (`writer.py:89-107`) and merged non-destructively by `_merge_into_file()` /
  `_merge_recommendations()` (`writer.py:162-193`), which carries forward any
  prior section not re-surfaced by the current run instead of clobbering the
  file. `ClaudeCodeWriter` (`writer.py:212-341`) defaults project-level output
  to the gitignored `CLAUDE.local.md` rather than the team-shared `CLAUDE.md`,
  and migrates any stale block left in a legacy `CLAUDE.md` out to the new
  target (`_migrate_legacy_block`, `writer.py:287-336`); `CodexWriter` /
  `GeminiWriter` / `GrokWriter` (`writer.py:349-440`) target `AGENTS.md` /
  `GEMINI.md` / `GROK.md` respectively — one writer per host convention, not
  one shared file. Coverage is wider than the primary target per writer:
  `ClaudeCodeWriter` also writes `MEMORY.md` (`writer.py:338-341`) alongside
  `CLAUDE.local.md`, and `CodexWriter` also writes `instructions.md`
  (`writer.py:373`) alongside `AGENTS.md`.
- **Store resolution is per-host and reads an override, not a hardcoded
  path** — confirming the plan's premise. `ClaudeCodePlugin.__init__`
  resolves the base directory via `claude_config_dir()` (`_shared.py:16-26`),
  which honors the `CLAUDE_CONFIG_DIR` environment variable and falls back to
  `~/.claude`, then reads `<base>/projects/` (`plugins/claude.py:35-37`);
  `detect()` is a cheap existence-plus-non-empty check
  (`plugins/claude.py:53-54`). `OpenCodePlugin._resolve_db_path`
  (`plugins/opencode.py:189-197`) checks an explicit constructor argument,
  then the `HEADROOM_OPENCODE_DB` environment variable, before falling back to
  `~/.local/share/opencode/{opencode-local.db,opencode.db}`
  (`plugins/opencode.py:51-54`). Neither plugin is wired in by a hardcoded
  path in the CLI: `registry.py:21-40` auto-discovers plugins by scanning
  `headroom.learn.plugins.*` submodules for a module-level `plugin` instance.
  This machine's transcript store sits at a non-standard location,
  `~/.claude-os/projects/` rather than `~/.claude/projects/` — but that is
  already handled: `CLAUDE_CONFIG_DIR` names the config directory itself, not
  a sibling of `projects/`, and this machine already has
  `CLAUDE_CONFIG_DIR=~/.claude-os` set, so stock `ClaudeCodePlugin()` resolves
  `self.claude_dir` to `~/.claude-os` and `self.projects_dir` to
  `~/.claude-os/projects/` with no subclass and no override. The plan's
  task-5 prerequisite — resolve the store, don't hardcode it — is satisfied
  by the upstream technique as-is: the env-var-honoring resolver plus the
  `claude_dir=` constructor escape hatch (for a store that isn't reachable
  through `CLAUDE_CONFIG_DIR` at all) is exactly the pattern to port.

- **Two deterministic components sit inside the rejected analyzer, and one
  sits outside it entirely** — surfaced by the audit of the analyzer SKIP, and
  in scope for this item even though the analyzer itself is not. (a)
  `_build_digest` (`analyzer.py:254-348`) is LLM-free: it computes failure
  rates and token totals, enforces an 80k-token char budget
  (`_MAX_DIGEST_TOKENS`, `analyzer.py:50`; truncation marker at `:307-314`),
  and head-and-tail-truncates error output (`_truncate_head_tail`,
  `analyzer.py:377-391`) so a traceback's `ExceptionType: message` survives the
  cut — directly reusable by a session-memory feeder. (b)
  `_build_prior_patterns_section` (`analyzer.py:215-251`) reads the existing
  marker block back as the baseline before a re-run, pairing with `writer.py`'s
  non-destructive merge. (c) `headroom/memory/traffic_learner.py`
  (`_patterns_to_recommendations`, `:1657-1694`) already builds `Recommendation`
  objects from extracted patterns with no model in the loop and feeds the same
  `ContextWriter` — the closest upstream analogue to what this item wants, and
  it is not covered by the analyzer SKIP.

None of the above is copied source — the above is a description of the
technique in original words, with citations for anyone who wants to check the
claim against the clone directly.

### Explicit SKIPs

- **headroom Rust/Python parity harness** (`crates/headroom-parity/`, commits
  `c15e557`, `fd6abac`) — gates two implementations of the same compressor
  against each other. dummyindex has no dual-implementation surface, so there is
  nothing to compare; `context reality-check` already covers the nearest
  analogue (doc claims vs source).
- **headroom proxy + compressor stack** (`crates/headroom-proxy`,
  `headroom-core`, commits `57bf720`, `e530de5`, `83e27e5`, `cb8f4b6`) — token
  compression at the LLM transport layer. Outside dummyindex's domain.
- **headroom LLM analyzer** (`headroom/learn/analyzer.py`) — re-verified against
  the 2026-07-29 clone (HEAD `1588f5e`), read start to finish this round (was
  listing-only through R1). R1's rejection stands. `SessionAnalyzer.analyze()`
  (`analyzer.py:169-207`) always routes through `_call_llm()` (called at
  `:198`), which either calls `litellm.completion()` against a hosted provider
  (`:817`, model chosen by `_detect_default_model()`, `:116-156`) or, when no
  API key is present, subprocess-execs a coding-agent CLI — `claude -p
  --output-format stream-json`, `gemini -p`, or `codex exec`
  (`_CLI_BACKENDS`, `:56-60`) — via `_call_cli_llm()` (`:542-631`) /
  `_call_claude_cli_streaming()` (`:633-781`), both built on
  `headroom._subprocess.run`/`Popen` (imported `:27`, invoked `:584`, `:649`).
  The only deterministic code in the file — digest assembly (`_build_digest`,
  `:254-348`) and response parsing (`_strip_fenced_json`, `:491-539`;
  `_parse_llm_response`, `:840-883`) — is plumbing around that call, not a
  standalone analysis path: nothing in `analyze()` produces a
  `Recommendation` without going through `_call_llm()`, and when the call
  raises, the `except` block (`:203-206`) returns zero recommendations rather
  than falling back to a deterministic result. A non-deterministic,
  network/subprocess-dependent memory writer is not acceptable here.

## Contracts

- Every row in **Sources evaluated** cites a file read from a clone, and every
  DONE verdict cites the dummyindex symbol that superseded it. A row whose
  grounding cannot be stated is not added.
- R1 is not edited by this proposal. Its `spec.md` lives on an unmerged branch;
  the deltas above supersede it in place and name the R1 item number they
  replace.
- No adoption work is performed here. This proposal produces the ranked backlog;
  each item lands through its own build-loop wave.

## Risks

- **Item 1 introduces the first model-dependent test in the suite.** Cost and
  flakiness are real. Mitigation is item 3 (selftest first) plus keeping the gate
  out of the default `pytest -q` path.
- **Item 2 can ossify prose.** Assert only load-bearing phrases; over-pinning
  turns every docs edit red for no defect.
- **Both upstreams track their default branch.** Verdicts are pinned per-source,
  not to one date: headroom to 2026-07-29 (clone HEAD `1588f5e`, committer date
  2026-07-28); ponytail to 2026-07-29 (clone HEAD `16f2980`, committer date
  2026-07-15) — item 4's two correction passes (2026-07-29 and 2026-07-30) both
  re-read this same `16f2980` clone rather than re-cloning, since the defects
  found in both were reasoning or arithmetic errors (incomplete coverage,
  mis-applied evidence, miscounted files), not staleness. A later re-eval
  must re-clone rather than trust these rows.

## Acceptance

- [ ] Both sources carry a license, a grounding statement, and a verdict — no `TBD` rows.
- [ ] Each of the three R1 deltas names the R1 item number it supersedes and the dummyindex symbol or test that justifies it.
- [ ] `headroomlabs-ai/headroom` appears exactly once as a re-evaluation, not as a duplicate new source.
- [ ] ponytail's already-ported `loc.js`/`correctness.js` is recorded as DONE with its credit site, so no wave re-adopts it.
- [ ] Every SKIP states why the technique has no seam in this codebase.
- [ ] Backlog items are ordered by value and each names a concrete seam file.
- [ ] Item 4's coverage table classifies every host surface opened as
      covered / partial / gap / out-of-scope, grounds each verdict in
      dummyindex's own `SUPPORTED_PLATFORMS`/`.agents/skills` host list or an
      identified README line, and adds no host.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `install-surface`
- `tree-enrich`
- `equip`
- `feature-taxonomy`
- `session-memory`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
