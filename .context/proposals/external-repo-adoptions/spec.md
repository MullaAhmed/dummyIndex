# External-repo adoptions — spec

`status: planned` · `created: 2026-07-01`

A code-grounded backlog of techniques worth folding into dummyindex, distilled from
a two-pass LLM-council analysis of 8+ external repositories. Every call below is
**ADOPT / ADAPT / PILOT / SKIP** with the exact dummyindex seam it touches, an effort
estimate, and the verification status of its source. This is an **umbrella proposal**:
each ADOPT/ADAPT item is a small, independently shippable change; the first deliverable
(the build-loop test gate) is specified in depth here and gets its own checklist in
`plan.md`.

---

## Problem

dummyindex builds itself for each repo — generating skills/agents and indexing code into
`.context/`. Two structural gaps motivated scanning the ecosystem for proven techniques:

1. **No test/verification gating anywhere in the build pipeline.** `context/domains/buildloop/`
   is deliberately pure state management; the package docstring is explicit that
   *"the agent dispatch + verify-before-tick discipline live in the `dummyindex-build`
   skill (markdown), not here."* So "full suite green before a tick" is **asserted in prose,
   enforced by nothing in code.** A wave can flip `- [ ]` → `- [x]` on an unproven claim.
2. **equip hardens *governance* but not *artifact correctness*.** equip has gap-driven
   discovery, trust/blast-radius gating, atomic vendor-install, and a hash-baselined
   lifecycle — but it never checks whether a generated/vendored `SKILL.md` is well-formed,
   carries provenance, or still matches the source it documents.

The question put to the council: *of these external sources, what should dummyindex adopt,
adapt, or skip — optimizing for high-value, license-compatible changes that strengthen the
core (context engine, equip, council, build-loop) without bloating surface area?*

---

## Methodology (how this backlog was produced)

Two LLM-council runs, each: **parallel research → advisor lenses (Contrarian / First-Principles /
Expansionist / Outsider / Executor) → adversarial cross-check → chairman synthesis.**

- **Run 1** (8 sources): research agents fetched each repo, a 9th agent built a capability
  map from `.context/`, then the five lenses deliberated and peer-reviewed.
- **Run 2** (gap-fill): two Run-1 sources failed — one errored, one returned **fabricated**
  schema-filler. Re-run hardened with a 6-method fetch ladder + an **adversarial verify stage**
  that independently re-fetches and sets `grounded` / `fabrication_flag`, discarding anything
  it cannot confirm.

**Grounding status per source** (only fetched/verified sources drive ADOPT calls):

| Source | License | Grounding | Outcome |
|---|---|---|---|
| `nizos/tdd-guard` | MIT | cloned + file-verified | ADOPT (reporter) / ADAPT (hook) / SKIP (judge) |
| `addyosmani/agent-skills` | MIT | fetched | ADOPT (lint) / ADAPT (anatomy) |
| GitHub `gh skill` | proprietary (technique only) | fetched (changelog) | ADOPT (provenance idiom) |
| `yusufkaraaslan/Skill_Seekers` | OSS (verify) | fetched | PILOT (doc↔code detection) |
| `headroomlabs-ai/headroom` | Apache-2.0 | fetched + verified | ADAPT (sentinels) / PILOT (miner) / SKIP (rest) |
| `letta-ai/claude-subconscious` | MIT | fetched | ADAPT (Stop-hook idiom only) |
| `ZhangHanDong/cowork-skills` | OSS | fetched | SKIP (AST-author; equip dominates) |
| `multica-ai/andrej-karpathy-skills` | MIT | fetched | SKIP (one prose skill) |
| `skilluse.dev` | MIT | fetched | SKIP (no harvestable schema) |
| `aiwithremy/claude-skills-llm-council` | **none** | fetched + md5-matched | SKIP (byte-identical dup of installed skill) |

---

## The adoption backlog (priority-ordered)

| # | Item | Call | Seam | Effort |
|---|---|---|---|---|
| 1 | tdd-guard pytest reporter → `test.json` + build-loop gate | **ADOPT** | new `context/domains/build/` + `cli/build_loop/waves.py` | S–M |
| 2 | gh-skill provenance-in-frontmatter | **ADOPT** | `cli/equip/install.py` vendor write + `plugins/sources.py` | S |
| 3 | agent-skills frontmatter/anatomy lint as install gate | **ADOPT** | `cli/equip/install.py` + `plugins/sources.py` | S |
| 4 | headroom managed-region sentinels (own-a-region) | **ADAPT** | `cli/guard_doc_write.py` + `docguard/` + in-place writers | S |
| 5 | tdd-guard fail-open opt-in PreToolUse test-gate hook | **ADAPT** | `context/hooks.py` + new CLI guard | M |
| 6 | agent-skills anatomy emission + Verification/Red-Flags | **ADAPT** | `context/domains/equip/generate/` | M |
| 7 | subconscious fire-and-forget Stop-hook idiom | **ADAPT** | `context/hooks.py` + `cli/reconcile.py` | M |
| 8 | Skill_Seekers doc↔code conflict detection | **PILOT** | `context/domains/equip/generate/gaps.py` | M |
| 9 | headroom deterministic failure-miner → `core-memories.md` | **PILOT** | session-memory feeder over `~/.claude/projects/*.jsonl` | M |
| — | LLM-judge hard block · per-language reporter "marketplace" · cowork AST-author · skilluse.dev · karpathy · aiwithremy-council | **SKIP** | — | — |

