"""Confidence demotion / promotion — the self-healing feedback loop.

A report with contradictions flips the feature's ``confidence`` to ``AMBIGUOUS``,
stashing the prior value under ``confidence_demoted_from``; a later clean re-run
restores it. Both mirror the change into ``INDEX.json``. The two-file write is
staged-then-committed: **best-effort, not crash-atomic**, but a raise before the
first replace loses nothing (see :func:`_commit_confidence_change`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dummyindex.pipeline.enums import ConfidenceLevel

from .models import RealityReport

# feature.json key holding the pre-demotion confidence so a clean re-run can
# restore it. Written by demote_feature_on_contradiction, consumed (popped) by
# promote_feature_on_clean.
DEMOTED_FROM_KEY = "confidence_demoted_from"

_VALID_CONFIDENCE_VALUES = frozenset(level.value for level in ConfidenceLevel)

# Transition kinds carried back to the CLI so it can report the confidence
# delta. A bare bool cannot distinguish a demotion from a restoration, nor
# carry the prior value.
TRANSITION_DEMOTED = "demoted"
TRANSITION_RESTORED = "restored"


@dataclass(frozen=True)
class ConfidenceTransition:
    """A confidence change a demote/promote actually applied (a no-op returns ``None``).

    ``kind`` is ``TRANSITION_DEMOTED`` or ``TRANSITION_RESTORED``; ``from_value`` is
    ``None`` when feature.json had no prior confidence.
    """

    kind: str
    from_value: str | None
    to_value: str


def demote_feature_on_contradiction(
    features_dir: Path, report: RealityReport
) -> ConfidenceTransition | None:
    """On contradictions, flip confidence to ``AMBIGUOUS`` in feature.json + INDEX.json.

    A valid prior confidence is stashed under ``confidence_demoted_from`` (unless
    one is already stashed) for :func:`promote_feature_on_clean`. Returns a
    ``TRANSITION_DEMOTED`` :class:`ConfidenceTransition`, or ``None`` when nothing
    was touched. Idempotent: an already-AMBIGUOUS feature is a no-op. Writes go
    through :func:`_commit_confidence_change`, so the stash can never be lost.
    """
    if not report.has_contradictions:
        return None
    feat_dir = features_dir / report.feature_id
    feature_json = feat_dir / "feature.json"
    if not feature_json.exists():
        return None
    try:
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    prior = payload.get("confidence")
    if prior == ConfidenceLevel.AMBIGUOUS:
        return None
    payload["confidence"] = ConfidenceLevel.AMBIGUOUS.value
    if (
        isinstance(prior, str)
        and prior in _VALID_CONFIDENCE_VALUES
        and DEMOTED_FROM_KEY not in payload
    ):
        payload[DEMOTED_FROM_KEY] = prior

    _commit_confidence_change(
        features_dir,
        feature_json,
        payload,
        report.feature_id,
        ConfidenceLevel.AMBIGUOUS.value,
    )
    from_value = prior if isinstance(prior, str) else None
    return ConfidenceTransition(
        kind=TRANSITION_DEMOTED,
        from_value=from_value,
        to_value=ConfidenceLevel.AMBIGUOUS.value,
    )


def promote_feature_on_clean(
    features_dir: Path, report: RealityReport
) -> ConfidenceTransition | None:
    """The exact inverse of :func:`demote_feature_on_contradiction`.

    On a clean report, an ``AMBIGUOUS`` feature with a valid stash gets the stashed
    value back (stash popped) in feature.json + INDEX.json and returns a
    ``TRANSITION_RESTORED`` :class:`ConfidenceTransition`; anything else is a no-op
    returning ``None``. The pop is on the staged payload only, so a raise before
    the first replace never strands the feature at AMBIGUOUS without its stash.
    """
    if report.has_contradictions:
        return None
    feat_dir = features_dir / report.feature_id
    feature_json = feat_dir / "feature.json"
    if not feature_json.exists():
        return None
    try:
        payload = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("confidence") != ConfidenceLevel.AMBIGUOUS.value:
        return None
    stash = payload.get(DEMOTED_FROM_KEY)
    if not isinstance(stash, str) or stash not in _VALID_CONFIDENCE_VALUES:
        return None
    restored = ConfidenceLevel(stash)
    payload["confidence"] = restored.value
    del payload[DEMOTED_FROM_KEY]

    _commit_confidence_change(
        features_dir,
        feature_json,
        payload,
        report.feature_id,
        restored.value,
    )
    return ConfidenceTransition(
        kind=TRANSITION_RESTORED,
        from_value=ConfidenceLevel.AMBIGUOUS.value,
        to_value=restored.value,
    )


def _commit_confidence_change(
    features_dir: Path,
    feature_json: Path,
    feature_payload: dict,
    feature_id: str,
    confidence: str,
) -> bool:
    """Stage feature.json + INDEX.json to ``.tmp``, then replace back-to-back.

    Hand-rolled (not ``write_text_atomic``) so both ``.tmp`` siblings exist before
    either ``Path.replace``: a raise before the first replace leaves both files
    untouched. Best-effort, **not** crash-atomic: a crash between the replaces
    leaves INDEX.json one transition behind, reconciled by the next (idempotent)
    run. Returns ``True`` iff at least one INDEX entry matched ``feature_id``.
    """
    feature_text = json.dumps(feature_payload, indent=2, sort_keys=True) + "\n"
    staged = _mirror_confidence_to_index(features_dir, feature_id, confidence)

    # INDEX's tmp is already staged; a raise before the first replace strands nothing.
    feature_tmp = feature_json.with_suffix(feature_json.suffix + ".tmp")
    feature_json.parent.mkdir(parents=True, exist_ok=True)
    feature_tmp.write_text(feature_text, encoding="utf-8")

    if staged is None:
        # No INDEX to mirror — commit feature.json alone.
        feature_tmp.replace(feature_json)
        return False

    index_path, index_tmp, matched = staged
    feature_tmp.replace(feature_json)
    index_tmp.replace(index_path)
    return matched


def _mirror_confidence_to_index(
    features_dir: Path, feature_id: str, confidence: str
) -> tuple[Path, Path, bool] | None:
    """Mirror a confidence change into INDEX.json's ``.tmp`` (not committed).

    Returns ``(index_path, index_tmp, matched)`` for the caller to replace
    back-to-back with feature.json, or ``None`` when INDEX.json is
    absent/unreadable. ``matched`` is ``False`` when no entry had ``feature_id``,
    surfacing a mirror that landed nowhere rather than a silent no-op.
    """
    index_path = features_dir / "INDEX.json"
    if not index_path.exists():
        return None
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    matched = False
    for entry in idx.get("features", []) or []:
        if entry.get("feature_id") == feature_id:
            entry["confidence"] = confidence
            matched = True
    index_tmp = index_path.with_suffix(index_path.suffix + ".tmp")
    index_tmp.write_text(
        json.dumps(idx, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return index_path, index_tmp, matched
