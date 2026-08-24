"""Fleet-run domain: checkpointed multi-proposal execution state.

A fleet run coordinates SEVERAL proposals ("units") executed in parallel by
host-side orchestrators, each in its own worktree. The deterministic CLI owns
everything that must survive a crash:

- ``init_run`` scaffolds ``.context/fleet/run-<id>/`` with a human-readable
  ``RUN-MANIFEST.md`` (written FIRST) and machine state ``state.json``
  (written LAST) — both atomic, both **committed** (the ``gc/state.json``
  precedent for committing run artifacts).
- ``load_run`` reads a run back and fails LOUD on anything corrupt. Unlike
  ``gc/anchor.py``'s tolerate-to-``None`` precedent this is deliberate:
  fleet state is the single recovery path for an overnight run, so silently
  degrading would strand it. The raised error carries repair instructions.
- ``next_units`` is the dispatch frontier: up to ``max_parallel`` pending
  units, earliest-priority first, never two whose member-path sets intersect
  (disjointness frozen at init into each unit's ``paths[]``), gated/blocked
  skipped until answered — the anti-stall rule. At/over budget cap every
  response is a ``BUDGET-HALT`` envelope carrying exact resume steps.
- ``checkpoint`` / ``add_spend`` mutate through a read-modify-write loop
  serialized by an exclusive lock file (atomic replace alone is
  last-writer-wins), so concurrent checkpoint/spend never loses increments.
- ``merge_order`` projects landing order with disjointness rationale.

No LLM in-process; no ``print`` here — the CLI prints. Tracker-agnostic:
intake entries carry ``{ticket, title, paths[]}``; host-only metadata
(``repo_hint``, ``size``, …) is ignored by this module.
"""

from __future__ import annotations

import dataclasses
import json
import os
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .atomic_io import write_text_atomic

# The `.context/` namespace this domain owns. Maintenance runs share the
# directory under the `maintain-*` prefix; discovery here only ever
# considers `run-*`.
FLEET_REL = "fleet"
RUN_PREFIX = "run-"
MANIFEST_NAME = "RUN-MANIFEST.md"
STATE_NAME = "state.json"

DEFAULT_BRANCH_TEMPLATE = "{run}/{id}-{slug}"

_SLUG_OK_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_")
_TEMPLATE_TOKENS = ("{run}", "{id}", "{slug}")

# RMW lock: bounded acquire retries; a lock older than this is stolen (the
# writer that made it either crashed or finished without unlinking).
_LOCK_ATTEMPTS = 200
_LOCK_RETRY_SECONDS = 0.005
_LOCK_STALE_SECONDS = 30.0

_UNIT_NOTE_CAP = 20


class FleetUnitStatus(str, Enum):
    """Closed status alphabet for one unit of a fleet run."""

    PENDING = "pending"
    PLANNING = "planning"
    BUILDING = "building"
    MERGING = "merging"
    DONE = "done"
    BLOCKED = "blocked"
    GATED = "gated"

    # Render as the value ("gated"), never the enum repr — matches every
    # other closed-alphabet enum in this codebase.
    __str__ = str.__str__


_STATUS_ALPHABET = frozenset(s.value for s in FleetUnitStatus)


class FleetError(Exception):
    """Base class for every fleet-run failure."""


class FleetSlugError(FleetError):
    """A unit slug / --plans slug is not a safe lowercase token."""


class FleetInitError(FleetError):
    """`init` refuses: zero units, duplicate slugs, or a bad flag value."""


class FleetStateCorruptError(FleetError):
    """Loud failure: the run dir is missing, torn, or its state is corrupt."""


class FleetUnitError(FleetError):
    """Unknown unit id or an invalid checkpoint/spend argument."""


class FleetLockError(FleetError):
    """Another writer held the run's RMW lock past the retry budget."""


# ----- models ---------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class UnitSpec:
    """One requested unit at init time, before ids are minted.

    Priority is list position: index 0 dispatches first. ``paths`` freezes
    the file-disjointness contract for the whole run — later plan edits can
    never mutate a running fleet.
    """

    slug: str
    paths: tuple[str, ...] = ()
    ticket: str | None = None
    title: str | None = None


@dataclasses.dataclass(frozen=True)
class FleetUnit:
    """A single proposal-sized unit of work inside a fleet run."""

    id: str
    slug: str
    branch: str
    status: str  # a FleetUnitStatus value
    paths: tuple[str, ...]
    revision: int = 0  # per-unit checkpoint counter
    wave: int | None = None
    gate_question: str | None = None
    notes: tuple[str, ...] = ()
    spend_est_usd: float = 0.0
    ticket: str | None = None
    title: str | None = None


@dataclasses.dataclass(frozen=True)
class Budget:
    """The spend circuit-breaker meter."""

    cap_usd: float
    spent_est_usd: float = 0.0


