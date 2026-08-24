"""`dummyindex context evolve <verb>` — the self-improvement loop CLI.

Wire-only sibling of ``cli/gc.py``: parse this command's own flag alphabet,
lazy-import the ``context.domains.evolve`` domain inside ``run`` (the layering
rule — ``cli`` imports the domain, never the reverse), call a domain function,
print, return an exit code. No judgment lives here: trigger decisions arrive
only as host-produced observation files scored by the equip eval domain, and
the LLM steps (diagnosis authoring) live in the packaged
``dummyindex-evolve`` skill.

The six verbs:

- ``harvest [--since DATE] [--sleep] [--json] [--run NAME]`` — collect audit
  findings, session-memory corrections, reconcile deltas, and transcript
  adoption misses into ``<run>/harvest.json``. ``--sleep`` is the overnight
  contract: nothing new → exit 0 having written nothing at all.
- ``diagnose --run NAME --from-file FILE`` — validate host-authored
  candidates (structure, scope guard, citation existence; ≤5 candidates,
  ≤5 target files each) into ``<run>/candidates.jsonl``.
- ``apply --candidate N --run NAME`` — stage candidate N (0-based line) and
  run the three-stage gate; any errored/missing stage yields verdict
  ``blocked``, never pass.
- ``promote --candidate N --run NAME [--override REASON]`` — adopt the gated
  edit; a blocked verdict requires an explicit override, recorded in
  ``evolution.jsonl``.
- ``rollback|discard --candidate N --run NAME`` — revert an adopted edit /
  drop the staged copy.

Every transition appends exactly one line to ``.context/gc/evolution.jsonl``
(the committed decision history).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .common import resolve_context_root, usage_error

_EVOLVE_USAGE = (
    "usage: dummyindex context evolve "
    "harvest|diagnose|apply|promote|rollback|discard ..."
)


def run(args: list[str]) -> int:
    """`dummyindex context evolve harvest|diagnose|apply|promote|rollback|discard ...`."""
    if not args:
        print(f"error: {_EVOLVE_USAGE}", file=sys.stderr)
        return 2
    verb, rest = args[0], args[1:]
    handlers = {
        "harvest": _evolve_harvest,
        "diagnose": _evolve_diagnose,
        "apply": _evolve_apply,
        "promote": _evolve_promote,
        "rollback": _evolve_rollback,
        "discard": _evolve_discard,
    }
    handler = handlers.get(verb)
    if handler is None:
        print(
            "error: unknown evolve verb "
            f"{verb!r} (expected harvest|diagnose|apply|promote|rollback|discard)",
            file=sys.stderr,
        )
        return 2
    return handler(rest)


# ----- shared helpers --------------------------------------------------------


def _parse_flags(
    args: list[str],
    *,
    value_keys: set[str],
    bool_keys: set[str],
) -> tuple[dict[str, str], set[str], str | None]:
    """Parse ``--key value`` / ``--key=value`` / ``--flag`` arguments."""
    values: dict[str, str] = {}
    flags: set[str] = set()
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            return values, flags, f"unexpected argument: {token!r}"
        if "=" in token:
            name, inline_value = token[2:].split("=", 1)
            has_inline = True
        else:
            name, inline_value = token[2:], None
            has_inline = False
        if name in bool_keys:
            if has_inline:
                return values, flags, f"--{name} takes no value"
            flags.add(name)
            i += 1
            continue
        if name in value_keys:
            if has_inline:
                values[name] = inline_value or ""
                i += 1
            else:
                if i + 1 >= len(args):
                    return values, flags, f"--{name} requires a value"
                values[name] = args[i + 1]
                i += 2
            continue
        return values, flags, f"unknown argument: --{name}"
    return values, flags, None


def _context_dir(root: str | None) -> Path | None:
    explicit_root = Path(root) if root else None
    out_root = resolve_context_root(Path("."), explicit_root=explicit_root)
    context_dir = out_root / ".context"
    return context_dir if context_dir.is_dir() else None


def _missing_context() -> int:
    print(
        "error: .context not found. Run `dummyindex ingest` first.",
        file=sys.stderr,
    )
    return 2


def _candidate_index(raw: object) -> int | None:
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _load_candidate_lines(run_dir: Path) -> list[dict]:
    """Non-empty lines of ``candidates.jsonl`` as parsed objects (corrupt → [])."""
    from dummyindex.context.domains.evolve import CANDIDATES_NAME

    path = run_dir / CANDIDATES_NAME
    lines: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            lines.append(obj)
    return lines


# ----- verbs -----------------------------------------------------------------


def _evolve_harvest(args: list[str]) -> int:
    """`evolve harvest [--since DATE] [--sleep] [--json] [--run NAME]` (exit 0)."""
    from dummyindex.context.domains.atomic_io import write_text_atomic
    from dummyindex.context.domains.evolve import (
        EVOLVE_DIR_REL,
        HARVEST_NAME,
        check_predictions,
        mint_run_dir,
        record_event,
    )
    from dummyindex.context.domains.evolve import (
        harvest as harvest_domain,
    )

    values, flags, err = _parse_flags(
        args,
        value_keys={"since", "run", "root"},
        bool_keys={"sleep", "json"},
    )
    if err is not None:
        return usage_error("evolve", f"{err} (for `evolve harvest`)")

    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    project_root = context_dir.parent

    report = harvest_domain(
        context_dir,
        project_root,
        since=values.get("since"),
    )
    flipped = check_predictions(context_dir, report)

    # Sleep contract: nothing new → exit 0, write NOTHING (no run dir, no
    # event, no output). The fleet runner drives this overnight.
    if "sleep" in flags and not report.items and not flipped:
        return 0

    run_name = values.get("run") or ""
    base = context_dir / EVOLVE_DIR_REL
    if run_name:
        run_dir = base / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = mint_run_dir(context_dir)
    run_name = run_dir.name

    payload = {
        **report.to_dict(),
        "flipped_predictions": [
            {
                "targets": list(flag.targets),
                "prediction": flag.prediction,
                "matched_citations": list(flag.matched_citations),
            }
            for flag in flipped
        ],
    }
    write_text_atomic(
        run_dir / HARVEST_NAME,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    record_event(
        context_dir,
        {
            "kind": "harvest",
            "run": run_name,
            "evidence": [item.citation for item in report.items],
            "target": None,
            "outcome": {
                "items": len(report.items),
                "flipped_predictions": len(flipped),
            },
        },
    )
    if "json" in flags:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(
        f"context evolve harvest ({run_name}): "
        f"{len(report.items)} item(s), {len(flipped)} flipped prediction(s)"
    )
    for flag in flipped:
        print(
            f"  prediction flip: {', '.join(flag.targets)} — {flag.prediction}"
        )
    return 0


def _evolve_diagnose(args: list[str]) -> int:
    """`evolve diagnose --run NAME --from-file FILE [--json]`."""
    from dummyindex.context.domains.evolve import (
        CANDIDATES_NAME,
        HARVEST_NAME,
        MAX_CANDIDATES,
        EvolveError,
        parse_candidate,
        record_event,
        run_dir_for,
        validate_candidate,
    )

    values, flags, err = _parse_flags(
        args,
        value_keys={"run", "from-file", "root"},
        bool_keys={"json"},
    )
    if err is not None:
        return usage_error("evolve", f"{err} (for `evolve diagnose`)")
    if not values.get("run"):
        return usage_error("evolve", "--run NAME is required (for `evolve diagnose`)")
    if not values.get("from-file"):
        return usage_error(
            "evolve", "--from-file FILE is required (for `evolve diagnose`)"
        )
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    project_root = context_dir.parent

    try:
        run_dir = run_dir_for(context_dir, values["run"])
    except EvolveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not (run_dir / HARVEST_NAME).is_file():
        print(
            f"error: {run_dir / HARVEST_NAME} missing — run `evolve harvest` first",
            file=sys.stderr,
        )
        return 2

    source = Path(values["from-file"])
    valid: list[dict] = []
    errors_by_line: list[str] = []
    warnings: list[str] = []
    try:
        raw_lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"error: candidates file not readable: {exc}", file=sys.stderr)
        return 2
    for line_no, line in enumerate(raw_lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            warnings.append(f"candidates line {line_no}: invalid JSON")
            continue
        if not isinstance(obj, dict):
            warnings.append(f"candidates line {line_no}: not an object")
            continue
        line_errors = validate_candidate(
            obj, context_dir, project_root=project_root
        )
        if line_errors:
            errors_by_line.extend(
                f"candidate {len(valid) + len(errors_by_line)} "
                f"(line {line_no}): {message}"
                for message in line_errors
            )
        else:
            valid.append(obj)
    total = len(valid) + len(errors_by_line)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if total > MAX_CANDIDATES:
        print(
            f"error: a diagnosis emits at most {MAX_CANDIDATES} candidates "
            f"(got {total})",
            file=sys.stderr,
        )
        return 1
    if errors_by_line:
        for message in errors_by_line:
            print(f"error: {message}", file=sys.stderr)
        return 1

    canonical = "".join(
        json.dumps(parse_candidate(obj).to_dict(), sort_keys=True) + "\n"
        for obj in valid
    )
    with (run_dir / CANDIDATES_NAME).open("a", encoding="utf-8") as handle:
        handle.write(canonical)
    parsed = [parse_candidate(obj) for obj in valid]
    record_event(
        context_dir,
        {
            "kind": "diagnosis",
            "run": run_dir.name,
            "target": [c.primary_target for c in parsed],
            "evidence": sorted({e for c in parsed for e in c.evidence}),
            "outcome": {"candidates": len(parsed)},
        },
    )
    if "json" in flags:
        print(json.dumps({"candidates": len(parsed)}))
    else:
        print(
            f"context evolve diagnose ({run_dir.name}): "
            f"{len(parsed)} candidate(s) validated"
        )
    return 0


def _evolve_apply(args: list[str]) -> int:
    """`evolve apply --candidate N --run NAME [--json]` — stage + gate (exit 0)."""
    from dummyindex.context.domains.evolve import (
        CANDIDATES_NAME,
        GATE_NAME_FMT,
        STAGED_DIR_NAME,
        EvolveError,
        parse_candidate,
        record_event,
        run_dir_for,
        run_gate,
        validate_candidate,
    )

    values, flags, err = _parse_flags(
        args,
        value_keys={"candidate", "run", "root"},
        bool_keys={"json"},
    )
    if err is not None:
        return usage_error("evolve", f"{err} (for `evolve apply`)")
    if "candidate" not in values or "run" not in values:
        return usage_error(
            "evolve",
            "--candidate N and --run NAME are required (for `evolve apply`)",
        )
    index = _candidate_index(values["candidate"])
    if index is None:
        return usage_error(
            "evolve", "--candidate must be a 0-based line index (for `evolve apply`)"
        )
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    project_root = context_dir.parent

    try:
        run_dir = run_dir_for(context_dir, values["run"])
    except EvolveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not (run_dir / CANDIDATES_NAME).is_file():
        print(
            f"error: {run_dir / CANDIDATES_NAME} missing — run `evolve diagnose` first",
            file=sys.stderr,
        )
        return 2

    lines = _load_candidate_lines(run_dir)
    if index >= len(lines):
        print(
            f"error: candidate {index} out of range "
            f"(run has {len(lines)} candidate line(s))",
            file=sys.stderr,
        )
        return 2
    obj = lines[index]
    errors = validate_candidate(obj, context_dir, project_root=project_root)
    if errors:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
        return 1
    candidate = parse_candidate(obj)

    staged = [
        run_dir / STAGED_DIR_NAME / str(index) / Path(t).name
        for t in candidate.targets
    ]
    missing = [str(p) for p in staged if not p.is_file()]
    if missing:
        print(
            "error: staged content missing for target(s) — expected proposed "
            "content at " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    result = run_gate(candidate.targets, run_dir, context_dir, project_root)
    gate_payload = {"candidate": index, **result.to_dict()}
    from dummyindex.context.domains.atomic_io import write_text_atomic

    write_text_atomic(
        run_dir / GATE_NAME_FMT.format(index),
        json.dumps(gate_payload, indent=2, sort_keys=True) + "\n",
    )
    record_event(
        context_dir,
        {
            "kind": "gate",
            "run": run_dir.name,
            "candidate": index,
            "target": list(candidate.targets),
            "prediction": candidate.prediction,
            "evidence": list(candidate.evidence),
            "gate": result.to_dict(),
        },
    )
    if "json" in flags:
        print(json.dumps(gate_payload, indent=2, sort_keys=True))
        return 0
    print(
        f"context evolve apply ({run_dir.name}, candidate {index}): "
        f"verdict {result.verdict}"
    )
    for stage in result.stages:
        print(f"  {stage.name}: {stage.status} — {stage.detail}")
    return 0


def _evolve_promote(args: list[str]) -> int:
    """`evolve promote --candidate N --run NAME [--override REASON]`."""
    from dummyindex.context.domains.evolve import (
        BACKUP_DIR_NAME,
        STAGED_DIR_NAME,
        EvolveError,
        parse_candidate,
        record_event,
        run_dir_for,
        validate_candidate,
    )

    values, _flags, err = _parse_flags(
        args,
        value_keys={"candidate", "run", "override", "root"},
        bool_keys=set(),
    )
    if err is not None:
        return usage_error("evolve", f"{err} (for `evolve promote`)")
    if "candidate" not in values or "run" not in values:
        return usage_error(
            "evolve",
            "--candidate N and --run NAME are required (for `evolve promote`)",
        )
    index = _candidate_index(values["candidate"])
    if index is None:
        return usage_error(
            "evolve", "--candidate must be a 0-based line index (for `evolve promote`)"
        )
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    project_root = context_dir.parent

    try:
        run_dir = run_dir_for(context_dir, values["run"])
    except EvolveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    gate_path = run_dir / f"gate-{index}.json"
    if not gate_path.is_file():
        print(
            f"error: {gate_path} missing — run `evolve apply` first",
            file=sys.stderr,
        )
        return 2
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    verdict = gate.get("verdict")

    override = (values.get("override") or "").strip()
    if verdict != "pass":
        reason = (
            f"gate verdict is {verdict}" if verdict != "blocked" else "gate is blocked"
        )
        if not override:
            if verdict == "blocked":
                print(
                    'error: blocked verdict — rerun promote with '
                    '--override "<reason>" to record why it is being adopted',
                    file=sys.stderr,
                )
            else:
                print(
                    f"error: refusing to promote — {reason}; fix the candidate",
                    file=sys.stderr,
                )
            return 1
        if verdict != "blocked":
            print(
                "error: --override applies only to a blocked verdict; a failed "
                "gate cannot be overridden",
                file=sys.stderr,
            )
            return 1

    lines = _load_candidate_lines(run_dir)
    if index >= len(lines):
        print(f"error: candidate {index} out of range", file=sys.stderr)
        return 2
    obj = lines[index]
    errors = validate_candidate(obj, context_dir, project_root=project_root)
    if errors:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
        return 1
    candidate = parse_candidate(obj)

    staged = [
        run_dir / STAGED_DIR_NAME / str(index) / Path(t).name
        for t in candidate.targets
    ]
    missing = [str(p) for p in staged if not p.is_file()]
    if missing:
        print(
            "error: staged content missing: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    backup_dir = run_dir / BACKUP_DIR_NAME / str(index)
    applied: list[str] = []
    for target, staged_file in zip(
        candidate.targets, staged, strict=True
    ):
        destination = project_root / target
        backup = backup_dir / target
        backup.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file():
            shutil.copy2(destination, backup)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged_file, destination)
        applied.append(target)

    outcome: dict = {"applied": applied}
    if override:
        outcome["override"] = override
    record_event(
        context_dir,
        {
            "kind": "promote",
            "run": run_dir.name,
            "candidate": index,
            "target": list(candidate.targets),
            "prediction": candidate.prediction,
            "evidence": list(candidate.evidence),
            "outcome": outcome,
        },
    )
    print(
        f"context evolve promote ({run_dir.name}, candidate {index}): "
        f"{len(applied)} file(s) adopted"
        + (f" [override: {override}]" if override else "")
    )
    for target in applied:
        print(f"  {target}")
    return 0


def _evolve_rollback(args: list[str]) -> int:
    """`evolve rollback --candidate N --run NAME` — restore pre-promote content."""
    from dummyindex.context.domains.evolve import (
        BACKUP_DIR_NAME,
        EvolveError,
        record_event,
        run_dir_for,
    )

    values, _flags, err = _parse_flags(
        args,
        value_keys={"candidate", "run", "root"},
        bool_keys=set(),
    )
    if err is not None:
        return usage_error("evolve", f"{err} (for `evolve rollback`)")
    if "candidate" not in values or "run" not in values:
        return usage_error(
            "evolve",
            "--candidate N and --run NAME are required (for `evolve rollback`)",
        )
    index = _candidate_index(values["candidate"])
    if index is None:
        return usage_error(
            "evolve",
            "--candidate must be a 0-based line index (for `evolve rollback`)",
        )
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    project_root = context_dir.parent

    try:
        run_dir = run_dir_for(context_dir, values["run"])
    except EvolveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    backup_dir = run_dir / BACKUP_DIR_NAME / str(index)
    if not backup_dir.is_dir():
        print(
            f"error: {backup_dir} missing — nothing to roll back for candidate "
            f"{index}",
            file=sys.stderr,
        )
        return 2

    restored: list[str] = []
    for backup_file in sorted(backup_dir.rglob("*")):
        if not backup_file.is_file():
            continue
        rel = backup_file.relative_to(backup_dir)
        destination = project_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, destination)
        restored.append(rel.as_posix())

    record_event(
        context_dir,
        {
            "kind": "rollback",
            "run": run_dir.name,
            "candidate": index,
            "target": restored,
            "outcome": {"restored": restored},
        },
    )
    print(
        f"context evolve rollback ({run_dir.name}, candidate {index}): "
        f"{len(restored)} file(s) restored"
    )
    for target in restored:
        print(f"  {target}")
    return 0


def _evolve_discard(args: list[str]) -> int:
    """`evolve discard --candidate N --run NAME` — drop the staged copy."""
    from dummyindex.context.domains.evolve import (
        BACKUP_DIR_NAME,
        STAGED_DIR_NAME,
        EvolveError,
        record_event,
        run_dir_for,
    )

    values, _flags, err = _parse_flags(
        args,
        value_keys={"candidate", "run", "root"},
        bool_keys=set(),
    )
    if err is not None:
        return usage_error("evolve", f"{err} (for `evolve discard`)")
    if "candidate" not in values or "run" not in values:
        return usage_error(
            "evolve",
            "--candidate N and --run NAME are required (for `evolve discard`)",
        )
    index = _candidate_index(values["candidate"])
    if index is None:
        return usage_error(
            "evolve",
            "--candidate must be a 0-based line index (for `evolve discard`)",
        )
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()

    try:
        run_dir = run_dir_for(context_dir, values["run"])
    except EvolveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    removed: list[str] = []
    for path in (
        run_dir / STAGED_DIR_NAME / str(index),
        run_dir / BACKUP_DIR_NAME / str(index),
        run_dir / f"gate-{index}.json",
    ):
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(str(path))
        elif path.is_file():
            path.unlink()
            removed.append(str(path))

    record_event(
        context_dir,
        {
            "kind": "discard",
            "run": run_dir.name,
            "candidate": index,
            "outcome": {"removed": len(removed)},
        },
    )
    print(
        f"context evolve discard ({run_dir.name}, candidate {index}): dropped"
    )
    return 0
