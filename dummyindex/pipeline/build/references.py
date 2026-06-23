"""Textual reference detection — augments the structure graph with cross-file
references that the AST extractor missed.

Walks every effective source file, looks for backticked / quoted mentions of
other files in the project, and emits AMBIGUOUS-confidence `references` edges
when a match is found. Also walks the repo for extra source files (configs,
docs adjacent to code) that should be scannable for references.
"""

from __future__ import annotations

import re
from pathlib import Path

from dummyindex.pipeline.enums import ConfidenceLevel

from .common import _STRUCTURE_IGNORE_FILES, _STRUCTURE_SKIP_DIRS, _rel_path


def _derive_textual_references(
    effective_files: list[Path],
    root_abs: Path,
    file_ids_by_rel: dict[str, str],
    cross_edges: list[dict],
    *,
    file_bytes: dict[str, bytes] | None = None,
) -> None:
    """Scan every source file for textual mentions of other source files.

    Emits a generic ``references`` cross-edge for every match, tagged
    ``INFERRED``. The match offset is recorded in ``source_location`` as
    ``offset:<n>`` so a downstream LLM enrichment pass can pull the
    surrounding context and replace the relation with something semantically
    meaningful (``renders_template``, ``loads_config``, ``packages_file``,
    etc.). This module stays language-agnostic — no hand-coded rules about
    what specific frameworks or file types mean.

    To limit false positives on short or common names, basenames shorter than
    5 characters are only accepted when the full relative path appears
    verbatim; colliding basenames are also rejected so only the full-path
    form counts.

    ``file_bytes`` (P2) maps ``str(path)`` to the bytes the extraction already
    read for that file. When a scanned file is present in the map its text is
    decoded from those cached bytes instead of being re-read from disk, so each
    source file is read at most twice across the whole build and every pass sees
    one consistent byte-state. Files absent from the map (e.g. discovered extras
    the extractor never parsed) fall back to a fresh disk read.
    """
    if not effective_files:
        return

    rel_to_id: dict[str, str] = {}
    basename_to_rels: dict[str, list[str]] = {}
    for path in effective_files:
        rel = _rel_path(str(path), root_abs)
        file_id = file_ids_by_rel.get(rel)
        if not rel or not file_id:
            continue
        rel_to_id[rel] = file_id
        basename_to_rels.setdefault(Path(rel).name, []).append(rel)

    # Per target, decide once which basename (if any) is an eligible fallback:
    # long (>= 5 chars) and unambiguous (exactly one rel carries it). This
    # mirrors the precedence rules in the old ``_find_reference`` so the
    # combined single-pass matcher below stays byte-faithful.
    fallback_name: dict[str, str | None] = {}
    for tgt_rel in rel_to_id:
        tgt_name = Path(tgt_rel).name
        if len(tgt_name) >= 5 and len(basename_to_rels.get(tgt_name, [])) == 1:
            fallback_name[tgt_rel] = tgt_name
        else:
            fallback_name[tgt_rel] = None

    # One combined matcher over the whole project alphabet: every full rel-path
    # plus every eligible fallback basename. Scanning each file's text once with
    # this matcher does a single regex pass instead of F separate `str.find`
    # calls per file — a real constant-factor win (one engine pass vs. F calls
    # with per-call interpreter overhead), though not an asymptotic one.
    matcher = _build_matcher(rel_to_id, fallback_name)

    existing_edge_keys = {
        (e["source"], e["target"], e.get("relation", "")) for e in cross_edges
    }

    for path in effective_files:
        src_rel = _rel_path(str(path), root_abs)
        src_id = rel_to_id.get(src_rel)
        if not src_id:
            continue
        text = _text_for_scan(path, file_bytes)
        if not text:
            continue
        # Single pass: earliest offset for every needle that occurs in ``text``.
        earliest = _earliest_offsets(matcher, text)
        if not earliest:
            continue
        for tgt_rel, tgt_id in rel_to_id.items():
            if tgt_id == src_id:
                continue
            match_idx = _reference_offset(tgt_rel, fallback_name[tgt_rel], earliest)
            if match_idx < 0:
                continue
            key = (src_id, tgt_id, "references")
            if key in existing_edge_keys:
                continue
            existing_edge_keys.add(key)
            cross_edges.append(
                {
                    "source": src_id,
                    "target": tgt_id,
                    "relation": "references",
                    "confidence": ConfidenceLevel.INFERRED,
                    "source_file": src_rel,
                    "source_location": f"offset:{match_idx}",
                }
            )