@dataclasses.dataclass(frozen=True)
class FleetRunState:
    """Whole machine state of one run — `state.json`, the single truth."""

    run_id: str
    units: tuple[FleetUnit, ...]  # stored in priority order (index == priority)
    budget: Budget
    max_parallel: int
    branch_template: str
    rulings: tuple[tuple[str, str], ...] = ()
    created: str = ""
    revision: int = 1  # monotonic whole-file RMW counter

    def unit(self, unit_id: str) -> FleetUnit:
        for unit in self.units:
            if unit.id == unit_id:
                return unit
        valid = ", ".join(u.id for u in self.units)
        raise FleetUnitError(
            f"unknown unit {unit_id!r} in run {self.run_id} (units: {valid})"
        )


@dataclasses.dataclass(frozen=True)
class NextEnvelope:
    """What `fleet next` returns — always a valid envelope, never a raise.

    ``status`` is ``"ok"`` or ``"BUDGET-HALT"``; a halt carries exact
    ``resume`` instructions and no units. An empty-but-valid ``ok``
    envelope (every unit gated/blocked) is the anti-stall guarantee.
    """

    status: str  # "ok" | "BUDGET-HALT"
    run_id: str
    units: tuple[FleetUnit, ...]
    skipped: tuple[tuple[str, str], ...] = ()  # (unit_id, reason)
    resume: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "run": self.run_id,
            "units": [_unit_dict(u) for u in self.units],
            "skipped": [{"id": uid, "reason": why} for uid, why in self.skipped],
            "resume": list(self.resume),
        }


@dataclasses.dataclass(frozen=True)
class MergeEntry:
    """One row of the projected landing order."""

    unit: FleetUnit
    position: int
    landed: bool  # status == done → lands now; others project after it
    reason: str


# ----- paths ----------------------------------------------------------------


def fleet_root(context_dir: Path) -> Path:
    """``.context/fleet/`` for a given ``.context/`` directory."""
    return context_dir / FLEET_REL


def run_dir_for(context_dir: Path, run_id: str) -> Path:
    return fleet_root(context_dir) / f"{RUN_PREFIX}{run_id}"


def latest_run_dir(context_dir: Path) -> Path | None:
    """Newest ``run-*`` dir, prefix-scoped (never a ``maintain-*`` sibling).

    Run ids are zero-padded numerics, so lexicographic order IS numeric
    order — deterministic without touching mtimes. ``None`` when no runs
    exist yet.
    """
    root = fleet_root(context_dir)
    if not root.is_dir():
        return None
    runs = sorted(
        (p for p in root.iterdir() if p.is_dir() and p.name.startswith(RUN_PREFIX)),
        key=lambda p: p.name,
    )
    return runs[-1] if runs else None


def resolve_run_dir(context_dir: Path, explicit: Path | None = None) -> Path:
    """Explicit ``--run DIR`` wins; else default discovery is prefix-scoped
    to the newest ``run-*`` dir only."""
    if explicit is not None:
        return explicit
    found = latest_run_dir(context_dir)
    if found is None:
        raise FleetStateCorruptError(
            _repair_note(
                f"no run-* directory exists under {fleet_root(context_dir)} — "
                "initialize one with `dummyindex context fleet init "
                "--plans <slug[,slug…]> …`."
            )
        )
    return found


def _repair_note(detail: str) -> str:
    """Every loud failure names the recovery path — state is all there is."""
    return (
        f"{detail} Fleet state.json is the single source of truth for the "
        "run and is deliberately NOT tolerated-silent: repair it by hand "
        "(restore valid JSON / restore RUN-MANIFEST.md), archive the run "
        "dir out of `.context/fleet/`, or re-init a fresh run with "
        "`dummyindex context fleet init …` and replay checkpoints from "
        "RUN-MANIFEST.md."
    )


# ----- serialization --------------------------------------------------------


def _unit_dict(unit: FleetUnit) -> dict:
    out: dict = {
        "id": unit.id,
        "slug": unit.slug,
        "branch": unit.branch,
        "status": unit.status,
        "paths": list(unit.paths),
        "revision": unit.revision,
    }
    if unit.wave is not None:
        out["wave"] = unit.wave
    if unit.gate_question is not None:
        out["gate_question"] = unit.gate_question
    if unit.notes:
        out["notes"] = list(unit.notes)
    if unit.spend_est_usd:
        out["spend_est_usd"] = unit.spend_est_usd
    if unit.ticket is not None:
        out["ticket"] = unit.ticket
    if unit.title is not None:
        out["title"] = unit.title
    return out


def _state_dict(state: FleetRunState) -> dict:
    return {
        "run_id": state.run_id,
        "created": state.created,
        "revision": state.revision,
        "max_parallel": state.max_parallel,
        "branch_template": state.branch_template,
        "rulings": [[k, v] for k, v in state.rulings],
        "budget": {
            "cap_usd": state.budget.cap_usd,
            "spent_est_usd": state.budget.spent_est_usd,
        },
        "units": [_unit_dict(u) for u in state.units],
    }


