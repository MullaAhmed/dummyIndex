"""`dummyindex context features-rename / features-merge / flow-remove / section-write`."""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional
from ._common import _parse_kv_flags, _parse_path_and_root, _resolve_context_root


def _cmd_features_rename(args: list[str]) -> int:
    from dummyindex.context.domains.features import FeatureRenameError, rename_feature

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)

    from_id: Optional[str] = None
    to_id: Optional[str] = None
    new_name: Optional[str] = None
    new_summary: Optional[str] = None
    leftover: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--from" and i + 1 < len(rest):
            from_id = rest[i + 1]
            i += 2
        elif a.startswith("--from="):
            from_id = a.split("=", 1)[1]
            i += 1
        elif a == "--to" and i + 1 < len(rest):
            to_id = rest[i + 1]
            i += 2
        elif a.startswith("--to="):
            to_id = a.split("=", 1)[1]
            i += 1
        elif a == "--name" and i + 1 < len(rest):
            new_name = rest[i + 1]
            i += 2
        elif a.startswith("--name="):
            new_name = a.split("=", 1)[1]
            i += 1
        elif a == "--summary" and i + 1 < len(rest):
            new_summary = rest[i + 1]
            i += 2
        elif a.startswith("--summary="):
            new_summary = a.split("=", 1)[1]
            i += 1
        else:
            leftover.append(a)
            i += 1
    if leftover:
        print(
            f"error: unknown argument(s) for `features-rename`: {leftover}",
            file=sys.stderr,
        )
        return 2
    if not from_id or not to_id:
        print(
            "error: --from <id> and --to <id> are both required",
            file=sys.stderr,
        )
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
        result = rename_feature(
            features_dir,
            from_id=from_id,
            to_id=to_id,
            new_name=new_name,
            new_summary=new_summary,
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.from_id == result.to_id:
        print(f"context features-rename: updated metadata for {result.to_id}")
    else:
        print(
            f"context features-rename: {result.from_id}  →  {result.to_id}"
        )
    if result.new_name or result.new_summary:
        if result.new_name:
            print(f"  name:    {result.new_name}")
        if result.new_summary:
            print(f"  summary: {result.new_summary}")
    if result.files_touched:
        print(f"  touched: {len(result.files_touched)} file(s)")
    return 0

def _cmd_features_merge(args: list[str]) -> int:
    """Atomically merge a trivial feature into another as a section."""
    from dummyindex.context.domains.features import FeatureRenameError, merge_feature

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)
    parsed, leftover = _parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `features-merge`: {leftover}",
            file=sys.stderr,
        )
        return 2
    from_id = parsed.get("from")
    into_id = parsed.get("into")
    as_section = parsed.get("as-section", "supporting")
    note = parsed.get("note")
    if not from_id or not into_id:
        print(
            "error: --from <id> and --into <id> are both required "
            "(optional: --as-section NAME, default 'supporting'; "
            "--note \"...\" chairman rationale, auto-generated if omitted)",
            file=sys.stderr,
        )
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
        result = merge_feature(
            features_dir,
            from_id=from_id,
            into_id=into_id,
            as_section=as_section,
            note=note,
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context features-merge: {result.from_id}  →  {result.to_id} "
        f"(as `{result.section}`, {len(result.files_touched)} files touched)"
    )
    return 0

def _cmd_flow_remove(args: list[str]) -> int:
    """Atomically remove a flow from a feature."""
    from dummyindex.context.domains.features import FeatureRenameError, remove_flow

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)
    parsed, leftover = _parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `flow-remove`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    flow_id = parsed.get("flow")
    if not feature_id or not flow_id:
        print(
            "error: --feature <id> and --flow <id> are both required",
            file=sys.stderr,
        )
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
        result = remove_flow(features_dir, feature_id=feature_id, flow_id=flow_id)
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.files_touched:
        print(
            f"context flow-remove: dropped {flow_id} from {feature_id} "
            f"({len(result.files_touched)} file(s) touched)"
        )
    else:
        print(f"context flow-remove: no-op (flow {flow_id} not present)")
    return 0

def _cmd_section_write(args: list[str]) -> int:
    """Atomic placement of a markdown into a feature's section."""
    from dummyindex.context.domains.features import FeatureRenameError, write_section

    scope, explicit_root, rest = _parse_path_and_root(args, take_positional=False)
    parsed, leftover = _parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `section-write`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    section = parsed.get("section")
    from_file = parsed.get("from-file")
    if not all((feature_id, section, from_file)):
        print(
            "error: --feature <id>, --section <name>, --from-file <path> are all required",
            file=sys.stderr,
        )
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
        target = write_section(
            features_dir,
            feature_id=feature_id,
            section=section,
            source_file=Path(from_file),
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"context section-write: {target}")
    return 0

