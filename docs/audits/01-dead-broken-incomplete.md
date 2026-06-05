# Audit: dead / broken / incomplete paths, flows & features

**Date:** 2026-06-05 · **Scope:** `dummyindex/` (19.5K LOC) · **Method:** deterministic tooling (ruff, mypy, pytest+coverage, vulture) → triage with a dynamic-dispatch/public-surface filter → targeted semantic verification (incl. empirically running extractors).

Excluded: `build/` (stale build artifact — `build/lib/dummyindex/runtime/` has no source counterpart), `.venv/`, `dummyindex.egg-info/`.

## Headline

The codebase is **mature and clean**: ruff's dead-code detectors (F401/F811/F841) find **zero** unused imports, redefinitions, or unused variables; there are no `TODO`/`FIXME`/`NotImplementedError` markers; the full suite passes (545 tests, deterministic under sequential runs). The real findings are a small number of genuine defects plus some vestigial surface — listed below, **ranked by runtime impact**.

> **Resolution (2026-06-06):** Finding **#1** resolved by **removing** the Objective-C extractor entirely (`languages/objc.py` deleted; `.m`/`.mm` dropped from dispatch/detection/`build/maps.py`; `tree-sitter-objc` dependency removed) rather than fixing it. Finding **#2** resolved by **wiring** the three skill-unwired commands into the shipped flow: `query` is now the optional fast-path shortlist in `retrieval/00-overview.md`, `10-feature-lookup.md`, and the generated `HOW_TO_USE.md`; `enrich-plan`/`enrich-apply` are now **Phase 4.5 — Tree enrichment** in `skill.md` with the procedure in `council/52-tree-enrich.md`. The full `enrich-plan → enrich-apply → query` sequence was validated end-to-end on `sample_repo`. Suite: 548 passing.

---

---

## Re-audit (2026-06-06) — delta since the changes above

Re-ran the full deterministic baseline (ruff F/B, mypy, pytest+cov, vulture) on the current tree. **Suite: 548 passing, 70% coverage.** Summary of what moved:

