"""Self-improvement loop: harvest evidence, validate candidates, gate edits.

The deterministic plumbing behind ``dummyindex context evolve`` and the
packaged ``dummyindex-evolve`` skill. The loop is *evidence -> cited
diagnosis -> bounded candidate edit -> validation gate -> adopt-or-drop ->
append-only decision history*: this module owns every deterministic half of
that pipeline and never judges anything itself. Trigger judgments arrive only
as host-produced observation files scored through the equip eval domain
(:func:`dummyindex.context.domains.equip.eval.score_run`) — the "never an LLM
judge in code" spine holds, exactly as it does for ``equip eval``.

Layout (all committed, extending the ``gc/`` area):

- ``.context/gc/evolution.jsonl`` — the append-only decision history. One
  line per transition (``harvest|diagnosis|gate|promote|rollback|discard``);
  corrupt lines are skipped with a warning on read, never fatal.
- ``.context/gc/evolve/<run>/`` — per-run artifacts: ``harvest.json``,
  ``candidates.jsonl`` (``--candidate N`` is the 0-based line index),
  ``staged/<N>/<name>`` (host-written proposed content per target),
  ``gate-<N>.json``, ``backup/<N>/<rel-path>`` (pre-promote copies used by
  ``rollback``).

Evidence citations are repo-relative (or projects-root-relative session
slugs for transcript hits — never absolute ``$HOME`` paths), so a harvested
report is portable across machines and leaks no username.

Scope guard: a candidate's targets may only touch curated ``.context/``
conventions/playbooks/equipment docs, packaged ``dummyindex/skills/*.md``
guidance, or equipment-eval cases — never source code
(``dummyindex/**/*.py``), never a ``features/<id>/spec.md`` body, never the
decision history or GC anchor itself, and never more than
:data:`MAX_TARGET_FILES` files.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dummyindex.usage.transcripts import (
    default_projects_root,
    encode_project_slug,
)

from ..build.reconcile import compute_reconcile_report
from .equip.eval.cases import parse_eval_suite, parse_observations
from .equip.eval.errors import (
    EvalSuiteError,
    MissingObservationError,
    ObservationMismatchError,
    ObservationsError,
)
from .equip.eval.models import EvalCase, TriggerObservation
from .equip.eval.score import score_run
from .gc.constants import AUDITS_REL, GC_STATE_REL

__all__ = [
    "AUDITS_REL",
    "CANDIDATES_NAME",
    "EVOLUTION_REL",
    "EVOLVE_DIR_REL",
    "GATE_NAME_FMT",
    "HARVEST_NAME",
    "MAX_CANDIDATES",
    "MAX_TARGET_FILES",
    "OBSERVATIONS_NAME",
    "Candidate",
    "CandidateError",
    "EvolveError",
    "EvolveWarning",
    "GateResult",
    "GateStage",
    "HarvestReport",
    "PredictionFlag",
    "check_predictions",
    "load_candidates",
    "load_events",
    "record_event",
    "run_gate",
    "validate_candidate",
]

# ----- layout constants ------------------------------------------------------

#: Append-only decision history, relative to ``.context/`` (committed).
EVOLUTION_REL = "gc/evolution.jsonl"

#: Per-run workspace root, relative to ``.context/`` (committed).
EVOLVE_DIR_REL = "gc/evolve"

#: Run artifact file names (pinned wire shapes, validated on read).
HARVEST_NAME = "harvest.json"
CANDIDATES_NAME = "candidates.jsonl"
OBSERVATIONS_NAME = "observations.json"
STAGED_DIR_NAME = "staged"
BACKUP_DIR_NAME = "backup"
GATE_NAME_FMT = "gate-{}.json"

#: A diagnosis emits at most five candidates; one application batch touches
#: at most five target files (both validation-enforced).
MAX_CANDIDATES = 5
MAX_TARGET_FILES = 5

# Closed alphabets.
EVENT_KINDS = ("harvest", "diagnosis", "gate", "promote", "rollback", "discard")
EVIDENCE_KINDS = (
    "audit_finding",
    "memory_correction",
    "reconcile_delta",
    "adoption_miss",
    "prediction_flip",
)
GATE_STAGE_NAMES = ("trigger-eval", "pytest-subset", "ruff")
GATE_STATUSES = ("pass", "fail", "blocked", "not_applicable")
GATE_VERDICTS = ("pass", "fail", "blocked")

# Curated surfaces a candidate may target. Everything else — most notably
# source code (``dummyindex/**/*.py``) and ``features/<id>/spec.md`` bodies —
# goes through normal plans/reconcile, never through evolve.
_ALLOWED_CONTEXT_PREFIXES = (
    "conventions/",
    "playbooks/",
    "equipment-evals/",
)
_EQUIPMENT_DOC = "equipment.json"
_SKILLS_PREFIX = "dummyindex/skills/"
_SUITE_SUFFIX = ".suite.json"


class EvolveError(Exception):
    """Base for evolve-stage failures the CLI maps to an exit code."""


class CandidateError(EvolveError):
    """A candidate object failed structural or scope validation."""


class EvolveWarning:
    """A non-fatal problem noted while reading tolerant artifacts."""

    __slots__ = ("message",)

    def __init__(self, message: str) -> None:
        self.message = message

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EvolveWarning) and other.message == self.message

    def __repr__(self) -> str:
        return f"EvolveWarning({self.message!r})"


# ----- models ----------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceItem:
    """One harvested piece of evidence, carrying a portable citation."""

    kind: str
    source: str
    citation: str
    summary: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "source": self.source,
            "citation": self.citation,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class HarvestReport:
    """The evidence side of one harvest run."""

    since: str | None
    items: tuple[EvidenceItem, ...]

    def to_dict(self) -> dict:
        return {
            "since": self.since,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: object) -> HarvestReport:
        if not isinstance(data, dict):
            raise EvolveError("harvest report must be a JSON object")
        items_raw = data.get("items")
        if not isinstance(items_raw, list):
            raise EvolveError("harvest report must contain an 'items' array")
        items: list[EvidenceItem] = []
        for index, raw in enumerate(items_raw):
            if not isinstance(raw, dict):
                raise EvolveError(f"harvest item #{index} must be an object")
            for key in ("kind", "source", "citation", "summary"):
                if not isinstance(raw.get(key), str):
                    raise EvolveError(
                        f"harvest item #{index} field {key!r} must be a string"
                    )
            items.append(
                EvidenceItem(
                    kind=raw["kind"],
                    source=raw["source"],
                    citation=raw["citation"],
                    summary=raw["summary"],
                )
            )
        since = data.get("since")
        if since is not None and not isinstance(since, str):
            raise EvolveError("harvest 'since' must be a string or null")
        return cls(since=since, items=tuple(items))


@dataclass(frozen=True)
class Candidate:
    """One bounded harness-edit proposal authored by the host-side LLM step."""

    targets: tuple[str, ...]
    diagnosis: str
    evidence: tuple[str, ...]
    change_sketch: str
    prediction: str

    @property
    def primary_target(self) -> str:
        return self.targets[0]

    def to_dict(self) -> dict:
        return {
            "target_file": (
                self.targets[0] if len(self.targets) == 1 else list(self.targets)
            ),
            "diagnosis": self.diagnosis,
            "evidence": list(self.evidence),
            "change_sketch": self.change_sketch,
            "prediction": self.prediction,
        }


@dataclass(frozen=True)
class GateStage:
    """The outcome of one gate stage."""

    name: str
    status: str
    detail: str

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class GateResult:
    """Overall gate verdict plus the per-stage trail.

    ``pass`` only when every applicable stage passed. Any stage that errored
    or could not run yields ``blocked`` — promoting then requires an explicit
    ``--override "<reason>"``. An absent suite match records the trigger-eval
    stage ``not_applicable`` honestly instead of faking coverage.
    """

    verdict: str
    stages: tuple[GateStage, ...]

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "stages": [stage.to_dict() for stage in self.stages],
        }


@dataclass(frozen=True)
class PredictionFlag:
    """A promoted prediction contradicted by fresh evidence."""

    targets: tuple[str, ...]
    prediction: str
    matched_citations: tuple[str, ...]


# ----- harvest ---------------------------------------------------------------

_FINDING_RE = re.compile(r"^- `([^`]+)`\s+—\s+\*\*(critical|high|medium|low|info)\*\*")
_DROPPED_VERDICTS = ("refuted", "withdrawn")
_CORRECTION_RE = re.compile(
    r"\b(correction|corrected|mistake|wrong|actually|instead|gotcha|lesson"
    r"|learned|never again|regression)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# Transcript adoption-miss sentinels: a user turn naming the context engine's
# own routing surface is evidence the loop needed a manual push. Only the
# matched sentinel is stored — never message content.
_ADOPTION_SENTINELS = (
    ".context/HOW_TO_USE.md",
    "/dummyindex-gc",
    "$dummyindex-gc",
    "--recouncil",
    "reconcile-stamp",
)


def _truncate(text: str, limit: int = 200) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _parse_since(since: str | None) -> datetime | None:
    if not since:
        return None
    try:
        parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvolveError(
            f"--since must be an ISO date (YYYY-MM-DD), got {since!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _section_date(heading: str) -> datetime | None:
    match = _DATE_RE.search(heading)
    if match is None:
        return None
    try:
        return datetime.fromisoformat(match.group(1)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _harvest_audits(context_dir: Path) -> list[EvidenceItem]:
    """Open findings from ``audits/<slug>/report.md`` (finding-bullet contract)."""
    items: list[EvidenceItem] = []
    reports_dir = context_dir / AUDITS_REL
    if not reports_dir.is_dir():
        return items
    for report in sorted(reports_dir.glob("*/report.md")):
        slug = report.parent.name
        try:
            lines = report.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for offset, line in enumerate(lines, start=1):
            match = _FINDING_RE.match(line.strip())
            if match is None:
                continue
            lowered = line.lower()
            if any(verdict in lowered for verdict in _DROPPED_VERDICTS):
                continue
            items.append(
                EvidenceItem(
                    kind="audit_finding",
                    source=f"{AUDITS_REL}/{slug}",
                    citation=f"{AUDITS_REL}/{slug}/report.md:L{offset}",
                    summary=_truncate(line),
                )
            )
    return items


_MEMORY_TIERS = ("now.md", "recent.md")


def _harvest_memory(
    context_dir: Path, since: datetime | None
) -> list[EvidenceItem]:
    """Correction notes from ``session-memory/{now,recent}.md`` sections."""
    items: list[EvidenceItem] = []
    memory_dir = context_dir / "session-memory"
    if not memory_dir.is_dir():
        return items
    for tier in _MEMORY_TIERS:
        path = memory_dir / tier
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue

        def flush(
            h: str | None,
            start: int,
            chunk: list[str],
            *,
            _tier: str = tier,
        ) -> None:
            if h is None:
                return
            text = "\n".join(chunk)
            if not _CORRECTION_RE.search(text):
                return
            items.append(
                EvidenceItem(
                    kind="memory_correction",
                    source=f"session-memory/{_tier}",
                    citation=f"session-memory/{_tier}:L{start}",
                    summary=_truncate(f"{h} — {text}"),
                )
            )

        heading: str | None = None
        heading_line = 0
        body: list[str] = []
        for offset, line in enumerate(lines, start=1):
            if line.startswith("## "):
                flush(heading, heading_line, body)
                heading, heading_line, body = line.strip(), offset, []
            else:
                body.append(line)
        flush(heading, heading_line, body)
    if since is not None:
        kept: list[EvidenceItem] = []
        for item in items:
            match = _DATE_RE.search(item.summary)
            if match is None:
                kept.append(item)
                continue
            try:
                dated = datetime.fromisoformat(match.group(1)).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                kept.append(item)
                continue
            if dated >= since:
                kept.append(item)
        items = kept
    return items


def _harvest_reconcile(context_dir: Path, project_root: Path) -> list[EvidenceItem]:
    """Reconcile blockers: drifted features, unassigned files, awaiting enrichment."""
    items: list[EvidenceItem] = []
    try:
        report = compute_reconcile_report(context_dir, project_root)
    except Exception:  # noqa: BLE001 — off-git / partial indexes must not crash a harvest
        return items
    for fid in report.drifted_features:
        items.append(
            EvidenceItem(
                kind="reconcile_delta",
                source="reconcile",
                citation=f"features/{fid}/spec.md",
                summary=_truncate(f"feature drifted since last reconcile: {fid}"),
            )
        )
    for rel in report.unassigned_new_files:
        items.append(
            EvidenceItem(
                kind="reconcile_delta",
                source="reconcile",
                citation=str(rel),
                summary=_truncate(f"new file owned by no feature: {rel}"),
            )
        )
    for fid in report.awaiting_enrichment:
        items.append(
            EvidenceItem(
                kind="reconcile_delta",
                source="reconcile",
                citation=f"features/{fid}/feature.json",
                summary=_truncate(f"feature awaiting enrichment: {fid}"),
            )
        )
    return items


def _transcript_citation(path: Path, projects_root: Path, offset: int) -> str:
    slug = encode_project_slug(path.parent.relative_to(projects_root))
    return f"projects/{slug}/{path.stem}.jsonl:L{offset}"


def _scan_transcript(
    path: Path, projects_root: Path
) -> list[EvidenceItem]:
    """Net-new content scan: user turns that manually invoke the context engine.

    File discovery mirrors :func:`dummyindex.usage.transcripts.iter_all_turns`
    (one glob over ``<projects>/*/<session>.jsonl``); the usage helpers
    themselves expose token counts, never message content, so this scan reads
    the JSONL itself and stores only sentinel hits + line citations.
    """
    items: list[EvidenceItem] = []
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError:
        return items
    with handle:
        for offset, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict) or obj.get("type") != "user":
                continue
            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            texts: list[str] = []
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text")
                        if isinstance(text, str):
                            texts.append(text)
            joined = "\n".join(texts)
            for sentinel in _ADOPTION_SENTINELS:
                if sentinel in joined:
                    items.append(
                        EvidenceItem(
                            kind="adoption_miss",
                            source=path.stem,
                            citation=_transcript_citation(path, projects_root, offset),
                            summary=f"manual adoption nudge: {sentinel}",
                        )
                    )
                    break
    return items


def harvest(
    context_dir: Path,
    project_root: Path,
    *,
    projects_root: Path | None = None,
    since: str | None = None,
) -> HarvestReport:
    """Compose every evidence parser into one :class:`HarvestReport`.

    Sources: audit report findings, session-memory correction notes, reconcile
    deltas, and transcript adoption misses. GC learnings are out of scope v1
    (no structured learnings store exists yet).
    """
    cutoff = _parse_since(since)
    items: list[EvidenceItem] = []
    items.extend(_harvest_audits(context_dir))
    items.extend(_harvest_memory(context_dir, cutoff))
    items.extend(_harvest_reconcile(context_dir, project_root))
    root = projects_root if projects_root is not None else default_projects_root()
    if root.is_dir():
        for transcript in sorted(root.glob("*/*.jsonl")):
            if cutoff is not None:
                try:
                    mtime = datetime.fromtimestamp(
                        transcript.stat().st_mtime, tz=timezone.utc
                    )
                except OSError:
                    continue
                if mtime < cutoff:
                    continue
            items.extend(_scan_transcript(transcript, root))
    return HarvestReport(since=since, items=tuple(items))


# ----- predictions -----------------------------------------------------------


def _split_citation(citation: str) -> str:
    """Strip a trailing ``:L12`` / ``:12`` line suffix from a citation."""
    head, _, last = citation.rpartition(":")
    if head and last.isdigit() or (head and last[:1] == "L" and last[1:].isdigit()):
        return head
    return citation


def _citation_paths(evidence: object) -> set[str]:
    paths: set[str] = set()
    if not isinstance(evidence, list):
        return paths
    for raw in evidence:
        if isinstance(raw, str) and raw.strip():
            paths.add(_split_citation(raw.strip()))
    return paths


def check_predictions(
    context_dir: Path, report: HarvestReport
) -> tuple[PredictionFlag, ...]:
    """Flag promoted predictions contradicted by fresh harvest evidence.

    A promote event carries a falsifiable prediction; a later harvest whose
    items share an evidence path with the promotion flags it flipped. Only
    the latest promote per ``(run, candidate)`` counts — a subsequent
    rollback/discard closes the prediction.
    """
    events, _warnings = load_events(context_dir)
    open_by_key: dict[tuple[str, str], dict] = {}
    for event in events:
        key = (str(event.get("run", "")), str(event.get("candidate", "")))
        kind = event.get("kind")
        if kind == "promote":
            open_by_key[key] = event
        elif kind in ("rollback", "discard"):
            open_by_key.pop(key, None)
    flags: list[PredictionFlag] = []
    for event in open_by_key.values():
        prediction = event.get("prediction")
        if not isinstance(prediction, str) or not prediction:
            continue
        watched = _citation_paths(event.get("evidence"))
        target_values = _event_targets(event)
        watched.update(target_values)
        matched = tuple(
            item.citation
            for item in report.items
            if _split_citation(item.citation) in watched
        )
        if matched:
            flags.append(
                PredictionFlag(
                    targets=target_values,
                    prediction=prediction,
                    matched_citations=matched,
                )
            )
    return tuple(flags)


def _event_targets(event: dict) -> tuple[str, ...]:
    values: list[str] = []
    raw = event.get("target")
    if isinstance(raw, str):
        values.append(raw)
    elif isinstance(raw, list):
        values.extend(t for t in raw if isinstance(t, str))
    extra = event.get("targets")
    if isinstance(extra, list):
        values.extend(t for t in extra if isinstance(t, str))
    return tuple(dict.fromkeys(values))


# ----- candidate validation --------------------------------------------------


def _normalize_target(raw: object) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise CandidateError("target_file must be a non-empty string")
    target = raw.strip()
    if target.endswith(".py"):
        raise CandidateError(
            f"scope guard: targets may never be source code ({target})"
        )
    if "\\" in target or target.startswith("/") or ".." in Path(target).parts:
        raise CandidateError(f"target_file must be a repo-relative POSIX path: {raw!r}")
    return target


def _check_scope(target: str, context_dir: Path, project_root: Path) -> str | None:
    """Return an error message when ``target`` is out of bounds, else None."""
    if target.startswith(_SKILLS_PREFIX):
        if not target.endswith(".md"):
            return (
                f"scope guard: packaged-skill targets must be *.md guidance "
                f"({target})"
            )
        if not (project_root / target).is_file():
            return f"target_file does not exist: {target}"
        return None

    rel = target[len(".context/") :] if target.startswith(".context/") else None
    if rel is None:
        return _out_of_scope_message(target)

    if rel == _EQUIPMENT_DOC or rel.startswith("equipment-evals/"):
        if not (context_dir / rel).is_file():
            return f"target_file does not exist: {target}"
        return None
    if rel in _DENY_EXACT:
        return f"scope guard: {target} is denied (never target the loop itself)"
    if rel.startswith("features/") and rel.endswith("spec.md"):
        return (
            f"scope guard: features/<id>/spec.md bodies go through plans/"
            f"reconcile ({target})"
        )
    if not rel.startswith(_ALLOWED_CONTEXT_PREFIXES):
        return _out_of_scope_message(target)
    if not (context_dir / rel).is_file():
        return f"target_file does not exist: {target}"
    return None


def _out_of_scope_message(target: str) -> str:
    return (
        "scope guard: target outside curated surfaces (allowed: "
        ".context/conventions/, .context/playbooks/, .context/equipment.json, "
        f".context/equipment-evals/, dummyindex/skills/*.md) — got {target}"
    )

_DENY_EXACT = frozenset({EVOLUTION_REL, GC_STATE_REL})


def _validate_evidence(
    citation: object,
    context_dir: Path,
    project_root: Path,
    projects_root: Path | None,
) -> str | None:
    if not isinstance(citation, str) or not citation.strip():
        return "evidence citations must be non-empty strings"
    raw = citation.strip()
    head = _split_citation(raw)
    if head.startswith("projects/"):
        root = projects_root if projects_root is not None else default_projects_root()
        rel_under_projects = Path(*head.split("/")[1:])
        if not (root / rel_under_projects).is_file():
            return f"evidence citation target not found: {raw}"
        return None
    for base in (project_root, context_dir):
        if (base / head).exists():
            return None
    return f"evidence citation target not found: {raw}"


def validate_candidate(
    obj: object,
    context_dir: Path,
    *,
    project_root: Path | None = None,
    projects_root: Path | None = None,
) -> list[str]:
    """Structural + scope + citation-existence validation.

    Returns every violation as a message string; an empty list means the
    candidate is well-formed and in scope. Never raises for a malformed
    candidate — callers render the error list.
    """
    root = project_root if project_root is not None else context_dir.parent
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["candidate must be a JSON object"]
    for key in ("target_file", "diagnosis", "evidence", "change_sketch", "prediction"):
        if key not in obj:
            errors.append(f"candidate is missing required field {key!r}")
    if errors:
        return errors

    raw_target = obj["target_file"]
    if isinstance(raw_target, str):
        raw_targets: list[object] = [raw_target]
    elif isinstance(raw_target, list):
        raw_targets = raw_target
    else:
        return ["target_file must be a string or an array of strings"]

    targets: list[str] = []
    for raw in raw_targets:
        try:
            targets.append(_normalize_target(raw))
        except CandidateError as exc:
            errors.append(str(exc))
    if len(targets) > MAX_TARGET_FILES:
        errors.append(
            f"scope guard: a candidate may target at most "
            f"{MAX_TARGET_FILES} files (got {len(targets)})"
        )
        targets = targets[:MAX_TARGET_FILES]

    for field in ("diagnosis", "change_sketch", "prediction"):
        value = obj[field]
        if not isinstance(value, str) or not value.strip():
            errors.append(f"candidate field {field!r} must be a non-empty string")

    evidence = obj["evidence"]
    if not isinstance(evidence, list) or not evidence:
        errors.append("candidate field 'evidence' must be a non-empty array")
    else:
        for citation in evidence:
            message = _validate_evidence(citation, context_dir, root, projects_root)
            if message is not None:
                errors.append(message)

    unique_targets = list(dict.fromkeys(targets))
    for target in unique_targets:
        message = _check_scope(target, context_dir, root)
        if message is not None:
            errors.append(message)
    return errors


def parse_candidate(obj: object) -> Candidate:
    """Inflate a validated candidate object into the frozen model."""
    raw_target = obj["target_file"]  # type: ignore[index]
    targets = (raw_target,) if isinstance(raw_target, str) else tuple(raw_target)
    return Candidate(
        targets=targets,  # type: ignore[arg-type]
        diagnosis=obj["diagnosis"],  # type: ignore[index]
        evidence=tuple(obj["evidence"]),  # type: ignore[index,arg-type]
        change_sketch=obj["change_sketch"],  # type: ignore[index]
        prediction=obj["prediction"],  # type: ignore[index]
    )


def load_candidates(
    path: Path,
    context_dir: Path,
    *,
    project_root: Path | None = None,
    projects_root: Path | None = None,
) -> tuple[list[Candidate], list[list[str]], list[EvolveWarning]]:
    """Read a ``candidates.jsonl`` file (tolerantly) and validate every line.

    Returns ``(valid, per_line_errors, warnings)``; corrupt JSON lines become
    warnings, structurally invalid candidates become per-line error lists.
    """
    root = project_root if project_root is not None else context_dir.parent
    valid: list[Candidate] = []
    invalid: list[list[str]] = []
    warnings: list[EvolveWarning] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvolveError(f"candidates file not readable: {exc}") from exc
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            warnings.append(EvolveWarning(f"candidates line {line_no}: invalid JSON"))
            continue
        errors = validate_candidate(
            obj,
            context_dir,
            project_root=root,
            projects_root=projects_root,
        )
        if errors:
            invalid.append(
                [
                    f"candidate {len(valid) + len(invalid)} (line {line_no}): {e}"
                    for e in errors
                ]
            )
        else:
            valid.append(parse_candidate(obj))
    return valid, invalid, warnings


# ----- gate ------------------------------------------------------------------

CommandRunner = Callable[[list[str]], tuple[int, str]]

_PYTEST_STOPWORDS = frozenset({"tests", "test", "dummyindex", "fixtures"})
_SEGMENT_MIN_LEN = 3


def _target_segments(targets: tuple[str, ...]) -> list[str]:
    segments: list[str] = []
    for target in targets:
        pure = Path(target)
        stems = [pure.stem, *(part for part in pure.parts)]
        for segment in stems:
            if (
                segment
                and len(segment) >= _SEGMENT_MIN_LEN
                and segment not in _PYTEST_STOPWORDS
                and segment not in segments
            ):
                segments.append(segment)
    return segments


def _matching_test_files(
    targets: tuple[str, ...], project_root: Path
) -> list[Path]:
    """Tests matching the changed path segments (the G1 targeted subset)."""
    tests_root = project_root / "tests"
    if not tests_root.is_dir():
        return []
    segments = _target_segments(targets)
    matched: list[Path] = []
    for candidate in sorted(tests_root.rglob("test_*.py")):
        rel = candidate.relative_to(project_root).as_posix()
        if any(segment in rel for segment in segments):
            matched.append(candidate)
    return matched


def _resolve_suite(
    targets: tuple[str, ...], context_dir: Path
) -> Path | None:
    """Map targets to an equipment-eval suite, or None (honestly unmatched)."""
    evals_dir = context_dir / "equipment-evals"
    for target in targets:
        if target.startswith(".context/equipment-evals/") and target.endswith(
            _SUITE_SUFFIX
        ):
            rel = target[len(".context/") :]
            path = context_dir / rel
            if path.is_file():
                return path
        if target.startswith(_SKILLS_PREFIX):
            tool = target[len(_SKILLS_PREFIX) :].split("/", 1)[0]
            path = evals_dir / f"{tool}{_SUITE_SUFFIX}"
            if path.is_file():
                return path
    return None


def _stage_trigger_eval(
    targets: tuple[str, ...],
    run_dir: Path,
    context_dir: Path,
) -> GateStage:
    suite_path = _resolve_suite(targets, context_dir)
    if suite_path is None:
        return GateStage(
            name="trigger-eval",
            status="not_applicable",
            detail="no equipment-eval suite maps to the targeted files",
        )
    observations_path = run_dir / OBSERVATIONS_NAME
    if not observations_path.is_file():
        return GateStage(
            name="trigger-eval",
            status="blocked",
            detail=f"suite {suite_path.name} matched but {OBSERVATIONS_NAME} is absent",
        )
    try:
        suite_data = json.loads(suite_path.read_text(encoding="utf-8"))
        obs_data = json.loads(observations_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return GateStage(
            name="trigger-eval",
            status="blocked",
            detail=f"suite/observations unreadable or invalid JSON: {exc}",
        )
    try:
        cases: tuple[EvalCase, ...] = parse_eval_suite(suite_data)
        observations: tuple[TriggerObservation, ...] = parse_observations(obs_data)
        result = score_run(cases, observations, tool_name=suite_path.stem)
    except (
        EvalSuiteError,
        ObservationsError,
        ObservationMismatchError,
        MissingObservationError,
    ) as exc:
        return GateStage(
            name="trigger-eval",
            status="blocked",
            detail=f"observations rejected: {exc}",
        )
    misfires = ", ".join(case.case_id for case in result.misfires)
    if result.misfires:
        return GateStage(
            name="trigger-eval",
            status="fail",
            detail=f"accuracy {result.accuracy:.3f}; misfires: {misfires}",
        )
    return GateStage(
        name="trigger-eval",
        status="pass",
        detail=f"accuracy {result.accuracy:.3f} over {len(result.cases)} case(s)",
    )


def _default_runner(argv: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as exc:
        raise EvolveError(f"command not found: {argv[0]}") from exc
    return completed.returncode, (completed.stdout + completed.stderr)


def _stage_pytest(
    targets: tuple[str, ...],
    project_root: Path,
    runner: CommandRunner,
) -> GateStage:
    matched = _matching_test_files(targets, project_root)
    if not matched:
        return GateStage(
            name="pytest-subset",
            status="not_applicable",
            detail="no test file matches the changed path segments",
        )
    rels = [p.relative_to(project_root).as_posix() for p in matched]
    argv = [sys.executable, "-m", "pytest", "-q", *rels]
    try:
        code, output = runner(argv)
    except EvolveError as exc:
        return GateStage(name="pytest-subset", status="blocked", detail=str(exc))
    tail = _truncate(output, 300)
    if code == 0:
        return GateStage(name="pytest-subset", status="pass", detail=tail)
    if code == 1:
        return GateStage(name="pytest-subset", status="fail", detail=tail)
    return GateStage(
        name="pytest-subset",
        status="blocked",
        detail=f"pytest could not run (exit {code}): {tail}",
    )


def _stage_ruff(
    targets: tuple[str, ...],
    project_root: Path,
    runner: CommandRunner,
) -> GateStage:
    py_targets = [t for t in targets if t.endswith(".py")]
    if not py_targets:
        return GateStage(
            name="ruff",
            status="not_applicable",
            detail="no touched Python files",
        )
    argv = ["ruff", "check", *py_targets]
    try:
        code, output = runner(argv)
    except EvolveError as exc:
        return GateStage(name="ruff", status="blocked", detail=str(exc))
    if code != 0:
        return GateStage(name="ruff", status="fail", detail=_truncate(output, 300))
    return GateStage(name="ruff", status="pass", detail="ruff clean")


def run_gate(
    targets: tuple[str, ...],
    run_dir: Path,
    context_dir: Path,
    project_root: Path,
    *,
    runner: CommandRunner | None = None,
) -> GateResult:
    """Run the three-stage validation gate over a staged candidate.

    Stages: trigger-eval scoring (only when a suite maps to the targets),
    the targeted pytest subset (subprocess ``python -m pytest <matches> -q``),
    and ``ruff check`` on touched Python. Any blocked stage forces the
    overall verdict to ``blocked``; any failing stage forces ``fail``;
    ``pass`` requires every applicable stage to pass.
    """
    execute = runner if runner is not None else _default_runner
    stages = (
        _stage_trigger_eval(targets, run_dir, context_dir),
        _stage_pytest(targets, project_root, execute),
        _stage_ruff(targets, project_root, execute),
    )
    statuses = {stage.status for stage in stages}
    if "blocked" in statuses:
        verdict = "blocked"
    elif "fail" in statuses:
        verdict = "fail"
    else:
        verdict = "pass"
    return GateResult(verdict=verdict, stages=stages)


# ----- decision history ------------------------------------------------------


def evolution_path(context_dir: Path) -> Path:
    return context_dir / EVOLUTION_REL


def record_event(context_dir: Path, event: dict) -> dict:
    """Append one transition line to the decision history (returns the event)."""
    stamped = {
        "id": next_event_id(context_dir),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **event,
    }
    path = evolution_path(context_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stamped, sort_keys=True) + "\n")
    return stamped


def load_events(context_dir: Path) -> tuple[list[dict], list[EvolveWarning]]:
    """Tolerant reader: corrupt lines are skipped with a warning, never fatal."""
    events: list[dict] = []
    warnings: list[EvolveWarning] = []
    path = evolution_path(context_dir)
    if not path.is_file():
        return events, warnings
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            warnings.append(
                EvolveWarning(f"{EVOLUTION_REL} line {line_no}: corrupt, skipped")
            )
            continue
        if isinstance(obj, dict):
            events.append(obj)
        else:
            warnings.append(
                EvolveWarning(f"{EVOLUTION_REL} line {line_no}: not an object, skipped")
            )
    return events, warnings


def next_event_id(context_dir: Path) -> int:
    events, _warnings = load_events(context_dir)
    ids = [e["id"] for e in events if isinstance(e.get("id"), int)]
    return (max(ids) + 1) if ids else 1


def run_dir_for(context_dir: Path, name: str) -> Path:
    """Resolve + validate a run directory under ``.context/gc/evolve/<name>/``."""
    if (
        not name
        or "/" in name
        or "\\" in name
        or name in (".", "..")
        or name != name.strip()
    ):
        raise EvolveError(f"invalid run name: {name!r}")
    path = context_dir / EVOLVE_DIR_REL / name
    if not path.is_dir():
        raise EvolveError(f"run directory not found: {path}")
    return path


def mint_run_dir(context_dir: Path, *, now: datetime | None = None) -> Path:
    """Create a fresh timestamped run directory under ``gc/evolve/``."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    base = context_dir / EVOLVE_DIR_REL
    candidate = base / stamp
    suffix = 2
    while candidate.exists():
        candidate = base / f"{stamp}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate
