"""Confidence demotion / promotion — the self-healing feedback loop.

A report with contradictions flips the feature's ``confidence`` to
``AMBIGUOUS`` (stashing the prior value under ``confidence_demoted_from``);
a later clean re-run restores the stashed value. Both mirror the change into
``INDEX.json`` so the table view stays consistent.

The two-file mirror is staged-then-committed (the same tmp+``replace``
mechanism as :func:`..atomic_io.write_text_atomic`, hand-rolled here so both
``.tmp`` siblings are written *before* either replace): both payloads are
serialized to ``.tmp`` first, then replaced back-to-back. This is
**best-effort, not crash-atomic** — a crash between the two ``Path.replace``
calls leaves INDEX.json lagging feature.json by one transition, reconciled on
the next run (the mirror is idempotent). What it does guarantee: a raise
before the first replace leaves both files unchanged, so a demotion's stash
can never be lost mid-write.
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
    """A confidence change a demote/promote actually applied.

    ``kind`` is ``TRANSITION_DEMOTED`` or ``TRANSITION_RESTORED``;
    ``from_value`` is the prior confidence (``None`` when feature.json had no
    prior value), ``to_value`` the new one. A no-op (nothing touched) is
    signalled by returning ``None`` instead of an instance.
    """

    kind: str
    from_value: str | None
    to_value: str


def demote_feature_on_contradiction(
    features_dir: Path, report: RealityReport
) -> ConfidenceTransition | None:
    """When the report has contradictions, flip the feature's confidence
    to ``AMBIGUOUS`` in feature.json + INDEX.json. Returns a
    :class:`ConfidenceTransition` (``kind=TRANSITION_DEMOTED``) describing the
    change, or ``None`` when nothing was touched — the CLI uses this to report
    the confidence delta (a bare bool cannot carry the prior value).

    The prior confidence is stashed under ``confidence_demoted_from`` so a
    later clean run can restore it (:func:`promote_feature_on_clean`).
    Idempotent: a second call after the confidence is already
    AMBIGUOUS is a no-op (returns ``None``) and leaves any existing stash
    untouched.

    The two-file mirror is staged-then-committed: both feature.json and
    INDEX.json are serialized to ``.tmp`` siblings and replaced back-to-back
    (see :func:`_commit_confidence_change`), so a raise before the first
    replace leaves both files untouched — the stash can never be lost.
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
        features_dir, feature_json, payload,
        report.feature_id, ConfidenceLevel.AMBIGUOUS.value,
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

    When a re-run is clean (zero contradictions) and the feature sits at
    ``AMBIGUOUS`` with a ``confidence_demoted_from`` stash, restore the
    stashed value (popping the stash) in feature.json + INDEX.json. Returns a
    :class:`ConfidenceTransition` (``kind=TRANSITION_RESTORED``) carrying the
    AMBIGUOUS→stashed delta, or ``None`` when nothing was touched. A dirty
    report, a non-AMBIGUOUS feature, or a missing/invalid stash are all
    no-ops (``None``) — never destructive.

    The stash is only popped from the *staged* payload; both files are
    committed back-to-back by :func:`_commit_confidence_change`, which
    serializes feature.json (post-pop) and INDEX.json to ``.tmp`` siblings
    *before* the first replace. A raise before that first replace leaves the
    on-disk feature.json — including its stash — untouched, so a failure can
    never strand the feature at AMBIGUOUS with no way to restore it.
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
        features_dir, feature_json, payload,
        report.feature_id, restored.value,
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

    Both payloads are serialized and written to ``.tmp`` siblings *before*
    either is committed via ``Path.replace``. A raise before the first
    replace therefore leaves both on-disk files untouched — which is what
    lets the caller pop a stash from the staged payload without risking its
    loss (the stash only leaves disk once the replaces actually run).

    Best-effort, **not** crash-atomic: the two ``Path.replace`` calls are
    distinct syscalls, so a crash *between* them leaves INDEX.json lagging
    feature.json by one transition. That residual single-replace window is
    reconciled on the next ``reality-check`` run (the mirror is idempotent).

    Returns ``True`` if at least one INDEX entry matched ``feature_id``;
    ``False`` when INDEX.json is absent/unreadable or **no entry matched**
    (the zero-match signal — see :func:`_mirror_confidence_to_index`).
    """
    feature_text = json.dumps(feature_payload, indent=2, sort_keys=True) + "\n"
    staged = _mirror_confidence_to_index(features_dir, feature_id, confidence)

    # Stage feature.json's bytes, then commit both back-to-back. The INDEX
    # mirror is committed only after feature.json's tmp is in place, so a
    # raise here (before the first replace) strands nothing.
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

    Returns ``(index_path, index_tmp, matched)`` where the staged bytes are
    written to ``index_tmp`` but **not** replaced into ``index_path`` (the
    caller commits it back-to-back with feature.json), or ``None`` when
    INDEX.json is absent/unreadable. ``matched`` is the zero-match signal:
    ``True`` if at least one INDEX entry matched ``feature_id``, ``False`` if
    none did — surfacing a mirror that landed nowhere rather than a silent
    no-op.
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
    index_tmp.write_text(json.dumps(idx, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index_path, index_tmp, matched
