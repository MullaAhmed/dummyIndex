# R3 — full external-repo reanalysis (2026-08-07)

> Ephemeral proposal artifact: this dir is GC-swept when the proposal closes.
> The durable copy of this record lives in the `dummyindex-repo-adoption-verdict`
> memory (and, for the meta-harness rows, `meta-harness-vs-dummyindex-verdict`).

**Coverage:** 13/13 previously-verdictized sources re-analysed against main
v0.34.0 (`cfe6a13`) with fresh upstream clones — 24 agents (13 survey + 11
adversarial refutes), **0 refuted** (corrections were precision-level only).
Scope = sources with prior R1/R2/bakeoff verdicts; the ~20 never-verdicted
search candidates (SkillOpt, Staleguard, …) and idiom-only inspirations
(PageIndex, aider repo-map, GraphRAG, Sourcetrail) stay queued for a future
survey. New survey candidates discovered this round: `nizos/probity`,
`001TMF/harness-forge`.

**Corrected premise (the workflow corrected the orchestrator):** the R2
22-surface host-coverage classification already postdated PR #9 (merged
2026-07-24; R2 ran 07-28..30), so **all 9 host-coverage gaps survive** on
current main (`installer/common.py:21 SUPPORTED_PLATFORMS` unchanged) — they
were NOT closed by universal-harness support.

## Verdict table (R3)

