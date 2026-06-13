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
    result = search_github("postgres", runner=runner)
    assert "foo/bar" in result.repos
    assert "anthropics/claude-plugins-official" in result.repos
    assert result.degraded is False


def test_search_github_empty_on_failure():
    runner = _fake_runner({})  # both gh search code + repos fail
    result = search_github("postgres", runner=runner)
    assert result.repos == ()
    assert result.degraded is True  # nothing answered — not a stable result


# ----- determinism (audit 2026-06-13, C4-P2): same query, same result --------


def test_search_github_sorts_and_dedupes_deterministically():
    runner = _fake_runner(
        {"gh search": RunResult(0, "z/last\na/first\nz/last\nm/mid\n", "")}
    )
    result = search_github("anything", runner=runner)
    assert result.repos == ("a/first", "m/mid", "z/last")  # sorted, deduped


def test_search_github_code_search_passes_limit():
    seen = []

    def runner(argv):
        seen.append(list(argv))
        return RunResult(0, "o/r\n", "")

    search_github("postgres", runner=runner)
    code_call = seen[0]
    assert code_call[:3] == ["gh", "search", "code"]
    assert "--limit" in code_call


def test_search_github_fallback_is_flagged_degraded():
    # gh search code fails (rate limit); the repos fallback answers — the
    # result must say so, because the universe just changed shape.
    def runner(argv):
        if argv[:3] == ["gh", "search", "code"]:
            return RunResult(1, "", "API rate limit exceeded")
        if argv[:3] == ["gh", "search", "repos"]:
            return RunResult(0, "o/r\n", "")
        return RunResult(1, "", "")

    result = search_github("postgres", runner=runner)
    assert result.repos == ("o/r",)
    assert result.degraded is True
    assert result.reason  # carries the why for the CLI warning
