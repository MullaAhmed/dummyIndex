"""`dummyindex context evolve <verb>` — the self-improvement loop CLI.

Wire-only sibling of ``cli/gc.py``: parse this command's own flag alphabet,
lazy-import the ``context.domains.evolve`` domain inside ``run`` (the layering
rule — ``cli`` imports the domain, never the reverse), call a domain function,
print, return an exit code. Diagnosis lives in the packaged skill. Project
tests qualify baseline and exact candidate guidance; model improvement remains
unmeasured.

The six verbs:

- ``harvest [--since DATE] [--sleep] [--json] [--run NAME]`` — collect audit
  findings, session-memory corrections, reconcile deltas, and transcript
  adoption misses into ``<run>/harvest.json``. ``--sleep`` is the overnight
  contract: nothing new → exit 0 having written nothing at all.
- ``diagnose --run NAME --from-file FILE`` — validate host-authored
  candidates (structure, scope guard, citation existence; ≤5 candidates,
  ≤5 target files each) into ``<run>/candidates.jsonl``.
- ``apply --candidate N --run NAME`` — stage candidate N (0-based line) and
  run existing project tests; unavailable checks yield verdict
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
    "harvest|diagnose|apply|promote|rollback|discard|evidence|learning|rules|experiment|utility ..."
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
        "evidence": _evolve_evidence,
        "learning": _evolve_learning,
        "rules": _evolve_rules,
        "experiment": _evolve_experiment,
        "utility": _evolve_utility,
    }
    handler = handlers.get(verb)
    if handler is None:
        print(
            "error: unknown evolve verb "
            f"{verb!r} (expected harvest|diagnose|apply|promote|rollback|discard|evidence|learning|rules|experiment|utility)",
            file=sys.stderr,
        )
        return 2
    return handler(rest)


def _evolve_evidence(args: list[str]) -> int:
    """Import project-scoped Claude/Codex evidence without copying prompt text."""
    from dummyindex.context.domains.evidence import scan_hosts
    from dummyindex.context.domains.evolve_gate import EvolveError

    values, _flags, err = _parse_flags(
        args,
        value_keys={"root", "claude", "codex", "state", "history"},
        bool_keys={"json"},
    )
    if err:
        return usage_error("evolve evidence", err)
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    home = Path.home()
    try:
        result = scan_hosts(
            context_dir,
            claude_projects=Path(values["claude"])
            if values.get("claude")
            else home / ".claude/projects",
            codex_sessions=Path(values["codex"])
            if values.get("codex")
            else home / ".codex/sessions",
            codex_state=Path(values["state"]) if values.get("state") else None,
            codex_history=Path(values["history"]) if values.get("history") else None,
        )
    except (EvolveError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def _evolve_learning(args: list[str]) -> int:
    """At closeout dispatch one pending reflection, then prepare or NO_ENTRY."""
    from dummyindex.context.domains.evolve_gate import EvolveError
    from dummyindex.context.domains.evolve_learning import (
        finish_learning,
        learning_status,
        pending_learning,
    )
    from dummyindex.context.domains.proposals.closeout import (
        learning_exit_code,
        learning_line,
    )

    values, flags, err = _parse_flags(
        args,
        value_keys={"root", "event", "from-file"},
        bool_keys={"next", "no-entry", "json"},
    )
    if err:
        return usage_error("evolve learning", err)
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    try:
        if "next" in flags or not values.get("event"):
            pending = pending_learning(context_dir)
            result = pending[:1]
        else:
            if "no-entry" not in flags and not values.get("from-file"):
                return usage_error(
                    "evolve learning",
                    "supply --from-file reflection.json or --no-entry",
                )
            reflection = (
                None
                if "no-entry" in flags
                else json.loads(Path(values["from-file"]).read_text(encoding="utf-8"))
            )
            result = finish_learning(
                context_dir,
                values["event"],
                reflection,
                tests=tuple(reflection.get("tests", []))
                if isinstance(reflection, dict)
                else (),
            )
    except (EvolveError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    if isinstance(result, dict):
        learning = {**result, "status": learning_status(result)}
        print(learning_line(learning), file=sys.stderr)
        return learning_exit_code(learning)
    return 0


def _evolve_rules(args: list[str]) -> int:
    from dummyindex.context.domains.evolve_gate import EvolveError
    from dummyindex.context.domains.living_rules import rule_status

    values, _flags, err = _parse_flags(args, value_keys={"root"}, bool_keys={"json"})
    if err:
        return usage_error("evolve rules", err)
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    try:
        print(json.dumps(rule_status(context_dir), sort_keys=True, indent=2))
    except (EvolveError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _evolve_utility(args: list[str]) -> int:
    from dummyindex.context.domains.evolve_experiments import utility_status
    from dummyindex.context.domains.evolve_gate import EvolveError

    values, _flags, err = _parse_flags(args, value_keys={"root"}, bool_keys={"json"})
    if err:
        return usage_error("evolve utility", err)
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    try:
        print(json.dumps(utility_status(context_dir), sort_keys=True, indent=2))
    except (EvolveError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _evolve_experiment(args: list[str]) -> int:
    from dummyindex.context.domains.evolve import run_dir_for
    from dummyindex.context.domains.evolve_experiments import run_experiment
    from dummyindex.context.domains.evolve_gate import EvolveError

    values, _flags, err = _parse_flags(
        args,
        value_keys={
            "root",
            "run",
            "from-file",
            "command",
            "case",
            "heldout",
            "candidate",
            "model",
            "rubric",
        },
        bool_keys={"json"},
    )
    if err:
        return usage_error("evolve experiment", err)
    if not values.get("run"):
        return usage_error("evolve experiment", "--run NAME is required")
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    try:
        if values.get("from-file"):
            specification = json.loads(
                Path(values["from-file"]).read_text(encoding="utf-8")
            )
        else:
            if (
                not {"command", "case", "heldout", "candidate", "model", "rubric"}
                <= values.keys()
            ):
                return usage_error(
                    "evolve experiment",
                    "use --from-file FILE or explicit --command JSON --case FILE --heldout FILE --candidate N --model NAME --rubric ID",
                )
            specification = {
                "command": json.loads(values["command"]),
                "cases": [
                    {
                        "id": values["case"],
                        "path": values["case"],
                        "split": "validation",
                    },
                    {
                        "id": values["heldout"],
                        "path": values["heldout"],
                        "split": "heldout",
                    },
                ],
                "candidates": {"alternative": int(values["candidate"])},
                "model": values["model"],
                "rubric": values["rubric"],
            }
        if not isinstance(specification, dict):
            raise EvolveError("experiment specification must be an object")
        result = run_experiment(
            context_dir, run_dir_for(context_dir, values["run"]), specification
        )
    except (EvolveError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


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
        print(f"  prediction flip: {', '.join(flag.targets)} — {flag.prediction}")
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
        line_errors = validate_candidate(obj, context_dir, project_root=project_root)
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
        EvolveError,
        parse_candidate,
        record_event,
        run_dir_for,
        run_gate,
        validate_candidate,
    )

    values, flags, err = _parse_flags(
        args,
        value_keys={"candidate", "run", "root", "tests"},
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

    try:
        result = run_gate(
            candidate.targets,
            run_dir,
            context_dir,
            project_root,
            candidate_index=index,
            candidate_payload=obj,
            test_paths=(values["tests"],) if values.get("tests") else None,
        )
    except (EvolveError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
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
    """Adopt only the exact qualified content, with a recoverable multi-file write."""
    from dummyindex.context.domains.evolve import (
        EvolveError,
        parse_candidate,
        record_event,
        run_dir_for,
        validate_candidate,
    )
    from dummyindex.context.domains.evolve_gate import (
        check_receipt,
        safe_file,
    )
    from dummyindex.context.domains.evolve_promotion import project_lock, promote_files

    values, _flags, err = _parse_flags(
        args,
        value_keys={"candidate", "run", "override", "root"},
        bool_keys=set(),
    )
    if err is not None:
        return usage_error("evolve", f"{err} (for `evolve promote`)")
    index = _candidate_index(values.get("candidate"))
    if index is None or not values.get("run"):
        return usage_error("evolve", "--candidate N and --run NAME are required")
    context_dir = _context_dir(values.get("root"))
    if context_dir is None:
        return _missing_context()
    project_root = context_dir.parent
    try:
        with project_lock(project_root):
            run_dir = run_dir_for(context_dir, values["run"])
            gate_path = safe_file(run_dir, f"gate-{index}.json")
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            if not isinstance(gate, dict) or gate.get("candidate") != index:
                raise EvolveError("invalid gate candidate identity; rerun evolve apply")
            lines = _load_candidate_lines(run_dir)
            if index >= len(lines):
                raise EvolveError(f"candidate {index} out of range")
            obj = lines[index]
            errors = validate_candidate(obj, context_dir, project_root=project_root)
            if errors:
                raise EvolveError("; ".join(errors))
            candidate = parse_candidate(obj)
            check_receipt(gate, candidate.targets, run_dir, index, project_root, obj)
            verdict = gate.get("verdict")
            override = (values.get("override") or "").strip()
            if verdict != "pass":
                if verdict != "blocked":
                    raise EvolveError(
                        "failed or malformed gate cannot be overridden; fix the candidate"
                    )
                if not override:
                    raise EvolveError(
                        'blocked/unmeasured verdict; use --override "<reason>" for recorded manual adoption'
                    )
            applied = promote_files(
                candidate.targets,
                run_dir,
                index,
                project_root,
                gate["receipt"],
            )
    except (EvolveError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    outcome: dict = {
        "applied": list(applied),
        "qualification": "manual_unmeasured"
        if verdict == "blocked"
        else "project_tests",
    }
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
        f"context evolve promote ({run_dir.name}, candidate {index}): {len(applied)} file(s) adopted"
        + (
            f" [manual, unmeasured: {override}]"
            if verdict == "blocked"
            else " [project tests; model improvement unmeasured]"
        )
    )
    for target in applied:
        print(f"  {target}")
    return 0


def _evolve_rollback(args: list[str]) -> int:
    """`evolve rollback --candidate N --run NAME` — restore pre-promote content."""
    from dummyindex.context.domains.evolve import (
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
    from dummyindex.context.domains.evolve_promotion import project_lock, rollback_files

    try:
        with project_lock(project_root):
            restored = list(rollback_files(run_dir, index, project_root))
    except (EvolveError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

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
    print(f"context evolve discard ({run_dir.name}, candidate {index}): dropped")
    return 0
