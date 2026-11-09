# per-file extraction cache - skip unchanged files on re-run
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import stat
import time
from collections.abc import Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile

from .paths import resolve_under_root

# Trusted in-process cache-dir override, set via ``cache_dir_override``
# (``context/build/common.py``); it must NOT go through the ambient-env
# confinement. ``None`` means the ambient ``DUMMYINDEX_CACHE_DIR`` (confined to
# the repo root) is consulted instead.
_TRUSTED_CACHE_DIR: Path | None = None

# Line-anchored YAML frontmatter closing fence: a bare ``---`` on its own line
# (optional trailing whitespace), not a substring like ``---hack`` mid-line.
_FRONTMATTER_FENCE_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)

# Name of a content-hash extraction entry (``save_cached``): ``<sha256>.json``.
# Matched with ``fullmatch`` so a name with a trailing newline never qualifies.
_ENTRY_NAME_RE = re.compile(r"[0-9a-f]{64}\.json")

# Stamp recording the package version that wrote the content-hash entries.
_VERSION_STAMP_NAME = "extraction-version"

# Build-scoped read cache. Inside :func:`build_read_cache` every
# ``read_source_bytes`` call for a path returns the bytes of one ``Path.read_bytes``,
# so all passes see one consistent byte-state (no cache-hit stale-node / new-byte
# mix). ``None`` (outside a build) means every call reads disk.
_BUILD_READ_CACHE: dict[str, bytes] | None = None


@contextlib.contextmanager
def build_read_cache() -> Iterator[None]:
    """Open a build-scoped, path-keyed read cache for the duration of one build.

    Repeated :func:`read_source_bytes` calls for a path inside the block are
    served from memory after the first read. Nested entries reuse the outer
    cache; it is cleared on exit so a later build re-reads disk.
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

    The closing fence must be a bare ``---`` line (line-anchored regex), so an
    in-body line like ``---hack`` doesn't truncate the body. Without a bare
    closing fence the whole file is returned.
    """
    text = content.decode(errors="replace")
    if text.startswith("---"):
        # Search for the closing fence strictly after the opening one.
        match = _FRONTMATTER_FENCE_RE.search(text, 3)
        if match is not None:
            return text[match.end() :].encode()
    return content


def file_hash(path: Path, root: Path = Path(".")) -> str:
    """SHA256 of file contents only — content-addressable, path-independent.

    No path component, so another cwd, absolute vs relative ``source_file``
    paths, and repo moves all hit the same entries. For ``.md`` files only the
    body below YAML frontmatter is hashed, so metadata-only edits don't
    invalidate. ``root`` no longer affects the hash (kept for API compatibility).
    Raises ``IsADirectoryError`` if ``path`` is not a file.
    """
    p = Path(path)
    if not p.is_file():
        raise IsADirectoryError(f"file_hash requires a file, got: {p}")
    raw = read_source_bytes(p)
    content = _body_content(raw) if p.suffix.lower() == ".md" else raw
    return hashlib.sha256(content).hexdigest()


def cache_dir(root: Path = Path(".")) -> Path:
    """Return the per-file extraction cache directory, creating it if needed.

    Default ``<root>/.context/cache/``. The trusted in-process override
    (:func:`set_trusted_cache_dir`, via ``cache_dir_override``) is honored
    unconditionally; it never carries untrusted input. The user-facing
    ``DUMMYINDEX_CACHE_DIR`` opt-out is honored only if it resolves inside ``root``;
    a value that escapes it is silently ignored and the default used.
    """
    if _TRUSTED_CACHE_DIR is not None:
        d = _TRUSTED_CACHE_DIR.resolve()
    else:
        resolved_root = Path(root).resolve()
        ambient = os.environ.get("DUMMYINDEX_CACHE_DIR")
        confined = resolve_under_root(Path(ambient), resolved_root) if ambient else None
        d = confined if confined is not None else resolved_root / ".context" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """Replace ``path`` from a unique temporary sibling; never creates parents.

    Same shape as ``context/domains/atomic_io._replace_bytes`` (which
    ``pipeline`` cannot import — layering is one-way ``context → pipeline``).
    The tmp name is unique so two concurrent writers never share a tmp file.
    """
    tmp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_path = Path(handle.name)
            handle.write(data)
        for attempt in range(6):
            try:
                os.replace(tmp_path, path)
                break
            except PermissionError:
                # Windows readers can briefly deny replacement while their
                # handle is open. Retain the complete temporary until retry.
                if os.name != "nt" or attempt == 5:
                    raise
                time.sleep(0.01 * (attempt + 1))
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _read_version_stamp(stamp: Path) -> str | None:
    """Return the stripped stamp text, or ``None`` when absent or unreadable."""
    try:
        return stamp.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None


def _is_plain_file(path: Path) -> bool:
    """``True`` for a regular, non-linked file (lstat; links never followed)."""
    info = os.lstat(path)
    linked = stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )
    return stat.S_ISREG(info.st_mode) and not linked


def scope_cache_to_version(cache_dir: Path, version: str) -> int:
    """Drop content-hash entries written by a different package version; return count.

    No-op when the ``extraction-version`` stamp equals ``version`` or ``cache_dir`` is
    missing (never created). Otherwise deletes only direct ``^[0-9a-f]{64}\\.json$``
    children that are regular, non-linked files (all else, e.g. ``manifest.json``
    and locks, is left alone), then rewrites the stamp atomically. OSErrors are
    contained; a failed deletion withholds the stamp so the next run retries.
    """
    cache_dir = Path(cache_dir)
    version = version.strip()
    if not cache_dir.is_dir():
        return 0
    stamp = cache_dir / _VERSION_STAMP_NAME
    if _read_version_stamp(stamp) == version:
        return 0

    deleted = 0
    failed = False
    try:
        with os.scandir(cache_dir) as entries:
            for entry in entries:
                if not _ENTRY_NAME_RE.fullmatch(entry.name):
                    continue
                path = Path(entry.path)
                try:
                    if not _is_plain_file(path):
                        continue
                    os.unlink(path)
                except FileNotFoundError:
                    continue  # removed concurrently — already gone
                except OSError:
                    failed = True
                    continue
                deleted += 1
    except OSError:
        # The directory itself could not be listed: nothing was proven clean.
        return deleted

    if not failed:
        with contextlib.suppress(OSError):
            _write_bytes_atomic(stamp, f"{version}\n".encode())
    return deleted


def _is_valid_cache_payload(payload: object) -> bool:
    """Accept-superset schema guard for a cached extraction entry.

    Anti-corruption, not anti-poisoning: a well-formed adversarial graph still
    passes; the real containment is the cache-dir confinement. ``True`` iff
    ``payload`` is a dict whose ``nodes`` and ``edges`` are lists and every node
    has a string ``id`` (edges aren't checked). Unknown keys are ignored.
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
    """Save extraction result for this file as ``<cache_dir>/{sha256}.json``.

    ``result`` should be a dict with 'nodes' and 'edges' lists. No-ops if
    ``path`` is not a regular file: semantic fragments sometimes carry a
    directory in ``source_file``, and raising would abort the whole batch.
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
