# Plan — Trim long code comments repo-wide (dummyindex/ + tests/) to the non-obvious why, no behavior change

Base commit: `0634bfd`. Tools live in the session scratchpad
`C:/Users/ahmed/AppData/Local/Temp/claude/ff57deaa33662588/dcba02dd-20b1-4a32-aba0-0e5715cad86f/scratchpad/` (`SP` below):

- `SP/ast_equiv.py [paths…]` — docstring-stripped AST equality versus base,
  plus per-file marker counts (directives, license/attribution, rationale
  prefixes). Run it from the repo root. A safety keyword that disappears from a
  file prints `WARN`, report-only.
- `SP/comment_scan.py <tree> --doc-min 9 [--all]` — long-item lines and total
  comment/docstring bytes.

Interpreter: `.venv/Scripts/python.exe` (3.12). CLI: `.venv/Scripts/dummyindex.exe`.

**Never `ruff format` these 7 files.** They were not format-clean at base, so
formatting would add code reflow to the diff:
- `dummyindex/cli/drift_ack.py`
- `dummyindex/context/domains/buildloop/__init__.py`
- `dummyindex/context/domains/drift_acks.py`
- `tests/cli/test_bootstrap_migration.py`
- `tests/cli/test_rebuild_migration.py`
- `tests/context/domains/test_fleet.py`
- `tests/context/test_drift.py`

## Tasks

Units 1–12 partition all 548 non-fixture `.py` files into disjoint sets; the
reuse critic verified there are no gaps or overlaps. Each unit:

- applies the spec's edit rules and keep-list to its own files only;
- runs `ruff format <explicit .py paths>` (never a directory, never the 7 files
  above);
- runs `ruff check <its paths>`;
- runs `SP/ast_equiv.py <its changed paths>` (0 problems), with paths taken from
  `git diff --name-only 0634bfd -- <its dirs>`;
- returns its changed files, the lines and bytes removed, every `WARN`, and its
  exceptions as `kind | path:line | lines | reason`.

**No per-unit pytest.** Other units are editing modules at the same time, and
the evolve fingerprint tests re-hash live source. The suite runs once, in task
14, after every unit has stopped.

1. **U1** `dummyindex/context/domains/{features,debt,preflight,doc_reorg}/`.
2. **U2** `dummyindex/context/domains/{equip,proposals,graph_query}/`.
3. **U3** files directly in `dummyindex/context/domains/` and `{source_docs,audit}/`.
4. **U4** `dummyindex/context/domains/{buildloop,memory,gc}/`. Keep-list: the `memory/miner/` Apache attribution, verbatim.
5. **U5** `dummyindex/context/domains/{reality_check,docguard}/`, `dummyindex/context/output/`, `dummyindex/usage/`, `dummyindex/analysis/`, `dummyindex/export/`. Keep-list: the `reality_check/__init__.py` contract, the `cluster.py` Louvain contract, and `styles.py` (string, untouchable).
6. **U6** `dummyindex/cli/**`. Keep-list: the `onboard.py` keywords and the `statusline.py` badge semantics.
7. **U7** `dummyindex/context/build/**`. The vendored v0.36 renderer's string literals in `upgrade.py` stay byte-identical.
8. **U8** files directly in `dummyindex/`, files directly in `dummyindex/context/`, `dummyindex/context/schemas/`, `dummyindex/skills/**/*.py`. Keep-list: the `drift.py` `compute_badge` semantics.
9. **U9** `dummyindex/installer/**`.
10. **U10** `dummyindex/pipeline/**`.
11. **U11** `tests/eval/**` and files directly in `tests/`. Keep-list: MIT attribution with holder, verbatim; `test_retrieval_eval.py:1-26` and `:40-47`; `tests/paths.py:1-14`.
12. **U12** `tests/{cli,context,pipeline,analysis,export,usage}/**`. Keep-list: the canary's SCOPE and COUPLING HOLE text plus its MIT line verbatim; `tests/pipeline/io/test_git.py:1-9`.
13. **Acceptance — proof + scope + license** (main session): `SP/ast_equiv.py` (no paths), the `git status --porcelain` scope check, and the license-line grep. All three are spec acceptance bullets 1–3.
14. **Acceptance — suite + lint** (main session, after all units stop): `ruff check dummyindex tests`, `ruff format --check` on changed files (minus the 7), then the full pytest run with `--basetemp=C:/ptrim -p no:cacheprovider`. It must end with exactly `3562 passed, 168 skipped`.
15. **Acceptance — reduction** (main session): write `exceptions.md` from the unit reports, run `comment_scan.py --doc-min 9 --all` on both trees, and check the line and byte targets plus 0 unlisted rows.
16. **Acceptance — sampled review**: one fresh reviewer reads `git diff 0634bfd -- <file>` for the 24 sampled files plus the `WARN` files, answers the 4 questions, and writes `review.md`. Any "no" reopens that unit.

**After acceptance (close-out, not checklist work):**
1. Commit the trim (`chore: trim long comments and docstrings`; the body states it is comment-only, proven by `ast_equiv`).
2. Run council Phase 3.5 `reality-check --demote` for the 8 recouncilled features.
3. Run `rebuild --changed`.
4. Run the reconcile stamp.
5. Make one `.context` commit.

## Reuse

No new production code. The checks reuse `python_rationale._RATIONALE_PREFIXES`
(`dummyindex/pipeline/extract/python_rationale.py:19-23`) as the
rationale-marker vocabulary. There is no AST-equivalence or comment-scan tool
in the repo to reuse.

## Risks

- **Parallel council:** its critics and stage-5 tree agents read source while
  units edit it. Code doesn't change, only line numbers. The reality check and
  the stamp wait for the trim commit.
- **Self-hashing files:** see the spec. Covered by running the suite only after
  all edits stop.
- **Shared test infrastructure:** U11 edits `tests/conftest.py` and
  `tests/paths.py`. A half-written file only matters if pytest runs mid-wave,
  and it doesn't.