def _corrupt(run_dir: Path, detail: str) -> FleetStateCorruptError:
    return FleetStateCorruptError(_repair_note(f"{run_dir / STATE_NAME}: {detail}"))


def _require(cond: object, run_dir: Path, detail: str) -> None:
    if not cond:
        raise _corrupt(run_dir, detail)


def state_from_dict(payload: object, run_dir: Path) -> FleetRunState:
    """Strict inverse of :func:`_state_dict` — anything off-shape fails LOUD."""
    _require(isinstance(payload, dict), run_dir, "payload is not a JSON object")
    assert isinstance(payload, dict)  # narrowed for the type checker
    _require(
        isinstance(payload.get("run_id"), str) and bool(payload["run_id"]),
        run_dir,
        "missing string 'run_id'",
    )
    _require(
        isinstance(payload.get("revision"), int) and payload["revision"] >= 1,
        run_dir,
        "missing positive integer 'revision'",
    )
    _require(
        isinstance(payload.get("max_parallel"), int) and payload["max_parallel"] >= 1,
        run_dir,
        "missing positive integer 'max_parallel'",
    )
    _require(
        isinstance(payload.get("branch_template"), str)
        and bool(payload["branch_template"]),
        run_dir,
        "missing string 'branch_template'",
    )

    budget = payload.get("budget")
    _require(isinstance(budget, dict), run_dir, "missing 'budget' object")
    assert isinstance(budget, dict)
    cap = budget.get("cap_usd")
    spent = budget.get("spent_est_usd", 0.0)
    for name, value in (("cap_usd", cap), ("spent_est_usd", spent)):
        _require(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value >= 0,
            run_dir,
            f"budget.{name} must be a non-negative number",
        )

    rulings_raw = payload.get("rulings", [])
    _require(isinstance(rulings_raw, list), run_dir, "'rulings' must be a list")
    assert isinstance(rulings_raw, list)
    rulings: list[tuple[str, str]] = []
    for pair in rulings_raw:
        _require(
            isinstance(pair, list)
            and len(pair) == 2
            and all(isinstance(part, str) for part in pair),
            run_dir,
            "each ruling must be a [key, value] pair of strings",
        )
        assert isinstance(pair, list)
        rulings.append((str(pair[0]), str(pair[1])))

    units_raw = payload.get("units")
    _require(isinstance(units_raw, list), run_dir, "missing 'units' list")
    assert isinstance(units_raw, list)
    _require(bool(units_raw), run_dir, "'units' is empty — a run is never zero-unit")
    units: list[FleetUnit] = []
    seen_ids: set[str] = set()
    seen_slugs: set[str] = set()
    for raw in units_raw:
        _require(isinstance(raw, dict), run_dir, "each unit must be a JSON object")
        assert isinstance(raw, dict)
        uid = raw.get("id")
        slug = raw.get("slug")
        status = raw.get("status")
        branch = raw.get("branch")
        paths = raw.get("paths")
        _require(isinstance(uid, str) and bool(uid), run_dir, f"bad unit id {uid!r}")
        _require(str(uid) not in seen_ids, run_dir, f"duplicate unit id {uid!r}")
        seen_ids.add(str(uid))
        _require(
            isinstance(slug, str) and bool(slug) and slug not in seen_slugs,
            run_dir,
            f"bad or duplicate unit slug {slug!r}",
        )
        seen_slugs.add(str(slug))
        _require(
            status in _STATUS_ALPHABET,
            run_dir,
            f"unit {uid!r}: unknown status {status!r} "
            f"(alphabet: {sorted(_STATUS_ALPHABET)})",
        )
        _require(
            isinstance(branch, str) and bool(branch),
            run_dir,
            f"unit {uid!r}: bad branch",
        )
        _require(
            isinstance(paths, list) and all(isinstance(p, str) for p in paths),
            run_dir,
            f"unit {uid!r}: 'paths' must be a list of strings",
        )
        gate = raw.get("gate_question")
        wave = raw.get("wave")
        notes = raw.get("notes", [])
        spend = raw.get("spend_est_usd", 0.0)
        _require(
            gate is None or isinstance(gate, str),
            run_dir,
            f"unit {uid!r}: gate_question must be a string or null",
        )
        _require(
            wave is None or (isinstance(wave, int) and not isinstance(wave, bool)),
            run_dir,
            f"unit {uid!r}: wave must be an integer or null",
        )
        _require(
            isinstance(notes, list) and all(isinstance(n, str) for n in notes),
            run_dir,
            f"unit {uid!r}: 'notes' must be a list of strings",
        )
        _require(
            isinstance(spend, (int, float))
            and not isinstance(spend, bool)
            and spend >= 0,
            run_dir,
            f"unit {uid!r}: spend_est_usd must be a non-negative number",
        )
        assert (
            isinstance(uid, str)
            and isinstance(slug, str)
            and isinstance(status, str)
            and isinstance(branch, str)
            and isinstance(paths, list)
        )
        units.append(
            FleetUnit(
                id=uid,
                slug=slug,
                branch=branch,
                status=status,
                paths=tuple(str(p) for p in paths),
                revision=int(raw.get("revision", 0)),
                wave=wave,
                gate_question=gate,
                notes=tuple(notes),
                spend_est_usd=float(spend),
                ticket=raw.get("ticket"),
                title=raw.get("title"),
            )
        )

    return FleetRunState(
        run_id=str(payload["run_id"]),
        units=tuple(units),
        budget=Budget(cap_usd=float(cap), spent_est_usd=float(spent)),
        max_parallel=int(payload["max_parallel"]),
        branch_template=str(payload["branch_template"]),
        rulings=tuple(rulings),
        created=str(payload.get("created", "")),
        revision=int(payload["revision"]),
    )


# ----- load / save ----------------------------------------------------------


def load_run(run_dir: Path) -> FleetRunState:
    """Read a run back; fail loud on anything short of a complete, valid run.

    Init ordering contract: RUN-MANIFEST.md is written first, state.json
    last — so a dir holding a state.json but no manifest is a torn init.
    Loud errors, never tolerant ``None``s: this state is the only recovery
    path an overnight run has.
    """
    if not run_dir.is_dir():
        raise FleetStateCorruptError(
            _repair_note(f"{run_dir} does not exist (no such fleet run).")
        )
    if not (run_dir / MANIFEST_NAME).is_file():
        raise FleetStateCorruptError(
            _repair_note(f"{run_dir / MANIFEST_NAME} is missing — a torn init.")
        )
    state_path = run_dir / STATE_NAME
    if not state_path.is_file():
        raise FleetStateCorruptError(
            _repair_note(f"{state_path} is missing — the run never went live.")
        )
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        raise _corrupt(run_dir, f"invalid JSON ({exc})") from exc
    return state_from_dict(payload, run_dir)


def write_state(run_dir: Path, state: FleetRunState) -> None:
    """Atomically persist ``state.json`` (trailing newline, EOF-fixer-clean)."""
    text = json.dumps(_state_dict(state), indent=2) + "\n"
    write_text_atomic(run_dir / STATE_NAME, text)


# ----- read-modify-write ----------------------------------------------------


def _acquire_lock(run_dir: Path) -> Path:
    lock = run_dir / ".lock"
    for attempt in range(_LOCK_ATTEMPTS):
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                stale = time.time() - lock.stat().st_mtime > _LOCK_STALE_SECONDS
            except OSError:
                stale = False
            if stale:
                lock.unlink(missing_ok=True)  # steal a crashed writer's lock
                continue
            time.sleep(_LOCK_RETRY_SECONDS * (attempt % 10 + 1))
            continue
        else:
            os.write(handle, f"{os.getpid()}".encode())
            os.close(handle)
            return lock
    raise FleetLockError(
        f"could not acquire the run lock {lock} after {_LOCK_ATTEMPTS} attempts; "
        "if no other writer is alive, remove the stale `.lock` file by hand."
    )


def mutate_run(
    run_dir: Path, mutate: Callable[[FleetRunState], FleetRunState]
) -> FleetRunState:
    """Serialized read-modify-write of ``state.json``.

    The atomic replace underneath is last-writer-wins, so bare concurrent
    checkpoint/spend calls could silently drop increments. The exclusive
    ``.lock`` file makes the whole read→mutate→write span single-file, and
    every successful mutation bumps the monotonic ``revision`` counter.
    Raises :class:`FleetLockError` past the retry budget rather than
    writing blind.
    """
    lock = _acquire_lock(run_dir)
    try:
        state = load_run(run_dir)
        new_state = dataclasses.replace(mutate(state), revision=state.revision + 1)
        write_state(run_dir, new_state)
        return new_state
    finally:
        lock.unlink(missing_ok=True)


# ----- init -----------------------------------------------------------------


def _validate_slug(slug: str) -> str:
    if not slug or not slug.strip():
        raise FleetSlugError("unit slug must not be empty")
    lowered = slug.strip().lower()
    if any(ch not in _SLUG_OK_CHARS for ch in lowered):
        raise FleetSlugError(
            f"unit slug {slug!r} must be lowercase letters, digits, '-', '_'"
        )
    if lowered.startswith("-") or lowered.endswith("-"):
        raise FleetSlugError(f"unit slug {slug!r} must not start or end with '-'")
    return lowered


