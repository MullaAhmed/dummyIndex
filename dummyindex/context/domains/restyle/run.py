"""Restyle run loop: plan, begin, next, done, stamp, status over curated ``.context/`` docs.

Units follow the STYLE scope (C2). A run is a ``kind="restyle"`` fleet run; its
snapshot (original text, ``mtime_ns``) lives in ``cache/restyle/<run>/``. Only
``stamp`` writes the ruleset: it touches ``meta.json`` and the two word ratchets.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dummyindex.context.build.meta import read_meta, write_meta
from dummyindex.context.domains import fleet
from dummyindex.context.domains.atomic_io import write_text_atomic
from dummyindex.context.domains.docbudget import (
    BudgetGroup,
    StyleViolation,
    lint_text,
    read_ratchet,
    read_ratchet_ruleset,
    reseed,
    scan,
    write_ratchet,
)
from dummyindex.context.domains.docbudget.constants import (
    CONTEXT_RATCHET_REL,
    STE_RULESET_VERSION,
    STYLE_RATCHET_REL,
)
from dummyindex.context.domains.restyle.constants import SNAPSHOT_NAME
from dummyindex.context.domains.restyle.errors import (
    DocTokenLossError,
    RestyleRunError,
)
from dummyindex.context.domains.restyle.snapshot import diff_tokens
from dummyindex.context.output.bootstrap import STE_DOC_STANDARD

__all__ = [
    "PlanUnit",
    "RestyleBegin",
    "RestyleDone",
    "RestyleNext",
    "RestylePlan",
    "RestyleStamp",
    "begin",
    "done",
    "next_unit",
    "plan",
    "stamp",
    "status",
]

_CURATED_PREFIXES = (".context/features/", ".context/conventions/")
_META_REL = "meta.json"
_CONTEXT_PREFIX = ".context/"
_BRIEF = (
    "{standard}\n\n"
    "Rewrite these docs in place: {docs}.\n"
    "Change the words, not the facts.\n"
    "Protected tokens stay exactly as written: `path:line` citations, code spans, "
    "code blocks, link targets, heading levels, numerals, and not, no, never, "
    "only, must, cannot. `restyle done` fails when one changes.\n"
)


@dataclass(frozen=True)
class PlanUnit:
    unit_id: str
    docs: tuple[str, ...]  # paths relative to the context folder
    strict: int
    advice: int


@dataclass(frozen=True)
class RestylePlan:
    status: str  # "ready" | "already_restyled" | "nothing_to_restyle"
    ruleset: int
    units: tuple[PlanUnit, ...]
    doc_count: int
    strict: int
    advice: int


@dataclass(frozen=True)
class RestyleBegin:
    run_dir: Path
    units: tuple[str, ...]
    doc_count: int


@dataclass(frozen=True)
class RestyleNext:
    unit_id: str
    docs: tuple[Path, ...]
    brief: str


@dataclass(frozen=True)
class RestyleDone:
    unit_id: str
    strict: tuple[tuple[str, StyleViolation], ...]  # (doc, violation) still to fix
    advice: tuple[tuple[str, StyleViolation], ...]  # (doc, advice line)
    added: tuple[tuple[str, str], ...]  # (doc, new protected token): warning only


@dataclass(frozen=True)
class RestyleStamp:
    ruleset: int
    docs: tuple[str, ...]  # restyled docs, relative to the context folder


def plan(context_dir: Path) -> RestylePlan:
    """Read-only: the curated units with their strict and advice counts."""
    units: list[PlanUnit] = []
    for unit_id, docs in _curated_units(context_dir).items():
        strict = advice = 0
        for rel in docs:
            for violation in lint_text(_read(context_dir / rel)):
                if violation.severity == "strict":
                    strict += 1
                else:
                    advice += 1
        units.append(PlanUnit(unit_id, docs, strict, advice))
    if _recorded_ruleset(context_dir) == STE_RULESET_VERSION:
        state = "already_restyled"
    elif not units:
        state = "nothing_to_restyle"
    else:
        state = "ready"
    return RestylePlan(
        status=state,
        ruleset=STE_RULESET_VERSION,
        units=tuple(units),
        doc_count=sum(len(u.docs) for u in units),
        strict=sum(u.strict for u in units),
        advice=sum(u.advice for u in units),
    )


def begin(
    context_dir: Path,
    *,
    all_units: bool,
    max_units: int | None,
    force: bool,
) -> RestyleBegin:
    """Start a restyle run over the first units (all, or ``max_units``) and snapshot their docs."""
    if not all_units and max_units is None:
        raise RestyleRunError(
            "restyle begin needs --all or --max-units N, so an unbounded rewrite "
            "is never started silently"
        )
    if max_units is not None and max_units < 1:
        raise RestyleRunError("--max-units must be at least 1")
    unfinished = _unfinished_run(context_dir)
    if unfinished is not None:
        raise RestyleRunError(
            f"restyle run {unfinished} is unfinished — resume with "
            "`dummyindex context restyle next`, or check it with "
            "`dummyindex context restyle status`"
        )
    current = plan(context_dir)
    if current.status == "already_restyled" and not force:
        raise RestyleRunError(
            f"already restyled (ruleset {STE_RULESET_VERSION}); "
            "pass --force to start a new run"
        )
    if not current.units:
        raise RestyleRunError("nothing to restyle: the index has no curated docs")

    chosen = current.units if max_units is None else current.units[:max_units]
    docs_by_unit = {u.unit_id: u.docs for u in chosen}
    try:
        run = fleet.create_run(
            context_dir,
            tuple(docs_by_unit),
            mode="restyle",
            stages_for_feature={uid: ((1, "restyle"),) for uid in docs_by_unit},
            kind=fleet.KIND_RESTYLE,
        )
    except fleet.FleetRunError as exc:
        raise RestyleRunError(str(exc)) from exc

    cache = _cache_dir(context_dir, run.run_dir.name)
    snapshot: dict[str, dict[str, int]] = {}
    for unit_id, docs in docs_by_unit.items():
        snapshot[unit_id] = {}
        for rel in docs:
            source = context_dir / rel
            copy = cache / rel
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, copy)
            snapshot[unit_id][rel] = source.stat().st_mtime_ns
    write_text_atomic(
        cache / SNAPSHOT_NAME, json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    )
    return RestyleBegin(
        run_dir=run.run_dir,
        units=tuple(docs_by_unit),
        doc_count=sum(len(d) for d in docs_by_unit.values()),
    )


def next_unit(context_dir: Path, run: str | None = None) -> RestyleNext | None:
    """The next unit with its doc paths and rewrite brief; ``None`` when all units are done."""
    loaded = _open_run(context_dir, run)
    unit = fleet.next_unit(loaded)
    if unit is None:
        return None
    docs = _read_snapshot(context_dir, loaded.run_dir.name)[unit.feature_id]
    names = ", ".join(docs)
    return RestyleNext(
        unit_id=unit.feature_id,
        docs=tuple(context_dir / rel for rel in docs),
        brief=_BRIEF.format(standard=STE_DOC_STANDARD, docs=names),
    )


def done(context_dir: Path, unit: str, run: str | None = None) -> RestyleDone:
    """Check one unit against its snapshot; restore mtimes and mark it done on a pass."""
    loaded = _open_run(context_dir, run)
    stage = _unit_stage(loaded, unit)
    snapshot = _read_snapshot(context_dir, loaded.run_dir.name)[unit]
    cache = _cache_dir(context_dir, loaded.run_dir.name)

    losses: list[tuple[str, str]] = []
    added: list[tuple[str, str]] = []
    texts: dict[str, str] = {}
    for rel in snapshot:
        texts[rel] = _read(context_dir / rel)
        diff = diff_tokens(_read(cache / rel), texts[rel])
        losses.extend((rel, token) for token in diff.lost)
        added.extend((rel, token) for token in diff.added)
    if losses:
        raise DocTokenLossError(tuple(losses))

    strict: list[tuple[str, StyleViolation]] = []
    advice: list[tuple[str, StyleViolation]] = []
    for rel, mtime_ns in snapshot.items():
        path = context_dir / rel
        os.utime(path, ns=(path.stat().st_atime_ns, mtime_ns))
        for violation in lint_text(texts[rel]):
            target = strict if violation.severity == "strict" else advice
            target.append((rel, violation))
    fleet.mark_done(loaded, unit, stage)
    return RestyleDone(unit, tuple(strict), tuple(advice), tuple(added))


def stamp(context_dir: Path, run: str | None = None) -> RestyleStamp:
    """Record the ruleset in ``meta.json`` and re-seed the restyled docs' word ratchets."""
    loaded = _open_run(context_dir, run)
    pending = [
        u.feature_id for u in loaded.units if u.status is fleet.UnitStatus.PENDING
    ]
    if pending:
        raise RestyleRunError(
            f"{len(pending)} unit(s) still pending: {', '.join(pending)} — "
            "finish each with `dummyindex context restyle done <unit>`"
        )
    snapshot = _read_snapshot(context_dir, loaded.run_dir.name)
    rels = tuple(
        rel
        for unit in loaded.units
        if unit.status is fleet.UnitStatus.DONE
        for rel in snapshot[unit.feature_id]
    )

    root = context_dir.parent
    scoped = [_CONTEXT_PREFIX + rel for rel in rels]
    context_ratchet = root / CONTEXT_RATCHET_REL
    if context_ratchet.is_file():
        fresh = reseed(read_ratchet(context_ratchet), root, scoped, BudgetGroup.CONTEXT)
        write_ratchet(context_ratchet, fresh)
    style_ratchet = root / STYLE_RATCHET_REL
    if style_ratchet.is_file():
        header = read_ratchet_ruleset(style_ratchet) or None
        fresh = reseed(read_ratchet(style_ratchet), root, scoped, BudgetGroup.STYLE)
        write_ratchet(style_ratchet, fresh, header)

    meta_path = context_dir / _META_REL
    try:
        meta = read_meta(meta_path)
    except (OSError, ValueError) as exc:
        raise RestyleRunError(f"cannot read {meta_path}: {exc}") from exc
    write_meta(meta_path, meta.with_updates(restyled_ruleset=STE_RULESET_VERSION))
    return RestyleStamp(ruleset=STE_RULESET_VERSION, docs=rels)


