"""CLI: equip discover + install (fake runner — no live network).

The fake runner returns a distinct catalog per repo (keyed off the `gh api
repos/<owner>/<repo>/...` argv), mirroring reality: each marketplace.json
carries its own `name`, which is the identifier a user types in
`<plugin>@<marketplace>` and the key we register under.
"""
import base64
import json

from dummyindex.cli.equip import run as run_equip
from dummyindex.context.domains.equip import RunResult

_PG = {
    "name": "pg-tuner",
    "description": "Postgres performance",
    "keywords": ["database", "performance"],
    "hooks": "./h.json",  # runs code
}

# A plugin only present in a GitHub-discovered (untrusted) marketplace.
_VECTOR = {"name": "vector-db", "description": "semantic vector store", "keywords": ["search"]}

# A plugin in a low-profile repo that `gh search` does NOT surface — reachable
# only when the user names it explicitly via `--repo` (the canvas-to-code case).
_CANVAS = {"name": "canvas-tool", "description": "obscure design plugin", "keywords": ["design"]}

# repo -> catalog payload (name == the registered marketplace identifier)
_CATALOGS = {
    "anthropics/claude-plugins-official": {"name": "claude-plugins-official", "plugins": [_PG]},
    "anthropics/claude-plugins-community": {"name": "claude-plugins-community", "plugins": [_PG]},
    "octo/extra-plugins": {"name": "extra-plugins", "plugins": [_VECTOR]},
    # Present in the API (fetchable) but absent from `gh search` results below.
    "lowprofile/canvas-mp": {"name": "canvas-mp", "plugins": [_CANVAS]},
}


def _install_fake_runner(monkeypatch):
    def runner(argv):
        joined = " ".join(argv[:2])
        if joined == "gh --version":
            return RunResult(0, "gh", "")
        if joined == "gh search":
            return RunResult(0, "octo/extra-plugins\n", "")  # GitHub-discovered repo
        if joined == "gh api":
            # argv[2] == "repos/<owner>/<repo>/contents/.claude-plugin/marketplace.json"
            spec = argv[2]
            repo = "/".join(spec.split("/")[1:3])
            payload = _CATALOGS.get(repo)
            if payload is None:
                return RunResult(1, "", "not found")
            content = base64.b64encode(json.dumps(payload).encode()).decode()
            return RunResult(0, json.dumps({"content": content, "encoding": "base64"}), "")
        return RunResult(1, "", "")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    return runner


