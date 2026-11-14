# Spec — Split dummyindex into shared, context and evolve layers with a one-way import boundary

## Intent

The self-evolve code and the context code live together in `dummyindex/context/domains/`.
They import each other in both directions: 15 context→evolve edges exist today.
This makes each part hard to change, test or ship alone.

This contract splits the package into three layers with a one-way import rule.
A later move task executes it. This proposal changes no source code.

Readers: the agents that do the move waves, and the Manager that orders them.

## Layers

| Layer | Path | Contents |
|---|---|---|
| shared | `dummyindex/shared/` | Primitives that both layers use: atomic writes, error type, path guard, project lock, lesson contract. |
| evolve | `dummyindex/evolve/` | Self-evolve loop, evidence, living rules, observe, probation, evolve CLI verbs. |
| context | every other module under `dummyindex/` | Create, manage and update `.context/`: pipeline, build, output, equip, gc, proposals, council, features, memory, installer, CLI. |

"Context layer" is wider than the `dummyindex/context/` package. It also holds `pipeline/`, `analysis/`, `export/`, `usage/`, `installer/` and `cli/`.
The old rules between those packages stay in `conventions/folder-organization.md`. The new test does not check them.

Decision: context modules do not move. Only evolve and shared code moves. This keeps the move small (KISS).

Decision: `memory/miner` stays in context. It writes `.context/session-memory/` and feeds the memory CLI.
Evolve reads it through public names. That direction is allowed.

Decision: the evolve CLI verbs move to `dummyindex/evolve/cli/`.
This is the one exception to "CLI subcommand → `cli/<sub>.py`". The docs task records it.

Counts (AST scan, current tree, 397 source + 261 test modules):

| Layer | Source modules | Test modules |
|---|---|---|
| context | 364 (includes the root `dummyindex/cli/__init__.py`) | 246 |
| evolve | 29 | 13 |
| shared | 4 moved + 4 new (`shared/__init__.py`, `errors.py`, `guard.py`, `lesson/rules.py`) | 2 |

The full per-module table is in `boundary-map.md` (sections A1–A3). A script generated it. Do not edit it by hand.