def _build_matcher(
    rel_to_id: dict[str, str], fallback_name: dict[str, str | None]
) -> re.Pattern[str] | None:
    """Compile one regex matching any project needle anywhere it appears.

    The needle alphabet is every full rel-path plus every eligible fallback
    basename. Each alternative is a zero-width lookahead so overlapping and
    adjacent occurrences are all reported independently — exactly what the old
    per-needle ``str.find`` did. Returns ``None`` when there is nothing to scan.
    """
    needles: set[str] = set(rel_to_id)
    needles.update(name for name in fallback_name.values() if name)
    if not needles:
        return None
    # Longest-first only affects readability of the alternation; the lookahead
    # capture makes order irrelevant to which offsets are recorded.
    alternation = "|".join(re.escape(n) for n in sorted(needles, key=len, reverse=True))
    return re.compile(f"(?=({alternation}))")


def _earliest_offsets(matcher: re.Pattern[str] | None, text: str) -> dict[str, int]:
    """Earliest start offset of every needle that occurs in ``text``.

    Mirrors ``text.find(needle)`` for each needle, but resolves all of them in a
    single left-to-right scan. The zero-width lookahead reports a match at every
    position where any needle starts, so the first time a needle is seen is its
    earliest offset.
    """
    if matcher is None:
        return {}
    out: dict[str, int] = {}
    for m in matcher.finditer(text):
        needle = m.group(1)
        if needle not in out:
            out[needle] = m.start()
    return out


def _reference_offset(
    tgt_rel: str, fallback: str | None, earliest: dict[str, int]
) -> int:
    """Offset of the earliest mention of ``tgt_rel``, or -1 if none.

    Prefers the full relative path; falls back to the precomputed eligible
    basename. Byte-faithful replacement for the old ``_find_reference``.
    """
    full = earliest.get(tgt_rel, -1)
    if full >= 0:
        return full
    if fallback is None:
        return -1
    return earliest.get(fallback, -1)


_MAX_SCAN_BYTES = 2 * 1024 * 1024  # skip files above 2MB — mostly vendored bundles


def _text_for_scan(path: Path, file_bytes: dict[str, bytes] | None) -> str:
    """Decode the text to scan, reusing extraction-read bytes when available.

    When ``file_bytes`` carries this path's bytes (P2: read once during
    extraction), decode those — byte-faithful to ``_read_text_safely`` (utf-8,
    ``errors="ignore"``, >2MB skipped) — so no second disk read happens.
    Otherwise read from disk via :func:`_read_text_safely`.
    """
    if file_bytes is not None:
        cached = file_bytes.get(str(path))
        if cached is not None:
            if len(cached) > _MAX_SCAN_BYTES:
                return ""
            return cached.decode("utf-8", errors="ignore")
    return _read_text_safely(path)


def _read_text_safely(path: Path) -> str:
    """Return file text for scanning, empty string on any error or if too large."""
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    # Skip files above 2MB — mostly vendored bundles we don't care about.
    if size > _MAX_SCAN_BYTES:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return ""


