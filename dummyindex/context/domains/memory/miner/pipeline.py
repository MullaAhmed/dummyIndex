"""Top-level orchestration: resolve a store, scan it, group, write.

Kept separate from `resolve.py` / `scan.py` / `signatures.py` / `render.py` /
`scope.py` so each concern stays independently testable (folder-organization
convention); this module only composes them.

The composition itself carries one rule worth stating plainly: **the default
scan is scoped to a single repo**. A transcript store spans every project the
host has ever opened, and the report lands in a git-tracked file, so pooling
the whole store would publish other repos' paths into this one. Cross-project
scanning stays available but has to be asked for by name. See `scope.py`.
"""

from __future__ import annotations

from pathlib import Path

from .corrections import aggregate_skill_corrections
from .enums import DEFAULT_MIN_OCCURRENCES
from .feedback import write_skill_feedback
from .models import (
    MinerReport,
    RecurringSkillCorrection,
    SkillDirectiveEvent,
    ToolCallRecord,
)
from .render import write_report
from .resolve import resolve_claude_config_dirs, resolve_transcript_store
from .scan import (
    discover_project_dirs,
    iter_main_transcript_files,
    iter_transcript_files,
    parse_skill_directive_events,
    parse_transcript,
)
from .scope import project_dir_name
from .signatures import detect_repeated_signatures


def scan_transcript_store(
    store_dir: Path,
    *,
    repo_root: Path | None = None,
    min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
) -> MinerReport:
    """Scan transcripts under `store_dir` into a `MinerReport`.

    With `repo_root`, only that repo's own project directory is read — the
    safe default for anything that gets written down. Without it, the whole
    store is pooled; that is the explicit, opt-in cross-project mode.

    Deterministic either way: discovery is sorted, parsing is a pure read,
    and grouping breaks ties on the signature string (see `signatures.py`).
    """
    if repo_root is None:
        project_dirs = discover_project_dirs(store_dir)
    else:
        wanted = project_dir_name(repo_root)
        project_dirs = tuple(
            d for d in discover_project_dirs(store_dir) if d.name == wanted
        )

    records_by_session: list[tuple[ToolCallRecord, ...]] = []
    unreadable = 0
    for project_dir in project_dirs:
        for transcript_path in iter_transcript_files(project_dir):
            records = parse_transcript(transcript_path)
            if records:
                records_by_session.append(records)
            else:
                unreadable += 1

    signatures = detect_repeated_signatures(
        records_by_session, min_occurrences=min_occurrences
    )
    return MinerReport(
        signatures=signatures,
        scanned_sessions=len(records_by_session),
        unreadable_sessions=unreadable,
    )


def mine_and_feed(
    context_dir: Path,
    *,
    store_override: Path | None = None,
    min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
    all_projects: bool = False,
) -> MinerReport:
    """Resolve the transcript store, scan this repo's slice of it, and write
    the result into `context_dir`'s session-memory store.

    `context_dir` is the repo's `.context/` directory, so its parent is the
    repo root — that is what scopes the scan and what paths are made relative
    to. Pass `all_projects=True` to pool the entire host store instead; do
    that only when the output is *not* going somewhere that gets committed.

    `store_override` overrides the resolved *config* directory (see
    `resolve.resolve_transcript_store`), not the store path directly.
    """
    repo_root = context_dir.resolve().parent
    store_dir = resolve_transcript_store(override=store_override)
    report = scan_transcript_store(
        store_dir,
        repo_root=None if all_projects else repo_root,
        min_occurrences=min_occurrences,
    )
    write_report(context_dir, report, repo_root=repo_root)
    return report


def scan_skill_feedback(
    repo_root: Path,
    *,
    config_dirs: tuple[Path, ...],
) -> tuple[RecurringSkillCorrection, ...]:
    """Aggregate safe human corrections across local Claude profiles."""
    try:
        resolved_root = repo_root.resolve()
    except (OSError, RuntimeError):
        return ()
    wanted = project_dir_name(resolved_root)
    events: list[SkillDirectiveEvent] = []
    unique_configs = tuple(sorted(set(config_dirs), key=lambda path: str(path)))
    for config_index, config_dir in enumerate(unique_configs):
        project_dir = config_dir / "projects" / wanted
        for file_index, transcript in enumerate(
            iter_main_transcript_files(project_dir)
        ):
            events.extend(
                parse_skill_directive_events(
                    transcript,
                    repo_root=resolved_root,
                    fallback_prefix=(config_index, file_index),
                )
            )
    return aggregate_skill_corrections(events)


def refresh_skill_feedback(
    context_dir: Path,
    *,
    config_override: Path | None = None,
) -> tuple[RecurringSkillCorrection, ...]:
    """Refresh the gitignored cache from every applicable local profile."""
    repo_root = context_dir.resolve().parent
    feedback = scan_skill_feedback(
        repo_root,
        config_dirs=resolve_claude_config_dirs(override=config_override),
    )
    write_skill_feedback(context_dir, feedback)
    return feedback