| Source | R3 verdict | What changed vs prior row |
|---|---|---|
| `nizos/tdd-guard` | ADOPT reporter / ADAPT PreToolUse gate / SKIP judge+marketplace | Still "the One Thing", still unbuilt. Seam corrected: pure gate in existing `domains/buildloop/test_state.py` (NOT a new `domains/build/`), wired at BOTH `cli/build_loop/dispatch.py:156-159` (flip_item tick) AND `waves.py:307 do_next_wave`; adopt upstream's run-level `reason: passed\|failed\|interrupted` field. Upstream in maintenance mode; successor `nizos/probity` = LLM-validated rules + Node → SKIP reinforced (harvest its deterministic forbidCommandPattern idea only) |
| `addyosmani/agent-skills` | ADOPT lint / ADAPT anatomy emission | Scope reduced: templates already carry trigger descriptions + verification checklists; remaining = Red-Flags section + conformance test. Lint seam corrected: `cli/equip/install.py:_run_vendor_install` before the `:428` write + new pure `domains/equip/plugins/skill_lint.py` (`sources.py` exists at `domains/equip/plugins/sources.py`) |
| `yusufkaraaslan/Skill_Seekers` | PILOT doc↔code conflict detection | **Unblocked**: license verified MIT (R1 left it unverified). `equip/generate/gaps.py` is capability math, not doc↔code diffing — the gap is real; PR #10's symbol-graph makes signature-mismatch checks feasible |
| `headroomlabs-ai/headroom` | DONE sentinels / DONE miner / **new ADAPT-S** license vendoring / SKIPs re-verified | Miner shipped as `domains/memory/miner/` + NOTICE. New compliance item: vendor the Apache-2.0 license text (§4(a)) — only the MIT LICENSE ships today; note a `LICENSES/` dir would NOT ship in the wheel, pick a packaged path |
| `letta-ai/claude-subconscious` | DONE / SKIP — **row closed** | dummyindex's Stop/PreCompact hooks predate R1 (de98833/8184397, June 2026), zero letta lineage; detached worker contraindicated (`hooks.py:88-90` "Background-detach is not used"; native `async: true` supersedes) |
| `ZhangHanDong/cowork-skills` | SKIP AST-author / **new ADAPT-S** content lint | Dominated harder by PR #10. New sub-item R1 never assessed: install-time content lint of vendored skill bodies — equip gates trust/hash but never inspects content; merge into the `skill_lint` gate |
| `DietrichGebert/ponytail` | Built items closed / PILOT host coverage (9 gaps survive) | Upstream frozen at the R2 pin `16f2980`. Behavior gate + canary + selftest BUILT; acceptance re-measure open (below). Opportunity: third behavior arm gating the shipped caveman/adhd plugin guidance (mirrors ponytail's own caveman arm) |
| `stanford-iris-lab/meta-harness` | Contraindication **upstream-corroborated**; execute this proposal | Upstream PR #12 (2026-07-11) added `experimental/harbor_meta_harness/`: reward = task-outcome via Harbor verifier suites (mean/min/fraction_solved), trigger accuracy appears NOWHERE; README mandates "Probe each collection before using it"; `forbidden_references` denylist ≈ our observed tuner-overfit mode. All proposal anchors verified EXACT on main (SKILL.md:483, :571 — no drift) |
| `multica-ai/andrej-karpathy-skills` | SKIP re-confirmed | Dormant (latest 2026-04-20); still one prose skill |
| `aiwithremy/claude-skills-llm-council` | SKIP re-confirmed | Dormant; still byte-identical md5 dup of the installed llm-council skill; still NO license |
| GitHub `gh skill` | ADOPT still open — **upgraded + defect found** | Source is MIT-readable (R1 mislabeled "proprietary"): exact vocabulary `metadata.github-repo/-ref/-tree-sha/-path/-pinned` harvestable. **Defect:** `domains/equip/plugins/vendor.py:17-21` prepends the vendored sentinel ABOVE `---`, so spec-conformant parsers (incl. `gh skill`) see NO frontmatter on dummyindex-vendored skills; fix helper already in-repo: `_insert_sentinel_after_frontmatter` at `equip/generate/render.py:152` |
| `skilluse.dev` | SKIP re-confirmed | Still no harvestable schema |
| `tirth8205/code-review-graph` | DONE harvest / **new PILOT** impact eval | Query verbs byte-identical since the bakeoff (nothing new to harvest). New: co-change impact-accuracy eval for `context graph impact` in `tests/eval/` (pattern of `test_retrieval_eval.py`) |
| `Graphify-Labs/graphify` | **new ADAPT-S** decorator edges / optional --directed path | Confirmed extractor blind spot: Python decorators emit ZERO edges (`pipeline/extract/generic.py:742-743` walks bodies only — empirically reproduced). Upstream #2154 emits `references` edges with context="decorator"; port as a labeled adaptation. Upstream relicensed MIT→Apache-2.0 |
| `abhigyanpatwari/GitNexus` | SKIP code (now PolyForm-NC + Node) / ADAPT ideas, clean-room only | Now a monorepo CLI + MCP server. Idea ports: inline staleness note via `_result(note=)` + reconcile anchor (S), `cycles` verb over `imports_from` SCCs (S), `diff-impact` verb reusing `context/build/git_delta.py` (M). PolyForm-NC forbids reuse — no TypeScript-derived text or structure |

## R3 priority backlog (recorded here, executed via separate proposals)

1. tdd-guard reporter → `.context/build/test.json` + `domains/buildloop/test_state.py` gate (updated seam; runner invokes pytest itself; `reason` field; fail open on interrupted/absent runs)
2. gh-skill frontmatter provenance (`metadata.github-*`) + the sentinel-below-frontmatter interop fix (reuse `render.py:152` helper on the vendor path; + regression test)
3. headroom Apache-2.0 license-text vendoring (compliance, S — packaged path, not `LICENSES/`)
4. `skill_lint` install gate (agent-skills frontmatter/anatomy lint + cowork-skills content lint, merged; fail-open, deterministic)
5. Behavior-gate acceptance re-measure — guidance 0.56 vs 0.6 floor at n=9 → raise repeats (carried from R2; the one open R2 item)
6. Decorator-edge extractor fix (S; also fixes false-zero-callers for decorated symbols)
7. GitNexus-idea graph verbs: staleness note (S), `cycles` (S), `diff-impact` (M)
8. tdd-guard PreToolUse test-gate (ADAPT; opt-in, off-by-default, fail-open; after #1)
9. Skill_Seekers doc↔code conflicts pilot (unblocked; symbol-graph substrate)
10. code-review-graph impact-accuracy eval + ponytail host-coverage pilot (9 surviving gaps)

## Addendum — new source surveyed on request (2026-08-07): `PrimeIntellect-ai/prime-agent`

First-round survey (no prior row): 3 lenses (continual-harness//refine,
skills/memory model, architecture/provenance), 6 agents (3 survey + 3
adversarial refutes), **0 refuted**. Pinned HEAD `87e7a7f` (2026-08-06; the
repo is fast-moving — v0.7.0, ~787 PRs since 2026-05-08).

**What it is.** MIT (dual copyright: Mario Zechner 2025 + Prime Intellect 2026)
TypeScript monorepo + Python `prime-agent-runtime`. NOT a GitHub fork but a
code-lineage continuation of pi-mono (all four packages still named
`@earendil-works/pi-*`); the RLM + Continual Harness layers (arXiv 2605.09998)
are PrimeIntellect-original. ★4.2k.

**Verdict row:**

| Source | Verdict | Key findings |
|---|---|---|
| `PrimeIntellect-ai/prime-agent` | **SKIP** (self-judged auto-refine loop + entire Node/TS + IPython runtime) / **ADAPT** (refine-loop *disciplines*, clean-room ideas only) / **NO-ACTION** interop fact | `/refine` is **self-judged, not outcome-validated**: "evidence" = the proposing LLM's own rationale; `expectedOutcome` is recorded but never validated; auto-refine defaults ON (every 25 turns/at compaction, LLM-gated); the kernel CRUD path (`rlm.harness.create_memory` etc.) bypasses even those gates. The paper's game environment had an outcome signal; the coding port **dropped the outcome channel** — i.e. a shipping instance of exactly the self-optimization shape our falsification experiments contraindicated. Second corroborating exhibit for this proposal's decision record. |

**ADAPT ideas (clean-room Python, each routes through its own proposal):**

1. [M] **Rollback ledger for the equip patch seam** — per-patch before/after
   snapshots + inverse replay (`equip rollback <id>`), modeled on
   `refinement.ts:804-836 rollbackProposal`. Confirmed gap: reset-to-pristine is
   equip's only escape (`lifecycle/status.py:314-340`); mitigation noted — git
   already gives coarse rollback, so the value is per-patch granularity.
2. [S] **Refinement-event audit fields** (trigger/changes/evidence/
   `expectedOutcome` + rollback pointer) on session-memory records and curated
   `.context/` mutations. Genuine gap is `expectedOutcome` ("how to validate")
   — the miner already emits structured evidence (`miner/models.py`).
3. [S] **Scope-promotion policy** (local-by-default; global entries read-only
   during local refinement — override via new local entry; project-qualified
   naming before global promotion) + smallest-relevant-component taxonomy →
   `dummyindex-remember` promotion rules (`SKILL.md` step 6, `core-memories.md`).
4. [S] **Noise-rejection criteria** ("one-off noise, unsupported hypotheses,
   transient tool outputs", `refinement.ts:175-185`) as negative criteria in the
   memory-skill guidance. Refuter-corrected seam: NOT `nudge.py` (that is a
   deterministic threshold, `is_significant()` `nudge.py:26-30`) — skill prose
   only.
5. [M] **Autonomous quality-gate loop mechanics** → refines the unbuilt R1 #1
   build-loop test gate (repo test command as gate, bounded retries, truncated
   failure feedback). Adaptation constraint from refute: their loop is
   fail-closed (`autonomous.ts:290-311`); dummyindex's gate must stay
   **fail-open** per the spine.
6. [S] **Context-handle guidance** — one paragraph in the generated
   HOW_TO_USE telling agents to bind query-verb JSON output to durable
   handles/files instead of re-querying. Corrected seam: `_HOW_TO_USE` template
   at `context/output/instructions.py:23-144` (NOT `docs.py:96-107`, which is
   INDEX.md's builder). Side-finding either way: **HOW_TO_USE never mentions
   the PR #10 `context graph` query verbs at all** — a doc gap worth closing
   regardless.
7. [M, speculative PILOT] Delegation-pattern detection in the failure-miner →
   "promote to specialist" suggestion feeding `equip/generate/specialists.py`.

**Interop fact (no action):** prime-agent natively discovers `.agents/skills`
— dummyindex's portable skill (`installer/common.py:73`) already carries into
prime-agent for free. It consumes NO `.claude/agents/*.md`, so rendered
subagent equipment does not carry over. Candidate for the harness-landscape
host matrix (documentation-only).

**Open before any test-suite-as-verifier design:** the reward wiring lives in
sibling repos `PrimeIntellect-ai/verifiers` + `prime-rl` (unexamined — future
survey candidates alongside `nizos/probity`, `001TMF/harness-forge`).

## Incident note

During the R3 workflow a survey/refute agent ran `git reset HEAD~1` on
`feat/meta-harness-alignment`, un-committing the rebased WIP. Index and worktree
were verified byte-identical to `8b283c9` and the ref was restored with
`git reset --soft 8b283c9`; all other refs audited clean (main == origin/main,
no stash, single worktree). Lesson for future workflows: survey agents get
read-only instructions for the host repo, mutations only in their clone dirs.

## Method

Per-source: fresh shallow clone (depth 50) → upstream delta vs pinned SHA/prior
survey date → seam re-check by reading current source (never the prior survey's
word) → structured verdict → adversarial refute for every actionable verdict
(refuters instructed to open files and default to refuted when uncertain).
Full structured rows with citations: workflow `wf_25d54444-2e6` output
(session-scratchpad `tasks/wkftn8sx3.output`; does not persist across sessions —
this file and the memory notes are the record).
