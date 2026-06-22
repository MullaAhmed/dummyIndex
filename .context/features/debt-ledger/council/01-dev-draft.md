# Technical-debt ledger — plan

confidence: INFERRED

## Where it lives

- `dummyindex/context/domains/debt/` — the domain: `models.py` (frozen dataclasses), `harvest.py` (the pure harvester), `__init__.py` (re-exports `harvest_debt`).
- `dummyindex/cli/debt.py` — the thin CLI boundary (`run`, renderers, `--write` persistence).
- Wiring: `ContextSubcommand.DEBT = "debt"` (`dummyindex/context/enums.py:85`), import + dispatch in `dummyindex/cli/__init__.py:29` and `dummyindex/cli/__init__.py:122`, help text in `dummyindex/cli/help.py:211`.
- Tests: `tests/context/domains/debt/test_harvest.py`, `tests/cli/test_debt_cli.py`.

## Architecture in three sentences

A pure, read-only harvester (`harvest_debt`, `dummyindex/context/domains/debt/harvest.py:34`) enumerates the repo's `.py` files via `detect()`, scans each line for a debt marker, and returns a deterministic `DebtLedger` — no writes, no LLM. A marker counts only on a **true comment line** (`stripped.startswith(prefix)`, `dummyindex/context/domains/debt/harvest.py:80`), so a `# TODO:` token living inside a string continuation never matches. The harvester reuses the existing seams rather than re-implementing them — `DEBT_PREFIXES` from `dummyindex/pipeline/extract/python_rationale.py:15` (one source of truth, shared with rationale extraction) and `drift._rel_or_none` (`dummyindex/context/drift.py:372`) for repo-relative POSIX paths that never leak a home directory.

## Data model

- **`DebtRow`** (`dummyindex/context/domains/debt/models.py:18`) — `@dataclass(frozen=True)` with `rel_path`, `line`, `marker` (bare token `TODO`/`FIXME`/`HACK`/`DEBT`), `ceiling` (the good-enough bound text), `trigger` (`Optional[str]`, the upgrade condition or `None`), `no_trigger` (`True` exactly when `trigger is None`). `to_dict()` emits a stable key order (`dummyindex/context/domains/debt/models.py:37`).
- **`DebtLedger`** (`dummyindex/context/domains/debt/models.py:48`) — `@dataclass(frozen=True)` wrapping `rows: tuple[DebtRow, ...]`; `total` and `no_trigger_count` are computed properties (`dummyindex/context/domains/debt/models.py:54`); `to_dict()` returns `{total, no_trigger_count, rows}` (`dummyindex/context/domains/debt/models.py:62`).
- **Sort order** — rows sorted by `(rel_path, line)` before the ledger is frozen (`dummyindex/context/domains/debt/harvest.py:56`), and the markdown renderer groups by file in that order (`dummyindex/cli/debt.py:90`), so the rendered ledger is byte-stable across runs and machines.

## Key decisions

- **Python-only (v1).** Only `.py` files are scanned (`dummyindex/context/domains/debt/harvest.py:42`); these markers are Python `#`-comment syntax. TS and other languages are explicitly out of scope — the file enumeration inherits `detect()`'s ignore/sensitive exclusions by design (`dummyindex/context/domains/debt/harvest.py:9`).
- **Deterministic, no LLM.** Pure string parsing and a stable sort; re-running on an unchanged tree is byte-identical. The harvester writes nothing — persistence is the CLI's job under explicit `--write` (`dummyindex/cli/debt.py:64`).
- **No-trigger as a rot-risk class.** A plain marker, a `# DEBT:` with a ceiling but empty/absent `upgrade:` clause, or a malformed marker all degrade to `no_trigger=True` without raising (`dummyindex/context/domains/debt/harvest.py:97`). Surfacing this count (the `M` in `N markers, M with no trigger.`) is the feature's reason to exist: deferred work that names no upgrade trigger is the work most likely to rot.
- **Reuse over re-implementation.** `DEBT_PREFIXES` and `_rel_or_none` are imported, not copied — a change to the marker set or path-relativization flows through one place.
- **Fail-soft I/O.** Unreadable / non-UTF-8 `.py` files are skipped silently in the harvester (`dummyindex/context/domains/debt/harvest.py:50`); a user-requested `--write` surfaces its failure rather than swallowing it (`dummyindex/cli/debt.py:127`).

## Open questions

- Multi-language scope: do TS/JS `// TODO:` markers warrant a second prefix set, or stay out of scope to keep the harvest Python-pure?
- Inline trailing markers: only line-leading comments match today (`stripped.startswith`); should `x = 1  # TODO: ...` count?
- Should `--write` output feed the drift signal (`community-8`) so a stale `.context/debt.md` is itself flagged, closing the loop between intent and mtime/commit drift?
