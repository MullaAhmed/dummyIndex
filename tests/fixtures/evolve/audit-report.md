# Audit report — fixture snippet

## Executive summary

2 confirmed findings, 0 unresolved disputes.

## Findings

- `src/loader.py:L40-L52` — **high** (confirmed) — config loader caches secrets in module state; rotate per call. Evidence: the module-level `_CACHE` dict. Suggested fix: drop the cache.
- `src/loader.py:L77-L81` — **medium** (confirmed) — retry loop swallows OSError and masks outages. Evidence: bare `except OSError: pass`. Suggested fix: log and re-raise after max retries.
- `src/loader.py:L10-L12` — **low** (refuted) — naming nit withdrawn during rebuttal; listed for completeness.
