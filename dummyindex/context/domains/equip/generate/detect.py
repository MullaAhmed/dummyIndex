"""Stack + toolchain detection for equip — deterministic, no LLM.

:func:`detect_stack` tallies the ``language`` field already present in
``.context/map/files.json`` (schema-guaranteed, nullable) and returns the
dominant label as a :class:`StackProfile`. A missing/unreadable/empty map
degrades to a ``generic`` profile rather than crashing — equip must still
produce a usable (if untuned) toolkit on a fresh repo.

It additionally derives the full toolchain (formatter + test/lint/typecheck
runners + their shell commands) from a raw-manifest token scan at *project
root*. Python commands are prefixed with ``uv run`` when ``uv.lock`` is present
(or ``[tool.uv]`` appears in a manifest); node commands are prefixed with
``npx``. Nothing detected ⇒ all toolchain fields ``None``.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

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
# First present token wins. ``$CLAUDE_FILE_PATHS`` is Claude Code's hook var —
# only the format command (which runs per-edit) uses it.
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
    ("ruff", "ruff", _PY, '{prefix}ruff format "$CLAUDE_FILE_PATHS"'),
    ("black", "black", _PY, '{prefix}black "$CLAUDE_FILE_PATHS"'),
    ("prettier", "prettier", _NODE, '{prefix}prettier --write "$CLAUDE_FILE_PATHS"'),
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
    project_root = context_dir.parent
    languages = _read_languages(context_dir / _FILES_MAP_REL)
    toolchain = _detect_toolchain(project_root)
    if not languages:
        return StackProfile(label="generic", frameworks=(), **toolchain)

    counts = Counter(languages)
    # most_common is insertion-ordered on ties; sort by (-count, label) for a
    # stable, deterministic winner across Python builds.
    label = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    frameworks = _detect_frameworks(project_root)
    return StackProfile(label=label, frameworks=frameworks, **toolchain)


def _detect_toolchain(project_root: Path) -> dict[str, str | None]:
    """Resolve the eight toolchain fields from the repo's manifests.

    Returns a kwargs dict for :class:`StackProfile` (``formatter`` …
    ``typecheck_command``). Every value is ``None`` when no manifest names the
    corresponding tool. Python commands gain a ``uv run`` prefix when uv is in
    use; node commands a ``npx`` prefix.
    """
    blob = _manifest_blob(project_root)
    uv = _uses_uv(project_root, blob)
    # test/lint/typecheck are run by an agent in the project dir, so python
    # commands take the venv-correct ``uv run`` prefix (spec §2). The format
    # command runs inside the minimal PostToolUse hook shell guarded by
    # ``command -v <formatter>`` (spec §5), so it stays bare for python; node
    # keeps ``npx`` in both schemes.
    run_prefixes = {_PY: "uv run " if uv else "", _NODE: "npx "}
    format_prefixes = {_PY: "", _NODE: "npx "}
    test_runner, test_command = _first_token(_TEST_TOKENS, blob, run_prefixes)
    linter, lint_command = _first_token(_LINT_TOKENS, blob, run_prefixes)
    type_checker, typecheck_command = _first_token(
        _TYPECHECK_TOKENS, blob, run_prefixes
    )
    formatter, format_command = _first_token(_FORMAT_TOKENS, blob, format_prefixes)
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
