"""Stack-aware author picker for the v0.14 council.

Given a feature's file list and the repo's harvested dependency tokens,
decide *which* stack-specialist "dev" persona should author that feature's
docs. Deterministic, first-match-wins, no LLM.

The precedence table is encoded as a tuple of :class:`_Rule` objects — a
predicate over ``(feature_files, dep_tokens)`` plus the persona/subagent it
yields and a framework *resolver* (the matched framework can depend on the
inputs, e.g. React vs. Vue vs. Svelte for the frontend rule). The first
rule whose predicate returns true wins; the final rule's predicate is the
constant-true fallback.

The ``subagent_type`` values are the exact **end-user-global** Claude agent
names (``Backend Architect``, ``Frontend Developer``, …) — never lowercased
or hyphenated, never project-local.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class SubagentType(str, Enum):
    """Exact global Claude agent identifiers a persona dispatches to.

    Wire-compatible: ``.value`` is the literal end-user-global agent name
    (``Backend Architect``, …), never lowercased/hyphenated/project-local.
    """

    BACKEND = "Backend Architect"
    FRONTEND = "Frontend Developer"
    DATA = "Data Engineer"
    AI = "AI Engineer"
    SENIOR = "Senior Developer"
    GENERAL = "general-purpose"  # universal built-in; the last-resort fallback


# The generalist ladder every specialist degrades down, most-specific first,
# ending at the always-available built-in. Specialists (Backend Architect, …)
# sit conceptually above the ladder, so they fall back onto the whole thing.
_FALLBACK_LADDER: tuple[SubagentType, ...] = (
    SubagentType.SENIOR,
    SubagentType.GENERAL,
)


def _fallbacks_for(primary: SubagentType) -> tuple[SubagentType, ...]:
    """Ordered alternatives to try when ``primary`` isn't installed.

    The skill consults this chain against the agents the preflight step found
    available, dispatching the first present one. The chain always ends at
    ``general-purpose`` (always available), so dispatch never bottoms out with
    no agent. A primary already on the ladder yields only the rungs below it;
    ``general-purpose`` itself yields an empty chain.
    """
    if primary in _FALLBACK_LADDER:
        return _FALLBACK_LADDER[_FALLBACK_LADDER.index(primary) + 1:]
    return _FALLBACK_LADDER


class PersonaId(str, Enum):
    """Closed alphabet of stack-specialist "dev" authoring personas."""

    BACKEND_FASTAPI = "dev-backend-fastapi"
    BACKEND_DJANGO = "dev-backend-django"
    BACKEND_SPRING = "dev-backend-spring"
    BACKEND_NODE = "dev-backend-node"
    FRONTEND = "dev-frontend"
    DATA = "dev-data"
    AI = "dev-ai"
    GENERIC_SENIOR = "dev-generic-senior"


# --- dependency-token alphabets ----------------------------------------------
_FRONTEND_DEP_TOKENS: tuple[str, ...] = ("react", "vue", "svelte")
_AI_DEP_TOKENS: frozenset[str] = frozenset(
    {
        "torch",
        "tensorflow",
        "sklearn",
        "scikit-learn",
        "transformers",
        "langchain",
        "openai",
        "anthropic",
    }
)
_FRONTEND_FILE_SUFFIXES: tuple[str, ...] = (".jsx", ".tsx", ".vue", ".svelte")

# AI-by-path: an exact path *segment* (not unanchored substring). ML pipelines
# are still caught via the ML dep tokens above; `pipeline` is intentionally not
# a path marker (this repo's own `pipeline/` would false-positive).
_AI_PATH_SEGMENTS: frozenset[str] = frozenset({"inference", "training"})
_AI_BASENAME_PREFIXES: tuple[str, ...] = ("train.", "train_", "inference.", "predict.")


@dataclass(frozen=True)
class DevPick:
    """The resolved authoring persona for a feature."""

    persona_id: PersonaId
    subagent_type: SubagentType
    framework: str
    fallbacks: tuple[SubagentType, ...] = ()  # tried in order if subagent_type absent

    def to_dict(self) -> dict[str, Any]:
        # Emit `.value` explicitly so the wire contract never depends on the
        # (str, Enum) mixin's serialization quirks — str() on a member is the
        # 'SubagentType.AI' repr on Python 3.11+, not the agent name.
        return {
            "persona_id": self.persona_id.value,
            "subagent_type": self.subagent_type.value,
            "framework": self.framework,
            "fallbacks": [f.value for f in self.fallbacks],
        }


class DevPickError(ValueError):
    """Raised when the picker cannot resolve a persona for the given inputs."""


# --- predicate / resolver helpers --------------------------------------------

def _any_path_contains(files: tuple[str, ...], needle: str) -> bool:
    return any(needle in f for f in files)


def _any_path_endswith(files: tuple[str, ...], *suffixes: str) -> bool:
    return any(f.endswith(suffixes) for f in files)


def _path_segments(path: str) -> tuple[str, ...]:
    """Split a posix-style path into its segments (drops empties)."""
    return tuple(seg for seg in path.split("/") if seg)


def _any_segment_in(files: tuple[str, ...], segments: frozenset[str]) -> bool:
    return any(seg in segments for f in files for seg in _path_segments(f))


def _any_basename_startswith(files: tuple[str, ...], *prefixes: str) -> bool:
    return any(f.rsplit("/", 1)[-1].startswith(prefixes) for f in files)


def _is_fastapi(files: tuple[str, ...], deps: frozenset[str]) -> bool:
    if "fastapi" not in deps:
        return False
    return _any_path_contains(files, "routes/") or _any_path_contains(files, "app/api/")


def _is_django(files: tuple[str, ...], deps: frozenset[str]) -> bool:
    return "django" in deps and _any_path_endswith(files, "views.py")


def _is_spring(files: tuple[str, ...], deps: frozenset[str]) -> bool:
    if not ({"spring-boot", "springframework"} & deps):
        return False
    return _any_path_endswith(files, "Controller.java")


def _is_node(files: tuple[str, ...], deps: frozenset[str]) -> bool:
    if not ({"express", "next"} & deps):
        return False
    return any(
        "app/api/" in f and f.endswith(("route.ts", "route.js"))
        for f in files
    )


def _is_frontend(files: tuple[str, ...], deps: frozenset[str]) -> bool:
    if _any_path_endswith(files, *_FRONTEND_FILE_SUFFIXES):
        return True
    return bool(set(_FRONTEND_DEP_TOKENS) & deps)


def _frontend_framework(files: tuple[str, ...], deps: frozenset[str]) -> str:
    """React/Vue/Svelte disambiguation.

    Precedence: a matching dependency token wins over a file extension;
    among deps, the declared order (react > vue > svelte) breaks ties. Falls
    back to the file-extension's implied framework, then the generic
    ``Frontend`` label when nothing names a framework.
    """
    for token, label in (("react", "React"), ("vue", "Vue"), ("svelte", "Svelte")):
        if token in deps:
            return label
    if _any_path_endswith(files, ".vue"):
        return "Vue"
    if _any_path_endswith(files, ".svelte"):
        return "Svelte"
    if _any_path_endswith(files, ".jsx", ".tsx"):
        return "React"
    return "Frontend"


_DATA_PATH_SEGMENTS: frozenset[str] = frozenset(
    {"models", "schemas", "schema", "migrations"}
)
_DATA_BASENAME_PREFIXES: tuple[str, ...] = ("models.", "models_", "schema.", "schema_")


def _is_data(files: tuple[str, ...], deps: frozenset[str]) -> bool:
    if _any_path_endswith(files, ".sql"):
        return True
    if _any_segment_in(files, _DATA_PATH_SEGMENTS):
        return True
    return _any_basename_startswith(files, *_DATA_BASENAME_PREFIXES)


def _is_ai(files: tuple[str, ...], deps: frozenset[str]) -> bool:
    if _AI_DEP_TOKENS & deps:
        return True
    if _any_segment_in(files, _AI_PATH_SEGMENTS):
        return True
    return _any_basename_startswith(files, *_AI_BASENAME_PREFIXES)


def _always(files: tuple[str, ...], deps: frozenset[str]) -> bool:
    return True


@dataclass(frozen=True)
class _Rule:
    """One row of the precedence table."""

    predicate: Callable[[tuple[str, ...], frozenset[str]], bool]
    persona_id: PersonaId
    subagent_type: SubagentType
    framework: Callable[[tuple[str, ...], frozenset[str]], str]


def _const(value: str) -> Callable[[tuple[str, ...], frozenset[str]], str]:
    """A framework resolver that ignores its inputs and returns ``value``."""
    return lambda _files, _deps: value


# First-match-wins. The final rule is the constant-true fallback.
_RULES: tuple[_Rule, ...] = (
    _Rule(_is_fastapi, PersonaId.BACKEND_FASTAPI, SubagentType.BACKEND, _const("FastAPI")),
    _Rule(_is_django, PersonaId.BACKEND_DJANGO, SubagentType.BACKEND, _const("Django")),
    _Rule(_is_spring, PersonaId.BACKEND_SPRING, SubagentType.BACKEND, _const("Spring Boot")),
    _Rule(_is_node, PersonaId.BACKEND_NODE, SubagentType.BACKEND, _const("Node")),
    _Rule(_is_frontend, PersonaId.FRONTEND, SubagentType.FRONTEND, _frontend_framework),
    _Rule(_is_data, PersonaId.DATA, SubagentType.DATA, _const("Data")),
    _Rule(_is_ai, PersonaId.AI, SubagentType.AI, _const("AI")),
    _Rule(_always, PersonaId.GENERIC_SENIOR, SubagentType.SENIOR, _const("generic")),
)


def pick_dev(
    *, feature_files: tuple[str, ...], dep_tokens: frozenset[str]
) -> DevPick:
    """Resolve the authoring persona for a feature.

    First-match-wins over :data:`_RULES`. The fallback rule guarantees a
    return, so :class:`DevPickError` is reserved for a malformed table — if
    no rule matched (which the constant-true fallback should prevent), it is
    raised rather than returning ``None``.
    """
    for rule in _RULES:
        if rule.predicate(feature_files, dep_tokens):
            return DevPick(
                persona_id=rule.persona_id,
                subagent_type=rule.subagent_type,
                framework=rule.framework(feature_files, dep_tokens),
                fallbacks=_fallbacks_for(rule.subagent_type),
            )
    raise DevPickError("no rule matched and no fallback fired")


# --- feature/manifest I/O (relocated from cli/dev_pick.py so domains own it) ---

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
)

_TOKEN_RE = re.compile(r"[a-z0-9_-]+")

_PROSE_KEY_RE = re.compile(
    r'^\s*"?(description|summary|readme|keywords|authors?|maintainers?|name'
    r"|license|homepage|documentation|repository|classifiers)\"?\s*[=:]",
    re.IGNORECASE,
)


def _is_noise_line(line: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith("#") or stripped.startswith("//"):
        return True
    return _PROSE_KEY_RE.match(line) is not None


def harvest_dep_tokens(repo_root: Path) -> frozenset[str]:
    """Lowercased dependency tokens harvested from whichever root manifests exist.

    Tolerates missing/unreadable files. Skips comment + prose-bearing lines so a
    ``description = "A Django-style framework"`` doesn't misroute the repo.
    """
    tokens: set[str] = set()
    for name in _MANIFEST_NAMES:
        path = repo_root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if _is_noise_line(line):
                continue
            tokens.update(_TOKEN_RE.findall(line.lower()))
    return frozenset(tokens)


def read_feature_files(features_dir: Path, feature_id: str) -> tuple[str, ...]:
    """The feature's ``files`` list from ``features/<id>/feature.json``.

    Raises ``FileNotFoundError`` if the feature.json is absent.
    """
    feature_json = features_dir / feature_id / "feature.json"
    if not feature_json.is_file():
        raise FileNotFoundError(str(feature_json))
    data = json.loads(feature_json.read_text(encoding="utf-8"))
    return tuple(str(f) for f in data.get("files", []))