def _validate_branch_template(template: str) -> str:
    stripped = template.strip()
    if "{id}" not in stripped or "{slug}" not in stripped:
        raise FleetInitError(
            f"--branch-template {template!r} must contain {{id}} and {{slug}} "
            f"(tokens: {', '.join(_TEMPLATE_TOKENS)})"
        )
    if ".." in stripped:
        raise FleetInitError(f"--branch-template {template!r} must not contain '..'")
    return stripped


def render_branch(template: str, run_id: str, unit_id: str, slug: str) -> str:
    """Token-replace ``{run}``/``{id}``/``{slug}``.

    Never ``str.format`` — a caller's template may carry stray braces.
    """
    out = template.replace("{run}", run_id).replace("{id}", unit_id)
    return out.replace("{slug}", slug)


def next_run_id(context_dir: Path) -> str:
    """Max existing numeric suffix + 1, zero-padded to width 4."""
    root = fleet_root(context_dir)
    highest = 0
    if root.is_dir():
        for entry in root.iterdir():
            name = entry.name
            if entry.is_dir() and name.startswith(RUN_PREFIX):
                suffix = name[len(RUN_PREFIX) :]
                if suffix.isdigit():
                    highest = max(highest, int(suffix))
    return f"{highest + 1:04d}"


def validate_unit_specs(specs: Sequence[UnitSpec]) -> list[UnitSpec]:
    """Charset-check slugs; refuse a zero-unit run and duplicate slugs."""
    if not specs:
        raise FleetInitError(
            "refusing to init a zero-unit run — pass --plans SLUG[,SLUG…] "
            "or --intake FILE with at least one unit"
        )
    normalized: list[UnitSpec] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for spec in specs:
        safe = _validate_slug(spec.slug)
        if safe in seen and safe not in duplicates:
            duplicates.append(safe)
        seen.add(safe)
        normalized.append(dataclasses.replace(spec, slug=safe))
    if duplicates:
        raise FleetInitError(
            "refusing duplicate unit slugs: " + ", ".join(sorted(duplicates))
        )
    return normalized


