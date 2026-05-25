"""`dummyindex context council-log` — append a council-debate log row."""
from __future__ import annotations
import sys
from ._common import _parse_kv_flags, _parse_path_and_root, _resolve_context_root


def _cmd_council_log(args: list[str]) -> int:
    """Append a council-log entry for a (feature, stage, agent) triple."""
    from dummyindex.context.domains.council import CouncilLogError, append_log

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)
    parsed, leftover = _parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `council-log`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    stage = parsed.get("stage")
    agent = parsed.get("agent")
    log_status = parsed.get("status")
    note = parsed.get("note")
    if not all((feature_id, stage, agent, log_status)):
        print(
            "error: --feature <id>, --stage <n>, --agent <name>, --status <state> are all required",
            file=sys.stderr,
        )
        return 2

    try:
        stage_int = int(stage)
    except ValueError:
        print(f"error: --stage must be an integer, got {stage!r}", file=sys.stderr)
        return 2

    out_root = _resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        entry = append_log(
            features_dir,
            feature_id=feature_id,
            stage=stage_int,
            agent=agent,
            status=log_status,
            note=note,
        )
    except CouncilLogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context council-log: {feature_id} stage={entry.stage} "
        f"agent={entry.agent} status={entry.status}"
    )
    return 0

