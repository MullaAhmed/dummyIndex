"""Managed Codex guidance in project and user-global instruction files."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from dummyindex.codex_guidance import (
    CODEX_INSTRUCTION_PRECEDENCE,
    codex_home,
    configured_project_doc_fallback_filenames,
    configured_project_doc_max_bytes,
)

from .bootstrap import (
    ALWAYS_ON_OUTPUT_POLICY,
    _managed_block_span,
    bootstrap_claude_md,
    remove_managed_block,
)

AGENTS_BEGIN_MARKER = (
    "<!-- dummyindex:begin:codex (managed — do not hand-edit; "
    "regenerate with `dummyindex install --platform codex`) -->"
)
AGENTS_END_MARKER = "<!-- dummyindex:end:codex -->"
PROJECT_OWNER_EXPLICIT = "project"
PROJECT_OWNER_USER_AUTO_INIT = "user-auto-init"
_PROJECT_OWNER_PREFIX = "<!-- dummyindex:owner:"

_PROJECT_BLOCK = f"""\
## dummyIndex context engine

This repo has a generated context index at `.context/`. **Read
`.context/HOW_TO_USE.md` before any non-trivial task** and follow its routing
before searching source broadly. Treat the code as the source of truth when it
disagrees with the index. Refresh deterministic maps with `dummyindex context
rebuild --changed`; reconcile curated feature documentation through
`dummyindex context reconcile` (read-only), the dummyindex reconcile skill,
and `dummyindex context reconcile-stamp`. Invoke reusable dummyindex
workflows — `dummyindex`, `dummyindex-plan`, `dummyindex-build`,
`dummyindex-equip`, `dummyindex-audit`, `dummyindex-remember`,
`dummyindex-gc`, and `dummyindex-update` — through whatever mechanism your
host uses to invoke an installed skill. The user's explicit instruction wins
over an older `.context/` spec or plan; note the divergence and proceed. Use
your host's own session/usage reporting for context and token accounting;
`dummyindex usage` specifically reads saved Claude Code transcripts and is not
a general session reporter.

{ALWAYS_ON_OUTPUT_POLICY}
"""

_GLOBAL_BLOCK = """\
## dummyIndex

The dummyindex skill family is installed under
`~/.agents/skills/dummyindex*/`. Invoke it however your host exposes an
installed skill — a slash command, a skill picker, or a direct name. In any
repository containing `.context/`, read `.context/HOW_TO_USE.md` before broad
source searches and use the indexed maps and feature docs as navigation aids.
The code and the user's current request remain authoritative when generated
context is stale. Use your host's own session/usage reporting for token
information; `dummyindex usage` reads saved Claude Code transcripts and is not
a general session reporter.
"""


_AGENTS_FILENAMES = CODEX_INSTRUCTION_PRECEDENCE
_MANAGED_GUIDANCE_SCAN_MAX_FILES = 20_000
_MANAGED_GUIDANCE_SCAN_MAX_DEPTH = 32
_MANAGED_GUIDANCE_SCAN_MAX_BYTES_PER_FILE = 256 * 1024
_MANAGED_GUIDANCE_SCAN_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".context",
        ".claude",
        ".agents",
        ".codex",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
)


@dataclass(frozen=True)
class AgentsMdCleanupIssue:
    """One AGENTS file that could not be safely cleaned."""

    path: Path
    message: str


@dataclass(frozen=True)
class AgentsMdCleanupResult:
    """Independent cleanup outcomes for the inspected Codex guidance files."""

    removed: tuple[Path, ...]
    errors: tuple[AgentsMdCleanupIssue, ...]


def bootstrap_project_agents_md(
    project_root: Path,
    *,
    owner: str = PROJECT_OWNER_EXPLICIT,
) -> Path:
    """Write/update the block in the active project-level Codex guidance.

    Codex selects the first existing regular candidate in precedence order,
    even when it is empty. Reuse exactly that target so a blank override cannot
    shadow a newly written lower-precedence file.
    """
    path, block_body = _project_guidance_plan(project_root, owner=owner)
    bootstrap_claude_md(
        path,
        block_body=block_body,
        begin_marker=AGENTS_BEGIN_MARKER,
        end_marker=AGENTS_END_MARKER,
        place_first=True,
    )
    return path


def preflight_project_agents_md(
    project_root: Path,
    *,
    owner: str = PROJECT_OWNER_EXPLICIT,
) -> Path:
    """Validate and resolve the active project target without writing it."""
    path, _block_body = _project_guidance_plan(project_root, owner=owner)
    return path


def _project_guidance_plan(project_root: Path, *, owner: str) -> tuple[Path, str]:
    """Resolve all deterministic project-guidance choices and validations."""
    if owner not in {PROJECT_OWNER_EXPLICIT, PROJECT_OWNER_USER_AUTO_INIT}:
        raise ValueError(f"unknown Codex project-guidance owner: {owner!r}")

    path = _active_project_agents_path(
        project_root,
        fallback_filenames=configured_project_doc_fallback_filenames(project_root),
    )
    _ensure_guidance_target_in_scope(project_root, path)
    has_existing_block, existing_owner = _project_guidance_owner(path)
    effective_owner: str | None = owner
    if owner == PROJECT_OWNER_USER_AUTO_INIT and has_existing_block:
        # A user-level reinstall may refresh a block, but must never take
        # ownership from an explicit project install/ingest. Legacy unowned
        # blocks remain unowned so user uninstall stays conservative.
        effective_owner = existing_owner
    block_body = _render_project_block(effective_owner)
    _validate_project_block_budget(project_root, path, block_body)
    return path, block_body


def bootstrap_global_agents_md(home: Path | None = None) -> Path:
    """Write/update the block in Codex's active user-global guidance file.

    ``CODEX_HOME`` is authoritative when set; otherwise Codex defaults to
    ``~/.codex``.  As at project scope, the first nonempty candidate wins.
    """
    directory = codex_home(home)
    path = _active_agents_path(directory)
    _ensure_guidance_target_in_scope(directory, path)
    bootstrap_claude_md(
        path,
        block_body=_GLOBAL_BLOCK,
        begin_marker=AGENTS_BEGIN_MARKER,
        end_marker=AGENTS_END_MARKER,
        place_first=True,
    )
    return path


def remove_project_agents_md(
    project_root: Path,
    *,
    owner: str | None = None,
) -> AgentsMdCleanupResult:
    """Remove dummyindex's block from project guidance files, if present."""
    if owner not in {None, PROJECT_OWNER_EXPLICIT, PROJECT_OWNER_USER_AUTO_INIT}:
        raise ValueError(f"unknown Codex project-guidance owner: {owner!r}")
    configured = configured_project_doc_fallback_filenames(project_root)
    return _remove_agents_blocks(
        project_root,
        fallback_filenames=(
            *configured,
            *_discover_managed_project_guidance(project_root, configured),
        ),
        owner=owner,
    )


