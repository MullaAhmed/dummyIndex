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
| shared | `dummyindex/shared/` | Primitives that both layers use: atomic writes, path guard, project lock, lesson contract. |
| evolve | `dummyindex/evolve/` | Self-evolve loop, evidence, living rules, observe, probation, evolve CLI verbs. |
| context | every other module under `dummyindex/` | Create, manage and update `.context/`: pipeline, build, output, equip, gc, proposals, council, features, memory, installer, CLI. |

Decision: context modules do not move. `dummyindex/context/` already holds them.
Only evolve and shared code moves. This keeps the move small (KISS).

Decision: `memory/miner` stays in context. It writes `.context/session-memory/` and feeds the memory CLI.
Evolve reads it through public names. That direction is allowed.

Counts (AST scan, current tree, 397 source + 261 test modules):

| Layer | Source modules | Test modules |
|---|---|---|
| context | 364 (includes `dummyindex/cli/__init__.py`) | 246 |
| evolve | 29 | 13 |
| shared | 4 moved + 3 new (`shared/__init__.py`, `shared/guard.py`, `shared/lesson/rules.py`) | 2 |

The full per-module table is in `boundary-map.md` (sections A1–A3). A script generated it. Do not edit it by hand.

## Contracts

### C1 — Import direction

- shared imports only shared and the standard library.
- context imports context and shared. It never imports evolve.
- evolve imports evolve, shared and the public names of context.
- One exception: `dummyindex/cli/__init__.py` is the composition root. It may import evolve.
  No other module gets this exception.

### C2 — Public names across layers

A cross-layer import must not name a symbol that starts with `_`.
Three names cross today. Each gets a public name in the wave that moves its file:

| Today | New public name | Wave |
|---|---|---|
| `atomic_io._replace_bytes` (used by `build/upgrade.py`, `proposals/closeout.py`) | `replace_bytes` | 2 |
| `equip/lifecycle/status._bump` (used by `evolve_gate.py`) | `bump` | 2 |
| `memory/miner/scan._human_prompt_text` (used by `observe/importer.py`) | `human_prompt_text` | 3 |

### C3 — Move rules

1. Move-only. Do not change behavior. Do not add features. Do not reformat moved code.
2. No compatibility shims. Do not leave a re-export at the old path. Update every importer.
3. Keep file names. `evolve_gate.py` stays `evolve_gate.py` under `dummyindex/evolve/`.
   Reason: `evolve_gate.py` and `evolve_native_snapshot.py` read sibling files by name through `Path(__file__).with_name(...)`.
4. Fix the one sibling read that the move breaks.
   `evolve_native_snapshot._controller` reads `atomic_io.py` as a sibling.
   Read `Path(atomic_io.__file__)` instead, like `graph_storage.__file__`. Keep the dict key `"atomic_io.py"`.
5. Code digests change: `gate_code_sha256`, `promotion_code_sha256` and the snapshot `controller` hash all hash file bytes.
   No test pins these values. Finish or discard open evolve runs before the split lands.
6. `pyproject.toml`: no change. `include = ["dummyindex*"]` finds the new packages.
   Each new package needs an `__init__.py`. `package-data` stays the same.
7. `dummyindex/skills/` does not move. `dummyindex/context/schemas/` does not move.
8. CLI surface does not change. `ContextSubcommand.EVOLVE` stays in `dummyindex/context/enums.py`.
   `dummyindex/cli/__init__.py` imports `evolve.run` from `dummyindex.evolve.cli.evolve`.
9. Hook and installer strings do not change. They name CLI commands and skills, not module paths:
   `context/hooks.py:217` (`dummyindex context evolve evidence`), `installer/common.py:89`, `installer/legacy_fingerprints.py:181`.
10. Generators do not change. `dummyindex/context/output/instructions.py` and `docs/COMMANDS.md` name no moved module path.
11. String module paths in tests move with the code:
    `tests/context/domains/memory/test_memory_cli.py:112` and `tests/context/domains/test_evolve_gate.py:111` (`monkeypatch.setattr` targets).
12. Tests mirror the source move. 15 test files move to `tests/evolve/` or `tests/shared/` (see `boundary-map.md` A3).
    New test folders get an `__init__.py`, like the existing ones.

### C4 — Seams (the only edits that are not moves)

Two context→evolve calls cannot move to shared. The composition root wires them.

**S1 — closeout learning.**
- Move `_learn_after_closeout`, `_SETTLED` and `_no_mark` from `proposals/closeout.py` to `dummyindex/evolve/evolve_learning.py`.
  The public name is `learn_after_closeout(context_dir, workspace, kind, manifest, receipt, learner=None)`.
- `closeout_workspace` and `closeout_from_file` take `after_closeout: Callable[[Path, Path, str, dict, dict], None] | None = None`.
  It replaces the `learner` parameter. When it is `None`, no learning runs.
- `cli/gc.py` `run(args, *, after_closeout=None)` and `cli/build_loop` `run(args, *, after_closeout=None)` pass it through to `closeout_from_file`.
- `dummyindex/cli/__init__.py` registers `functools.partial(gc.run, after_closeout=_closeout_learning)` and the same for `build_loop.run`.
  `_closeout_learning` is a root adapter. It imports `learn_after_closeout` lazily, at call time.
- `learning_exit_code`, `learning_line` and `failed_record_path` stay in `closeout.py`. They use only `LearningStatus` (shared).
- Effect: the CLI behaves as today. A direct library call without the hook skips learning.
  Tests that expect learning pass the hook.