def _discover_extra_source_files(root_abs: Path, code_files: list[Path]) -> list[Path]:
    """Walk ``root_abs`` and return every file not already in ``code_files``.

    Files and directories are excluded when they:
      * match a pattern in ``.codeindexignore`` (preferred) or ``.dummyindexignore``
      * are under a built-in junk directory (``_STRUCTURE_SKIP_DIRS``)
      * match a built-in ignore file itself (the ignore file doesn't index itself)

    No extension whitelist is applied — the tree reflects every real file in the
    source folder so downstream views are complete.
    """
    if not root_abs.exists() or not root_abs.is_dir():
        return []

    existing: set[str] = set()
    for path in code_files:
        rel = _rel_path(str(path), root_abs)
        if rel:
            existing.add(rel)

    ignore_matcher = _StructureIgnoreMatcher.load(root_abs)

    found: list[Path] = []
    stack: list[Path] = [root_abs]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            name = entry.name
            rel = _rel_path(str(entry), root_abs)
            if not rel:
                continue
            if entry.is_dir():
                if name in _STRUCTURE_SKIP_DIRS:
                    continue
                if ignore_matcher.matches(rel, is_dir=True):
                    continue
                stack.append(entry)
                continue
            if not entry.is_file():
                continue
            if name in _STRUCTURE_IGNORE_FILES:
                continue
            if ignore_matcher.matches(rel, is_dir=False):
                continue
            if rel in existing:
                continue
            existing.add(rel)
            found.append(entry)
    return found


class _StructureIgnoreMatcher:
    """Minimal gitignore-style matcher for the structure graph.

    Loads patterns from the first existing ``.codeindexignore`` or
    ``.dummyindexignore`` file at ``root``. Supports the common 95% of gitignore
    syntax: ``#`` comments, ``!`` negation, trailing ``/`` for directory-only,
    leading ``/`` for root-anchored, and ``*``/``?`` glob characters.
    """

    def __init__(self, rules: list[tuple[bool, str, bool, bool]]):
        # each rule: (negate, pattern, anchored, dir_only)
        self._rules = rules

    @classmethod
    def load(cls, root_abs: Path) -> _StructureIgnoreMatcher:
        for name in _STRUCTURE_IGNORE_FILES:
            path = root_abs / name
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                return cls(cls._parse(content))
        return cls([])

    @staticmethod
    def _parse(content: str) -> list[tuple[bool, str, bool, bool]]:
        rules: list[tuple[bool, str, bool, bool]] = []
        for raw in content.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negate = False
            if line.startswith("!"):
                negate = True
                line = line[1:].strip()
                if not line:
                    continue
            dir_only = False
            if line.endswith("/"):
                dir_only = True
                line = line.rstrip("/")
            anchored = False
            if line.startswith("/"):
                anchored = True
                line = line.lstrip("/")
            rules.append((negate, line, anchored, dir_only))
        return rules

    def matches(self, rel_path: str, is_dir: bool) -> bool:
        ignored = False
        for negate, pattern, anchored, dir_only in self._rules:
            if dir_only and not is_dir:
                continue
            if self._pattern_hits(pattern, rel_path, anchored):
                ignored = not negate
        return ignored

    @staticmethod
    def _pattern_hits(pattern: str, rel_path: str, anchored: bool) -> bool:
        import fnmatch

        # Normalize path separators for matching
        rel = rel_path
        if anchored:
            if fnmatch.fnmatch(rel, pattern):
                return True
            return fnmatch.fnmatch(rel, pattern + "/*")
        # If pattern has no slash, match the basename or any path segment
        if "/" not in pattern:
            if fnmatch.fnmatch(Path(rel).name, pattern):
                return True
            for part in rel.split("/"):
                if fnmatch.fnmatch(part, pattern):
                    return True
            return False
        # Pattern has slashes — match full rel path or any suffix / prefix
        if fnmatch.fnmatch(rel, pattern):
            return True
        if fnmatch.fnmatch(rel, pattern + "/*"):
            return True
        # Match at any depth via **
        if "**" in pattern:
            # crude: convert ** into * and re-check across segments
            flat = pattern.replace("**/", "").replace("/**", "")
            if fnmatch.fnmatch(rel, flat):
                return True
        return False
