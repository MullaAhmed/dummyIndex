"""I/O for plugin discovery: probe tools, fetch marketplace catalogs, search
GitHub.

The ONLY equip module that shells out — isolated behind a ``Runner`` seam (a
callable taking argv and returning :class:`RunResult`) so tests inject a fake
and never touch the network. Mirrors the subprocess-in-domain precedent in
``context/build/git_delta.py``: fixed argv, no shell, never raises on non-zero.
"""
from __future__ import annotations

import base64
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..errors import SourceError

CATALOG_PATH = ".claude-plugin/marketplace.json"


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[list[str]], RunResult]


def default_runner(argv: list[str]) -> RunResult:
    """Run ``argv`` with no shell, capturing output. Never raises on non-zero;
    a missing executable surfaces as returncode 127."""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return RunResult(returncode=127, stdout="", stderr=str(exc))
    return RunResult(proc.returncode, proc.stdout, proc.stderr)


@dataclass(frozen=True)
class ToolAvailability:
    claude: bool
    gh: bool
    git: bool


def available_tools(*, runner: Runner = default_runner) -> ToolAvailability:
    def has(tool: str) -> bool:
        return runner([tool, "--version"]).returncode == 0

    return ToolAvailability(claude=has("claude"), gh=has("gh"), git=has("git"))


def fetch_file(repo: str, path: str, *, runner: Runner = default_runner) -> str | None:
    """Fetch one file's text from a GitHub repo via ``gh api`` contents.

    Returns ``None`` when the file/repo is absent (non-zero exit). Raises
    :class:`SourceError` when the response is present but undecodable.
    """
    res = runner(["gh", "api", f"repos/{repo}/contents/{path}"])
    if res.returncode != 0:
        return None
    try:
        obj = json.loads(res.stdout)
        if isinstance(obj, dict) and obj.get("encoding") == "base64":
            return base64.b64decode(obj["content"]).decode("utf-8")
        if isinstance(obj, dict):
            return str(obj.get("content", ""))
        raise SourceError(f"unexpected gh api response shape for {repo}/{path}")
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        raise SourceError(f"could not decode {path} from {repo}: {exc}") from exc


def fetch_catalog(repo: str, *, runner: Runner = default_runner) -> dict[str, Any] | None:
    """Fetch + JSON-parse a repo's marketplace.json. ``None`` when absent."""
    text = fetch_file(repo, CATALOG_PATH, runner=runner)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SourceError(f"{repo}/{CATALOG_PATH} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceError(f"{repo}/{CATALOG_PATH} is not a JSON object")
    return data


def search_github(query: str, *, runner: Runner = default_runner) -> tuple[str, ...]:
    """Find repos that ship a marketplace.json, via GitHub code search.

    Tries ``gh search code`` for the catalog path + query; falls back to
    ``gh search repos`` on failure. Returns owner/repo strings, deduped and
    order-preserving. Empty tuple when ``gh`` is unavailable or finds nothing.
    """
    res = runner(
        [
            "gh", "search", "code", CATALOG_PATH, query,
            "--json", "repository",
            "--jq", ".[].repository.nameWithOwner",
        ]
    )
    if res.returncode != 0:
        res = runner(["gh", "search", "repos", query, "--limit", "20"])
        if res.returncode != 0:
            return ()
    seen: list[str] = []
    for line in res.stdout.splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if token and "/" in token and token not in seen:
            seen.append(token)
    return tuple(seen)
