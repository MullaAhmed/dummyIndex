"""Discovery I/O behind a fake Runner — no live network."""

import base64
import json

import pytest

from dummyindex.context.domains.equip import (
    RunResult,
    ToolAvailability,
    available_tools,
    fetch_catalog,
    fetch_file,
    search_github,
)
from dummyindex.context.domains.equip.errors import SourceError
from dummyindex.context.domains.equip.plugins.sources import (
    RepoMeta,
    SkillsShRef,
    find_skills_sh,
    is_safe_repo,
    list_skills,
    repo_meta,
)

pytestmark = pytest.mark.unit


def _fake_runner(responses):
    """responses: dict mapping the first 2 argv tokens (joined) -> RunResult."""

    def run(argv):
        key = " ".join(argv[:2])
        return responses.get(
            key, RunResult(returncode=1, stdout="", stderr="not found")
        )

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
        {
            "gh api": RunResult(
                0,
                json.dumps(
                    {
                        "content": base64.b64encode(b"hello").decode(),
                        "encoding": "base64",
                    }
                ),
                "",
            )
        }
    )
    assert fetch_file("o/r", "x.md", runner=runner) == "hello"


def test_fetch_catalog_decodes_gh_contents():
    payload = {"name": "m", "plugins": [{"name": "p"}]}
    content = base64.b64encode(json.dumps(payload).encode()).decode()
    runner = _fake_runner(
        {
            "gh api": RunResult(
                0, json.dumps({"content": content, "encoding": "base64"}), ""
            )
        }
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


# ----- Wave 2: pinned-ref enumeration + fetch (auto-vendor-skills) -----------

from dummyindex.context.domains.equip import (  # noqa: E402
    SkillRef,
    resolve_ref,
)


def _api_runner(table, *, record=None):
    """Fake gh runner keyed on the api endpoint (argv[2]), so a test can map
    distinct responses to commits/HEAD vs contents/<path>."""

    def run(argv):
        if record is not None:
            record.append(list(argv))
        if argv[:2] != ["gh", "api"]:
            return RunResult(1, "", "not found")
        return table.get(argv[2], RunResult(1, "", "not found"))

    return run


def _ok(payload) -> RunResult:
    return RunResult(0, json.dumps(payload), "")


def _b64(text: str) -> RunResult:
    content = base64.b64encode(text.encode()).decode()
    return RunResult(0, json.dumps({"content": content, "encoding": "base64"}), "")


def test_resolve_ref_returns_sha():
    sha = "a" * 40
    runner = _api_runner({"repos/o/r/commits/HEAD": _ok({"sha": sha})})
    assert resolve_ref("o/r", runner=runner) == sha


def test_resolve_ref_missing_returns_none():
    assert resolve_ref("o/r", runner=_api_runner({})) is None


def test_resolve_ref_undecodable_raises():
    runner = _api_runner({"repos/o/r/commits/HEAD": RunResult(0, "not json", "")})
    try:
        resolve_ref("o/r", runner=runner)
        raise AssertionError("expected SourceError")
    except SourceError:
        pass


def test_fetch_file_pins_ref_in_endpoint():
    rec: list = []
    sha = "b" * 40
    runner = _api_runner(
        {f"repos/o/r/contents/skills/x/SKILL.md?ref={sha}": _b64("hi")}, record=rec
    )
    assert fetch_file("o/r", "skills/x/SKILL.md", ref=sha, runner=runner) == "hi"
    assert any(f"?ref={sha}" in argv[2] for argv in rec)


def test_fetch_file_without_ref_has_no_query():
    rec: list = []
    runner = _api_runner({"repos/o/r/contents/x.md": _b64("hi")}, record=rec)
    assert fetch_file("o/r", "x.md", runner=runner) == "hi"
    assert all("?ref=" not in argv[2] for argv in rec)


def test_list_skills_enumerates_under_skills_dir():
    runner = _api_runner(
        {
            "repos/o/r/contents/skills": _ok(
                [
                    {"type": "dir", "name": "b-skill", "path": "skills/b-skill"},
                    {"type": "dir", "name": "a-skill", "path": "skills/a-skill"},
                    {"type": "file", "name": "README.md", "path": "skills/README.md"},
                ]
            )
        }
    )
    skills = list_skills("o/r", runner=runner)
    assert [s.name for s in skills] == ["a-skill", "b-skill"]  # sorted
    assert skills[0].path == "skills/a-skill/SKILL.md"
    assert all(isinstance(s, SkillRef) for s in skills)


def test_list_skills_falls_back_to_repo_root():
    runner = _api_runner(
        {
            # skills/ absent (404 -> not in table)
            "repos/o/r/contents": _ok(
                [{"type": "dir", "name": "solo", "path": "solo"}]
            ),
        }
    )
    skills = list_skills("o/r", runner=runner)
    assert [s.name for s in skills] == ["solo"]
    assert skills[0].path == "solo/SKILL.md"


def test_list_skills_skips_files_and_hidden_dirs():
    runner = _api_runner(
        {
            "repos/o/r/contents/skills": _ok(
                [
                    {"type": "dir", "name": ".github", "path": "skills/.github"},
                    {"type": "dir", "name": "real", "path": "skills/real"},
                    {"type": "file", "name": "x", "path": "skills/x"},
                ]
            )
        }
    )
    assert [s.name for s in list_skills("o/r", runner=runner)] == ["real"]


def test_list_skills_drops_unsafe_path_names():
    # A skill name becomes a path segment under .claude/skills/ at install time —
    # any separator/traversal name must be filtered out here (defense-in-depth)
    # so a crafted catalog entry can never escape the skills dir downstream.
    runner = _api_runner(
        {
            "repos/o/r/contents/skills": _ok(
                [
                    {"type": "dir", "name": "ok", "path": "skills/ok"},
                    {"type": "dir", "name": "a/b", "path": "skills/a/b"},
                    {"type": "dir", "name": "..", "path": "skills/.."},
                    {"type": "dir", "name": "a\\b", "path": "skills/a\\b"},
                ]
            )
        }
    )
    assert [s.name for s in list_skills("o/r", runner=runner)] == ["ok"]


def test_list_skills_empty_when_nothing_found():
    assert list_skills("o/r", runner=_api_runner({})) == ()


def test_list_skills_carries_pinned_ref():
    sha = "c" * 40
    runner = _api_runner(
        {
            f"repos/o/r/contents/skills?ref={sha}": _ok(
                [{"type": "dir", "name": "s", "path": "skills/s"}]
            )
        }
    )
    skills = list_skills("o/r", ref=sha, runner=runner)
    assert skills[0].ref == sha


# ----- specialist sourcing: root_fallback, skills.sh, repo_meta ---------------


def test_list_skills_root_fallback_off_skips_repo_root():
    seen: list[str] = []

    def runner(argv):
        seen.append(argv[2] if argv[:2] == ["gh", "api"] else "")
        if argv[:2] == ["gh", "api"] and argv[2] == "repos/o/r/contents":
            return _ok([{"type": "dir", "name": "solo", "path": "solo"}])
        return RunResult(1, "", "not found")

    assert list_skills("o/r", runner=runner, root_fallback=False) == ()
    assert "repos/o/r/contents" not in seen
    assert seen == ["repos/o/r/contents/skills"]


def test_list_skills_root_fallback_default_still_uses_root():
    runner = _api_runner(
        {"repos/o/r/contents": _ok([{"type": "dir", "name": "solo", "path": "solo"}])}
    )
    assert [s.name for s in list_skills("o/r", runner=runner)] == ["solo"]


def _sh_runner(*, rc=0, stdout="", stderr="", record=None):
    def run(argv):
        if record is not None:
            record.append(list(argv))
        return RunResult(rc, stdout, stderr)

    return run


def test_find_skills_sh_parses_ansi_and_counts():
    out = (
        "\x1b[32mvercel-labs/agent-skills@react-best\x1b[0m  1.2K installs\n"
        "foo/bar@baz 3,400\n"
    )
    refs, reason = find_skills_sh("implement", runner=_sh_runner(stdout=out))
    assert refs == (
        SkillsShRef("vercel-labs/agent-skills", "react-best", 1200),
        SkillsShRef("foo/bar", "baz", 3400),
    )
    assert reason is None


def test_find_skills_sh_missing_count_is_none():
    refs, reason = find_skills_sh("test", runner=_sh_runner(stdout="foo/bar@baz\n"))
    assert refs == (SkillsShRef("foo/bar", "baz", None),)
    assert reason is None


def test_find_skills_sh_drops_unsafe_repo_and_skill():
    out = "../x@evil\na/..@s\nfoo/bar@.hidden\nok/repo@good 5\n"
    refs, _ = find_skills_sh("verify", runner=_sh_runner(stdout=out))
    assert refs == (SkillsShRef("ok/repo", "good", 5),)


def test_find_skills_sh_dedupes_keeping_first_order():
    out = "a/b@x 10\nc/d@y\na/b@x 99\n"
    refs, _ = find_skills_sh("review", runner=_sh_runner(stdout=out))
    assert refs == (SkillsShRef("a/b", "x", 10), SkillsShRef("c/d", "y", None))


def test_find_skills_sh_nonzero_returns_first_stderr_line():
    refs, reason = find_skills_sh(
        "implement",
        runner=_sh_runner(rc=127, stderr="npx: not found\nmore"),
    )
    assert refs == ()
    assert reason == "npx: not found"


def test_find_skills_sh_empty_output_is_no_results():
    assert find_skills_sh("test", runner=_sh_runner()) == ((), "no results")


def test_find_skills_sh_rejects_non_capability_query_without_running():
    record: list = []
    refs, reason = find_skills_sh("rm -rf", runner=_sh_runner(record=record))
    assert refs == ()
    assert reason == "unsupported query"
    assert record == []


def test_find_skills_sh_uses_which_for_argv0(monkeypatch):
    import dummyindex.context.domains.equip.plugins.sources as sources

    record: list = []
    monkeypatch.setattr(sources.shutil, "which", lambda _name: "C:/x/npx.cmd")
    find_skills_sh("database", runner=_sh_runner(record=record))
    assert record[0][0] == "C:/x/npx.cmd"
    assert record[0][1:] == ["--no", "skills", "find", "database"]


def test_find_skills_sh_falls_back_to_bare_npx(monkeypatch):
    import dummyindex.context.domains.equip.plugins.sources as sources

    record: list = []
    monkeypatch.setattr(sources.shutil, "which", lambda _name: None)
    find_skills_sh("database", runner=_sh_runner(record=record))
    assert record[0][0] == "npx"


def test_repo_meta_parses_fields():
    payload = {
        "stargazers_count": 42,
        "pushed_at": "2026-01-02T03:04:05Z",
        "license": {"spdx_id": "MIT"},
        "archived": True,
    }
    runner = _sh_runner(stdout=json.dumps(payload))
    assert repo_meta("o/r", runner=runner) == RepoMeta(
        stars=42, pushed_at="2026-01-02T03:04:05Z", license="MIT", archived=True
    )


def test_repo_meta_null_license_is_none():
    payload = {"stargazers_count": 1, "pushed_at": "", "license": None}
    meta = repo_meta("o/r", runner=_sh_runner(stdout=json.dumps(payload)))
    assert meta.license is None and meta.archived is False


def test_repo_meta_nonzero_returns_none():
    assert repo_meta("o/r", runner=_sh_runner(rc=1, stderr="nope")) is None


def test_repo_meta_bad_json_raises():
    with pytest.raises(SourceError):
        repo_meta("o/r", runner=_sh_runner(stdout="{not json"))


def test_is_safe_repo_accepts_and_rejects():
    assert is_safe_repo("a/b") is True
    for bad in ("a/b/c", "../b", "a/..", "a b/c", "a", "./b", "a/."):
        assert is_safe_repo(bad) is False, bad
