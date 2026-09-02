"""Arm definitions: identical base, exactly one delta.

The two-arm discipline mirrors ``tests/eval/behavior_arms.py``: both arms
share an identical neutral ``AGENTS.md`` base and differ by exactly the
`.context/` navigation section — the faithful analogue of ponytail's additive
arms (baseline appends nothing, guidance adds the shipped file). An earlier
design replaced the whole file per arm, which made the context arm an ablation
("index INSTEAD OF normal scaffolding") rather than a measurement ("baseline
PLUS the index"); that mistake is documented in ``behavior_arms.py`` and not
repeated here.

Workspace preparation is fully scripted and deterministic:

1. Clone the target repo into a per-(repo, commit) cache (shared across arms).
2. Materialize an arm-local copy at the pinned commit.
3. Arm A only: run ``dummyindex ingest --platform agents --no-hooks ...`` to
   build the `.context/` backbone.
4. Write the rendered ``AGENTS.md`` (overwriting anything ingest bootstrap
   wrote, so the instruction delta is exactly the section under test).

The git/indexer subprocess calls are injectable so tests can verify command
sequences without touching the network or the real CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Arm(str, Enum):
    """The two arms under test. Rendered as their plain value."""

    BASELINE = "baseline"
    CONTEXT = "context"

    __str__ = str.__str__


ARMS: tuple[Arm, ...] = (Arm.BASELINE, Arm.CONTEXT)


# ---------------------------------------------------------------------------
# AGENTS.md rendering
# ---------------------------------------------------------------------------

# Identical in both arms. Deliberately minimal: it states the working rules a
# benchmark agent needs (answer format discipline) without teaching any
# navigation strategy, so it cannot advantage either arm.
NEUTRAL_BASE = """\
# Benchmark workspace

You are completing a repository task as part of a measured evaluation.

Rules:
- Work only inside this repository checkout.
- When you have found the answer or finished the change, state it plainly and \
stop exploring.
"""


# The single delta under test. Present ONLY in the context arm's AGENTS.md.
CONTEXT_SECTION = """\

## Repository index available (`.context/`)

This repository carries a prebuilt PageIndex-style index at `.context/`.
Before grepping, navigate the map — it is faster and cheaper than searching
the source tree:

1. Run `dummyindex context query "<the task>"` for a deterministic ranked
   shortlist of relevant features (`--json` for machine output).
2. Read `.context/features/INDEX.json` (the table of contents) and reason over
   feature names + summaries; pick the 1-3 features the task touches. The
   query ranking is a hint, not a verdict.
3. Open `.context/features/<feature_id>/feature.json` for member files and
   entry points, then `spec.md` / `plan.md` / `concerns.md` as needed.
4. Follow `path:range` citations to source when you need exact code.
5. Symbol lookups: `.context/map/symbols.json`; file inventory:
   `.context/map/files.json`; structure: `.context/tree.json`.

