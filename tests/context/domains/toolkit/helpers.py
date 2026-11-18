"""Helpers for the toolkit facade tests: tree snapshots and a fake GitHub/claude seam."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dummyindex.context.domains.equip.plugins.sources import RunResult

SHA_A = "a" * 40
SHA_B = "b" * 40
SKILL_TEXT = "---\nname: demo\ndescription: demo skill\n---\nbody\n"
MCP_TEXT = json.dumps({"type": "http", "url": "https://example.test/mcp"})


def snapshot(folder: Path) -> dict[str, bytes]:
    """Relative POSIX path -> bytes for every file under ``folder``."""
    if not folder.exists():
        return {}
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@dataclass
class FakeGh:
    """Stands in for ``gh api`` and ``claude plugin`` in install tests.

    ``contents`` maps repo -> {path: text}. ``commit_sha`` answers
    ``repos/<repo>/commits/<ref>``; it may be a callable so a test can move the
    ref between preview and apply. ``catalogs`` maps repo -> marketplace dict.
    """

    contents: dict[str, dict[str, str]] = field(default_factory=dict)
    commit_sha: str | Callable[[str], str] = SHA_A
    catalogs: dict[str, dict] = field(default_factory=dict)
    claude_returncode: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, argv: list[str]) -> RunResult:
        self.calls.append(list(argv))
        if argv[:2] == ["gh", "api"]:
            return self._gh(argv[2])
        if argv[:2] == ["claude", "plugin"]:
            return RunResult(
                self.claude_returncode,
                "{}",
                "claude failed" if self.claude_returncode else "",
            )
        return RunResult(127, "", "unexpected argv")

    def _gh(self, endpoint: str) -> RunResult:
        path = endpoint.partition("?")[0]
        if path.startswith("repos/") and "/commits/" in path:
            repo, _, ref = path[len("repos/") :].partition("/commits/")
            sha = self.commit_sha(ref) if callable(self.commit_sha) else self.commit_sha
            return RunResult(0, json.dumps({"sha": sha}), "")
        if path.startswith("repos/") and "/contents/" in path:
            repo, _, rel = path[len("repos/") :].partition("/contents/")
            if rel == ".claude-plugin/marketplace.json":
                if repo not in self.catalogs:
                    return RunResult(1, "", "not found")
                text = json.dumps(self.catalogs[repo])
            elif rel in self.contents.get(repo, {}):
                text = self.contents[repo][rel]
            else:
                return RunResult(1, "", "not found")
            return RunResult(
                0, json.dumps({"encoding": "base64", "content": b64(text)}), ""
            )
        return RunResult(1, "", "unhandled endpoint")


def plugin_catalog(name: str, plugin: str, *, hooks: bool) -> dict:
    entry: dict = {"name": plugin, "description": "lint helper", "keywords": []}
    if hooks:
        entry["hooks"] = {"PostToolUse": []}
    return {"name": name, "plugins": [entry]}
