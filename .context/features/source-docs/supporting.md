# Supporting

<!-- dummyindex:merged:begin -->
### Merged from `community-23`

**Files involved:**

- `dummyindex/context/domains/debt/__init__.py`
- `dummyindex/context/domains/debt/harvest.py`
- `dummyindex/context/domains/debt/models.py`
- `dummyindex/context/domains/source_docs/refs.py`
- `dummyindex/pipeline/extract/__init__.py`
- `dummyindex/pipeline/io/detect.py`
- `tests/context/domains/debt/test_harvest.py`

**Original notes:**

# Feature: community-23

_Deterministic stub (`confidence: ConfidenceLevel.EXTRACTED`). The `/dummyindex` skill will rewrite this `spec.md` — the feature's entry point — with a real summary based on the source code._

## At a glance

- **Members:** 67 symbol(s)
- **Files:** 7
- **Entry points:** 10
- **Flows:** 10

## Files involved

- `dummyindex/context/domains/debt/__init__.py`
- `dummyindex/context/domains/debt/harvest.py`
- `dummyindex/context/domains/debt/models.py`
- `dummyindex/context/domains/source_docs/refs.py`
- `dummyindex/pipeline/extract/__init__.py`
- `dummyindex/pipeline/io/detect.py`
- `tests/context/domains/debt/test_harvest.py`

## Flows

- [`flow-238`](./flows/flow-238.md) — entry: `_is_noise_dir()` (2 steps, 1 files)
- [`flow-239`](./flows/flow-239.md) — entry: `_is_sensitive()` (2 steps, 1 files)
- [`flow-240`](./flows/flow-240.md) — entry: `_looks_like_paper()` (3 steps, 1 files)
- [`flow-241`](./flows/flow-241.md) — entry: `Harvest technical-debt markers from a repo's Python source.  ``harvest_debt(proj` (6 steps, 3 files)
- [`flow-242`](./flows/flow-242.md) — entry: `Return the debt ledger for ``project_root`` (Python ``.py`` files only).` (6 steps, 3 files)
- [`flow-243`](./flows/flow-243.md) — entry: `Parse every true-comment debt marker in one file's raw text.` (6 steps, 3 files)
- [`flow-244`](./flows/flow-244.md) — entry: `Return the ``DEBT_PREFIXES`` entry this stripped comment line begins with.` (6 steps, 3 files)
- [`flow-245`](./flows/flow-245.md) — entry: `Build a :class:`DebtRow` from one matched comment line (never raises).      ``pr` (6 steps, 3 files)
- [`flow-246`](./flows/flow-246.md) — entry: `collect_files()` (3 steps, 2 files)
- [`flow-247`](./flows/flow-247.md) — entry: `_write()` (5 steps, 1 files)

## Entry points

- `detect_is_noise_dir`
- `detect_is_sensitive`
- `detect_looks_like_paper`
- `harvest_rationale_1`
- `harvest_rationale_35`
- `harvest_rationale_61`
- `harvest_rationale_73`
- `harvest_rationale_87`
- `init_collect_files`
- `test_harvest_write`

<!-- dummyindex:merged:end -->
