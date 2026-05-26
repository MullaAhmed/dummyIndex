# per-file extraction cache - skip unchanged files on re-run
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def _body_content(content: bytes) -> bytes:
    """Strip YAML frontmatter from Markdown content, returning only the body."""
    text = content.decode(errors="replace")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].encode()
    return content


def file_hash(path: Path, root: Path = Path(".")) -> str:
    """SHA256 of file contents only — content-addressable, path-independent.

    The cache key intentionally excludes any path component so that:
    - Re-runs from a different cwd hit the same cache entries.
    - Subagents that emit ``source_file`` as either absolute or relative paths
      both find the same cache entry on the next run.
    - Cache survives ``mv`` / repository moves without manual rebuild.

    For Markdown files (.md), only the body below the YAML frontmatter is hashed,
    so metadata-only changes (e.g. reviewed, status, tags) do not invalidate the cache.

    The ``root`` parameter is retained for API compatibility but no longer
    affects the hash. It is kept so downstream callers don't need to change.
    """
    p = Path(path)
    if not p.is_file():
        raise IsADirectoryError(f"file_hash requires a file, got: {p}")
    raw = p.read_bytes()
    content = _body_content(raw) if p.suffix.lower() == ".md" else raw
    return hashlib.sha256(content).hexdigest()


def cache_dir(root: Path = Path(".")) -> Path:
    """Returns the per-file extraction cache directory; creates it if needed.

    Default: ``<root>/.context/cache/``.
    Override: set ``DUMMYINDEX_CACHE_DIR`` to an absolute path to put the
    cache anywhere. The context engine sets this env var so its outputs
    stay contained when callers pass a different cache root.
    """
    override = os.environ.get("DUMMYINDEX_CACHE_DIR")
    if override:
        d = Path(override).resolve()
    else:
        d = Path(root).resolve() / ".context" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_cached(path: Path, root: Path = Path(".")) -> dict | None:
    """Return cached extraction for this file if hash matches, else None.

    Cache key: SHA256 of file contents.
    Cache value: stored as .context/cache/{hash}.json
    Returns None if no cache entry or file has changed.
    """
    try:
        h = file_hash(path, root)
    except OSError:
        return None
    entry = cache_dir(root) / f"{h}.json"
    if not entry.exists():
        return None
    try:
        return json.loads(entry.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_cached(path: Path, result: dict, root: Path = Path(".")) -> None:
    """Save extraction result for this file.

    Stores as .context/cache/{hash}.json where hash = SHA256 of current file contents.
    result should be a dict with 'nodes' and 'edges' lists.

    No-ops if `path` is not a regular file. Subagent-produced semantic fragments
    occasionally carry a directory path in `source_file`; skipping them prevents
    IsADirectoryError from aborting the whole batch.
    """
    p = Path(path)
    if not p.is_file():
        return
    h = file_hash(p, root)
    entry = cache_dir(root) / f"{h}.json"
    tmp = entry.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(result), encoding="utf-8")
        try:
            os.replace(tmp, entry)
        except PermissionError:
            # Windows: os.replace can fail with WinError 5 if the target is
            # briefly locked. Fall back to copy-then-delete.
            import shutil
            shutil.copy2(tmp, entry)
            tmp.unlink(missing_ok=True)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
