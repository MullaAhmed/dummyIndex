"""Stack + formatter detection for equip — deterministic, no LLM.

Two read-only probes:

- :func:`detect_stack` tallies the ``language`` field already present in
  ``.context/map/files.json`` (schema-guaranteed, nullable) and returns the
  dominant label as a :class:`StackProfile`. A missing/unreadable/empty map
  degrades to a ``generic`` profile rather than crashing — equip must still
  produce a usable (if untuned) toolkit on a fresh repo.
- :func:`detect_formatter` reads the repo's manifests at *project root* (not
  the context dir) as raw text and returns the dominant formatter token
  (``ruff`` / ``black`` / ``prettier``) or ``None``. Kept separate from
  ``detect_stack`` because the formatter lives in manifests, not the file map,
  and because the spec freezes ``detect_stack(context_dir)``'s signature.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Optional

from .models import StackProfile

_FILES_MAP_REL = Path("map") / "files.json"

# Frameworks we surface, keyed by the dependency token that names them. Read as
# raw substrings of the lowercased manifest text — no TOML/JSON parser
# dependency (mirrors cli.dev_pick's tolerant harvesting).
_FRAMEWORK_TOKENS: tuple[tuple[str, str], ...] = (
    ("fastapi", "FastAPI"),
    ("django", "Django"),
    ("flask", "Flask"),
    ("react", "React"),
    ("vue", "Vue"),
    ("svelte", "Svelte"),
    ("next", "Next.js"),
    ("express", "Express"),
    ("spring-boot", "Spring Boot"),
    ("springframework", "Spring Boot"),
)

# Formatter token -> canonical name, in precedence order. First present wins.
_FORMATTER_TOKENS: tuple[tuple[str, str], ...] = (
    ("ruff", "ruff"),
    ("black", "black"),
    ("prettier", "prettier"),
)

_MANIFEST_NAMES: tuple[str, ...] = (
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "package.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "Cargo.toml",
    ".pre-commit-config.yaml",
)


def detect_stack(context_dir: Path) -> StackProfile:
    """Resolve the repo's dominant stack from ``<context_dir>/map/files.json``.

    Counts the non-null ``language`` of every file entry; the most common
    language is the label. Ties break alphabetically for determinism. Returns
    a ``generic`` profile when the map is absent, unreadable, or has no
    language-tagged files.
    """
    languages = _read_languages(context_dir / _FILES_MAP_REL)
    if not languages:
        return StackProfile(label="generic", frameworks=())

    counts = Counter(languages)
    # most_common is insertion-ordered on ties; sort by (-count, label) for a
    # stable, deterministic winner across Python builds.
    label = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    frameworks = _detect_frameworks(context_dir.parent)
    return StackProfile(label=label, frameworks=frameworks)


def detect_formatter(project_root: Path) -> Optional[str]:
    """Return the dominant formatter token from repo manifests, or ``None``.

    Reads each known manifest as raw lowercased text and returns the first
    formatter (``ruff`` > ``black`` > ``prettier``) named anywhere in them.
    No parser dependency; tolerant of any manifest shape.
    """
    blob = _manifest_blob(project_root)
    for token, name in _FORMATTER_TOKENS:
        if token in blob:
            return name
    return None


def _read_languages(files_map_path: Path) -> tuple[str, ...]:
    if not files_map_path.is_file():
        return ()
    try:
        data = json.loads(files_map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(data, dict):
        return ()
    entries = data.get("files", [])
    if not isinstance(entries, list):
        return ()
    out: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        lang = entry.get("language")
        if isinstance(lang, str) and lang:
            out.append(lang)
    return tuple(out)


def _detect_frameworks(project_root: Path) -> tuple[str, ...]:
    blob = _manifest_blob(project_root)
    if not blob:
        return ()
    seen: list[str] = []
    for token, label in _FRAMEWORK_TOKENS:
        if token in blob and label not in seen:
            seen.append(label)
    return tuple(seen)


def _manifest_blob(project_root: Path) -> str:
    """Concatenated lowercased text of every manifest that exists at root."""
    parts: list[str] = []
    for name in _MANIFEST_NAMES:
        path = project_root / name
        if not path.is_file():
            continue
        try:
            parts.append(path.read_text(encoding="utf-8", errors="replace").lower())
        except OSError:
            continue
    return "\n".join(parts)
