"""Shared policy for Codex project-guidance filenames.

Codex always checks its two standard instruction filenames first, then any
project-only fallbacks configured in the active, trusted ``config.toml``.
Keeping the parser here lets guidance output, file detection, source-doc
discovery, and drift filtering agree without importing one another.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


CODEX_INSTRUCTION_PRECEDENCE: tuple[str, ...] = (
    "AGENTS.override.md",
    "AGENTS.md",
)
DEFAULT_PROJECT_DOC_MAX_BYTES = 32 * 1024
_MISSING = object()


def codex_home(home: Path | None = None) -> Path:
    """Return the active Codex home, honoring a nonempty ``CODEX_HOME``."""
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser()
    return (home if home is not None else Path.home()) / ".codex"


def configured_project_doc_fallback_filenames(
    project_root: Path | None = None,
) -> tuple[str, ...]:
    """Return validated project fallback names from active Codex config.

    Missing, unreadable, or malformed TOML safely means no fallbacks. A project
    layer is considered only when user-owned config explicitly trusts its
    resolved root. Invalid entries are ignored individually. Accepted entries
    are host-native relative paths confined to the project.
    """
    configured: object = _MISSING
    for payload in _config_layers(project_root):
        candidate = payload.get("project_doc_fallback_filenames", _MISSING)
        # Only a valid layer overrides the lower-precedence value. In
        # particular, an explicit project-level [] clears a user-level list.
        if isinstance(candidate, list):
            configured = candidate
    if configured is _MISSING:
        return ()

    safe: list[str] = []
    seen = set(CODEX_INSTRUCTION_PRECEDENCE)
    for entry in configured:
        if not isinstance(entry, str):
            continue
        normalized = _normalize_safe_fallback_path(entry)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        safe.append(normalized)
    return tuple(safe)


def configured_project_doc_max_bytes(project_root: Path | None = None) -> int:
    """Return Codex's effective project-instruction byte budget.

    System config is the lowest persistent layer, user config overlays it, and
    a trusted project-root ``.codex/config.toml`` overlays both when present.
    Invalid, unreadable, or untrusted project layers are ignored, matching
    Codex's own trust boundary.
    """
    configured = DEFAULT_PROJECT_DOC_MAX_BYTES
    for payload in _config_layers(project_root):
        candidate = payload.get("project_doc_max_bytes", _MISSING)
        if (
            isinstance(candidate, int)
            and not isinstance(candidate, bool)
            and candidate >= 0
        ):
            configured = candidate
    return configured


def project_instruction_paths(
    project_root: Path | None = None,
) -> tuple[str, ...]:
    """Ordered relative candidates Codex probes at each searched directory."""
    return tuple(
        dict.fromkeys(
            (
                *CODEX_INSTRUCTION_PRECEDENCE,
                *configured_project_doc_fallback_filenames(project_root),
            )
        )
    )


def project_instruction_filenames(
    project_root: Path | None = None,
) -> frozenset[str]:
    """Compatibility alias for the active relative instruction candidates."""
    return frozenset(project_instruction_paths(project_root))


def is_project_instruction_path(
    path: str | Path,
    project_root: Path,
    *,
    instruction_paths: Iterable[str] | None = None,
) -> bool:
    """Whether ``path`` can be a Codex instruction candidate in this project.

    Codex joins every configured relative candidate to each directory between
    the project root and the launch directory. This standalone CLI cannot know
    the latter, so a repository path is conservatively treated as guidance when
    its component suffix matches a candidate. Nested candidates are compared as
    paths, not by basename (``docs/RULES.md`` must not hide every ``RULES.md``).

    Absolute paths outside ``project_root`` retain basename matching for the
    standard/single-component candidates. That preserves the existing policy of
    not ingesting an explicitly supplied external ``AGENTS.md`` while ensuring
    a nested project fallback cannot accidentally suppress an unrelated file.
    """
    candidates = tuple(
        project_instruction_paths(project_root)
        if instruction_paths is None
        else instruction_paths
    )
    relative = _project_relative_match_path(path, project_root)
    relative_parts = PurePosixPath(relative).parts
    for candidate in candidates:
        candidate_parts = PurePosixPath(candidate).parts
        if len(relative_parts) >= len(candidate_parts) and (
            relative_parts[-len(candidate_parts) :] == candidate_parts
        ):
            return True
    return False


def _config_layers(project_root: Path | None) -> tuple[dict, ...]:
    """Load the discoverable Codex config layers in precedence order.

    Runtime ``-c`` overrides, selected profiles, and the launch directory's
    nested project layers belong to the Codex process and are not observable by
    this standalone CLI. The platform system layer, persistent user layer, its
    persisted project-trust table, and the repository-root project layer that
    governs the root guidance target are observable. Match Codex's trust
    boundary: a project layer is loaded only when the resolved root has an
    explicit ``trust_level = "trusted"`` entry in the user config.
    """
    loaded: list[dict] = []
    system_payload = _load_config(_system_config_path())
    if system_payload is not None:
        loaded.append(system_payload)

    user_path = codex_home() / "config.toml"
    user_payload = _load_config(user_path)
    if user_payload is not None:
        loaded.append(user_payload)

    if project_root is None or user_payload is None:
        return tuple(loaded)
    try:
        resolved_root = project_root.resolve()
    except (OSError, RuntimeError, ValueError):
        return tuple(loaded)
    if not _project_is_trusted(user_payload, resolved_root):
        return tuple(loaded)

    project_path = resolved_root / ".codex" / "config.toml"
    if project_path != user_path:
        project_payload = _load_config(project_path)
        if project_payload is not None:
            loaded.append(project_payload)
    return tuple(loaded)


def _system_config_path() -> Path:
    """Return Codex's platform system-config location.

    Codex uses ``/etc/codex/config.toml`` on Unix (including macOS) and the
    ``OpenAI\\Codex`` folder under Windows' ProgramData known folder. Python's
    ``PROGRAMDATA`` environment value is the portable spelling of that Windows
    known folder; use Codex's own fallback when it is unavailable.
    """
    if os.name == "nt":
        program_data = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        return Path(program_data) / "OpenAI" / "Codex" / "config.toml"
    return Path("/etc/codex/config.toml")


def _load_config(path: Path) -> dict | None:
    """Load one persistent Codex config, treating every failure as absent."""
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _project_is_trusted(user_payload: dict, project_root: Path) -> bool:
    """Whether user-owned config explicitly trusts this canonical root key.

    Codex canonicalizes the directory being looked up, but does not resolve
    every configured table key. Mirroring that distinction prevents a stale
    trusted symlink alias from transferring trust to whatever it targets now.
    Windows trust-key lookup is case-insensitive, as in Codex itself.
    """
    projects = user_payload.get("projects")
    if not isinstance(projects, dict):
        return False
    lookup = str(project_root)
    project = projects.get(lookup)
    if project is None and os.name == "nt":
        normalized_lookup = lookup.lower()
        matching_keys = sorted(
            key
            for key in projects
            if isinstance(key, str) and key.lower() == normalized_lookup
        )
        if matching_keys:
            project = projects[matching_keys[0]]
    return isinstance(project, dict) and project.get("trust_level") == "trusted"


def _normalize_safe_fallback_path(value: str) -> str | None:
    """Normalize one confined relative fallback using host-native semantics."""
    if not value or value != value.strip() or "\x00" in value:
        return None
    native = Path(value)
    if native.is_absolute() or native.drive or native.root:
        return None
    if any(part == ".." for part in native.parts):
        return None
    normalized = native.as_posix()
    return normalized if normalized not in {"", ".", ".."} else None


def _project_relative_match_path(path: str | Path, project_root: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.relative_to(project_root.resolve()).as_posix()
        except (OSError, RuntimeError, ValueError):
            return candidate.name
    return PurePosixPath(str(path)).as_posix()
