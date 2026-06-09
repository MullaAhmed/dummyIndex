"""CLI: equip discover + install (fake runner — no live network).

The fake runner returns a distinct catalog per repo (keyed off the `gh api
repos/<owner>/<repo>/...` argv), mirroring reality: each marketplace.json
carries its own `name`, which is the identifier a user types in
`<plugin>@<marketplace>` and the key we register under.
"""
import base64
import json

from dummyindex.cli.equip import _cmd_equip
from dummyindex.context.domains.equip import RunResult

_PG = {
    "name": "pg-tuner",
    "description": "Postgres performance",
    "keywords": ["database", "performance"],
    "hooks": "./h.json",  # runs code
}

# A plugin only present in a GitHub-discovered (untrusted) marketplace.
_VECTOR = {"name": "vector-db", "description": "semantic vector store", "keywords": ["search"]}

# repo -> catalog payload (name == the registered marketplace identifier)
_CATALOGS = {
    "anthropics/claude-plugins-official": {"name": "claude-plugins-official", "plugins": [_PG]},
    "anthropics/claude-plugins-community": {"name": "claude-plugins-community", "plugins": [_PG]},
    "octo/extra-plugins": {"name": "extra-plugins", "plugins": [_VECTOR]},
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

    monkeypatch.setattr("dummyindex.cli._equip_discover._RUNNER", runner, raising=False)
    return runner


def test_discover_query_prints_plan(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = _cmd_equip(["discover", "postgres performance", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pg-tuner" in out
    assert "blast radius" in out.lower()
    assert "--yes" in out or "approval" in out.lower()


def test_discover_writes_nothing(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    _cmd_equip(["discover", "postgres", "--root", str(tmp_path)])
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_discover_auto_no_context_does_not_crash(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    assert _cmd_equip(["discover", "--root", str(tmp_path)]) == 0


def test_install_trusted_native_writes_settings_and_manifest(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = _cmd_equip(["install", "pg-tuner@claude-plugins-official", "--root", str(tmp_path)])
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
    rc = _cmd_equip(["install", "pg-tuner@claude-plugins-community", "--root", str(tmp_path)])
    assert rc == 1
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_untrusted_codeplugin_allowed_with_yes(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = _cmd_equip(
        ["install", "pg-tuner@claude-plugins-community", "--yes", "--root", str(tmp_path)]
    )
    assert rc == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert settings["enabledPlugins"]["pg-tuner@claude-plugins-community"] is True


def test_install_unknown_target_errors(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = _cmd_equip(["install", "nope@claude-plugins-official", "--root", str(tmp_path)])
    assert rc == 1


def test_install_invalid_scope_errors(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = _cmd_equip(
        ["install", "pg-tuner@claude-plugins-official", "--scope", "global", "--root", str(tmp_path)]
    )
    assert rc == 2


def test_install_local_scope_writes_local_settings_and_records_path(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = _cmd_equip(
        ["install", "pg-tuner@claude-plugins-official", "--scope", "local", "--root", str(tmp_path)]
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
    rc = _cmd_equip(["discover", "vector", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    # vector-db lives only in the GitHub-discovered (untrusted) marketplace
    assert "vector-db@extra-plugins" in out
    assert "untrusted" in out


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

    monkeypatch.setattr("dummyindex.cli._equip_discover._RUNNER", runner, raising=False)
    rc = _cmd_equip(["discover", "evil-tool", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "evil-tool" not in captured.out  # impersonator never surfaces
    assert "reserved marketplace name" in captured.err  # rejection is reported