def units_from_intake(payload: object) -> list[UnitSpec]:
    """Parse host-produced intake JSON into :class:`UnitSpec`s.

    Shape: ``{"units": [{"ticket": "…", "title": "…", "paths": ["a.py"], …}]}``.
    Host-only metadata keys (``repo_hint``, ``size``, …) are ignored here —
    the CLI stays tracker-agnostic. A missing ``ticket`` falls back to
    ``unit-<n>`` so an intake without ids still inits deterministically.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("units"), list):
        raise FleetInitError('--intake FILE must hold {"units": [...]}')
    specs: list[UnitSpec] = []
    for i, entry in enumerate(payload["units"]):
        if not isinstance(entry, dict):
            raise FleetInitError(f"intake unit #{i + 1} is not an object")
        ticket = entry.get("ticket")
        title = entry.get("title")
        paths_raw = entry.get("paths", [])
        if not isinstance(paths_raw, list) or not all(
            isinstance(p, str) for p in paths_raw
        ):
            raise FleetInitError(
                f"intake unit #{i + 1} ({ticket!r}): 'paths' must be a list "
                "of relative-path strings"
            )
        specs.append(
            UnitSpec(
                slug=str(ticket) if ticket else f"unit-{i + 1}",
                paths=tuple(dict.fromkeys(p for p in paths_raw if p)),
                ticket=str(ticket) if ticket is not None else None,
                title=str(title) if title is not None else None,
            )
        )
    return specs


def units_from_plans(
    context_dir: Path, slugs: Sequence[str]
) -> tuple[list[UnitSpec], list[str]]:
    """Build specs from ``proposals/<slug>/proposal.json`` (``--plans`` mode).

    Reads each proposal's optional ``member_files`` as its frozen paths;
    absent/empty yields an empty path set — the caller surfaces the
    conservative-serial warning. Returns ``(specs, warnings)``.
    """
    specs: list[UnitSpec] = []
    warnings: list[str] = []
    proposals_root = context_dir / "proposals"
    for slug in slugs:
        safe = _validate_slug(slug)
        proposal_json = proposals_root / safe / "proposal.json"
        if not proposal_json.is_file():
            raise FleetSlugError(
                f"--plans slug {safe!r}: {proposal_json} not found — "
                "scaffold it with `dummyindex context propose --slug …` first"
            )
        try:
            payload = json.loads(proposal_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
            raise FleetSlugError(f"{proposal_json} is invalid JSON ({exc})") from exc
        member_files = (
            payload.get("member_files") if isinstance(payload, dict) else None
        )
        paths: tuple[str, ...] = ()
        if isinstance(member_files, list) and all(
            isinstance(p, str) for p in member_files
        ):
            paths = tuple(dict.fromkeys(p for p in member_files if p))
        if not paths:
            warnings.append(
                f"{safe}: proposal.json has no usable member_files — scheduling "
                "serially (conservative intersection with every unit)"
            )
        title = payload.get("title") if isinstance(payload, dict) else None
        specs.append(UnitSpec(slug=safe, paths=paths, title=title))
    return specs, warnings


def init_run(
    context_dir: Path,
    specs: Sequence[UnitSpec],
    *,
    budget_usd: float,
    max_parallel: int,
    branch_template: str = DEFAULT_BRANCH_TEMPLATE,
    rulings: Sequence[tuple[str, str]] = (),
) -> tuple[FleetRunState, list[str]]:
    """Scaffold ``.context/fleet/run-<id>/`` and go live.

    Writes ``RUN-MANIFEST.md`` FIRST and ``state.json`` LAST — the ordering
    :func:`load_run` enforces. Per-unit ``paths[]`` freeze here; later plan
    edits never mutate a running fleet. Returns ``(state, warnings)`` where
    warnings record conservative-serial units (no frozen paths).

    Refuses: zero-unit runs, duplicate slugs, non-positive budgets,
    ``max_parallel < 1``, branch templates without ``{id}``/``{slug}``, and
    a re-init over an already-live run id.
    """
    checked = validate_unit_specs(specs)
    if not (budget_usd > 0):
        raise FleetInitError(f"--budget-usd must be > 0, got {budget_usd!r}")
    if max_parallel < 1:
        raise FleetInitError(f"--max-parallel must be >= 1, got {max_parallel!r}")
    template = _validate_branch_template(branch_template)

    run_id = next_run_id(context_dir)
    target = run_dir_for(context_dir, run_id)
    if target.exists():
        raise FleetInitError(
            f"refusing to overwrite existing run dir {target} — archive it "
            "away or pass a fresh location first"
        )

    units: list[FleetUnit] = []
    warnings: list[str] = []
    for i, spec in enumerate(checked):
        unit_id = f"u{i + 1:02d}"
        paths = tuple(dict.fromkeys(spec.paths))
        units.append(
            FleetUnit(
                id=unit_id,
                slug=spec.slug,
                branch=render_branch(template, run_id, unit_id, spec.slug),
                status=FleetUnitStatus.PENDING.value,
                paths=paths,
                ticket=spec.ticket,
                title=spec.title,
            )
        )
        if not paths:
            warnings.append(
                f"{unit_id} ({spec.slug}): no member paths known — scheduling "
                "serially (conservative intersection with every unit)"
            )

    state = FleetRunState(
        run_id=run_id,
        units=tuple(units),
        budget=Budget(cap_usd=float(budget_usd)),
        max_parallel=max_parallel,
        branch_template=template,
        rulings=tuple(rulings),
        created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    # Ordering contract: manifest first, state last. A crash between the two
    # leaves a dir load_run refuses (torn init), never a half-live run.
    write_text_atomic(target / MANIFEST_NAME, _render_manifest(state, warnings))
    write_state(target, state)
    return state, warnings


# ----- dispatch frontier ----------------------------------------------------


def _paths_conflict(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Conservative disjointness: an empty path set intersects EVERYTHING
    (including another empty set) — unknown overlap means serialize."""
    if not a or not b:
        return True
    return not set(a).isdisjoint(b)


def budget_halted(state: FleetRunState) -> bool:
    """True once the meter has reached the cap — the breaker is latched."""
    return state.budget.spent_est_usd >= state.budget.cap_usd


def _halt_resume(state: FleetRunState) -> tuple[str, ...]:
    over = max(state.budget.spent_est_usd - state.budget.cap_usd, 0.0)
    # The breaker latches at spent >= cap, so correcting by exactly the
    # overshoot would land ON the cap and stay halted — the suggested
    # reduction clears strictly below it.
    correction = round(over + 0.01, 2)
    return (
        f"BUDGET-HALT: run {state.run_id} spent ${state.budget.spent_est_usd:.2f} "
        f"of its ${state.budget.cap_usd:.2f} cap "
        f"(over by ${over:.2f}). No units will dispatch until the "
        "meter drops below the cap.",
        "Resume: correct the meter with a checkpointed reduction against the "
        "unit that ran over, e.g.",
        f"  dummyindex context fleet spend --unit <id> --est-usd -{correction:.2f} "
        "--adjust",
        "then re-run `dummyindex context fleet next --run <dir>` — the breaker "
        "clears only via `spend --adjust`, never silently.",
    )


