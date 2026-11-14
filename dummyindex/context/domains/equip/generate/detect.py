"""Stack + toolchain detection for equip — deterministic, no LLM.

:func:`detect_stack` returns the dominant ``language`` in ``.context/map/files.json``
as a :class:`StackProfile`; a missing/unreadable/empty map degrades to ``generic``.
The toolchain (formatter, test/lint/typecheck runners + commands) comes from a raw
manifest token scan at project root: Python commands get ``uv run`` with ``uv.lock``
or ``[tool.uv]``, node commands ``npx``. Nothing detected ⇒ all toolchain ``None``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ..models import StackProfile

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

# Each toolchain table maps a manifest token to (canonical-name, ecosystem,
# command-template). ``{prefix}`` is filled with the ecosystem's runner prefix
# (``uv run `` for python when uv is present, ``npx `` for node, else ``""``).
# First present token wins. Formatting names changed paths at execution time.
_PY = "python"
_NODE = "node"

# (token, name, ecosystem, command_template)
_TEST_TOKENS: tuple[tuple[str, str, str, str], ...] = (
    ("pytest", "pytest", _PY, "{prefix}pytest -q"),
    ("vitest", "vitest", _NODE, "{prefix}vitest run"),
    ("jest", "jest", _NODE, "{prefix}jest"),
)
_LINT_TOKENS: tuple[tuple[str, str, str, str], ...] = (
    ("ruff", "ruff", _PY, "{prefix}ruff check ."),
    ("eslint", "eslint", _NODE, "{prefix}eslint ."),
)
_TYPECHECK_TOKENS: tuple[tuple[str, str, str, str], ...] = (
    ("mypy", "mypy", _PY, "{prefix}mypy ."),
    ("pyright", "pyright", _PY, "{prefix}pyright"),
)
_FORMAT_TOKENS: tuple[tuple[str, str, str, str], ...] = (
    ("ruff", "ruff", _PY, "{prefix}ruff format <changed-paths>"),
    ("black", "black", _PY, "{prefix}black <changed-paths>"),
    ("prettier", "prettier", _NODE, "{prefix}prettier --write <changed-paths>"),
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

# Evidence tokens match whole words in the same manifests as the framework scan.
# README and other prose are never read, so a sentence cannot forge evidence.
_DATA_STORE_TOKENS: tuple[str, ...] = (
    "sqlalchemy",
    "alembic",
    "psycopg",
    "psycopg2",
    "asyncpg",
    "pymongo",
    "motor",
    "prisma",
    "drizzle-orm",
    "typeorm",
    "sequelize",
    "knex",
    "mongoose",
    "django",
    "supabase",
    "peewee",
    "tortoise-orm",
    "sqlite3",
    "mysql",
    "mysqlclient",
    "pgx",
    "gorm",
    "sqlx",
    "sqlc",
    "diesel",
    "activerecord",
    "dapper",
    "hibernate",
    "jdbc",
)
_SEARCH_TOKENS: tuple[str, ...] = (
    "elasticsearch",
    "opensearch",
    "meilisearch",
    "typesense",
    "algoliasearch",
    "whoosh",
    "tantivy",
    "pgvector",
    "faiss",
    "faiss-cpu",
    "qdrant-client",
    "chromadb",
    "weaviate-client",
    "pinecone",
    "rank_bm25",
    "lunr",
)
# File evidence runs over ``map/files.json`` paths normalised to ``/``, lowercased.
_DB_FILE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sql", re.compile(r"\.sql$")),
    ("alembic", re.compile(r"(^|/)alembic\.ini$")),
    ("prisma", re.compile(r"(^|/)prisma/schema\.prisma$")),
    ("migrations", re.compile(r"(^|/)migrations/")),
)


def detect_stack(context_dir: Path) -> StackProfile:
    """Resolve the repo's dominant stack from ``<context_dir>/map/files.json``.

    Counts the non-null ``language`` of every file entry; the most common
    language is the label. Ties break alphabetically for determinism. Returns
    a ``generic`` profile when the map is absent, unreadable, or has no
    language-tagged files. Data-store and search evidence is independent of
    the label and is filled in either way.
    """
    project_root = context_dir.parent
    entries = _read_map_entries(context_dir / _FILES_MAP_REL)
    languages = tuple(
        lang for lang in (_entry_str(e, "language") for e in entries) if lang
    )
    toolchain = _detect_toolchain(project_root)
    data_stores, search_backends = _detect_evidence(
        project_root, tuple(_entry_str(e, "path") or "" for e in entries)
    )
    if not languages:
        return StackProfile(
            label="generic",
            frameworks=(),
            data_stores=data_stores,
            search_backends=search_backends,
            **toolchain,
        )

    counts = Counter(languages)
    # most_common is insertion-ordered on ties; sort by (-count, label) for a
    # stable, deterministic winner across Python builds.
    label = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    frameworks = _detect_frameworks(project_root)
    return StackProfile(
        label=label,
        frameworks=frameworks,
        data_stores=data_stores,
        search_backends=search_backends,
        **toolchain,
    )


def _detect_toolchain(project_root: Path) -> dict[str, str | None]:
    """Resolve the eight toolchain fields from the repo's manifests.

    Returns a kwargs dict for :class:`StackProfile` (``formatter`` …
    ``typecheck_command``). Every value is ``None`` when no manifest names the
    corresponding tool. Python commands gain a ``uv run`` prefix when uv is in
    use; node commands a ``npx`` prefix.
    """
    blob = _manifest_blob(project_root)
    uv = _uses_uv(project_root, blob)
    # Shared capability commands run in the project environment. Native hook
    # plumbing adapts its formatter command separately.
    run_prefixes = {_PY: "uv run " if uv else "", _NODE: "npx "}
    test_runner, test_command = _first_token(_TEST_TOKENS, blob, run_prefixes)
    linter, lint_command = _first_token(_LINT_TOKENS, blob, run_prefixes)
    type_checker, typecheck_command = _first_token(
        _TYPECHECK_TOKENS, blob, run_prefixes
    )
    formatter, format_command = _first_token(_FORMAT_TOKENS, blob, run_prefixes)
    return {
        "formatter": formatter,
        "format_command": format_command,
        "test_runner": test_runner,
        "test_command": test_command,
        "linter": linter,
        "lint_command": lint_command,
        "type_checker": type_checker,
        "typecheck_command": typecheck_command,
    }


def _first_token(
    table: tuple[tuple[str, str, str, str], ...],
    blob: str,
    prefixes: dict[str, str],
) -> tuple[str | None, str | None]:
    """First (name, command) whose token is present in ``blob``, else (None, None)."""
    for token, name, ecosystem, template in table:
        if token in blob:
            return name, template.format(prefix=prefixes[ecosystem])
    return None, None


def _uses_uv(project_root: Path, blob: str) -> bool:
    """True when the repo runs python via uv (``uv.lock`` present or ``[tool.uv]``).

    Substring-safe: checks the lock file's existence and the exact
    ``[tool.uv]`` table header — never the bare ``uv`` substring (which would
    false-match ``uvicorn``).
    """
    if (project_root / "uv.lock").is_file():
        return True
    return "[tool.uv]" in blob


def _read_map_entries(files_map_path: Path) -> list[dict[str, Any]]:
    if not files_map_path.is_file():
        return []
    try:
        data = json.loads(files_map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("files", [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _entry_str(entry: dict[str, Any], key: str) -> str | None:
    value = entry.get(key)
    return value if isinstance(value, str) and value else None


def _detect_evidence(
    project_root: Path, map_paths: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Data-store and search-backend evidence as ``(data_stores, search_backends)``.

    Data stores combine manifest tokens with file patterns over the map paths;
    search backends come from manifest tokens only.
    """
    blob = _manifest_blob(project_root)
    normalised = tuple(p.replace("\\", "/").lower() for p in map_paths)
    stores = [t for t in _DATA_STORE_TOKENS if _has_token(blob, t)]
    stores += [
        label
        for label, pattern in _DB_FILE_PATTERNS
        if any(pattern.search(p) for p in normalised)
    ]
    search = tuple(t for t in _SEARCH_TOKENS if _has_token(blob, t))
    return tuple(dict.fromkeys(stores)), search


def _has_token(blob: str, token: str) -> bool:
    return re.search(rf"\b{re.escape(token)}\b", blob) is not None


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
