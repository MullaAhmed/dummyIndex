# per-file extraction cache - skip unchanged files on re-run
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterator, Optional

from .paths import resolve_under_root

# Trusted in-process cache-dir override. Set by ``cache_dir_override``
# (``context/build/common.py``) — an internal, already-in-repo target that must
# NOT flow through the ambient-env confinement path. ``None`` means "no trusted
# override active"; the ambient ``DUMMYINDEX_CACHE_DIR`` env var (if any) is then
# consulted and confined to the repo root.
_TRUSTED_CACHE_DIR: Path | None = None

# Line-anchored YAML frontmatter closing fence: a bare ``---`` on its own line
# (optional trailing whitespace), not a substring like ``---hack`` mid-line.
_FRONTMATTER_FENCE_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)

# Build-scoped read cache (P2). All three byte reads — the cache-hash read
# (``file_hash``), the extractor read (``generic.py``), and the textual-reference
# read (``references.py``) — funnel through ``read_source_bytes``. When a build
# opens a read cache via :func:`build_read_cache`, every read of the same path
# within that build returns the SAME bytes from a single ``Path.read_bytes`` call,
# so each source file is read at most once per build and all passes see one
# consistent byte-state (no cache-hit stale-node / new-byte mix). Outside a build
# (cache is ``None``) every call reads disk, preserving the prior behaviour.
_BUILD_READ_CACHE: Optional[dict[str, bytes]] = None


@contextlib.contextmanager
def build_read_cache() -> Iterator[None]:
    """Open a build-scoped, path-keyed read cache for the duration of one build.

    Within the ``with`` block, repeated :func:`read_source_bytes` calls for the
    same path are served from memory after the first ``Path.read_bytes``, so the
    hash pass, the extractor pass, and the textual-reference pass share one read.
    Nested entries reuse the outer cache; the cache is cleared on exit so a later
    build (or a mid-build file mutation handled across builds) re-reads disk.
    """
    global _BUILD_READ_CACHE
    if _BUILD_READ_CACHE is not None:
        # Already inside a build read cache — reuse it (no nested reset).
        yield
        return
    _BUILD_READ_CACHE = {}
    try:
        yield
    finally:
        _BUILD_READ_CACHE = None


def read_source_bytes(path: Path) -> bytes:
    """Single named seam for reading a source file's bytes.

    Every byte read of a source file in the build routes through here, giving a
    spy one wrap point and the build one consistent byte-state per path. Inside a
    :func:`build_read_cache` block the first read is memoized by ``str(path)`` and
    subsequent reads of that path return the cached bytes without re-reading disk.
    """
    cache = _BUILD_READ_CACHE
    if cache is None:
        return Path(path).read_bytes()
    key = str(path)
    cached = cache.get(key)
    if cached is None:
        cached = Path(path).read_bytes()
        cache[key] = cached
    return cached


def set_trusted_cache_dir(target: Path | None) -> None:
    """Set (or clear) the trusted in-process cache directory.

    This is the channel ``cache_dir_override`` uses instead of the ambient
    ``DUMMYINDEX_CACHE_DIR`` env var, so an internal in-repo override is never
    subjected to the out-of-repo confinement applied to user-supplied values.
    """
    global _TRUSTED_CACHE_DIR
    _TRUSTED_CACHE_DIR = target


def _body_content(content: bytes) -> bytes:
    """Strip YAML frontmatter from Markdown content, returning only the body.

    The closing fence is matched with a **line-anchored** regex (``^---\\s*$``),
    not a loose ``find("\\n---")`` substring — the latter truncated the body at
    the first in-body line *starting* with ``---`` even when it was a non-bare
    token like ``---hack``. When there is no bare closing fence the whole file is
    hashed (frontmatter-without-close is not a regression).
    """
    text = content.decode(errors="replace")
    if text.startswith("---"):
        # Search for the closing fence strictly after the opening one.
        match = _FRONTMATTER_FENCE_RE.search(text, 3)
        if match is not None:
            return text[match.end():].encode()
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
    raw = read_source_bytes(p)
    content = _body_content(raw) if p.suffix.lower() == ".md" else raw
    return hashlib.sha256(content).hexdigest()


def cache_dir(root: Path = Path(".")) -> Path:
    """Returns the per-file extraction cache directory; creates it if needed.

    Default: ``<root>/.context/cache/``.

    Two override channels with different trust levels:

    1. **Trusted in-process override** — set by ``cache_dir_override``
       (``context/build/common.py``) via :func:`set_trusted_cache_dir`. The
       context engine uses this to pin the cache to its own in-repo
       ``.context/cache/`` target. It is honored unconditionally (no
       confinement) because it never carries untrusted input.
    2. **Ambient ``DUMMYINDEX_CACHE_DIR`` env var** — the documented
       user-facing opt-out ("put the cache anywhere", ``CHANGELOG.md:1095``).

    **Opt-out policy (recorded):** the ``DUMMYINDEX_CACHE_DIR`` opt-out is
    **preserved, not deprecated** — but it is now *confined to the repo root*.
    An ambient value resolving to ``root`` or a descendant is honored; one that
    escapes (out-of-repo, ``../``, absolute join) is **silently ignored** and
    the cache falls back to ``<root>/.context/cache/``. This never raises
    (``test_cache_env_var_is_restored``). Distinguishing the trusted override
    (channel 1) from the ambient value (channel 2) is what keeps the internal
    override working while still confining user-supplied paths.
    """
    if _TRUSTED_CACHE_DIR is not None:
        d = _TRUSTED_CACHE_DIR.resolve()
    else:
        resolved_root = Path(root).resolve()
        ambient = os.environ.get("DUMMYINDEX_CACHE_DIR")
        confined = (
            resolve_under_root(Path(ambient), resolved_root) if ambient else None
        )
        d = confined if confined is not None else resolved_root / ".context" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_valid_cache_payload(payload: object) -> bool:
    """Accept-superset schema guard for a cached extraction entry.

    Anti-corruption (not anti-poisoning): a well-formed but adversarial graph
    still passes — the real containment is the cache-dir confinement above.
    Returns ``True`` iff ``payload`` is a dict whose ``nodes`` and ``edges`` are
    both lists and every **node** carries a string ``id`` (edges use
    ``source``/``target``, never ``id`` — they are not checked for ``id``).
    Unknown keys are ignored, so existing well-formed entries still hit.
    """
    if not isinstance(payload, dict):
        return False
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return False
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            return False
    return True


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
        payload = json.loads(entry.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    # Accept-superset schema guard: a corrupt/foreign-shaped entry is a MISS
    # (re-extract, never merge), but a well-formed entry still hits.
    if not _is_valid_cache_payload(payload):
        return None
    return payload


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
        tmp.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
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