Never grep the source tree first — walk the tree, then read source to verify.
"""


def render_agents_md(arm: Arm) -> str:
    """Render the workspace ``AGENTS.md`` for one arm.

    The baseline arm gets exactly :data:`NEUTRAL_BASE`; the context arm gets
    the same bytes plus :data:`CONTEXT_SECTION` appended — the shared-base /
    single-delta contract.
    """
    if arm is Arm.BASELINE:
        return NEUTRAL_BASE
    if arm is Arm.CONTEXT:
        return NEUTRAL_BASE + CONTEXT_SECTION
    raise ValueError(f"unknown arm: {arm!r}")


# ---------------------------------------------------------------------------
# Workspace preparation
# ---------------------------------------------------------------------------


def _run(argv: list[str], *, cwd: Path | None = None) -> None:
    """Run a setup subprocess; any failure is a hard error, never silent."""
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise WorkspaceError(
            f"{' '.join(argv)} exited {result.returncode} "
            f"(cwd={cwd}): stderr={result.stderr[-500:]!r}"
        )


class WorkspaceError(Exception):
    """Raised when workspace clone/pin/index preparation fails."""


def repo_cache_dir(repo: str, commit: str, cache_root: Path) -> Path:
    """Stable per-(repo, commit) cache path shared by every arm."""
    slug = repo.replace("/", "-")
    return cache_root / f"{slug}-{commit[:12]}"


def ensure_pinned_clone(
    repo: str,
    commit: str,
    *,
    cache_root: Path,
    url_for: Callable[[str], str] | None = None,
    run_fn: Callable[..., None] | None = None,
) -> Path:
    """Clone ``repo`` once at ``commit`` into the shared cache and return it.

    Full clones (not shallow): arbitrary pinned commits are checked out from
    history, and SWE-bench grading needs the base commit reachable. Idempotent
    — an existing cache dir with a completion marker is reused untouched.
    """
    url = url_for(repo) if url_for else f"https://github.com/{repo}.git"
    runner = run_fn or _run
    dest = repo_cache_dir(repo, commit, cache_root)
    marker = dest / ".git" / "BI_BENCH_PINNED"
    if (dest / ".git").exists() and marker.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    runner(["git", "clone", url, str(dest)])
    runner(["git", "checkout", "--detach", commit], cwd=dest)
    marker.write_text(commit + "\n")
    return dest


def materialize_workspace(cached: Path, target: Path, *, copy_fn=None) -> Path:
    """Copy a cached pinned clone into a fresh arm-local workspace.

    The default path copies into a sibling temp dir and renames atomically,
    so a concurrent duplicate can never observe a half-populated target; on
    losing such a race the caller retries and takes the reuse branch.
    """
    if target.exists():
        raise WorkspaceError(f"workspace already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    copier = copy_fn or shutil.copytree
    if copy_fn is not None:
        copier(cached, target)
        return target
    tmp = target.parent / f".{target.name}.tmp-{os.getpid()}-{threading.get_ident()}"
    try:
        shutil.copytree(cached, tmp)
        os.rename(tmp, target)
    except OSError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        if target.exists():
            raise WorkspaceError(
                f"lost workspace-creation race for {target}: {exc}"
            ) from exc
        raise
    return target


INGEST_ARGV_TEMPLATE = [
    "dummyindex",
    "ingest",
    "--platform",
    "agents",
    "--no-hooks",
    "--no-default-plugins",
    "--no-superpowers",
    # Workspace-local .context/ is a disposable artifact rebuilt from the
    # pinned cache; if a prior agent session enriched it, discarding that
    # curation is exactly what we want on rebuild.
    "--force",
]


@dataclass(frozen=True)
class PreparedWorkspace:
    """One arm-local, task-ready workspace."""

    arm: Arm
    path: Path
    agents_md: str
    indexed: bool
    index_mode: str = "none"  # "none" | "backbone" | "enriched"


READY_MARKER = ".bi_bench_ready"
ENRICH_MARKER = ".bi_bench_enriched"


def is_enriched(root: Path) -> bool:
    """True when the cached clone carries a completed council enrichment."""
    return (root / ENRICH_MARKER).exists()


def mark_enriched(root: Path, *, mode: str, units: int) -> None:
    (root / ENRICH_MARKER).write_text(
        json.dumps({"mode": mode, "units": units}, sort_keys=True) + "\n"
    )


def _ready_marker_path(target: Path) -> Path:
    return target / READY_MARKER


def _recently_modified(target: Path, max_age_s: float = 60.0) -> bool:
    """True if anything under ``target`` changed within the last window."""
    import time as _time

    now = _time.time()
    try:
        candidates = [target.stat().st_mtime]
        for child in target.iterdir():
            try:
                candidates.append(child.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        return False
    return (now - max(candidates)) <= max_age_s


def prepare_arm_workspace(
    arm: Arm,
    repo: str,
    commit: str,
    workspace_root: Path,
    *,
    cache_root: Path,
    repeat: int | None = None,
    indexer=None,
    run_setup=None,
    copy_fn=None,
) -> PreparedWorkspace:
    """Prepare one arm's workspace for one suite task.

    Steps: ensure the shared pinned clone, materialize an arm-local copy,
    optionally build the `.context/` backbone (context arm only), then write
    the rendered ``AGENTS.md`` last so no other writer can append to it.

    Idempotent for resume: a workspace whose ready marker matches
    ``arm:commit`` is reused untouched; a leftover partial directory (crash
    mid-copy or mid-ingest) is wiped and rebuilt from the shared cache.

    ``repeat`` namespaces the directory per repetition so parallel repeats
    of the same task never share (and corrupt) one checkout.
    """
    cached = ensure_pinned_clone(repo, commit, cache_root=cache_root, run_fn=run_setup)
    ws_name = f"{repo.replace('/', '-')}-{commit[:12]}-{arm.value}"
    if repeat is not None:
        ws_name += f"-r{repeat}"
    target = workspace_root / ws_name

    expected_ready = f"{arm.value}:{commit}"
    marker = _ready_marker_path(target)
    if target.exists():
        # A racing twin may have just created the dir but not yet written
        # its ready marker; give it a short window before wiping.
        for _ in range(15):
            if marker.exists() and marker.read_text().startswith(expected_ready + ":"):
                doc = render_agents_md(arm)
                return PreparedWorkspace(
                    arm=arm,
                    path=target,
                    agents_md=doc,
                    indexed=marker_indexed(marker),
                    index_mode=marker_index_mode(marker),
                )
            if not _recently_modified(target):
                break
            time.sleep(2.0)
        if not (
            marker.exists() and marker.read_text().startswith(expected_ready + ":")
        ):
            shutil.rmtree(target)

    materialize_workspace(cached, target, copy_fn=copy_fn)

    # The cache clone may carry a completed council enrichment. The context
    # arm inherits it verbatim (skipping re-ingest — never overwrite curated
    # work); the baseline arm must NEVER see it, so strip it after copy.
    cache_enriched = is_enriched(cached)
    if arm is Arm.BASELINE and (target / ".context").exists():
        shutil.rmtree(target / ".context")

    index_mode = "none"
    indexed = False
    if arm is Arm.CONTEXT:
        if cache_enriched:
            # Inherit the curated index verbatim; re-ingesting would discard
            # exactly the council work phase 0 paid for.
            indexed = True
            index_mode = "enriched"
        else:
            argv = [*INGEST_ARGV_TEMPLATE, str(target)]
            (run_setup or _run)(argv)
            indexed = True
            index_mode = "backbone"

    doc = render_agents_md(arm)
    (target / "AGENTS.md").write_text(doc)
    marker.write_text(expected_ready + f":indexed={int(indexed)}:mode={index_mode}\n")
    return PreparedWorkspace(
        arm=arm, path=target, agents_md=doc, indexed=indexed, index_mode=index_mode
    )


def marker_indexed(marker: Path) -> bool:
    return "indexed=1" in marker.read_text()


def marker_index_mode(marker: Path) -> str:
    for part in marker.read_text().split(":"):
        if part.startswith("mode="):
            return part.removeprefix("mode=").strip()
    return "backbone"
