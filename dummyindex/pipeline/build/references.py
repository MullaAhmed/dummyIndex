"""Textual reference detection — augments the structure graph with cross-file
references that the AST extractor missed.

Walks every effective source file, looks for backticked / quoted mentions of
other files in the project, and emits AMBIGUOUS-confidence `references` edges
when a match is found. Also walks the repo for extra source files (configs,
docs adjacent to code) that should be scannable for references.
"""
from __future__ import annotations
from pathlib import Path
from dummyindex.pipeline.enums import ConfidenceLevel
from .common import _STRUCTURE_IGNORE_FILES, _STRUCTURE_SKIP_DIRS, _rel_path


def _derive_textual_references(
    effective_files: list[Path],
    root_abs: Path,
    file_ids_by_rel: dict[str, str],
    cross_edges: list[dict],
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

    existing_edge_keys = {
        (e["source"], e["target"], e.get("relation", ""))
        for e in cross_edges
    }

    for path in effective_files:
        src_rel = _rel_path(str(path), root_abs)
        src_id = rel_to_id.get(src_rel)
        if not src_id:
            continue
        text = _read_text_safely(path)
        if not text:
            continue
        for tgt_rel, tgt_id in rel_to_id.items():
            if tgt_id == src_id:
                continue
            match_idx = _find_reference(text, tgt_rel, basename_to_rels)
            if match_idx < 0:
                continue
            key = (src_id, tgt_id, "references")
            if key in existing_edge_keys:
                continue
            existing_edge_keys.add(key)
            cross_edges.append({
                "source": src_id,
                "target": tgt_id,
                "relation": "references",
                "confidence": ConfidenceLevel.INFERRED,
                "source_file": src_rel,
                "source_location": f"offset:{match_idx}",
            })


def _find_reference(text: str, tgt_rel: str, basename_to_rels: dict[str, list[str]]) -> int:
    """Return the offset of the earliest textual mention of ``tgt_rel`` in
    ``text``, or -1 if none. Prefers the full relative path; falls back to the
    basename only when it's long and unambiguous.
    """
    idx = text.find(tgt_rel)
    if idx >= 0:
        return idx
    tgt_name = Path(tgt_rel).name
    if len(tgt_name) < 5:
        return -1
    collisions = basename_to_rels.get(tgt_name, [])
    if len(collisions) != 1:
        return -1
    return text.find(tgt_name)


def _read_text_safely(path: Path) -> str:
    """Return file text for scanning, empty string on any error or if too large."""
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    # Skip files above 2MB — mostly vendored bundles we don't care about.
    if size > 2 * 1024 * 1024:
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
    def load(cls, root_abs: Path) -> "_StructureIgnoreMatcher":
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
