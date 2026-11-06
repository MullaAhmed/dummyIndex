"""Keep the mined report inside one repo, and keep host paths out of it.

Two separate hazards, both found by an audit of the first cut of this miner,
both of which land in a **git-tracked** file (`.context/session-memory/`):

1. **Cross-project bleed.** A transcript store holds every project the host
   has ever opened. Scanning all of it and writing the result into one repo
   publishes other repos' file paths — and, through them, the existence and
   layout of unrelated private work — into this repo's history. headroom
   avoids this by decoding each project directory back to its real path
   (`learn/plugins/claude.py`) and staying per-project; the first cut of this
   port dropped that step and pooled everything. :func:`project_dir_name`
   restores it.
2. **Absolute host paths.** `.context/conventions/data-access.md` is explicit:
   paths in committed artifacts are POSIX and repo-relative. A signature is
   built from a tool call's own input, so it carries whatever path the caller
   typed — usually absolute. :func:`sanitize_signature` rewrites the ones
   inside the repo and redacts the ones outside it, so a path that cannot be
   made repo-relative never reaches the file rather than being emitted raw.

Neither guard is best-effort: a leak here is not a wrong number in a report,
it is private data committed to a shared repo.
"""

from __future__ import annotations

import ntpath
import posixpath
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

# Claude Code names a project's transcript directory after its filesystem
# path with every separator replaced by a dash, so `/a/b/c` becomes `-a-b-c`.
_PATH_SEP_RE = re.compile(r"[/\\]")

# An absolute POSIX path (`/usr/...`) or a Windows drive path (`C:\...`),
# as it would appear inside a serialized tool input or a shell command.
_ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\|/)[^\s\"'`,;)]{1,}")

REDACTED = "<redacted-absolute-path>"


def project_dir_name(repo_root: Path) -> str:
    """The transcript-store directory name Claude Code uses for `repo_root`.

    Exact, not a prefix: sibling repos routinely share a prefix
    (`-a-b-mono` and `-a-b-mono-backend` are different projects), so a
    prefix match would re-introduce exactly the cross-project bleed this
    module exists to prevent.
    """
    root = repo_root.resolve()
    path = str(root)
    if root.drive:
        path = path.replace(":", "-", 1)
    return _PATH_SEP_RE.sub("-", path)


def sanitize_signature(signature: str, *, repo_root: Path) -> str:
    """Rewrite in-repo absolute paths as repo-relative; redact the rest.

    Redaction rather than pass-through is the point: a path outside the repo
    is precisely the thing that must not be written down, so an unmatched
    absolute path is replaced, never emitted. The signature stays stable and
    deterministic — the same input always yields the same output.
    """
    # Captured paths may come from another OS; do not resolve them on this host.
    root_text = repo_root.as_posix()
    if (
        not PureWindowsPath(root_text).drive
        and not PurePosixPath(root_text).is_absolute()
    ):
        root_text = repo_root.resolve().as_posix()
    windows = bool(PureWindowsPath(root_text).drive)
    path_type = PureWindowsPath if windows else PurePosixPath
    normalize = ntpath.normpath if windows else posixpath.normpath
    root = path_type(normalize(root_text))

    def replace(match: re.Match[str]) -> str:
        found = match.group(0)
        if found.startswith("\\\\\\\\"):
            found = found.replace("\\\\", "\\")  # JSON-escaped UNC path.
        path = path_type(normalize(found))
        if not path.is_absolute():
            return REDACTED
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return REDACTED

    return _ABSOLUTE_PATH_RE.sub(replace, signature)
