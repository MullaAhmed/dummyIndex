"""Confidence demotion / promotion — the self-healing feedback loop.

A report with contradictions flips the feature's ``confidence`` to
``AMBIGUOUS`` (stashing the prior value under ``confidence_demoted_from``);
a later clean re-run restores the stashed value. Both mirror the change into
``INDEX.json`` so the table view stays consistent.
"""
from __future__ import annotations

import json
from pathlib import Path

from dummyindex.pipeline.enums import ConfidenceLevel

from .models import RealityReport
from .render import _atomic_write

# feature.json key holding the pre-demotion confidence so a clean re-run can
# restore it. Written by demote_feature_on_contradiction, consumed (popped) by
# promote_feature_on_clean.
DEMOTED_FROM_KEY = "confidence_demoted_from"

_VALID_CONFIDENCE_VALUES = frozenset(level.value for level in ConfidenceLevel)


def demote_feature_on_contradiction(features_dir: Path, report: RealityReport) -> bool:
    """When the report has contradictions, flip the feature's confidence
    to ``AMBIGUOUS`` in feature.json + INDEX.json. Returns True if
    anything was touched.

    The prior confidence is stashed under ``confidence_demoted_from`` so a
    later clean run can restore it (:func:`promote_feature_on_clean`).
    Idempotent: a second call after the confidence is already
    AMBIGUOUS is a no-op and leaves any existing stash untouched.
    """
    if not report.has_contradictions:
        return False
    feat_dir = features_dir / report.feature_id
    feature_json = feat_dir / "feature.json"
    if not feature_json.exists():
        return False
    try:
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    prior = payload.get("confidence")
    if prior == ConfidenceLevel.AMBIGUOUS:
        return False
    payload["confidence"] = ConfidenceLevel.AMBIGUOUS.value
    if (
        isinstance(prior, str)
        and prior in _VALID_CONFIDENCE_VALUES
        and DEMOTED_FROM_KEY not in payload
    ):
        payload[DEMOTED_FROM_KEY] = prior
    _atomic_write(feature_json, json.dumps(payload, indent=2) + "\n")

    _mirror_confidence_to_index(
        features_dir, report.feature_id, ConfidenceLevel.AMBIGUOUS.value
    )
    return True


def promote_feature_on_clean(features_dir: Path, report: RealityReport) -> bool:
    """The exact inverse of :func:`demote_feature_on_contradiction`.

    When a re-run is clean (zero contradictions) and the feature sits at
    ``AMBIGUOUS`` with a ``confidence_demoted_from`` stash, restore the
    stashed value (popping the stash) in feature.json + INDEX.json. Returns
    True if anything was touched. A dirty report, a non-AMBIGUOUS feature,
    or a missing/invalid stash are all no-ops — never destructive.
    """
    if report.has_contradictions:
        return False
    feat_dir = features_dir / report.feature_id
    feature_json = feat_dir / "feature.json"
    if not feature_json.exists():
        return False
    try:
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if payload.get("confidence") != ConfidenceLevel.AMBIGUOUS.value:
        return False
    stash = payload.get(DEMOTED_FROM_KEY)
    if not isinstance(stash, str) or stash not in _VALID_CONFIDENCE_VALUES:
        return False
    restored = ConfidenceLevel(stash)
    payload["confidence"] = restored.value
    del payload[DEMOTED_FROM_KEY]
    _atomic_write(feature_json, json.dumps(payload, indent=2) + "\n")

    _mirror_confidence_to_index(features_dir, report.feature_id, restored.value)
    return True


def _mirror_confidence_to_index(
    features_dir: Path, feature_id: str, confidence: str
) -> None:
    """Mirror a confidence change into INDEX.json so the table view matches."""
    index_path = features_dir / "INDEX.json"
    if not index_path.exists():
        return
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for entry in idx.get("features", []) or []:
        if entry.get("feature_id") == feature_id:
            entry["confidence"] = confidence
    _atomic_write(index_path, json.dumps(idx, indent=2) + "\n")
