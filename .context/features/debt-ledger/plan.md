# Technical-debt ledger — plan

confidence: INFERRED

## Bounded context

One domain (`dummyindex/context/domains/debt/`) plus one wire-only CLI boundary (`dummyindex/cli/debt.py`). The domain owns a **pure, read-only harvest** of Python debt markers into a frozen `DebtLedger`; the CLI owns all I/O — argv parsing, rendering, and the only write path (`--write`). Nothing here mutates source, calls an LLM, or persists outside the explicit `--write` gate.

- **Domain** — `domains/debt/harvest.py` (the harvester), `domains/debt/models.py` (frozen `DebtRow`/`DebtLedger`), `domains/debt/__init__.py` (re-exports `harvest_debt`).
- **CLI boundary** — `cli/debt.py`: `run` (`cli/debt.py:34`), `render_markdown`/`render_json`/`_render_row`, `_persist` (`cli/debt.py:127`).
- **Wiring** — `ContextSubcommand.DEBT = "debt"` (`context/enums.py:85`), import + dispatch (`cli/__init__.py:29`, `cli/__init__.py:122`), help text (`cli/help.py:207`).
- **Tests** — `tests/context/domains/debt/test_harvest.py`, `tests/cli/test_debt_cli.py`.

## Patterns named (at `path:range`)

- **Deterministic harvester.** `harvest_debt` (`domains/debt/harvest.py:34`) runs `detect()` (`harvest.py:37`), keeps only `.py` files (`harvest.py:42`), scans each line, sorts rows by `(rel_path, line)` before freezing the ledger (`harvest.py:56`). Pure string parsing + a stable sort ⇒ re-running on an unchanged tree is byte-identical.
- **True-comment-line guard.** A marker counts only when `stripped.startswith(prefix)` (`_matching_prefix`, `harvest.py:72`, test at `harvest.py:81`) — a `# TODO:` token inside a string continuation never matches.
- **Structured-marker parse.** `_parse_marker` (`harvest.py:86`) splits the `# DEBT: <ceiling>; upgrade: <trigger>` form on the first `_UPGRADE_SEP` (`harvest.py:31`); an empty `upgrade:` clause degrades to no-trigger (`harvest.py:110`) rather than raising.
- **Shared-prefix single source of truth.** `DEBT_PREFIXES` is imported, not copied, from `pipeline/extract/python_rationale.py:15` (`harvest.py:24`) — the same tuple rationale extraction already consumes (`python_rationale.py:19`). Marker-set changes flow through one place.
- **Frozen-dataclass + `to_dict()` (project convention).** `DebtRow` (`models.py:19`) and `DebtLedger` (`models.py:49`) are `@dataclass(frozen=True)` with a hand-written `to_dict()` emitting stable key order (`models.py:37`, `models.py:62`) — matches `conventions/coding-practices.md`. `total` and `no_trigger_count` are computed properties (`models.py:55`, `models.py:59`).
- **Wire-only CLI boundary (project convention).** `cli/debt.py` mirrors `cli/query.py:7-15`: parse argv, lazy-import the domain, render, exit. The domain never imports `cli`. Subcommand name lives on the `ContextSubcommand` StrEnum (`enums.py:85`), not as a bare string.

## Dependencies surfaced

- **Reuses rationale-extraction prefixes** — `DEBT_PREFIXES` from `pipeline/extract/python_rationale.py:15`. This is the load-bearing port seam: the feature is the *ledger view* over the prefix set ingest already extracts.
- **Reuses `drift._rel_or_none`** (`context/drift.py:372`) for repo-relative POSIX paths (`harvest.py:45`) — the same no-absolute-path-leakage discipline as `maps._rel_posix` (`conventions/data-access.md`). No rendered row leaks a home directory.
- **Complements the drift signal (`community-8`).** mtime/commit drift answers *what changed*; this answers *what was deferred*. They are siblings, not coupled — debt harvest reads no drift state.

## Decisions promoted

- **Python-only (v1).** Only `.py` files are scanned (`harvest.py:42`); the markers are `#`-comment syntax. File enumeration inherits `detect()`'s ignore/sensitive exclusions for free. TS/JS `// TODO:` is explicitly out of scope to keep the harvest Python-pure.
- **No-trigger is the rot-risk class — the feature's reason to exist.** A plain marker, a `# DEBT:` with a ceiling but empty/absent `upgrade:`, or a malformed marker all degrade to `no_trigger=True` without raising (`harvest.py:110`); `no_trigger` is `True` exactly when `trigger is None`. The `M` in the rendered `N markers, M with no trigger.` tally (`cli/debt.py:101`) equals `no_trigger_count` — surfacing deferred work that names no upgrade trigger is the point.
- **Deterministic, no LLM, no implicit writes.** The harvester writes nothing; persistence is the CLI's job under explicit `--write` (`cli/debt.py:46`). The on-disk ledger at `.context/debt.md` is always the markdown view even when stdout is JSON (`cli/debt.py:62`), and `_persist` creates the context dir if absent (`cli/debt.py:127`).
- **Reuse over re-implementation.** `DEBT_PREFIXES` and `_rel_or_none` are imported, not copied — one change point each for the marker set and path-relativization.
- **Fail-soft harvest, fail-loud user write.** Unreadable / non-UTF-8 `.py` files are skipped silently (`harvest.py:51`); a user-requested `--write` surfaces its failure rather than swallowing it.

## Open questions

- Multi-language scope: do TS/JS `// TODO:` markers warrant a second prefix set, or stay out of scope to keep the harvest Python-pure?
- Inline trailing markers: only line-leading comments match today (`stripped.startswith`); should `x = 1  # TODO: ...` count?
- Should `--write` output feed the drift signal (`community-8`) so a stale `.context/debt.md` is itself flagged, closing the loop between intent and mtime/commit drift?