**Resolved since the first pass:** objc broken extractor (#1) removed wholesale; `_get_name` gone with it; `enrich-plan`/`enrich-apply`/`query` (#2) wired into the skill. The changes introduced **nothing broken** — the only shifted signal is `instructions.py:316` (was `:315`), a pre-existing call-overload moved down one line by the `query` edit.

**NEW finding — dead `LanguageConfig` fields (low severity, audit #1 missed it):**
- **`dummyindex/pipeline/extract/config.py:49` `function_label_parens`** and **`:52` `extra_walk_fn`** are dead config knobs. `_generic.py` reads 18 other `config.*` attributes but **never these two**; a whole-package grep finds only their definitions; and **no language config ever sets them** (they only ever hold defaults). Their docstrings claim behavior the code doesn't honor:
  - `function_label_parens` ("if True, functions get `name()` label"): the paren label is **hardcoded** at `_generic.py:308` (`add_node(func_nid, f"{func_name}()", line)`) with no `if config.function_label_parens` guard — the toggle was never wired, so a language *cannot* turn parens off. Dead knob; behavior hardcoded-on.
  - `extra_walk_fn` ("extra walk hook called after generic dispatch"): never invoked, so the post-dispatch hook never fires.

  Safe to delete both (and tighten the docstrings), or wire them if the behavior was intended. Audit #1's agents covered `_resolve/_imports/_helpers/validate/references` but not `config.py`'s consumption, so this slipped through.

**Still open (unchanged, not fixed):** the dead `pipeline/enums.py` enums (#3), `_common.py:21 _resolve_name` (#3), `references.py:228` missing `return` (#4), `collect_files._EXTENSIONS` still missing `.dart/.jl/.ex/.exs/.v/.sv/.vue/.svelte` (#4), `_print_help()` 7-of-23 doc drift (#5), `_cache_dir_override` parallel-unsafe `os.environ` (#6), no ruff/mypy CI gate (#7).

**Re-confirmed false positives (do not chase):** the 11 `B023` closures in `_resolve.py` (`walk`/`walk_imports` are defined *and invoked synchronously within the same loop iteration* — lines 144, 229 — so they see the correct loop value); vulture's `RESTORE` (`doc_reorg.py:33` `DocReorgAction(args[0])` → dispatched at `:92`) and `ROLL` (`memory.py:36` `MemoryVerb(verb_str)` → dispatched at `:66`), both reached via enum-from-string; and the previously-cleared `rebuild.py` IncrementalResult attrs, `julia.py:212-213`, and guarded CLI `arg-type`s.

---

## 1. BROKEN — Objective-C call extraction emits zero `calls` edges (isolated)

- **`dummyindex/pipeline/extract/languages/objc.py:178-206`** — the second-pass call-resolution closure only matches `child.type in ("selector", "keyword_argument_list")`, but the installed `tree_sitter_objc` grammar represents message-send selectors as bare `identifier` children for **both** simple (`[self world]`) and compound (`[self runWith:a]`) sends. **Verified empirically:** `extract_objc` on real samples produces **0 `calls` edges**. The call graph for any Objective-C code is silently empty.
- **Calibration:** the same empirical test on **rust → 1 calls edge**, **go → 1 calls edge + imports_from**, **julia → correct call edges**. So this is an **isolated objc defect, not a systemic grammar-mismatch pattern**. (The 15 ruff `B023` warnings on these lines are a *false positive* — the closure is invoked synchronously within the loop iteration, so it sees the correct loop value. The bug is the node-type assumption, not the closure binding.)
- **`objc.py:43-47,168`** — secondary: `add_edge` has no dedup (unlike `add_node`), so a method both *declared* in `@interface` and *defined* in `@implementation` emits its `method` edge twice. Low severity; verified empirically.

**Not-broken (mypy false positives, verified guarded):** `objc.py:118,138` (`name=None` then `if not name:`/`if name:`), `julia.py:212-213` (`object` is a tree-sitter Node at runtime), `_generic.py:595`, `extract/__init__.py:163`.

## 2. INCOMPLETE FEATURE / DEAD FLOW — `enrich-plan`, `enrich-apply`, `query` are skill-unwired

- **`dummyindex/cli/enrich.py`, `dummyindex/cli/query.py`** + the `dummyindex/context/domains/enrich.py` and `…/query.py` domains. These three `context` subcommands are fully implemented, tested, and documented in `cli/_usage.py`, **but invoked by nothing in the shipped flow** — no `skills/**.md`, no `context/hooks.py`, no internal pipeline step references `dummyindex context enrich-plan|enrich-apply|query`. The `enrich` domain's `build_plan`/`apply_updates` are called *only* by their own CLI handler. The skill enriches via the council `section-write` path instead; retrieval docs describe manual tree navigation, never the `query` CLI.
- **Impact:** a whole "LLM enrichment write-back" flow and a retrieval `query` flow exist as working CLI surface that the product's own skill never uses. **Decision needed: wire them into the skill, or remove them.** (Contrast: `plan-update` and `memory` *look* skill-orphaned but are reachable — `context/hooks.py:44,54` shells out to them from the SessionStart hook.)

## 3. DEAD CODE — confirmed, zero references (safe to delete)

- **`dummyindex/pipeline/enums.py`** — dead *parallel* definitions; the real values flow through the code as raw strings, and these enums are never imported:
  - `NodeKind` (class + `FOLDER/FILE/CLASS/FUNCTION/METHOD/GLOBAL`) — node kinds are emitted as literals in `pipeline/build/structure.py` (`"file"`, `"folder"`, `"method"`…).
  - `EdgeRelation` (class + `INHERITS/IMPORTS/IMPORTS_FROM/CALLS/BOUND_TO/…`) — edges emitted as literals (`"calls"`, `"imports"`…).
  - `ConfidenceLevel.PINNED`, `INFERABLE_LEVELS`, and the `enums.py` copy of `HIERARCHY_RELATIONS` (shadowed by the live one at `structure.py:49`).
- **`dummyindex/pipeline/extract/languages/objc.py:55` `_get_name`** — 1 grep hit (the def), 0 callers.
- **`dummyindex/pipeline/extract/_common.py:21` `_resolve_name`** — 0 callers; its docstring (`_common.py:3`) falsely claims it is "used by every language extractor" (`_generic.py` uses `config.resolve_function_name_fn` directly).

**Not-dead (vulture false positives, verified live):** `council.py` `is_stage_complete`/`latest_status` (skill-driven resume API — `skills/council/19-resume.md`, 8 test assertions); all flagged `config.py` enum members (constructed via `enum_cls(raw)` validation at `config.py:157`); `usage/models.py`/`graph.py` `*_count`/`models` (frozen-dataclass fields); `__init__.py:12 __getattr__` (lazy-import hook).

## 4. INCOMPLETE — minor, type-unsound or by-design

- **`dummyindex/pipeline/build/references.py:228` `_pattern_hits`** — declared `-> bool` but the slashed-pattern branch falls off the end returning implicit `None` (no trailing `return False`). **Masked at runtime** (sole caller uses it in a boolean `if`), but the contract is violated. Add `return False`.
- **`dummyindex/pipeline/extract/__init__.py:258` `collect_files._EXTENSIONS`** — missing `.dart .jl .ex .exs .v .sv .vue .svelte`, so this `__all__`-exported helper silently skips those languages. **Not on the production build path** (production uses `detect.py`'s complete `CODE_EXTENSIONS`), so secondary.
- **`dummyindex/cli/config.py:4-5,23-24` `config get`/`set`** — deliberately rejected with a clear error, documented "reserved for a future release" in `_usage.py:130`. Incomplete *by design*, not a defect.

## 5. DOC DRIFT — `--help` under-documents the CLI

- **`dummyindex/__main__.py:514-534` `_print_help()`** lists only **7 of 23** `context` subcommands. 10 user-facing ones are wired + working but invisible in `dummyindex --help`: `check, hooks, query, reality-check, plan-update, onboard, config, preflight, doc-reorg, memory`. (`cli/_usage.py` — the `dummyindex context --help` surface — *is* complete and its documented flags all exist.) No command is documented-but-unwired.

## 6. TEST FRAGILITY — parallel-unsafe cache-dir env state (latent)

- **`dummyindex/context/build/runner.py:399-411` `_cache_dir_override`** mutates **process-global `os.environ["DUMMYINDEX_CACHE_DIR"]`** (correctly save/restore for *sequential* use). Combined with the **content-addressable, path-independent** cache key and a non-unique `{hash}.tmp` temp name (`pipeline/io/cache.py:20-40,95`), concurrent/parallel builds in one process (e.g. `pytest -n auto`) would race on shared cache files.
- **Observed:** `test_rebuild_preserves_memory_content` failed **once** under `--cov`, and the passed-count wobbled (542/543/545) — both occurred only while two pytest loops ran concurrently. Under clean **sequential** execution it is **0/25+ failures**, fully deterministic. So: report as **latent parallel-safety fragility**, not a confirmed sequential bug. (The memory-preservation logic itself, `memory/store.py:38`, is provably non-destructive.)

## 7. STYLE (not dead/broken — noted because CI has no lint gate)

CI runs only pytest (`.github/workflows/tests.yml`); there is **no ruff/mypy gate**, so style/type drift accumulates silently: ruff reports 334 `E501`, 126 `UP045` (use `X | None`), 18 `UP035` (deprecated `typing` imports), 5 `RUF022` (unsorted `__all__`), plus the false-positive `B023`s. None are dead/broken. Consider adding a ruff+mypy CI step to stop the accumulation.

---

## Recommended order of action
1. Fix the **objc call extractor** (`objc.py:178-206`) + add `add_edge` dedup — the only user-visible correctness defect.
2. Decide **enrich-plan / enrich-apply / query**: wire into the skill or remove (largest dead-flow surface).
3. Delete the **dead enums** + `_get_name` + `_resolve_name` (pure cleanup, zero risk).
4. Add `return False` at `references.py:254`; backfill `collect_files._EXTENSIONS`.
5. Sync `_print_help()` with `_usage.py`.
6. Make `_cache_dir_override` parallel-safe (or document that the suite must run single-process) **before** adopting `pytest-xdist`.
7. Add a ruff+mypy CI gate.
