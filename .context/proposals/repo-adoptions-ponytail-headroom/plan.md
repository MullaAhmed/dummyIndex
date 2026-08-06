# Plan — Repo adoptions R2: ponytail behavior-gate + rule-copy canary, headroom failure-miner re-eval

> Ordered tasks naming their file paths. Each task lands independently; nothing
> here depends on R1 (`.context/proposals/external-repo-adoptions/`) being merged.

## Ordering rationale

Task 1 first because it is small, deterministic, needs no API key, and closes the
exact hole that let the inert ADHD policy ship. Tasks 2–3 are the model-dependent
behavior gate, ordered so the grader is proven before any paid run. Tasks 4–5 are
pilots and may be deferred without blocking anything.

## Tasks

1. **Rule-copy canary — invariant phrases in the doc-sync guard.**
   Extend `tests/cli/test_cli_doc_sync.py` (the existing
   `test_default_plugin_docs_pin_targets_and_reviewed_trust` over
   `_DEFAULT_PLUGIN_DOCS`) with a second assertion class: for each load-bearing
   phrase of `ALWAYS_ON_OUTPUT_POLICY`, require that every doc restating the
   policy carries a phrase that does not contradict it. Reuse
   `dummyindex.context.output.bootstrap.ALWAYS_ON_OUTPUT_POLICY` as the single
   source — the test file already imports from `dummyindex.context.enums`, so the
   import direction is established. Keep the existing token-presence assertions;
   this is additive.
   Ported from ponytail `scripts/check-rule-copies.js` (MIT), whose `INVARIANTS`
   list is the fallback for surfaces that cannot be byte-compared. Do **not**
   byte-compare here: `docs/COMMANDS.md`, `docs/guide/07-cli.md`, and
   `dummyindex/skills/skill.md` restate the policy in deliberately different
   prose.
   Acceptance: reverting the policy constant to its pre-fix "use the combined
   `caveman`/`i-have-adhd` behavior" wording turns this test red.

2. **Behavior-gate grader + selftest (no API key).**
   Add a grader beside `tests/eval/test_retrieval_eval.py` that scores one
   response against the observable rules of `ALWAYS_ON_OUTPUT_POLICY`:
   outcome-or-next-action first, numbered multi-step work, specific quantities
   over vague ones, one concrete closing action. Ship it with a selftest over
   fixture responses — known-passing and known-failing — so the instrument is
   proven at zero cost.
   Ported from ponytail `benchmarks/behavior.js` plus the `--selftest` discipline
   in `benchmarks/robustness-audit.js:1-5` (MIT). Mirror the existing
   deterministic-fixture pattern in `tests/eval/retrieval_fixtures.json`.
   Acceptance: the selftest runs inside the default `pytest -q` path, needs no
   network, and fails if any check is inverted.

3. **Behavior-gate two-arm run (model-dependent, opt-in).**
   Wire the task 2 grader to two arms — a no-guidance control expected to fail
   and a managed-guidance arm expected to pass — and report the delta. Keep it
   **out** of the default `pytest -q` path: mark it so it runs only on an
   explicit opt-in, matching how `tests/eval/BASELINE.md` records measured
   numbers rather than gating every run.
   Ported from ponytail `benchmarks/behavior.yaml` + `benchmarks/arms/`.
   Acceptance: the control arm fails the gates, the guidance arm passes, and the
   delta is recorded next to `tests/eval/BASELINE.md`.

4. **Host coverage gap list (pilot, no host added).**
   Compare ponytail's per-host surfaces — `opencode.json`,
   `gemini-extension.json`, `pi-extension/`, `plugin.yaml`,
   `hooks/{claude-codex,copilot,qoder}-hooks.json`, and its `.qoder/`, `.kiro/`,
   `.windsurf/` rule copies — against what dummyindex's `agents` platform already
   covers through `dummyindex/installer/link/families.py`. Write the gap list into
   this proposal's spec; add no host.
   Acceptance: every ponytail host surface is classified covered / gap /
   out-of-scope, with the reason stated.

5. **Deterministic failure-miner (pilot, carried from R1 item 9).**
   Scanner over host transcript stores that extracts repeated tool-error and loop
   signatures and feeds `.context/session-memory/`. Reuse
   `dummyindex/context/domains/memory/store.py` and
   `dummyindex/context/domains/atomic_io.py:write_text_atomic` for the write path.
   Grounded in headroom `headroom/learn/scanner.py` + `loops.py` + `writer.py`
   (Apache-2.0). `headroom/learn/analyzer.py` is explicitly rejected —
   deterministic scanner only.
   Note a real prerequisite this session surfaced: transcripts on this machine
   live under **`~/.claude-os/projects/`**, not `~/.claude/projects/`. Any miner
   must resolve the store rather than hardcode one path, exactly as headroom does
   with `learn/plugins/claude.py` vs `learn/plugins/opencode.py`.
   Acceptance: the scanner is deterministic, writes atomically, and resolves the
   transcript store instead of assuming it.

## Attribution

Both upstreams are permissively licensed and must be credited where their
technique lands, following the existing idiom at
`tests/eval/test_retrieval_eval.py:11` ("mirroring ponytail's `loc.js` +
`correctness.js`").

- `DietrichGebert/ponytail` — MIT — tasks 1, 2, 3, 4.
- `headroomlabs-ai/headroom` — Apache-2.0 — task 5. Apache-2.0 requires the
  `NOTICE` attribution be preserved for any copied source; prefer
  reimplementation from the described technique over copied code.

## Out of scope

- Editing R1's `spec.md` on branch `external-repo-addition`.
- Adding any new host platform (task 4 is a gap list).
- headroom's proxy, compressor, and parity stacks — see the spec's SKIP section.
