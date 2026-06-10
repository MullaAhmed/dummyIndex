"""`dummyindex context dev-pick --feature ID` — stack-aware author picker.

Resolves which stack-specialist "dev" persona should author a feature's
docs and prints the result as JSON to stdout. Deterministic, no LLM —
the council skill uses it for inspection and dispatch.

Reads the feature's ``files`` list from
``.context/features/<id>/feature.json`` and harvests lowercased dependency
tokens from whichever manifests exist at the repo root. No TOML/JSON parser
dependency: manifests are read as raw text and split on non-token
characters, preserving hyphens and dots so tokens like ``spring-boot`` and
``scikit-learn`` survive.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .common import parse_kv_flags, parse_path_and_root, resolve_context_root

# Manifests scanned for dependency/framework tokens. Missing files tolerated.
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

# Token = run of lowercase word chars plus hyphen (keeps `spring-boot`,
# `scikit-learn` intact). The dot is a separator so dotted package paths split
# into components (`org.springframework.boot` -> `org`, `springframework`,
# `boot`). Split on everything else.
_TOKEN_RE = re.compile(r"[a-z0-9_-]+")

# Lines that carry prose, not dependencies. A `description = "A Django-style
# framework"` would otherwise inject `django` and misroute the whole repo.
_PROSE_KEY_RE = re.compile(
    r'^\s*"?(description|summary|readme|keywords|authors?|maintainers?|name'
    r"|license|homepage|documentation|repository|classifiers)\"?\s*[=:]",
    re.IGNORECASE,
)


def _is_noise_line(line: str) -> bool:
    """True for comment lines and prose-bearing key lines (skip when harvesting)."""
    stripped = line.lstrip()
    if stripped.startswith("#") or stripped.startswith("//"):
        return True
    return _PROSE_KEY_RE.match(line) is not None


def _harvest_dep_tokens(repo_root: Path) -> frozenset[str]:
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


def _read_feature_files(features_dir: Path, feature_id: str) -> tuple[str, ...]:
    feature_json = features_dir / feature_id / "feature.json"
    if not feature_json.is_file():
        raise FileNotFoundError(str(feature_json))
    data = json.loads(feature_json.read_text(encoding="utf-8"))
    files = data.get("files", [])
    return tuple(str(f) for f in files)


def run(args: list[str]) -> int:
    from dummyindex.context.domains.dev_pick import pick_dev

    scope, explicit_root, rest = parse_path_and_root(args)
    parsed, leftover = parse_kv_flags(rest)
    if leftover:
        print(f"error: unknown argument(s) for `dev-pick`: {leftover}", file=sys.stderr)
        return 2
    feature_id = parsed.get("feature")
    if not feature_id:
        print("error: --feature <id> is required", file=sys.stderr)
        return 2

    repo_root = resolve_context_root(scope, explicit_root=explicit_root)
    features_dir = repo_root / ".context" / "features"

    try:
        feature_files = _read_feature_files(features_dir, feature_id)
    except FileNotFoundError as exc:
        print(f"error: feature {feature_id} not found ({exc})", file=sys.stderr)
        return 2

    dep_tokens = _harvest_dep_tokens(repo_root)
    pick = pick_dev(feature_files=feature_files, dep_tokens=dep_tokens)
    print(json.dumps(pick.to_dict()))
    return 0
