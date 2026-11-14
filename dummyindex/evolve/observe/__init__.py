"""Local evolution evidence plane: keyed, bounded, hostile-input aware."""

from __future__ import annotations

from .attribution import (
    attributions,
    commit_evidence_stub,
    corrections,
    exposures,
    open_corrections,
    record_attribution,
    record_exposure,
    resolution_packet,
    session_tool_calls,
)
from .enums import CorrectionStatus, ExposureVia, Verdict
from .importer import DETECTOR_VERSION
from .keys import (
    evidence_key,
    evolution_enabled,
    keyed_id,
    retention_days,
    session_key,
)
from .ledger import observe_lock
from .security import scan_text

__all__ = [
    "open_corrections",
    "corrections",
    "attributions",
    "exposures",
    "session_tool_calls",
    "resolution_packet",
    "record_attribution",
    "record_exposure",
    "commit_evidence_stub",
    "retention_days",
    "evolution_enabled",
    "keyed_id",
    "session_key",
    "observe_lock",
    "evidence_key",
    "scan_text",
    "DETECTOR_VERSION",
    "CorrectionStatus",
    "Verdict",
    "ExposureVia",
]
