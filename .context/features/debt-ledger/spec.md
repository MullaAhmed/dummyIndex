# Feature: Technical-debt ledger

confidence: INFERRED

Harvests deliberate **debt markers** from the repo's Python source into a deterministic, repo-relative ledger — complementing the mtime/commit drift signals (`community-8`) with an *intent* signal. Ported from the ponytail `ponytail-debt` mechanism onto dummyindex's existing rationale-extraction seam.

## Intent

dummyindex already extracts rationale-comment prefixes during ingest (`dummyindex/pipeline/extract/python_rationale.py:15`). This feature adds the missing *ledger* view: collect every `# TODO:` / `# FIXME:` / `# HACK:` / `# DEBT:` marker, then surface those that name no upgrade trigger as the rot-risk class, so deferred work can't quietly become permanent. The harvest is pure, read-only, and deterministic — no LLM in the loop (`dummyindex/cli/debt.py:6`).

## User-visible behavior

The `dummyindex context debt` CLI (`dummyindex/cli/debt.py:34`) renders a per-file, path-sorted ledger:

- **Default** — prints the markdown ledger to **stdout**; nothing is persisted (`dummyindex/cli/debt.py:67`).
- **`--write`** — ALSO persists the markdown ledger to `.context/debt.md`, creating the context dir if absent (`dummyindex/cli/debt.py:64`, `dummyindex/cli/debt.py:127`). The on-disk ledger is always the human-readable markdown view, even when stdout is JSON.
- **`--json`** — emits `DebtLedger.to_dict()` as indented JSON to stdout instead of markdown (`dummyindex/cli/debt.py:67`, `dummyindex/cli/debt.py:120`).
- An unknown flag prints `error: unknown argument(s) for \`debt\`` to stderr and returns exit code `2` (`dummyindex/cli/debt.py:51`).
- An empty ledger prints the no-debt message (`dummyindex/cli/debt.py:82`).

Re-running on an unchanged tree is byte-identical and leaks no absolute path — every rendered row is repo-relative POSIX.

## Contracts

- **`harvest_debt(project_root) -> DebtLedger`** (`dummyindex/context/domains/debt/harvest.py:34`) — pure, read-only, deterministic (no LLM). Enumerates **only `.py` files** via `detect()` under `files["code"]` (`dummyindex/context/domains/debt/harvest.py:37`); relativizes each path to repo-relative POSIX (reuses `drift._rel_or_none`, `dummyindex/context/drift.py:372`); matches a marker only on a **true comment line** — `stripped.startswith(prefix)` (`dummyindex/context/domains/debt/harvest.py:80`); parses the structured `# DEBT: <ceiling>; upgrade: <trigger>` form by splitting on the first `; upgrade:` (`dummyindex/context/domains/debt/harvest.py:97`); rows sorted by `(rel_path, line)` (`dummyindex/context/domains/debt/harvest.py:56`). Skips unreadable / non-UTF-8 files without raising (`dummyindex/context/domains/debt/harvest.py:50`).
- **`DEBT_PREFIXES`** is imported from `dummyindex/pipeline/extract/python_rationale.py:15` (`("# TODO:", "# FIXME:", "# HACK:", "# DEBT:")`) — single source of truth, shared with rationale extraction (`dummyindex/context/domains/debt/harvest.py:24`).
- **`DebtRow` / `DebtLedger`** (`dummyindex/context/domains/debt/models.py:18`, `dummyindex/context/domains/debt/models.py:48`) — frozen dataclasses; `DebtLedger.total` and `DebtLedger.no_trigger_count` are computed properties (`dummyindex/context/domains/debt/models.py:54`, `dummyindex/context/domains/debt/models.py:59`); `to_dict` gives stable JSON (`dummyindex/context/domains/debt/models.py:37`, `dummyindex/context/domains/debt/models.py:62`).
- **`no-trigger` rule** (`dummyindex/context/domains/debt/harvest.py:86`): a plain marker (TODO/FIXME/HACK), or a `# DEBT:` with a ceiling but no/empty `upgrade:` clause, or a malformed marker ⇒ `no_trigger=True` (never raises). `no_trigger` is `True` exactly when `trigger is None`. The `M` in the rendered `N markers, M with no trigger.` tally equals `no_trigger_count` (`dummyindex/cli/debt.py:101`).
- **CLI `dummyindex context debt`** (`dummyindex/cli/debt.py:34`) — flat `run(args) -> int` mirroring `cli/query.py`, registered as `ContextSubcommand.DEBT` (`dummyindex/context/enums.py:85`) and dispatched at `dummyindex/cli/__init__.py:122`.

## Examples

A structured `# DEBT:` line with an upgrade trigger:

```python
# DEBT: linear scan is fine under 10k rows; upgrade: switch to an index when N > 10k
```

renders as a triggered row:

```
- src/scan.py:42 — linear scan is fine under 10k rows. upgrade: switch to an index when N > 10k.
```

A plain marker with no trigger:

```python
# TODO: handle the empty-input case
```

renders tagged `no-trigger`:

```
- src/scan.py:7 — handle the empty-input case. no-trigger.
```

`--json` over the same two markers:

```json
{
  "total": 2,
  "no_trigger_count": 1,
  "rows": [
    {"rel_path": "src/scan.py", "line": 7, "marker": "TODO", "ceiling": "handle the empty-input case", "trigger": null, "no_trigger": true},
    {"rel_path": "src/scan.py", "line": 42, "marker": "DEBT", "ceiling": "linear scan is fine under 10k rows", "trigger": "switch to an index when N > 10k", "no_trigger": false}
  ]
}
```

A clean repo prints `_No debt markers found in the repo's Python source._` (`dummyindex/cli/debt.py:85`).

## Key symbols

- `harvest_debt`, `_rows_for_file`, `_matching_prefix`, `_parse_marker`, `_no_trigger_row` — `dummyindex/context/domains/debt/harvest.py`
- `DebtRow`, `DebtLedger` — `dummyindex/context/domains/debt/models.py`
- `run`, `render_markdown`, `render_json`, `_render_row`, `_persist` — `dummyindex/cli/debt.py`

## Tests

`tests/context/domains/debt/test_harvest.py` (parsing, no-trigger rule, Python-only scope, repo-relative paths, determinism, unreadable-file skip) and `tests/cli/test_debt_cli.py` (stdout / `--write` / `--json`, clean-repo message, no absolute paths).
