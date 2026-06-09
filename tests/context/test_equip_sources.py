"""Discovery I/O behind a fake Runner — no live network."""
import base64
import json

from dummyindex.context.domains.equip import (
    RunResult,
    ToolAvailability,
    available_tools,
    fetch_catalog,
    fetch_file,
    search_github,
)


def _fake_runner(responses):
    """responses: dict mapping the first 2 argv tokens (joined) -> RunResult."""

    def run(argv):
        key = " ".join(argv[:2])
        return responses.get(key, RunResult(returncode=1, stdout="", stderr="not found"))

    return run


def test_available_tools_detects_presence():
    runner = _fake_runner(
        {
            "gh --version": RunResult(0, "gh 2.0", ""),
            "git --version": RunResult(0, "git 2.40", ""),
        }
    )
    tools = available_tools(runner=runner)
    assert isinstance(tools, ToolAvailability)
    assert tools.gh is True and tools.git is True and tools.claude is False


def test_fetch_file_decodes_base64_contents():
    runner = _fake_runner(
        {"gh api": RunResult(0, json.dumps({"content": base64.b64encode(b"hello").decode(), "encoding": "base64"}), "")}
    )
    assert fetch_file("o/r", "x.md", runner=runner) == "hello"


def test_fetch_catalog_decodes_gh_contents():
    payload = {"name": "m", "plugins": [{"name": "p"}]}
    content = base64.b64encode(json.dumps(payload).encode()).decode()
    runner = _fake_runner(
        {"gh api": RunResult(0, json.dumps({"content": content, "encoding": "base64"}), "")}
    )
    data = fetch_catalog("anthropics/claude-plugins-official", runner=runner)
    assert data["plugins"][0]["name"] == "p"


def test_fetch_catalog_missing_returns_none():
    runner = _fake_runner({})  # gh api -> returncode 1
    assert fetch_catalog("o/r", runner=runner) is None


def test_search_github_parses_repo_lines():
    runner = _fake_runner(
        {"gh search": RunResult(0, "anthropics/claude-plugins-official\nfoo/bar\n", "")}
    )
    repos = search_github("postgres", runner=runner)
    assert "foo/bar" in repos
    assert "anthropics/claude-plugins-official" in repos


def test_search_github_empty_on_failure():
    runner = _fake_runner({})  # both gh search code + repos fail
    assert search_github("postgres", runner=runner) == ()
