"""`dummyindex context scan-check` — validate `features/graph.json`.

The curated scan is the one `.context/` artifact a model writes freehand,
so it is the one that needs a check the model can run itself. This is that
check: every violation, each with a JSON path, in a single pass.

Wire-only, per the CLI contract — parse flags, call the domain validator,
print, return an exit code:

- ``0`` the scan is valid (a seed counts; it just says so). Warning-severity
  violations — checks that could not run, like a `symbolRef` with no
  extraction artifact on disk — are printed but do not fail the check.
- ``1`` the scan is on disk and violates the contract
- ``2`` there is nothing to check, or the arguments were wrong
"""

from __future__ import annotations

import json
import sys

from .common import parse_path_and_root, resolve_context_root


def run(args: list[str]) -> int:
    """Validate the on-disk scan and report every violation."""
    from dummyindex.context.domains.features.scan import (
        load_symbol_ref_index,
        validate_scan,
    )
    from dummyindex.context.enums import ScanViolationSeverity
    from dummyindex.pipeline.enums import ConfidenceLevel

    scope, explicit_root, rest = parse_path_and_root(args)
    as_json = False
    leftover: list[str] = []
    for arg in rest:
        if arg == "--json":
            as_json = True
        else:
            leftover.append(arg)
    if leftover:
        print(
            f"error: unknown argument(s) for `scan-check`: {leftover}",
            file=sys.stderr,
        )
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    scan_path = features_dir / "graph.json"
    if not scan_path.is_file():
        print(
            f"error: {scan_path} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        payload = json.loads(scan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: {scan_path} is not valid JSON: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: could not read {scan_path}: {exc}", file=sys.stderr)
        return 2

    violations = validate_scan(payload, symbol_refs=load_symbol_ref_index(features_dir))
    errors = [v for v in violations if v.severity != ScanViolationSeverity.WARNING]
    warnings = [v for v in violations if v.severity == ScanViolationSeverity.WARNING]
    confidence = (
        payload.get("confidence") if isinstance(payload, dict) else None
    ) or "UNKNOWN"

    if as_json:
        print(
            json.dumps(
                {
                    "ok": not errors,
                    "path": str(scan_path),
                    "confidence": str(confidence),
                    "violations": [
                        {
                            "code": v.code,
                            "path": v.path,
                            "message": v.message,
                            "severity": str(v.severity),
                        }
                        for v in violations
                    ],
                },
                indent=2,
            )
        )
        return 1 if errors else 0

    if errors:
        print(
            f"scan-check: {len(errors)} violation(s) in {scan_path}",
            file=sys.stderr,
        )
        for v in errors:
            print(f"  {v.path}: {v.message} [{v.code}]", file=sys.stderr)
        for v in warnings:
            print(f"  warning: {v.path}: {v.message} [{v.code}]", file=sys.stderr)
        return 1

    for v in warnings:
        print(f"warning: {v.path}: {v.message} [{v.code}]", file=sys.stderr)
    print(f"scan-check: ok — {scan_path} ({confidence})")
    if confidence == ConfidenceLevel.EXTRACTED:
        # Valid but uncurated. Worth saying out loud: a seed that validates
        # is a correctly-shaped map of the code's structure, and still says
        # nothing about what the project does.
        print(
            "  note: this is the deterministic seed. Run the codebase-scan "
            "stage to author the curated map."
        )
    return 0