def next_units(state: FleetRunState) -> NextEnvelope:
    """The dispatch frontier: priority order, parallel cap, file-disjointness.

    - candidates are PENDING units in stored (priority) order; sort key
      ``(priority, unit_id)`` with stable tie traversal;
    - a candidate is taken only when its frozen ``paths[]`` are disjoint
      from every already-taken unit's (empty sets conflict with everything);
    - gated / blocked / in-flight units are skipped with reasons — gated
      forever until answered by a later checkpoint (anti-stall);
    - at/over budget cap: a ``BUDGET-HALT`` envelope with resume steps.
    """
    if budget_halted(state):
        return NextEnvelope(
            status="BUDGET-HALT",
            run_id=state.run_id,
            units=(),
            resume=_halt_resume(state),
        )

    chosen: list[FleetUnit] = []
    taken_paths: list[tuple[str, ...]] = []
    skipped: list[tuple[str, str]] = []
    # Deterministic traversal: sort key (priority, unit_id) where priority is
    # the unit's init order (its index in the stored tuple).
    priority = {u.id: i for i, u in enumerate(state.units)}
    for unit in sorted(state.units, key=lambda u: (priority[u.id], u.id)):
        if unit.status == FleetUnitStatus.GATED.value:
            reason = "gated until answered"
            if unit.gate_question:
                reason += f": {unit.gate_question}"
            skipped.append((unit.id, reason))
            continue
        if unit.status == FleetUnitStatus.BLOCKED.value:
            skipped.append((unit.id, "blocked"))
            continue
        if unit.status != FleetUnitStatus.PENDING.value:
            skipped.append((unit.id, f"in-flight ({unit.status})"))
            continue
        if len(chosen) >= state.max_parallel:
            skipped.append((unit.id, "parallel cap reached this round"))
            continue
        if any(_paths_conflict(unit.paths, other) for other in taken_paths):
            skipped.append(
                (
                    unit.id,
                    "member paths intersect an already-dispatched unit"
                    if unit.paths or taken_paths
                    else "no member paths known — serialized conservatively",
                )
            )
            continue
        chosen.append(unit)
        taken_paths.append(unit.paths)

    return NextEnvelope(
        status="ok", run_id=state.run_id, units=tuple(chosen), skipped=tuple(skipped)
    )


# ----- mutations (each revision-bumped through mutate_run) ------------------


def _replace_unit(state: FleetRunState, updated: FleetUnit) -> FleetRunState:
    return dataclasses.replace(
        state,
        units=tuple(updated if u.id == updated.id else u for u in state.units),
    )


def checkpoint(
    run_dir: Path,
    unit_id: str,
    *,
    status: str | None = None,
    wave: int | None = None,
    gate: str | None = None,
    note: str | None = None,
) -> FleetRunState:
    """Advance one unit; ``--gate`` parks it as ``gated`` (the anti-stall rule).

    Gate semantics:
    - a non-empty ``gate`` question forces status to ``gated`` and records
      the question — `next` skips the unit until answered;
    - checkpointing an already-gated unit with an explicit ``status`` and no
      new question ANSWERS the gate: question clears, status lands;
    - a note-only / wave-only checkpoint is allowed for progress.

    Every call is a locked read-modify-write: concurrent checkpoint/spend
    never loses an increment.
    """
    if gate is not None and not gate.strip():
        raise FleetUnitError(
            "--gate must be a non-empty question (omit it to answer/clear)"
        )
    if status is not None and status not in _STATUS_ALPHABET:
        raise FleetUnitError(
            f"unknown --status {status!r} (alphabet: {sorted(_STATUS_ALPHABET)})"
        )

    def apply(state: FleetRunState) -> FleetRunState:
        current = state.unit(unit_id)
        notes = current.notes
        if note:
            notes = (*notes, note.strip())[-_UNIT_NOTE_CAP:]
        next_wave = wave if wave is not None else current.wave
        gated_now = gate is not None
        if gated_now:
            next_status = FleetUnitStatus.GATED.value
            next_gate: str | None = gate.strip()
        elif current.status == FleetUnitStatus.GATED.value and status is None:
            raise FleetUnitError(
                f"{unit_id} is gated on: {current.gate_question!r}. Answer it "
                "by passing --status (and --note carrying the answer)."
            )
        elif status is not None:
            # A plain transition — and any checkpoint that supplies a status
            # to a gated unit ANSWERS its recorded question (clears it).
            next_status = status
            next_gate = None
        else:
            next_status = current.status
            next_gate = current.gate_question
        updated = dataclasses.replace(
            current,
            status=next_status,
            gate_question=next_gate,
            wave=next_wave,
            notes=notes,
            revision=current.revision + 1,
        )
        return _replace_unit(state, updated)

    return mutate_run(run_dir, apply)


