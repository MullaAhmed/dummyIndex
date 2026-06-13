"""`dummyindex context features-rename / features-merge / flow-remove / section-write / scaffold-feature / assign-files`."""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional
from .common import (
    parse_kv_flags,
    parse_path_and_root,
    pull_repeatable_flag,
    resolve_context_root,
)

# CLI-boundary guard for `section-write` (mirrors the section alphabet in
# `domains/features/ops.py:write_section`'s docstring). Canonical v0.14
# sections are always writable; a legacy essay name may only UPDATE an
# existing file — creating a new legacy sibling (the stray `security.md`
# pattern) needs the explicit `--allow-new-section` escape hatch.
_CANONICAL_SECTIONS = frozenset({"spec", "plan", "concerns"})
_LEGACY_SECTIONS = frozenset(
    {
        "README",
        "architecture",
        "implementation",
        "data-model",
        "security",
        "product",
        "supporting",
    }
)


def run_rename(args: list[str]) -> int:
    from dummyindex.context.domains.features import FeatureRenameError, rename_feature

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)

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

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
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

def run_merge(args: list[str]) -> int:
    """Atomically merge a trivial feature into another as a section."""
    from dummyindex.context.domains.features import FeatureRenameError, merge_feature

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    parsed, leftover = parse_kv_flags(rest)
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

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
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

def run_flow_remove(args: list[str]) -> int:
    """Atomically remove a flow from a feature."""
    from dummyindex.context.domains.features import FeatureRenameError, remove_flow

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    parsed, leftover = parse_kv_flags(rest)
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

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
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

def _validate_section_name(
    features_dir: Path, *, feature_id: str, section: str, allow_new: bool
) -> Optional[str]:
    """Section-name guard for `section-write`. Returns an error message or None.

    Rule: canonical names always pass; a legacy essay name passes only when
    its target file already exists (transition-window updates keep working,
    but a NEW legacy sibling in a canonical-shaped feature is the stray
    `security.md` failure mode); anything else is rejected unless
    ``--allow-new-section`` was given.
    """
    if allow_new:
        return None
    name = section[:-3] if section.endswith(".md") else section
    if name in _CANONICAL_SECTIONS:
        return None
    if (features_dir / feature_id / f"{name}.md").is_file():
        return None  # updating an existing (legacy or extension) section
    canonical = ", ".join(sorted(_CANONICAL_SECTIONS))
    if name in _LEGACY_SECTIONS:
        return (
            f"--section {section!r} would create a new legacy file. Canonical "
            f"sections: {canonical}. Critique output belongs in `--section "
            f"concerns`; legacy sections may only be updated, not created "
            f"(pass --allow-new-section to override)."
        )
    return (
        f"--section {section!r} is not a canonical section ({canonical}) and "
        f"no such file exists yet (pass --allow-new-section to deliberately "
        f"create `{name}.md`)."
    )


def run_section_write(args: list[str]) -> int:
    """Atomic placement of a markdown into a feature's section.

    Canonical sections (spec/plan/concerns) are always writable; legacy essay
    names only update an existing file; anything else needs
    ``--allow-new-section``.
    """
    from dummyindex.context.domains.features import FeatureRenameError, write_section

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    allow_new = "--allow-new-section" in rest
    rest = [a for a in rest if a != "--allow-new-section"]
    parsed, leftover = parse_kv_flags(rest)
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

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    section_error = _validate_section_name(
        features_dir, feature_id=feature_id, section=section, allow_new=allow_new
    )
    if section_error:
        print(f"error: {section_error}", file=sys.stderr)
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


def run_scaffold(args: list[str]) -> int:
    """Atomically scaffold a NEW feature folder for net-new files."""
    from dummyindex.context.domains.features import FeatureRenameError, scaffold_feature

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    file_values, rest = pull_repeatable_flag(rest, "file")
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `scaffold-feature`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("id")
    name = parsed.get("name")
    summary = parsed.get("summary")
    if not feature_id or not name or not file_values:
        print(
            "error: --id <feature_id>, --name \"<name>\", and at least one "
            "--file <path> are required (optional: --summary \"...\")",
            file=sys.stderr,
        )
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        result = scaffold_feature(
            features_dir,
            repo_root=out_root,
            feature_id=feature_id,
            name=name,
            summary=summary,
            files=[Path(f) for f in file_values],
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context scaffold-feature: created {result.feature_id} "
        f"({len(result.files)} file(s), {len(result.members)} member(s))"
    )
    return 0


def run_assign_files(args: list[str]) -> int:
    """Atomically add files to an EXISTING feature (preserves enrichment)."""
    from dummyindex.context.domains.features import FeatureRenameError, assign_files

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    file_values, rest = pull_repeatable_flag(rest, "file")
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `assign-files`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    if not feature_id or not file_values:
        print(
            "error: --feature <feature_id> and at least one --file <path> "
            "are required",
            file=sys.stderr,
        )
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        result = assign_files(
            features_dir,
            repo_root=out_root,
            feature_id=feature_id,
            files=[Path(f) for f in file_values],
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context assign-files: {result.feature_id} now owns "
        f"{len(result.files)} file(s), {len(result.members)} member(s)"
    )
    return 0


def run_unassign_files(args: list[str]) -> int:
    """Atomically remove files from an EXISTING feature (preserves enrichment)."""
    from dummyindex.context.domains.features import FeatureRenameError, unassign_files

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    file_values, rest = pull_repeatable_flag(rest, "file")
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `unassign-files`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    if not feature_id or not file_values:
        print(
            "error: --feature <feature_id> and at least one --file <path> "
            "are required",
            file=sys.stderr,
        )
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        result = unassign_files(
            features_dir,
            repo_root=out_root,
            feature_id=feature_id,
            files=[Path(f) for f in file_values],
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context unassign-files: {result.feature_id} now owns "
        f"{len(result.files)} file(s), {len(result.members)} member(s)"
    )
    return 0


def run_remove(args: list[str]) -> int:
    """Atomically delete a feature whose code is gone (drop folder + index)."""
    from dummyindex.context.domains.features import FeatureRenameError, remove_feature

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    force = "--force" in rest
    rest = [a for a in rest if a != "--force"]
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `features-remove`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    if not feature_id:
        print("error: --feature <id> is required", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        result = remove_feature(
            features_dir,
            feature_id=feature_id,
            repo_root=out_root,
            force=force,
        )
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"context features-remove: deleted {result.feature_id} "
        f"({len(result.files_touched)} file(s) touched)"
    )
    return 0


def run_mark_enriched(args: list[str]) -> int:
    """Clear a feature's pending-enrichment marker after the council enriched it."""
    from dummyindex.context.domains.features import (
        FeatureRenameError,
        clear_pending_enrichment,
    )

    scope, explicit_root, rest = parse_path_and_root(args, take_positional=False)
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(
            f"error: unknown argument(s) for `mark-enriched`: {leftover}",
            file=sys.stderr,
        )
        return 2
    feature_id = parsed.get("feature")
    if not feature_id:
        print("error: --feature <id> is required", file=sys.stderr)
        return 2

    out_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = out_root / ".context" / "features"
    if not features_dir.is_dir():
        print(
            f"error: {features_dir} not found. Run `dummyindex ingest` first.",
            file=sys.stderr,
        )
        return 2

    try:
        cleared = clear_pending_enrichment(features_dir, feature_id)
    except FeatureRenameError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if cleared:
        print(
            f"context mark-enriched: cleared pending-enrichment for {feature_id}"
        )
    else:
        print(
            f"context mark-enriched: {feature_id} had no pending-enrichment "
            "marker (no-op)"
        )
    return 0

