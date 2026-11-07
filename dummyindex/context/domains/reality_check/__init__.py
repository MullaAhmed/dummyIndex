"""Post-synthesis reality checker.

After the chairman writes a feature's canonical docs, re-read the line-checkable
ones and verify each *concrete claim* against the AST extraction, the symbol graph
and the source files. ``spec.md`` is intent-level and deliberately NOT checked;
``plan.md`` + ``concerns.md`` carry the grounding claims. The legacy essay docs
(``architecture.md``, ``implementation.md``, ``data-model.md``, ``security.md``,
``product.md``) are still scanned, so a pre-reshape ``.context/`` keeps getting
checked until it is re-councilled.

Claim kinds (backticked forms only):

- **Calls / uses.** `` `X` calls `Y` `` / `` `X.foo()` uses `Y.bar()` `` — both
  symbols must exist; a missing ``features/symbol-graph.json`` edge is ambiguous.
- **Has-method.** `` `X` has method `Y` `` — both names in ``map/symbols.json``.
- **File:line.** `` `path/to/file.py:42` `` — the file exists and has ≥ N lines.

Not verified: semantic/behavioral claims (``X is faster than Y``), unstructured
prose, and references rooted *outside* the repo (``os.environ.setdefault``,
``requests.get``): absence from ``map/symbols.json`` is not proof of falsehood,
so these are ``ambiguous``, never ``contradicted``.

File:line citations resolve in order: exact ``map/files.json`` entry → literal
path under the repo root (manifests/docs the index doesn't track) → the feature's
own docs (``spec.md:12`` cited from ``concerns.md``) → basename match over the
index, disambiguated by the feature's ``files``. Several matches with no unique
feature-scoped hit is ``ambiguous`` (fully qualify the citation), never a pick.

Output: ``features/<id>/_reality-check.json`` + ``_reality-check.md``. Any
``contradicted`` claim flips the feature's ``confidence`` to ``AMBIGUOUS``,
stashing the prior value as ``confidence_demoted_from``; a clean re-run restores
it via :func:`promote_feature_on_clean`.

Split into :mod:`.models`, :mod:`.extract`, :mod:`.verify` (incl. the
:func:`reality_check_feature` orchestrator), :mod:`.render` and :mod:`.confidence`;
this package re-exports their public surface so existing imports keep working.
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
