"""CLI: equip discover + install (fake runner — no live network).

The fake runner returns a distinct catalog per repo (keyed off the `gh api
repos/<owner>/<repo>/...` argv), mirroring reality: each marketplace.json
carries its own `name`, which is the identifier a user types in
`<plugin>@<marketplace>` and the key we register under.
"""

import base64
import json
import tempfile
from pathlib import Path

from dummyindex.cli.equip import run as run_equip
from dummyindex.cli.equip.discover import _needed_caps
from dummyindex.context.default_plugins import WiredKind
from dummyindex.context.domains.config import default_config, read_config, write_config
from dummyindex.context.domains.equip import RunResult, StackProfile

_PG = {
    "name": "pg-tuner",
    "description": "Postgres performance",
    "version": "3.5.0",  # a versioned listing — regression bait for the ref bug
    "keywords": ["database", "performance"],
    "hooks": "./h.json",  # runs code
}

# A plugin only present in a GitHub-discovered (untrusted) marketplace.
_VECTOR = {
    "name": "vector-db",
    "description": "semantic vector store",
    "keywords": ["search"],
}

# A plugin in a low-profile repo that `gh search` does NOT surface — reachable
# only when the user names it explicitly via `--repo` (the canvas-to-code case).
_CANVAS = {
    "name": "canvas-tool",
    "description": "obscure design plugin",
    "keywords": ["design"],
}

# repo -> catalog payload (name == the registered marketplace identifier)
_CATALOGS = {
    "anthropics/claude-plugins-official": {
        "name": "claude-plugins-official",
        "plugins": [_PG],
    },
    "anthropics/claude-plugins-community": {
        "name": "claude-plugins-community",
        "plugins": [_PG],
    },
    "octo/extra-plugins": {"name": "extra-plugins", "plugins": [_VECTOR]},
    # Present in the API (fetchable) but absent from `gh search` results below.
    "lowprofile/canvas-mp": {"name": "canvas-mp", "plugins": [_CANVAS]},
}


def _install_fake_runner(monkeypatch, *, catalogs=None, home=None, record=None):
    """Install the fake gh runner and isolate HOME.

    HOME isolation matters: the discover/install path now reads locally-declared
    marketplaces from ``~/.claude`` — tests must never see the developer's real
    plugin state. ``catalogs`` overrides the repo->payload table; ``record``
    (a list) captures every argv the runner sees.
    """
    table = catalogs if catalogs is not None else _CATALOGS
    home_dir = (
        Path(home) if home is not None else Path(tempfile.mkdtemp(prefix="di-home-"))
    )
    home_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home_dir))

    def runner(argv):
        if record is not None:
            record.append(list(argv))
        joined = " ".join(argv[:2])
        if joined == "gh --version":
            return RunResult(0, "gh", "")
        if joined == "gh search":
            return RunResult(0, "octo/extra-plugins\n", "")  # GitHub-discovered repo
        if joined == "gh api":
            # argv[2] == "repos/<owner>/<repo>/contents/.claude-plugin/marketplace.json"
            spec = argv[2]
            repo = "/".join(spec.split("/")[1:3])
            payload = table.get(repo)
            if payload is None:
                return RunResult(1, "", "not found")
            content = base64.b64encode(json.dumps(payload).encode()).decode()
            return RunResult(
                0, json.dumps({"content": content, "encoding": "base64"}), ""
            )
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
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
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
    assert manifest["schema_version"] == 4


