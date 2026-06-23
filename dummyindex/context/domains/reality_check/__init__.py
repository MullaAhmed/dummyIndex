"""Post-synthesis reality checker.

After the chairman writes a feature's canonical docs (spec.md, plan.md,
concerns.md), this module re-reads the line-checkable ones and verifies
each *concrete claim* against the AST extraction + the symbol graph +
actual source files. ``spec.md`` is intent-level (what the feature does)
and is deliberately NOT line-checked; ``plan.md`` + ``concerns.md`` carry
the concrete grounding claims. The legacy essay docs (``architecture.md``,
``implementation.md``, ``data-model.md``, ``security.md``, ``product.md``)
are also still scanned during the v0.14 transition window, so a pre-reshape
``.context/`` keeps getting checked until it's re-councilled.

What counts as a claim:

- **Calls.**  `` `X` calls `Y` `` / `` `X.foo()` calls `Y.bar()` `` —
  check that the call relation actually exists in
  ``features/symbol-graph.json``.
- **File:line.**  `` `path/to/file.py:42` `` or
  ``"on line 42 of file.py"`` — check the file exists and has ≥ N lines.
- **Symbol existence.**  Bare-name claims like
  `` `Calculator.add` `` resolved against ``map/symbols.json``.

What we deliberately don't try to verify:

- Semantic / behavioral claims (``X is faster than Y``, ``Z is
  thread-safe``). The reality checker is a fact-check on grounding, not
  on judgment.
- Claims that aren't structured (free prose without an extractable
  subject/object).
- References rooted *outside* the repo (``os.environ.setdefault``,
  ``requests.get``): absence from ``map/symbols.json`` is not proof of
  falsehood, so these are reported ``ambiguous``, never ``contradicted``.

File:line citations resolve in this order: exact ``map/files.json`` entry →
the literal path on disk under the repo root (manifests/docs the index
doesn't track) → the feature's own docs (``spec.md:12`` cited from
``concerns.md``) → basename match over the index, disambiguated against the
feature's own ``files`` list. A basename that matches several files with no
unique feature-scoped hit is ``ambiguous`` (fully qualify the citation),
never an arbitrary pick.

Output is a JSON report at ``features/<id>/_reality-check.json`` plus a
human summary at ``features/<id>/_reality-check.md``. Claims with status
``contradicted`` flip the feature's ``confidence`` to ``AMBIGUOUS`` (the
prior value is stashed as ``confidence_demoted_from``) — the council can
re-run with the report in hand to fix them, and a clean re-run restores
the stashed confidence via :func:`promote_feature_on_clean`.

The implementation is split across focused modules — :mod:`.models` (data),
:mod:`.extract` (claim extraction), :mod:`.verify` (AST verification + the
:func:`reality_check_feature` orchestrator), :mod:`.render` (report writers),
and :mod:`.confidence` (demotion/promotion). This package re-exports the same
public surface the single-file module used to expose, so existing
``from ...reality_check import X`` imports keep working unchanged.
"""

from __future__ import annotations

from .confidence import (  # noqa: F401 - private compatibility re-exports
    _VALID_CONFIDENCE_VALUES,
    DEMOTED_FROM_KEY,
    ConfidenceTransition,
    _mirror_confidence_to_index,
    demote_feature_on_contradiction,
    promote_feature_on_clean,
)
from .extract import (  # noqa: F401 - private compatibility re-exports
    _CALL_RE,
    _CANONICAL_DOCS,
    _FILE_LINE_RE,
    _HAS_METHOD_RE,
    _USES_RE,
    _extract_claims,
)
from .models import SCHEMA_VERSION, Claim, RealityReport
from .render import render_report_md, write_report
from .verify import (  # noqa: F401 - private compatibility re-exports
    _bare_name,
    _is_external_reference,
    _load_call_edges,
    _load_feature_files,
    _load_file_paths,
    _load_symbols,
    _repo_module_names,
    _repo_root_from_meta,
    _resolve_cited_path,
    _summarize,
    _verify_claim,
    _with_status,
    reality_check_feature,
)

__all__ = [
    "SCHEMA_VERSION",
    "Claim",
    "RealityReport",
    "reality_check_feature",
    "render_report_md",
    "write_report",
    "demote_feature_on_contradiction",
    "promote_feature_on_clean",
    "ConfidenceTransition",
    "DEMOTED_FROM_KEY",
]
