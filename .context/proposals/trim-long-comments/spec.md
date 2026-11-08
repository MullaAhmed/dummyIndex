# Spec — Trim long code comments repo-wide (dummyindex/ + tests/) to the non-obvious why, no behavior change

## Intent

The Python source carries long comment blocks and docstrings that narrate
history ("was X before v0.2x", "a second audit found…"), restate what the next
lines do, or argue design at essay length. They cost every reader, and every
agent that opens a file pays for them in context. The user asked for them to be
cut. The goal is shorter, plainer comments that keep only what the code cannot
say itself: the non-obvious *why*, invariants, safety and platform quirks.

Baseline at `0634bfd`, measured with `comment_scan.py <tree> --doc-min 9`
(comment blocks are 5+ consecutive pure-comment lines found by tokenize;
docstrings are 9+ lines, matching the 8-line target):

| Tree | Blocks (lines) | Docstrings 9+ (lines) | Combined | All comment + docstring bytes |
|---|---|---|---|---|
| `dummyindex/` | 98 (665) | 395 (6,397) | 7,062 | 752,482 |
| `tests/` | 49 (470) | 94 (1,382) | 1,852 | 427,044 |

The full item lists are in the scratchpad files `scan_base_dummyindex.txt` and
`scan_base_tests.txt`.

## Contracts

**Edit rules (every unit):**

1. Comments and docstrings only. No change to code, string literals that are
   not docstrings, imports, names, signatures or decorators.
2. Compress to the non-obvious why. Drop history/changelog narration, audit and
   proposal backstory, restatements of the code, and repeated rationale. A
   docstring keeps one summary line plus the contract a caller needs (inputs,
   return, raises, invariants). Target: comment blocks of 4 lines or fewer,
   docstrings of 8 lines or fewer. Do not game the target by joining lines into
   longer ones (keep lines at 100 characters or fewer) or by splitting a block
   with blank lines.
3. Keep verbatim: license and attribution text (license name, source repo or
   URL, copyright holder, `NOTICE` pointer, "ported/derived/adapted from"),
   tool directives (`# noqa`, `# type: ignore[...]`, `# pragma`, `# fmt:`,
   `# ruff:`), and rationale-prefixed comments
   (`python_rationale._RATIONALE_PREFIXES`: `# TODO:`, `# FIXME:`, `# HACK:`,
   `# DEBT:`, `# NOTE:`, `# IMPORTANT:`, `# WHY:`, `# RATIONALE:`). The last
   group may be shortened but must keep its prefix.
4. Keep safety-relevant content: security and trust-boundary notes, data-loss
   warnings, platform quirks (Windows junctions, MAX_PATH, CRLF, py3.10
   behavior), and "why not the obvious approach" notes. Shorten them; do not
   delete them.
5. A block or docstring that must stay over target is allowed. The unit report
   names it as `kind | path:line | lines | reason`.
6. Python files only. Do not touch `.context/`, any `*.md`, templates,
   non-Python files, `tests/fixtures/**` or any `fixtures/` directory.

**Keep-list (load-bearing; shorten only where noted, always allowed over target):**

| Path | What | Why |
|---|---|---|
| `dummyindex/cli/onboard.py` module docstring | must keep `--depth`, `command_depths`, `wired` | asserted by `tests/cli/test_subcommand_help.py:91-99` |
| `dummyindex/context/domains/reality_check/__init__.py` module docstring | the pipeline contract; may tighten wording | `reality-check/plan.md` cites it as the human-facing spec |
| `dummyindex/cli/statusline.py` module docstring, `dummyindex/context/drift.py` `compute_badge` | badge semantics (`[ctx ✓]` / `N drift`) | only place they're documented (`freshness-statusline/concerns.md:25`) |
| `dummyindex/analysis/cluster.py` `_louvain_partition`, `cluster` | the Louvain-only `community` contract | `extraction-pipeline/concerns.md` |
| `dummyindex/context/domains/memory/miner/__init__.py:4-27`, `miner/signatures.py:26-28`, `miner/resolve.py:3-4` | Apache-2.0 attribution, source URL, "derived from" disclosure, NOTICE pointer — **verbatim** | license obligation |
| `tests/eval/behavior_gate.py:4-5`, `tests/eval/behavior_arms.py:6`, `tests/eval/test_behavior_gate.py:4,11`, `tests/cli/test_cli_doc_sync_policy_canary.py:26-27` | MIT attribution with holder (`© 2026 DietrichGebert`) — **verbatim** | license obligation |
| `tests/cli/test_cli_doc_sync_policy_canary.py` | keep the `SCOPE` statement and the `COUPLING HOLE` warning (may tighten) | documents the canary's known limits |
| `tests/eval/test_retrieval_eval.py:1-26` docstring, `:40-47` floor block | brittleness rationale; "Do not lower these" | cited by `conventions/testing.md:50,53` |
| `tests/pipeline/io/test_git.py:1-9`, `tests/paths.py:1-14` | "no subprocess / real git"; the blessed fixture paths | cited by `conventions/testing.md:21`, `repo-tooling/concerns.md` |
| `dummyindex/context/output/viewer/styles.py:455` | CSS text inside a string literal, not a comment | rule 1 forbids editing it |

