## Data integrity

- `dummyindex/context/domains/query.py:616-632` and `dummyindex/context/domains/query.py:698-719` — feature/member joins silently omit missing symbol IDs and optional unreadable feature records. Mixed-generation inputs can lose ranking signals or ranged citations without a degraded-result flag; use a reconciled index when assessing retrieval quality.
- `dummyindex/context/domains/query.py:703-719` — citation lookup keys on symbol name, so multiple owned symbols sharing a name overwrite one another in symbol-map iteration order. Scores remain deterministic for identical inputs, but reordering colliding records can change the cited path; unique symbol IDs remain the stronger citation identity.

## Security

- `dummyindex/context/domains/query.py:616-620`, `dummyindex/context/domains/query.py:645-665`, `dummyindex/context/domains/query.py:723-753` — An index with a forged absolute or parent-traversing feature ID redirects feature-record and Markdown reads outside the context directory; matching external prose can reach output. Resolving the context root does not confine these child joins. Existing mitigation is the owner-controlled local-index trust boundary; no feature-ID containment check is enforced here. Read-only operation avoids writes, not unintended reads.
- `dummyindex/context/domains/query.py:307-312`, `dummyindex/context/domains/query.py:406-425`, `dummyindex/context/domains/query.py:576-620` — Explicit query/top-K/output limits reject oversized requests and preserve complete bounded results. They do not cap the index, symbol-map or Markdown bytes loaded before rendering, so a hostile oversized local index can still exhaust resources. Treat shared indexes as untrusted artifacts until inspected; optional parse fallbacks are not arbitrary-schema validation. The former shell-length-only bound and every-parse-is-guarded claims are obsolete.

## Product surface

- **A small byte allowance removes every ranked match** — the byte guard can
  return `matches=()` with `truncated=True`; Markdown then says no feature
  matched and the CLI exits 1 — JSON preserves the truncation distinction, but
  the empty Markdown result does not distinguish clipping from a genuine miss
  (`dummyindex/context/domains/query.py:406-425`,
  `dummyindex/context/domains/query.py:786-800`,
  `dummyindex/cli/query.py:124-126`).
- **Raising only `--budget` to recover clipped results** — estimated-token and
  byte allowances are independent, and whole matches are removed at the byte
  cap — a larger token budget alone cannot restore them; nonempty Markdown's
  generic “truncated by budget” label does not identify which cap was reached
  (`dummyindex/context/domains/query.py:379-425`,
  `dummyindex/context/domains/query.py:801-805`).
- **Navigating after source/index drift** — retrieval reads the current files
  without a freshness check and unresolved member IDs contribute no symbol
  citation — a result can still appear normally while paths/ranges are stale or
  absent. Improved ranking does not refresh the index
  (`dummyindex/context/domains/query.py:335-358`,
  `dummyindex/context/domains/query.py:687-720`).
- **Interpreting a score as confidence** — scores are now floating weighted
  contributions with query/feature-dependent IDF and size normalization — they
  rank this query's candidates, not calibrated confidence or comparable quality
  across queries; short substring hits remain possible
  (`dummyindex/context/domains/query.py:428-573`,
  `dummyindex/context/domains/query.py:808-820`).