**S2 — probation block at session start.**
- `cli/memory.py` `run(args, *, session_block=None)`. `_print_probation` does nothing when `session_block` is `None`.
- `dummyindex/cli/__init__.py` registers `functools.partial(memory.run, session_block=_probation_block)`.
  `_probation_block` imports `dummyindex.evolve.probation.session_block` lazily, so `monkeypatch` targets still apply.

### C5 — Boundary test (`tests/test_import_boundaries.py`)

- Marker `@pytest.mark.unit`. Standard library only (`ast`, `pathlib`). No grep, no regex on source.
- Walk every `dummyindex/**/*.py`. Collect every import form:
  `import x`, `from x import y`, relative imports, imports inside functions, imports under `if TYPE_CHECKING:`,
  and `importlib.import_module("<literal>")`.
- Resolve `from pkg import name` to `pkg.name` when that module file exists.
- Layer by path: `dummyindex/shared/` → shared, `dummyindex/evolve/` → evolve, any other `dummyindex/` path → context.
- Fail on: shared→context, shared→evolve, context→evolve (except importer `dummyindex/cli/__init__.py`),
  and any cross-layer import of a `_`-prefixed name (C2).
- Fail when an old path exists again: `dummyindex/context/domains/{atomic_io,evolve*,evidence,living_rules}.py`,
  `dummyindex/context/domains/{lesson,observe,probation}/`, `dummyindex/cli/evolve*.py` (no shims, C3.2).
- The failure message lists each bad edge as `path:line -> module (names)`.
- A self-check test runs the scanner on a `tmp_path` tree with one lazy relative forbidden import.
  It asserts the scanner reports that edge. This stops the scanner from going blind.

## Cross-boundary imports

Full table: `boundary-map.md` section B (110 rows, both directions, each with a fix). Summary:

| Direction (today) | Edges | Fix |
|---|---|---|
| context→evolve | 15 | 12 move into shared (`EvolveError`, `safe_file`, `project_lock`, `lesson`); 2 seam (S1, S2); 1 root allowlist |
| evolve→context | 29 | 10 move into shared (`atomic_io`); 17 keep (public names); 2 promote private name (C2) |
| context→context that becomes context→shared | 41 | move into shared (`atomic_io`) |
| evolve→evolve that becomes evolve→shared | 25 | move into shared (guard symbols, `lesson`, `rules_in`) |

No edge needs deletion. After the split: 53 context→shared, 35 evolve→shared, 19 evolve→context, 1 root→evolve, 0 forbidden.

Shared candidates from the brief, and the decision:

| Candidate | Decision | Reason |
|---|---|---|
| `EvolveError` | → `shared/guard.py` | Context catches it from the guard and lock. Name kept (move-only). |
| `safe_file` | → `shared/guard.py` | Used by `project_lock` and closeout. |
| `project_lock` | → `shared/guard.py` | buildloop, gc delete and closeout take the project writer lock. |
| `atomic_io` | → `shared/atomic_io.py` | 49 source importers across both layers. |
| `LearningStatus` | → `shared/lesson/enums.py` (whole `lesson` package) | Closeout and equip library validate lessons. |
| `rules_in` | → `shared/lesson/rules.py` (symbol only) | `lesson.models` needs it. The rest of `living_rules` is evolve-only. |
| `sha256` (`living_rules.sha256`) | stays in evolve | No context importer. YAGNI. |

## Conflict with the equip-bugs task

The equip-bugs task edits: every `atomic_io` importer, `context/hooks.py`, `context/enums.py`, `cli/__init__.py`,
`context/domains/gc/*`, `context/domains/config.py`, `equip/*`.
Wave 2 touches 59 of these files. Wave 3 touches 12. So waves 2–4 start only after equip-bugs merges (Wave 1 is the gate).

Each conflict file has one owner task:

| Conflict files | Owner until equip-bugs merges | Split item that edits it after merge |
|---|---|---|
| `context/domains/atomic_io.py` and its importers (49 source, 7 test) | equip-bugs | Wave 2 (evolve-side importers move again in Wave 3, serially) |
| `context/domains/gc/{delete,anchor}.py`, `tests/context/domains/gc/test_delete.py` | equip-bugs | Wave 2 |
| `context/domains/equip/lifecycle/{library,status,evolve}.py`, `equip/generate/adapters.py`, `cli/equip/{dispatch,install}.py`, 4 equip tests | equip-bugs | Wave 2 |
| `cli/__init__.py`, `cli/gc.py` | equip-bugs | Wave 3 |
| `context/hooks.py`, `context/enums.py`, `context/domains/config.py` | equip-bugs | none: the split does not edit them |

Before each wave, rerun the scan. Rebase the file lists on the merged tree.

## Acceptance

- [ ] `python -m pytest tests/test_import_boundaries.py -q` passes on the split tree.
- [ ] The boundary self-check test reports a planted lazy relative context→evolve import in a `tmp_path` tree.
- [ ] `python -m pytest tests/ -q --tb=short` passes (the CI command).
- [ ] No file exists at any old path listed in C5. No module re-exports a moved symbol from its old path.
- [ ] `git diff main -- pyproject.toml docs/COMMANDS.md dummyindex/skills dummyindex/context/hooks.py dummyindex/context/enums.py` is empty.

## Open questions

- The brief lists `cli/__init__.py` as a coupling to fix. This contract keeps it as the one composition-root exception (C1).
  The Manager confirms or rejects this exception before Wave 3.
- `EvolveError` keeps its name in `shared/guard.py`. A rename to a neutral name is a later, separate change.

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
