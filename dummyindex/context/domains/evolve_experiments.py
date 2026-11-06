"""Bounded paired replay of guidance with a fixed, external executor/evaluator.

The executor must actually run the agent and independently judge its artifacts.
This module never infers quality from trigger words or successful discovery. It
keeps the incumbent eligible and treats absent measurements as infrastructure
failures. General/domain probes and any composition all execute separately.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path

from .atomic_io import write_text_atomic
from .evidence import digest, expose_case
from .evolve import parse_candidate, validate_candidate
from .evolve_gate import (
    EvolveError,
    _environment,
    _working_inputs,
    safe_file,
    staged_files,
)
from .evolve_promotion import project_lock

_BASE = ".context/gc/experiments"
_UTILITY = ".context/gc/guidance-utility.json"
MAX_RAW_BYTES = 64_000


def _write(path: Path, data: dict) -> None:
    write_text_atomic(path, json.dumps(data, sort_keys=True, indent=2) + "\n")


def _finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _measurement(value: object, request: dict, *, native: bool = False) -> dict:
    if not isinstance(value, dict) or value.get("status") not in {
        "measured",
        "infra_error",
    }:
        raise EvolveError("executor must return measured or infra_error status")
    if value["status"] == "infra_error":
        result = {
            "status": "infra_error",
            "reason": str(value.get("reason", "execution unavailable"))[:500],
        }
        if (
            all(_finite(value.get(k)) and value[k] >= 0 for k in ("tokens", "cost_usd"))
            and int(value["tokens"]) == value["tokens"]
        ):
            result.update(tokens=value["tokens"], cost_usd=value["cost_usd"])
        else:
            result["unaccounted"] = True
        return result
    for key in ("cost_usd", "tokens"):
        if native and value.get(key) is None:
            value[key] = None
            continue
        if not _finite(value.get(key)) or value[key] < 0:
            raise EvolveError(
                f"executor returned invalid independent {key} measurement"
            )
    if value["tokens"] is not None and int(value["tokens"]) != value["tokens"]:
        raise EvolveError("tokens must be an integer")
    outcomes = value.get("cases")
    wanted = {case["id"]: case for case in request["cases"]}
    if (
        not isinstance(outcomes, list)
        or len(outcomes) != len(wanted)
        or any(
            not isinstance(row, dict)
            or row.get("id") not in wanted
            or row.get("status") not in {"pass", "fail"}
            for row in outcomes
        )
        or len({row["id"] for row in outcomes}) != len(wanted)
    ):
        raise EvolveError(
            "executor must independently grade every requested case exactly once"
        )
    # Required regression controls cannot be hidden behind a higher aggregate.
    value["quality"] = sum(row["status"] == "pass" for row in outcomes) / len(outcomes)
    value["controls_pass"] = all(
        row["status"] == "pass"
        for row in outcomes
        if wanted[row["id"]].get("required", True)
    )
    loaded = value.get("loaded")
    expected = {
        (row["id"], row["version"], row["sha256"]) for row in request["guidance"]
    }
    if not isinstance(loaded, list) or any(
        not isinstance(r, dict)
        or not isinstance(r.get("id"), str)
        or not r["id"]
        or not isinstance(r.get("version"), str)
        or not r["version"]
        or not isinstance(r.get("sha256"), str)
        or (r["id"], r["version"], r.get("sha256")) not in expected
        for r in loaded
    ):
        raise EvolveError(
            "executor must report actually loaded guidance IDs, versions and exact content hashes"
        )
    actual = {(row["id"], row["version"], row["sha256"]) for row in loaded}
    if expected - actual:
        raise EvolveError(
            "required candidate/incumbent guidance was not actually loaded"
        )
    details = {
        (row["id"], row["version"], row["sha256"]): row for row in request["guidance"]
    }
    value["loaded"] = [
        {**row, "path": details[(row["id"], row["version"], row["sha256"])]["path"]}
        for row in loaded
    ]
    if not isinstance(value.get("evidence"), str) or not value["evidence"].strip():
        raise EvolveError("measured outcomes require independent execution evidence")
    return {
        k: value[k]
        for k in (
            "status",
            "quality",
            "controls_pass",
            "cases",
            "cost_usd",
            "tokens",
            "loaded",
            "evidence",
        )
    }


def _comparison_reason(candidate: dict, incumbent: dict) -> str | None:
    if (
        candidate.get("status") != "measured"
        or incumbent.get("status") != "measured"
        or candidate.get("controls_pass") is not True
    ):
        return None
    if candidate["quality"] > incumbent["quality"]:
        return "higher_quality"
    if candidate["quality"] < incumbent["quality"]:
        return None
    if any(
        not _finite(row.get(key))
        for row in (candidate, incumbent)
        for key in ("cost_usd", "tokens")
    ):
        return None
    for key, reason in (
        ("cost_usd", "lower_cost"),
        ("tokens", "lower_tokens"),
        ("guidance_bytes", "fewer_guidance_bytes"),
    ):
        if candidate[key] < incumbent[key]:
            return reason
        if candidate[key] > incumbent[key]:
            return None
    return None


def _better(candidate: dict, incumbent: dict) -> bool:
    return _comparison_reason(candidate, incumbent) is not None


def _captured_guidance_bytes(
    inputs: dict[str, bytes], overlay: dict[str, bytes], paths: set[str]
) -> int:
    combined = inputs | overlay
    return sum(len(combined[path]) for path in paths)


def _execute(argv: list[str], cwd: Path, request: dict, remaining: float) -> dict:
    request_path = cwd / ".dummyindex-replay-request.json"
    _write(request_path, request)
    env = dict(os.environ)
    # Replay home is isolated from the user's global host configuration.
    home = cwd / ".dummyindex-replay-home"
    home.mkdir(exist_ok=True)
    env.update(
        HOME=str(home), USERPROFILE=str(home), DUMMYINDEX_LEARNING_ORIGIN="experiment"
    )
    env.pop("CODEX_HOME", None)
    env.pop("CLAUDE_CONFIG_DIR", None)
    try:
        # File-backed output avoids unbounded pipe allocations from a bad runner.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                [*argv, "--request", str(request_path)],
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=errors,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0,
                start_new_session=os.name != "nt",
            )
            deadline = time.monotonic() + remaining
            while process.poll() is None:
                overflow = (
                    os.fstat(output.fileno()).st_size
                    + os.fstat(errors.fileno()).st_size
                    > MAX_RAW_BYTES
                )
                if overflow or time.monotonic() >= deadline:
                    _kill_tree(process)
                    return {
                        "status": "infra_error",
                        "reason": "executor output exceeds bounded receipt size"
                        if overflow
                        else "total replay wall-time budget exhausted",
                    }
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            output.seek(0, os.SEEK_END)
            size = output.tell() + os.fstat(errors.fileno()).st_size
            if size > MAX_RAW_BYTES:
                return {
                    "status": "infra_error",
                    "reason": "executor output exceeds bounded receipt size",
                }
            if process.returncode:
                return {
                    "status": "infra_error",
                    "reason": f"executor exited {process.returncode}",
                }
            output.seek(0)
            return _measurement(json.loads(output.read()), request)
    except (OSError, ValueError, EvolveError, subprocess.SubprocessError) as exc:
        return {"status": "infra_error", "reason": str(exc)[:500]}


def _kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=10,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def _guidance(
    inputs: dict[str, bytes],
    overlay: dict[str, bytes],
    paths: set[str],
    declared: dict[str, dict],
) -> list[dict]:
    rows = []
    combined = inputs | overlay
    manifest = json.loads(combined.get(".context/equipment.json", b"{}"))
    owned = (
        {
            row.get("path"): row
            for row in manifest.get("items", [])
            if isinstance(row, dict)
        }
        if isinstance(manifest, dict)
        else {}
    )
    for path in sorted(paths):
        if path not in combined:
            raise EvolveError("expected guidance must be a captured project input")
        fingerprint = hashlib.sha256(combined[path]).hexdigest()
        version_match = re.search(rb"(?m)^version:\s*[\"']?([^\s\"']+)", combined[path])
        meta = declared.get(path, owned.get(path, {}))
        version = (
            version_match[1].decode() if version_match else "sha256:" + fingerprint
        )
        rows.append(
            {
                "id": meta.get("id", meta.get("capability_id", path)),
                "version": version,
                "path": path,
                "sha256": fingerprint,
            }
        )
    return rows


def utility_status(context_dir: Path) -> list[dict]:
    path = safe_file(context_dir.parent, _UTILITY, exists=False)
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, dict):
        raise EvolveError("invalid guidance utility ledger")
    from .living_rules import rule_status

    stale = {
        row["target"] for row in rule_status(context_dir) if row["state"] == "stale"
    }
    return [
        dict(
            value,
            state="suspect"
            if value["failures"] >= 2 or value.get("path") in stale
            else "observed",
            source_invalid=value.get("path") in stale,
        )
        for _, value in sorted(rows.items())
    ]


def _utility(context_dir: Path, stage: str, measurement: dict, identity: str) -> None:
    if measurement.get("status") != "measured":
        return
    path = safe_file(context_dir.parent, _UTILITY, exists=False)
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for item in measurement["loaded"]:
        key = digest([item["id"], item["version"], item["sha256"]])
        row = rows.setdefault(
            key,
            {
                "id": item["id"],
                "version": item["version"],
                "sha256": item["sha256"],
                "path": item["path"],
                "trials": [],
                "successes": 0,
                "failures": 0,
                "tokens": 0,
                "cost_usd": 0,
            },
        )
        trial = digest([identity, stage])
        if trial in row["trials"]:
            continue
        row["trials"].append(trial)
        row["successes" if measurement["quality"] == 1 else "failures"] += 1
        for key in ("tokens", "cost_usd"):
            row[key] = (
                row[key] + measurement[key]
                if row[key] is not None and measurement[key] is not None
                else None
            )
    _write(path, rows)


def run_experiment(context_dir: Path, run_dir: Path, specification: dict) -> dict:
    """Serialize paired replays so concurrent callers reuse, rather than double-pay."""
    with project_lock(context_dir.parent, lock_name="replay.lock"):
        if specification.get("execution") == "native" or "request_id" in specification:
            from .evolve_native import run_native

            return run_native(context_dir, run_dir, specification)
        return _run_experiment(context_dir, run_dir, specification)


def _run_experiment(context_dir: Path, run_dir: Path, specification: dict) -> dict:
    """Execute incumbent, two improvement lenses and supported composition.

    ``command`` is a JSON argv array for an existing trusted runner. It receives
    ``--request FILE`` and returns one bounded JSON measurement. Its Python,
    rubric, cases and acceptance policy are outside candidate mutation scope.
    Cost/token limits are passed to the trusted runner for reservation before a
    paid call, then checked on every result; timeout is enforced by this process.
    """
    root = context_dir.resolve().parent
    command = specification.get("command")
    cases = specification.get("cases")
    variants = specification.get("candidates", {})
    budget = specification.get("budget", {})
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(x, str) and x for x in command)
    ):
        raise EvolveError("experiment requires an explicit command argv array")
    if (
        not isinstance(cases, list)
        or not cases
        or not all(
            isinstance(c, dict)
            and isinstance(c.get("id"), str)
            and c["id"]
            and isinstance(c.get("path"), str)
            and c.get("split") in {"train", "validation", "heldout"}
            for c in cases
        )
    ):
        raise EvolveError("experiment requires named case files with explicit splits")
    if len({c["id"] for c in cases}) != len(cases):
        raise EvolveError("case IDs must be unique")
    if not isinstance(variants, dict) or set(variants) - {
        "general",
        "domain",
        "composition",
        "alternative",
    }:
        raise EvolveError(
            "candidate lenses are general, domain, composition or alternative"
        )
    if "composition" in variants and not {"general", "domain"} <= variants.keys():
        raise EvolveError("composition requires both independently executed lenses")
    if any(
        not isinstance(i, int) or isinstance(i, bool) or i < 0
        for i in variants.values()
    ):
        raise EvolveError("candidate values are existing nonnegative candidate indices")
    limits = {
        "stages": 6,
        "seconds": 120,
        "tokens": 20000,
        "cost_usd": 2.0,
        "no_progress": 2,
        "infra_retries": 0,
        **budget,
    }
    if (
        any(not _finite(v) or v < 0 for v in limits.values())
        or not 1 <= limits["stages"] <= 12
        or not 1 <= limits["seconds"] <= 1800
        or not 1 <= limits["no_progress"] <= 12
        or not 0 <= limits["infra_retries"] <= 2
    ):
        raise EvolveError("invalid bounded experiment budget")
    if (
        not isinstance(specification.get("model"), str)
        or not specification["model"]
        or not isinstance(specification.get("rubric"), str)
        or not specification["rubric"]
    ):
        raise EvolveError("pin model and rubric identities for replay")
    seed, repetition = specification.get("seed", 0), specification.get("repetition", 0)
    if any(
        not isinstance(x, int) or isinstance(x, bool) or x < 0
        for x in (seed, repetition)
    ):
        raise EvolveError("seed and repetition must be nonnegative integers")
    inputs = _working_inputs(root)
    # Experiment receipts, learning and utility cannot invalidate their own cache.
    inputs = {
        p: b
        for p, b in inputs.items()
        if not p.startswith((".context/gc/experiments/", ".context/gc/learning/"))
        and p not in {".context/gc/guidance-utility.json", ".context/gc/evidence.json"}
    }
    for case in cases:
        safe_file(root, case["path"])
        if case["path"] not in inputs:
            raise EvolveError("replay case must be a captured nonignored project input")
    raw_candidates = [
        json.loads(line)
        for line in (run_dir / "candidates.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    overlays = {"incumbent": {}}
    for label, index in variants.items():
        if index >= len(raw_candidates):
            raise EvolveError("experiment candidate index out of range")
        raw = raw_candidates[index]
        errors = validate_candidate(raw, context_dir)
        if errors:
            raise EvolveError("; ".join(errors))
        candidate = parse_candidate(raw)
        overlays[label] = {
            p: f.read_bytes()
            for p, f in zip(
                candidate.targets,
                staged_files(run_dir, index, candidate.targets),
                strict=True,
            )
        }
    declared = specification.get("guidance", [])
    if not isinstance(declared, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("path"), str)
        for row in declared
    ):
        raise EvolveError("optional guidance identities require existing paths")
    guidance_paths = {p for overlay in overlays.values() for p in overlay} | {
        row["path"] for row in declared
    }
    declared_guidance = {row["path"]: row for row in declared}
    hashes = {p: digest(b.hex()) for p, b in inputs.items()}
    modes = {p: stat.S_IMODE(safe_file(root, p).stat().st_mode) for p in inputs}
    for arg in command:
        candidate_path = Path(arg)
        if candidate_path.is_file():
            hashes["executor:" + arg] = digest(candidate_path.read_bytes().hex())
        elif arg.endswith(".py"):
            hashes["executor:" + arg] = digest(safe_file(root, arg).read_bytes().hex())
    binary = shutil.which(command[0])
    if binary:
        hashes["executor-binary"] = hashlib.sha256(
            Path(binary).read_bytes()
        ).hexdigest()
    # Environment identity prevents a changed model endpoint/tool setup reusing a trial.
    contract = {
        "specification": specification,
        "inputs": hashes,
        "modes": modes,
        "overlays": {
            k: {p: digest(b.hex()) for p, b in v.items()} for k, v in overlays.items()
        },
        "environment": digest(
            {
                "env": _environment(),
                "platform": platform.platform(),
                "distributions": sorted(
                    (d.metadata.get("Name", ""), d.version)
                    for d in importlib.metadata.distributions()
                ),
            }
        ),
        "controller": digest(Path(__file__).read_bytes().hex()),
    }
    identity = digest(contract)
    receipt_path = safe_file(root, f"{_BASE}/{identity}.json", exists=False)
    with project_lock(root):
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("identity") != identity:
                raise EvolveError("experiment receipt identity mismatch")
            if receipt.get("receipt_sha256") != digest(
                {k: v for k, v in receipt.items() if k != "receipt_sha256"}
            ):
                raise EvolveError(
                    "experiment receipt was altered; preserve it and use a new repetition"
                )
            return {**receipt, "cached": True}
    for case in cases:
        expose_case(
            context_dir,
            case["id"],
            split=case["split"],
            derived_from=tuple(case.get("derived_from", [])),
            content_sha256=hashlib.sha256(inputs[case["path"]]).hexdigest(),
        )
    development = [c for c in cases if c["split"] != "heldout"]
    heldout = [c for c in cases if c["split"] == "heldout"]
    if not development:
        raise EvolveError("strategy selection needs development/validation cases")
    result = {
        "schema_version": 1,
        "identity": identity,
        "contract": contract,
        "stages": [],
        "best": "incumbent",
        "current": "incumbent",
        "best_reason": "incumbent",
        "current_reason": "incumbent",
        "cached": False,
        "qualification": "external executor reports actual runtime outcomes; project-test promotion remains separate",
    }
    started = time.monotonic()
    spent_tokens = 0
    spent_cost = 0.0
    accounting_complete = True
    no_progress = 0
    stage_ids = set()
    measurements = {}
    stopped = "completed"
    with tempfile.TemporaryDirectory(prefix="dummyindex-replay-") as temporary:
        workspace = Path(temporary) / "workspace"

        def execute(label: str, selected_cases: list[dict], phase: str) -> dict | None:
            nonlocal spent_tokens, spent_cost, stopped, accounting_complete
            stage_id = f"{phase}:{label}:{seed}:{repetition}"
            if stage_id in stage_ids:
                raise EvolveError("duplicate replay stage identity")
            stage_ids.add(stage_id)
            measurement = None
            for attempt in range(int(limits["infra_retries"]) + 1):
                remaining = limits["seconds"] - (time.monotonic() - started)
                if (
                    len(result["stages"]) >= limits["stages"]
                    or not accounting_complete
                    or remaining <= 0
                    or spent_tokens >= limits["tokens"]
                    or spent_cost >= limits["cost_usd"]
                ):
                    stopped = "budget_exhausted"
                    return None
                if workspace.exists():
                    if (
                        workspace.is_symlink()
                        or workspace.resolve().parent != Path(temporary).resolve()
                    ):
                        raise EvolveError("replay workspace escaped its temporary root")
                    shutil.rmtree(workspace)
                workspace.mkdir()
                hidden_cases = (
                    {case["path"] for case in heldout}
                    if phase == "development"
                    else set()
                )
                for relative, content in (inputs | overlays[label]).items():
                    if relative in hidden_cases:
                        continue
                    destination = safe_file(workspace, relative, exists=False)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)
                    destination.chmod(modes.get(relative, 0o644))
                request = {
                    "schema_version": 1,
                    "stage_id": stage_id,
                    "attempt": attempt,
                    "phase": phase,
                    "model": specification["model"],
                    "rubric": specification["rubric"],
                    "guidance": _guidance(
                        inputs, overlays[label], guidance_paths, declared_guidance
                    ),
                    "cases": selected_cases,
                    "seed": seed,
                    "repetition": repetition,
                    "max_tokens": limits["tokens"] - spent_tokens,
                    "max_cost_usd": limits["cost_usd"] - spent_cost,
                }
                before = time.monotonic()
                measurement = _execute(command, workspace, request, remaining)
                if measurement["status"] == "measured":
                    measurement["guidance_bytes"] = _captured_guidance_bytes(
                        inputs, overlays[label], guidance_paths
                    )
                result["stages"].append(
                    {
                        "id": stage_id,
                        "attempt": attempt,
                        "label": label,
                        "phase": phase,
                        "seconds": time.monotonic() - before,
                        **measurement,
                    }
                )
                if measurement["status"] != "measured" and (
                    measurement.get("unaccounted")
                    or "tokens" not in measurement
                    or "cost_usd" not in measurement
                ):
                    accounting_complete = False
                    stopped = "resource_accounting_unavailable"
                    break
                spent_tokens += measurement["tokens"]
                spent_cost += measurement["cost_usd"]
                if measurement["status"] == "measured":
                    if (
                        spent_tokens > limits["tokens"]
                        or spent_cost > limits["cost_usd"]
                    ):
                        measurement = {
                            "status": "infra_error",
                            "reason": "trusted executor exceeded reserved resource budget",
                        }
                        result["stages"][-1].update(measurement)
                        stopped = "budget_exhausted"
                    break
            return measurement

        for label in (
            name
            for name in ("incumbent", "general", "domain", "alternative", "composition")
            if name in overlays
        ):
            if label == "composition" and any(
                not _better(
                    measurements.get(lens, {}), measurements.get("incumbent", {})
                )
                for lens in ("general", "domain")
            ):
                result["stages"].append(
                    {
                        "id": "composition:unsupported",
                        "label": label,
                        "status": "skipped",
                        "reason": "both lenses must improve in actual independent probes",
                    }
                )
                continue
            measurement = execute(label, development, "development")
            if measurement is None:
                break
            measurements[label] = measurement
            if label == "incumbent":
                if measurement["status"] != "measured":
                    stopped = "incumbent_unmeasured"
                    break
                continue
            reason = _comparison_reason(measurement, measurements[result["best"]])
            if reason:
                result["best"] = label
                result["best_reason"] = reason
                no_progress = 0
            else:
                no_progress += 1
                if no_progress >= limits["no_progress"]:
                    stopped = "no_progress"
                    break
        chosen = result["best"]
        if chosen != "incumbent":
            if not heldout:
                stopped = "heldout_qualification_required"
            else:
                before = execute("incumbent", heldout, "heldout")
                after = execute(chosen, heldout, "heldout") if before else None
                reason = _comparison_reason(after, before) if before and after else None
                if reason:
                    result["current"] = chosen
                    result["current_reason"] = reason
                elif stopped != "budget_exhausted":
                    stopped = "heldout_regression_or_unmeasured"
    result.update(
        stop_reason=stopped,
        tokens=spent_tokens,
        cost_usd=spent_cost,
        seconds=time.monotonic() - started,
        accounting_complete=accounting_complete,
    )
    with project_lock(root):
        result["receipt_sha256"] = digest(result)
        _write(receipt_path, result)
        _write(
            safe_file(root, f"{_BASE}/best.json", exists=False),
            {
                "identity": identity,
                "current": result["current"],
                "best": result["best"],
            },
        )
        for stage in result["stages"]:
            _utility(context_dir, str(stage["id"]), stage, identity)
    return result