---

## Council reasoning (distilled)

**Agreements (high-confidence):**
- The tdd-guard **reporter** (not the judge) is the anchor — deterministic, machine-readable,
  Python-native; even the Contrarian kept it.
- The **LLM-as-judge hard block must not be ported**: a per-edit LLM round-trip contradicts
  dummyindex's deliberately fail-open `guard_doc_write.py` and would block the very edit that
  fixes a red test.
- Frontmatter/anatomy lint and provenance-in-frontmatter are cheap, deterministic wins.
- letta-subconscious: adopt the **idiom**, vendor nothing (its memory taxonomy overlaps
  session-memory; the repo is a self-described demo).

**Clashes (resolved):**
- *How far to push tdd-guard* — the "verification marketplace" framing (auto-vendor a
  per-language reporter fleet) was overruled as premature surface-area growth. Ship the
  Python gate first.
- *Skill_Seekers doc↔code detection — polish or core?* — promoting it to a general
  feature-doc drift engine is the right north star but a multi-sprint bet; scope the pilot
  to **vendored skills** (which expose a machine-extractable claimed API) first.
- *The test-gate hook* — the "enforcement violates dummyindex's no-enforcement stance"
  objection collapses once the gate reads the **deterministic `test.json`** (never an LLM)
  and is **fail-open + opt-in**.

**Blind spots the cross-check caught:**
- **License unverified for most sources** — only resolved in Run 2 (headroom Apache-2.0 ✓;
  aiwithremy = no license, SKIP).
- **Vendoring the reporter means owning a fork that rots** — pin the `test.json` schema with
  a contract test so upstream drift surfaces loudly.
- **Nobody specified who runs pytest** — the reporter only writes `test.json` *during a run*;
  if nothing invokes pytest before a wave tick, the gate reads stale/absent JSON. *The trigger
  is the missing organ, not the format.* (Addressed in deliverable #1 below.)
- **No success metric for "trustworthy context"** — every adoption hardens artifact
  correctness; none proves `.context/` improves retrieval. Out of scope here, flagged as a
  standing gap.

---

## Deliverable #1 (deep dive): build-loop test gate

The anchor. Everything else is downstream of a deterministic test-truth artifact existing.

### Design (corrected for dummyindex's layering)

The council's phrasing — *"make `next_wave` itself invoke pytest"* — must be adjusted: the
build-loop **domain is pure**, and `conventions/coding-practices.md` keeps subprocess I/O at
the CLI boundary. So:

- **Reporter (impure, installable):** a `pytest11` plugin (entry-point in `pyproject.toml`)
  that hooks `pytest_runtest_logreport` / `pytest_collectreport` / `pytest_sessionfinish`
  and writes a normalized record to `.context/build/test.json`. Ported in spirit from
  tdd-guard's `reporters/pytest/` (MIT); not vendored verbatim.
- **Schema + reader (pure domain):** new `context/domains/build/test_state.py` —
  `TestState`/`TestModule`/`TestCase` frozen dataclasses, `parse_test_state(json) -> TestState`,
  and `test_gate(state) -> GateDecision` (pure, deterministic: red suite ⇒ block).
- **Runner (impure, CLI boundary):** `cli/build_loop/` gains a step that **invokes pytest**
  (subprocess) *before* reading `test.json`, so the gate can never tick on stale data — this
  is the "missing organ." It then calls the pure `test_gate`.
- **Wiring:** `cli/build_loop/waves.py:do_next_wave` surfaces a conductor instruction
  (sibling to `_GATE_INSTRUCTION`) when the suite is red, refusing to advance the wave.
- **Drift safety:** a **schema contract test** asserts the `test.json` shape; if a future
  reporter (or upstream) changes it, the test fails loudly rather than the gate silently
  mis-reading.

### Acceptance (deliverable #1)

- [ ] The pytest reporter emits `.context/build/test.json` with the normalized
      `{testModules:[{moduleId,tests:[{name,fullName,state,errors}]}]}` shape for passing,
      failing, and collection-error fixtures.
- [ ] `parse_test_state` + `test_gate` are pure (no I/O), fully unit-tested; a red suite ⇒
      `GateDecision` blocks, an all-green suite ⇒ allows, absent/stale JSON ⇒ **fail-open with
      a stderr warning** (never a hard crash).
- [ ] The CLI runner invokes pytest before reading, so the gate observes the *current* suite,
      not a previous run; a failing fixture flips the wave gate end-to-end.
- [ ] A schema contract test fails loudly on any `test.json` shape drift.
- [ ] Full suite green (`conventions/testing.md`); `.context/features/build-loop/*` updated.

---

## Design notes (remaining ADOPT/ADAPT items)

- **#2 provenance-in-frontmatter** — equip already computes the pinned sha
  (`plugins/sources.py:resolve_ref`); stamp `repository` + `ref` + git tree-sha into the
  copied `SKILL.md` frontmatter (not only `.context/equipment.json`) in
  `cli/equip/install.py`'s vendor write path (`context/atomic_io.py:write_text_atomic`).
  Makes the pin portable when the skill is copied out of the repo.
- **#3 anatomy lint gate** — deterministic validator (name == dir, `description` with a
  "Use when" trigger ≤1024 chars, `SKILL.md` ≤ size cap, required sections present) that
  **fails the atomic vendor-install** in `cli/equip/install.py` and re-checks vendored skills
  via `plugins/sources.py`. Hardens both generated and SHA-pinned skills.