def test_install_untrusted_codeplugin_refused_without_yes(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-community", "--root", str(tmp_path)]
    )
    assert rc == 1
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_untrusted_codeplugin_allowed_with_yes(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-community",
            "--yes",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
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
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--scope",
            "global",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 2


def test_install_local_scope_writes_local_settings_and_records_path(
    monkeypatch, tmp_path
):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--scope",
            "local",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert not (tmp_path / ".claude" / "settings.json").exists()
    local = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
    assert local["enabledPlugins"]["pg-tuner@claude-plugins-official"] is True
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(
        i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official"
    )
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
            "install",
            "canvas-tool@canvas-mp",
            "--repo",
            "lowprofile/canvas-mp",
            "--yes",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
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
        [
            "install",
            "canvas-tool@canvas-mp",
            "--repo",
            "lowprofile/canvas-mp",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_explicit_repo_malformed_errors(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "canvas-tool@canvas-mp",
            "--repo",
            "notarepo",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 2


def test_discover_explicit_repo_malformed_errors(monkeypatch, tmp_path):
    # run_discover and run_install share _parse_repo_flag but are wired
    # independently — guard the discover verb's validation path too.
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["discover", "canvas", "--repo", "notarepo", "--root", str(tmp_path)]
    )
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
        [
            "install",
            "ghost@nowhere",
            "--repo",
            "lowprofile/canvas-mp",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert "low-profile" not in capsys.readouterr().err


def test_discover_explicit_repo_surfaces_undiscoverable_plugin(
    monkeypatch, tmp_path, capsys
):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "discover",
            "canvas",
            "--repo",
            "lowprofile/canvas-mp",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "canvas-tool@canvas-mp" in out
    assert "untrusted" in out  # explicit repo is never auto-trusted


def test_explicit_repo_fetch_failure_warns(monkeypatch, tmp_path, capsys):
    # A repo the user named explicitly but whose marketplace.json can't be read
    # (absent / private / transient gh API error) must warn — not be silently
    # dropped into a generic "not found" (the canvas-to-code failure mode).
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["discover", "canvas", "--repo", "ghost/missing", "--root", str(tmp_path)]
    )
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
        "plugins": [
            {
                "name": "evil-tool",
                "description": "totally legit",
                "keywords": ["database"],
            }
        ],
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
            return RunResult(
                0, json.dumps({"content": content, "encoding": "base64"}), ""
            )
        return RunResult(1, "", "")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    rc = run_equip(
        [
            "install",
            "evil-tool@claude-plugins-official",
            "--repo",
            "evil/repo",
            "--yes",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_requires_usage_doc_or_skip(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-official", "--root", str(tmp_path)]
    )
    assert rc == 2
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_usage_doc_and_skip_conflict(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    doc = tmp_path / "play.md"
    doc.write_text("# how to use\n")
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--usage-doc",
            str(doc),
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 2


def test_install_usage_doc_missing_file_errors(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--usage-doc",
            str(tmp_path / "nope.md"),
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_install_usage_doc_recorded_in_grounded_in(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    doc = tmp_path / ".context" / "equipment" / "pg-tuner.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# pg-tuner — usage in this repo\n")
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--usage-doc",
            str(doc),
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(
        i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official"
    )
    assert item["grounded_in"] == [".context/equipment/pg-tuner.md"]


def test_install_skip_usage_doc_leaves_grounded_in_empty(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(
        i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official"
    )
    assert item["grounded_in"] == []


def test_install_approval_error_precedes_usage_gate(monkeypatch, tmp_path):
    # An untrusted plugin without --yes fails on approval (rc 1) before the usage
    # gate is evaluated — approval keeps priority.
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["install", "pg-tuner@claude-plugins-community", "--root", str(tmp_path)]
    )
    assert rc == 1


def test_install_usage_doc_outside_repo_recorded_absolute(
    monkeypatch, tmp_path, capsys
):
    # A playbook outside the repo root is recorded as an absolute path, with a
    # warning that it won't travel with the committed manifest.
    _install_fake_runner(monkeypatch)
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "external.md"  # sibling of proj, outside the repo root
    outside.write_text("# external playbook\n")
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--usage-doc",
            str(outside),
            "--root",
            str(root),
        ]
    )
    assert rc == 0
    assert "outside the repo" in capsys.readouterr().err
    manifest = json.loads((root / ".context" / "equipment.json").read_text())
    item = next(
        i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official"
    )
    assert item["grounded_in"] == [str(outside.resolve())]


def test_discover_rejects_reserved_name_impersonation(monkeypatch, tmp_path, capsys):
    # A GitHub-discovered repo tries to ride the official identity by naming its
    # marketplace "claude-plugins-official". It must be dropped, not surfaced.
    evil = {
        "name": "claude-plugins-official",
        "plugins": [
            {
                "name": "evil-tool",
                "description": "totally legit",
                "keywords": ["database"],
            }
        ],
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
            return RunResult(
                0, json.dumps({"content": content, "encoding": "base64"}), ""
            )
        return RunResult(1, "", "")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    rc = run_equip(["discover", "evil-tool", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "evil-tool" not in captured.out  # impersonator never surfaces
    assert "reserved marketplace name" in captured.err  # rejection is reported


def test_install_relative_usage_doc_resolves_against_root(monkeypatch, tmp_path):
    # A relative --usage-doc resolves against --root (project_root), not the CWD.
    _install_fake_runner(monkeypatch)
    (tmp_path / "play.md").write_text("# usage\n")
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--usage-doc",
            "play.md",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(
        i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official"
    )
    assert item["grounded_in"] == ["play.md"]


def test_install_approval_error_precedes_usage_gate_even_with_doc(
    monkeypatch, tmp_path
):
    # Untrusted plugin with a valid --usage-doc but no --yes still fails on
    # approval (rc 1) — the gate sits after the approval check.
    _install_fake_runner(monkeypatch)
    (tmp_path / "play.md").write_text("# usage\n")
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-community",
            "--usage-doc",
            "play.md",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1


# ----- P0: resolve marketplaces Claude Code already knows --------------------
#
# REGRESSION (audit 2026-06-13, C4-P0): `install canvas-to-code@canvas-to-code-
# marketplace` failed "not found in known marketplaces" even though the
# marketplace was declared in the very settings.json install writes to, present
# in ~/.claude/plugins/known_marketplaces.json, and cloned on disk. The
# candidate universe must include locally-declared marketplaces.

_LOCAL_MKT = {
    "name": "canvas-to-code-marketplace",
    "plugins": [
        {"name": "canvas-to-code", "description": "design bridge", "version": "0.5.0"}
    ],
}


def _declare_project_marketplace(
    root, name="canvas-to-code-marketplace", repo="lowkey/canvas-to-code"
):
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(
            {
                "extraKnownMarketplaces": {
                    name: {"source": {"source": "github", "repo": repo}}
                }
            }
        ),
        encoding="utf-8",
    )


def test_install_resolves_marketplace_declared_in_project_settings(
    monkeypatch, tmp_path
):
    # The marketplace is declared in committed project settings; `gh search`
    # does NOT return its repo and it is not a seed — install must still
    # resolve it (it falls back to fetching the declared repo's catalog).
    catalogs = dict(_CATALOGS)
    catalogs["lowkey/canvas-to-code"] = _LOCAL_MKT
    _install_fake_runner(monkeypatch, catalogs=catalogs)
    _declare_project_marketplace(tmp_path)
    rc = run_equip(
        [
            "install",
            "canvas-to-code@canvas-to-code-marketplace",
            "--yes",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert (
        settings["enabledPlugins"]["canvas-to-code@canvas-to-code-marketplace"] is True
    )


def test_install_resolves_marketplace_from_known_marketplaces_json(
    monkeypatch, tmp_path
):
    home = tmp_path / "home"
    catalogs = dict(_CATALOGS)
    catalogs["lowkey/canvas-to-code"] = _LOCAL_MKT
    _install_fake_runner(monkeypatch, catalogs=catalogs, home=home)
    known = home / ".claude" / "plugins" / "known_marketplaces.json"
    known.parent.mkdir(parents=True)
    known.write_text(
        json.dumps(
            {
                "canvas-to-code-marketplace": {
                    "source": {"source": "github", "repo": "lowkey/canvas-to-code"},
                    "installLocation": str(
                        home
                        / ".claude"
                        / "plugins"
                        / "marketplaces"
                        / "canvas-to-code-marketplace"
                    ),
                    "lastUpdated": "2026-06-12T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "proj"
    root.mkdir()
    rc = run_equip(
        [
            "install",
            "canvas-to-code@canvas-to-code-marketplace",
            "--yes",
            "--skip-usage-doc",
            "--root",
            str(root),
        ]
    )
    assert rc == 0
    settings = json.loads((root / ".claude" / "settings.json").read_text())
    assert (
        settings["enabledPlugins"]["canvas-to-code@canvas-to-code-marketplace"] is True
    )


def test_declared_marketplace_local_clone_used_without_network(monkeypatch, tmp_path):
    # The on-disk clone's marketplace.json is preferred — no gh api fetch for
    # the declared repo is issued.
    home = tmp_path / "home"
    runner_calls = []
    _install_fake_runner(monkeypatch, home=home, record=runner_calls)
    clone = home / ".claude" / "plugins" / "marketplaces" / "canvas-to-code-marketplace"
    (clone / ".claude-plugin").mkdir(parents=True)
    (clone / ".claude-plugin" / "marketplace.json").write_text(json.dumps(_LOCAL_MKT))
    known = home / ".claude" / "plugins" / "known_marketplaces.json"
    known.write_text(
        json.dumps(
            {
                "canvas-to-code-marketplace": {
                    "source": {"source": "github", "repo": "lowkey/canvas-to-code"},
                    "installLocation": str(clone),
                }
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "proj"
    root.mkdir()
    rc = run_equip(
        [
            "install",
            "canvas-to-code@canvas-to-code-marketplace",
            "--yes",
            "--skip-usage-doc",
            "--root",
            str(root),
        ]
    )
    assert rc == 0
    fetched = [
        argv
        for argv in runner_calls
        if argv[:2] == ["gh", "api"] and "lowkey/canvas-to-code" in argv[2]
    ]
    assert fetched == []  # local clone served the catalog; no network fetch


def test_discover_surfaces_declared_marketplace_plugins(monkeypatch, tmp_path, capsys):
    catalogs = dict(_CATALOGS)
    catalogs["lowkey/canvas-to-code"] = _LOCAL_MKT
    _install_fake_runner(monkeypatch, catalogs=catalogs)
    _declare_project_marketplace(tmp_path)
    rc = run_equip(
        ["discover", "canvas to code design bridge", "--root", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "canvas-to-code@canvas-to-code-marketplace" in out


# ----- P0: the plugin's semver must never become the marketplace git ref -----


def test_install_never_writes_plugin_version_as_marketplace_ref(monkeypatch, tmp_path):
    # REGRESSION (audit C4-P0): install wrote the PLUGIN's listing semver as the
    # MARKETPLACE repo's git ref ({source: {repo, ref: "3.5.0"}}). The repo has
    # no such tag, so Claude Code's native fetch of the marketplace failed —
    # breaking every plugin from that marketplace.
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    source = settings["extraKnownMarketplaces"]["claude-plugins-official"]["source"]
    assert "ref" not in source  # never the plugin semver


def test_install_records_plugin_kind_and_catalog_version(monkeypatch, tmp_path):
    # The manifest entry is a PLUGIN (not a dispatchable agent) and carries the
    # catalog version; origin_ref no longer mis-records the semver.
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(
        i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official"
    )
    assert item["kind"] == "plugin"
    assert item["version"] == "3.5.0"
    assert item["origin_ref"] is None


def test_install_rewire_repairs_stale_semver_ref(monkeypatch, tmp_path):
    # A repo poisoned by the old bug carries ref="3.5.0"; re-installing the same
    # target rewrites the marketplace entry WITHOUT the bogus ref.
    _install_fake_runner(monkeypatch)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "extraKnownMarketplaces": {
                    "claude-plugins-official": {
                        "source": {
                            "source": "github",
                            "repo": "anthropics/claude-plugins-official",
                            "ref": "3.5.0",
                        }
                    }
                },
                "enabledPlugins": {"pg-tuner@claude-plugins-official": True},
            }
        )
    )
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    source = json.loads(settings_path.read_text())["extraKnownMarketplaces"][
        "claude-plugins-official"
    ]["source"]
    assert "ref" not in source


# ----- --repo dead-ends fixed (audit C4-P1) ----------------------------------


def test_discover_repo_without_query_lists_its_plugins(monkeypatch, tmp_path, capsys):
    # REGRESSION: `discover --repo X` with no query printed "no matching
    # plugins found" and advised adding the --repo flag that was just used.
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        ["discover", "--repo", "lowprofile/canvas-mp", "--root", str(tmp_path)]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "canvas-tool@canvas-mp" in out
    assert "from --repo lowprofile/canvas-mp" in out  # labeled
    assert "add --repo" not in out  # tip suppressed when the flag was given


def test_discover_repo_accepts_github_url(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "discover",
            "--repo",
            "https://github.com/lowprofile/canvas-mp.git",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "canvas-tool@canvas-mp" in out


def test_discover_repo_fetch_failure_noted_on_stdout(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = run_equip(["discover", "--repo", "ghost/missing", "--root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "--repo ghost/missing" in captured.out  # stdout, not just stderr


def test_discover_explicit_repo_wins_name_collision_over_search(
    monkeypatch, tmp_path, capsys
):
    # A search-discovered catalog claiming the same marketplace name must LOSE
    # to the explicitly named repo.
    catalogs = dict(_CATALOGS)
    catalogs["octo/extra-plugins"] = {
        "name": "canvas-mp",  # search result claims the --repo catalog's name
        "plugins": [{"name": "squatter", "description": "canvas design tool"}],
    }
    _install_fake_runner(monkeypatch, catalogs=catalogs)
    rc = run_equip(
        [
            "discover",
            "canvas",
            "--repo",
            "lowprofile/canvas-mp",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "canvas-tool@canvas-mp" in out
    assert "squatter" not in out


# ----- trust gate: prior approval from existing settings (audit C4-P1) -------


def test_install_already_enabled_target_skips_yes_gate(monkeypatch, tmp_path, capsys):
    # The exact target is already enabled in committed project settings — the
    # blast radius was accepted; re-registering must not demand --yes again.
    _install_fake_runner(monkeypatch)
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"enabledPlugins": {"vector-db@extra-plugins": True}}),
        encoding="utf-8",
    )
    rc = run_equip(
        [
            "install",
            "vector-db@extra-plugins",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "already enabled" in out
    data = json.loads(settings.read_text())
    assert data["enabledPlugins"]["vector-db@extra-plugins"] is True


def test_install_new_untrusted_target_still_requires_yes(monkeypatch, tmp_path):
    # A DIFFERENT (new) untrusted target keeps the gate.
    _install_fake_runner(monkeypatch)
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"enabledPlugins": {"something-else@extra-plugins": True}}),
        encoding="utf-8",
    )
    rc = run_equip(
        [
            "install",
            "vector-db@extra-plugins",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1


# ----- post-install verification (audit C4-P1) --------------------------------


def test_install_prints_restart_and_verify_guidance(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "session start" in out
    assert "equip verify" in out


def test_install_preflight_warns_when_repo_unreachable(monkeypatch, tmp_path, capsys):
    # The fake runner fails `git ls-remote` (unknown argv) — install must warn
    # that the native fetch may fail, without blocking.
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert "native marketplace fetch may fail" in capsys.readouterr().err


def test_verify_reports_loaded_plugin(monkeypatch, tmp_path, capsys):
    home = tmp_path / "home"
    _install_fake_runner(monkeypatch, home=home)
    plugins_dir = home / ".claude" / "plugins"
    (plugins_dir / "marketplaces" / "claude-plugins-official").mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "pg-tuner@claude-plugins-official": [
                        {"scope": "project", "installPath": "/x", "version": "3.5.0"}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    rc = run_equip(["verify", "pg-tuner@claude-plugins-official"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "loaded: yes" in out
    assert "3.5.0" in out


def test_verify_declared_but_not_loaded_exits_1(monkeypatch, tmp_path, capsys):
    home = tmp_path / "home"
    _install_fake_runner(monkeypatch, home=home)
    rc = run_equip(["verify", "pg-tuner@claude-plugins-official"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "loaded: NO" in out
    assert "restart" in out


def test_verify_requires_target_rc2(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch, home=tmp_path / "home")
    assert run_equip(["verify"]) == 2


# ----- --capabilities override (audit C4-P1) ----------------------------------


def test_install_capabilities_override_recorded_exactly(monkeypatch, tmp_path):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--capabilities",
            "database,frontend",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(
        i for i in manifest["items"] if i["name"] == "pg-tuner@claude-plugins-official"
    )
    assert item["capabilities"] == ["database", "frontend"]


def test_install_unknown_capability_rc2(monkeypatch, tmp_path, capsys):
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--capabilities",
            "blockchain",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 2
    assert "blockchain" in capsys.readouterr().err


# ----- equip install write-back to config.wired (config-depth-wired-ux) -------
#
# `equip install` is the declared-intent writer: alongside the equipment.json
# MARKETPLACE record, it upserts a matching WiredEntry into the committed
# config.json keyed on <plugin>@<marketplace>. The two ledgers must agree on that
# key (config.wired = intent; equipment.json = render manifest) and not diverge.


def _seed_committed_config(root):
    """Write a fresh committed config.json under ``root/.context`` and return it."""
    context_dir = root / ".context"
    context_dir.mkdir(parents=True, exist_ok=True)
    write_config(context_dir, default_config())


def test_install_upserts_wired_and_agrees_with_manifest(monkeypatch, tmp_path):
    # Project scope, committed config present: the install records both the
    # equipment.json MARKETPLACE item AND a matching config.wired entry, and the
    # two agree on the <plugin>@<marketplace> key (they don't diverge).
    _install_fake_runner(monkeypatch)
    _seed_committed_config(tmp_path)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0

    config = read_config(tmp_path / ".context")
    wired_targets = {e.target for e in config.wired}
    assert "pg-tuner@claude-plugins-official" in wired_targets
    entry = next(
        e for e in config.wired if e.target == "pg-tuner@claude-plugins-official"
    )
    assert entry.kind == WiredKind.PLUGIN
    assert entry.version == "3.5.0"  # descriptive catalog version recorded

    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    names = {i["name"] for i in manifest["items"]}
    assert "pg-tuner@claude-plugins-official" in names
    # The shared key keeps the two ledgers reconcilable — they agree, not diverge.
    assert entry.target in names


def test_install_reinstall_upserts_no_duplicate_wired(monkeypatch, tmp_path):
    # Re-installing the same target upserts (replace-by-key), never appends a
    # duplicate config.wired entry.
    _install_fake_runner(monkeypatch)
    _seed_committed_config(tmp_path)
    args = [
        "install",
        "pg-tuner@claude-plugins-official",
        "--skip-usage-doc",
        "--root",
        str(tmp_path),
    ]
    assert run_equip(args) == 0
    assert run_equip(args) == 0
    config = read_config(tmp_path / ".context")
    matching = [
        e for e in config.wired if e.target == "pg-tuner@claude-plugins-official"
    ]
    assert len(matching) == 1


def test_install_user_scope_writes_no_config_and_does_not_raise(monkeypatch, tmp_path):
    # --scope user (personal ~/.claude) is never written back to a repo config —
    # and with no committed config.json present, the write-back is skipped and
    # nothing is created.
    home = tmp_path / "home"
    _install_fake_runner(monkeypatch, home=home)
    root = tmp_path / "proj"
    root.mkdir()
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--scope",
            "user",
            "--skip-usage-doc",
            "--root",
            str(root),
        ]
    )
    assert rc == 0
    assert not (root / ".context" / "config.json").exists()


def test_install_absent_config_skips_write_back_with_warning(
    monkeypatch, tmp_path, capsys
):
    # Project scope but NO committed config.json: the install succeeds, records
    # the manifest, and skips the wired write-back with a warning — it never
    # materialises a seeded config as a side effect.
    _install_fake_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert not (tmp_path / ".context" / "config.json").exists()
    err = capsys.readouterr().err
    assert "config.wired" in err
    # The manifest record is still intact.
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    assert any(
        i["name"] == "pg-tuner@claude-plugins-official" for i in manifest["items"]
    )


def test_install_write_config_failure_warned_and_continues(
    monkeypatch, tmp_path, capsys
):
    # An injected write_config failure is warned-and-continued: the install rc is
    # unchanged (0) and the equipment.json manifest record is intact — the
    # exception never escapes run_install.
    _install_fake_runner(monkeypatch)
    _seed_committed_config(tmp_path)

    def boom(context_dir, config):
        raise OSError("disk full")

    monkeypatch.setattr("dummyindex.cli.equip.install.write_config", boom)
    rc = run_equip(
        [
            "install",
            "pg-tuner@claude-plugins-official",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "config.json not updated" in err
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    assert any(
        i["name"] == "pg-tuner@claude-plugins-official" for i in manifest["items"]
    )


# ----- _needed_caps gap-awareness (T1b) -------------------------------------


def _write_manifest(tmp_path: Path, caps: list[str]) -> None:
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True, exist_ok=True)
    (ctx / "equipment.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "items": [
                    {
                        "kind": "agent",
                        "name": "impl",
                        "path": ".claude/agents/impl.md",
                        "source": "generated",
                        "capabilities": caps,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_needed_caps_excludes_capabilities_already_covered(monkeypatch, tmp_path):
    # The old stub returned ("test","implement") off the stack regardless of the
    # manifest. Now a fully-equipped repo reports NO gap.
    monkeypatch.setattr(
        "dummyindex.cli.equip.discover.detect_stack",
        lambda _ctx: StackProfile(
            label="python", test_runner="pytest", formatter="ruff"
        ),
    )
    _write_manifest(tmp_path, ["implement", "test", "review", "verify", "format"])
    assert _needed_caps(tmp_path) == ()


def test_needed_caps_surfaces_uncovered_stack_gap(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "dummyindex.cli.equip.discover.detect_stack",
        lambda _ctx: StackProfile(label="python", test_runner="pytest"),
    )
    # No manifest at all → the stack baseline itself is the gap.
    gaps = _needed_caps(tmp_path)
    assert "implement" in gaps
    assert "test" in gaps


def test_needed_caps_degrades_on_unreadable_manifest(monkeypatch, tmp_path, capsys):
    # A corrupt equipment.json must not crash discover; it degrades to a
    # stack-only gap and warns on stderr (mirrors _record_native's handling).
    monkeypatch.setattr(
        "dummyindex.cli.equip.discover.detect_stack",
        lambda _ctx: StackProfile(label="python", test_runner="pytest"),
    )
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True)
    (ctx / "equipment.json").write_text("{ not valid json", encoding="utf-8")
    gaps = _needed_caps(tmp_path)
    assert "implement" in gaps
    assert "test" in gaps
    assert "unreadable" in capsys.readouterr().err


# ----- Wave 3: vendor install of collection skills (auto-vendor-skills) ------

_SHA = "d" * 40

# Keyed by SEED repo. vercel-labs/agent-skills -> seed "vercel-agent-skills"
# (TRUSTED); msitarzewski/agency-agents -> seed "agency-agents" (UNTRUSTED).
_COLLECTION_SKILLS = {
    "vercel-labs/agent-skills": {
        "code-review": "---\nname: code-review\n---\n# Code review skill\n",
        "pdf": "---\nname: pdf\n---\n# PDF skill\n",
    },
    "msitarzewski/agency-agents": {
        "growth": "---\nname: growth\n---\n# Growth skill\n",
    },
}


def _install_collection_runner(monkeypatch, *, record=None):
    home_dir = Path(tempfile.mkdtemp(prefix="di-home-"))
    monkeypatch.setenv("HOME", str(home_dir))

    def runner(argv):
        if record is not None:
            record.append(list(argv))
        j2 = " ".join(argv[:2])
        if j2 == "gh --version":
            return RunResult(0, "gh", "")
        if j2 == "gh search":
            return RunResult(0, "", "")  # no extra discovered repos
        if argv[:2] == ["git", "ls-remote"]:
            return RunResult(0, "", "")
        if j2 != "gh api":
            return RunResult(1, "", "")
        endpoint = argv[2].partition("?")[0]
        for repo, skills in _COLLECTION_SKILLS.items():
            if endpoint == f"repos/{repo}/commits/HEAD":
                return RunResult(0, json.dumps({"sha": _SHA}), "")
            if endpoint == f"repos/{repo}/contents/skills":
                listing = [
                    {"type": "dir", "name": n, "path": f"skills/{n}"} for n in skills
                ]
                return RunResult(0, json.dumps(listing), "")
            for n, text in skills.items():
                if endpoint == f"repos/{repo}/contents/skills/{n}/SKILL.md":
                    blob = base64.b64encode(text.encode()).decode()
                    return RunResult(
                        0, json.dumps({"content": blob, "encoding": "base64"}), ""
                    )
        return RunResult(1, "", "not found")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    return runner


def test_install_vendors_skill_from_trusted_collection(monkeypatch, tmp_path):
    _install_collection_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "code-review@vercel-agent-skills",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    skill_file = tmp_path / ".claude" / "skills" / "code-review" / "SKILL.md"
    assert skill_file.is_file()
    body = skill_file.read_text()
    assert body.startswith("<!-- dummyindex:installed -->")
    assert "Code review skill" in body
    # vendor copies a file — it must NOT write native settings wiring
    assert not (tmp_path / ".claude" / "settings.json").exists()
    manifest = json.loads((tmp_path / ".context" / "equipment.json").read_text())
    item = next(
        i for i in manifest["items"] if i["name"] == "code-review@vercel-agent-skills"
    )
    assert item["source"] == "vendored"
    assert item["mechanism"] == "vendor"
    assert item["kind"] == "skill"
    assert item["origin_repo"] == "vercel-labs/agent-skills"
    assert item["origin_ref"] == _SHA  # pinned sha — not None, not a semver
    assert item["path"] == ".claude/skills/code-review/SKILL.md"


def test_install_vendor_pins_commit_ref_in_fetch(monkeypatch, tmp_path):
    rec: list = []
    _install_collection_runner(monkeypatch, record=rec)
    run_equip(
        [
            "install",
            "pdf@vercel-agent-skills",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    want = f"repos/vercel-labs/agent-skills/contents/skills/pdf/SKILL.md?ref={_SHA}"
    assert any(a[:2] == ["gh", "api"] and a[2] == want for a in rec)


def test_install_vendor_untrusted_collection_requires_yes(monkeypatch, tmp_path):
    _install_collection_runner(monkeypatch)
    rc = run_equip(
        ["install", "growth@agency-agents", "--skip-usage-doc", "--root", str(tmp_path)]
    )
    assert rc == 1
    assert not (tmp_path / ".claude" / "skills" / "growth" / "SKILL.md").exists()


def test_install_vendor_untrusted_with_yes_vendors(monkeypatch, tmp_path):
    _install_collection_runner(monkeypatch)
    rc = run_equip(
        [
            "install",
            "growth@agency-agents",
            "--yes",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert (tmp_path / ".claude" / "skills" / "growth" / "SKILL.md").is_file()


def test_install_vendor_never_clobbers_user_skill(monkeypatch, tmp_path):
    _install_collection_runner(monkeypatch)
    target = tmp_path / ".claude" / "skills" / "code-review" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("MY OWN SKILL — do not touch\n")  # no sentinel => user file
    rc = run_equip(
        [
            "install",
            "code-review@vercel-agent-skills",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert target.read_text() == "MY OWN SKILL — do not touch\n"  # untouched


def test_install_vendor_reinstall_overwrites_own_file(monkeypatch, tmp_path):
    _install_collection_runner(monkeypatch)
    args = [
        "install",
        "code-review@vercel-agent-skills",
        "--skip-usage-doc",
        "--root",
        str(tmp_path),
    ]
    assert run_equip(args) == 0
    assert run_equip(args) == 0  # re-vendoring our own file is allowed
    target = tmp_path / ".claude" / "skills" / "code-review" / "SKILL.md"
    assert target.read_text().startswith("<!-- dummyindex:installed -->")


def test_install_vendor_rejects_unsafe_skill_name(monkeypatch, tmp_path):
    # A collection listing that yields a path-separator name must be refused —
    # the vendored skill name must never escape .claude/skills/.
    monkeypatch.setenv("HOME", str(Path(tempfile.mkdtemp(prefix="di-home-"))))

    def runner(argv):
        j2 = " ".join(argv[:2])
        if j2 == "gh --version":
            return RunResult(0, "gh", "")
        if j2 == "gh search":
            return RunResult(0, "", "")
        if j2 != "gh api":
            return RunResult(1, "", "")
        ep = argv[2].partition("?")[0]
        if ep == "repos/vercel-labs/agent-skills/contents/skills":
            listing = [{"type": "dir", "name": "a/b", "path": "skills/a/b"}]
            return RunResult(0, json.dumps(listing), "")
        return RunResult(1, "", "not found")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    rc = run_equip(
        [
            "install",
            "a/b@vercel-agent-skills",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert not (tmp_path / ".claude" / "skills" / "a").exists()


def test_install_vendor_reinstall_refuses_edited_file(monkeypatch, tmp_path, capsys):
    # Re-installing over a vendored skill the user has hand-edited must REFUSE —
    # the same origin-hash oracle refresh/uninstall use freezes it, so a re-run
    # never silently discards the edit (even though it still carries our sentinel).
    _install_collection_runner(monkeypatch)
    args = [
        "install",
        "code-review@vercel-agent-skills",
        "--skip-usage-doc",
        "--root",
        str(tmp_path),
    ]
    assert run_equip(args) == 0
    target = tmp_path / ".claude" / "skills" / "code-review" / "SKILL.md"
    edited = target.read_text() + "\n# my hand-edit — keep me\n"
    target.write_text(edited)  # USER_MODIFIED: hash now differs from origin_hash
    assert run_equip(args) == 1
    assert target.read_text() == edited  # edit preserved, not clobbered
    assert "has local edits" in capsys.readouterr().err


def test_install_vendor_resolve_ref_source_error(monkeypatch, tmp_path, capsys):
    # commits/HEAD returns a present-but-undecodable body => resolve_ref raises
    # SourceError; install must surface rc 1, not crash. (Discovery never resolves
    # a ref, so the candidate still forms.)
    monkeypatch.setenv("HOME", str(Path(tempfile.mkdtemp(prefix="di-home-"))))
    repo = "vercel-labs/agent-skills"

    def runner(argv):
        j2 = " ".join(argv[:2])
        if j2 == "gh --version":
            return RunResult(0, "gh", "")
        if j2 == "gh search":
            return RunResult(0, "", "")
        if j2 != "gh api":
            return RunResult(1, "", "")
        ep = argv[2].partition("?")[0]
        if ep == f"repos/{repo}/contents/skills":
            listing = [
                {"type": "dir", "name": "code-review", "path": "skills/code-review"}
            ]
            return RunResult(0, json.dumps(listing), "")
        if ep == f"repos/{repo}/commits/HEAD":
            return RunResult(0, "<<not json>>", "")  # present but undecodable
        return RunResult(1, "", "not found")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    rc = run_equip(
        [
            "install",
            "code-review@vercel-agent-skills",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert "could not enumerate skills" in capsys.readouterr().err
    assert not (tmp_path / ".claude" / "skills" / "code-review").exists()


def test_install_vendor_list_skills_source_error(monkeypatch, tmp_path, capsys):
    # The pinned-ref re-enumeration at install raises SourceError (undecodable
    # listing); install must surface rc 1, not crash. Discovery (no ref) succeeds.
    monkeypatch.setenv("HOME", str(Path(tempfile.mkdtemp(prefix="di-home-"))))
    repo = "vercel-labs/agent-skills"

    def runner(argv):
        j2 = " ".join(argv[:2])
        if j2 == "gh --version":
            return RunResult(0, "gh", "")
        if j2 == "gh search":
            return RunResult(0, "", "")
        if j2 != "gh api":
            return RunResult(1, "", "")
        raw = argv[2]
        ep = raw.partition("?")[0]
        if ep == f"repos/{repo}/commits/HEAD":
            return RunResult(0, json.dumps({"sha": _SHA}), "")
        if ep == f"repos/{repo}/contents/skills":
            if "?ref=" in raw:  # install-time re-enum chokes; discovery (no ref) is ok
                return RunResult(0, "<<not json>>", "")
            listing = [
                {"type": "dir", "name": "code-review", "path": "skills/code-review"}
            ]
            return RunResult(0, json.dumps(listing), "")
        return RunResult(1, "", "not found")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    rc = run_equip(
        [
            "install",
            "code-review@vercel-agent-skills",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert "could not enumerate skills" in capsys.readouterr().err


def test_install_vendor_corrupt_manifest_refuses(monkeypatch, tmp_path, capsys):
    # The manifest is the never-clobber oracle; a corrupt equipment.json means we
    # cannot tell a pristine vendored copy from a hand-edited one — install must
    # fail closed with a clean rc 1, not crash with an EquipError traceback.
    _install_collection_runner(monkeypatch)
    ctx = tmp_path / ".context"
    ctx.mkdir(parents=True)
    (ctx / "equipment.json").write_text("{ not valid json", encoding="utf-8")
    rc = run_equip(
        [
            "install",
            "code-review@vercel-agent-skills",
            "--skip-usage-doc",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert "cannot read equipment manifest" in capsys.readouterr().err
    assert not (tmp_path / ".claude" / "skills" / "code-review" / "SKILL.md").exists()


def test_discover_collection_undecodable_listing_degrades(
    monkeypatch, tmp_path, capsys
):
    # A collection seed whose skills listing is present-but-undecodable must not
    # crash discover — `_collection_catalog` degrades to no candidates + a warning.
    monkeypatch.setenv("HOME", str(Path(tempfile.mkdtemp(prefix="di-home-"))))

    def runner(argv):
        j2 = " ".join(argv[:2])
        if j2 == "gh --version":
            return RunResult(0, "gh", "")
        if j2 == "gh search":
            return RunResult(0, "", "")
        if j2 != "gh api":
            return RunResult(1, "", "")
        ep = argv[2].partition("?")[0]
        if ep.endswith("/contents/skills"):
            return RunResult(0, "<<not json>>", "")  # present but undecodable
        return RunResult(1, "", "not found")

    monkeypatch.setattr("dummyindex.cli.equip.discover._RUNNER", runner, raising=False)
    rc = run_equip(["discover", "--root", str(tmp_path)])
    assert rc == 0  # degraded, did not crash
    assert "could not enumerate skills" in capsys.readouterr().err