def status(context_dir: Path, run: str | None = None) -> dict[str, Any]:
    """Progress of a restyle run, as ``fleet.run_status`` reports it."""
    return fleet.run_status(_open_run(context_dir, run))


def _curated_units(context_dir: Path) -> dict[str, tuple[str, ...]]:
    """Unit id -> its docs. A feature groups its docs; each convention is its own unit."""
    units: dict[str, list[str]] = {}
    for rel in scan(context_dir.parent, BudgetGroup.STYLE):
        if not rel.startswith(_CURATED_PREFIXES):
            continue
        inner = rel[len(_CONTEXT_PREFIX) :]
        unit_id = inner.split("/")[1] if inner.startswith("features/") else inner
        units.setdefault(unit_id, []).append(inner)
    return {uid: tuple(docs) for uid, docs in sorted(units.items())}


def _recorded_ruleset(context_dir: Path) -> int | None:
    meta_path = context_dir / _META_REL
    if not meta_path.is_file():
        return None
    try:
        return read_meta(meta_path).restyled_ruleset
    except (OSError, ValueError) as exc:
        raise RestyleRunError(f"cannot read {meta_path}: {exc}") from exc


def _open_run(context_dir: Path, run: str | None) -> fleet.FleetRun:
    """The named run (checked for kind) or the newest restyle run."""
    try:
        run_dir = fleet.resolve_run_dir(context_dir, run, kind=fleet.KIND_RESTYLE)
        if run_dir is None:
            raise RestyleRunError(
                "no restyle run — start one with `dummyindex context restyle begin --all`"
            )
        loaded = fleet.load_run(run_dir)
    except fleet.FleetRunError as exc:
        raise RestyleRunError(str(exc)) from exc
    if loaded.kind != fleet.KIND_RESTYLE:
        raise RestyleRunError(
            f"{loaded.run_dir.name} is a {loaded.kind} run, not a restyle run"
        )
    return loaded


def _unfinished_run(context_dir: Path) -> str | None:
    newest = fleet.find_newest_run(context_dir, fleet.KIND_RESTYLE)
    if newest is None:
        return None
    try:
        loaded = fleet.load_run(newest)
    except fleet.FleetRunError as exc:
        raise RestyleRunError(str(exc)) from exc
    return None if fleet.run_status(loaded)["complete"] else newest.name


def _unit_stage(run: fleet.FleetRun, unit_id: str) -> int:
    for unit in run.units:
        if unit.feature_id == unit_id:
            return unit.stage
    raise RestyleRunError(f"run {run.run_dir.name} has no unit {unit_id!r}")


def _cache_dir(context_dir: Path, run_name: str) -> Path:
    return context_dir / "cache" / "restyle" / run_name


def _read_snapshot(context_dir: Path, run_name: str) -> dict[str, dict[str, int]]:
    path = _cache_dir(context_dir, run_name) / SNAPSHOT_NAME
    if not path.is_file():
        raise RestyleRunError(f"no snapshot for run {run_name} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RestyleRunError(f"cannot read {path}: {exc}") from exc