def remove_global_agents_md(home: Path | None = None) -> AgentsMdCleanupResult:
    """Remove dummyindex's block from user-global Codex AGENTS files."""
    return _remove_agents_blocks(codex_home(home))


def _active_agents_path(
    directory: Path,
    *,
    fallback_filenames: tuple[str, ...] = (),
) -> Path:
    standard = directory / "AGENTS.md"
    for name in (*_AGENTS_FILENAMES, *fallback_filenames):
        candidate = directory / name
        if _has_nonwhitespace_content(candidate):
            return candidate
    # Neither candidate is active.  AGENTS.md is Codex's canonical filename
    # and is the least surprising creation target, including when a blank
    # override already exists.
    return standard


def _active_project_agents_path(
    directory: Path,
    *,
    fallback_filenames: tuple[str, ...] = (),
) -> Path:
    """Select the first existing project candidate, matching Codex discovery."""
    for name in (*_AGENTS_FILENAMES, *fallback_filenames):
        candidate = _relative_guidance_path(directory, name)
        try:
            metadata = candidate.stat()
        except FileNotFoundError:
            continue
        except OSError:
            return candidate
        else:
            if stat.S_ISREG(metadata.st_mode):
                return candidate
    return directory / "AGENTS.md"


def _has_nonwhitespace_content(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except (OSError, UnicodeError):
        # Do not silently bypass an existing candidate whose contents cannot
        # be inspected.  Selecting it lets bootstrap surface the real error
        # rather than writing a lower-precedence file that Codex may ignore.
        return True


def _ensure_guidance_target_in_scope(directory: Path, path: Path) -> None:
    """Reject a guidance path whose resolved target escapes its selected scope.

    Nested fallbacks may contain symlinked parent directories even when the leaf
    itself is regular. Resolve every selected path before a read or write so a
    repository-controlled link cannot escape the repository. The same boundary
    applies to user-global guidance beneath the active ``CODEX_HOME``.
    """
    try:
        scope = directory.resolve()
        target = path.resolve(strict=False)
        target.relative_to(scope)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(
            f"refusing to access out-of-scope Codex guidance path {path}"
        ) from exc


def _discover_managed_project_guidance(
    directory: Path,
    configured_filenames: tuple[str, ...],
) -> tuple[str, ...]:
    """Find managed files left under an older fallback configuration.

    Codex config can change between install and uninstall, including removal of
    a nested fallback. A bounded recursive scan finds the exact dummyindex
    marker without following directory symlinks or treating marker-free files
    as owned.
    """
    known = {*_AGENTS_FILENAMES, *configured_filenames}
    discovered: list[str] = []
    inspected = 0
    root = directory.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        try:
            depth = len(current.relative_to(root).parts)
        except ValueError:
            continue
        if depth >= _MANAGED_GUIDANCE_SCAN_MAX_DEPTH:
            dirnames.clear()
        else:
            safe_dirs: list[str] = []
            for name in sorted(dirnames):
                if name in _MANAGED_GUIDANCE_SCAN_SKIP_DIRS:
                    continue
                child = current / name
                try:
                    if not child.is_symlink():
                        safe_dirs.append(name)
                except OSError:
                    continue
            dirnames[:] = safe_dirs

        for filename in sorted(filenames):
            inspected += 1
            if inspected > _MANAGED_GUIDANCE_SCAN_MAX_FILES:
                return tuple(discovered)
            candidate = current / filename
            try:
                relative = candidate.relative_to(root).as_posix()
            except ValueError:
                continue
            if relative in known:
                continue
            try:
                _ensure_guidance_target_in_scope(root, candidate)
                is_file = candidate.is_file()
            except (OSError, ValueError):
                continue
            if is_file and _contains_agents_marker(candidate):
                discovered.append(relative)
    return tuple(discovered)


def _contains_agents_marker(path: Path) -> bool:
    """Search a bounded prefix for either marker without loading the file."""
    markers = (AGENTS_BEGIN_MARKER.encode(), AGENTS_END_MARKER.encode())
    overlap_size = max(len(marker) for marker in markers) - 1
    overlap = b""
    remaining = _MANAGED_GUIDANCE_SCAN_MAX_BYTES_PER_FILE
    try:
        with path.open("rb") as handle:
            while remaining > 0 and (chunk := handle.read(min(64 * 1024, remaining))):
                remaining -= len(chunk)
                window = overlap + chunk
                if any(marker in window for marker in markers):
                    return True
                overlap = window[-overlap_size:]
    except OSError:
        return False
    return False


def _render_project_block(owner: str | None) -> str:
    if owner is None:
        return _PROJECT_BLOCK
    return f"{_PROJECT_OWNER_PREFIX}{owner} -->\n{_PROJECT_BLOCK}"


def _project_guidance_owner(path: Path) -> tuple[bool, str | None]:
    """Return whether ``path`` has our block and its explicit owner, if any."""
    if not path.exists() and not path.is_symlink():
        return False, None
    existing = path.read_text(encoding="utf-8")
    span = _managed_block_span(
        existing,
        path=path,
        begin_marker=AGENTS_BEGIN_MARKER,
        end_marker=AGENTS_END_MARKER,
    )
    if span is None:
        return False, None
    managed_lines = existing[span.start : span.content_end].splitlines()
    owners = [
        line.strip()[len(_PROJECT_OWNER_PREFIX) : -len(" -->")]
        for line in managed_lines
        if line.strip().startswith(_PROJECT_OWNER_PREFIX)
        and line.strip().endswith(" -->")
    ]
    if len(owners) == 1 and owners[0] in {
        PROJECT_OWNER_EXPLICIT,
        PROJECT_OWNER_USER_AUTO_INIT,
    }:
        return True, owners[0]
    return True, None


def _validate_project_block_budget(
    project_root: Path,
    path: Path,
    block_body: str,
) -> None:
    """Refuse to claim success when Codex cannot read the complete block."""
    managed = f"{AGENTS_BEGIN_MARKER}\n{block_body.rstrip()}\n{AGENTS_END_MARKER}\n"
    prefix_bytes = 0
    try:
        with path.open("rb") as handle:
            if handle.read(3) == b"\xef\xbb\xbf":
                prefix_bytes = 3
    except FileNotFoundError:
        pass
    required = prefix_bytes + len(managed.encode("utf-8"))
    configured = configured_project_doc_max_bytes(project_root)
    if required > configured:
        raise ValueError(
            "dummyindex's managed Codex guidance needs "
            f"{required} bytes, but project_doc_max_bytes is {configured}; "
            "raise that Codex setting before retrying"
        )


def _remove_agents_blocks(
    directory: Path,
    *,
    fallback_filenames: tuple[str, ...] = (),
    owner: str | None = None,
) -> AgentsMdCleanupResult:
    """Clean both active and potentially stale inactive guidance files.

    A user may add or remove an override after installation, so uninstall must
    inspect both filenames.  The shared remover validates a complete ordered
    marker pair before changing each file and preserves every byte outside it.
    """
    removed: list[Path] = []
    errors: list[AgentsMdCleanupIssue] = []
    filenames = dict.fromkeys((*_AGENTS_FILENAMES, *fallback_filenames))
    for name in filenames:
        path = _relative_guidance_path(directory, name)
        try:
            _ensure_guidance_target_in_scope(directory, path)
            if owner is not None:
                has_block, existing_owner = _project_guidance_owner(path)
                if not has_block or existing_owner != owner:
                    continue
            changed = remove_managed_block(
                path,
                begin_marker=AGENTS_BEGIN_MARKER,
                end_marker=AGENTS_END_MARKER,
                placed_first=True,
            )
        except (OSError, ValueError) as exc:
            errors.append(AgentsMdCleanupIssue(path=path, message=str(exc)))
            continue
        if changed:
            removed.append(path)
    return AgentsMdCleanupResult(removed=tuple(removed), errors=tuple(errors))


def _relative_guidance_path(directory: Path, relative: str) -> Path:
    """Join one validated POSIX-style relative candidate to ``directory``."""
    return directory.joinpath(*relative.split("/"))
