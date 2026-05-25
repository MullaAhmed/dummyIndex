"""Source-docs constants: schema version, classification thresholds, banner."""
from __future__ import annotations

SCHEMA_VERSION = 1

# Confidence classification thresholds. Tunable.
_HIGH_BROKEN_RATIO = 0.10    # ≤10% broken refs → still trust the doc
_LOW_BROKEN_RATIO = 0.40     # ≥40% broken refs → don't trust it
_MIN_BROKEN_FOR_LOW = 4      # don't crash a doc to "low" off a single broken ref

_ADVISORY_BANNER = (
    "> **Advisory — verify before quoting.** This catalog is generated from "
    "prose checked into the repo. Docs drift faster than code. Every entry "
    "carries a `confidence` (high / medium / low) derived from how many of "
    "its backticked code references still match the current AST. Treat "
    "high-confidence docs as hypotheses worth quoting; cross-check "
    "medium-confidence docs against `../map/symbols.json` and `../tree.json`; "
    "treat low-confidence docs as historical context only.\n"
)