The scan scripts are in `D:\temp\` as the mission brief requires:
- `split_scan.py` (edges)
- `split_contract.py` (tables)
- `split_waves.py` (file sets per item)
- `split_privattr.py` (private attribute reads)

The Wave 2 boundary test replaces them as the durable scanner.

## Contracts

### C1 — Import direction

- shared imports only shared and the standard library.
- context imports context and shared. It never imports evolve.
- evolve imports evolve, shared and the public names of context.
- One exception: the composition root `dummyindex/cli/__init__.py` may import exactly these 3 evolve modules.
  It imports each one lazily inside a function: `dummyindex.evolve.cli.evolve` (`run`), `dummyindex.evolve.evolve_learning` (`learn_after_closeout`), `dummyindex.evolve.probation` (`session_block`).
- Reason for lazy: `evolve/cli/evolve.py` imports `dummyindex.cli.common`. That runs `dummyindex/cli/__init__.py`.
  A module-level import of evolve there makes an import cycle when evolve loads first.

### C2 — Public names across layers

A cross-layer import must not name a symbol that starts with `_`.
A cross-layer module alias must not read an attribute that starts with `_` (`storage._decode`).
These names cross today. Each gets a public name. Rename the definition and every use. Do not keep an alias.

| Today | New public name | Wave |
|---|---|---|
| `atomic_io._replace_bytes` (used by `build/upgrade.py`, `proposals/closeout.py`, test monkeypatches) | `replace_bytes` | 2 |
| `equip/lifecycle/status._bump` (used in `status.py`, `equip/lifecycle/evolve.py`, `evolve_gate.py`) | `bump` | 2 |
| `memory/miner/scan._human_prompt_text` (used in `scan.py`, `observe/importer.py`) | `human_prompt_text` | 3 |
| `export/storage._decode`, `_FORMAT`, `_read_manifest`, `_HASH_RE` (read by `evolve_native_snapshot.py:53-55,80`) | `decode`, `FORMAT`, `read_manifest`, `HASH_RE` | 3 |

Tests are not scanned. They may keep private imports, but their paths move (C3.11).

### C3 — Move rules

1. Move-only. Do not change behavior. Do not add features. Do not reformat moved code.
   Import-sort changes that `ruff check .` requires are allowed.
2. No compatibility shims. Do not leave a re-export at the old path. Update every importer.
3. Keep file names. `evolve_gate.py` stays `evolve_gate.py` under `dummyindex/evolve/`.
   Reason: `evolve_gate.py` and `evolve_native_snapshot.py` read sibling files by name through `Path(__file__).with_name(...)`.
4. Fix the one sibling read that the move breaks, and keep digest coverage.
   - `evolve_native_snapshot._controller` reads `atomic_io.py` as a sibling. Read `Path(atomic_io.__file__)` instead. Keep the key `"atomic_io.py"`.
   - `safe_file` and `project_lock` leave the hashed files. Add `"guard.py": Path(guard.__file__)` to `_controller`.
     Fold `guard.py` bytes into `gate_code_sha256` in `evolve_gate`. The receipt keeps its fields.
5. Code digests change: `gate_code_sha256`, `promotion_code_sha256` and the snapshot `controller` hash all hash file bytes.
   No test pins these values. Finish or discard open evolve runs before the split lands.
6. `pyproject.toml`: no change. `include = ["dummyindex*"]` finds the new packages. `[project.scripts]` points at `dummyindex.__main__:main`.
   Each new package needs an `__init__.py`. `package-data` stays the same.
7. `dummyindex/skills/` does not move. `dummyindex/context/schemas/` does not move.
8. CLI surface does not change. `ContextSubcommand.EVOLVE` stays in `dummyindex/context/enums.py`.
   The root maps it to a lazy adapter that calls `dummyindex.evolve.cli.evolve.run`.
9. Hook and installer strings do not change. They name CLI commands and skills, not module paths:
   `context/hooks.py:217` (`dummyindex context evolve evidence`), `installer/common.py:89`, `installer/legacy_fingerprints.py:181`.
10. Generators do not change. `dummyindex/context/output/instructions.py` and `docs/COMMANDS.md` name no moved module path.
11. String targets and private paths in tests move with the code:
    - `tests/context/domains/memory/test_memory_cli.py:112` and `tests/context/domains/test_evolve_gate.py:111` (`monkeypatch.setattr` strings).
    - `tests/context/domains/test_closeout.py:512,522,547,557,564` (`module._replace_bytes` → `module.replace_bytes`).
    - `tests/cli/test_closeout_exit_codes.py:16` (`evolve_learning._path` import path).
12. Tests mirror the source move. 15 test files move to `tests/evolve/` or `tests/shared/` (see `boundary-map.md` A3).
    New test folders get an `__init__.py`, like the existing ones.
13. Comments that name an old path get the new path: `pipeline/io/cache.py:147`, `context/domains/log_scan.py:3`.
    `pipeline/io/cache.py` keeps its own `_write_bytes_atomic`. Removing that duplicate is a later change.
14. `.context/` is not edited by hand. The `/dummyindex-build` close-out (rebuild, reconcile, re-anchor) refreshes
    features, maps and conventions after the last wave.

### C4 — Seams (the only edits that are not moves or renames)

Two context→evolve calls cannot move to shared. The composition root wires them.

**S1 — closeout learning.**
- Move `_learn_after_closeout`, `_SETTLED` and `_no_mark` from `proposals/closeout.py` to `dummyindex/evolve/evolve_learning.py`.
  The public name is `learn_after_closeout(context_dir, workspace, kind, manifest, receipt, learner=None)`.
- `closeout_workspace` and `closeout_from_file` take `after_closeout: Callable[[Path, Path, str, dict, dict], None] | None = None`.
  It replaces the `learner` parameter. When it is `None`, no learning runs.
- `cli/gc.py` `run(args, *, after_closeout=None)` and the `cli/build_loop` run entry pass it through to `closeout_from_file`
  (`gc.py:109` and `build_loop/dispatch.py:181` are the only callers).
- `dummyindex/cli/__init__.py` registers `functools.partial(gc.run, after_closeout=_closeout_learning)` and the same for the build entry.
- `_closeout_learning` imports `learn_after_closeout` lazily inside `try`. On any exception it sets
  `receipt["learning"] = {"status": "failed", "error": "<Type>: <message>"}`. This keeps today's failure path: closeout exits 1, no traceback.
- `learning_exit_code`, `learning_line` and `failed_record_path` stay in `closeout.py`. They use only `LearningStatus` (shared).
- Tests that pass `learner=` today pass `after_closeout=functools.partial(learn_after_closeout, learner=...)`.

**S2 — probation block at session start.**
- `cli/memory.py` `run(args, *, session_block=None)`. `_print_probation` does nothing when `session_block` is `None`.
  The `try/except` around the call stays.
- `dummyindex/cli/__init__.py` registers `functools.partial(memory.run, session_block=_probation_block)`.
  `_probation_block` imports `dummyindex.evolve.probation.session_block` lazily, so `monkeypatch` targets still apply.

### C5 — Boundary test (`tests/test_import_boundaries.py`)

Standard library only (`ast`, `pathlib`, `subprocess`). No grep, no regex on source. About 200 lines.

Scanner:
- Walk every `dummyindex/**/*.py`. Layer by `Path.parts`: `("dummyindex", "shared", ...)` → shared, `("dummyindex", "evolve", ...)` → evolve, other → context.
- Collect every import form: `import x`, `from x import y`, relative imports (package level in `__init__.py`),
  imports inside functions, imports under `if TYPE_CHECKING:`, and `importlib.import_module("<literal>")`.
- Resolve `from pkg import name` to `pkg.name` when that module exists.
- Record module aliases. Collect `alias._x` attribute reads on cross-layer modules.

Rules (each failure prints `path:line -> module (names)`):

| Rule | Fails when |
|---|---|
| R1 direction | shared→context, shared→evolve, or context→evolve outside the 3 root pairs (C1) |
| R2 root pairs | a root pair is not lazy, or an allowlisted pair no longer exists (stale entry) |
| R3 private names | a cross-layer import names `_x`, or a cross-layer alias reads `_x` (C2) |
| R4 moved symbols | an import takes one of 4 moved symbols from its old home: `evolve_gate.EvolveError`, `evolve_gate.safe_file`, `evolve_promotion.project_lock`, `living_rules.rules_in` (whole-module moves are R5) |
| R5 old paths | an import names an old qualified path from `boundary-map.md` A1 (match `module` and `module.name`, no file check), or an old file exists again |
| R6 resolution | a `dummyindex.*` import base resolves to no module or package |
| R7 dynamic imports | a non-literal `import_module`/`__import__` exists outside `dummyindex/__init__.py:30` and `pipeline/extract/generic.py:25` |

We ran R6 and R7 on the proposal tree (`D:\temp\split_r6r7.py`). R6 finds 0 unresolved bases. R7 finds only the 2 allowlisted sites.

Self-checks (`@pytest.mark.unit`):
- Parametrized `tmp_path` trees, one per forbidden form. Each asserts the exact message. The forms:
  - `TYPE_CHECKING`, literal `import_module`, `from dummyindex.evolve import probation`.
  - A relative import in an `__init__.py`, shared→context, shared→evolve.
  - A cross-layer `_name`, a cross-layer `alias._x`.
  - A moved symbol from its old home, an old-path import.
- One allowed tree (context→shared, evolve→context public name, lazy root pair) reports 0 violations.
- Real-tree sanity: files scanned equal the `rglob` count. At least 1 real edge exists for context→shared, evolve→shared, evolve→context and root→evolve.

Fresh-interpreter check (`@pytest.mark.integration`): `subprocess.run([sys.executable, "-c", "import <m>"])` exits 0 for
`dummyindex.shared`, `dummyindex.shared.guard`, `dummyindex.shared.atomic_io`, `dummyindex.shared.lesson`, `dummyindex.evolve`,
`dummyindex.evolve.cli.evolve`, `dummyindex.evolve.cli.evolve_probation`. `python -m dummyindex --help` exits 0.

Staging: Wave 2 lands the scanner, R1 for shared, R4–R7, the self-checks and the sanity check.
Wave 3 adds the context→evolve part of R1, R2, R3, the evolve entries of R5 and the fresh-interpreter check.

## Cross-boundary imports

Full table: `boundary-map.md` section B (110 rows, both directions, each with a fix). Summary:

| Direction (today) | Edges | Fix |
|---|---|---|
| context→evolve | 15 | 12 move into shared (`EvolveError`, `safe_file`, `project_lock`, `lesson`); 2 seam (S1, S2); 1 root pair (made lazy) |
| evolve→context | 29 | 10 move into shared (`atomic_io`); 17 keep (public names); 2 promote private name (C2) |
| context→context that becomes context→shared | 41 | move into shared (`atomic_io`) |
| evolve→evolve that becomes evolve→shared | 25 | move into shared (`EvolveError`, guard symbols, `lesson`, `rules_in`) |

Plus 4 private attribute reads (evolve→context, `export.storage`), fixed by C2.
No edge needs deletion. After the split: 53 context→shared, 35 evolve→shared, 19 evolve→context, 3 lazy root→evolve, 0 forbidden.

Shared candidates from the brief, and the decision:

| Candidate | Decision | Reason |
|---|---|---|
| `EvolveError` | → `shared/errors.py` | Context catches it from the guard and lock. Name kept (move-only). |
| `safe_file` | → `shared/guard.py` | Used by `project_lock` and closeout. |
| `project_lock` | → `shared/guard.py` | buildloop, gc delete and closeout take the project writer lock. Its lock-name set stays as is. |
| `atomic_io` | → `shared/atomic_io.py` | 49 source importers across both layers. |
| `LearningStatus` | → `shared/lesson/enums.py` (whole `lesson` package) | Closeout and equip library validate lessons. |
| `rules_in` | → `shared/lesson/rules.py` (with `_BLOCK`) | `lesson.models.lesson_to_delta` needs it. One symbol move keeps `lesson` whole. |
| `sha256` (`living_rules.sha256`) | stays in evolve | No context importer. YAGNI. |

Considered and left: moving `lesson_to_delta`, `LessonDelta` and `DeltaOp` to evolve instead of `rules_in` to shared.
That splits two `lesson` files for three symbols. The chosen move splits one file for one function.

## Conflict with the equip-bugs task

The equip-bugs task edits: every `atomic_io` importer, `context/hooks.py`, `context/enums.py`, `cli/__init__.py`,
`context/domains/gc/*`, `context/domains/config.py`, `equip/*`.
Wave 2 touches 59 of these files. Wave 3 touches 12. So waves 2–3 start only after equip-bugs merges.
No equip-bugs branch exists in this repo yet, so the Wave 1 gate checks the merge by commit.

Each conflict file has one owner task:

| Files | Owner until equip-bugs merges | Split item that edits it after merge |
|---|---|---|
| `context/domains/atomic_io.py` and its importers (49 source, 7 test) | equip-bugs | Wave 2 (evolve-side importers move again in Wave 3, serially) |
| `context/domains/gc/{delete,anchor}.py`, `tests/context/domains/gc/test_delete.py` | equip-bugs | Wave 2 |
| `context/domains/equip/lifecycle/{library,status,evolve}.py`, `equip/generate/adapters.py`, `cli/equip/{dispatch,install}.py`, 4 equip tests | equip-bugs | Wave 2 |
| `cli/__init__.py`, `cli/gc.py` | equip-bugs | Wave 3 |
| `context/hooks.py`, `context/enums.py`, `context/domains/config.py` | equip-bugs | none: the split does not edit them |
| Equip API consumers: `evolve_gate.py`, `evolve_native*.py` | equip-bugs, only if its API change needs it | Wave 2 then Wave 3 |
| Split-only: `cli/build_loop/dispatch.py`, `cli/memory.py`, `export/storage.py`, `memory/miner/scan.py`, `docs/reference/01-conventions.md` | split | Wave 3 |

## Acceptance

- [ ] `python -m pytest tests/test_import_boundaries.py -q` passes on the split tree. Every R1–R7 self-check reports its planted edge.
- [ ] `python -m pytest tests/ -q --tb=short` passes (the CI command), and `ruff check .` passes.
- [ ] `closeout_from_file(..., after_closeout=None)` writes no learning event. A recording hook is called once with `(context_dir, workspace, kind, manifest, receipt)`.
- [ ] `dispatch` of `gc closeout` and of the build closeout both write the learning event, as today.
- [ ] `memory.run(args, session_block=None)` prints no probation block. `dispatch` of the memory session-start verb prints the block from a monkeypatched `session_block`.
- [ ] `git diff <GATE_SHA> HEAD -- pyproject.toml docs/COMMANDS.md dummyindex/skills dummyindex/context/hooks.py dummyindex/context/enums.py` is empty.

## Open questions

- The brief lists `cli/__init__.py` as a coupling to fix. This contract keeps it as the composition root with 3 lazy pairs (C1).
  The Manager confirms or rejects this before Wave 3.
- `EvolveError` keeps its name in `shared/errors.py`. A rename to a neutral name is a later, separate change.

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