- **#4 managed-region sentinels** — a finer granularity on the **managed-doc-homes** work
  already shipped (`cli/guard_doc_write.py`, commit `4b401a6`): marker-fenced
  `<!-- dummyindex:start --> … <!-- dummyindex:end -->` regions let dummyindex own a *region
  inside* a user-owned `CLAUDE.md`/feature doc instead of the whole file. Ported concept from
  headroom's `learn/writer.py` (Apache-2.0). **Hard requirement: fail-safe** — a corrupted or
  user-deleted fence pair must append, never clobber; needs an explicit test that hand-written
  prose outside a broken fence survives a rewrite.
- **#5 test-gate hook** — optional, **off by default**, fail-open PreToolUse hook (sibling to
  the doc-guard under `context/hooks.py:_CLAUDE_HOOKS`) that reads `.context/build/test.json`
  and warns/blocks on a red suite. **Never** an LLM round-trip; reuses tdd-guard's
  ignore-patterns + SessionStart state-reset ergonomics. Gated behind #1 landing.
- **#6 anatomy emission** — make `context/domains/equip/generate/` emit every generated skill
  against a fixed anatomy with a mandatory **Verification** checklist (exact command +
  expected result) and a **Red-Flags** section. Take the template shape; skip the
  anti-rationalization-table ceremony.
- **#7 Stop-hook idiom** — adopt subconscious's *fire-and-forget* pattern (parse → write
  payload to scratch → spawn detached worker → exit fast) as a shared hooks helper, e.g. to
  precompute a reconcile delta on session end so the next SessionStart shows a fresh drift
  report. **Do not** run `dummyindex context reconcile` as a *detached writer* to `.context/`
  — concurrent writers against a deliberately in-session/read-only design is a corruption
  hazard. Idiom only.
- **#8 doc↔code conflict detection (PILOT)** — a new pass in
  `context/domains/equip/generate/gaps.py` beside `capability_gaps`, diffing the API a
  vendored `SKILL.md` *claims* against the repo's extracted symbol index
  (missing-in-code = high severity). Scoped to **vendored skills** first (prose skills expose
  no clean claimed-API). **Verify Skill_Seekers' license before writing code.**
- **#9 failure-miner (CONSTRAINED PILOT)** — a **deterministic** scanner over
  `~/.claude/projects/*.jsonl` (glob → ToolCall → collect `is_error`, repeated-path,
  loop detection) feeding session-memory `core-memories.md`. **Reject headroom's LLM analyzer**
  — keeping the miner deterministic upholds the "never an LLM judge" spine. **Falsifiable:**
  if the deterministic shell yields no useful signal without an LLM step, it auto-demotes to
  SKIP. Gated behind #4.

---

## Non-goals / SKIP rationale

- **tdd-guard LLM-as-judge hard block** + **per-language reporter "marketplace"** — fights the
  fail-open design; premature surface growth.
- **cowork AST-author-a-skill** (L effort) — equip already dominates repo→skill on governance;
  long-tail value.
- **skilluse.dev / karpathy-skills** — no harvestable schema / a single prose skill.
- **aiwithremy/claude-skills-llm-council** — verified **byte-for-byte (md5) identical** to the
  already-installed `~/.claude/skills/llm-council/` skill, and carries **no license**. The
  premise that it differs from the existing council is false; dummyindex's deterministic,
  resumable, persona-routed `council_batch.py` already exceeds it.

---

## Risks & caveats

- **#1 fork-rot:** the reporter is a spirit-port of an MIT plugin; pin the `test.json` schema
  with a contract test so upstream changes surface as a red test, not silent gate drift.
- **#4 clobber risk:** region-level rewrites must fail safe on malformed/missing fences.
- **#8/#9 are PILOTs, not commitments:** both carry an explicit kill condition (no clean
  claimed-API for prose skills; no deterministic signal for the miner).
- **License discipline:** all code-level adoptions are technique ports of permissively-licensed
  (MIT/Apache-2.0) or uncopyrightable-pattern sources; nothing is vendored verbatim.
- **Layering:** keep new domain modules pure; all subprocess/file I/O stays at the CLI boundary
  per `conventions/coding-practices.md`.

See `plan.md` for sequencing and the deliverable-#1 checklist.
