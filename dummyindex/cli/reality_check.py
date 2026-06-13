"""`dummyindex context reality-check` — post-synthesis fact-check vs. extraction graph."""
from __future__ import annotations
import json
import sys
from .common import parse_kv_flags, parse_path_and_root, resolve_context_root


def run(args: list[str]) -> int:
    """`dummyindex context reality-check --feature ID` — fact-check the docs.

    With ``--demote``, a report with contradictions flips the feature's
    confidence to AMBIGUOUS (stashing the prior value), and a clean report
    restores the stashed confidence — so the documented loop "fix docs →
    re-run reality-check --demote" self-heals.
    """
    from dummyindex.context.domains.reality_check import (
        demote_feature_on_contradiction,
        promote_feature_on_clean,
        reality_check_feature,
        render_report_md,
        write_report,
    )

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    parsed, leftover = parse_kv_flags(rest)
    as_json = False
    demote = False
    final_leftover: list[str] = []
    for a in leftover:
        if a == "--json":
            as_json = True
        elif a == "--demote":
            demote = True
        else:
            final_leftover.append(a)
    if final_leftover:
        print(f"error: unknown argument(s) for `reality-check`: {final_leftover}", file=sys.stderr)
        return 2
    feature_id = parsed.get("feature")
    if not feature_id:
        print(
            "error: --feature <id> is required",
            file=sys.stderr,
        )
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    context_dir = out_root / ".context"
    if not context_dir.is_dir():
        print(
            f"error: {context_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        report = reality_check_feature(context_dir, feature_id)
    except FileNotFoundError as exc:
        print(f"error: feature folder {exc} not found", file=sys.stderr)
        return 2

    feat_dir = context_dir / "features" / feature_id
    write_report(feat_dir, report)

    if demote:
        if report.has_contradictions:
            demote_feature_on_contradiction(context_dir / "features", report)
        else:
            promote_feature_on_clean(context_dir / "features", report)

    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_report_md(report), end="")
    return 1 if report.has_contradictions else 0