def add_spend(
    run_dir: Path,
    unit_id: str,
    est_usd: float,
    *,
    adjust: bool = False,
) -> FleetRunState:
    """Accumulate the breaker meter (and the unit's own tally).

    Negative deltas require ``adjust=True`` — a correction against the
    metered total, the documented resume path after a BUDGET-HALT. A bare
    negative add is refused as a probable typo; so is a correction that
    would drive the run meter (or the unit tally) below zero.
    """
    if est_usd < 0 and not adjust:
        raise FleetUnitError(
            "negative spend needs --adjust (a recorded correction), "
            "not a plain meter add"
        )

    def apply(state: FleetRunState) -> FleetRunState:
        current = state.unit(unit_id)
        new_spent = round(state.budget.spent_est_usd + est_usd, 2)
        if new_spent < 0:
            raise FleetUnitError(
                f"correction {est_usd} would drive the run meter negative "
                f"(currently {state.budget.spent_est_usd})"
            )
        new_unit_spend = max(round(current.spend_est_usd + est_usd, 2), 0.0)
        updated_budget = Budget(cap_usd=state.budget.cap_usd, spent_est_usd=new_spent)
        return _replace_unit(
            dataclasses.replace(state, budget=updated_budget),
            dataclasses.replace(current, spend_est_usd=new_unit_spend),
        )

    return mutate_run(run_dir, apply)


# ----- merge order ----------------------------------------------------------


def merge_order(state: FleetRunState) -> tuple[MergeEntry, ...]:
    """Projected landing order with disjointness rationale.

    Done units land first (priority order); every other unit follows in
    priority order as its projected landing slot. Rationale cites the first
    earlier unit whose member paths intersect (must land after it) or marks
    the row parallel-safe.
    """
    priority = {u.id: i for i, u in enumerate(state.units)}
    ordered = sorted(state.units, key=lambda u: (priority[u.id], u.id))
    done = [u for u in ordered if u.status == FleetUnitStatus.DONE.value]
    rest = [u for u in ordered if u.status != FleetUnitStatus.DONE.value]

    entries: list[MergeEntry] = []
    landed_paths: list[tuple[str, ...]] = []
    for position, unit in enumerate([*done, *rest]):
        conflict = next(
            (
                prior
                for prior, paths in zip(
                    [e.unit for e in entries], landed_paths, strict=True
                )
                if _paths_conflict(unit.paths, paths)
            ),
            None,
        )
        if conflict is not None:
            shared = sorted(set(unit.paths) & set(conflict.paths))
            reason = f"lands after {conflict.id}: shares {', '.join(shared)}"
        elif not entries:
            reason = "first to land"
        else:
            reason = "parallel-safe with all above (disjoint paths)"
        entries.append(
            MergeEntry(unit=unit, position=position, landed=unit in done, reason=reason)
        )
        landed_paths.append(unit.paths)
    return tuple(entries)


# ----- RUN-MANIFEST.md rendering --------------------------------------------

_MAGIC_WORDS = (
    ("DONE", "unit complete, verified in the foreground, ready to merge"),
    ("BLOCKED", "cannot proceed — the report must say why"),
    ("GATED", "parked on its recorded gate question; `next` skips it until answered"),
)

_TRAILER_BLOCKLIST = ("Reviewed-by:", "Signed-off-by:", "Co-authored-by:")


def _render_manifest(state: FleetRunState, warnings: Sequence[str]) -> str:
    """Human-readable run contract (written FIRST, before state.json)."""
    lines: list[str] = [
        f"# Fleet run {RUN_PREFIX}{state.run_id}",
        "",
        f"Created: {state.created or '(unset)'}",
        f"Branch template: `{state.branch_template}`",
        f"Max parallel: {state.max_parallel}",
        f"Budget cap: ${state.budget.cap_usd:.2f} "
        f"(metered: ${state.budget.spent_est_usd:.2f})",
        "",
        "## Units (priority order = dispatch order)",
        "",
        "| # | id | slug | branch | member paths | status |",
        "|---|---|---|---|---|---|",
    ]
    for i, unit in enumerate(state.units):
        paths = ", ".join(unit.paths) if unit.paths else "(none — serialized)"
        ticket = f" [{unit.ticket}]" if unit.ticket else ""
        title = f" — {unit.title}" if unit.title else ""
        lines.append(
            f"| {i + 1} | {unit.id} | {unit.slug}{ticket}{title} | "
            f"`{unit.branch}` | {paths} | {unit.status} |"
        )
    lines += ["", "## Rulings", ""]
    if state.rulings:
        lines += [f"- `{k}={v}`" for k, v in state.rulings]
    else:
        lines.append("- (none recorded)")
    lines += [
        "",
        "## Commit policy",
        "",
        "- Conventional commit types only: `feat` `fix` `test` `docs` "
        "`refactor` `chore`.",
        "- Magic words (worker report vocabulary):",
    ]
    lines += [f"  - `{word}` — {meaning}" for word, meaning in _MAGIC_WORDS]
    lines += [
        "- Stage ONLY files your unit owns (its frozen `paths[]`) — never "
        "stage a file another unit owns.",
        "- Trailer blocklist — never append: "
        + ", ".join(f"`{t}`" for t in _TRAILER_BLOCKLIST),
    ]
    if warnings:
        lines += ["", "## Init warnings", ""]
        lines += [f"- {w}" for w in warnings]
    lines.append("")
    return "\n".join(lines)