**Self-hashing files (allowed, noted):** several files hash their own source as
a fingerprint:
- `evolve_native_snapshot._controller()` hashes 10 files, including
  `export/storage.py` (U5), `atomic_io.py` and `evidence.py`;
- `evolve_gate._profile()` hashes `evolve_gate.py` and `evolve_promotion.py`;
- `evolve_experiments.py:536`;
- `installer/ownership.package_source_hash()` hashes every package
  `.py`/`.md`/`.tmpl`.

Editing comments changes those fingerprints exactly as any code edit does. No
test pins a hash. Tests that apply and then promote within one run can fail
only if the source changes mid-run, so the suite runs after every edit has
stopped.

**Invariant (the no-behavior-change proof):** `ast_equiv.py` compares each
changed file's `ast.dump`, with docstrings removed, against `0634bfd`. It also
requires that the per-file counts of directive, attribution, license and
rationale markers never drop. A code change reads `CODE`, a lost marker `LOST`.

## Acceptance

- [ ] `ast_equiv.py` with no paths reports 0 `CODE`, 0 `LOST`, 0 `NEW`, 0
  `GONE`, 0 `PARSE`. Every `WARN` file (safety keyword gone) is in the sampled
  review.
- [ ] Scope: `git status --porcelain --untracked-files=all -- dummyindex tests`
  lists only modified (` M`) `.py` files, none under any `fixtures/`
  directory. Each changed file belongs to exactly one unit.
- [ ] License lines intact: `git diff -U0 0634bfd -- dummyindex tests | grep '^-' | grep -E 'Apache|Licen[cs]e|NOTICE|©|MIT|[Pp]orted from|[Dd]erived from'`
  prints no attribution line. *Amended during build:* that broad pattern also
  matches descriptive prose ("members derived from `map/symbols.json`", "never
  derived from an environment variable", and "imported from" via the substring
  "ported from"). All 13 matches were inspected and none is attribution. The
  files that lost every "headroom" mention (`miner/scope.py`, the canary test,
  `behavior_arms.py`, `test_behavior_arms.py`) only compared designs or pointed
  at a proposal; they had no credit line. The Apache notice
  (`memory/miner/__init__.py`, `signatures.py`, `resolve.py`) and the root
  `NOTICE` are intact. The MIT holder lines are byte-identical.
- [ ] `ruff check dummyindex tests` passes. `ruff format --check` passes on
  every changed file except the 7 that were already not format-clean at base;
  those are listed in the plan and never formatted.
- [ ] `python -m pytest tests/ -q --tb=short -p no:cacheprovider --basetemp=C:/ptrim`
  ends with exactly `3562 passed, 168 skipped`, with 0 failed and 0 errors.
  It runs only after all 12 units have stopped.
- [ ] Reduction:
  - `comment_scan.py --doc-min 9` combined lines are at most 2,824 for
    `dummyindex/` and at most 740 for `tests/` (a 60% cut).
  - Total comment + docstring bytes drop at least 25% per tree (at most 564,361
    and 320,283).
  - Every `--all` row left after the trim has a matching row in
    `.context/proposals/trim-long-comments/exceptions.md` (0 unlisted). That
    file is written by the orchestrator from the unit reports.
- [ ] Sampled quality review, by a reviewer who didn't edit the files. It
  covers the 2 files per unit with the most removed comment lines (24 files)
  plus every `WARN` file, and answers yes or no for each:
  1. Summary line kept?
  2. Returns/raises/invariants kept?
  3. Every safety note survives?
  4. No new claim that the code contradicts?
  Any "no" reopens that unit. Verdicts go in
  `.context/proposals/trim-long-comments/review.md`.

## Open questions

None. The user chose the scope (`dummyindex/` + `tests/`) and asked for this to
run in parallel with the 8-feature recouncil.

Accepted drift: line citations shift in the `.context/features/*` docs and in
`conventions/{testing,coding-practices,data-access}.md`. To keep the council
from demoting features over shrunken files, council Phase 3.5 (`reality-check`)
and the reconcile stamp wait until this trim is committed. After that,
`rebuild --changed` refreshes the deterministic backbone.

<!-- dummyindex:consistency:begin -->
## Consistency

**Related features:**

- `equip`
- `index-lifecycle`
- `tree-enrich`

**Conventions to honor:**

- `conventions/coding-practices.md`
- `conventions/data-access.md`
- `conventions/folder-organization.md`
- `conventions/naming.md`
- `conventions/testing.md`

<!-- dummyindex:consistency:end -->
