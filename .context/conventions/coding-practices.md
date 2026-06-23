# Coding practices (derived)

How code in this **synchronous Python CLI** is written. Reconciles the
canonical rules in `docs/reference/01-conventions.md` (which declares "Code
wins" at `docs/reference/01-conventions.md:11`) with what the source actually
does. AST wins on conflict — divergences are flagged.

## Frozen dataclasses, data-only, with `to_dict()`

Every data class is `@dataclass(frozen=True)` (rule: `01-conventions.md:436-462`;
46 source files declare `frozen=True`). Collection fields are `tuple[...]`, never
`list[...]`, so the freeze is real — `Feature.members`/`files`/`flow_ids` are all
tuples (`dummyindex/context/domains/features/models.py:57-67`). Models carry data
only; serialization is a hand-written `to_dict()` next to the class that emits the
wire shape and re-inflates tuples to JSON lists:

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
(`dummyindex/context/domains/features/models.py:32-54`). The result-type pattern
is pervasive: builders return frozen `*Result` records — `ScaffoldResult`,
`RenameResult`, `MergeResult`, `RemoveResult`, `PlacementResult`
(`models.py:84-133`).

## Enum constants, never bare strings

Closed alphabets are `(str, Enum)` so `.value` is wire-compatible with the
JSON/markdown on disk (rule: `01-conventions.md:402-414`). `DocConfidence`
(`dummyindex/context/enums.py:12-30`) pins `__str__ = str.__str__` so 3.11+
f-strings render `"low"`, not `DocConfidence.LOW` — a real interpreter-portability
fix, not boilerplate. CLI subcommand names live in the `ContextSubcommand` StrEnum
(`enums.py:40-87`), not as bare strings in the dispatcher.

## Typed exception hierarchy

Each domain that errors ships an `errors.py` with a base exception and specific
subclasses carrying context as attributes
(`dummyindex/context/domains/audit/errors.py:5-54`): `AuditError(Exception)` →
`AuditSlugError`, `AuditExistsError`, `AuditNotFoundError`, `ModelRequiredError`.
No bare `raise ValueError` for domain conditions (rule: `01-conventions.md:573`).

> **Divergence (AST wins):** the convention doc says field validation in
> `__post_init__` raises `ValueError` (`01-conventions.md:475`). Source raises a
> *typed* domain exception instead — `Config.__post_init__` raises `ConfigError`
> (`dummyindex/context/domains/config.py:95-98`). The typed form is stronger and
> consistent with §10; treat the doc line as stale.

## I/O at the CLI boundary; subprocess behind a `Runner` seam

The CLI dispatcher is wire-only: parse flags → call a domain function → print →
return an `int` exit code (rule: `01-conventions.md:482-519`). `print` lives only
in `cli/*`; domain modules return and raise. The dispatcher translates typed
exceptions to exit codes — `0` ok, `2` bad args / usage, `1` runtime failure —
catching specific-before-base (`dummyindex/cli/audit.py:84-92`, `run` returning
`2` on missing args at `audit.py:31-43`).

This is **dependency injection by Callable seam, not Protocol.** The one equip
module that shells out hides subprocess behind a `Runner = Callable[[list[str]],
RunResult]` type alias with a `default_runner` default arg, so tests inject a fake
and never touch the network (`dummyindex/context/domains/equip/plugins/sources.py:30-62`).
`default_runner` uses fixed argv, no shell, `check=False`, and maps a missing
executable to returncode 127 — it never raises on non-zero
(`sources.py:33-48`). The same precedent governs `context/build/git_delta.py`
(`sources.py:5-8`).

File writes are atomic — tmp file + `replace` — and byte-faithful by contract, so
equip's hash-baselines don't misread a silent rewrite as a user edit
(`dummyindex/context/domains/atomic_io.py:11-24`).

## Sync vs async — N/A here

There is **no async**. The codebase is a synchronous CLI: tree-sitter is sync, no
DB, no network round-trips in the hot path (rule: `01-conventions.md:731`). The
only `await` in the tree is JavaScript inside the `VIEWER_HTML` template string
(`dummyindex/context/output/viewer.py:223`), not Python. **Pydantic is not used**
(no HTTP/validation boundary, `01-conventions.md:437-441`); the only mentions are
in generated guidance text. **`typing.Protocol` is not used** — DI is via Callable
aliases.

## Layering, splitting, validation surface

Strict one-way imports (`__main__ → cli/installer → context → analysis →
pipeline`; rule: `01-conventions.md:248-256`). A package grows the canonical trio —
`__init__.py` (public re-exports = the test surface), `enums.py`, `models.py` —
then splits by concern, then by size: >600 lines must split, CLI dispatchers stay
<~300 (`01-conventions.md:328-337`). Validation lives in `__post_init__`
(field/cross-field invariants) or `pipeline/validate.py` (artefact-level), never in
the consumer (`01-conventions.md:474-479`).

## Linting & formatting — ruff is the single tool

**`ruff` is the one linter *and* formatter** (rule: `01-conventions.md:662-669`,
"Pre-flight"). Config is centralised in `pyproject.toml` `[tool.ruff]`:
`line-length = 88`, `target-version = "py310"` (the oldest supported interpreter),
lint `select = ["E", "F", "I", "W", "UP", "B"]` (pycodestyle, pyflakes,
import-sorting, pyupgrade, bugbear) with `ignore = ["E501"]` — the formatter treats
88 as a wrapping *target*, not a hard limit, so line-length is not lint-enforced.
The selected set is exactly what the existing tree passes clean; additions stay
opt-in so a new rule never reddens CI without an accompanying sweep.

**Pre-flight before any change** (the same commands as `01-conventions.md:668-669`):

```bash
ruff check .            # lint — the gate CI enforces
ruff format --check .   # formatting — local/pre-commit only, not a CI gate
```

The tree is fully green today (`ruff check` passes; 366 files already
`ruff format`-clean). Two enforcement seams, deliberately asymmetric:

- **CI** (`.github/workflows/lint.yml`) runs `ruff check --output-format=github .`
  on every push/PR to `main` — **lint only**. Formatting is *not* a CI gate yet.
- **pre-commit** (`.pre-commit-config.yaml`, `astral-sh/ruff-pre-commit`) runs
  `ruff --fix` then `ruff-format` on staged files (plus `check-yaml`,
  `trailing-whitespace`, `end-of-file-fixer` excluding `*.json`,
  `check-added-large-files`). Install once with `pre-commit install`.

The mechanical normalisation ruff applies (blank line after module docstring,
`Optional[X]` → `X | None` under UP, F401 unused-import removal, 88-col reflow) is
behaviour-preserving — a `chore(lint)` sweep does not change feature contracts, so
it drifts only the deterministic backbone (`map/`, `tree.json`, symbol ranges),
which `dummyindex context rebuild --changed` refreshes without re-clustering.
