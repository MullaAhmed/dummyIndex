# Coding practices (derived)

How code in this **synchronous Python CLI** is written. Reconciles canonical rules in `docs/reference/01-conventions.md` with actual source. Doc declares "Code wins" at `docs/reference/01-conventions.md:11`. AST wins on conflict. Divergences are flagged.

## Frozen dataclasses, data-only, with `to_dict()`

Every data class is `@dataclass(frozen=True)`. Rule: `01-conventions.md:436-462`. 46 source files declare `frozen=True`.

Collection fields are `tuple[...]`, never `list[...]`, so the freeze is real. `Feature.members`/`files`/`flow_ids` are all tuples (`dummyindex/context/domains/features/models.py:57-67`).

Models hold data only. Serialization is a hand-written `to_dict()` beside the class. It emits the wire shape and turns tuples into JSON lists:

```python
@dataclass(frozen=True)
class Flow:
    steps: tuple[FlowStep, ...]
    confidence: str = ConfidenceLevel.EXTRACTED
    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, ...,
                "steps": [s.to_dict() for s in self.steps],
                "files": list(self.files), ...}
```

Source: `dummyindex/context/domains/features/models.py:32-54`.

The result-type pattern is everywhere. Builders return frozen `*Result` records: `ScaffoldResult`, `RenameResult`, `MergeResult`, `RemoveResult`, `PlacementResult` (`models.py:84-133`).

## Enum constants, never bare strings

Closed alphabets use `(str, Enum)`. `.value` stays wire-compatible with JSON and markdown on disk. Rule: `01-conventions.md:402-414`.

`DocConfidence` (`dummyindex/context/enums.py:12-30`) pins `__str__ = str.__str__`. So 3.11+ f-strings render `"low"`, not `DocConfidence.LOW`. A real interpreter-portability fix, not boilerplate.

CLI subcommand names live in `ContextSubcommand` StrEnum (`enums.py:40-87`). Not as bare strings in the dispatcher.

## Typed exception hierarchy

Each domain that raises errors ships `errors.py`. It has a base exception and specific subclasses. Subclasses carry context as attributes (`dummyindex/context/domains/audit/errors.py:5-54`). Example: `AuditError(Exception)` → `AuditSlugError`, `AuditExistsError`, `AuditNotFoundError`, `ModelRequiredError`.

No bare `raise ValueError` for domain conditions. Rule: `01-conventions.md:573`.

> **Divergence (AST wins):** the doc says field validation in `__post_init__` raises `ValueError` (`01-conventions.md:475`). Source raises a *typed* domain exception instead. `Config.__post_init__` raises `ConfigError` (`dummyindex/context/domains/config.py:95-98`). The typed form is stronger and consistent with §10. Treat the doc line as stale.

## I/O at the CLI boundary; subprocess behind a `Runner` seam

CLI dispatcher is wire-only. It parses flags, calls a domain function, prints, and returns an `int` exit code. Rule: `01-conventions.md:482-519`.

`print` lives only in `cli/*`. Domain modules return and raise.

Dispatcher maps typed exceptions to exit codes. `0` ok, `2` bad args or usage, `1` runtime failure. It catches specific before base (`dummyindex/cli/audit.py:84-92`). `run` returns `2` on missing args at `audit.py:31-43`.

This is **dependency injection by Callable seam, not Protocol.** The one equip module that shells out hides subprocess behind a `Runner = Callable[[list[str]],
RunResult]` type alias. Its `default_runner` default arg lets tests inject a fake. Tests never touch the network (`dummyindex/context/domains/equip/plugins/sources.py:30-62`).

`default_runner` uses fixed argv and no shell. It sets `check=False`. A missing executable maps to returncode 127. It never raises on non-zero (`sources.py:33-48`). Same precedent governs `context/build/git_delta.py` (`sources.py:5-8`).

File writes are atomic: tmp file + `replace`. They are byte-faithful by contract. Otherwise equip hash-baselines misread a silent rewrite as a user edit (`dummyindex/context/domains/atomic_io.py:11-24`).

## Sync vs async — N/A here

There is **no async**. Codebase is a synchronous CLI. Tree-sitter is sync. No DB. No network round-trips in the hot path. Rule: `01-conventions.md:731`.

Only `await` in the tree is JavaScript inside the `VIEWER_HTML` template string (`dummyindex/context/output/viewer.py:223`). Not Python.

**Pydantic is not used.** No HTTP or validation boundary (`01-conventions.md:437-441`). Only mentions are in generated guidance text.

**`typing.Protocol` is not used.** DI uses Callable aliases.

## Layering, splitting, validation surface

Imports are strictly one-way: `__main__ → cli/installer → context → analysis →
pipeline`. Rule: `01-conventions.md:248-256`.

A package starts with the canonical trio: `__init__.py`, `enums.py`, `models.py`. `__init__.py` holds the public re-exports, which form the test surface. It then splits by concern, then by size. Over 600 lines must split. CLI dispatchers stay <~300 lines (`01-conventions.md:328-337`).

Validation lives in `__post_init__` (field and cross-field invariants) or `pipeline/validate.py` (artefact-level). Never in the consumer. Rule: `01-conventions.md:474-479`.

## Linting & formatting — ruff is the single tool

**`ruff` is the one linter *and* formatter.** Rule: `01-conventions.md:662-669`, "Pre-flight".

Config is centralised in `pyproject.toml` `[tool.ruff]`. It sets `line-length = 88` and `target-version = "py310"`, the oldest supported interpreter. Lint `select = ["E", "F", "I", "W", "UP", "B"]` covers pycodestyle, pyflakes, import-sorting, pyupgrade, bugbear. Ignore list: `ignore = ["E501"]`. Formatter treats 88 as a wrapping *target*, not a hard limit. So line-length is not lint-enforced.

Selected set is exactly what the tree passes clean. Additions stay opt-in. A new rule never reddens CI without a sweep.

**Pre-flight before any change.** Same commands as `01-conventions.md:668-669`:

```bash
ruff check .            # lint — the gate CI enforces
ruff format --check .   # formatting — local/pre-commit only, not a CI gate
```

Tree is fully green today. `ruff check` passes. 366 files are already `ruff format`-clean. Two enforcement seams, deliberately asymmetric:

- **CI** (`.github/workflows/lint.yml`) runs `ruff check --output-format=github .` on every push or PR to `main`. **Lint only.** Formatting is *not* a CI gate yet.
- **pre-commit** (`.pre-commit-config.yaml`, `astral-sh/ruff-pre-commit`) runs `ruff --fix`, then `ruff-format`, on staged files. Also runs `check-yaml`, `trailing-whitespace`, `end-of-file-fixer` (excluding `*.json`), `check-added-large-files`. Install once with `pre-commit install`.

Ruff's mechanical normalisation is behaviour-preserving. Examples: blank line after module docstring, `Optional[X]` → `X | None` under UP, F401 unused-import removal, 88-col reflow. A `chore(lint)` sweep keeps feature contracts. It drifts only the deterministic backbone: `map/`, `tree.json`, symbol ranges. `dummyindex context rebuild --changed` refreshes that without re-clustering.