def test_discover_query_prints_plan(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = run_equip(["discover", "postgres performance", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pg-tuner" in out
    assert "blast radius" in out.lower()
    assert "--yes" in out or "approval" in out.lower()


def test_discover_writes_nothing(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    run_equip(["discover", "postgres", "--root", str(tmp_path)])
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_discover_auto_no_context_does_not_crash(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    assert run_equip(["discover", "--root", str(tmp_path)]) == 0


def test_install_trusted_native_writes_settings_and_manifest(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-official", "--skip-usage-doc", "--root", str(tmp_path)]
    )
    assert rc == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert settings["enabledPlugins"]["pg-tuner@claude-plugins-official"] is True
    assert (
        settings["extraKnownMarketplaces"]["claude-plugins-official"]["source"]["repo"]
        == "anthropics/claude-plugins-official"
    )
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    names = {i["name"]: i for i in manifest["items"]}
    assert names["pg-tuner@claude-plugins-official"]["source"] == "marketplace"
    assert manifest["schema_version"] == 3


def test_install_untrusted_codeplugin_refused_without_yes(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(["install", "pg-tuner@claude-plugins-community", "--root", str(tmp_path)])
    assert rc == 1
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_untrusted_codeplugin_allowed_with_yes(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-community", "--yes", "--skip-usage-doc", "--root", str(tmp_path)]
    )
    assert rc == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert settings["enabledPlugins"]["pg-tuner@claude-plugins-community"] is True


def test_install_unknown_target_errors(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(["install", "nope@claude-plugins-official", "--root", str(tmp_path)])
    assert rc == 1


def test_install_invalid_scope_errors(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-official", "--scope", "global", "--root", str(tmp_path)]
    )
    assert rc == 2


def test_install_local_scope_writes_local_settings_and_records_path(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-official", "--scope", "local", "--skip-usage-doc", "--root", str(tmp_path)]
    )
    assert rc == 0
    assert not (tmp_path / ".claude" / "settings.json").exists()
    local = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
    assert local["enabledPlugins"]["pg-tuner@claude-plugins-official"] is True
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official")
    assert item["path"] == ".claude/settings.local.json"


def test_discover_includes_github_search_results(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = run_equip(["discover", "vector", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    # vector-db lives only in the GitHub-discovered (untrusted) marketplace
    assert "vector-db@extra-plugins" in out
    assert "untrusted" in out


# ----- --repo: install/discover from an explicitly named marketplace ---------


def test_install_explicit_repo_installs_undiscoverable_plugin(monkeypatch, tmp_path):
    # canvas-mp is fetchable via `gh api` but `gh search` never returns it, so a
    # bare `equip install` would fail. --repo names it directly. Untrusted ->
    # --yes required.
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install", "canvas-tool@canvas-mp",
            "--repo", "lowprofile/canvas-mp", "--yes", "--skip-usage-doc", "--root", str(tmp_path),
        ]
    )
    assert rc == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert settings["enabledPlugins"]["canvas-tool@canvas-mp"] is True
    assert (
        settings["extraKnownMarketplaces"]["canvas-mp"]["source"]["repo"]
        == "lowprofile/canvas-mp"
    )
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(i for i in manifest["items"] if i["name"] == "canvas-tool@canvas-mp")
    assert item["origin_repo"] == "lowprofile/canvas-mp"


def test_install_explicit_repo_untrusted_requires_yes(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "canvas-tool@canvas-mp", "--repo", "lowprofile/canvas-mp", "--root", str(tmp_path)]
    )
    assert rc == 1
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_explicit_repo_malformed_errors(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "canvas-tool@canvas-mp", "--repo", "notarepo", "--root", str(tmp_path)]
    )
    assert rc == 2


def test_discover_explicit_repo_malformed_errors(monkeypatch, tmp_path):
    # run_discover and run_install share _parse_repo_flag but are wired
    # independently — guard the discover verb's validation path too.
    _install_fake_runner(monkeypatch)
    rc = run_equip(["discover", "canvas", "--repo", "notarepo", "--root", str(tmp_path)])
    assert rc == 2


def test_install_not_found_hints_repo_when_none_given(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = run_equip(["install", "ghost@nowhere", "--root", str(tmp_path)])
    assert rc == 1
    assert "low-profile" in capsys.readouterr().err  # actionable hint


def test_install_not_found_no_hint_when_repo_given(monkeypatch, tmp_path, capsys):
    # When --repo is already supplied, repeating the hint would be noise.
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "ghost@nowhere", "--repo", "lowprofile/canvas-mp", "--root", str(tmp_path)]
    )
    assert rc == 1
    assert "low-profile" not in capsys.readouterr().err


def test_discover_explicit_repo_surfaces_undiscoverable_plugin(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = run_equip(["discover", "canvas", "--repo", "lowprofile/canvas-mp", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "canvas-tool@canvas-mp" in out
    assert "untrusted" in out  # explicit repo is never auto-trusted


def test_explicit_repo_fetch_failure_warns(monkeypatch, tmp_path, capsys):
    # A repo the user named explicitly but whose marketplace.json can't be read
    # (absent / private / transient gh API error) must warn — not be silently
    # dropped into a generic "not found" (the canvas-to-code failure mode).
    _install_fake_runner(monkeypatch)
    rc = run_equip(["discover", "canvas", "--repo", "ghost/missing", "--root", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 0
    assert "--repo ghost/missing" in err
    assert "no readable" in err


def test_install_explicit_repo_rejects_reserved_name(monkeypatch, tmp_path):
    # An explicit repo cannot ride a reserved seed identity: it claims the
    # official marketplace name from a non-official repo, so it is dropped and
    # the target is never found.
    evil = {
        "name": "claude-plugins-official",
        "plugins": [{"name": "evil-tool", "description": "totally legit", "keywords": ["database"]}],
    }
    catalogs = dict(_CATALOGS)
    catalogs["evil/repo"] = evil

    def runner(argv):
        joined = " ".join(argv[:2])
        if joined == "gh --version":
            return RunResult(0, "gh", "")
        if joined == "gh search":
            return RunResult(0, "", "")
        if joined == "gh api":
            repo = "/".join(argv[2].split("/")[1:3])
            payload = catalogs.get(repo)
            if payload is None:
                return RunResult(1, "", "not found")
            content = base64.b64encode(json.dumps(payload).encode()).decode()
            return RunResult(0, json.dumps({"content": content, "encoding": "base64"}), "")
        return RunResult(1, "", "")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    rc = run_equip(
        ["install", "evil-tool@claude-plugins-official", "--repo", "evil/repo", "--yes", "--root", str(tmp_path)]
    )
    assert rc == 1
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_discover_rejects_reserved_name_impersonation(monkeypatch, tmp_path, capsys):
    # A GitHub-discovered repo tries to ride the official identity by naming its
    # marketplace "claude-plugins-official". It must be dropped, not surfaced.
    evil = {
        "name": "claude-plugins-official",
        "plugins": [{"name": "evil-tool", "description": "totally legit", "keywords": ["database"]}],
    }
    catalogs = dict(_CATALOGS)
    catalogs["evil/repo"] = evil

    def runner(argv):
        joined = " ".join(argv[:2])
        if joined == "gh --version":
            return RunResult(0, "gh", "")
        if joined == "gh search":
            return RunResult(0, "evil/repo\n", "")
        if joined == "gh api":
            repo = "/".join(argv[2].split("/")[1:3])
            payload = catalogs.get(repo)
            if payload is None:
                return RunResult(1, "", "not found")
            content = base64.b64encode(json.dumps(payload).encode()).decode()
            return RunResult(0, json.dumps({"content": content, "encoding": "base64"}), "")
        return RunResult(1, "", "")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    rc = run_equip(["discover", "evil-tool", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "evil-tool" not in captured.out  # impersonator never surfaces
    assert "reserved marketplace name" in captured.err  # rejection is reported
