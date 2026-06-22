# Architect notes — debt-ledger (stage 2)

## What I changed

- Replaced the loose "Where it lives / Architecture in three sentences" framing with a tight **Bounded context** section: one domain + one wire-only CLI boundary, with the read-only / no-LLM / no-implicit-write invariant stated up front.
- Reorganised the body into four mandate-aligned sections — **Patterns named**, **Dependencies surfaced**, **Decisions promoted**, **Open questions** — so each `path:range` claim sits under the heading it serves.
- Corrected drifted line citations against `.context/map/symbols.json` + source: `DebtRow` 18→19, `DebtLedger` 48→49, `total`→55, `no_trigger_count`→59, `render_markdown` def→71, `_render_row`→106, `render_json`→120, `--write` gate→`cli/debt.py:46`, help text 211→207, `startswith` guard→`harvest.py:81`, `_parse_marker` body split→`harvest.py:110`, no-trigger degrade→`harvest.py:110`.
- Cut filler (the "in three sentences" prose, repeated re-statements of determinism) and removed unlocated assertions; every pattern now carries a verified `path:range`.

## Patterns named

- **Deterministic harvester** — `harvest_debt` (`domains/debt/harvest.py:34`); `.py` filter (`harvest.py:42`); stable sort before freeze (`harvest.py:56`).
- **True-comment-line guard** — `_matching_prefix` / `stripped.startswith(prefix)` (`harvest.py:72`, `harvest.py:81`).
- **Structured-marker parse** — `_parse_marker` (`harvest.py:86`) on `_UPGRADE_SEP` (`harvest.py:31`), empty-clause degrade (`harvest.py:110`).
- **Shared-prefix single source of truth** — `DEBT_PREFIXES` imported from `pipeline/extract/python_rationale.py:15` (`harvest.py:24`).
- **Frozen-dataclass + `to_dict()`** (project convention) — `DebtRow`/`DebtLedger` (`models.py:19`, `models.py:49`); stable key order (`models.py:37`, `models.py:62`).
- **Wire-only CLI boundary** (project convention) — `cli/debt.py` mirrors `cli/query.py:7-15`; name on `ContextSubcommand` (`enums.py:85`).

## Dependencies surfaced

- Reuses **rationale-extraction prefixes** — `DEBT_PREFIXES` (`python_rationale.py:15`), the load-bearing port seam.
- Reuses **`drift._rel_or_none`** (`context/drift.py:372`) for repo-relative POSIX paths (`harvest.py:45`) — same no-absolute-leak discipline as `maps._rel_posix`.
- **Complements** the `community-8` drift signal (what-changed vs what-was-deferred); siblings, not coupled — harvest reads no drift state.

## Decisions promoted

- **Python-only (v1)** — `.py` only (`harvest.py:42`); inherits `detect()` exclusions; TS/JS out of scope.
- **No-trigger rot-risk class** is the feature's reason to exist; the `M` tally (`cli/debt.py:101`) == `no_trigger_count`.
- **Deterministic, no LLM, no implicit writes** — persistence only under explicit `--write` (`cli/debt.py:46`); on-disk always markdown (`cli/debt.py:62`).
- **Reuse over re-implementation** — one change point each for marker set and path-relativization.
- **Fail-soft harvest, fail-loud user write** — silent skip (`harvest.py:51`) vs surfaced `--write` failure.
